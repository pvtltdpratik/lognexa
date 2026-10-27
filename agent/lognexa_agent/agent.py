"""Agent runtime: enrolment, collection, buffering, delivery and heartbeats.

Threads:
* **collector loop** - every ``poll_interval`` s, runs each available collector,
  redacts and writes new events to the durable buffer.
* **sender loop** - every ``send_interval`` s, drains the buffer to the server in
  batches with exponential backoff; events are deleted only after the server
  acknowledges them (at-least-once, deduplicated server-side).
* **heartbeat loop** - every ``heartbeat_interval`` s, reports health (buffer
  depth, collector statuses, privilege) and honours credential-rotation requests.

All three share one buffer and stop cleanly on SIGINT/SIGTERM.
"""

from __future__ import annotations

import json
import logging
import platform
import socket
import threading
import time
import uuid

from lognexa_agent import __version__
from lognexa_agent.buffer import EventBuffer
from lognexa_agent.client import ApiClient, ApiError
from lognexa_agent.collectors import collectors_for_platform
from lognexa_agent.config import AgentConfig, State, is_privileged
from lognexa_agent.models import fit_payload, to_json, utcnow
from lognexa_agent.redaction import redact_event

log = logging.getLogger("lognexa.agent")


def machine_id() -> str:
    """Stable per-machine id. Prefers an OS-provided id, falls back to hostname."""
    try:
        if platform.system() == "Linux":
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    with open(path) as fh:
                        mid = fh.read().strip()
                        if mid:
                            return mid
                except OSError:
                    continue
        elif platform.system() == "Windows":
            import subprocess

            out = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for token in out.split():
                if len(token) >= 32 and "-" in token:
                    return token
    except Exception:
        pass
    return f"{socket.gethostname()}-{uuid.getnode():x}"


