"""Durable local event buffer backed by SQLite.

Guarantees across agent restarts and network outages:

* **Persistence** - events survive a crash or reboot (committed to disk).
* **Deduplication** - ``event_uid`` is the primary key, so re-adding an event
  that is still buffered is a no-op (``INSERT OR IGNORE``). The server also
  deduplicates, so at-least-once delivery never creates duplicate rows.
* **Checkpoint recovery** - events stay buffered until the server acknowledges
  them; only then are they deleted.
* **Bounded size** - the oldest events are dropped once ``max_events`` is
  exceeded, and the drop count is reported in the next heartbeat.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class EventBuffer:
    def __init__(self, path: Path, max_events: int = 200_000):
        self.path = path
        self.max_events = max_events
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   event_uid TEXT PRIMARY KEY,
                   payload   TEXT NOT NULL,
                   seq       INTEGER
               )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL)"""
        )
        self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('seq', 0), ('dropped', 0)")
        self._conn.commit()

    def _next_seq(self) -> int:
        cur = self._conn.execute("UPDATE meta SET value = value + 1 WHERE key='seq' RETURNING value")
        return cur.fetchone()[0]

    def add_many(self, items: list[tuple[str, str]]) -> int:
        """Add (event_uid, payload_json) pairs. Returns the number newly stored."""
        if not items:
            return 0
        with self._lock:
            before = self._count()
            rows = [(uid, payload, self._next_seq()) for uid, payload in items]
            self._conn.executemany("INSERT OR IGNORE INTO events(event_uid, payload, seq) VALUES (?,?,?)", rows)
            self._enforce_limit()
            self._conn.commit()
            return self._count() - before + self._just_dropped

    _just_dropped = 0

    def _enforce_limit(self) -> None:
        self._just_dropped = 0
        overflow = self._count() - self.max_events
        if overflow > 0:
            self._conn.execute(
                "DELETE FROM events WHERE seq IN (SELECT seq FROM events ORDER BY seq ASC LIMIT ?)", (overflow,)
            )
            self._conn.execute("UPDATE meta SET value = value + ? WHERE key='dropped'", (overflow,))
            self._just_dropped = overflow

    def peek(self, limit: int) -> list[tuple[str, str]]:
        with self._lock:
            cur = self._conn.execute("SELECT event_uid, payload FROM events ORDER BY seq ASC LIMIT ?", (limit,))
            return cur.fetchall()

    def ack(self, uids: list[str]) -> None:
        if not uids:
            return
        with self._lock:
            self._conn.executemany("DELETE FROM events WHERE event_uid = ?", [(u,) for u in uids])
            self._conn.commit()

    def _count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def pending(self) -> int:
        with self._lock:
            return self._count()

    def dropped(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT value FROM meta WHERE key='dropped'").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
