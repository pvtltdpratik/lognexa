"""Shared dataclasses: a normalised Event and collector health."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

CATEGORIES = ("authentication", "process", "network", "file", "persistence", "system", "agent")

# Mirrors the limits of the server's EventIn schema (server/app/endpoint_schemas.py).
# The server rejects a whole batch when one event breaks them, so every payload is
# clamped to fit before it is buffered and again before it is sent.
FIELD_LIMITS = {
    "username": 128, "process_name": 255, "process_path": 1024, "command_line": 8192,
    "parent_process": 255, "file_path": 2048, "message": 4096,
}
MAX_RAW_BYTES = 16_384
TRUNCATED = " ...[truncated]"


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
        payload = {k: v for k, v in d.items() if v is not None or k in ("event_uid", "timestamp", "source", "category", "event_type")}
        return fit_payload(payload)


def _valid_ip(value) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        # Drop IPv6 zone ids ("fe80::1%12"), which the server does not accept.
        return str(ipaddress.ip_address(value.strip("[]").split("%", 1)[0]))
    except ValueError:
        return None


def fit_payload(payload: dict) -> dict:
    """Clamp an event payload to the server schema (in place, and returned).

    Over-long text is truncated (and listed in ``raw.truncated_fields``), invalid
    IPs and out-of-range numbers are cleared, and an oversized ``raw`` is replaced,
    so a single unusual event can never cause the server to reject a batch.
    """
    truncated = []
    for key, limit in FIELD_LIMITS.items():
        value = payload.get(key)
        if isinstance(value, str) and len(value) > limit:
            payload[key] = value[: limit - len(TRUNCATED)] + TRUNCATED
            truncated.append(key)
    for key in ("src_ip", "dst_ip"):
        if key in payload:
            payload[key] = _valid_ip(payload[key])
    for key, upper in (("pid", 2**31 - 1), ("parent_pid", 2**31 - 1), ("dst_port", 65535)):
        value = payload.get(key)
        if value is not None and (not isinstance(value, int) or not 0 <= value <= upper):
            payload[key] = None
    raw = payload.get("raw")
    if truncated:
        raw = dict(raw or {})
        raw["truncated_fields"] = truncated
    if raw is not None and len(json.dumps(raw, default=str)) > MAX_RAW_BYTES:
        raw = {"truncated_fields": truncated + ["raw"]}
    if raw is not None:
        payload["raw"] = raw
    return {k: v for k, v in payload.items() if v is not None or k in ("event_uid", "timestamp", "source", "category", "event_type")}


def to_json(obj) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))
