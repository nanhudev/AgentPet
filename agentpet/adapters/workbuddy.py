"""WorkBuddy adapter — P0 for V0.1.

Everything here was derived by *inspecting this machine* (scripts/probe_wb*.py),
not by assuming paths (§13).

Observed sources
----------------
1. process tree        : WorkBuddy.exe (+ codebuddy children)      -> AGENT_*
2. workbuddy.db        : table `sessions(id, cwd, title, status,
                         created_at, updated_at, last_activity_at, model)`
                                                                   -> SESSION_*, TASK_DETECTED
3. sdk conversation log: ~/.workbuddy/logs/<UTC-date>/sdk/conversations/<sid>.log
     state-machine:transition  {from,to,input}   -> TASK_STARTED / PLANNING /
                                                    THINKING / TASK_COMPLETED / TASK_FAILED
     event-machine:dispatch    {input}           -> COMMAND_STARTED / COMMAND_OUTPUT
     resource-effect:failed                      -> ERROR_DETECTED
4. changes-index       : changes-index/<sid>.json -> FILE_CHANGED (real paths,
                                                    real +/- counts)

What is deliberately NOT claimed (§73)
--------------------------------------
* The SDK log records that a tool call happened but never its name or arguments,
  so COMMAND_STARTED carries **no command text**. The Mini Terminal must render
  "Running command...".
* Test results are not directly observable; they are inferred by the fusion layer
  and always carry truth_level=INFERRED.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..core import safety
from ..core.paths import workbuddy_db, workbuddy_logs_dir, workbuddy_user_dir
from ..events.schema import (EventType, NormalizedEvent, TruthLevel, make)
from ..observation.logtail import LogTailer
from ..observation.process import find_processes
from ..observation.window import visible_window_titles
from .base import AgentAdapter, Capability, HealthLevel, AdapterStatus

AGENT_ID = "workbuddy"

# sdk log -> normalized event
TRANSITION_MAP = {
    "PROMPT_SENT": EventType.TASK_STARTED,
    "TURN_COMPLETED": EventType.TASK_COMPLETED,
    "TURN_ERROR": EventType.TASK_FAILED,
    "PERMISSION_REQUESTED": None,   # intentionally not dramatised
    "PERMISSION_RESOLVED": None,
}

DISPATCH_MAP = {
    "tool_call": EventType.COMMAND_STARTED,
    "terminal_output_chunk": EventType.COMMAND_OUTPUT,
    "terminal_update": EventType.COMMAND_OUTPUT,
    "session_end": EventType.SESSION_ENDED,
}

MAX_FILE_EVENTS_PER_TICK = 6


class WorkBuddyAdapter(AgentAdapter):
    id = AGENT_ID
    display_name = "WorkBuddy"
    version = "0.1.0"

    def __init__(self, root: Optional[Path] = None,
                 tail_from_start: bool = False,
                 focus: str = "latest") -> None:
        """focus: 'latest' = follow the most recently active working session,
        'all' = observe every session (noisier)."""
        super().__init__()
        self.tail_from_start = tail_from_start
        self.focus = focus
        self.focus_session: Optional[str] = None
        self.root = Path(root) if root else workbuddy_user_dir()
        self.logs_dir = self.root / "logs"
        self.changes_dir = self.root / "changes-index"
        self.db_path = self.root / "workbuddy.db"
        self._tailers: Dict[str, LogTailer] = {}
        self._session_state: Dict[str, Dict[str, object]] = {}
        self._seen_changes: Set[Tuple[str, str]] = set()
        self._last_state: Dict[str, str] = {}
        self._cmd_last_emit: Dict[str, float] = {}
        self._intervals = {"process": 1.0, "sessions": 2.0, "log": 0.4,
                           "changes": 1.5, "window": 5.0}
        self._next_at = {k: 0.0 for k in self._intervals}
        self._processes: List[Dict[str, object]] = []
        self._window_hit = False
        self._last_error = ""

    # ------------------------------------------------------------------
    # detection
    # ------------------------------------------------------------------
    def identify(self) -> bool:
        procs = find_processes(("workbuddy",))
        self._processes = procs
        return bool(procs)

    def get_processes(self) -> List[Dict[str, object]]:
        return list(self._processes)

    # ------------------------------------------------------------------
    # observation tick
    # ------------------------------------------------------------------
    def observe(self) -> List[NormalizedEvent]:
        now = time.time()
        out: List[NormalizedEvent] = []
        try:
            self._refresh_focus()
            if now >= self._next_at["process"]:
                self._next_at["process"] = now + self._intervals["process"]
                out += self._poll_process(now)
            if now >= self._next_at["sessions"]:
                self._next_at["sessions"] = now + self._intervals["sessions"]
                out += self._poll_sessions(now)
            if now >= self._next_at["log"]:
                self._next_at["log"] = now + self._intervals["log"]
                out += self._tail_logs(now)
            if now >= self._next_at["changes"]:
                self._next_at["changes"] = now + self._intervals["changes"]
                out += self._poll_changes(now)
            if now >= self._next_at["window"]:
                self._next_at["window"] = now + self._intervals["window"]
                out += self._poll_windows(now)
        except Exception as exc:  # an observer failure must never crash the app
            self._last_error = f"{type(exc).__name__}: {exc}"
        return out

    # --- process -------------------------------------------------------
    def _poll_process(self, now: float) -> List[NormalizedEvent]:
        procs = find_processes(("workbuddy",))
        evs: List[NormalizedEvent] = []
        was_online = bool(self._processes)
        is_online = bool(procs)
        self._processes = procs
        if is_online and not was_online:
            evs.append(make(
                EventType.AGENT_STARTED,
                "workbuddy:process:psutil",
                agent_id=AGENT_ID,
                payload={"executable": self._executable(), "pid_count": len(procs)},
            ))
            evs.append(make(
                EventType.AGENT_DISCOVERED,
                "workbuddy:process:psutil",
                agent_id=AGENT_ID,
                payload={"executable": self._executable(), "pid_count": len(procs)},
            ))
        elif was_online and not is_online:
            evs.append(make(
                EventType.AGENT_STOPPED,
                "workbuddy:process:psutil",
                agent_id=AGENT_ID,
                payload={"pid_count": 0},
            ))
        return evs

    def _executable(self) -> str:
        for p in self._processes:
            exe = str(p.get("exe") or "")
            if exe.lower().endswith("workbuddy.exe"):
                return exe
        return str(self._processes[0].get("exe") or "WorkBuddy") if self._processes else ""

    # --- sessions db ---------------------------------------------------
    FRESH_WINDOW_S = 120.0

    def _is_fresh(self, row: dict, now: float) -> bool:
        """A session counts as active only if it ticked recently. WorkBuddy
        leaves stale rows marked 'working' forever (ms timestamps)."""
        ts = int(row.get("updated_at") or row.get("last_activity_at") or 0)
        if ts > 10_000_000_000_000:      # ms → s
            ts /= 1000.0
        return ts > 0 and (now - ts) <= self.FRESH_WINDOW_S

    def _poll_sessions(self, now: float) -> List[NormalizedEvent]:
        if not self.db_path.exists():
            return []
        evs: List[NormalizedEvent] = []
        try:
            con = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True,
                                  timeout=1.0)
            con.row_factory = sqlite3.Row
            rows = [dict(r) for r in con.execute(
                "SELECT id, cwd, title, status, created_at, updated_at, "
                "last_activity_at, model FROM sessions")]
            con.close()
        except Exception as exc:
            self._last_error = f"sessions-db: {exc}"
            return []

        # pick the session to follow: the most recently *fresh* working one.
        # Stale rows stay "working" forever in the DB, so without this gate
        # every old session would demand its own pet (§52 false positives).
        fresh = [r for r in rows if (r.get("status") or "") == "working"
                 and self._is_fresh(r, now)]
        if fresh:
            self.focus_session = max(
                fresh, key=lambda r: int(r.get("last_activity_at") or
                                          r.get("updated_at") or 0))["id"]
        elif self.focus_session not in {r["id"] for r in rows}:
            self.focus_session = None

        active_ids = set()
        for r in rows:
            sid = r["id"]
            active_ids.add(sid)
            prev = self._session_state.get(sid)
            title_hash = safety.title_hash(r.get("title") or "")
            cwd = r.get("cwd") or ""
            rec = {"status": r["status"], "cwd": cwd, "title_hash": title_hash,
                   "model": r.get("model") or "", "updated_at": r.get("updated_at") or 0}
            if prev is None:
                evs.append(make(
                    EventType.SESSION_STARTED,
                    "workbuddy:db:sessions",
                    agent_id=AGENT_ID,
                    session_id=sid,
                    workspace_id=cwd,
                    payload={"title_hash": title_hash, "model": rec["model"],
                             "status": r["status"]},
                ))
                if r["status"] == "working" and sid == self.focus_session:
                    evs.append(make(
                        EventType.TASK_DETECTED,
                        "workbuddy:db:sessions",
                        agent_id=AGENT_ID,
                        session_id=sid,
                        workspace_id=cwd,
                        payload={"title_hash": title_hash},
                    ))
            else:
                if prev.get("status") != r["status"] and r["status"] in (
                        "completed", "archived"):
                    evs.append(make(
                        EventType.SESSION_ENDED,
                        "workbuddy:db:sessions",
                        agent_id=AGENT_ID,
                        session_id=sid,
                        workspace_id=cwd,
                        payload={"status": r["status"]},
                    ))
            self._session_state[sid] = rec

        for sid in list(self._session_state):
            if sid not in active_ids:
                self._session_state.pop(sid, None)
        self._active_ids = active_ids
        return evs

    # --- sdk log tail --------------------------------------------------
    def _candidate_log_dirs(self) -> List[Path]:
        """Scan the actual dated directories — WorkBuddy names them by *local*
        date on this machine, so deriving candidates from UTC silently finds
        nothing (discovered empirically, §13 'do not assume paths')."""
        if not self.logs_dir.exists():
            return []
        dated = []
        try:
            for d in self.logs_dir.iterdir():
                if not d.is_dir():
                    continue
                name = d.name
                if len(name) == 10 and name[4] == "-" and name[7] == "-" and \
                        name.replace("-", "").isdigit():
                    dated.append(d)
        except Exception:
            return []
        out: List[Path] = []
        for d in sorted(dated, key=lambda p: p.name)[-3:]:
            p = d / "sdk" / "conversations"
            if p.is_dir():
                out.append(p)
        return out

    def _refresh_focus(self) -> None:
        """Follow whichever working session is actually writing logs right now.

        Using the DB's last_activity_at is not enough: several sessions can be
        'working' simultaneously, and the one the user is looking at is the one
        whose event stream is moving.
        """
        working = {sid for sid, v in self._session_state.items()
                   if v.get("status") == "working"}
        best: Optional[Tuple[str, float]] = None
        for d in self._candidate_log_dirs():
            try:
                names = os.listdir(d)
            except Exception:
                continue
            for fn in names:
                if not fn.endswith(".log"):
                    continue
                sid = fn[:-4]
                if working and sid not in working:
                    continue
                try:
                    mt = (d / fn).stat().st_mtime
                except Exception:
                    continue
                if best is None or mt > best[1]:
                    best = (sid, mt)
        if best:
            self.focus_session = best[0]

    def _target_sessions(self) -> Set[str]:
        """Which sessions we actually follow (§52: don't attribute everything)."""
        active = getattr(self, "_active_ids", set()) or set()
        if self.focus == "latest":
            return {self.focus_session} if self.focus_session else set()
        return active

    def _tail_logs(self, now: float) -> List[NormalizedEvent]:
        evs: List[NormalizedEvent] = []
        targets = self._target_sessions()
        if not targets:
            return evs
        for d in self._candidate_log_dirs():
            try:
                names = os.listdir(d)
            except Exception:
                continue
            for fn in names:
                if not fn.endswith(".log"):
                    continue
                sid = fn[:-4]
                if sid not in targets:
                    continue
                fp = d / fn
                tailer = self._tailers.get(sid)
                if tailer is None or tailer.path != fp:
                    tailer = LogTailer(fp, start_at_end=not self.tail_from_start)
                    self._tailers[sid] = tailer
                try:
                    for line in tailer.read_new():
                        ev = self._parse_line(line, sid)
                        if ev:
                            evs.append(ev)
                except Exception as exc:
                    self._last_error = f"logtail:{sid}: {exc}"
        # NOTE: tailers are kept (not destroyed) when a session loses focus —
        # rebuilding one would restart at EOF and silently drop everything
        # written while it was unfocused.
        if len(self._tailers) > 12:
            for sid in list(self._tailers)[:-8]:
                self._tailers.pop(sid, None)
        return evs

    def _parse_line(self, line: str, sid: str) -> Optional[NormalizedEvent]:
        parts = line.split(" ", 2)
        if len(parts) < 3:
            return None
        _ts, kind, blob = parts
        if not blob.startswith("{"):
            return None
        try:
            obj = json.loads(blob)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None

        if kind == "state-machine:transition":
            return self._from_transition(obj, sid)
        if kind == "event-machine:dispatch":
            return self._from_dispatch(obj, sid)
        if kind == "resource-effect:failed":
            return make(
                EventType.ERROR_DETECTED,
                "workbuddy:sdk-log:resource-effect:failed",
                agent_id=AGENT_ID, session_id=sid,
                confidence=0.85,
                payload={"type": obj.get("type"),
                         "error": safety.truncate(str(obj.get("error", "")), 80)},
            )
        if kind == "runtime.applyStopReason":
            if obj.get("hasFatalError") or obj.get("hasTurnError"):
                return make(
                    EventType.TASK_FAILED,
                    "workbuddy:sdk-log:runtime.applyStopReason",
                    agent_id=AGENT_ID, session_id=sid,
                    payload={"stop_reason": obj.get("stopReason")},
                )
        return None

    def _from_transition(self, obj: Dict[str, object], sid: str) -> Optional[NormalizedEvent]:
        inp = obj.get("input")
        frm = obj.get("from")
        to = obj.get("to")
        if obj.get("valid") is False:
            return None

        if inp == "PHASE_PLANNING" and to == "planning":
            if self._last_state.get(sid) == "planning":
                return None
            self._last_state[sid] = "planning"
            return make(EventType.PLANNING,
                        "workbuddy:sdk-log:state-machine:transition",
                        agent_id=AGENT_ID, session_id=sid,
                        payload={"from": frm, "to": to, "input": inp})

        if inp == "PHASE_WORKING" and to == "working":
            if self._last_state.get(sid) == "working":
                return None
            self._last_state[sid] = "working"
            return make(EventType.THINKING,
                        "workbuddy:sdk-log:state-machine:transition",
                        agent_id=AGENT_ID, session_id=sid,
                        confidence=0.95,
                        payload={"from": frm, "to": to, "input": inp})

        if inp in ("PHASE_IDLE", "PHASE_WAITING") and to == "idle":
            if self._last_state.get(sid) == "idle":
                return None
            self._last_state[sid] = "idle"
            return None  # completion is signalled by TURN_COMPLETED, not idle

        et = TRANSITION_MAP.get(str(inp))
        if et is None:
            return None
        if et is EventType.TASK_COMPLETED and to not in (None, "idle"):
            return None
        self._last_state[sid] = "idle" if et is EventType.TASK_COMPLETED else "working"
        return make(et, "workbuddy:sdk-log:state-machine:transition",
                    agent_id=AGENT_ID, session_id=sid,
                    payload={"from": frm, "to": to, "input": inp})

    def _from_dispatch(self, obj: Dict[str, object], sid: str) -> Optional[NormalizedEvent]:
        inp = obj.get("input")
        et = DISPATCH_MAP.get(str(inp))
        if et is None:
            return None
        now = time.time()
        # tool_call bursts: at most one COMMAND_STARTED per session per 1.5s
        if et is EventType.COMMAND_STARTED:
            last = self._cmd_last_emit.get(sid, 0.0)
            if now - last < 1.5:
                return None
            self._cmd_last_emit[sid] = now
        if et is EventType.COMMAND_OUTPUT:
            last = self._cmd_last_emit.get("out:" + sid, 0.0)
            if now - last < 0.8:
                return None
            self._cmd_last_emit["out:" + sid] = now
        return make(et, f"workbuddy:sdk-log:event-machine:dispatch:{inp}",
                    agent_id=AGENT_ID, session_id=sid, confidence=0.95,
                    payload={"request_id": str(obj.get("requestId", ""))[:16]})

    # --- changes index -------------------------------------------------
    def _poll_changes(self, now: float) -> List[NormalizedEvent]:
        if not self.changes_dir.exists():
            return []
        evs: List[NormalizedEvent] = []
        targets = self._target_sessions()
        try:
            names = [n for n in os.listdir(self.changes_dir) if n.endswith(".json")]
        except Exception:
            return []
        for n in names:
            sid = n[:-5]
            if sid not in targets:
                continue
            fp = self.changes_dir / n
            try:
                data = json.loads(fp.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            changes = data.get("changes") or []
            workspace = self._session_state.get(sid, {}).get("cwd", "") or ""
            for ch in changes:
                rid = str(ch.get("requestId", ""))
                for f in (ch.get("files") or [])[:40]:
                    path = f.get("path") if isinstance(f, dict) else str(f)
                    if not path:
                        continue
                    key = (rid, str(path))
                    if key in self._seen_changes:
                        continue
                    self._seen_changes.add(key)
                    if safety.is_sensitive(str(path)):
                        continue
                    p = str(path).replace("\\", "/")
                    rel = safety.safe_relpath(p, workspace) \
                        if (workspace and os.path.isabs(p)) else p
                    evs.append(make(
                        EventType.FILE_CHANGED,
                        "workbuddy:changes-index",
                        agent_id=AGENT_ID, session_id=sid,
                        workspace_id=workspace,
                        payload={
                            "path": rel,
                            "additions": (f.get("additions") if isinstance(f, dict) else None),
                            "deletions": (f.get("deletions") if isinstance(f, dict) else None),
                        },
                    ))
                    if len(evs) >= MAX_FILE_EVENTS_PER_TICK:
                        return evs
        return evs

    # --- windows -------------------------------------------------------
    def _poll_windows(self, now: float) -> List[NormalizedEvent]:
        titles = visible_window_titles(("workbuddy",))
        hit = bool(titles)
        if hit != self._window_hit:
            self._window_hit = hit
            return [make(EventType.APP_CONTEXT_CHANGED,
                         "workbuddy:window:enumwindows",
                         agent_id=AGENT_ID,
                         payload={"visible": hit})]
        return []

    # ------------------------------------------------------------------
    def get_capabilities(self) -> Set[Capability]:
        caps: Set[Capability] = set()
        if self._processes:
            caps.add(Capability.PROCESS_DETECTION)
        if self._window_hit:
            caps.add(Capability.WINDOW_DETECTION)
        if any(self._tailers.values()):
            caps.add(Capability.LOG_OBSERVATION)
            caps.add(Capability.COMMAND_ACTIVITY)
            caps.add(Capability.TASK_LIFECYCLE)
        if getattr(self, "_active_ids", None):
            caps.add(Capability.FILE_ACTIVITY)
        return caps

    def health_check(self) -> AdapterStatus:
        caps = self.get_capabilities()
        if not caps:
            level = HealthLevel.OFFLINE
        elif {Capability.LOG_OBSERVATION, Capability.TASK_LIFECYCLE} <= caps:
            level = HealthLevel.FULL
        elif Capability.FILE_ACTIVITY in caps or Capability.TASK_LIFECYCLE in caps:
            level = HealthLevel.DEGRADED
        else:
            level = HealthLevel.MINIMAL
        sessions = [
            {"id": sid, "cwd": str(v.get("cwd", "")), "status": str(v.get("status", ""))}
            for sid, v in self._session_state.items()
        ]
        return AdapterStatus(
            level=level,
            capabilities=caps,
            detail=f"{len(self._processes)} process(es), {len(sessions)} session(s), "
                   f"{len(self._tailers)} log tailer(s)",
            last_error=self._last_error,
            sessions=sessions,
            process_count=len(self._processes),
            last_observation_at=time.time() if caps else 0.0,
        )

    def shutdown(self) -> None:
        self._tailers.clear()
