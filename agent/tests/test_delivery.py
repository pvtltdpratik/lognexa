"""Delivery robustness: timestamps, schema fitting, and poison-event isolation."""

from datetime import datetime, timezone

from lognexa_agent.agent import Agent
from lognexa_agent.buffer import EventBuffer
from lognexa_agent.client import ApiError
from lognexa_agent.collectors.windows import _parse_ts
from lognexa_agent.config import AgentConfig
from lognexa_agent.models import FIELD_LIMITS, Event, fit_payload


def test_windows_timestamp_with_100ns_precision():
    # wevtutil emits 7 fractional digits; Python 3.10 fromisoformat only takes 6.
    ts = _parse_ts("2026-10-27T18:40:17.4392170Z")
    assert ts == datetime(2026, 10, 27, 18, 40, 17, 439217, tzinfo=timezone.utc)
    assert _parse_ts("2026-10-27T18:40:17Z") == datetime(2026, 10, 27, 18, 40, 17, tzinfo=timezone.utc)


def test_payload_is_clamped_to_server_limits():
    ev = Event(source="powershell", category="process", event_type="powershell_script",
               command_line="x" * 50_000, username="u" * 500, src_ip="-", dst_ip="fe80::1%12",
               dst_port=70_000, raw={"EventID": "4104"})
    p = ev.to_payload("scope")
    assert len(p["command_line"]) == FIELD_LIMITS["command_line"]
    assert p["command_line"].endswith("[truncated]")
    assert len(p["username"]) == FIELD_LIMITS["username"]
    assert "src_ip" not in p and p["dst_ip"] == "fe80::1" and "dst_port" not in p
    assert p["raw"] == {"EventID": "4104", "truncated_fields": ["username", "command_line"]}


def test_oversized_raw_is_replaced():
    p = fit_payload({"event_uid": "a" * 64, "timestamp": "2026-01-01T00:00:00", "source": "s1",
                     "category": "system", "event_type": "e1", "raw": {"blob": "z" * 20_000}})
    assert p["raw"] == {"truncated_fields": ["raw"]}


class _RejectingClient:
    """Fake server: 422 for any batch containing a poisoned event."""

    def __init__(self):
        self.calls = 0
        self.accepted = []

    def send_events(self, events):
        self.calls += 1
        if any(e.get("message") == "poison" for e in events):
            raise ApiError(422, "validation_error", "bad event")
        self.accepted.extend(events)
        return {"accepted": len(events)}


def _agent(tmp_path, client):
    agent = Agent.__new__(Agent)  # skip collector/enrolment setup
    agent.config = AgentConfig(server_url="https://example.test", data_dir=tmp_path)
    agent.buffer = EventBuffer(tmp_path / "buffer.db")
    agent.client = client
    agent._rejected = 0
    return agent


def test_one_bad_event_does_not_block_the_batch(tmp_path):
    client = _RejectingClient()
    agent = _agent(tmp_path, client)
    events = [{"event_uid": f"{i:064x}", "message": "poison" if i == 37 else "ok"} for i in range(100)]
    agent.buffer.add_many([(e["event_uid"], "{}") for e in events])

    rejected = agent._deliver([e["event_uid"] for e in events], events)

    assert rejected == 1
    assert len(client.accepted) == 99                    # every good event delivered
    assert agent.buffer.pending() == 0                   # nothing left to block the queue
    assert client.calls <= 2 * 8                         # bisection, not one request per event
    assert "poison" in (tmp_path / "rejected.jsonl").read_text(encoding="utf-8")
    agent.buffer.close()


def test_transient_errors_keep_events_buffered(tmp_path):
    class _Down:
        def send_events(self, events):
            raise ApiError(503, "unavailable", "server down")

    agent = _agent(tmp_path, _Down())
    agent.buffer.add_many([("a" * 64, "{}")])
    try:
        agent._deliver(["a" * 64], [{"event_uid": "a" * 64}])
    except ApiError as exc:
        assert exc.retryable
    assert agent.buffer.pending() == 1                   # retried later, never dropped
    assert not (tmp_path / "rejected.jsonl").exists()
    agent.buffer.close()
