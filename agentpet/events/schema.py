"""Event schema — the single normalized shape everything else speaks.

Truth discipline is enforced here, not by convention:
  * every event needs a machine-readable ``source``;
  * an INFERRED event may never claim confidence above 0.75.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional


class TruthLevel(str, Enum):
    OBSERVED = "OBSERVED"        # directly read from an agent-produced record
    INFERRED = "INFERRED"        # derived by fusing several signals
    VISUAL_ONLY = "VISUAL_ONLY"  # produced by AgentPet's own theatre, no external fact


MAX_INFERRED_CONFIDENCE = 0.75


class EventType(str, Enum):
    # lifecycle
    AGENT_DISCOVERED = "AGENT_DISCOVERED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_STOPPED = "AGENT_STOPPED"
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"
    TASK_DETECTED = "TASK_DETECTED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    # cognition
    THINKING = "THINKING"
    PLANNING = "PLANNING"
    # files
    READING_FILE = "READING_FILE"
    FILE_OPENED = "FILE_OPENED"
    FILE_CHANGED = "FILE_CHANGED"
    FILE_CREATED = "FILE_CREATED"
    FILE_DELETED = "FILE_DELETED"
    WRITING_FILE = "WRITING_FILE"
    # commands
    COMMAND_STARTED = "COMMAND_STARTED"
    COMMAND_OUTPUT = "COMMAND_OUTPUT"
    COMMAND_COMPLETED = "COMMAND_COMPLETED"
    COMMAND_FAILED = "COMMAND_FAILED"
    # tests
    TEST_STARTED = "TEST_STARTED"
    TEST_PROGRESS = "TEST_PROGRESS"
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    # debug
    DEBUGGING_STARTED = "DEBUGGING_STARTED"
    DEBUGGING_ENDED = "DEBUGGING_ENDED"
    # git
    GIT_REPOSITORY_DETECTED = "GIT_REPOSITORY_DETECTED"
    GIT_STATUS_CHANGED = "GIT_STATUS_CHANGED"
    GIT_COMMIT_DETECTED = "GIT_COMMIT_DETECTED"
    GIT_PUSH_DETECTED = "GIT_PUSH_DETECTED"
    # misc
    APP_CONTEXT_CHANGED = "APP_CONTEXT_CHANGED"
    ERROR_DETECTED = "ERROR_DETECTED"
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class NormalizedEvent:
    event_type: EventType
    source: str
    truth_level: TruthLevel = TruthLevel.OBSERVED
    confidence: float = 1.0
    agent_id: str = ""
    agent_type: str = ""
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    workspace_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    dedup_key: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("every NormalizedEvent requires a non-empty source")
        if self.truth_level is TruthLevel.INFERRED:
            object.__setattr__(
                self, "confidence", min(self.confidence, MAX_INFERRED_CONFIDENCE))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not self.dedup_key:
            key_material = "|".join([
                self.event_type.value,
                str(self.session_id or ""),
                str(self.workspace_id or ""),
                str(self.payload.get("path", "")),
            ])
            object.__setattr__(self, "dedup_key", key_material)

    # --- serialization -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["truth_level"] = self.truth_level.value
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NormalizedEvent":
        return NormalizedEvent(
            event_type=EventType(d["event_type"]),
            source=d.get("source", "replay"),
            truth_level=TruthLevel(d.get("truth_level", "OBSERVED")),
            confidence=d.get("confidence", 1.0),
            agent_id=d.get("agent_id", ""),
            agent_type=d.get("agent_type", ""),
            session_id=d.get("session_id"),
            task_id=d.get("task_id"),
            workspace_id=d.get("workspace_id"),
            payload=d.get("payload", {}),
            timestamp=d.get("timestamp", time.time()),
            event_id=d.get("event_id", uuid.uuid4().hex[:16]),
            dedup_key=d.get("dedup_key", ""),
        )

    def short(self) -> str:
        return (f"{self.event_type.value:<22} {self.truth_level.value:<11} "
                f"{self.confidence:.2f}  {self.source}")


def make(  # compact constructor used by adapters
    event_type: EventType,
    source: str,
    *,
    agent_id: str,
    session_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    truth_level: TruthLevel = TruthLevel.OBSERVED,
    confidence: float = 1.0,
    payload: Optional[Dict[str, Any]] = None,
    timestamp: Optional[float] = None,
) -> NormalizedEvent:
    kwargs: Dict[str, Any] = dict(
        event_type=event_type,
        source=source,
        agent_id=agent_id,
        agent_type=agent_id,
        session_id=session_id,
        task_id=session_id,
        workspace_id=workspace_id,
        truth_level=truth_level,
        confidence=confidence,
        payload=payload or {},
    )
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return NormalizedEvent(**kwargs)
