"""Adapter registry (§75) — keeps `if agent == ...` out of the core."""
from __future__ import annotations

from typing import Dict, List

from .base import AgentAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self.adapters: Dict[str, AgentAdapter] = {}

    def register(self, adapter: AgentAdapter) -> None:
        self.adapters[adapter.id] = adapter

    def get(self, agent_id: str) -> AgentAdapter:
        return self.adapters[agent_id]

    def all(self) -> List[AgentAdapter]:
        return list(self.adapters.values())

    def observe_all(self) -> List:
        out = []
        for a in self.adapters.values():
            try:
                out += a.observe()
            except Exception:
                continue
        return out

    def shutdown(self) -> None:
        for a in self.adapters.values():
            try:
                a.shutdown()
            except Exception:
                pass
