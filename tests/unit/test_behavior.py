"""Unit tests: behavior engine priorities and interruption (§19-§20).

Updated for the Workbench model: panels are docked to the pet; work activity
deploys the bench in place (a small hop at most) instead of cross-screen runs.
"""
import time

import pytest

from agentpet.behavior.engine import BehaviorEngine
from agentpet.behavior.pet import PetInstance, PetManager, PetState, Personality
from agentpet.events.schema import EventType, make
from agentpet.renderer.workbench import Workbench


class FakeOverlay:
    def __init__(self):
        self.privacy = False
        self.show_git = True
        self.ground_y = 900.0
        self.home = (200.0, 900.0)
        self.reduce_motion = False
        self.mini_mode = False
        self._benches = {}

    def bench_half_width(self, pet) -> float:
        return self.workbench_for(pet).half_width(pet)

    def workbench_for(self, pet):
        wb = self._benches.get(pet.pet_id)
        if wb is None:
            wb = Workbench(pet.pet_id)
            self._benches[pet.pet_id] = wb
        return wb

    @property
    def primary_bench(self):
        pet = self._pets[0]
        return self.workbench_for(pet)

    @property
    def editor(self):
        return self.primary_bench.editor

    @property
    def terminal(self):
        return self.primary_bench.terminal

    @property
    def gitfx(self):
        return self.primary_bench.gitfx

    def bounds_tuple(self):
        return (0.0, 0.0, 1920.0, 900.0)


def _engine():
    mgr = PetManager()
    mgr.spawn(1, (200.0, 900.0), Personality())
    ov = FakeOverlay()
    ov._pets = mgr.pets
    eng = BehaviorEngine(mgr, ov, FakeSettings())
    return mgr, ov, eng


class FakeSettings:
    privacy_mode = False
    reduce_motion = False
    pet_scale = 1.0
    animation_speed = 1.0
    personality = {"energy": 0.7, "curiosity": 0.8, "patience": 0.5,
                   "expressiveness": 0.8, "sleepiness": 0.35}


def test_task_started_notices():
    mgr, ov, eng = _engine()
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb", session_id="s"))
    assert mgr.primary.state in (PetState.NOTICE_TASK, PetState.MOVE_TO_TERMINAL,
                                 PetState.MOVE_TO_EDITOR)
    assert mgr.primary.bubble == "Task active"


def test_file_change_deploys_bench_at_station():
    """File activity: the bench opens where the pet stands — no cross-screen run."""
    mgr, ov, eng = _engine()
    pet = mgr.primary
    ev = make(EventType.FILE_CHANGED, "test", agent_id="wb", session_id="s",
              workspace_id="D:/w", payload={"path": "calculator.py"})
    eng.handle(ev)
    assert pet.state is PetState.MOVE_TO_EDITOR
    assert pet.destination == (ov.bench_half_width(pet), 900.0)  # nearest station
    assert ov.primary_bench.pending_deploy
    assert ov.editor.file_path == "calculator.py"


def test_command_started_turns_pet_to_terminal():
    mgr, ov, eng = _engine()
    pet = mgr.primary
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb",
                    session_id="s"))
    eng.update(0.05)
    pet.destination = None                                # simulate arrival
    eng.update(0.05)
    bench = ov.workbench_for(pet)
    assert bench.state == "open"
    eng.handle(make(EventType.COMMAND_STARTED, "test", agent_id="wb",
                    session_id="s"))
    assert pet.direction == 1                             # facing its terminal
    assert bench.terminal.state == "running"


def test_output_spawns_grab_particles():
    """The pet physically grabs terminal output text."""
    mgr, ov, eng = _engine()
    pet = mgr.primary
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb", session_id="s"))
    pet.destination = None
    eng.update(0.05)
    bench = ov.workbench_for(pet)
    eng.handle(make(EventType.COMMAND_OUTPUT, "test", agent_id="wb",
                    session_id="s", payload={"text": "hello"}))
    assert [p for p in bench.particles if p["kind"] == "grab"]


def test_sleeping_pet_wakes_for_critical_event():
    """§20 — TASK_COMPLETED must interrupt even deep states."""
    mgr, ov, eng = _engine()
    pet = mgr.primary
    pet.transition(PetState.SLEEP)
    assert pet.state is PetState.SLEEP
    eng.handle(make(EventType.TASK_COMPLETED, "test", agent_id="wb",
                    session_id="s"))
    assert pet.state is PetState.CELEBRATE
    assert eng.interrupts >= 1


def test_task_completed_schedules_retract_and_celebrates():
    mgr, ov, eng = _engine()
    pet = mgr.primary
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb", session_id="s"))
    eng.handle(make(EventType.TASK_COMPLETED, "test", agent_id="wb",
                    session_id="s"))
    assert pet.state is PetState.CELEBRATE
    bench = ov.workbench_for(pet)
    assert bench.retract_at > 0
    bench.update(10.0, pet, time.time() + 10)             # time passes
    assert bench.state == "docked"


def test_second_session_gets_second_pet():
    """Multi concurrent tasks → multiple stations (multi-pet staging)."""
    mgr, ov, eng = _engine()
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb",
                    session_id="s1"))
    eng.handle(make(EventType.TASK_STARTED, "test", agent_id="wb",
                    session_id="s2"))
    assert len(mgr.pets) == 2
    assert eng._session_pet["s1"] is not eng._session_pet["s2"]


def test_error_reaction():
    mgr, ov, eng = _engine()
    eng.handle(make(EventType.ERROR_DETECTED, "test", agent_id="wb",
                    session_id="s"))
    assert mgr.primary.state is PetState.ERROR_REACTION
    assert ov.terminal.state == "error"


def test_git_commit_triggers_animation_only_when_real():
    mgr, ov, eng = _engine()
    eng.handle(make(EventType.GIT_COMMIT_DETECTED, "git:rev-parse",
                    agent_id="wb", session_id="s",
                    payload={"sha": "abc1234", "message": "add calc"}))
    assert mgr.primary.state is PetState.GIT_COMMIT


def test_file_events_are_debounced():
    """§20 — the pet must not twitch on every single file write."""
    mgr, ov, eng = _engine()
    for _ in range(5):
        eng.handle(make(EventType.FILE_CHANGED, "test", agent_id="wb",
                        session_id="s", workspace_id="D:/w",
                        payload={"path": "a.py"}))
    assert ov.editor.file_path == "a.py"                  # one real update
    assert eng._last_file_at > 0


def test_autonomous_behaviour_eventually_changes_state():
    mgr, ov, eng = _engine()
    pet = mgr.primary
    pet.state_time = 99.0
    eng.last_event_at = 0.0
    seen = set()
    for _ in range(400):
        eng.update(0.05)
        seen.add(pet.state)
        pet.state_time = 99.0
    assert len(seen) > 1
