"""Behavior engine (§19-§20): priority + state machine + weighted random.

Workbench model: when work happens the pet deploys its docked Mini Terminal /
Mini Editor right where it stands (a short hop at most) and STAYS at its
station — no random cross-screen runs. Activity is expressed as turns, grabs
and gestures toward the docked panels. Panels retract when the work ends or
the world goes quiet.

Multi-task: each active session gets its own pet (up to 3), and each pet
carries its own workbench — so two concurrent tasks produce two stations.
"""
from __future__ import annotations

import random
import time
from typing import Dict, Optional, Tuple

from ..events.schema import EventType, NormalizedEvent
from ..events.bus import EventBus
from .pet import (MIN_DWELL, PetInstance, PetManager, PetState, Personality)

# priority tiers
P0 = {EventType.ERROR_DETECTED, EventType.TASK_FAILED, EventType.TASK_COMPLETED,
      EventType.COMMAND_FAILED, EventType.TEST_FAILED}
P1 = {EventType.COMMAND_STARTED, EventType.COMMAND_OUTPUT, EventType.FILE_CHANGED,
      EventType.WRITING_FILE, EventType.TEST_STARTED, EventType.TEST_PASSED,
      EventType.PLANNING, EventType.THINKING, EventType.TASK_STARTED,
      EventType.TASK_DETECTED, EventType.GIT_COMMIT_DETECTED,
      EventType.GIT_PUSH_DETECTED, EventType.AGENT_STARTED,
      EventType.AGENT_DISCOVERED, EventType.DEBUGGING_STARTED}

MAX_PETS = 2


