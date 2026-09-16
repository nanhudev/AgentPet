"""Unit tests: pet finite state machine (§18, §20)."""
import pytest

from agentpet.behavior.pet import (MIN_DWELL, PetInstance, PetManager,
                                   PetState, Personality)


def test_spawn_then_idle():
    p = PetInstance(pet_id="p1")
    assert p.state is PetState.SPAWN
    assert p.transition(PetState.IDLE)
    assert p.state is PetState.IDLE


def test_illegal_transition_is_rejected():
    p = PetInstance(pet_id="p1")
    p.transition(PetState.IDLE)
    assert not p.can_transition(PetState.WATCH_TERMINAL)
    assert p.state is PetState.IDLE


def test_sleep_can_be_interrupted_by_task():
    """§20 — a sleeping pet must wake for TASK_STARTED."""
    p = PetInstance(pet_id="p1")
    p.transition(PetState.IDLE)
    p.transition(PetState.SLEEP)
    assert p.state is PetState.SLEEP
    assert p.can_transition(PetState.NOTICE_TASK)


def test_sleep_cannot_jump_to_celebrate():
    p = PetInstance(pet_id="p1")
    p.transition(PetState.IDLE)
    p.transition(PetState.SLEEP)
    assert not p.can_transition(PetState.CELEBRATE)


def test_move_then_arrive():
    p = PetInstance(pet_id="p1", x=0.0, y=0.0)
    p.transition(PetState.IDLE)
    p.transition(PetState.MOVE_TO_TERMINAL)
    p.move_to(100.0, 0.0)
    for _ in range(200):
        p.update(0.05, (0, 0, 1000, 1000))
    assert p.arrived()
    assert abs(p.x - 100.0) < 1.0


def test_stays_inside_bounds():
    p = PetInstance(pet_id="p1", x=500.0, y=500.0)
    p.move_to(-5000.0, -5000.0)
    for _ in range(400):
        p.update(0.05, (0, 0, 800, 600))
    assert 0 < p.x < 800 and 0 < p.y < 600


def test_animation_mapping_is_asset_independent():
    p = PetInstance(pet_id="p1")
    p.transition(PetState.IDLE)
    p.transition(PetState.MOVE_TO_TERMINAL)
    assert p.animation.value == "run"
    p.transition(PetState.WATCH_TERMINAL)
    assert p.animation.value == "watch"


def test_manager_supports_multiple_pets():
    """§21 — never a hard-coded singleton."""
    m = PetManager()
    pets = m.spawn(3, (100.0, 900.0), Personality())
    assert len(pets) == 3
    assert m.primary is pets[0]
    assert len({p.pet_id for p in m.pets}) == 3
