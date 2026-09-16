"""Pet actor + finite state machine (§17, §18, §30).

The pet is an independent actor with position, velocity and a state machine.
Behavior emits *AnimationKey* strings; the renderer decides how to draw them —
so a future sprite/Live2D swap never touches this file (§30).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class PetState(str, Enum):
    SPAWN = "SPAWN"
    IDLE = "IDLE"
    LOOK_AROUND = "LOOK_AROUND"
    WALK = "WALK"
    RUN = "RUN"
    SIT = "SIT"
    SLEEP = "SLEEP"
    WAKE = "WAKE"
    NOTICE_AGENT = "NOTICE_AGENT"
    NOTICE_TASK = "NOTICE_TASK"
    MOVE_TO_TERMINAL = "MOVE_TO_TERMINAL"
    WATCH_TERMINAL = "WATCH_TERMINAL"
    MOVE_TO_EDITOR = "MOVE_TO_EDITOR"
    WATCH_EDITOR = "WATCH_EDITOR"
    TYPE_SIMULATION = "TYPE_SIMULATION"
    TESTING = "TESTING"
    CONFUSED = "CONFUSED"
    FRUSTRATED = "FRUSTRATED"
    SUCCESS = "SUCCESS"
    CELEBRATE = "CELEBRATE"
    ERROR_REACTION = "ERROR_REACTION"
    GIT_COMMIT = "GIT_COMMIT"
    GIT_PUSH = "GIT_PUSH"
    RETURN_HOME = "RETURN_HOME"


class AnimationKey(str, Enum):
    """What the renderer must be able to draw (§29)."""
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    SIT = "sit"
    SLEEP = "sleep"
    WAKE = "wake"
    NOTICE = "notice"
    WATCH = "watch"
    TYPING = "typing"
    TESTING = "testing"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    CELEBRATE = "celebrate"
    ERROR = "error"
    CARRY = "carry"


STATE_TO_ANIMATION: Dict[PetState, AnimationKey] = {
    PetState.SPAWN: AnimationKey.IDLE,
    PetState.IDLE: AnimationKey.IDLE,
    PetState.LOOK_AROUND: AnimationKey.IDLE,
    PetState.WALK: AnimationKey.WALK,
    PetState.RUN: AnimationKey.RUN,
    PetState.SIT: AnimationKey.SIT,
    PetState.SLEEP: AnimationKey.SLEEP,
    PetState.WAKE: AnimationKey.WAKE,
    PetState.NOTICE_AGENT: AnimationKey.NOTICE,
    PetState.NOTICE_TASK: AnimationKey.NOTICE,
    PetState.MOVE_TO_TERMINAL: AnimationKey.RUN,
    PetState.MOVE_TO_EDITOR: AnimationKey.RUN,
    PetState.WATCH_TERMINAL: AnimationKey.WATCH,
    PetState.WATCH_EDITOR: AnimationKey.WATCH,
    PetState.TYPE_SIMULATION: AnimationKey.TYPING,
    PetState.TESTING: AnimationKey.TESTING,
    PetState.CONFUSED: AnimationKey.CONFUSED,
    PetState.FRUSTRATED: AnimationKey.FRUSTRATED,
    PetState.SUCCESS: AnimationKey.CELEBRATE,
    PetState.CELEBRATE: AnimationKey.CELEBRATE,
    PetState.ERROR_REACTION: AnimationKey.ERROR,
    PetState.GIT_COMMIT: AnimationKey.CARRY,
    PetState.GIT_PUSH: AnimationKey.CARRY,
    PetState.RETURN_HOME: AnimationKey.WALK,
}

# Legal transitions. Anything not listed is rejected -> no impossible states.
TRANSITIONS: Dict[PetState, Tuple[PetState, ...]] = {
    PetState.SPAWN: (PetState.IDLE, PetState.WALK),
    PetState.IDLE: (PetState.WALK, PetState.SIT, PetState.LOOK_AROUND,
                    PetState.SLEEP, PetState.NOTICE_AGENT, PetState.NOTICE_TASK,
                    PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR,
                    PetState.GIT_COMMIT, PetState.RETURN_HOME),
    PetState.LOOK_AROUND: (PetState.IDLE, PetState.WALK, PetState.SIT,
                           PetState.NOTICE_AGENT, PetState.NOTICE_TASK,
                           PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR),
    PetState.WALK: (PetState.IDLE, PetState.SIT, PetState.LOOK_AROUND,
                    PetState.RUN, PetState.SLEEP, PetState.NOTICE_AGENT,
                    PetState.NOTICE_TASK, PetState.MOVE_TO_TERMINAL,
                    PetState.MOVE_TO_EDITOR, PetState.RETURN_HOME),
    PetState.RUN: (PetState.IDLE, PetState.WALK, PetState.NOTICE_AGENT,
                   PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR,
                   PetState.RETURN_HOME),
    PetState.SIT: (PetState.IDLE, PetState.SLEEP, PetState.WALK,
                   PetState.NOTICE_AGENT, PetState.NOTICE_TASK,
                   PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR),
    PetState.SLEEP: (PetState.WAKE, PetState.NOTICE_AGENT, PetState.NOTICE_TASK,
                     PetState.MOVE_TO_TERMINAL),
    PetState.WAKE: (PetState.IDLE, PetState.WALK, PetState.NOTICE_TASK,
                    PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR),
    PetState.NOTICE_AGENT: (PetState.WALK, PetState.RUN, PetState.IDLE,
                            PetState.MOVE_TO_TERMINAL, PetState.MOVE_TO_EDITOR,
                            PetState.WATCH_TERMINAL, PetState.WATCH_EDITOR),
    PetState.NOTICE_TASK: (PetState.RUN, PetState.MOVE_TO_TERMINAL,
                           PetState.MOVE_TO_EDITOR, PetState.WALK, PetState.IDLE),
    PetState.MOVE_TO_TERMINAL: (PetState.WATCH_TERMINAL, PetState.IDLE,
                                PetState.MOVE_TO_EDITOR, PetState.RUN),
    PetState.MOVE_TO_EDITOR: (PetState.WATCH_EDITOR, PetState.IDLE,
                              PetState.MOVE_TO_TERMINAL, PetState.TYPE_SIMULATION),
    PetState.WATCH_TERMINAL: (PetState.IDLE, PetState.MOVE_TO_EDITOR,
                              PetState.TESTING, PetState.CONFUSED,
                              PetState.FRUSTRATED, PetState.SUCCESS,
                              PetState.ERROR_REACTION, PetState.WALK),
    PetState.WATCH_EDITOR: (PetState.IDLE, PetState.TYPE_SIMULATION,
                            PetState.MOVE_TO_TERMINAL, PetState.WALK,
                            PetState.NOTICE_TASK),
    PetState.TYPE_SIMULATION: (PetState.WATCH_EDITOR, PetState.IDLE,
                               PetState.MOVE_TO_TERMINAL, PetState.WATCH_TERMINAL),
    PetState.TESTING: (PetState.CONFUSED, PetState.FRUSTRATED, PetState.SUCCESS,
                       PetState.IDLE, PetState.WATCH_TERMINAL,
                       PetState.MOVE_TO_EDITOR),
    PetState.CONFUSED: (PetState.FRUSTRATED, PetState.IDLE, PetState.WATCH_TERMINAL,
                        PetState.MOVE_TO_EDITOR, PetState.TESTING),
    PetState.FRUSTRATED: (PetState.IDLE, PetState.MOVE_TO_EDITOR,
                          PetState.WATCH_TERMINAL, PetState.CONFUSED),
    PetState.SUCCESS: (PetState.CELEBRATE, PetState.IDLE, PetState.WATCH_TERMINAL),
    PetState.CELEBRATE: (PetState.IDLE, PetState.RETURN_HOME, PetState.WALK),
    PetState.ERROR_REACTION: (PetState.CONFUSED, PetState.MOVE_TO_EDITOR,
                              PetState.IDLE, PetState.WATCH_TERMINAL),
    PetState.GIT_COMMIT: (PetState.GIT_PUSH, PetState.IDLE, PetState.CELEBRATE,
                          PetState.RETURN_HOME),
    PetState.GIT_PUSH: (PetState.IDLE, PetState.CELEBRATE, PetState.RETURN_HOME),
    PetState.RETURN_HOME: (PetState.IDLE, PetState.SIT, PetState.SLEEP,
                           PetState.WALK, PetState.NOTICE_TASK),
}

# States that a high-priority event may jump to from almost anywhere.
EMERGENCY_STATES = frozenset({
    PetState.NOTICE_AGENT, PetState.NOTICE_TASK, PetState.MOVE_TO_TERMINAL,
    PetState.MOVE_TO_EDITOR, PetState.CELEBRATE, PetState.SUCCESS,
    PetState.ERROR_REACTION, PetState.CONFUSED, PetState.FRUSTRATED,
    PetState.GIT_COMMIT, PetState.GIT_PUSH,
})

MIN_DWELL: Dict[PetState, float] = {
    PetState.IDLE: 1.5, PetState.SIT: 3.0, PetState.SLEEP: 6.0,
    PetState.WATCH_TERMINAL: 2.0, PetState.WATCH_EDITOR: 2.0,
    PetState.NOTICE_AGENT: 0.9, PetState.NOTICE_TASK: 0.9,
    PetState.CELEBRATE: 2.2, PetState.CONFUSED: 1.2, PetState.FRUSTRATED: 1.4,
    PetState.TESTING: 2.0, PetState.GIT_COMMIT: 2.0, PetState.GIT_PUSH: 1.6,
    PetState.TYPE_SIMULATION: 1.6, PetState.ERROR_REACTION: 1.2,
}


@dataclass
class Personality:
    """§31 — no LLM, just parameters."""
    energy: float = 0.7
    curiosity: float = 0.8
    patience: float = 0.5
    expressiveness: float = 0.8
    sleepiness: float = 0.35

    def as_dict(self) -> Dict[str, float]:
        return {"energy": self.energy, "curiosity": self.curiosity,
                "patience": self.patience, "expressiveness": self.expressiveness,
                "sleepiness": self.sleepiness}


@dataclass
class PetInstance:
    pet_id: str
    x: float = 200.0
    y: float = 900.0
    home_x: float = 200.0
    home_y: float = 900.0
    state: PetState = PetState.SPAWN
    prev_state: Optional[PetState] = None
    direction: int = 1
    destination: Optional[Tuple[float, float]] = None
    state_time: float = 0.0
    emotion: str = "calm"
    energy: float = 1.0
    scale: float = 1.0
    speed: float = 90.0
    attention_target: Optional[str] = None
    current_agent: Optional[str] = None
    activity: str = ""
    personality: Personality = field(default_factory=Personality)
    bubble: str = ""
    bubble_until: float = 0.0
    animation_t: float = 0.0
    pinned_until: float = 0.0        # set after the user drags the pet by hand
    _last_dist: float = field(default=float("inf"), repr=False)
    _stuck: int = field(default=0, repr=False)

    # --- state ---------------------------------------------------------
    @property
    def animation(self) -> AnimationKey:
        return STATE_TO_ANIMATION.get(self.state, AnimationKey.IDLE)

    def can_transition(self, to: PetState) -> bool:
        if to == self.state:
            return False
        if self.state is PetState.SPAWN:
            return True
        # P0 reactions may interrupt almost anything (§20). Deep sleep still has
        # to wake up first so the animation reads correctly.
        if to in EMERGENCY_STATES and self.state is not PetState.SLEEP:
            return True
        return to in TRANSITIONS.get(self.state, ())

    def transition(self, to: PetState) -> bool:
        if not self.can_transition(to):
            # allow legalising via IDLE when a jump is not directly permitted
            if self.can_transition(PetState.IDLE) and \
                    PetState.IDLE in TRANSITIONS.get(self.state, ()):
                self._force(PetState.IDLE)
                if to in TRANSITIONS.get(PetState.IDLE, ()):
                    self._force(to)
                    return True
            return False
        self._force(to)
        return True

    def _force(self, to: PetState) -> None:
        self.prev_state = self.state
        self.state = to
        self.state_time = 0.0
        if to in (PetState.MOVE_TO_TERMINAL, PetState.RUN):
            self.speed = 210.0
        elif to in (PetState.WALK, PetState.RETURN_HOME):
            self.speed = 95.0
        elif to is PetState.MOVE_TO_EDITOR:
            self.speed = 200.0

    def set_bubble(self, text: str, seconds: float = 4.0, now: float = 0.0) -> None:
        self.bubble = text
        self.bubble_until = now + seconds

    # --- motion --------------------------------------------------------
    def move_to(self, x: float, y: float) -> None:
        self.destination = (x, y)

    def arrived(self) -> bool:
        return self.destination is None

    def update(self, dt: float, bounds: Tuple[float, float, float, float]) -> None:
        """bounds = (left, top, right, bottom) in world coordinates."""
        self.state_time += dt
        self.animation_t += dt
        if self.bubble_until and self.animation_t > self.bubble_until:
            self.bubble = ""
            self.bubble_until = 0.0

        if self.destination is not None:
            dx = self.destination[0] - self.x
            dy = self.destination[1] - self.y
            dist = math.hypot(dx, dy)
            step = self.speed * dt * (0.6 + 0.4 * self.personality.energy)
            if dist <= max(step, 3.0):
                self.x, self.y = self.destination
                self.destination = None
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step
                if abs(dx) > 1.0:
                    self.direction = 1 if dx > 0 else -1

        # soft clamp inside the world
        left, top, right, bottom = bounds
        pad = 24.0
        self.x = max(left + pad, min(right - pad, self.x))
        self.y = max(top + pad, min(bottom - pad, self.y))

        # a destination outside the world would be unreachable forever because
        # of the clamp above — give up instead of walking into a wall
        if self.destination is not None:
            remaining = math.hypot(self.destination[0] - self.x,
                                   self.destination[1] - self.y)
            if remaining >= self._last_dist - 0.01:
                self._stuck += 1
                if self._stuck > 5:
                    self.destination = None
                    self._stuck = 0
            else:
                self._stuck = 0
            self._last_dist = remaining
        else:
            self._last_dist = float("inf")
            self._stuck = 0

    def rect(self, w: float = 74.0, h: float = 86.0) -> Tuple[float, float, float, float]:
        s = self.scale
        return (self.x - w * s / 2, self.y - h * s, w * s, h * s)


class PetManager:
    """§21 — never a hard-coded singleton."""

    def __init__(self) -> None:
        self.pets: List[PetInstance] = []

    def spawn(self, count: int, home: Tuple[float, float],
              personality: Optional[Personality] = None) -> List[PetInstance]:
        self.pets = []
        for i in range(max(1, count)):
            jitter = (i - (count - 1) / 2) * 90.0
            pet = PetInstance(
                pet_id=f"pet-{i+1}",
                x=home[0] + jitter,
                y=home[1],
                home_x=home[0] + jitter,
                home_y=home[1],
                state=PetState.SPAWN,
                personality=personality or Personality(),
            )
            pet.transition(PetState.IDLE)
            self.pets.append(pet)
        return self.pets

    @property
    def primary(self) -> Optional[PetInstance]:
        return self.pets[0] if self.pets else None

    def update(self, dt: float, bounds: Tuple[float, float, float, float]) -> None:
        for p in self.pets:
            p.update(dt, bounds)
