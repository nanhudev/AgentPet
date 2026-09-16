"""Unit tests: replay system (§46)."""
import time

from agentpet.sim.replay import ReplayPlayer, load, save
from agentpet.sim.simulator import build as build_simulation
from agentpet.events.schema import EventType, TruthLevel


def test_roundtrip(tmp_path):
    evs = build_simulation(time.time())
    p = tmp_path / "session_001.jsonl"
    save(p, evs)
    back = load(p)
    assert len(back) == len(evs)
    assert back[0].event_type == evs[0].event_type


def test_player_releases_on_cadence():
    now = time.time()
    evs = build_simulation(now)
    player = ReplayPlayer(evs, speed=10.0)
    first = player.pending(now)
    assert first and first[0].event_type is EventType.AGENT_STARTED
    later = player.pending(now + 30)
    assert len(later) > 0
    assert player.done


def test_simulation_events_are_labelled_visual_only():
    evs = build_simulation(time.time())
    assert all(e.truth_level is TruthLevel.VISUAL_ONLY for e in evs)
    assert all(e.source.startswith("simulation:") for e in evs)
    assert any(e.event_type is EventType.GIT_COMMIT_DETECTED for e in evs)


def test_replay_file_is_valid_jsonl(tmp_path):
    evs = build_simulation(time.time())
    p = tmp_path / "s.jsonl"
    save(p, evs)
    for ln in p.read_text(encoding="utf-8").splitlines():
        assert ln.strip()
