"""Unit tests: event schema truth discipline (§10, §12, §54)."""
import json

import pytest

from agentpet.events.schema import (EventType, NormalizedEvent, TruthLevel,
                                    make)


def test_requires_source():
    with pytest.raises(ValueError):
        NormalizedEvent(event_type=EventType.FILE_CHANGED, source="")


def test_inferred_confidence_is_capped():
    ev = make(EventType.WRITING_FILE, "fusion:test", agent_id="workbuddy",
              truth_level=TruthLevel.INFERRED, confidence=0.99)
    assert ev.confidence == 0.75


def test_observed_keeps_full_confidence():
    ev = make(EventType.TASK_STARTED, "workbuddy:sdk-log", agent_id="workbuddy",
              confidence=1.0)
    assert ev.confidence == 1.0


def test_confidence_bounds():
    with pytest.raises(ValueError):
        make(EventType.IDLE, "x", agent_id="a", confidence=1.5)


def test_dedup_key_default():
    a = make(EventType.FILE_CHANGED, "src", agent_id="wb", session_id="s1",
             payload={"path": "a.py"})
    b = make(EventType.FILE_CHANGED, "src", agent_id="wb", session_id="s1",
             payload={"path": "a.py"})
    c = make(EventType.FILE_CHANGED, "src", agent_id="wb", session_id="s1",
             payload={"path": "b.py"})
    assert a.dedup_key == b.dedup_key
    assert a.dedup_key != c.dedup_key


def test_roundtrip_serialization():
    ev = make(EventType.GIT_COMMIT_DETECTED, "git:rev-parse", agent_id="wb",
              payload={"sha": "abc1234"})
    d = ev.to_dict()
    back = NormalizedEvent.from_dict(d)
    assert back.event_type == ev.event_type
    assert back.truth_level == ev.truth_level
    assert back.payload["sha"] == "abc1234"


def test_short_contains_truth_and_source():
    ev = make(EventType.TEST_PASSED, "pytest-cache", agent_id="wb",
              truth_level=TruthLevel.OBSERVED)
    s = ev.short()
    assert "OBSERVED" in s and "pytest-cache" in s
