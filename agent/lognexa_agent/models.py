"""Shared dataclasses: a normalised Event and collector health."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

CATEGORIES = ("authentication", "process", "network", "file", "persistence", "system", "agent")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class Event:
    """One normalised telemetry event. Matches the server's EventIn schema."""

    source: str
    category: str
    event_type: str
    timestamp: datetime = field(default_factory=utcnow)
    username: str | None = None
    process_name: str | None = None
    process_path: str | None = None
    command_line: str | None = None
    pid: int | None = None
    parent_process: str | None = None
    parent_pid: int | None = None
    src_ip: str | None = None
    dst_ip: str | None = None
    dst_port: int | None = None
    file_path: str | None = None
    message: str | None = None
    raw: dict | None = None
    # Stable identity for deduplication; provided by the collector when the OS
    # gives a durable record id, otherwise derived from the content below.
    dedup_key: str | None = None

    def event_uid(self, device_scope: str) -> str:
        if self.dedup_key:
            basis = f"{device_scope}|{self.source}|{self.dedup_key}"
        else:
            basis = "|".join(
                str(x) for x in (
                    device_scope, self.source, self.event_type,
                    self.timestamp.isoformat(), self.username, self.process_name,
                    self.command_line, self.pid, self.src_ip, self.dst_ip, self.dst_port,
                    self.file_path, self.message,
                )
            )
        return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()

    def to_payload(self, device_scope: str) -> dict:
        d = asdict(self)
        d.pop("dedup_key", None)
        d["event_uid"] = self.event_uid(device_scope)
        d["timestamp"] = self.timestamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        return {k: v for k, v in d.items() if v is not None or k in ("event_uid", "timestamp", "source", "category", "event_type")}


def to_json(obj) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))
