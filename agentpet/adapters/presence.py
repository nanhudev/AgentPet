"""P1 adapters — architecture-ready (§1).

V0.1 only needs these to *exist behind the same interface* and to detect process
presence. Deep activity detection is deliberately not implemented yet, and the
capability set says so honestly.
"""
from __future__ import annotations

from typing import Dict, List, Set

from ..events.schema import EventType, NormalizedEvent, make
from ..observation.process import find_processes
from .base import AgentAdapter, Capability, HealthLevel, AdapterStatus


class ProcessPresenceAdapter(AgentAdapter):
    """Detects that an agent is installed/running; nothing more."""

    match_names: tuple = ()

    def identify(self) -> bool:
        return bool(find_processes(self.match_names))

    def get_processes(self) -> List[Dict[str, object]]:
        return find_processes(self.match_names)

    def observe(self) -> List[NormalizedEvent]:
        procs = self.get_processes()
        was = self.status.process_count
        self.status.process_count = len(procs)
        if procs and not was:
            return [make(EventType.AGENT_STARTED, f"{self.id}:process:psutil",
                         agent_id=self.id, payload={"pid_count": len(procs)})]
        if not procs and was:
            return [make(EventType.AGENT_STOPPED, f"{self.id}:process:psutil",
                         agent_id=self.id, payload={"pid_count": 0})]
        return []

    def get_capabilities(self) -> Set[Capability]:
        return {Capability.PROCESS_DETECTION} if self.status.process_count else set()

    def health_check(self) -> AdapterStatus:
        procs = self.get_processes()
        self.status.process_count = len(procs)
        self.status.level = (HealthLevel.MINIMAL if procs else HealthLevel.OFFLINE)
        self.status.capabilities = self.get_capabilities()
        self.status.detail = f"{len(procs)} process(es) — presence only in V0.1"
        return self.status


class CodexAdapter(ProcessPresenceAdapter):
    id = "codex"
    display_name = "OpenAI Codex"
    match_names = ("codex",)


class ClaudeCodeAdapter(ProcessPresenceAdapter):
    id = "claude_code"
    display_name = "Claude Code"
    match_names = ("claude",)


class CursorAdapter(ProcessPresenceAdapter):
    id = "cursor"
    display_name = "Cursor"
    match_names = ("cursor",)


class DeepSeekHarnessAdapter(ProcessPresenceAdapter):
    id = "deepseek_harness"
    display_name = "DeepSeek Harness"
    match_names = ("dsh", "deepseek")


def all_p1_adapters() -> List[AgentAdapter]:
    return [CodexAdapter(), ClaudeCodeAdapter(), CursorAdapter(),
            DeepSeekHarnessAdapter()]