class BehaviorEngine:
    def __init__(self, manager: PetManager, overlay, settings,
                 min_switch: float = 0.8) -> None:
        self.manager = manager
        self.overlay = overlay
        self.settings = settings
        self.min_switch = min_switch
        self.last_event_at = 0.0
        self.last_handled: Optional[str] = None
        self.interrupts = 0
        self._last_file_at = 0.0
        self._session_pet: Dict[str, PetInstance] = {}

    # --- pet routing ----------------------------------------------------
    def _pet_for(self, ev: NormalizedEvent) -> PetInstance:
        """Route an event to the pet assigned to its session. An unknown
        session uses the primary pet when it is free; only when the primary is
        already bound to another active session do we claim (or spawn) a
        second pet — that is the multi-task staging rule."""
        sid = ev.session_id or ""
        assigned = set(id(p) for p in self._session_pet.values())
        if sid and sid in self._session_pet:
            pet = self._session_pet[sid]
            if pet in self.manager.pets:
                return pet
        primary = self.manager.primary
        if not sid or id(primary) not in assigned:
            if sid:
                self._session_pet[sid] = primary
            return primary
        # primary busy with another session → claim a free pet
        for pet in self.manager.pets:
            if id(pet) not in assigned:
                self._session_pet[sid] = pet
                return pet
        if len(self.manager.pets) < MAX_PETS:
            pet = self._add_pet()
            if pet is not None:
                self._session_pet[sid] = pet
                return pet
        return primary

    def _add_pet(self) -> Optional[PetInstance]:
        if len(self.manager.pets) >= MAX_PETS:
            return None
        home = self.overlay.home
        i = len(self.manager.pets) + 1
        pet = PetInstance(
            pet_id=f"pet-{i}",
            x=home[0] + 90.0 * i, y=home[1],
            home_x=home[0] + 90.0 * i, home_y=home[1],
            state=PetState.SPAWN,
            personality=Personality(**self.settings.personality))
        pet.scale = self.settings.pet_scale
        pet.speed = 95.0 * self.settings.animation_speed
        self.manager.pets.append(pet)
        return pet

    def _release(self, pet: PetInstance) -> None:
        for sid, p in list(self._session_pet.items()):
            if p is pet:
                self._session_pet.pop(sid, None)
        pet.current_agent = None

    # ------------------------------------------------------------------
    def handle(self, ev: NormalizedEvent) -> None:
        pet = self._pet_for(ev)
        if pet is None:
            return
        bench = self.overlay.workbench_for(pet)
        self.last_event_at = time.time()
        self.last_handled = ev.event_type.value
        et = ev.event_type
        now = time.time()

        if et in (EventType.AGENT_STARTED, EventType.AGENT_DISCOVERED):
            self._interrupt(pet, PetState.NOTICE_AGENT)
            pet.set_bubble("WorkBuddy online", 4.0, now)
            return
        if et in (EventType.TASK_DETECTED, EventType.TASK_STARTED):
            pet.current_agent = pet.current_agent or "workbuddy"
            self._interrupt(pet, PetState.NOTICE_TASK)
            pet.set_bubble("Task active", 5.0, now)
            self._ensure_open(pet, bench)
            return
        if et is EventType.PLANNING:
            pet.set_bubble("Planning", 4.0, now)
            self._face(pet, bench, editor=True)
            return
        if et is EventType.THINKING:
            pet.set_bubble("Working", 4.0, now)
            if bench.state == "open":
                bench.terminal.begin_stream("think")
            return
        if et in (EventType.FILE_CHANGED, EventType.WRITING_FILE,
                  EventType.FILE_CREATED):
            if now - self._last_file_at < 1.2:
                return
            self._last_file_at = now
            path = str(ev.payload.get("path", ""))
            self.overlay.editor.on_file_changed(
                path, ev.workspace_id,
                ev.payload.get("additions"), ev.payload.get("deletions"))
            self._face(pet, bench, editor=True)
            bench.grab_file(pet)
            name = path.rsplit("/", 1)[-1] if path else ""
            pet.set_bubble(f"Editing {name}" if name and not self.overlay.privacy
                           else "Editing", 4.0, now)
            return
        if et is EventType.COMMAND_STARTED:
            self._face(pet, bench, editor=False)
            bench.terminal.on_command_started(
                ev.payload.get("command") if ev.payload else None)
            pet.set_bubble("Running command", 4.0, now)
            return
        if et is EventType.COMMAND_OUTPUT:
            bench.terminal.on_output(
                ev.payload.get("text") if ev.payload else None)
            bench.grab_output(pet)          # the pet grabs the output text
            return
        if et in (EventType.COMMAND_FAILED, EventType.ERROR_DETECTED):
            self._interrupt(pet, PetState.ERROR_REACTION)
            bench.terminal.on_finished(False)
            pet.set_bubble("Something failed", 4.0, now)
            return
        if et is EventType.TEST_STARTED:
            self._face(pet, bench, editor=False)
            bench.terminal.state = "running"
            bench.terminal.begin_stream("test")
            if pet.transition(PetState.TESTING):
                pet.set_bubble("Testing", 5.0, now)
            return
        if et is EventType.TEST_FAILED:
            self._interrupt(pet, PetState.CONFUSED)
            bench.terminal.on_finished(False)
            pet.set_bubble("Tests failed", 5.0, now)
            return
        if et is EventType.TEST_PASSED:
            self._interrupt(pet, PetState.SUCCESS)
            bench.terminal.on_finished(True)
            pet.set_bubble("Tests passed", 5.0, now)
            return
        if et is EventType.GIT_COMMIT_DETECTED and self.overlay.show_git:
            self._interrupt(pet, PetState.GIT_COMMIT)
            sha = str(ev.payload.get("sha", ""))
            msg = str(ev.payload.get("message", ""))
            bench.gitfx.commit(sha, msg, pet.x - 40, pet.y - 210 * pet.scale)
            pet.set_bubble("Commit detected", 5.0, now)
            return
        if et is EventType.GIT_PUSH_DETECTED and self.overlay.show_git:
            pet.transition(PetState.GIT_PUSH)
            bench.gitfx.push(pet.x - 40, pet.y - 210 * pet.scale)
            pet.set_bubble("Push detected", 4.0, now)
            return
        if et is EventType.TASK_FAILED:
            self._interrupt(pet, PetState.ERROR_REACTION)
            bench.terminal.on_finished(False)
            pet.set_bubble("Task failed", 5.0, now)
            return
        if et is EventType.TASK_COMPLETED:
            self._interrupt(pet, PetState.CELEBRATE)
            bench.terminal.on_finished(True)
            pet.set_bubble("Done", 5.0, now)
            bench.schedule_retract(3.5)     # panels fold back after the party
            self._release(pet)
            return

    # --- station helpers -------------------------------------------------
    def _ensure_open(self, pet: PetInstance, bench) -> None:
        """Deploy the workbench where the pet stands (at most a small hop)."""
        if bench.state == "open":
            return
        if getattr(self.overlay, "mini_mode", False):
            return                      # pet only — the user asked for space
        if self.overlay.reduce_motion:
            bench.deploy(pet)
            return
        b = self.overlay.bounds_tuple()
        # keep the docked workbench fully on screen: the editor extends left of
        # the pet, the terminal right — both scale with the screen (§39)
        half = self.overlay.bench_half_width(pet)
        lo = b[0] + half
        hi = b[2] - half
        if lo > hi:
            # screen too narrow for a full bench — stay docked, react only
            # with bubbles and gestures (avoids clutter: 鼠太多会挡住电脑)
            return
        candidates = [min(max(pet.x, lo), hi)]
        # if another pet's bench is already open nearby, try to shift away;
        # if there is no room for a second station, stay docked
        for other in self.manager.pets:
            ob = self.overlay.workbench_for(other)
            if other is pet or ob.state != "open":
                continue
            base = candidates[0]
            if abs(base - other.x) < 920:
                shifted = [v for v in (other.x - 920, other.x + 920)
                           if lo <= v <= hi]
                if not shifted:
                    return          # no room → stay docked, no visual spam
                candidates[0] = shifted[0]
        tx = candidates[0]
        if abs(tx - pet.x) > 30:
            pet.move_to(tx, self.overlay.ground_y)
        bench.pending_deploy = True
        # hopping right → editor ends on the pet's left; hopping left →
        # terminal on its right: pick the arrival state that faces a panel
        to = PetState.MOVE_TO_EDITOR if tx >= pet.x else PetState.MOVE_TO_TERMINAL
        if not self._interrupt(pet, to):
            bench.pending_deploy = False
            bench.deploy(pet)

    def _face(self, pet: PetInstance, bench, editor: bool) -> None:
        """Turn toward the relevant panel and make sure it is open. The pet
        does NOT relocate for routine activity — that is the point."""
        if bench.state != "open":
            self._ensure_open(pet, bench)
            return
        pet.direction = -1 if editor else 1

    # ------------------------------------------------------------------
    def _interrupt(self, pet: PetInstance, to: PetState) -> bool:
        """§20 — allow a higher-priority event to break the current action."""
        if pet.state is to:
            return False
        if pet.can_transition(to):
            pet.transition(to)
            self.interrupts += 1
            return True
        # wake first, then retry once
        if pet.state is PetState.SLEEP and pet.transition(PetState.WAKE):
            pet.transition(PetState.IDLE)
            self.interrupts += 1
        if pet.can_transition(to):
            pet.transition(to)
            return True
        # last resort: via IDLE
        pet.transition(PetState.IDLE)
        ok = pet.transition(to)
        if ok:
            self.interrupts += 1
        return ok

    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Autonomous life when nothing is happening (§19 P3)."""
        now = time.time()
        for pet in self.manager.pets:
            bench = self.overlay.workbench_for(pet)
            # arrivals
            if pet.destination is None:
                if bench.pending_deploy:
                    bench.deploy(pet)
                    to = PetState.WATCH_TERMINAL if pet.direction >= 0 \
                        else PetState.WATCH_EDITOR
                    if not pet.transition(to):
                        pet.transition(PetState.IDLE)
                elif pet.state is PetState.MOVE_TO_TERMINAL:
                    pet.transition(PetState.WATCH_TERMINAL)
                elif pet.state is PetState.MOVE_TO_EDITOR:
                    pet.transition(PetState.WATCH_EDITOR) if \
                        random.random() < 0.6 else pet.transition(
                            PetState.TYPE_SIMULATION)

            dwell = MIN_DWELL.get(pet.state, 0.6)
            if pet.state_time < dwell:
                continue

            idle_like = pet.state in (PetState.IDLE, PetState.LOOK_AROUND,
                                      PetState.WALK, PetState.SIT, PetState.SLEEP,
                                      PetState.WATCH_TERMINAL,
                                      PetState.WATCH_EDITOR,
                                      PetState.TYPE_SIMULATION,
                                      PetState.NOTICE_AGENT, PetState.NOTICE_TASK,
                                      PetState.SPAWN, PetState.CONFUSED,
                                      PetState.FRUSTRATED, PetState.ERROR_REACTION,
                                      PetState.WAKE, PetState.RETURN_HOME)
            if not idle_like:
                continue

            quiet = now - self.last_event_at
            p = pet.personality

            if pet.state is PetState.SLEEP:
                if quiet < 12.0 or random.random() < 0.30:
                    pet.transition(PetState.WAKE)
                else:
                    pet.state_time = 0.0
                continue

            if pet.state in (PetState.CONFUSED, PetState.FRUSTRATED,
                             PetState.ERROR_REACTION):
                pet.transition(PetState.IDLE)
                continue

            if pet.state is PetState.WAKE:
                pet.transition(PetState.IDLE)
                continue

            if pet.state is PetState.RETURN_HOME:
                pet.transition(PetState.IDLE)
                continue

            if pet.state in (PetState.WATCH_TERMINAL, PetState.WATCH_EDITOR,
                             PetState.TYPE_SIMULATION):
                if quiet < 8.0:
                    # stay focused while the agent is working — but micro-shift
                    # attention between the docked panels
                    if random.random() < 0.10:
                        pet.direction *= -1
                    pet.state_time = 0.0
                    continue
                # work is over: fold the bench, resume life
                if bench.state == "open":
                    bench.schedule_retract(0.0)
                pet.transition(PetState.IDLE)
                continue

            # quiet for a while → put the tools away before idling
            if quiet > 20.0 and bench.state == "open":
                bench.schedule_retract(0.0)

            # truly autonomous choices
            weights = []
            if quiet > 25.0 and p.sleepiness > 0.25:
                weights.append((PetState.SLEEP, 0.30 * p.sleepiness))
            if quiet > 18.0:
                weights.append((PetState.RETURN_HOME, 0.25))
            weights += [
                (PetState.WALK, 0.34 * (0.5 + p.energy)),
                (PetState.SIT, 0.22),
                (PetState.LOOK_AROUND, 0.18 * (0.5 + p.curiosity)),
                (PetState.IDLE, 0.16),
            ]
            total = sum(w for _, w in weights) or 1.0
            r = random.random() * total
            chosen = PetState.IDLE
            for state, w in weights:
                if r <= w:
                    chosen = state
                    break
                r -= w

            if chosen is PetState.WALK:
                bx = self.overlay.bounds_tuple()
                tx = random.uniform(bx[0] + 80, bx[2] - 80)
                pet.move_to(tx, self.overlay.ground_y)
                if pet.transition(PetState.WALK):
                    pass
                else:
                    pet.transition(PetState.IDLE)
                    pet.move_to(tx, self.overlay.ground_y)
            elif chosen is PetState.RETURN_HOME:
                pet.move_to(pet.home_x, self.overlay.ground_y)
                if not pet.transition(PetState.RETURN_HOME):
                    pet.transition(PetState.WALK)
            else:
                if not pet.transition(chosen):
                    pet.transition(PetState.IDLE)