class Agent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = State(config.state_path)
        self.buffer = EventBuffer(config.buffer_path, config.max_buffer_events)
        self.client = ApiClient(config, self.state.credential)
        self._stop = threading.Event()
        self._started = time.monotonic()
        self._send_failures = 0
        self._rejected = 0
        self._last_flush = None
        collector_classes = collectors_for_platform()
        self.collectors = []
        for cls in collector_classes:
            inst = cls(config, self.state)
            enabled = config.collector_enabled(inst.name)
            ok, status, detail = inst.available()
            if not enabled:
                inst.health.status, inst.health.detail = "disabled", "disabled in configuration"
            elif not ok:
                inst.health.status, inst.health.detail = status, detail
                log.warning("collector %s unavailable: %s (%s)", inst.name, status, detail)
            inst._runnable = enabled and ok
            self.collectors.append(inst)

    # --- enrolment -----------------------------------------------------------
    def ensure_enrolled(self) -> None:
        if self.state.enrolled:
            self.client.credential = self.state.credential
            return
        if not self.config.enroll_token:
            raise SystemExit("Agent is not enrolled and no enrolment token was provided (LOGNEXA_ENROLL_TOKEN).")
        payload = {
            "token": self.config.enroll_token,
            "hostname": socket.gethostname()[:255],
            "os_type": "windows" if platform.system() == "Windows" else "linux",
            "os_version": platform.platform()[:255],
            "agent_version": __version__,
            "machine_id": machine_id()[:128],
        }
        log.info("enrolling with %s", self.config.server_url)
        resp = self.client.enroll(payload)
        self.state.set_credential(resp["device_uid"], resp["credential"])
        self.client.credential = resp["credential"]
        self.config.heartbeat_interval = resp.get("heartbeat_interval_seconds", self.config.heartbeat_interval)
        self.config.batch_size = min(self.config.batch_size, resp.get("max_events_per_batch", self.config.batch_size))
        log.info("enrolled as device %s", resp["device_uid"])

    # --- loops ---------------------------------------------------------------
    def _collect_once(self) -> int:
        scope = self.state.device_uid or "unenrolled"
        items = []
        for c in self.collectors:
            if not getattr(c, "_runnable", False):
                continue
            for event in c.run():
                redact_event(event)
                items.append((event.event_uid(scope), to_json(event.to_payload(scope))))
        return self.buffer.add_many(items)

    def collector_loop(self) -> None:
        while not self._stop.is_set():
            try:
                n = self._collect_once()
                if n:
                    log.debug("collected %d new events (buffer=%d)", n, self.buffer.pending())
            except Exception:
                log.exception("collector cycle failed")
            self._stop.wait(self.config.poll_interval)

    def sender_loop(self) -> None:
        backoff = self.config.send_interval
        while not self._stop.is_set():
            sent_any = False
            try:
                while not self._stop.is_set():
                    batch = self.buffer.peek(self.config.batch_size)
                    if not batch:
                        break
                    uids = [u for u, _ in batch]
                    # fit_payload also repairs events buffered by an older agent version.
                    events = [fit_payload(json.loads(p)) for _, p in batch]
                    rejected = self._deliver(uids, events)
                    self._last_flush = utcnow()
                    self._send_failures = 0
                    sent_any = True
                    log.info("sent %d events, %d rejected (buffer=%d)",
                             len(uids) - rejected, rejected, self.buffer.pending())
                backoff = self.config.send_interval
            except ApiError as exc:
                self._send_failures += 1
                if exc.status in (401, 403):
                    log.error("authentication rejected (%s); will retry after re-check", exc.code)
                if exc.retryable:
                    backoff = min(backoff * 2, 300)
                    log.warning("send failed (%s), backing off %.0fs", exc.code, backoff)
                else:
                    log.error("send rejected (%s): %s", exc.code, exc.message)
                    backoff = self.config.send_interval
            except Exception:
                self._send_failures += 1
                log.exception("sender cycle failed")
                backoff = min(backoff * 2, 300)
            self._stop.wait(self.config.send_interval if sent_any else backoff)

    def _deliver(self, uids: list[str], events: list[dict]) -> int:
        """Send a batch and acknowledge it. Returns how many events were rejected.

        If the server refuses the batch as invalid (422) or too large (413), the
        batch is split in half and each half retried, down to single events. An
        event the server still refuses is moved to ``rejected.jsonl`` and removed
        from the buffer, so one bad event can never block everything behind it.
        Other errors (network, 5xx, auth) propagate and the batch stays buffered.
        """
        try:
            self.client.send_events(events)
        except ApiError as exc:
            if exc.status not in (413, 422):
                raise
            if len(events) > 1:
                mid = len(events) // 2
                return self._deliver(uids[:mid], events[:mid]) + self._deliver(uids[mid:], events[mid:])
            self._quarantine(uids[0], events[0], exc)
            self.buffer.ack(uids)
            return 1
        self.buffer.ack(uids)
        return 0

    def _quarantine(self, uid: str, event: dict, exc: ApiError) -> None:
        self._rejected += 1
        log.error("server rejected event %s (%s: %s); saved to rejected.jsonl", uid[:12], exc.code, exc.message)
        path = self.config.data_dir / "rejected.jsonl"
        try:
            if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
                path.replace(path.with_suffix(".jsonl.1"))  # keep one old file
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(to_json({"event_uid": uid, "error": exc.code, "message": exc.message, "event": event}) + "\n")
        except OSError:
            log.exception("could not write rejected.jsonl")

    def _health_payload(self) -> dict:
        return {
            "agent_version": __version__,
            "os_version": platform.platform()[:255],
            "hostname": socket.gethostname()[:255],
            "uptime_seconds": int(time.monotonic() - self._started),
            "buffer_pending": self.buffer.pending(),
            "buffer_total": self.buffer.pending() + self.buffer.dropped(),
            "send_failures": self._send_failures,
            "last_flush_at": self._last_flush.isoformat() if self._last_flush else None,
            "is_privileged": is_privileged(),
            "collectors": [c.health.to_payload() for c in self.collectors],
        }

    def heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                resp = self.client.heartbeat(self._health_payload())
                if resp.get("rotate_credentials"):
                    self._rotate()
            except ApiError as exc:
                log.warning("heartbeat failed (%s)", exc.code)
            except Exception:
                log.exception("heartbeat cycle failed")
            self._stop.wait(self.config.heartbeat_interval)

    def _rotate(self) -> None:
        try:
            resp = self.client.rotate()
            self.state.set_credential(self.state.device_uid, resp["credential"])
            self.client.credential = resp["credential"]
            log.info("rotated device credential")
        except ApiError as exc:
            log.error("credential rotation failed (%s)", exc.code)

    # --- lifecycle -----------------------------------------------------------
    def run(self) -> None:
        self.ensure_enrolled()
        log.info("agent %s started: %d collectors (%d active)", __version__, len(self.collectors),
                 sum(1 for c in self.collectors if getattr(c, "_runnable", False)))
        threads = [
            threading.Thread(target=self.collector_loop, name="collector", daemon=True),
            threading.Thread(target=self.sender_loop, name="sender", daemon=True),
            threading.Thread(target=self.heartbeat_loop, name="heartbeat", daemon=True),
        ]
        for t in threads:
            t.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        log.info("stopping agent")
        self._stop.set()
        self.buffer.close()
