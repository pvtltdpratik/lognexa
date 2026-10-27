"""Collector base class and health reporting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from lognexa_agent.config import AgentConfig, State
from lognexa_agent.models import Event, utcnow

log = logging.getLogger("lognexa.agent.collector")

# status: ok | unsupported | permission_denied | error | disabled
STATUSES = ("ok", "unsupported", "permission_denied", "error", "disabled")


@dataclass
class CollectorHealth:
    name: str
    status: str = "ok"
    detail: str | None = None
    events_collected: int = 0
    last_run_at: datetime | None = None

    def to_payload(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "events_collected": self.events_collected,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
        }


class Collector:
    """Base class. Subclasses set ``name`` and implement ``collect``.

    ``available()`` reports whether the collector can run on this host (OS match,
    tool present, sufficient privilege). An unavailable collector is reported in
    heartbeats with a clear reason instead of silently producing nothing.
    """

    name: str = "base"

    def __init__(self, config: AgentConfig, state: State):
        self.config = config
        self.state = state
        self.health = CollectorHealth(name=self.name)

    def available(self) -> tuple[bool, str, str | None]:
        """Return (ok, status, detail). Override in subclasses."""
        return True, "ok", None

    def collect(self) -> Iterator[Event]:
        """Yield new events since the last checkpoint. Override in subclasses."""
        return iter(())

    # --- checkpoint helpers ---------------------------------------------------
    def get_checkpoint(self, default=None):
        return self.state.checkpoint(self.name, default)

    def set_checkpoint(self, value) -> None:
        self.state.set_checkpoint(self.name, value)

    def run(self) -> list[Event]:
        """Run one collection cycle, updating health. Never raises."""
        self.health.last_run_at = utcnow()
        try:
            events = list(self.collect())
        except PermissionError as exc:
            self.health.status = "permission_denied"
            self.health.detail = str(exc)[:300]
            return []
        except Exception as exc:  # a broken collector must not stop the agent
            log.exception("collector %s failed", self.name)
            self.health.status = "error"
            self.health.detail = f"{type(exc).__name__}: {exc}"[:300]
            return []
        self.health.status = "ok"
        self.health.detail = None
        self.health.events_collected += len(events)
        return events
