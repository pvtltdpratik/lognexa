"""Detection for Windows and Linux endpoint telemetry.

Same design as the access-log engine (services/rules.py + ml.py + scoring.py):

1. Per-device behavioural features computed over a look-back window.
2. Explainable rules (``EP-*`` codes) add points with a concrete reason.
3. An Isolation Forest scores how isolated each event is for that device.
4. ``scoring.combine_scores`` / ``classify`` produce risk and severity.

Event types are normalised by the agent, so the same rules apply to Windows
(Security / System / Sysmon / PowerShell logs) and Linux (journald, auth log,
auditd, /proc polling, file-integrity checks).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from app.services.ml import isolation_forest_scores
from app.services.scoring import classify, combine_scores

CATEGORIES = ["authentication", "process", "network", "file", "persistence", "system"]

ENDPOINT_ML_FEATURES = [
    "hour_deviation",
    "is_failure",
    "events_10m",
    "process_rarity",
    "dst_rarity",
    "is_external_dst",
    "cmd_length",
    "indicator_count",
] + [f"cat_{c}" for c in CATEGORIES]

PRIVILEGED_GROUPS = {"administrators", "domain admins", "enterprise admins", "sudo", "wheel", "admin", "root", "remote desktop users"}

SENSITIVE_PATH_PATTERNS = [
    r"^/etc/(passwd|shadow|gshadow|group|sudoers)$",
    r"^/etc/sudoers\.d/",
    r"^/etc/ssh/sshd_config$",
    r"/\.ssh/authorized_keys$",
    r"^/etc/(crontab|ld\.so\.preload|hosts)$",
    r"(?i)^[a-z]:\\windows\\system32\\drivers\\etc\\hosts$",
    r"(?i)\\windows\\system32\\config\\(sam|security|system)$",
]

TEMP_DIR_PATTERN = re.compile(
    r"(?i)(?:^/tmp/|^/var/tmp/|^/dev/shm/|\\appdata\\local\\temp\\|\\windows\\temp\\|\\users\\public\\)"
)

# Command-line indicators commonly used by intrusion-detection rule sets. Each
# entry is (name, pattern); a match adds evidence, it does not prove intent.
COMMAND_INDICATORS: list[tuple[str, re.Pattern[str]]] = [
    ("encoded PowerShell command", re.compile(r"(?i)powershell(\.exe)?\b.*\s-(e|en|enc|encodedcommand)\s+[A-Za-z0-9+/=]{16,}")),
    ("PowerShell download cradle", re.compile(r"(?i)(downloadstring|downloadfile|invoke-webrequest|iwr\s|invoke-restmethod)\b.*(iex|invoke-expression)|(iex|invoke-expression)\b.*(downloadstring|new-object\s+net\.webclient)")),
    ("hidden / bypassed PowerShell", re.compile(r"(?i)powershell.*(-w(indowstyle)?\s+hidden|-exec(utionpolicy)?\s+bypass|-nop\b)")),
    ("remote script piped to a shell", re.compile(r"(?i)\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")),
    ("decoded payload piped to a shell", re.compile(r"(?i)base64\s+(-d|--decode)[^|]*\|\s*(ba)?sh\b")),
    ("interactive shell redirected to network", re.compile(r"(?i)(/dev/tcp/|\bnc(at)?\b.*\s-e\s|\bsocat\b.*exec:)")),
    ("certutil download/decode", re.compile(r"(?i)certutil(\.exe)?\b.*(-urlcache|-decode|-split)")),
    ("script host / LOLBin network fetch", re.compile(r"(?i)\b(mshta|regsvr32|rundll32|bitsadmin)(\.exe)?\b.*(https?://|/transfer|scrobj)")),
    ("shadow copy deletion", re.compile(r"(?i)(vssadmin(\.exe)?\s+delete\s+shadows|wmic\s+shadowcopy\s+delete|wbadmin\s+delete\s+catalog)")),
    ("security tooling disabled", re.compile(r"(?i)(set-mppreference\b.*-disable\w+\s+\$?true|netsh\s+advfirewall\s+set\s+\w+\s+state\s+off|setenforce\s+0|systemctl\s+(stop|disable)\s+(auditd|apparmor|firewalld|ufw))")),
    ("event or shell history wiped", re.compile(r"(?i)(wevtutil(\.exe)?\s+cl\b|clear-eventlog|history\s+-c\b|>\s*/var/log/(auth\.log|secure|syslog)|shred\b.*/var/log/)")),
    ("credential store access", re.compile(r"(?i)(reg(\.exe)?\s+save\s+hklm\\(sam|security)|ntdsutil|procdump.*lsass|comsvcs(\.dll)?.*minidump)")),
    ("world-writable binary made executable", re.compile(r"(?i)chmod\s+(\+x|[0-7]?7[0-7][0-7])\s+(/tmp|/var/tmp|/dev/shm)/")),
]

COMMON_PORTS = {22, 53, 80, 123, 443, 445, 587, 993, 995, 3389, 5353, 5355, 8080, 8443}


def _sensitive_path(path: str | None) -> bool:
    return bool(path) and any(re.search(p, path) for p in SENSITIVE_PATH_PATTERNS)


def _is_external(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved)


def command_indicators(cmd: str | None) -> list[str]:
    if not cmd:
        return []
    return [name for name, pattern in COMMAND_INDICATORS if pattern.search(cmd)]


# --- features --------------------------------------------------------------------------
def _circular_mean_hour(hours: pd.Series) -> float:
    a = hours.to_numpy() / 24.0 * 2 * np.pi
    return float((np.arctan2(np.sin(a).mean(), np.cos(a).mean()) / (2 * np.pi) * 24.0) % 24.0)


def _trailing_count(df: pd.DataFrame, mask: pd.Series, keys: list[str], window: str) -> pd.Series:
    """Count rows where ``mask`` is true per ``keys`` group in a trailing window."""
    tmp = df[keys + ["timestamp"]].copy()
    tmp["flag"] = mask.astype(float)
    tmp = tmp.fillna({k: "∅" for k in keys}).sort_values(keys + ["timestamp"])
    rolled = tmp.set_index("timestamp").groupby(keys)["flag"].rolling(window).sum().to_numpy()
    return pd.Series(rolled, index=tmp.index).reindex(df.index).fillna(0).astype(int)


def build_endpoint_features(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "id"]).reset_index(drop=True)
    for col in ("username", "process_name", "process_path", "command_line", "dst_ip", "src_ip", "dst_port", "file_path", "message", "raw"):
        if col not in df:
            df[col] = None

    df["hour"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    logons = df[df["event_type"] == "logon_success"]
    usual = _circular_mean_hour(logons["hour"]) if len(logons) >= 20 else None
    if usual is None:
        df["usual_hour"] = np.nan
        df["hour_deviation"] = 0.0
    else:
        diff = (df["hour"] - usual).abs() % 24
        df["usual_hour"] = usual
        df["hour_deviation"] = np.minimum(diff, 24 - diff).round(2)

    df["is_failure"] = df["event_type"].isin(["logon_failure", "sudo_failure", "access_denied"]).astype(int)
    failures = df["event_type"] == "logon_failure"
    df["failures_user_10m"] = _trailing_count(df, failures, ["device_id", "username"], "10min")
    df["failures_src_10m"] = _trailing_count(df, failures, ["device_id", "src_ip"], "10min")
    df["failures_10m"] = np.maximum(df["failures_user_10m"], df["failures_src_10m"])
    df["events_10m"] = _trailing_count(df, pd.Series(True, index=df.index), ["device_id"], "10min")

    proc = df["process_name"].fillna("").str.lower()
    proc_counts = proc.map(proc.value_counts())
    df["process_rarity"] = np.where(proc != "", 1.0 / proc_counts, 0.0)
    df["process_seen"] = np.where(proc != "", proc_counts, 0)

    dst = df["dst_ip"].fillna("")
    dst_counts = dst.map(dst.value_counts())
    df["dst_rarity"] = np.where(dst != "", 1.0 / dst_counts, 0.0)
    df["dst_seen"] = np.where(dst != "", dst_counts, 0)
    df["is_external_dst"] = df["dst_ip"].map(_is_external).astype(int)

    df["cmd_length"] = df["command_line"].fillna("").str.len().clip(upper=2000)
    df["indicators"] = df["command_line"].map(command_indicators)
    df["indicator_count"] = df["indicators"].map(len)
    df["sensitive_path"] = df["file_path"].map(_sensitive_path).astype(int)
    exe = df["process_path"].fillna(df["process_name"]).fillna("")
    df["temp_exec"] = ((df["category"] == "process") & exe.str.contains(TEMP_DIR_PATTERN)).astype(int)
    for c in CATEGORIES:
        df[f"cat_{c}"] = (df["category"] == c).astype(int)
    df["process_events_total"] = int((df["category"] == "process").sum())
    return df


# --- rules ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EndpointRule:
    code: str
    name: str
    tactic: str
    points: int
    condition: Callable[[pd.Series], bool]
    reason: Callable[[pd.Series], str]


def _group(raw) -> str:
    return str((raw or {}).get("group") or "").lower() if isinstance(raw, dict) else ""


ENDPOINT_RULES: list[EndpointRule] = [
    EndpointRule("EP-AUTH-1", "Logon brute force", "credential_access", 60,
        lambda r: r["event_type"] == "logon_failure" and r["failures_10m"] >= 5,
        lambda r: f"{int(r['failures_10m'])} failed logons within 10 minutes"
                  + (f" for '{r['username']}'" if r["username"] else "")
                  + (f" from {r['src_ip']}" if r["src_ip"] else "")),
    EndpointRule("EP-AUTH-2", "Logon after repeated failures", "credential_access", 45,
        lambda r: r["event_type"] == "logon_success" and r["failures_10m"] >= 3,
        lambda r: f"Successful logon after {int(r['failures_10m'])} recent failures (possible password guessing success)"),
    EndpointRule("EP-AUTH-3", "Logon at an unusual hour", "initial_access", 25,
        lambda r: r["event_type"] == "logon_success" and r["hour_deviation"] >= 7,
        lambda r: f"Logon at {r['timestamp']:%H:%M}, {r['hour_deviation']:.1f} h from this device's usual logon time"),
    EndpointRule("EP-AUTH-4", "Failed privilege elevation", "privilege_escalation", 30,
        lambda r: r["event_type"] == "sudo_failure",
        lambda r: f"Privilege elevation failed for '{r['username'] or 'unknown'}'"),
    EndpointRule("EP-ACCT-1", "Local account created", "persistence", 35,
        lambda r: r["event_type"] == "user_created",
        lambda r: f"New account created: {(r['raw'] or {}).get('target_user') if isinstance(r['raw'], dict) else ''}".rstrip(": ")),
    EndpointRule("EP-ACCT-2", "Account added to privileged group", "privilege_escalation", 55,
        lambda r: r["event_type"] == "group_member_added" and (_group(r["raw"]) in PRIVILEGED_GROUPS),
        lambda r: f"Account added to privileged group '{_group(r['raw'])}'"),
    EndpointRule("EP-PROC-1", "Suspicious command line", "execution", 55,
        lambda r: r["indicator_count"] > 0,
        lambda r: "Command line matches: " + ", ".join(r["indicators"])),
    EndpointRule("EP-PROC-2", "Execution from a temporary directory", "execution", 25,
        lambda r: bool(r["temp_exec"]),
        lambda r: f"Process started from a temporary/world-writable location: {r.get('process_path') or r['process_name']}"),
    EndpointRule("EP-PROC-3", "First-seen process on this device", "execution", 10,
        lambda r: r["category"] == "process" and r["process_seen"] == 1 and r["process_events_total"] >= 50,
        lambda r: f"'{r['process_name']}' has not been seen on this device in the look-back window"),
    EndpointRule("EP-PERS-1", "Persistence mechanism created", "persistence", 45,
        lambda r: r["event_type"] in {"service_installed", "scheduled_task_created", "autorun_modified", "cron_modified", "systemd_unit_modified"},
        lambda r: f"{r['event_type'].replace('_', ' ').capitalize()}: {r['file_path'] or r['message'] or ''}".strip(": ")),
    EndpointRule("EP-FILE-1", "Sensitive file changed", "persistence", 45,
        lambda r: r["category"] == "file" and bool(r["sensitive_path"]),
        lambda r: f"Sensitive file {r['event_type'].replace('file_', '')}: {r['file_path']}"),
    EndpointRule("EP-LOG-1", "Audit log cleared", "defense_evasion", 70,
        lambda r: r["event_type"] == "log_cleared",
        lambda r: f"Event log cleared{(' by ' + r['username']) if r['username'] else ''}"),
    EndpointRule("EP-NET-1", "Connection to a rarely seen external host", "command_and_control", 15,
        lambda r: r["category"] == "network" and bool(r["is_external_dst"]) and r["dst_seen"] == 1,
        lambda r: f"First connection to external address {r['dst_ip']}:{int(r['dst_port']) if pd.notna(r['dst_port']) else '?'}"),
    EndpointRule("EP-NET-2", "Uncommon remote port", "command_and_control", 15,
        lambda r: r["category"] == "network" and bool(r["is_external_dst"]) and pd.notna(r["dst_port"]) and int(r["dst_port"]) not in COMMON_PORTS,
        lambda r: f"Outbound connection to uncommon port {int(r['dst_port'])}"),
    EndpointRule("EP-NET-3", "New listening port", "persistence", 20,
        lambda r: r["event_type"] == "listen_port_opened",
        lambda r: f"Process '{r['process_name'] or 'unknown'}' started listening on port {int(r['dst_port']) if pd.notna(r['dst_port']) else '?'}"),
]

ENDPOINT_RULES_BY_CODE = {r.code: r for r in ENDPOINT_RULES}


def evaluate_endpoint_row(row: pd.Series) -> tuple[float, list[dict]]:
    hits = []
    for rule in ENDPOINT_RULES:
        try:
            matched = rule.condition(row)
        except (KeyError, TypeError, ValueError):
            matched = False
        if matched:
            hits.append({"code": rule.code, "name": rule.name, "category": rule.tactic, "points": rule.points, "reason": rule.reason(row)})
    return float(min(100, sum(h["points"] for h in hits))), hits


def explain_endpoint(rule_score: float, ml_score: float, ml_flag: bool, hits: list[dict], ml_fitted: bool) -> str:
    parts = ["Rules triggered: " + "; ".join(f"{h['reason']} (+{h['points']})" for h in hits) + "."] if hits else ["No detection rule was triggered."]
    if not ml_fitted:
        parts.append("Isolation Forest not applied (fewer than 50 events from this device in the look-back window).")
    elif ml_flag:
        parts.append(f"Isolation Forest marked this event as an outlier for this device (ML score {ml_score:.0f}/100).")
    else:
        parts.append(f"Isolation Forest ML score {ml_score:.0f}/100.")
    return " ".join(parts)


MIN_EVENTS_FOR_ML = 50


def score_endpoint_frame(events: pd.DataFrame, rule_weight: float = 0.6, contamination: float = 0.03, seed: int = 42) -> pd.DataFrame:
    """Pure scoring step for one device's events (no database access)."""
    if events.empty:
        return events
    df = build_endpoint_features(events)
    scored = [evaluate_endpoint_row(row) for _, row in df.iterrows()]
    df["rule_score"] = [s for s, _ in scored]
    df["triggered_rules"] = [h for _, h in scored]
    ml_fitted = len(df) >= MIN_EVENTS_FOR_ML
    if ml_fitted:
        ml, flags = isolation_forest_scores(df, contamination=contamination, seed=seed, features=ENDPOINT_ML_FEATURES)
    else:
        ml, flags = pd.Series(0.0, index=df.index), pd.Series(False, index=df.index)
    df["ml_score"] = ml
    df["ml_is_anomaly"] = flags.astype(bool)
    if ml_fitted:
        df["risk_score"] = [combine_scores(r, m, bool(f), rule_weight) for r, m, f in zip(df["rule_score"], df["ml_score"], df["ml_is_anomaly"])]
    else:
        # Not enough history to fit the forest: fall back to pure explainable rules
        # so a strong single indicator still raises an alert in a new deployment.
        df["risk_score"] = df["rule_score"].astype(float)
    df["severity"] = df["risk_score"].map(classify)
    df["explanation"] = [
        explain_endpoint(r, m, bool(f), h, ml_fitted)
        for r, m, f, h in zip(df["rule_score"], df["ml_score"], df["ml_is_anomaly"], df["triggered_rules"])
    ]
    return df
