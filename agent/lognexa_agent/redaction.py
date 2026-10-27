"""Client-side sensitive-data redaction.

Kept in sync with server/app/services/redaction.py. Redaction happens before an
event is written to the local buffer, so secrets never reach disk or the network.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), MASK),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@"), r"\1:" + MASK + "@"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + MASK),
    (
        re.compile(
            r"(?i)((?:--?|/)(?:password|passwd|pass|pwd|token|secret|api[-_]?key|access[-_]?key|client[-_]?secret))"
            r"(\s+|[=:])(\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1\2" + MASK,
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|connectionstring)"
            r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s;&,]+)"
        ),
        r"\1\2" + MASK,
    ),
    (re.compile(r"(?i)\b(net1?(?:\.exe)?\s+user\s+\S+\s+)(?!/)(\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)(ConvertTo-SecureString\s+(?:-String\s+)?)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)\b(mysql\S*\s+(?:.*\s)?-p)(\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)\b((?:sqlcmd|osql)\S*\s+(?:.*\s)?-P\s*)(\S+)"), r"\1" + MASK),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), MASK),
]

_SENSITIVE_KEY = re.compile(r"(?i).*(password|secret|token|apikey|api_key).*")


def redact_text(value: str | None) -> tuple[str | None, bool]:
    if not value:
        return value, False
    out = value
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out, out != value


def redact_obj(obj):
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        changed = False
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SENSITIVE_KEY.fullmatch(k) and isinstance(v, str) and v:
                out[k], changed = MASK, True
                continue
            out[k], c = redact_obj(v)
            changed = changed or c
        return out, changed
    if isinstance(obj, list):
        changed = False
        out = []
        for v in obj:
            r, c = redact_obj(v)
            out.append(r)
            changed = changed or c
        return out, changed
    return obj, False


def redact_event(event) -> None:
    """Redact an Event in place across its free-text fields."""
    for attr in ("command_line", "message", "process_path", "file_path"):
        redacted, _ = redact_text(getattr(event, attr, None))
        setattr(event, attr, redacted)
    if event.raw:
        event.raw, _ = redact_obj(event.raw)
