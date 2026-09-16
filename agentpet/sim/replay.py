"""Replay system (§46) — UI development without running a real agent.

A session captured as JSONL can be replayed through the same event bus the real
adapter uses. Replay is a development tool; it never replaces real acceptance.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator, List, Optional

from ..events.schema import NormalizedEvent


def load(path: Path) -> List[NormalizedEvent]:
    out: List[NormalizedEvent] = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            try:
                out.append(NormalizedEvent.from_dict(json.loads(ln)))
            except Exception:
                continue
    return out


def save(path: Path, events: List[NormalizedEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")


class ReplayPlayer:
    """Emits recorded events on their original relative cadence."""

    def __init__(self, events: List[NormalizedEvent], speed: float = 1.0) -> None:
        self.events = sorted(events, key=lambda e: e.timestamp)
        self.speed = max(0.05, speed)
        self.i = 0
        self.started_at: Optional[float] = None
        self.base_ts = self.events[0].timestamp if self.events else 0.0

    def pending(self, now: Optional[float] = None) -> List[NormalizedEvent]:
        if not self.events:
            return []
        now = now if now is not None else time.time()
        if self.started_at is None:
            self.started_at = now
        out: List[NormalizedEvent] = []
        while self.i < len(self.events):
            ev = self.events[self.i]
            due = self.started_at + (ev.timestamp - self.base_ts) / self.speed
            if now < due:
                break
            out.append(ev)
            self.i += 1
        return out

    @property
    def done(self) -> bool:
        return self.i >= len(self.events)
