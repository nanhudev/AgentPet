"""Transparent overlay world (§22, §38-§40).

Two windows cooperate:
  * ``OverlayWindow``  — full virtual-desktop, translucent, always on top,
                         transparent for mouse events (never blocks the user).
  * ``PetInputWindow`` — a small window that tracks the pet and is the ONLY
                         region that captures the mouse, so the user can drag the
                         pet and open its menu while the rest of the desktop stays
                         click-through (§40).

Panels are not free-floating: every pet owns a ``Workbench`` (its Mini Terminal
and Mini Editor docked to its body). Multiple pets therefore naturally means
multiple concurrent workbenches.
"""
from __future__ import annotations

import math
import time
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from ..behavior import avoid
from ..behavior.pet import PetInstance, PetManager, PetState
from .actors import GitFx, MiniEditor, MiniTerminal, TaskBubble, draw_pet
from .workbench import Workbench

# States in which the pet is allowed to step aside for another window; while it
# is working at its bench it stays put (moving would break the coupling) and the
# panels dim / drop behind instead.
IDLE_LIKE = frozenset({PetState.IDLE, PetState.WALK, PetState.SIT,
                       PetState.LOOK_AROUND, PetState.SLEEP,
                       PetState.RETURN_HOME})


def virtual_desktop_rect() -> QRect:
    """Available area (excludes the taskbar) across all screens — the pet must
    never end up hidden behind the taskbar or off-screen (§38)."""
    rect = QRect()
    for scr in QGuiApplication.screens():
        rect = rect.united(scr.availableGeometry())
    if rect.isEmpty():
        screen = QGuiApplication.primaryScreen()
        rect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1040)
    return rect


