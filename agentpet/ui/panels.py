"""Debug panel (§34), settings (§32) and first-run welcome (§70)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHeaderView, QLabel,
                               QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from ..adapters.base import Capability
from ..events.schema import NormalizedEvent
from ..observation.process import cpu_percent, memory_mb


class DebugPanel(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.setWindowTitle("AgentPet — Debug")
        self.resize(940, 620)
        self.tabs = QTabWidget(self)
        self.summary = QTextEdit(readOnly=True)
        self.events = QTableWidget(0, 6)
        self.events.setHorizontalHeaderLabels(
            ["time", "event", "truth", "conf", "source", "payload"])
        self.events.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.events.horizontalHeader().setStretchLastSection(True)
        self.events.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.timeline = QTextEdit(readOnly=True)
        self.timeline.setFontFamily("Consolas")
        self.summary.setFontFamily("Consolas")
        self.tabs.addTab(self.summary, "State")
        self.tabs.addTab(self.events, "Events")
        self.tabs.addTab(self.timeline, "Timeline")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(700)
        self.refresh()

    def refresh(self) -> None:
        app = self.app
        lines: List[str] = []
        lines.append(f"uptime            : {time.time() - app.started_at:.0f}s")
        lines.append(f"fps               : {app.overlay.fps:.1f}")
        lines.append(f"cpu (agentpet)    : {cpu_percent():.1f}%")
        lines.append(f"memory (agentpet) : {memory_mb():.1f} MB")
        lines.append("")
        for aid, st in app.world.agents.items():
            lines.append(f"agent {aid}")
            lines.append(f"  online={st.online} status={st.status} "
                         f"session={st.session_id} task_active={st.task_active}")
            lines.append(f"  workspace={st.workspace}")
            lines.append(f"  events={st.event_count} last={st.last_event}")
        lines.append("")
        for adapter in app.adapters:
            hc = adapter.health_check()
            lines.append(f"adapter {adapter.id} ({adapter.display_name})")
            lines.append(f"  level={hc.level.value}  detail={hc.detail}")
            lines.append(f"  capabilities={sorted(c.value for c in hc.capabilities)}")
            if hc.last_error:
                lines.append(f"  last_error={hc.last_error}")
            for s in hc.sessions[:6]:
                lines.append(f"  session {s['id'][:8]} {s['status']} {s['cwd']}")
        lines.append("")
        lines.append(f"file watcher      : {app.file_observer.health()} "
                     f"(pending {app.file_observer.pending()})")
        lines.append(f"git observer      : repo={app.git_observer.is_repo} "
                     f"head={app.git_observer.last_head} "
                     f"branch={app.git_observer.last_branch} err={app.git_observer.last_error}")
        lines.append(f"test artifacts    : ws={app.test_observer.workspace} "
                     f"err={app.test_observer.last_error}")
        lines.append(f"event bus         : {app.bus.stats()}")
        lines.append(f"pet               : {self._pet_line()}")
        self.summary.setPlainText("\n".join(lines))

        evs = app.bus.history(200)[::-1]
        self.events.setRowCount(len(evs))
        for i, ev in enumerate(evs):
            vals = [time.strftime("%H:%M:%S", time.localtime(ev.timestamp)),
                    ev.event_type.value, ev.truth_level.value,
                    f"{ev.confidence:.2f}", ev.source,
                    str(ev.payload)[:90]]
            for j, v in enumerate(vals):
                self.events.setItem(i, j, QTableWidgetItem(v))
        self.timeline.setPlainText("\n".join(app.world.timeline[-200:]))

    def _pet_line(self) -> str:
        pet = self.app.manager.primary
        if not pet:
            return "none"
        return (f"{pet.pet_id} state={pet.state.value} anim={pet.animation.value} "
                f"pos=({pet.x:.0f},{pet.y:.0f}) dst={pet.destination} "
                f"bubble={pet.bubble!r}")


class SettingsDialog(QDialog):
    def __init__(self, settings, on_changed) -> None:
        super().__init__()
        self.settings = settings
        self.on_changed = on_changed
        self.setWindowTitle("AgentPet — Settings")
        form = QFormLayout(self)

        self.count = QSpinBox(minimum=1, maximum=3, value=settings.pet_count)
        self.scale = QDoubleSpinBox(minimum=0.5, maximum=2.5, singleStep=0.1,
                                    value=settings.pet_scale)
        self.speed = QDoubleSpinBox(minimum=0.25, maximum=3.0, singleStep=0.25,
                                    value=settings.animation_speed)
        self.opacity = QDoubleSpinBox(minimum=0.3, maximum=1.0, singleStep=0.05,
                                      value=settings.opacity)
        self.always = QCheckBox(checked=settings.always_on_top)
        self.avoid = QComboBox()
        self.avoid.addItem("Auto — dodge + step behind full-screen apps", "auto")
        self.avoid.addItem("Dodge — walk to a free spot when idle", "dodge")
        self.avoid.addItem("Behind — drop always-on-top under full apps", "behind")
        self.avoid.addItem("Off — always on top, never move", "off")
        idx = self.avoid.findData(getattr(settings, "avoid_mode", "auto"))
        self.avoid.setCurrentIndex(max(0, idx))
        self.mini = QCheckBox(checked=getattr(settings, "mini_mode", False))
        self.dim = QDoubleSpinBox(minimum=0.05, maximum=1.0, singleStep=0.05,
                                  value=getattr(settings, "panel_dim", 0.35))
        self.reduce = QCheckBox(checked=settings.reduce_motion)
        self.sound = QCheckBox(checked=settings.sound_enabled)
        self.term = QCheckBox(checked=settings.show_mini_terminal)
        self.edit = QCheckBox(checked=settings.show_mini_editor)
        self.gitanim = QCheckBox(checked=settings.show_git_animations)
        self.privacy = QCheckBox(checked=settings.privacy_mode)
        self.wsobserve = QCheckBox(checked=settings.workspace_observation)
        self.debug = QCheckBox(checked=settings.debug_mode)
        self.startup = QCheckBox(checked=settings.launch_on_startup)

        form.addRow("Pets", self.count)
        form.addRow("Pet scale", self.scale)
        form.addRow("Animation speed", self.speed)
        form.addRow("Opacity", self.opacity)
        form.addRow("Always on top", self.always)
        form.addRow("Avoid programs", self.avoid)
        form.addRow("Mini mode (pet only)", self.mini)
        form.addRow("Dim panels when covered", self.dim)
        form.addRow("Reduce motion", self.reduce)
        form.addRow("Sound", self.sound)
        form.addRow("Show Mini Terminal", self.term)
        form.addRow("Show Mini Editor", self.edit)
        form.addRow("Show Git animations", self.gitanim)
        form.addRow("Privacy mode", self.privacy)
        form.addRow("Observe workspace files", self.wsobserve)
        form.addRow("Debug mode", self.debug)
        form.addRow("Launch on startup", self.startup)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _save(self) -> None:
        self.settings.update(
            pet_count=self.count.value(),
            pet_scale=self.scale.value(),
            animation_speed=self.speed.value(),
            opacity=self.opacity.value(),
            always_on_top=self.always.isChecked(),
            avoid_mode=self.avoid.currentData() or "auto",
            mini_mode=self.mini.isChecked(),
            panel_dim=self.dim.value(),
            reduce_motion=self.reduce.isChecked(),
            sound_enabled=self.sound.isChecked(),
            show_mini_terminal=self.term.isChecked(),
            show_mini_editor=self.edit.isChecked(),
            show_git_animations=self.gitanim.isChecked(),
            privacy_mode=self.privacy.isChecked(),
            workspace_observation=self.wsobserve.isChecked(),
            debug_mode=self.debug.isChecked(),
            launch_on_startup=self.startup.isChecked(),
        )
        self.settings.save()
        self.on_changed()
        self.accept()


class WelcomeDialog(QDialog):
    """§70 — no API key, no account, just an honest explanation."""

    def __init__(self, detected: bool) -> None:
        super().__init__()
        self.setWindowTitle("Welcome to AgentPet")
        self.resize(520, 320)
        lay = QVBoxLayout(self)
        status = "Found" if detected else "Not found — AgentPet will keep waiting"
        lay.addWidget(QLabel(
            "<h2>AgentPet</h2>"
            "<p>AgentPet watches your coding agents locally and turns their work "
            "into a little living world on your desktop.</p>"
            "<ul><li>It never controls your computer.</li>"
            "<li>It never runs, writes or commits anything.</li>"
            "<li>Nothing is sent to the cloud.</li></ul>"
            f"<p><b>WorkBuddy: {status}</b></p>"))
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
