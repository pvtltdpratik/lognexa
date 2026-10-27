"""Windows collectors: Security/System/Sysmon/PowerShell event logs, process, network.

Event logs are read with ``wevtutil qe <channel> /q:<xpath> /f:xml``, which needs
no third-party module. The Security channel requires Administrator; when it is
not readable the collector reports ``permission_denied`` and the others continue.
Process and network collectors use PowerShell CIM queries, diffed between cycles.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from lognexa_agent.collectors.base import Collector
from lognexa_agent.models import Event, utcnow

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

# channel -> (collector-relevant event ids)
SECURITY_IDS = {
    4624: "logon_success", 4625: "logon_failure", 4634: "logoff", 4672: "special_logon",
    4720: "user_created", 4728: "group_member_added", 4732: "group_member_added", 4756: "group_member_added",
    4688: "process_start", 4698: "scheduled_task_created", 4697: "service_installed",
    1102: "log_cleared", 4740: "account_lockout",
}
SYSTEM_IDS = {7045: "service_installed", 104: "log_cleared"}
SYSMON_IDS = {
    1: "process_start", 3: "network_connection", 11: "file_created", 13: "autorun_modified",
    12: "autorun_modified", 23: "file_deleted",
}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    return p.returncode, p.stdout, p.stderr


def _text(node, path):
    el = node.find(path, NS)
    return el.text if el is not None else None


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return utcnow()


def _base(path) -> str | None:
    """os.path.basename that tolerates None/empty (empty XML elements are None)."""
    return os.path.basename(path) if path else None


class _WevtutilCollector(Collector):
    channel = ""
    id_map: dict[int, str] = {}
    category_map: dict[str, str] = {}

    def available(self):
        if os.name != "nt":
            return False, "unsupported", "Windows-only collector"
        if not shutil.which("wevtutil"):
            return False, "unsupported", "wevtutil is not available"
        rc, _, err = _run(["wevtutil", "qe", self.channel, "/c:1", "/f:xml"])
        if rc != 0:
            low = err.lower()
            if "access is denied" in low or "5011" in err:
                return False, "permission_denied", f"cannot read the '{self.channel}' channel (Administrator required)"
            if "channel was not found" in low or "not be found" in low:
                return False, "unsupported", f"the '{self.channel}' channel is not present (is Sysmon installed?)"
            return False, "error", err.strip()[:200]
        return True, "ok", None

    def collect(self):
        last_record = self.get_checkpoint(0)
        ids = " or ".join(f"EventID={eid}" for eid in self.id_map)
        xpath = f"*[System[({ids}) and (EventRecordID>{last_record})]]"
        rc, out, err = _run(["wevtutil", "qe", self.channel, f"/q:{xpath}", "/f:xml", "/c:500", "/rd:false"])
        if rc != 0:
            if "access is denied" in err.lower():
                raise PermissionError(f"cannot read the '{self.channel}' channel (Administrator required)")
            raise RuntimeError(err.strip() or f"wevtutil exited {rc}")
        max_record = last_record
        for chunk in self._split(out):
            try:
                node = ET.fromstring(chunk)
            except ET.ParseError:
                continue
            rec_id = int(_text(node, "e:System/e:EventRecordID") or 0)
            max_record = max(max_record, rec_id)
            ev = self._to_event(node)
            if ev:
                ev.dedup_key = f"{self.channel}:{rec_id}"
                yield ev
        if max_record > last_record:
            self.set_checkpoint(max_record)

    _EVENT_RE = re.compile(r"<Event\b.*?</Event>", re.S)

    @classmethod
    def _split(cls, xml_out: str):
        # wevtutil /f:xml concatenates every <Event>...</Event> record with no
        # separators (often on a single line), so split on the element itself.
        for match in cls._EVENT_RE.finditer(xml_out):
            yield match.group(0)

    def _data(self, node) -> dict:
        out = {}
        for d in node.findall("e:EventData/e:Data", NS):
            name = d.get("Name")
            if name:
                out[name] = d.text
        return out

    def _to_event(self, node) -> Event | None:
        eid = int(_text(node, "e:System/e:EventID") or 0)
        etype = self.id_map.get(eid)
        if not etype:
            return None
        ts = _parse_ts(node.find("e:System/e:TimeCreated", NS).get("SystemTime") if node.find("e:System/e:TimeCreated", NS) is not None else None)
        data = self._data(node)
        return self.build(eid, etype, ts, data, node)

    def build(self, eid, etype, ts, data, node) -> Event | None:
        raise NotImplementedError


class WindowsSecurityCollector(_WevtutilCollector):
    name = "windows_security"
    channel = "Security"
    id_map = SECURITY_IDS

    def build(self, eid, etype, ts, data, node):
        cat = {
            "logon_success": "authentication", "logon_failure": "authentication", "logoff": "authentication",
            "special_logon": "authentication", "account_lockout": "authentication",
            "user_created": "persistence", "group_member_added": "persistence",
            "process_start": "process", "scheduled_task_created": "persistence",
            "service_installed": "persistence", "log_cleared": "system",
        }.get(etype, "system")
        ev = Event(
            source="win_security", category=cat, event_type=etype, timestamp=ts,
            username=data.get("TargetUserName") or data.get("SubjectUserName"),
            src_ip=(data.get("IpAddress") or "").replace("-", "") or None,
            message=f"Security event {eid} ({etype})",
            raw={k: v for k, v in data.items() if k in ("LogonType", "WorkstationName", "TargetDomainName", "MemberName", "TaskName", "ServiceName", "ProcessName")},
        )
        if etype == "process_start":
            ev.process_name = _base(data.get("NewProcessName"))
            ev.process_path = data.get("NewProcessName")
            ev.command_line = data.get("CommandLine")
            ev.parent_process = _base(data.get("ParentProcessName"))
        if etype == "group_member_added":
            ev.raw["group"] = data.get("TargetUserName")
            ev.raw["target_user"] = data.get("MemberName")
        if etype == "user_created":
            ev.raw["target_user"] = data.get("TargetUserName")
        return ev


class WindowsSystemCollector(_WevtutilCollector):
    name = "windows_system"
    channel = "System"
    id_map = SYSTEM_IDS

    def build(self, eid, etype, ts, data, node):
        return Event(
            source="win_system", category="persistence" if etype == "service_installed" else "system",
            event_type=etype, timestamp=ts, message=f"System event {eid} ({etype})",
            file_path=data.get("ImagePath"), process_name=data.get("ServiceName"),
            raw={k: v for k, v in data.items() if v},
        )


class WindowsSysmonCollector(_WevtutilCollector):
    name = "windows_sysmon"
    channel = "Microsoft-Windows-Sysmon/Operational"
    id_map = SYSMON_IDS

    def build(self, eid, etype, ts, data, node):
        cat = {"process_start": "process", "network_connection": "network"}.get(etype, "file")
        ev = Event(
            source="sysmon", category=cat, event_type=etype, timestamp=ts,
            username=data.get("User"), message=f"Sysmon event {eid} ({etype})",
        )
        if etype == "process_start":
            ev.process_name = _base(data.get("Image"))
            ev.process_path = data.get("Image")
            ev.command_line = data.get("CommandLine")
            ev.parent_process = _base(data.get("ParentImage"))
            ev.parent_process = ev.parent_process
        elif etype == "network_connection":
            ev.process_name = _base(data.get("Image"))
            ev.dst_ip = data.get("DestinationIp")
            ev.src_ip = data.get("SourceIp")
            try:
                ev.dst_port = int(data.get("DestinationPort")) if data.get("DestinationPort") else None
            except ValueError:
                pass
        else:
            ev.file_path = data.get("TargetFilename")
        return ev


class WindowsPowerShellCollector(_WevtutilCollector):
    name = "windows_powershell"
    channel = "Microsoft-Windows-PowerShell/Operational"
    id_map = {4104: "powershell_script"}

    def build(self, eid, etype, ts, data, node):
        block = data.get("ScriptBlockText")
        if not block:
            return None
        return Event(
            source="powershell", category="process", event_type="powershell_script", timestamp=ts,
            command_line=block, message="PowerShell script block logged",
        )


class WindowsProcessCollector(Collector):
    """New processes via CIM, for hosts without Sysmon / 4688 command-line auditing."""

    name = "windows_process"

    def available(self):
        if os.name != "nt":
            return False, "unsupported", "Windows-only collector"
        if not shutil.which("powershell"):
            return False, "unsupported", "powershell is not available"
        return True, "ok", None

    def collect(self):
        import json

        script = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        )
        rc, out, err = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
        if rc != 0:
            raise RuntimeError(err.strip() or "powershell failed")
        try:
            procs = json.loads(out or "[]")
        except ValueError:
            return
        if isinstance(procs, dict):
            procs = [procs]
        seen = set(self.get_checkpoint([]) or [])
        current, events = set(), []
        for p in procs:
            pid = p.get("ProcessId")
            key = f"{pid}:{p.get('Name')}"
            current.add(key)
            if key in seen or not pid:
                continue
            events.append(Event(
                source="cim", category="process", event_type="process_start",
                process_name=p.get("Name"), process_path=p.get("ExecutablePath"),
                command_line=p.get("CommandLine"), pid=pid, parent_pid=p.get("ParentProcessId"),
                dedup_key=f"{key}:{(p.get('CommandLine') or '')[:100]}",
            ))
        self.set_checkpoint(sorted(current))
        yield from events


WINDOWS_COLLECTORS = [
    WindowsSecurityCollector, WindowsSystemCollector, WindowsSysmonCollector,
    WindowsPowerShellCollector, WindowsProcessCollector,
]