class OverlayWindow(QWidget):
    """Paints the world at 30 fps while animating, 10 fps when static."""

    def __init__(self, settings, manager: PetManager,
                 on_tick: Optional[Callable[[float], None]] = None) -> None:
        super().__init__()
        self.settings = settings
        self.manager = manager
        self.on_tick = on_tick
        self.benches: Dict[str, Workbench] = {}
        self.bubble = TaskBubble()
        self.privacy = bool(getattr(settings, "privacy_mode", False))
        self.reduce_motion = bool(getattr(settings, "reduce_motion", False))
        self.show_terminal = True
        self.show_editor = True
        self.show_git = True
        self._last = time.perf_counter()
        self._fps = 0.0
        self._frames = 0
        self._fps_at = time.time()
        self.demo = False
        self._last_dirty = QRectF().toRect()

        # --- staying out of the way ------------------------------------
        self.avoid_mode = str(getattr(settings, "avoid_mode", "auto") or "auto")
        self.mini_mode = bool(getattr(settings, "mini_mode", False))
        self._dim_setting = float(getattr(settings, "panel_dim", 0.35) or 0.35)
        self.panel_dim = 1.0              # animated: 1.0 = full, <1 = faded back
        self._wins: List = []
        self._fg = None
        self._dodge_cd = 0.0
        self._topmost = True
        self.behind = False               # True while the pet is under a full app
        self.panel_scale = 1.0

        self.setWindowTitle("AgentPet")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        self._win_timer = QTimer(self)
        self._win_timer.timeout.connect(self._sample_windows)
        self._win_timer.start(900)

        self.apply_geometry()
        self.layout_world()
        self._sample_windows()

    # --- workbenches ----------------------------------------------------
    def workbench_for(self, pet: PetInstance) -> Workbench:
        wb = self.benches.get(pet.pet_id)
        if wb is None:
            wb = Workbench(pet.pet_id)
            wb.apply_scale(self.panel_scale)
            self.benches[pet.pet_id] = wb
        return wb

    @property
    def primary_bench(self) -> Workbench:
        return self.workbench_for(self.manager.primary)

    # compatibility shims — the primary pet's panels (debug panel, tests)
    @property
    def terminal(self) -> MiniTerminal:
        return self.primary_bench.terminal

    @property
    def editor(self) -> MiniEditor:
        return self.primary_bench.editor

    @property
    def gitfx(self) -> GitFx:
        return self.primary_bench.gitfx

    # --- geometry ------------------------------------------------------
    def apply_geometry(self) -> None:
        r = virtual_desktop_rect()
        self.setGeometry(r)
        self.world_rect = r

    def layout_world(self) -> None:
        r = self.world_rect
        self.ground_y = r.bottom() - 36
        # panels scale down on narrow / portrait screens so the docked bench
        # always fits (§39) — a 960px bench cannot live on an 864px screen
        b = self.bounds_tuple()
        avail = (b[2] - b[0]) - 80.0
        need = (MiniTerminal.BASE_W + MiniEditor.BASE_W + 132.0)
        self.panel_scale = max(0.55, min(1.15, avail / max(1.0, need)))
        for wb in self.benches.values():
            wb.apply_scale(self.panel_scale)

        half = self.bench_half_width()
        self.home = (r.left() + min(max(half + 20.0, r.width() * 0.12),
                                    max(half + 20.0, r.width() - half - 20.0)),
                     float(self.ground_y))
        # panels are pet-docked now; these legacy anchors only serve the
        # debug panel / compatibility
        self.terminal_pos = (r.right() - 430.0, float(self.ground_y) - 250.0)
        self.editor_pos = (r.left() + max(60.0, r.width() * 0.08),
                           float(self.ground_y) - 300.0)
        self.git_pos = (r.left() + max(80.0, r.width() * 0.30),
                        float(self.ground_y) - 190.0)

    def bounds_tuple(self) -> Tuple[float, float, float, float]:
        r = self.world_rect
        return (r.left() + 20.0, r.top() + 20.0, r.right() - 20.0, self.ground_y)

    def bench_half_width(self, pet: Optional[PetInstance] = None) -> float:
        """Room a deployed workbench needs on each side of the pet."""
        pet = pet or self.manager.primary
        if pet is None:
            return MiniEditor.BASE_W * self.panel_scale + 66.0
        return max(self.workbench_for(pet).half_width(pet), 40.0)

    # --- anchors used by the behavior engine ---------------------------
    def anchor_terminal(self) -> Tuple[float, float]:
        return self.primary_bench.anchor_terminal(self.manager.primary)

    def anchor_editor(self) -> Tuple[float, float]:
        return self.primary_bench.anchor_editor(self.manager.primary)

    # --- loop ----------------------------------------------------------
    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(0.1, now - self._last)
        self._last = now
        if self.on_tick:
            try:
                self.on_tick(dt)
            except Exception:
                pass

        t = time.time()
        busy = False
        for pet in self.manager.pets:
            pet.update(dt, self.bounds_tuple())
            wb = self.workbench_for(pet)
            wb.update(dt, pet, t)
            busy = busy or (pet.destination is not None) or pet.state in (
                PetState.WALK, PetState.RUN, PetState.MOVE_TO_TERMINAL,
                PetState.MOVE_TO_EDITOR, PetState.RETURN_HOME, PetState.CELEBRATE,
                PetState.TYPE_SIMULATION, PetState.TESTING, PetState.GIT_COMMIT,
                PetState.GIT_PUSH)
            busy = busy or wb.state == "open" or bool(wb.particles)

        self._avoidance(dt)

        # dirty-rect repaint: the old code repainted the whole 1920x1032
        # translucent window every frame; Qt now repaints only the union of
        # the previous and current content boxes — the single biggest perf win
        bbox = self._content_bbox()
        dirty = bbox.toRect().adjusted(-80, -80, 80, 80)
        if self._last_dirty.isValid():
            dirty = dirty.united(self._last_dirty)
        self._last_dirty = bbox.toRect().adjusted(-80, -80, 80, 80)
        if not dirty.isEmpty():
            self.update(dirty)
        elif busy:
            self.update()

        self._timer.setInterval(33 if busy else 160)

        self._frames += 1
        if time.time() - self._fps_at >= 1.0:
            self._fps = self._frames / (time.time() - self._fps_at)
            self._frames = 0
            self._fps_at = time.time()

    @property
    def fps(self) -> float:
        return self._fps

    def _content_bbox(self) -> QRectF:
        """Bounding box of everything visible — used for dirty-rect repaints."""
        box = QRectF()
        for pet in self.manager.pets:
            x, y, w, h = pet.rect()
            box = box.united(QRectF(x - 40, y - 200, w + 80, h + 220))
            wb = self.workbench_for(pet)
            if wb.deploy_t > 0.02:
                box = box.united(wb.terminal.bounds)
                box = box.united(wb.editor.bounds)
                box = box.united(wb.gitfx.bounds)
            if wb.particles:
                box = box.united(QRectF(pet.x - 330, pet.y - 300, 660, 340))
        if self.demo:
            box = box.united(QRectF(self.world_rect.left() + 20,
                                    self.world_rect.top() + 20, 470, 50))
        return box

    # --- avoidance: never be in the user's way -------------------------
    def _sample_windows(self) -> None:
        """Read public window rectangles (read-only, no hooks — §2)."""
        if self.avoid_mode == "off":
            self._wins, self._fg = [], None
            self._apply_window_state()
            return
        try:
            from ..observation import winrect
            self._wins = winrect.visible_windows()
            self._fg = winrect.foreground_window()
        except Exception:
            self._wins, self._fg = [], None
        self._apply_window_state()

    def _apply_window_state(self) -> None:
        fg = self._fg
        covered = False
        if fg is not None:
            if fg.maximized:
                covered = True
            else:
                for scr in QGuiApplication.screens():
                    g = scr.availableGeometry()
                    from ..observation import winrect as _wr
                    r = (g.left(), g.top(), g.right(), g.bottom())
                    if _wr.screen_coverage(fg, r) >= 0.92:
                        covered = True
                        break
        self.behind = covered and self.avoid_mode in ("auto", "behind")
        want_top = bool(getattr(self.settings, "always_on_top", True)) and not self.behind
        self._set_topmost(want_top)

    def _set_topmost(self, on: bool) -> None:
        if on == self._topmost:
            return
        self._topmost = on
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()                       # setWindowFlags() hides the widget
        self.raise_()

    def _screen_windows(self) -> List[tuple]:
        """Windows on the pet's own screen, clipped to it (others can't be covered)."""
        wr = self.world_rect
        sl, st = float(wr.left()), float(wr.top())
        sr, sb = float(wr.right()), float(wr.bottom())
        out: List[tuple] = []
        for w in self._wins:
            l, t, r, b = w.rect
            if r <= sl or l >= sr or b <= st or t >= sb:
                continue
            out.append((max(l, sl), max(t, st), min(r, sr), min(b, sb)))
        return out

    def _target_dim(self) -> float:
        """Fade the docked panels back while they cover another app."""
        if self.avoid_mode == "off" or not self._wins:
            return 1.0
        wins = self._screen_windows()
        if not wins:
            return 1.0
        for pet in self.manager.pets:
            wb = self.workbench_for(pet)
            if wb.deploy_t < 0.05:
                continue
            for obj in (wb.terminal, wb.editor):
                r = obj.bounds
                rect = (r.left(), r.top(), r.right(), r.bottom())
                for wrect in wins:
                    if avoid.overlap_ratio(rect, wrect) > 0.25:
                        return self._dim_setting
        return 1.0

    def _avoidance(self, dt: float) -> None:
        if self._dodge_cd > 0:
            self._dodge_cd -= dt
        target = self._target_dim()
        self.panel_dim += (target - self.panel_dim) * min(1.0, dt * 4.0)
        if abs(self.panel_dim - target) < 0.01:
            self.panel_dim = target

        if self.avoid_mode not in ("auto", "dodge") or self._dodge_cd > 0:
            return
        band_t, band_b = avoid.band_for(self.ground_y)
        bounds = self.bounds_tuple()
        rects = self._screen_windows()
        # an open workbench is also "occupied space" for the other pets
        for other in self.manager.pets:
            ob = self.workbench_for(other)
            if ob.deploy_t > 0.3:
                for obj in (ob.terminal, ob.editor):
                    r = obj.bounds
                    rects.append((r.left(), r.top(), r.right(), r.bottom()))
        if not rects:
            return
        spans = avoid.occupied_spans(rects, band_t, band_b, bounds)
        if not spans:
            return
        now = time.time()
        for pet in self.manager.pets:
            if pet.state not in IDLE_LIKE or pet.pinned_until > now:
                continue
            if not avoid.conflicts(pet.x, spans, 60.0):
                continue
            spot = avoid.best_x(pet.x, spans, bounds, deployed=False)
            if spot is None or abs(spot - pet.x) < 40.0:
                continue
            pet.move_to(spot, self.ground_y)
            pet.home_x = spot
            self._dodge_cd = 5.0
            break                          # one pet per dodge keeps it calm

    def pin_primary(self, seconds: float = 25.0) -> None:
        """The user just placed the pet by hand — respect that for a while."""
        pet = self.manager.primary
        if pet is not None:
            pet.pinned_until = time.time() + seconds
            pet.home_x, pet.home_y = pet.x, pet.y

    def park(self, where: str) -> None:
        """Dock the pet to a screen edge — a one-click way to clear space."""
        pet = self.manager.primary
        if pet is None:
            return
        b = self.bounds_tuple()
        half = self.bench_half_width(self.manager.primary)
        margin = half + 20.0 if not self.mini_mode else 90.0
        if where == "left":
            x = b[0] + margin
        elif where == "right":
            x = b[2] - margin
        else:
            x = (b[0] + b[2]) / 2
        x = min(max(x, b[0] + 60.0), b[2] - 60.0)
        pet.move_to(x, self.ground_y)
        pet.home_x, pet.home_y = x, self.ground_y
        pet.pinned_until = time.time() + 45.0

    # --- paint ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        t = time.time()
        dim = self.panel_dim < 0.99
        for pet in self.manager.pets:
            wb = self.workbench_for(pet)
            if dim and wb.deploy_t > 0.02:
                p.setOpacity(self.panel_dim)
            wb.paint(p, self.privacy, pet, t)      # docked panels + leashes
            if dim:
                p.setOpacity(1.0)
        for pet in self.manager.pets:
            draw_pet(p, pet, t)                    # pet on top of its bench
            self.bubble.paint(p, pet)

        if self.demo:
            p.setFont(QFont("Segoe UI", 22, QFont.Bold))
            p.setPen(QColor("#FF6B6B"))
            p.drawText(QRect(self.world_rect.left() + 20, self.world_rect.top() + 20,
                             int(self.world_rect.width() - 40), 44),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "DEMO / SIMULATION — not real agent activity")
        p.end()

    # --- helpers used by the app / engine ------------------------------
    def show_terminal_at(self, seconds: float = 0.0) -> None:
        if self.show_terminal:
            self.primary_bench.deploy(self.manager.primary)

    def show_editor_at(self, seconds: float = 0.0) -> None:
        if self.show_editor:
            self.primary_bench.deploy(self.manager.primary)

    def hide_panels(self) -> None:
        self.primary_bench.retract()


