"""Desktop actors drawn into the overlay world (§22-§27, §29, §67).

Everything here is *theatre* layered on top of observed facts. Two hard rules:

1. A terminal shows `Running command...` unless a real command string was observed.
   WorkBuddy's SDK log never exposes the command, so in V0.1 it never does.
2. The Mini Editor only shows a file path that came from a real change record; if a
   file cannot be safely read it shows `Updating <name>...` and nothing else.
"""
from __future__ import annotations

import math
import os
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen, QPolygonF)

from ..core import safety
from ..behavior.pet import AnimationKey, PetInstance, PetState
from .stream import OutputStreamer

INK = QColor("#2B2B3A")
PAPER = QColor("#FFFFFF")


def _rgba(hex_color: str, alpha: float) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def _round(painter: QPainter, rect: QRectF, r: float) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    painter.drawPath(path)


# --- font cache -------------------------------------------------------
# Building a QFont/QFontMetrics on every paint frame was the single biggest
# CPU cost in the render loop; fonts are immutable once built, so cache them.
_FONTS: Dict[Tuple[str, int, bool], QFont] = {}
_METRICS: Dict[Tuple[str, int, bool], QFontMetrics] = {}


def _font(name: str, size: int, bold: bool = False) -> QFont:
    key = (name, size, bold)
    f = _FONTS.get(key)
    if f is None:
        f = QFont(name, size, QFont.Bold if bold else QFont.Normal)
        _FONTS[key] = f
    return f


def _fm(name: str, size: int, bold: bool = False) -> QFontMetrics:
    key = (name, size, bold)
    m = _METRICS.get(key)
    if m is None:
        m = QFontMetrics(_font(name, size, bold))
        _METRICS[key] = m
    return m


