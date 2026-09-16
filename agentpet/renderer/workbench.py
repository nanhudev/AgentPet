"""Pet-tethered workbench — the pet physically carries its Mini Terminal and
Mini Editor.

Design answers three product rules:

1. Physical coupling: panels are DOCKED to the pet (drawn relative to the pet's
   position every frame, with a dotted "leash" from paw to panel). They are
   never free-floating rectangles on the other side of the screen.
2. Entrance ritual: deploy = particle burst from the pet + panels pop open
   (scale + fade, 350 ms). Retract folds them back into the pet.
3. The pet grabs output: every COMMAND_OUTPUT spawns small text chips that fly
   from the terminal into the pet's paws — reading, theatrically.

All positions derive from the pet each frame, so the panels travel with the
pet and multiple pets naturally means multiple workbenches.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPainter

from .actors import GitFx, MiniEditor, MiniTerminal, _rgba

GRAB_COLORS = ("#7EE787", "#9AA4C7", "#FEBC2E", "#8B93B8")


class Workbench:
    """Terminal + editor + git fx, docked to one pet."""

    def __init__(self, pet_id: str) -> None:
        self.pet_id = pet_id
        self.terminal = MiniTerminal()
        self.editor = MiniEditor()
        self.gitfx = GitFx()
        self.state = "docked"          # docked | open
        self.deploy_t = 0.0            # 0 = folded into pet, 1 = fully open
        self.pending_deploy = False
        self.retract_at = 0.0
        self.particles: List[dict] = []
        self.panel_scale = 1.0

    def apply_scale(self, k: float) -> None:
        """Shrink/grow the docked panels so the bench fits the screen (§39)."""
        k = max(0.55, min(1.35, k))
        if abs(k - self.panel_scale) < 0.01:
            return
        self.panel_scale = k
        self.terminal.set_scale(k)
        self.editor.set_scale(k)
        self.gitfx.set_scale(k)

    def half_width(self, pet) -> float:
        """Horizontal room the deployed bench needs on each side of the pet."""
        gap = 66.0 * pet.scale
        return max(self.editor.bounds.width() + gap,
                   self.terminal.bounds.width() + gap)

    # --- geometry (pet-relative) ---------------------------------------
    def _dock_positions(self, pet) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        ground = pet.y
        t = self.terminal.bounds
        e = self.editor.bounds
        tx = pet.x + 66 * pet.scale
        ty = ground - 10 - t.height()
        ex = pet.x - 66 * pet.scale - e.width()
        ey = ground - 10 - e.height()
        return (tx, ty), (ex, ey)

    def anchor_terminal(self, pet) -> Tuple[float, float]:
        (tx, ty), _ = self._dock_positions(pet)
        return (tx + 12, ty + self.terminal.bounds.height() - 30)

    def anchor_editor(self, pet) -> Tuple[float, float]:
        _, (ex, ey) = self._dock_positions(pet)
        return (ex + self.editor.bounds.width() - 12,
                ey + self.editor.bounds.height() - 30)

    # --- lifecycle ------------------------------------------------------
    def deploy(self, pet) -> None:
        if self.state == "open":
            return
        self.state = "open"
        self.pending_deploy = False
        self.retract_at = 0.0
        for obj in (self.terminal, self.editor):
            obj.visible = True
            obj._target_opacity = 1.0
            obj.opacity = 0.15
            obj._hold_until = 0.0
        self._burst(pet)

    def retract(self) -> None:
        self.state = "docked"
        self.pending_deploy = False
        self.retract_at = 0.0
        for obj in (self.terminal, self.editor, self.gitfx):
            obj._target_opacity = 0.0

    def schedule_retract(self, delay: float = 3.5) -> None:
        self.retract_at = time.time() + delay

    # --- particles ------------------------------------------------------
    def _burst(self, pet) -> None:
        cx, cy = pet.x, pet.y - 46 * pet.scale
        for i in range(16):
            a = (i / 16.0) * math.tau + 0.2
            speed = 120.0 + (i % 4) * 46.0
            self.particles.append({
                "kind": "burst", "x": cx, "y": cy,
                "vx": math.cos(a) * speed, "vy": math.sin(a) * speed - 60,
                "life": 0.0, "max": 0.55 + (i % 3) * 0.12,
                "color": ("#7C9CF5", "#FFD166", "#06D6A0", "#FF9AB5")[i % 4],
                "r": 3.2,
            })

    def grab_output(self, pet) -> None:
        """Text chips fly from the terminal into the pet's paws."""
        if self.state != "open":
            return
        (tx, ty), _ = self._dock_positions(pet)
        for i in range(3):
            fx = tx + 30 + i * 46
            fy = ty + 46 + (i % 2) * 22
            self.particles.append({
                "kind": "grab",
                "x0": fx, "y0": fy,
                "x1": pet.x + 8 * pet.scale, "y1": pet.y - 40 * pet.scale,
                "life": 0.0, "max": 0.5 + i * 0.08,
                "color": GRAB_COLORS[i % len(GRAB_COLORS)],
            })
        pet.direction = 1

    def grab_file(self, pet) -> None:
        """The pet pulls a 'page' out of the editor (file-change theatre)."""
        if self.state != "open":
            return
        _, (ex, ey) = self._dock_positions(pet)
        self.particles.append({
            "kind": "grab",
            "x0": ex + self.editor.bounds.width() * 0.5,
            "y0": ey + 60,
            "x1": pet.x - 8 * pet.scale, "y1": pet.y - 40 * pet.scale,
            "life": 0.0, "max": 0.55,
            "color": "#C9CFE0",
        })
        pet.direction = -1

    def _update_particles(self, dt: float) -> None:
        alive: List[dict] = []
        for pt in self.particles:
            pt["life"] += dt
            if pt["life"] < pt["max"]:
                if pt["kind"] == "burst":
                    pt["vy"] += 380.0 * dt          # gravity
                    pt["x"] += pt["vx"] * dt
                    pt["y"] += pt["vy"] * dt
                alive.append(pt)
        # hard cap: particles must never become a perf hazard
        self.particles = alive[-48:]

    def _paint_particles(self, p: QPainter) -> None:
        for pt in self.particles:
            k = 1.0 - pt["life"] / pt["max"]
            p.setOpacity(max(0.0, k))
            if pt["kind"] == "burst":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pt["color"]))
                p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["r"] * (0.5 + k),
                              pt["r"] * (0.5 + k))
            else:  # grab — bezier from source to paws
                t = pt["life"] / pt["max"]
                e = 1 - (1 - t) ** 2
                x0, y0 = pt["x0"], pt["y0"]
                x1, y1 = pt["x1"], pt["y1"]
                mx, my = (x0 + x1) / 2, min(y0, y1) - 60   # arc control point
                x = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * mx + e ** 2 * x1
                y = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * my + e ** 2 * y1
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pt["color"]))
                p.drawRoundedRect(QRectF(x - 9, y - 3.5, 18, 7), 3, 3)
        p.setOpacity(1.0)

    # --- per-frame ------------------------------------------------------
    def update(self, dt: float, pet, now: float) -> None:
        target = 1.0 if self.state == "open" else 0.0
        speed = 3.2 if self.state == "open" else 4.5
        self.deploy_t += (target - self.deploy_t) * min(1.0, dt * speed)
        if abs(self.deploy_t - target) < 0.01:
            self.deploy_t = target

        # docked-follow: pin panels to the pet every frame
        (tx, ty), (ex, ey) = self._dock_positions(pet)
        self.terminal.bounds.moveTopLeft(QPointF(tx, ty))
        self.editor.bounds.moveTopLeft(QPointF(ex, ey))

        self.terminal.update(dt, now)
        self.editor.update(dt, now)
        self.gitfx.update(dt, now)
        self._update_particles(dt)

        if self.retract_at and now >= self.retract_at:
            self.retract()

    # --- paint ----------------------------------------------------------
    def paint(self, p: QPainter, privacy: bool, pet, t: float) -> None:
        k = max(0.0, min(1.0, self.deploy_t))
        if k > 0.02:
            e = 1 - (1 - k) ** 3                      # ease-out cubic
            ax, ay = pet.x, pet.y - 50 * pet.scale    # fold-out anchor: the pet
            p.save()
            p.translate(ax, ay)
            p.scale(0.25 + 0.75 * e, 0.25 + 0.75 * e)
            p.translate(-ax, -ay)
            self.editor.paint(p, privacy)
            self.terminal.paint(p, privacy)
            self.gitfx.paint(p, privacy)
            self._paint_leashes(p, pet)
            p.restore()
        self._paint_particles(p)

    def _paint_leashes(self, p: QPainter, pet) -> None:
        """Dotted connection lines paw→panel: the physical coupling cue."""
        (tx, ty), (ex, ey) = self._dock_positions(pet)
        p.setPen(QPen(_rgba("#7C9CF5", 0.45), 1.4, Qt.DotLine))
        paw_y = pet.y - 30 * pet.scale
        p.drawLine(QPointF(pet.x + 20 * pet.scale, paw_y),
                   QPointF(tx + 8, ty + self.terminal.bounds.height() - 24))
        p.drawLine(QPointF(pet.x - 20 * pet.scale, paw_y),
                   QPointF(ex + self.editor.bounds.width() - 8, ey + 24))