class PetInputWindow(QWidget):
    """The only mouse-capturing region: follows the primary pet."""

    def __init__(self, overlay: OverlayWindow, manager: PetManager,
                 actions: Dict[str, Callable[[], None]]) -> None:
        super().__init__()
        self.overlay = overlay
        self.manager = manager
        self.actions = actions
        self._drag: Optional[QPoint] = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._follow)
        self._timer.start(50)

    def _follow(self) -> None:
        pet = self.manager.primary
        if pet is None:
            return
        x, y, w, h = pet.rect()
        self.setGeometry(int(x), int(y), int(w), int(h))
        if not self.isVisible():
            self.show()

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag is None:
            return
        pet = self.manager.primary
        if pet is None:
            return
        delta = ev.globalPosition().toPoint() - self._drag
        if delta.manhattanLength() == 0:
            return
        self._drag = ev.globalPosition().toPoint()
        pet.x += delta.x()
        pet.y += delta.y()
        pet.destination = None
        pet.home_x, pet.home_y = pet.x, pet.y

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._drag is not None:
            # the user placed the pet by hand — don't dodge away from there
            self.overlay.pin_primary()
        self._drag = None

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        self._open_menu(ev.globalPosition().toPoint())

    def contextMenuEvent(self, ev) -> None:  # noqa: N802
        try:
            self._open_menu(ev.globalPos())
        except Exception:
            self._open_menu(ev.globalPosition().toPoint())

    def _open_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        act = self.actions.get

        def add(label, key, checkable=False, checked=False):
            fn = act(key)
            if fn is None:
                return None
            a = menu.addAction(label)
            if checkable:
                a.setCheckable(True)
                a.setChecked(checked)
            a.triggered.connect(fn)
            return a

        add("Settings…", "settings")
        add("Debug panel", "debug")
        menu.addSeparator()

        move = menu.addMenu("Move to")
        for label, key in (("Left edge", "park_left"), ("Center", "park_center"),
                           ("Right edge", "park_right")):
            fn = act(key)
            if fn:
                move.addAction(label).triggered.connect(fn)

        size = menu.addMenu("Pet size")
        for label, key in (("Small (70%)", "size_small"),
                           ("Normal (100%)", "size_normal"),
                           ("Large (140%)", "size_large")):
            fn = act(key)
            if fn:
                size.addAction(label).triggered.connect(fn)

        avoid_menu = menu.addMenu("Avoid programs")
        for label, key in (("Auto (dodge + step behind)", "avoid_auto"),
                           ("Dodge windows", "avoid_dodge"),
                           ("Step behind full-screen apps", "avoid_behind"),
                           ("Off (always on top)", "avoid_off")):
            fn = act(key)
            if fn:
                a = avoid_menu.addAction(label)
                a.setCheckable(True)
                a.setChecked(self.overlay.avoid_mode == key.replace("avoid_", ""))
                a.triggered.connect(fn)

        add("Mini mode (pet only, no panels)", "mini", checkable=True,
            checked=self.overlay.mini_mode)
        menu.addSeparator()
        add("Hide pet", "hide")
        add("Simulate coding (demo)", "simulate")
        add("Exit", "exit")
        menu.exec(pos)
