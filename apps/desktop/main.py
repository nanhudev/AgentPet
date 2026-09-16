"""AgentPet desktop entry point.

Wires: adapters -> event bus -> world -> behavior -> renderer.

Nothing here can execute a command on the user's behalf; the only subprocess
path in the entire app is agentpet.core.proc, allow-listed to read-only git.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# allow running from source without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from agentpet.adapters.presence import all_p1_adapters
from agentpet.adapters.registry import AdapterRegistry
from agentpet.adapters.workbuddy import WorkBuddyAdapter
from agentpet.behavior.engine import BehaviorEngine
from agentpet.behavior.pet import Personality, PetManager
from agentpet.core.config import Settings
from agentpet.core.hotkey import HotkeyManager
from agentpet.events.bus import EventBus
from agentpet.events.schema import EventType, NormalizedEvent, make
from agentpet.observation.filesystem import FileObserver
from agentpet.observation.git import GitObserver
from agentpet.observation.testartifacts import TestArtifactObserver
from agentpet.persistence.store import Store
from agentpet.renderer.overlay import OverlayWindow, PetInputWindow
from agentpet.sim.simulator import build as build_simulation
from agentpet.sim.replay import ReplayPlayer
from agentpet.ui.panels import DebugPanel, SettingsDialog, WelcomeDialog
from agentpet.world.state import FusionEngine, WorldState


class AgentPetApp:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.settings = Settings.load()
        self.bus = EventBus()
        self.world = WorldState()
        self.fusion = FusionEngine()
        self.store = Store()
        self.store.prune(self.settings.timeline_retention_days)

        self.registry = AdapterRegistry()
        self.workbuddy = WorkBuddyAdapter()
        self.registry.register(self.workbuddy)
        for a in all_p1_adapters():
            self.registry.register(a)
        self.adapters = self.registry.all()

        self.manager = PetManager()
        self.overlay = OverlayWindow(self.settings, self.manager, on_tick=self._tick)
        self.engine = BehaviorEngine(self.manager, self.overlay, self.settings)
        personality = Personality(**self.settings.personality)
        self.manager.spawn(self.settings.pet_count, self.overlay.home, personality)
        for pet in self.manager.pets:
            pet.scale = self.settings.pet_scale

        self.input_window = PetInputWindow(self.overlay, self.manager, {
            "settings": self.open_settings,
            "debug": self.open_debug,
            "simulate": self.run_simulation,
            "hide": self.toggle_hide,
            "exit": self.quit,
            "park_left": lambda: self.overlay.park("left"),
            "park_center": lambda: self.overlay.park("center"),
            "park_right": lambda: self.overlay.park("right"),
            "size_small": lambda: self.set_scale(0.7),
            "size_normal": lambda: self.set_scale(1.0),
            "size_large": lambda: self.set_scale(1.4),
            "avoid_auto": lambda: self.set_avoid("auto"),
            "avoid_dodge": lambda: self.set_avoid("dodge"),
            "avoid_behind": lambda: self.set_avoid("behind"),
            "avoid_off": lambda: self.set_avoid("off"),
            "mini": self.toggle_mini,
        })

        self.file_observer = FileObserver()
        self.git_observer = GitObserver()
        self.test_observer = TestArtifactObserver()
        self._extra_git: Dict[str, GitObserver] = {}
        self._extra_tests: Dict[str, TestArtifactObserver] = {}
        self._workspace: Optional[str] = None
        self.replay: Optional[ReplayPlayer] = None
        self.debug_panel: Optional[DebugPanel] = None

        self._apply_settings()

        # observer timers (throttled inside the adapter too)
        self._adapter_timer = QTimer()
        self._adapter_timer.timeout.connect(self._poll_adapters)
        self._adapter_timer.start(250)
        self._git_timer = QTimer()
        self._git_timer.timeout.connect(self._poll_git)
        self._git_timer.start(4000)
        self._test_timer = QTimer()
        self._test_timer.timeout.connect(self._poll_tests)
        self._test_timer.start(3000)
        self._store_timer = QTimer()
        self._store_timer.timeout.connect(self.store.commit)
        self._store_timer.start(5000)

        self._build_tray()
        self.overlay.show()
        self.input_window.show()
        self._poll_adapters()

        self._capture_path = os.environ.get("AGENTPET_CAPTURE")
        self._capture_after = float(os.environ.get("AGENTPET_CAPTURE_AFTER", "3"))
        self._quit_after = float(os.environ.get("AGENTPET_QUIT_AFTER", "0"))
        self._captured = False
        if self._capture_path:
            QTimer.singleShot(int(self._capture_after * 1000), self._capture)
        # multi-frame capture: AGENTPET_CAPTURE_AT="6,12,20"
        at = os.environ.get("AGENTPET_CAPTURE_AT", "")
        for token in [t for t in at.split(",") if t.strip()]:
            QTimer.singleShot(int(float(token) * 1000),
                              lambda t=token.strip(): self._capture(suffix="_t" + t))
        if self._quit_after:
            QTimer.singleShot(int(self._quit_after * 1000), self.quit)
        if os.environ.get("AGENTPET_SIMULATE"):
            QTimer.singleShot(500, self.run_simulation)

        if not self.settings.first_run_done:
            self.settings.first_run_done = True
            self.settings.save()
            dlg = WelcomeDialog(bool(self.workbuddy._processes))
            dlg.exec()
        if self.settings.debug_mode:
            self.open_debug()

    # --- settings ------------------------------------------------------
    def _apply_settings(self) -> None:
        s = self.settings
        self.overlay.privacy = s.privacy_mode
        self.overlay.reduce_motion = s.reduce_motion
        self.overlay.avoid_mode = s.avoid_mode
        self.overlay.mini_mode = s.mini_mode
        self.overlay._dim_setting = s.panel_dim
        self.overlay.show_terminal = s.show_mini_terminal
        self.overlay.show_editor = s.show_mini_editor
        self.overlay.show_git = s.show_git_animations
        self.overlay.setWindowOpacity(max(0.3, min(1.0, s.opacity)))
        if s.mini_mode:
            for wb in self.overlay.benches.values():
                wb.retract()
        for pet in self.manager.pets:
            pet.scale = s.pet_scale
            pet.speed = 95.0 * s.animation_speed
        # always_on_top is applied by the avoidance controller (it may drop the
        # hint while a full-screen app has the foreground)
        self.overlay._apply_window_state()

    # --- quick controls (menu / hotkeys) -------------------------------
    def set_scale(self, scale: float) -> None:
        self.settings.pet_scale = scale
        self.settings.save()
        self._apply_settings()

    def set_avoid(self, mode: str) -> None:
        self.settings.avoid_mode = mode
        self.settings.save()
        self._apply_settings()
        self.overlay._sample_windows()

    def toggle_mini(self) -> None:
        self.settings.mini_mode = not self.settings.mini_mode
        self.settings.save()
        self._apply_settings()

    # --- polling -------------------------------------------------------
    def _poll_adapters(self) -> None:
        for ev in self.registry.observe_all():
            self.bus.publish(ev)
        # follow the active workspace
        wb = self.world.agents.get("workbuddy")
        ws = None
        if wb and wb.workspace and os.path.isdir(wb.workspace):
            ws = wb.workspace
        if ws != self._workspace:
            self._workspace = ws
            if ws:
                self.git_observer.attach(ws)
                self.test_observer.attach(ws)
                if self.settings.workspace_observation:
                    self.file_observer.watch(ws)
            else:
                self.file_observer.stop()

    def _poll_git(self) -> None:
        for obs in self.git_observer.poll():
            self._git_event(obs)
        for obs in list(self._extra_git.values()):
            for o in obs.poll():
                self._git_event(o)

    def _git_event(self, obs: Dict[str, object]) -> None:
        kind = obs.get("kind")
        if kind == "commit":
            self.bus.publish(make(
                EventType.GIT_COMMIT_DETECTED,
                "workbuddy:git:rev-parse+log",
                agent_id="workbuddy",
                workspace_id=str(obs.get("repo", "")),
                confidence=0.85,
                payload={"sha": obs.get("sha"), "message": obs.get("message")},
            ))
        elif kind == "status":
            self.bus.publish(make(
                EventType.GIT_STATUS_CHANGED,
                "workbuddy:git:status",
                agent_id="workbuddy",
                workspace_id=str(obs.get("repo", "")),
                confidence=0.85,
                payload={"changed_files": obs.get("changed_files")},
            ))

    def _poll_tests(self) -> None:
        observers: List[TestArtifactObserver] = [self.test_observer]
        observers.extend(self._extra_tests.values())
        for tobs in observers:
            self._poll_one_test_observer(tobs)

    def _poll_one_test_observer(self, tobs: TestArtifactObserver) -> None:
        ws = str(getattr(tobs, "workspace", "") or self._workspace or "")
        for obs in tobs.poll():
            kind = obs.get("kind")
            if kind == "test_run":
                continue
            if kind == "test_failed":
                self.bus.publish(make(
                    EventType.TEST_FAILED,
                    f"workbuddy:test-artifacts:{obs.get('source')}",
                    agent_id="workbuddy",
                    workspace_id=ws,
                    payload={"failed": obs.get("failed"),
                             "runner": obs.get("runner")},
                ))
            elif kind == "test_passed":
                self.bus.publish(make(
                    EventType.TEST_PASSED,
                    f"workbuddy:test-artifacts:{obs.get('source')}",
                    agent_id="workbuddy",
                    workspace_id=ws,
                    payload={"total": obs.get("total"),
                             "runner": obs.get("runner")},
                ))

    # --- main tick -----------------------------------------------------
    def _tick(self, dt: float) -> None:
        # 1. filesystem (debounced) — only attributed to an agent that is online
        if self._workspace and self.settings.workspace_observation:
            for path in self.file_observer.flush():
                st = self.world.agents.get("workbuddy")
                if not (st and st.online):
                    continue
                rel = os.path.relpath(path, self._workspace).replace("\\", "/")
                self._ensure_repo_observers(path)
                self.bus.publish(make(
                    EventType.FILE_CHANGED,
                    "workbuddy:fileobserver:watchdog",
                    agent_id="workbuddy",
                    workspace_id=self._workspace,
                    session_id=st.session_id,
                    payload={"path": rel},
                ))

        # 2. replay (developer tool)
        if self.replay is not None:
            for ev in self.replay.pending():
                self.bus.publish(ev)
            if self.replay.done:
                self.replay = None
                self.overlay.demo = False

        # 3. drain normalized events
        for ev in self.bus.drain():
            self.world.apply(ev)
            self.store.append(ev)
            self.engine.handle(ev)
            # follow repos that the agent actually touches (even outside the
            # session workspace) — read-only git/test observation only
            if ev.event_type is EventType.FILE_CHANGED:
                p = str(ev.payload.get("path") or "")
                if os.path.isabs(p):
                    self._ensure_repo_observers(p)
            for fused in self.fusion.observe(ev):
                self.bus.publish(fused)

    def _ensure_repo_observers(self, path: str) -> None:
        """Attach read-only git/test observers to any repo the agent touches."""
        d = os.path.dirname(path)
        root = ""
        while d and len(d) > 3:
            if os.path.isdir(os.path.join(d, ".git")):
                root = d
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        if not root or root in self._extra_git:
            return
        if len(self._extra_git) >= 4:
            return  # safety cap
        g = GitObserver()
        t = TestArtifactObserver()
        if g.attach(root):
            self._extra_git[root] = g
            t.attach(root)
            self._extra_tests[root] = t

        # 4. autonomous behaviour
        self.engine.update(dt)

    # --- ui ------------------------------------------------------------
    # --- screenshot helper used for visible QA (§79, §80) ----------------
    def _capture(self, suffix: str = "") -> None:
        try:
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QImage, QPainter as _QP
            screen = QGuiApplication.primaryScreen()
            bg = screen.grabWindow(0)
            canvas = QImage(bg.size(), QImage.Format_ARGB32)
            canvas.fill(Qt.transparent)
            p = _QP(canvas)
            p.drawPixmap(0, 0, bg)
            off = self.overlay.geometry().topLeft() - screen.geometry().topLeft()
            p.drawPixmap(off, self.overlay.grab())
            p.end()
            out = Path(self._capture_path)
            if suffix:
                out = out.parent / (out.stem + suffix + out.suffix)
            out.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(str(out), "PNG")
            print(f"[capture] wrote {out}", flush=True)
            raw = self.overlay.grab()
            raw.save(str(out.parent / (out.stem + "_overlay_raw.png")), "PNG")
            print(f"[capture] overlay raw size={raw.width()}x{raw.height()} "
                  f"pet_at=({self.manager.primary.x:.0f},{self.manager.primary.y:.0f})"
                  f" state={self.manager.primary.state.name}",
                  flush=True)
        except Exception as exc:
            print(f"[capture] failed: {exc}", flush=True)
        self._captured = True

    def _build_tray(self) -> None:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        from PySide6.QtGui import QPainter
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor("#7C9CF5"))
        p.setPen(QColor("#2E3A66"))
        p.drawRoundedRect(8, 14, 48, 40, 18, 18)
        p.setBrush(QColor("#2B2B3A"))
        p.drawEllipse(22, 30, 6, 7)
        p.drawEllipse(38, 30, 6, 7)
        p.end()
        icon = QIcon(pix)
        self.tray = QSystemTrayIcon(icon, None)
        menu = QMenu()
        menu.addAction("Settings…", self.open_settings)
        menu.addAction("Debug panel", self.open_debug)
        menu.addSeparator()

        move = menu.addMenu("Move to")
        move.addAction("Left edge", lambda: self.overlay.park("left"))
        move.addAction("Center", lambda: self.overlay.park("center"))
        move.addAction("Right edge", lambda: self.overlay.park("right"))

        size = menu.addMenu("Pet size")
        size.addAction("Small (70%)", lambda: self.set_scale(0.7))
        size.addAction("Normal (100%)", lambda: self.set_scale(1.0))
        size.addAction("Large (140%)", lambda: self.set_scale(1.4))

        av = menu.addMenu("Avoid programs")
        for label, mode in (("Auto (dodge + step behind)", "auto"),
                            ("Dodge windows", "dodge"),
                            ("Step behind full-screen apps", "behind"),
                            ("Off (always on top)", "off")):
            a = av.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.settings.avoid_mode == mode)
            a.triggered.connect(lambda _c, m=mode: self.set_avoid(m))

        mini = menu.addAction("Mini mode (pet only)")
        mini.setCheckable(True)
        mini.setChecked(self.settings.mini_mode)
        mini.triggered.connect(self.toggle_mini)
        self._mini_action = mini
        menu.addSeparator()

        self._hide_action = menu.addAction("Hide pet", self.toggle_hide)
        menu.addAction("Simulate coding (demo)", self.run_simulation)
        menu.addSeparator()
        menu.addAction("Exit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

        self.hotkeys = HotkeyManager({"p": self.toggle_hide, "m": self.toggle_mini})
        tip = "AgentPet — observer, not controller"
        if self.hotkeys.enabled:
            tip += f"  ({self.hotkeys.help}: hide/show · mini)"
        self.tray.setToolTip(tip)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        # single click on the tray icon also toggles visibility
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_hide()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self._apply_settings)
        dlg.exec()
        # pet count changed
        if len(self.manager.pets) != self.settings.pet_count:
            personality = Personality(**self.settings.personality)
            self.manager.spawn(self.settings.pet_count, self.overlay.home, personality)
            self._apply_settings()

    def open_debug(self) -> None:
        if self.debug_panel is None:
            self.debug_panel = DebugPanel(self)
        self.debug_panel.show()
        self.debug_panel.raise_()

    def run_simulation(self) -> None:
        """§47 — clearly labelled; never used for acceptance."""
        self.overlay.demo = True
        self.replay = ReplayPlayer(build_simulation(time.time()), speed=1.0)
        QTimer.singleShot(30000, self._end_simulation)

    def _end_simulation(self) -> None:
        self.overlay.demo = False

    def toggle_hide(self) -> None:
        vis = not self.overlay.isVisible()
        self.overlay.setVisible(vis)
        self.input_window.setVisible(vis)
        if hasattr(self, "_hide_action"):
            self._hide_action.setText("Show pet" if not vis else "Hide pet")

    def quit(self) -> None:
        self.file_observer.stop()
        self.registry.shutdown()
        if getattr(self, "hotkeys", None):
            self.hotkeys.shutdown()
        self.store.commit()
        self.store.close()
        QApplication.quit()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AgentPet")
    pet = AgentPetApp()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
