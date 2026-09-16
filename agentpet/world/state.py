"""Observation fusion (§15) and world state (§16).

Everything the UI shows comes from WorldState. The UI never talks to an observer.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..events.schema import EventType, NormalizedEvent, TruthLevel, make

AgentStatus = str  # offline|idle|thinking|planning|reading|writing|terminal|
                   # testing|debugging|git|error|done

_STATUS_BY_EVENT: Dict[EventType, AgentStatus] = {
    EventType.AGENT_STARTED: "idle",
    EventType.AGENT_DISCOVERED: "idle",
    EventType.AGENT_STOPPED: "offline",
    EventType.TASK_STARTED: "thinking",
    EventType.TASK_DETECTED: "thinking",
    EventType.TASK_PROGRESS: "thinking",
    EventType.TASK_COMPLETED: "done",
    EventType.TASK_FAILED: "error",
    EventType.PLANNING: "planning",
    EventType.THINKING: "thinking",
    EventType.READING_FILE: "reading",
    EventType.FILE_OPENED: "reading",
    EventType.WRITING_FILE: "writing",
    EventType.FILE_CHANGED: "writing",
    EventType.FILE_CREATED: "writing",
    EventType.COMMAND_STARTED: "terminal",
    EventType.COMMAND_OUTPUT: "terminal",
    EventType.COMMAND_FAILED: "error",
    EventType.TEST_STARTED: "testing",
    EventType.TEST_PROGRESS: "testing",
    EventType.TEST_PASSED: "testing",
    EventType.TEST_FAILED: "error",
    EventType.DEBUGGING_STARTED: "debugging",
    EventType.GIT_COMMIT_DETECTED: "git",
    EventType.GIT_PUSH_DETECTED: "git",
    EventType.GIT_STATUS_CHANGED: "git",
    EventType.ERROR_DETECTED: "error",
}


@dataclass
class AgentState:
    agent_id: str
    online: bool = False
    status: AgentStatus = "offline"
    session_id: Optional[str] = None
    workspace: Optional[str] = None
    last_event: Optional[str] = None
    last_event_at: float = 0.0
    task_active: bool = False
    current_file: Optional[str] = None
    event_count: int = 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "online": self.online,
            "status": self.status,
            "session_id": self.session_id,
            "workspace": self.workspace,
            "last_event": self.last_event,
            "task_active": self.task_active,
            "current_file": self.current_file,
            "event_count": self.event_count,
        }


@dataclass
class WorldState:
    agents: Dict[str, AgentState] = field(default_factory=dict)
    timeline: List[str] = field(default_factory=list)
    last_commit: Optional[Dict[str, str]] = None
    terminal_lines: List[str] = field(default_factory=list)
    editor_file: Optional[str] = None
    started_at: float = field(default_factory=time.time)

    def agent(self, agent_id: str) -> AgentState:
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentState(agent_id=agent_id)
        return self.agents[agent_id]

    def apply(self, ev: NormalizedEvent) -> None:
        st = self.agent(ev.agent_id or "unknown")
        st.event_count += 1
        st.last_event = ev.event_type.value
        st.last_event_at = ev.timestamp
        if ev.session_id:
            st.session_id = ev.session_id
        if ev.workspace_id:
            st.workspace = ev.workspace_id

        if ev.event_type is EventType.AGENT_STARTED or \
           ev.event_type is EventType.AGENT_DISCOVERED:
            st.online = True
        elif ev.event_type is EventType.AGENT_STOPPED:
            st.online = False
            st.status = "offline"
            st.task_active = False
            return

        new_status = _STATUS_BY_EVENT.get(ev.event_type)
        if new_status:
            st.status = new_status

        if ev.event_type is EventType.TASK_STARTED:
            st.task_active = True
        elif ev.event_type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED):
            st.task_active = False

        path = ev.payload.get("path") if ev.payload else None
        if path:
            st.current_file = str(path)
            self.editor_file = str(path)

        if ev.event_type is EventType.GIT_COMMIT_DETECTED and ev.payload:
            self.last_commit = {
                "sha": str(ev.payload.get("sha", "")),
                "message": str(ev.payload.get("message", ""))[:120],
            }

        self.timeline.append(
            f"{time.strftime('%H:%M:%S', time.localtime(ev.timestamp))} "
            f"{ev.event_type.value} {ev.truth_level.value} {ev.confidence:.2f}"
            + (f"  {path}" if path else ""))
        if len(self.timeline) > 400:
            del self.timeline[:-400]

    def push_terminal(self, line: str) -> None:
        self.terminal_lines.append(line)
        if len(self.terminal_lines) > 60:
            del self.terminal_lines[:-60]


class FusionEngine:
    """Turns correlated signals into higher-confidence events (§15).

    Rule of this implementation: an inference may only *add* an event when at
    least two independent signals agree, and it must be marked INFERRED.
    """

    def __init__(self, window: float = 6.0) -> None:
        self.window = window
        self._recent_files: List[tuple] = []
        self._recent_commands: List[tuple] = []
        self._last_infer: Dict[str, float] = {}

    def observe(self, ev: NormalizedEvent) -> List[NormalizedEvent]:
        now = ev.timestamp
        out: List[NormalizedEvent] = []
        if ev.event_type is EventType.FILE_CHANGED:
            self._recent_files.append((now, ev))
        elif ev.event_type in (EventType.COMMAND_STARTED, EventType.COMMAND_OUTPUT):
            self._recent_commands.append((now, ev))
        self._prune(now)

        # file changed + agent thinking/working => actively writing
        if ev.event_type is EventType.FILE_CHANGED and ev.session_id:
            if self._throttle("writing", now, 3.0):
                out.append(make(
                    EventType.WRITING_FILE,
                    "fusion:file-changed+during-task",
                    agent_id=ev.agent_id,
                    session_id=ev.session_id,
                    workspace_id=ev.workspace_id,
                    truth_level=TruthLevel.INFERRED,
                    confidence=0.75,
                    payload={"path": ev.payload.get("path")},
                ))

        # command activity + a test-like file touched => probably running tests
        if ev.event_type in (EventType.COMMAND_STARTED, EventType.COMMAND_OUTPUT):
            if self._recent_files and self._throttle("testing", now, 8.0):
                recent_file = self._recent_files[-1][1]
                path = str(recent_file.payload.get("path", ""))
                if self._looks_like_test(path):
                    out.append(make(
                        EventType.TEST_STARTED,
                        "fusion:command-activity+test-file",
                        agent_id=ev.agent_id,
                        session_id=ev.session_id,
                        workspace_id=ev.workspace_id,
                        truth_level=TruthLevel.INFERRED,
                        confidence=0.6,
                        payload={"path": path},
                    ))
        return out

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _looks_like_test(path: str) -> bool:
        p = path.lower().replace("\\", "/")
        name = p.rsplit("/", 1)[-1]
        return (name.startswith("test_") or name.endswith("_test.py")
                or name.endswith(".test.ts") or name.endswith(".test.js")
                or name.endswith(".spec.ts") or "/tests/" in p
                or "/test/" in p or name in ("conftest.py", "pytest.ini"))

    def _throttle(self, key: str, now: float, seconds: float) -> bool:
        last = self._last_infer.get(key, 0.0)
        if now - last < seconds:
            return False
        self._last_infer[key] = now
        return True

    def _prune(self, now: float) -> None:
        self._recent_files = [x for x in self._recent_files
                              if now - x[0] <= self.window * 4]
        self._recent_commands = [x for x in self._recent_commands
                                 if now - x[0] <= self.window]
