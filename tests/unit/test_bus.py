"""Unit tests: event bus dedup / hysteresis (§20, §66)."""
import time

from agentpet.events.bus import EventBus
from agentpet.events.schema import EventType, make


def test_dedup_suppresses_identical_burst():
    bus = EventBus(dedup_window=1.0)
    for _ in range(5):
        bus.publish(make(EventType.FILE_CHANGED, "src", agent_id="wb",
                         session_id="s", payload={"path": "a.py"}))
    assert bus.emitted == 1
    assert bus.deduped == 4


def test_different_paths_are_not_deduped():
    bus = EventBus(dedup_window=1.0)
    bus.publish(make(EventType.FILE_CHANGED, "src", agent_id="wb",
                     session_id="s", payload={"path": "a.py"}))
    bus.publish(make(EventType.FILE_CHANGED, "src", agent_id="wb",
                     session_id="s", payload={"path": "b.py"}))
    assert bus.emitted == 2


def test_drain_returns_events_and_notifies_subscribers():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda ev: seen.append(ev))
    bus.publish(make(EventType.TASK_STARTED, "src", agent_id="wb"))
    out = bus.drain()
    assert len(out) == 1 and len(seen) == 1


def test_bad_subscriber_does_not_break_drain():
    bus = EventBus()

    def boom(ev):
        raise RuntimeError("nope")

    bus.subscribe(boom)
    bus.publish(make(EventType.IDLE, "src", agent_id="wb"))
    assert len(bus.drain()) == 1


def test_history_bound():
    bus = EventBus()
    for i in range(600):
        bus.publish(make(EventType.FILE_CHANGED, "src", agent_id="wb",
                         payload={"path": f"f{i}.py"}))
    assert len(bus.history(500)) <= 500
