"""Re-enrolment: never report "already enrolled" with a credential the server rejects."""

import json

import pytest

import lognexa_agent.agent as agent_mod
import lognexa_agent.cli as cli
from lognexa_agent.client import ApiClient, ApiError


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A machine enrolled with server A (old credential, state file without server_url)."""
    for var in ("LOGNEXA_SERVER_URL", "LOGNEXA_AGENT_DATA_DIR", "LOGNEXA_ENROLL_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(agent_mod, "collectors_for_platform", lambda: [])
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"server_url": "https://server-b.example.test", "data_dir": str(tmp_path)}))
    (tmp_path / "state.json").write_text(json.dumps({"device_uid": "old-uid", "credential": "old-uid.secret"}))
    calls = {"heartbeat": 0, "enroll": 0}

    def fake_enroll(self, payload):
        calls["enroll"] += 1
        return {"device_uid": "new-uid", "credential": "new-uid.secret2"}

    monkeypatch.setattr(ApiClient, "enroll", fake_enroll)
    return tmp_path, cfg, calls


def _heartbeat(monkeypatch, calls, error=None):
    def fake(self, payload):
        calls["heartbeat"] += 1
        if error:
            raise error
        return {"status": "ok", "rotate_credentials": False}
    monkeypatch.setattr(ApiClient, "heartbeat", fake)


def _state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text())


def test_credential_from_another_server_triggers_enrolment(machine, monkeypatch, capsys):
    tmp_path, cfg, calls = machine
    _heartbeat(monkeypatch, calls, ApiError(401, "invalid_device_credential", "Device credential is not valid"))
    assert cli.main(["-c", str(cfg), "enroll", "--token", "lnx_new_token"]) == 0
    assert calls == {"heartbeat": 1, "enroll": 1}
    state = _state(tmp_path)
    assert state["device_uid"] == "new-uid" and state["server_url"] == "https://server-b.example.test"
    assert "not valid on https://server-b.example.test" in capsys.readouterr().out


def test_valid_credential_is_kept_and_server_recorded(machine, monkeypatch, capsys):
    tmp_path, cfg, calls = machine
    _heartbeat(monkeypatch, calls)
    assert cli.main(["-c", str(cfg), "enroll", "--token", "lnx_new_token"]) == 0
    assert calls == {"heartbeat": 1, "enroll": 0}
    state = _state(tmp_path)
    assert state["device_uid"] == "old-uid" and state["server_url"] == "https://server-b.example.test"
    assert "Already enrolled as device old-uid with https://server-b.example.test" in capsys.readouterr().out


def test_revoked_device_is_not_silently_re_enrolled(machine, monkeypatch, capsys):
    tmp_path, cfg, calls = machine
    _heartbeat(monkeypatch, calls, ApiError(403, "device_revoked", "Device has been revoked"))
    assert cli.main(["-c", str(cfg), "enroll", "--token", "lnx_new_token"]) == 1
    assert calls["enroll"] == 0 and _state(tmp_path)["device_uid"] == "old-uid"
    assert "revoked" in capsys.readouterr().err


def test_invalid_credential_without_token_fails_loudly(machine, monkeypatch, capsys):
    tmp_path, cfg, calls = machine
    _heartbeat(monkeypatch, calls, ApiError(401, "invalid_device_credential", "nope"))
    assert cli.main(["-c", str(cfg), "enroll"]) == 1
    assert calls["enroll"] == 0
    assert "not valid" in capsys.readouterr().err


def test_unreachable_server_is_an_error_not_already_enrolled(machine, monkeypatch, capsys):
    tmp_path, cfg, calls = machine
    _heartbeat(monkeypatch, calls, ApiError(0, "transport_error", "connection refused"))
    assert cli.main(["-c", str(cfg), "enroll", "--token", "lnx_new_token"]) == 1
    captured = capsys.readouterr()
    assert "Already enrolled" not in captured.out and "transport_error" in captured.err
