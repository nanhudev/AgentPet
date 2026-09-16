"""Settings (§32). Persisted as JSON under D:\\AgentPet\\data."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

from .paths import SETTINGS_FILE


@dataclass
class Settings:
    # appearance / behaviour
    pet_count: int = 1
    pet_scale: float = 1.0
    animation_speed: float = 1.0
    opacity: float = 1.0
    always_on_top: bool = True
    reduce_motion: bool = False
    sound_enabled: bool = False
    # staying out of the way (see docs/BEHAVIOR_ENGINE.md §avoidance)
    #   off    — never moves for another window
    #   dodge  — walks to a free spot when idle
    #   behind — drops always-on-top while a maximised app covers the screen
    #   auto   — dodge + behind + dim overlapped panels (default)
    avoid_mode: str = "auto"
    mini_mode: bool = False          # pet only: never deploy the workbench
    panel_dim: float = 0.35          # panel opacity while covered by a window
    # panels
    show_mini_terminal: bool = True
    show_mini_editor: bool = True
    show_git_animations: bool = True
    # privacy
    privacy_mode: bool = False
    workspace_observation: bool = True
    # system
    launch_on_startup: bool = False
    debug_mode: bool = False
    # runtime-only
    first_run_done: bool = False
    timeline_retention_days: int = 7
    personality: Dict[str, float] = field(default_factory=lambda: {
        "energy": 0.7, "curiosity": 0.8, "patience": 0.5,
        "expressiveness": 0.8, "sleepiness": 0.35})

    # --- persistence ---------------------------------------------------
    @classmethod
    def load(cls, path: Path = SETTINGS_FILE) -> "Settings":
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items() if k in cls().__dict__}
                return cls(**known)
        except Exception:
            pass
        return cls()

    def save(self, path: Path = SETTINGS_FILE) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except Exception:
            pass

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