# ----------------------------------------------------------------------
# World objects
# ----------------------------------------------------------------------
class WorldObject:
    def __init__(self, name: str) -> None:
        self.name = name
        self.bounds = QRectF(0, 0, 0, 0)
        self.visible = False
        self.opacity = 0.0
        self._target_opacity = 0.0
        self._slide_from = QPointF()
        self._slide_to = QPointF()
        self._slide_t = 1.0
        self._slide_dur = 0.25
        self._hold_until = 0.0

    # --- lifecycle -----------------------------------------------------
    def show(self, x: float, y: float, seconds: float = 0.0) -> None:
        self.bounds.moveTopLeft(QPointF(x, y))
        if not self.visible:
            self._slide_from = QPointF(x + (60 if x > 0 else -60), y)
            self._slide_t = 0.0
        else:
            self._slide_from = QPointF(x, y)
            self._slide_t = 1.0
        self._slide_to = QPointF(x, y)
        self.visible = True
        self._target_opacity = 1.0
        if seconds:
            self._hold_until = time.time() + seconds

    def hide(self) -> None:
        self._target_opacity = 0.0

    def update(self, dt: float, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        if self._slide_t < 1.0:
            self._slide_t = min(1.0, self._slide_t + dt / self._slide_dur)
            e = 1 - (1 - self._slide_t) ** 3          # ease-out cubic
            x = self._slide_from.x() + (self._slide_to.x() - self._slide_from.x()) * e
            y = self._slide_from.y() + (self._slide_to.y() - self._slide_from.y()) * e
            self.bounds.moveTopLeft(QPointF(x, y))
        self.opacity += (self._target_opacity - self.opacity) * min(1.0, dt * 8.0)
        if self._target_opacity == 0.0 and self.opacity < 0.02:
            self.visible = False
            self.opacity = 0.0
        if self._hold_until and now > self._hold_until and self._target_opacity > 0:
            self.hide()
            self._hold_until = 0.0

    # --- geometry ------------------------------------------------------
    def anchor_left(self) -> QPointF:
        return QPointF(self.bounds.left() - 58, self.bounds.bottom() - 12)

    def set_scale(self, k: float) -> None:
        """Fit the panel to a small / portrait screen (§39 display scaling)."""
        k = max(0.55, min(1.35, k))
        top_left = self.bounds.topLeft()
        self.bounds.setSize(QSizeF(self.BASE_W * k, self.BASE_H * k))
        self.bounds.moveTopLeft(top_left)

    def anchor_right(self) -> QPointF:
        return QPointF(self.bounds.right() + 58, self.bounds.bottom() - 12)


class MiniTerminal(WorldObject):
    BASE_W = 380.0
    BASE_H = 210.0

    """§23-§24 — a visual terminal. It never executes anything."""

    def __init__(self) -> None:
        super().__init__("terminal")
        self.bounds = QRectF(0, 0, 380, 210)
        self.lines: List[Tuple[str, str]] = []   # (style, text)
        self.state = "idle"                      # idle | running | success | error
        self.command: Optional[str] = None
        self._cursor_phase = 0.0
        self.streamer = OutputStreamer()
        self._last_real_output = 0.0
        self._stream_text: Optional[str] = None

    def begin_stream(self, kind: str) -> None:
        """Abstract streaming template (VISUAL_ONLY) for unobservable output."""
        self.streamer.start(kind)

    def on_command_started(self, command: Optional[str] = None) -> None:
        self.state = "running"
        self.command = command
        self.lines.append(("prompt", command or "Running command..."))
        if not command:
            self.begin_stream("command")
        self._trim()

    def on_output(self, text: Optional[str] = None) -> None:
        if text:
            self.lines.append(("out", text))
            self._last_real_output = time.time()
        else:
            self.lines.append(("out", "·"))
        self._trim()

    def on_finished(self, ok: bool) -> None:
        self.state = "success" if ok else "error"
        self.streamer.stop()
        self.lines.append(("ok" if ok else "err",
                           "done" if ok else "failed"))
        self._trim()

    def _trim(self) -> None:
        if len(self.lines) > 24:
            self.lines = self.lines[-24:]

    def update(self, dt: float, now: Optional[float] = None) -> None:
        super().update(dt, now)
        self._cursor_phase += dt
        if self.streamer.active and self.state == "running":
            self.streamer.t += dt
            # real observed output wins for 6 s after it last arrived
            if now is not None and now - self._last_real_output < 6.0:
                self._stream_text = None
            else:
                self._stream_text = self.streamer.current()
        elif not self.streamer.active:
            self._stream_text = None

    def paint(self, p: QPainter, privacy: bool = False) -> None:
        if not self.visible or self.opacity < 0.02:
            return
        p.save()
        p.setOpacity(self.opacity)
        r = self.bounds
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba("#1B1D2B", 0.93))
        _round(p, r, 12)
        p.setPen(QPen(_rgba("#8B93B8", 0.9), 1.2))
        p.setBrush(Qt.NoBrush)
        _round(p, r.adjusted(0.5, 0.5, -0.5, -0.5), 12)

        # title bar
        p.setPen(Qt.NoPen)
        for i, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(r.left() + 16 + i * 16, r.top() + 16), 5, 5)

        title = _font("Segoe UI", 9)
        p.setFont(title)
        p.setPen(QColor("#C9D1E9"))
        p.drawText(QRectF(r.left() + 66, r.top() + 7, max(60.0, r.width() - 76), 18),
                   Qt.AlignLeft | Qt.AlignVCenter, "Mini Terminal")

        body = r.adjusted(14, 34, -14, -14)
        mono = _font("Consolas", 9)
        p.setFont(mono)
        fm = _fm("Consolas", 9)
        y = body.top() + 12
        room = int(max(1.0, (body.bottom() - 26 - y) // 15))
        for style, text in self.lines[-max(2, room):]:
            if style == "prompt":
                p.setPen(QColor("#7EE787"))
                txt = "> " + (("Running command..." if privacy else text) or "")
            elif style == "out":
                p.setPen(QColor("#9AA4C7"))
                txt = ("output" if privacy else text)
            elif style == "ok":
                p.setPen(QColor("#28C840"))
                txt = text
            elif style == "err":
                p.setPen(QColor("#FF6B6B"))
                txt = text
            else:
                p.setPen(QColor("#9AA4C7"))
                txt = text
            p.drawText(QRectF(body.left(), y, body.width(), 15),
                       Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(
                           txt, Qt.ElideRight, int(body.width())))
            y += 15

        if self.state == "running":
            blink = (int(self._cursor_phase * 2) % 2) == 0
            if self._stream_text:
                p.setPen(QColor("#6FB7E8"))
                p.drawText(QRectF(body.left(), y, body.width(), 15),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(self._stream_text, Qt.ElideRight,
                                         int(body.width())))
                y += 15
            if blink:
                p.setPen(QColor("#7EE787"))
                p.drawText(QRectF(body.left(), y, 10, 15), Qt.AlignLeft, "_")

        # status strip
        strip = QRectF(r.left() + 12, r.bottom() - 20, r.width() - 24, 4)
        color = {"running": "#FEBC2E", "success": "#28C840",
                 "error": "#FF6B6B"}.get(self.state, "#3A3F5C")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        _round(p, strip, 2)
        p.restore()


class MiniEditor(WorldObject):
    BASE_W = 400.0
    BASE_H = 240.0

    """§25-§26 — shows real file names; real content only when safely readable."""

    MAX_LINES = 10

    def __init__(self) -> None:
        super().__init__("editor")
        self.bounds = QRectF(0, 0, 400, 240)
        self.file_path: Optional[str] = None
        self.rows: List[Tuple[str, str]] = []   # (marker, text)
        self.additions: Optional[int] = None
        self.deletions: Optional[int] = None
        self.readable = False

    def on_file_changed(self, path: str, workspace: Optional[str],
                        additions: Optional[int] = None,
                        deletions: Optional[int] = None) -> None:
        self.file_path = path
        self.additions = additions
        self.deletions = deletions
        self.rows = []
        self.readable = False
        full = None
        if workspace:
            cand = os.path.join(workspace, path.replace("/", os.sep))
            if os.path.isfile(cand) and not safety.is_sensitive(cand):
                full = cand
        if full:
            try:
                if os.path.getsize(full) <= 200_000:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        for i, ln in enumerate(f):
                            if i >= self.MAX_LINES:
                                break
                            self.rows.append((" ", ln.rstrip()[:110]))
                    self.readable = True
            except Exception:
                self.rows = []
        if not self.rows:
            self.rows = [(" ", "Updating {}...".format(os.path.basename(path)))]

    def paint(self, p: QPainter, privacy: bool = False) -> None:
        if not self.visible or self.opacity < 0.02:
            return
        p.save()
        p.setOpacity(self.opacity)
        r = self.bounds
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba("#FFFFFF", 0.96))
        _round(p, r, 12)
        p.setPen(QPen(_rgba("#C9CFE0", 1.0), 1.2))
        p.setBrush(Qt.NoBrush)
        _round(p, r.adjusted(0.5, 0.5, -0.5, -0.5), 12)

        head = QRectF(r.left() + 1, r.top() + 1, r.width() - 2, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba("#F1F3FA", 1.0))
        _round(p, head, 11)

        f = _font("Segoe UI", 9)
        p.setFont(f)
        p.setPen(QColor("#5A6485"))
        name = "file" if privacy else (self.file_path or "")
        p.drawText(QRectF(r.left() + 14, r.top() + 7, r.width() - 120, 18),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   _fm("Segoe UI", 9).elidedText(name, Qt.ElideLeft,
                                              int(r.width() - 130)))
        if self.additions is not None or self.deletions is not None:
            p.setPen(QColor("#2FA84F"))
            p.drawText(QRectF(r.right() - 110, r.top() + 7, 96, 18),
                       Qt.AlignRight | Qt.AlignVCenter,
                       f"+{self.additions or 0} -{self.deletions or 0}")

        mono = _font("Consolas", 9)
        p.setFont(mono)
        fm = _fm("Consolas", 9)
        y = r.top() + 42
        for i, (marker, text) in enumerate(self.rows):
            p.setPen(QColor("#C2C8DC"))
            p.drawText(QRectF(r.left() + 10, y, 22, 15), Qt.AlignRight, str(i + 1))
            if privacy:
                p.setPen(QColor("#8A93B0"))
                p.drawText(QRectF(r.left() + 38, y, r.width() - 60, 15),
                           Qt.AlignLeft | Qt.AlignVCenter, "· · ·")
            else:
                p.setPen(QColor("#3A4160"))
                p.drawText(QRectF(r.left() + 38, y, r.width() - 60, 15),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(text, Qt.ElideRight, int(r.width() - 70)))
            y += 16
        p.setFont(_font("Segoe UI", 8))
        p.setPen(QColor("#A6ADC4"))
        p.drawText(QRectF(r.left() + 12, r.bottom() - 18, r.width() - 24, 14),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "Mini Editor · visualization · read-only")
        p.restore()


class GitFx(WorldObject):
    BASE_W = 190.0
    BASE_H = 66.0

    """§27 — commit = carry a box, push = the box flies away. Dramatic, but only
    when a real commit was observed."""

    def __init__(self) -> None:
        super().__init__("gitfx")
        self.bounds = QRectF(0, 0, 190, 66)
        self.kind = "commit"
        self.sha = ""
        self.message = ""
        self._t = 0.0
        self._flying = False
        self._fly_dx = 0.0

    def commit(self, sha: str, message: str, x: float, y: float) -> None:
        self.kind = "commit"
        self.sha = sha
        self.message = message
        self._flying = False
        self.show(x, y, seconds=5.0)

    def push(self, x: float, y: float) -> None:
        self.kind = "push"
        self._flying = True
        self._fly_dx = 0.0
        self.show(x, y, seconds=3.0)

    def update(self, dt: float, now: Optional[float] = None) -> None:
        super().update(dt, now)
        if self._flying:
            self._fly_dx += dt * 260.0
            self.opacity = max(0.0, self.opacity - dt * 0.5)

    def paint(self, p: QPainter, privacy: bool = False) -> None:
        if not self.visible or self.opacity < 0.02:
            return
        p.save()
        p.setOpacity(max(0.0, self.opacity))
        x = self.bounds.left() + self._fly_dx
        y = self.bounds.top()
        # box
        p.setPen(QPen(QColor("#8A6A3B"), 2))
        p.setBrush(QColor("#D9A566"))
        p.drawRoundedRect(QRectF(x, y + 18, 46, 34), 4, 4)
        p.setPen(QPen(QColor("#8A6A3B"), 1.5))
        p.drawLine(QPointF(x, y + 30), QPointF(x + 46, y + 30))
        # label
        f = _font("Segoe UI", 9, True)
        p.setFont(f)
        p.setPen(QColor("#6B5228"))
        label = "Commit detected" if self.kind == "commit" else "Push detected"
        p.drawText(QRectF(x + 56, y + 6, 220, 18), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setFont(_font("Consolas", 9))
        p.setPen(QColor("#8A7448"))
        sub = self.sha if not privacy else "***"
        if self.message and not privacy:
            sub += "  " + self.message[:28]
        p.drawText(QRectF(x + 56, y + 26, 260, 18), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.restore()


class TaskBubble:
    """§28 — short by default; privacy mode shows only the abstract state."""

    def __init__(self) -> None:
        self.text = ""
        self.until = 0.0

    def set(self, text: str, seconds: float = 4.0) -> None:
        self.text = text
        self.until = time.time() + seconds

    def paint(self, p: QPainter, pet: PetInstance) -> None:
        if not self.text or time.time() > self.until:
            return
        f = _font("Segoe UI", 9)
        p.setFont(f)
        fm = _fm("Segoe UI", 9)
        w = min(240.0, fm.horizontalAdvance(self.text) + 24)
        x = pet.x - w / 2
        y = pet.y - 118 * pet.scale
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba("#FFFFFF", 0.95))
        _round(p, QRectF(x, y, w, 26), 10)
        p.setPen(QPen(_rgba("#C9CFE0", 1.0), 1))
        p.setBrush(Qt.NoBrush)
        _round(p, QRectF(x, y, w, 26), 10)
        p.setPen(QColor("#3A4160"))
        p.drawText(QRectF(x, y, w, 26), Qt.AlignCenter, self.text)


# ----------------------------------------------------------------------
# The pet itself — procedurally drawn, asset-independent
# ----------------------------------------------------------------------
def draw_pet(p: QPainter, pet: PetInstance, t: float) -> None:
    """Draws the mascot. Swap this function (or dispatch on a sprite sheet) and
    nothing else in the codebase changes (§30)."""
    s = pet.scale
    anim = pet.animation
    x, y = pet.x, pet.y
    bob = math.sin(t * (9.0 if anim in (AnimationKey.WALK, AnimationKey.RUN) else 2.2))
    if anim is AnimationKey.SLEEP:
        bob = math.sin(t * 1.1) * 0.4
    lift = bob * (3.2 if anim is AnimationKey.RUN else 1.8)
    if anim is AnimationKey.SLEEP:
        lift = 0.0

    body_w, body_h = 62 * s, 50 * s
    cx = x
    cy = y - body_h / 2 - 22 * s + lift
    if anim is AnimationKey.SIT:
        cy = y - body_h / 2 - 14 * s
    if anim is AnimationKey.SLEEP:
        cy = y - body_h / 2 - 10 * s

    p.save()
    # shadow
    p.setPen(Qt.NoPen)
    p.setBrush(_rgba("#000000", 0.12))
    p.drawEllipse(QPointF(x, y - 2 * s), 30 * s, 7 * s)

    body = QRectF(cx - body_w / 2, cy - body_h / 2, body_w, body_h)

    # tail
    tail_swing = math.sin(t * (10 if anim in (AnimationKey.WALK, AnimationKey.RUN)
                               else 2.0)) * (14 if anim is AnimationKey.RUN else 7)
    p.setPen(QPen(QColor("#5C7AE8"), 6 * s, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx - body_w / 2 * 0.9 * pet.direction, cy + 4 * s),
               QPointF(cx - body_w / 2 * 0.9 * pet.direction - 16 * s,
                       cy - 6 * s + tail_swing * 0.4))

    # legs
    leg_phase = math.sin(t * (16 if anim is AnimationKey.RUN else 9))
    if anim in (AnimationKey.WALK, AnimationKey.RUN) or pet.destination is not None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4C68D8"))
        for i, off in enumerate((-12 * s, 12 * s)):
            swing = leg_phase * (10 if anim is AnimationKey.RUN else 6) * (1 if i else -1)
            p.drawRoundedRect(QRectF(cx + off - 6 * s + swing,
                                     cy + body_h / 2 - 4 * s, 12 * s, 16 * s), 5, 5)
    elif anim is AnimationKey.SIT:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4C68D8"))
        p.drawRoundedRect(QRectF(cx - 6 * s, cy + body_h / 2 - 6 * s, 26 * s, 12 * s), 6, 6)

    # body
    p.setPen(QPen(QColor("#2E3A66"), 2.0 * s))
    p.setBrush(QColor("#7C9CF5"))
    p.drawRoundedRect(body, 22 * s, 22 * s)

    # belly
    p.setPen(Qt.NoPen)
    p.setBrush(_rgba("#FFFFFF", 0.55))
    p.drawRoundedRect(QRectF(cx - 16 * s, cy - 2 * s, 32 * s, 26 * s), 12 * s, 12 * s)

    # ears
    p.setPen(QPen(QColor("#2E3A66"), 2.0 * s))
    p.setBrush(QColor("#6C8BF0"))
    for off in (-18 * s, 18 * s):
        ear = QRectF(cx + off - 9 * s, cy - body_h / 2 - 16 * s, 18 * s, 24 * s)
        p.drawRoundedRect(ear, 8 * s, 8 * s)
    p.setBrush(QColor("#FFC2D6"))
    p.setPen(Qt.NoPen)
    for off in (-18 * s, 18 * s):
        p.drawRoundedRect(QRectF(cx + off - 4 * s, cy - body_h / 2 - 11 * s,
                                 8 * s, 14 * s), 4 * s, 4 * s)

    # eyes
    eye_y = cy - 6 * s
    p.setPen(Qt.NoPen)
    if anim is AnimationKey.SLEEP:
        p.setPen(QPen(QColor("#2B2B3A"), 2.4 * s))
        for off in (-11 * s, 11 * s):
            p.drawLine(QPointF(cx + off - 5 * s, eye_y), QPointF(cx + off + 5 * s, eye_y))
    elif anim is AnimationKey.CONFUSED:
        p.setFont(_font("Segoe UI", max(6, int(15 * s)), True))
        p.setPen(QColor("#E8604C"))
        p.drawText(QRectF(cx + 14 * s, eye_y - 26 * s, 40 * s, 26 * s),
                   Qt.AlignLeft | Qt.AlignVCenter, "?")
        p.setPen(QColor("#2B2B3A"))
        for off in (-11 * s, 11 * s):
            p.drawEllipse(QPointF(cx + off, eye_y), 4.2 * s, 4.2 * s)
    elif anim is AnimationKey.CELEBRATE:
        p.setPen(QPen(QColor("#2B2B3A"), 2.4 * s))
        for off in (-11 * s, 11 * s):
            p.drawArc(QRectF(cx + off - 6 * s, eye_y - 6 * s, 12 * s, 12 * s),
                      0, 180 * 16)
    else:
        look = 1.2 * s * pet.direction if anim is AnimationKey.WATCH else 0.0
        p.setBrush(QColor("#2B2B3A"))
        for off in (-11 * s, 11 * s):
            p.drawEllipse(QPointF(cx + off + look, eye_y), 4.6 * s, 5.4 * s)
        p.setBrush(QColor("#FFFFFF"))
        for off in (-11 * s, 11 * s):
            p.drawEllipse(QPointF(cx + off + look + 1.4 * s, eye_y - 1.6 * s),
                          1.7 * s, 1.7 * s)

    # cheeks
    if pet.personality.expressiveness > 0.4:
        p.setBrush(_rgba("#FF9AB5", 0.75))
        p.setPen(Qt.NoPen)
        for off in (-22 * s, 22 * s):
            p.drawEllipse(QPointF(cx + off, eye_y + 10 * s), 6 * s, 4 * s)

    # mouth
    p.setPen(QPen(QColor("#2B2B3A"), 1.8 * s))
    if anim is AnimationKey.FRUSTRATED:
        p.drawArc(QRectF(cx - 7 * s, eye_y + 8 * s, 14 * s, 10 * s), 180 * 16, 180 * 16)
    elif anim in (AnimationKey.CELEBRATE, AnimationKey.NOTICE):
        p.drawArc(QRectF(cx - 7 * s, eye_y + 4 * s, 14 * s, 12 * s), 0, -180 * 16)
    elif anim is AnimationKey.SLEEP:
        pass
    else:
        p.drawLine(QPointF(cx - 4 * s, eye_y + 10 * s),
                   QPointF(cx + 4 * s, eye_y + 10 * s))

    # typing paws
    if anim is AnimationKey.TYPING:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#6C8BF0"))
        for i, off in enumerate((-16 * s, 16 * s)):
            tap = abs(math.sin(t * 12 + i)) * 5 * s
            p.drawEllipse(QPointF(cx + off, cy + body_h / 2 + 2 * s + tap), 7 * s, 6 * s)

    # carried git box
    if anim is AnimationKey.CARRY:
        p.setPen(QPen(QColor("#8A6A3B"), 2))
        p.setBrush(QColor("#D9A566"))
        p.drawRoundedRect(QRectF(cx - 15 * s, cy - body_h / 2 - 4 * s, 30 * s, 24 * s),
                          3, 3)

    # sleep zzz
    if anim is AnimationKey.SLEEP:
        p.setFont(_font("Segoe UI", max(6, int(11 * s))))
        p.setPen(QColor("#5A6485"))
        for i in range(3):
            phase = (t * 0.7 + i * 0.33) % 1.0
            p.setOpacity(1.0 - phase)
            p.drawText(QPointF(cx + 20 * s + phase * 14 * s,
                               cy - body_h / 2 - 14 * s - phase * 22 * s), "z")
        p.setOpacity(1.0)

    # celebrate sparks
    if anim is AnimationKey.CELEBRATE:
        p.setPen(Qt.NoPen)
        for i in range(6):
            a = t * 4 + i * (math.pi / 3)
            rr = 34 * s + math.sin(t * 6 + i) * 6 * s
            p.setBrush(QColor(["#FFD166", "#06D6A0", "#EF476F"][i % 3]))
            p.drawEllipse(QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.6),
                          4 * s, 4 * s)
    p.restore()
