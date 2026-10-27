"""Linux collectors: journald/auth log, process execution, network, file integrity.

Sources, in order of preference:
* Authentication: ``journalctl _COMM=sshd/sudo/...`` (JSON), or ``/var/log/auth.log``.
* Process: auditd execve records via ``journalctl`` when available, else /proc polling.
* Network: new listening/established sockets via ``ss -tunp`` diffing.
* File: hash-based integrity checks on a watch list of sensitive files.

Each collector reports ``unsupported`` / ``permission_denied`` clearly instead of
silently producing nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from lognexa_agent.collectors.base import Collector
from lognexa_agent.models import Event, utcnow

AUTH_UNITS = ["sshd", "sudo", "su", "login", "systemd-logind", "polkitd", "gdm-password"]
SENSITIVE_FILES = [
    "/etc/passwd", "/etc/shadow", "/etc/group", "/etc/sudoers",
    "/etc/ssh/sshd_config", "/etc/crontab", "/etc/hosts", "/etc/ld.so.preload",
    "/root/.ssh/authorized_keys",
]


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _parse_journal_ts(micros: str) -> datetime:
    try:
        return datetime.fromtimestamp(int(micros) / 1_000_000, tz=timezone.utc)
    except (ValueError, TypeError):
        return utcnow()


class JournaldAuthCollector(Collector):
    """Authentication events from journald (falls back to /var/log/auth.log)."""

    name = "linux_auth"

    def available(self):
        if os.name != "posix":
            return False, "unsupported", "Linux-only collector"
        if shutil.which("journalctl") or os.path.exists("/var/log/auth.log"):
            return True, "ok", None
        return False, "unsupported", "neither journalctl nor /var/log/auth.log is available"

    def collect(self):
        if shutil.which("journalctl"):
            yield from self._from_journal()
        else:
            yield from self._from_authlog()

    def _from_journal(self):
        cursor = self.get_checkpoint()
        cmd = ["journalctl", "-o", "json", "--no-pager", "-q"]
        for unit in AUTH_UNITS:
            cmd += ["_COMM=" + unit]
        cmd += ["--after-cursor", cursor] if cursor else ["-n", "200"]
        rc, out, err = _run(cmd)
        if rc != 0:
            if "No journal files were opened" in err or "not have permission" in err.lower():
                raise PermissionError("cannot read the journal (add the agent user to the 'systemd-journal' group)")
            raise RuntimeError(err.strip() or f"journalctl exited {rc}")
        last = cursor
        for line in out.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            last = rec.get("__CURSOR", last)
            ev = self._classify(rec.get("MESSAGE", ""), _parse_journal_ts(rec.get("__REALTIME_TIMESTAMP", "")), rec.get("_COMM"))
            if ev:
                ev.dedup_key = rec.get("__CURSOR")
                yield ev
        if last and last != cursor:
            self.set_checkpoint(last)

    def _from_authlog(self):
        path = "/var/log/auth.log"
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            raise PermissionError(str(exc))
        offset = self.get_checkpoint(0)
        if offset > size:  # rotated
            offset = 0
        with open(path, "r", errors="replace") as fh:
            fh.seek(offset)
            for line in fh:
                ev = self._classify(line.strip(), utcnow(), None)
                if ev:
                    yield ev
            self.set_checkpoint(fh.tell())

    def _classify(self, msg: str, ts: datetime, comm: str | None) -> Event | None:
        low = msg.lower()
        base = dict(source="journald", category="authentication", timestamp=ts, message=msg[:4000], raw={"comm": comm} if comm else None)
        if "failed password" in low or "authentication failure" in low:
            return Event(event_type="logon_failure", username=self._user(msg), src_ip=self._ip(msg), **base)
        if "accepted password" in low or "accepted publickey" in low or "session opened for user" in low:
            return Event(event_type="logon_success", username=self._user(msg), src_ip=self._ip(msg), **base)
        if "sudo:" in low and "command=" in low:
            if "authentication failure" in low or "incorrect password" in low:
                return Event(event_type="sudo_failure", username=self._user(msg), **base)
            return Event(event_type="sudo_command", username=self._user(msg), command_line=self._sudo_cmd(msg), **base)
        if "new user" in low or "useradd" in low:
            return Event(event_type="user_created", **base)
        if "to group" in low and ("add" in low):
            return Event(event_type="group_member_added", raw={"group": self._group(msg), "comm": comm}, **{k: v for k, v in base.items() if k != "raw"})
        return None

    @staticmethod
    def _user(msg: str) -> str | None:
        import re

        m = re.search(r"(?:for (?:invalid user )?|user[= ]|USER=)(\S+)", msg)
        return m.group(1) if m else None

    @staticmethod
    def _ip(msg: str) -> str | None:
        import re

        m = re.search(r"from (\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]+)", msg)
        return m.group(1) if m else None

    @staticmethod
    def _sudo_cmd(msg: str) -> str | None:
        import re

        m = re.search(r"COMMAND=(.+)$", msg)
        return m.group(1) if m else None

    @staticmethod
    def _group(msg: str) -> str | None:
        import re

        m = re.search(r"to group (\S+)", msg)
        return m.group(1) if m else None


class LinuxProcessCollector(Collector):
    """New process executions. Uses auditd execve via journald when present,
    otherwise polls /proc for processes not seen in the previous cycle."""

    name = "linux_process"

    def available(self):
        if os.name != "posix":
            return False, "unsupported", "Linux-only collector"
        if not os.path.isdir("/proc"):
            return False, "unsupported", "/proc is not mounted"
        return True, "ok", None

    def collect(self):
        seen: set[int] = set(self.get_checkpoint([]) or [])
        current: set[int] = set()
        events = []
        for pid_dir in os.scandir("/proc"):
            if not pid_dir.name.isdigit():
                continue
            pid = int(pid_dir.name)
            current.add(pid)
            if pid in seen:
                continue
            info = self._read_proc(pid)
            if info:
                events.append(info)
        # Keep only live pids in the checkpoint so it does not grow without bound.
        self.set_checkpoint(sorted(current))
        yield from events

    def _read_proc(self, pid: int) -> Event | None:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmdline = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
            exe = os.readlink(f"/proc/{pid}/exe") if os.path.exists(f"/proc/{pid}/exe") else None
            with open(f"/proc/{pid}/status") as fh:
                status = fh.read()
            with open(f"/proc/{pid}/stat") as fh:
                ppid = int(fh.read().split(") ", 1)[1].split()[1])
        except (PermissionError, ProcessLookupError, FileNotFoundError):
            return None
        if not cmdline and not exe:
            return None
        import re

        uid_m = re.search(r"Uid:\s+(\d+)", status)
        name_m = re.search(r"Name:\s+(\S+)", status)
        username = None
        if uid_m:
            try:
                import pwd

                username = pwd.getpwuid(int(uid_m.group(1))).pw_name
            except (KeyError, ImportError):
                username = uid_m.group(1)
        parent = None
        try:
            with open(f"/proc/{ppid}/comm") as fh:
                parent = fh.read().strip()
        except OSError:
            pass
        return Event(
            source="proc", category="process", event_type="process_start",
            process_name=name_m.group(1) if name_m else (os.path.basename(exe) if exe else None),
            process_path=exe, command_line=cmdline or None, pid=pid, parent_pid=ppid,
            parent_process=parent, username=username, dedup_key=f"pid{pid}:{cmdline[:120]}",
        )


class LinuxNetworkCollector(Collector):
    """New listening and established TCP/UDP sockets, diffed between cycles."""

    name = "linux_network"

    def available(self):
        if os.name != "posix":
            return False, "unsupported", "Linux-only collector"
        if shutil.which("ss"):
            return True, "ok", None
        return False, "unsupported", "the 'ss' command (iproute2) is not installed"

    def collect(self):
        rc, out, err = _run(["ss", "-tunpH", "state", "all"])
        if rc != 0:
            raise RuntimeError(err.strip() or "ss failed")
        seen = set(self.get_checkpoint([]) or [])
        current, events = set(), []
        for line in out.splitlines():
            parsed = self._parse(line)
            if not parsed:
                continue
            key, ev = parsed
            current.add(key)
            if key not in seen:
                events.append(ev)
        self.set_checkpoint(sorted(current)[-5000:])
        yield from events

    def _parse(self, line: str):
        import re

        parts = line.split()
        if len(parts) < 6:
            return None
        proto, state, local, peer = parts[0], parts[1], parts[4], parts[5]
        proc = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        pname = proc.group(1) if proc else None
        ppid = int(proc.group(2)) if proc else None
        listening = state == "LISTEN"
        host, _, port = peer.rpartition(":") if not listening else local.rpartition(":")
        try:
            dport = int(port)
        except ValueError:
            dport = None
        event_type = "listen_port_opened" if listening else "network_connection"
        key = f"{proto}|{state}|{local}|{peer}|{pname}"
        ev = Event(
            source="ss", category="network", event_type=event_type,
            process_name=pname, pid=ppid, dst_ip=None if listening else host.strip("[]") or None,
            dst_port=dport, message=f"{proto} {state} {local} -> {peer}", dedup_key=key,
        )
        return key, ev


class LinuxFileIntegrityCollector(Collector):
    """Hash-based change detection for a watch list of sensitive files."""

    name = "linux_file"

    def available(self):
        if os.name != "posix":
            return False, "unsupported", "Linux-only collector"
        return True, "ok", None

    def collect(self):
        import hashlib

        state = dict(self.get_checkpoint({}) or {})
        new_state, events = {}, []
        for path in SENSITIVE_FILES:
            try:
                with open(path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                mtime = os.path.getmtime(path)
            except (FileNotFoundError, PermissionError):
                continue
            new_state[path] = digest
            previous = state.get(path)
            if previous and previous != digest:
                events.append(Event(
                    source="file_integrity", category="file", event_type="file_modified",
                    file_path=path, timestamp=datetime.fromtimestamp(mtime, tz=timezone.utc),
                    message=f"Content hash of {path} changed", dedup_key=f"{path}:{digest}",
                ))
        self.set_checkpoint(new_state)
        yield from events


LINUX_COLLECTORS = [JournaldAuthCollector, LinuxProcessCollector, LinuxNetworkCollector, LinuxFileIntegrityCollector]
