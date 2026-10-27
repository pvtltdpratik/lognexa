"""Sensitive-data redaction for telemetry (applied on ingest, defence in depth).

The agent redacts before sending; the server repeats the same pass so a
misconfigured or outdated agent cannot store secrets in the database.
Patterns mirror agent/lognexa_agent/redaction.py.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # -----BEGIN ... PRIVATE KEY----- blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), MASK),
    # scheme://user:password@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@"), r"\1:" + MASK + "@"),
    # Authorization headers / bearer tokens
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + MASK),
    # --password value / -password=value / /password:value style flags
    (
        re.compile(
            r"(?i)((?:--?|/)(?:password|passwd|pass|pwd|token|secret|api[-_]?key|access[-_]?key|client[-_]?secret))"
            r"(\s+|[=:])(\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1\2" + MASK,
    ),
    # key=value / key: value pairs
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|connectionstring)"
            r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s;&,]+)"
        ),
        r"\1\2" + MASK,
    ),
    # Windows: net user <name> <password>
    (re.compile(r"(?i)\b(net1?(?:\.exe)?\s+user\s+\S+\s+)(?!/)(\S+)"), r"\1" + MASK),
    # PowerShell: ConvertTo-SecureString "<plaintext>" -AsPlainText
    (re.compile(r"(?i)(ConvertTo-SecureString\s+(?:-String\s+)?)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1" + MASK),
    # mysql -pSECRET (password glued to the flag)
    (re.compile(r"(?i)\b(mysql\S*\s+(?:.*\s)?-p)(\S+)"), r"\1" + MASK),
    # sqlcmd / osql -P <password> (SQL Server)
    (re.compile(r"(?i)\b((?:sqlcmd|osql)\S*\s+(?:.*\s)?-P\s*)(\S+)"), r"\1" + MASK),
    # AWS access key ids and JWTs
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), MASK),
]


def redact_text(value: str | None) -> tuple[str | None, bool]:
    if not value:
        return value, False
    out = value
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out, out != value


def redact_obj(obj):
    """Recursively redact strings inside dicts/lists. Returns (obj, changed)."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        changed = False
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and re.fullmatch(r"(?i).*(password|secret|token|apikey|api_key).*", k) and isinstance(v, str) and v:
                out[k], changed = MASK, True
                continue
            out[k], c = redact_obj(v)
            changed |= c
        return out, changed
    if isinstance(obj, list):
        changed = False
        out = []
        for v in obj:
            r, c = redact_obj(v)
            out.append(r)
            changed |= c
        return out, changed
    return obj, False
