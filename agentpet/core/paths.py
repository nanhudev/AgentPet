"""Filesystem layout. Everything AgentPet writes lives under D:\\AgentPet.

The user's hard constraint for this project: work on D:, do not consume C:.
Only truly unavoidable OS-provided locations (the Python install, the user's
existing ~/.workbuddy observation targets) are read from C:.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]          # D:\\AgentPet
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "agentpet.db"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
CAPTURE_DIR = PROJECT_ROOT / "docs" / "testing" / "screenshots"

for _d in (DATA_DIR, LOG_DIR, FIXTURES_DIR, CAPTURE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def user_home() -> Path:
    return Path.home()


def workbuddy_user_dir() -> Path:
    """Discovered, not assumed (§13). Honours AGENTPET_WB_DIR for tests."""
    env = os.environ.get("AGENTPET_WB_DIR")
    if env:
        return Path(env)
    return user_home() / ".workbuddy"


def workbuddy_logs_dir() -> Path:
    return workbuddy_user_dir() / "logs"


def workbuddy_db() -> Path:
    return workbuddy_user_dir() / "workbuddy.db"
