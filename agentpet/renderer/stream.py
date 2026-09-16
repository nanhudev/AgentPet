"""Abstract streaming templates for the Mini Terminal (§23 Truthful Theatre).

WorkBuddy's local logs do NOT expose command text or stdout (verified by
scripts/probe_wb4.py: dispatch events carry counters only). Fabricating a
concrete command would violate Truthful Theatre, so the terminal streams
*abstract state lines* instead — dots, typewriter text like "working" /
"running checks" — which is exactly what §23 prescribes for unknown facts:
"Running command... / Working... / Testing...".

Real observed output always wins: the moment a real COMMAND_OUTPUT event
arrives, the streamer stands down for a while (engine decides) and real text
is shown instead.
"""
from __future__ import annotations

from typing import List, Optional

TEMPLATES = {
    "command": ["running command", "working", "waiting for output"],
    "test": ["running checks", "collecting results"],
    "think": ["thinking", "planning"],
    "file": ["updating files", "working"],
}

REVEAL_TIME = 0.7      # seconds to type a line out
LINE_TIME = 2.4        # seconds a line stays before cycling
DOTS = "..."           # animated as ·.. / ··· / ....


class OutputStreamer:
    """One animated abstract line, cycled from a template list."""

    def __init__(self) -> None:
        self.kind: Optional[str] = None
        self.t = 0.0
        self._lines: List[str] = []

    @property
    def active(self) -> bool:
        return self.kind is not None

    def start(self, kind: str) -> None:
        if self.kind != kind:
            self.kind = kind
            self.t = 0.0
            self._lines = list(TEMPLATES.get(kind, ["working"]))

    def stop(self) -> None:
        self.kind = None

    def current(self) -> Optional[str]:
        """The animated partial line, e.g. 'runni..' — None when idle."""
        if not self.active or not self._lines:
            return None
        idx = int(self.t / LINE_TIME) % len(self._lines)
        local = self.t - idx * LINE_TIME
        base = self._lines[idx]
        if local < REVEAL_TIME:
            n = max(1, int(len(base) * local / REVEAL_TIME))
            return base[:n]
        # after reveal: animated dots + ellipsis breathing
        dots = "." * (1 + int(local * 2.5) % 3)
        return base + " " + dots
