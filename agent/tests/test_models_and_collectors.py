"""Event identity/dedup, collector availability reporting, and CLI smoke tests."""

import os
from pathlib import Path

import pytest

from lognexa_agent.config import AgentConfig, State
from lognexa_agent.models import Event


def test_event_uid_is_stable_and_scoped():
    e1 = Event(source="s", category="process", event_type="process_start", pid=1, command_line="a.exe")
    e2 = Event(source="s", category="process", event_type="process_start", pid=1, command_line="a.exe",
               timestamp=e1.timestamp)
    assert e1.event_uid("dev1") == e2.event_uid("dev1")
    # different device scope -> different uid (prevents cross-device collisions)
    assert e1.event_uid("dev1") != e1.event_uid("dev2")


def test_event_uid_uses_dedup_key_when_present():
    e = Event(source="win_security", category="system", event_type="log_cleared", dedup_key="Security:12345")
    assert len(e.event_uid("d")) == 64


def test_to_payload_shape():
    e = Event(source="s", category="network", event_type="network_connection", dst_ip="8.8.8.8", dst_port=53)
    p = e.to_payload("dev1")
    assert p["event_uid"] and p["category"] == "network" and p["dst_port"] == 53
    assert "dedup_key" not in p
    # None fields are dropped
    assert "username" not in p


def test_collector_availability_reports_reason():
    from lognexa_agent.collectors import collectors_for_platform

    cfg = AgentConfig(server_url="http://localhost", data_dir=Path("."))
    state = State(Path("nonexistent-state.json"))
    for cls in collectors_for_platform():
        inst = cls(cfg, state)
        ok, status, detail = inst.available()
        assert status in ("ok", "unsupported", "permission_denied", "error", "disabled")
        if not ok:
            assert detail  # an unavailable collector must explain why


def test_cross_platform_collector_set():
    """The registry returns this platform's collectors, and the other platform's
    collectors correctly report themselves unsupported here."""
    from lognexa_agent.collectors.linux import LINUX_COLLECTORS
    from lognexa_agent.collectors.windows import WINDOWS_COLLECTORS

    cfg = AgentConfig(server_url="http://localhost", data_dir=Path("."))
    state = State(Path("nonexistent-state.json"))
    other = WINDOWS_COLLECTORS if os.name != "nt" else LINUX_COLLECTORS
    for cls in other:
        ok, status, _ = cls(cfg, state).available()
        assert not ok and status == "unsupported"


def test_run_never_raises_on_broken_collector():
    from lognexa_agent.collectors.base import Collector

    class Broken(Collector):
        name = "broken"

        def collect(self):
            raise ValueError("boom")

    cfg = AgentConfig(server_url="http://localhost", data_dir=Path("."))
    inst = Broken(cfg, State(Path("s.json")))
    assert inst.run() == []
    assert inst.health.status == "error" and "boom" in inst.health.detail


def test_checkpoint_persists(tmp_path):
    state = State(tmp_path / "state.json")
    state.set_checkpoint("col", {"offset": 42})
    reloaded = State(tmp_path / "state.json")
    assert reloaded.checkpoint("col") == {"offset": 42}


def test_http_client_requires_https_for_remote():
    from lognexa_agent.client import ApiClient

    cfg = AgentConfig(server_url="http://example.com:8000", data_dir=Path("."), insecure_http_ok=False)
    with pytest.raises(SystemExit):
        ApiClient(cfg)
    # localhost dev with explicit opt-in is allowed
    local = AgentConfig(server_url="http://localhost:8000", data_dir=Path("."), insecure_http_ok=True)
    assert ApiClient(local).base == "http://localhost:8000"


def test_config_and_state_accept_utf8_bom(tmp_path, monkeypatch):
    # Windows PowerShell 5.1 (Set-Content -Encoding UTF8) and Notepad write a BOM.
    for var in ("LOGNEXA_SERVER_URL", "LOGNEXA_AGENT_DATA_DIR", "LOGNEXA_AGENT_ALLOW_HTTP"):
        monkeypatch.delenv(var, raising=False)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"server_url": "http://localhost:8000", "insecure_http_ok": true}', encoding="utf-8-sig")
    cfg = AgentConfig.load(str(cfg_file))
    assert cfg.server_url == "http://localhost:8000" and cfg.insecure_http_ok is True

    state_file = tmp_path / "state.json"
    state_file.write_text('{"device_uid": "dev1", "credential": "dev1.secret"}', encoding="utf-8-sig")
    assert State(state_file).enrolled


def test_log_file_setting_writes_rotating_log(tmp_path, monkeypatch):
    import logging

    from lognexa_agent.cli import _setup_logging

    monkeypatch.delenv("LOGNEXA_AGENT_LOG_FILE", raising=False)
    cfg_file = tmp_path / "config.json"
    log_file = tmp_path / "logs" / "agent.log"
    cfg_file.write_text('{"server_url": "https://example.test", "log_file": "%s"}'
                        % str(log_file).replace("\\", "\\\\"), encoding="utf-8")
    cfg = AgentConfig.load(str(cfg_file))
    assert cfg.log_file == str(log_file)
    try:
        _setup_logging("INFO", cfg.log_file)
        logging.getLogger("lognexa.test").info("hello from the background agent")
        for h in logging.getLogger().handlers:
            h.flush()
        assert "hello from the background agent" in log_file.read_text(encoding="utf-8")
    finally:
        for h in list(logging.getLogger().handlers):
            h.close()
            logging.getLogger().removeHandler(h)


def test_cli_reports_server_errors_without_traceback(monkeypatch, capsys):
    import lognexa_agent.cli as cli
    from lognexa_agent.client import ApiError

    def boom(args):
        raise ApiError(0, "transport_error", "connection refused")

    monkeypatch.setattr(cli, "cmd_status", boom)
    monkeypatch.setenv("LOGNEXA_SERVER_URL", "https://example.test")
    assert cli.main(["status"]) == 1
    err = capsys.readouterr().err
    assert "transport_error: connection refused" in err and "Traceback" not in err


def test_server_flag_works_without_config_or_env(tmp_path, monkeypatch):
    # A fresh machine: no config.json and no LOGNEXA_SERVER_URL, only --server.
    for var in ("LOGNEXA_SERVER_URL", "LOGNEXA_AGENT_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    missing = tmp_path / "absent.json"
    cfg = AgentConfig.load(str(missing), server_url="https://lognexa.example.test/")
    assert cfg.server_url == "https://lognexa.example.test"
    # The flag also beats the environment.
    monkeypatch.setenv("LOGNEXA_SERVER_URL", "https://from-env.example.test")
    assert AgentConfig.load(str(missing), server_url="https://flag.example.test").server_url == "https://flag.example.test"
    assert AgentConfig.load(str(missing)).server_url == "https://from-env.example.test"
