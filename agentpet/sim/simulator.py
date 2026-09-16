"""Developer simulation mode (§47).

Generates synthetic *labelled* events for visual testing. The UI must show a
SIMULATION badge whenever this is used, and final acceptance forbids it.
"""
from __future__ import annotations

import time
from typing import List

from ..events.schema import (EventType, NormalizedEvent, TruthLevel, make)

SCRIPT = [
    (0.0, EventType.AGENT_STARTED, {}),
    (1.5, EventType.TASK_STARTED, {}),
    (2.5, EventType.PLANNING, {}),
    (4.0, EventType.FILE_CHANGED, {"path": "calculator.py", "additions": 24,
                                   "deletions": 0}),
    (5.0, EventType.FILE_CHANGED, {"path": "tests/test_calculator.py",
                                   "additions": 18, "deletions": 0}),
    (7.0, EventType.COMMAND_STARTED, {}),
    (9.0, EventType.COMMAND_OUTPUT, {}),
    (10.5, EventType.TEST_STARTED, {}),
    (13.0, EventType.TEST_FAILED, {}),
    (15.0, EventType.FILE_CHANGED, {"path": "calculator.py", "additions": 3,
                                    "deletions": 2}),
    (17.0, EventType.TEST_STARTED, {}),
    (19.5, EventType.TEST_PASSED, {}),
    (21.0, EventType.GIT_COMMIT_DETECTED, {"sha": "abc1234",
                                           "message": "add calculator"}),
    (23.0, EventType.TASK_COMPLETED, {}),
]


def build(start: float, workspace: str = "D:\\AgentPet\\tests\\fixtures\\demo_repo",
          session_id: str = "simulation") -> List[NormalizedEvent]:
    evs: List[NormalizedEvent] = []
    for offset, et, payload in SCRIPT:
        evs.append(make(
            et,
            f"simulation:{et.value.lower()}",
            agent_id="workbuddy",
            session_id=session_id,
            workspace_id=workspace,
            truth_level=TruthLevel.VISUAL_ONLY,
            confidence=0.0,
            payload=payload,
            timestamp=start + offset,
        ))
    return evs
