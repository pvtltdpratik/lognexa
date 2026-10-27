"""Agent redaction must strip secrets before events are buffered."""

import pytest

from lognexa_agent.models import Event
from lognexa_agent.redaction import redact_event, redact_obj, redact_text

SECRETS = [
    ("mysql -u root -pSuperSecret db", "SuperSecret"),
    ("sqlcmd -S srv -U sa -P Hunter2! -Q 'select 1'", "Hunter2!"),
    ("connect postgresql://user:p4ssw0rd@host/db", "p4ssw0rd"),
    ("--password MyPass123", "MyPass123"),
    ("API_KEY=sk_live_abcdef123456", "sk_live_abcdef123456"),
    ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ("curl -H 'token: secrettoken12345' url", "secrettoken12345"),
    ("net user admin P@ssw0rd123 /add", "P@ssw0rd123"),
]


@pytest.mark.parametrize("text,secret", SECRETS)
def test_secrets_are_redacted(text, secret):
    redacted, changed = redact_text(text)
    assert changed is True
    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_benign_text_unchanged():
    text = "powershell Get-Process | Sort-Object CPU"
    redacted, changed = redact_text(text)
    assert changed is False and redacted == text


def test_private_key_block_redacted():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEvQID...\n-----END RSA PRIVATE KEY-----"
    redacted, changed = redact_text(text)
    assert changed and "MIIEvQID" not in redacted


def test_redact_obj_by_key_name():
    obj = {"user": "bob", "password": "hunter2", "nested": {"api_key": "abc123", "ok": "visible"}}
    out, changed = redact_obj(obj)
    assert changed
    assert out["password"] == "[REDACTED]" and out["nested"]["api_key"] == "[REDACTED]"
    assert out["user"] == "bob" and out["nested"]["ok"] == "visible"


def test_redact_event_in_place():
    ev = Event(source="t", category="process", event_type="process_start",
               command_line="psql postgresql://u:topsecret@db/app", message="ran psql")
    redact_event(ev)
    assert "topsecret" not in ev.command_line
