"""Durable buffer: persistence, deduplication, acknowledgement, bounded size."""

from lognexa_agent.buffer import EventBuffer


def _items(n, start=0):
    return [(f"{i:064x}", f'{{"n":{i}}}') for i in range(start, start + n)]


def test_add_peek_ack_roundtrip(tmp_path):
    buf = EventBuffer(tmp_path / "b.db")
    buf.add_many(_items(5))
    assert buf.pending() == 5
    batch = buf.peek(3)
    assert len(batch) == 3
    buf.ack([u for u, _ in batch])
    assert buf.pending() == 2
    buf.close()


def test_deduplicates_on_uid(tmp_path):
    buf = EventBuffer(tmp_path / "b.db")
    buf.add_many(_items(3))
    buf.add_many(_items(3))  # same uids
    assert buf.pending() == 3
    buf.close()


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "b.db"
    buf = EventBuffer(path)
    buf.add_many(_items(4))
    buf.close()
    # Simulate a restart: events are still there and still ordered.
    buf2 = EventBuffer(path)
    assert buf2.pending() == 4
    first = buf2.peek(10)
    assert [u for u, _ in first] == [u for u, _ in _items(4)]
    buf2.close()


def test_fifo_order_preserved(tmp_path):
    buf = EventBuffer(tmp_path / "b.db")
    buf.add_many(_items(3, start=0))
    buf.add_many(_items(2, start=100))
    order = [u for u, _ in buf.peek(10)]
    assert order == [f"{i:064x}" for i in (0, 1, 2, 100, 101)]
    buf.close()


def test_bounded_size_drops_oldest(tmp_path):
    buf = EventBuffer(tmp_path / "b.db", max_events=10)
    buf.add_many(_items(8, start=0))
    buf.add_many(_items(8, start=100))  # exceeds 10 -> oldest 6 dropped
    assert buf.pending() == 10
    assert buf.dropped() == 6
    remaining = [u for u, _ in buf.peek(20)]
    # the very first events are gone, the newest remain
    assert f"{0:064x}" not in remaining
    assert f"{107:064x}" in remaining
    buf.close()


def test_ack_unknown_is_safe(tmp_path):
    buf = EventBuffer(tmp_path / "b.db")
    buf.add_many(_items(2))
    buf.ack(["deadbeef"])  # not present
    assert buf.pending() == 2
    buf.close()
