"""Test bootstrap — make `agentpet` importable from the repo root without install."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# AgentPet must never write outside D: during tests.
import os  # noqa: E402
os.environ.setdefault("AGENTPET_WB_DIR", str(ROOT / "tests" / "fixtures" / "wb_root"))
