"""Agent Adapter SDK (§9, §75).

The core never contains `if agent == "workbuddy"` logic. All agent-specific
knowledge lives in an adapter. Third parties can add `plugins/agents/my_agent`
by implementing the same interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from ..events.schema import NormalizedEvent


class Capability(str, Enum):
    PROCESS_DETECTION = "PROCESS_DETECTION"
    WINDOW_DETECTION = "WINDOW_DETECTION"
    LOG_OBSERVATION = "LOG_OBSERVATION"
    FILE_ACTIVITY = "FILE_ACTIVITY"
    COMMAND_ACTIVITY = "COMMAND_ACTIVITY"
    TEST_ACTIVITY = "TEST_ACTIVITY"
    GIT_ACTIVITY = "GIT_ACTIVITY"
    TASK_LIFECYCLE = "TASK_LIFECYCLE"


class HealthLevel(str, Enum):
    FULL = "full"
    DEGRADED = "degraded"
    MINIMAL = "minimal"
    OFFLINE = "offline"


@dataclass
class AdapterStatus:
    level: HealthLevel = HealthLevel.OFFLINE
    capabilities: Set[Capability] = field(default_factory=set)
    detail: str = ""
    last_error: str = ""
    sessions: List[Dict[str, str]] = field(default_factory=list)
    process_count: int = 0
    pid: Optional[int] = None
    last_observation_at: float = 0.0

    def has(self, cap: Capability) -> bool:
        return cap in self.capabilities

    def as_dict(self) -> Dict[str, object]:
        return {
            "level": self.level.value,
            "capabilities": sorted(c.value for c in self.capabilities),
            "detail": self.detail,
            "last_error": self.last_error,
            "sessions": self.sessions,
            "process_count": self.process_count,
            "pid": self.pid,
        }


class AgentAdapter(ABC):
    """Uniform interface every agent integration implements."""

    id: str = "abstract"
    display_name: str = "Abstract Agent"
    version: str = "0.1.0"

    def __init__(self) -> None:
        self.status = AdapterStatus()

    # --- identity ------------------------------------------------------
    def get_identity(self) -> Dict[str, str]:
        return {"id": self.id, "display_name": self.display_name,
                "version": self.version}

    # --- detection -----------------------------------------------------
    @abstractmethod
    def identify(self) -> bool:
        """True if this agent is present on the machine at all."""

    @abstractmethod
    def get_processes(self) -> List[Dict[str, object]]:
        """Public process info for this agent (name, pid, ppid, cmdline)."""

    # --- observation ---------------------------------------------------
    @abstractmethod
    def observe(self) -> List[NormalizedEvent]:
        """One observation tick. Must never raise; return [] on failure."""

    # --- capability / health -------------------------------------------
    @abstractmethod
    def get_capabilities(self) -> Set[Capability]:
        """Capabilities currently *working*, not theoretically supported."""

    @abstractmethod
    def health_check(self) -> AdapterStatus:
        """"""

    def normalize_event(self, raw: Dict[str, object]) -> Optional[NormalizedEvent]:
        """Optional hook: raw record -> NormalizedEvent."""
        return None

    def shutdown(self) -> None:
        """Release handles/watchers."""
