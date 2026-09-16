"""Integration test: the WorkBuddy adapter against a synthetic-but-real-shaped
WorkBuddy root (same layout/format discovered on this machine).

This proves parsing and normalization. It does NOT replace the real acceptance
test (docs/testing/REAL_WORKBUDDY_ACCEPTANCE.md).
"""
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pytest

from agentpet.adapters.workbuddy import WorkBuddyAdapter
from agentpet.events.schema import EventType, TruthLevel

SID = "11111111-2222-3333-4444-555555555555"
CWD = "D:\\e2e-workspace"

LOG_LINES = [
    'lifecycle:created {"instanceId":"ci-1","state":"idle","transport":"local"}',
    'state-machine:transition {"from":"idle","to":"working","input":"PROMPT_SENT",'
    '"declaredTo":"working","valid":true,"actions":[]}',
    'state-machine:transition {"from":"working","to":"planning",'
    '"input":"PHASE_PLANNING","declaredTo":"planning","valid":true,"actions":[]}',
    'event-machine:dispatch {"input":"tool_call","instanceId":"ci-1",'
    '"requestId":"r1","output":{}}',
    'event-machine:dispatch {"input":"terminal_output_chunk","instanceId":"ci-1",'
    '"requestId":"r1","output":{}}',
    'resource-effect:failed {"type":"fs","error":"denied","requestId":"r1"}',
    'state-machine:transition {"from":"working","to":"idle",'
    '"input":"TURN_COMPLETED","declaredTo":"idle","valid":true,"actions":[]}',
]


def _build_root(tmp_path: Path) -> Path:
    root = tmp_path / ".workbuddy"
    date = datetime.now().strftime("%Y-%m-%d")
    conv = root / "logs" / date / "sdk" / "conversations"
    conv.mkdir(parents=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    (conv / f"{SID}.log").write_text(
        "\n".join(f"{ts} {ln}" for ln in LOG_LINES) + "\n", encoding="utf-8")

    db = root / "workbuddy.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE sessions (id TEXT, cwd TEXT, title TEXT, status TEXT,"
        " created_at INT, updated_at INT, last_activity_at INT, model TEXT)")
    con.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                (SID, CWD, "build a calculator", "working",
                 int(time.time() * 1000), int(time.time() * 1000),
                 int(time.time() * 1000), "hy4-preview-f"))
    con.commit()
    con.close()

    idx = root / "changes-index"
    idx.mkdir()
    (idx / f"{SID}.json").write_text(json.dumps({
        "version": 2,
        "changes": [{
            "id": f"{SID},r1", "conversationId": SID, "requestId": "r1",
            "summary": "2 files changed", "fileCount": 2,
            "additions": 30, "deletions": 0,
            "createdAt": int(time.time() * 1000),
            "files": [
                {"path": "calculator.py", "additions": 24, "deletions": 0},
                {"path": "tests/test_calculator.py", "additions": 6,
                 "deletions": 0},
            ],
        }],
    }), encoding="utf-8")
    return root


@pytest.fixture()
def adapter(tmp_path):
    root = _build_root(tmp_path)
    a = WorkBuddyAdapter(root=root, tail_from_start=True)
    a.get_processes = lambda: [{"pid": 1, "name": "WorkBuddy.exe",
                                "exe": "D:\\workbuddy\\WorkBuddy.exe"}]
    a._processes = a.get_processes()
    for k in a._next_at:
        a._next_at[k] = 0.0
    return a


def test_observes_task_lifecycle(adapter):
    evs = adapter.observe()
    kinds = {e.event_type for e in evs}
    assert EventType.TASK_STARTED in kinds
    assert EventType.PLANNING in kinds
    assert EventType.TASK_COMPLETED in kinds
    assert EventType.COMMAND_STARTED in kinds
    assert EventType.ERROR_DETECTED in kinds


def test_observes_session_and_workspace(adapter):
    evs = adapter.observe()
    sess = [e for e in evs if e.event_type is EventType.SESSION_STARTED]
    assert sess and sess[0].workspace_id == CWD
    assert sess[0].session_id == SID


def test_file_changes_carry_real_paths(adapter):
    evs = adapter.observe()
    files = [e for e in evs if e.event_type is EventType.FILE_CHANGED]
    paths = {e.payload["path"] for e in files}
    assert "calculator.py" in paths
    assert all(e.truth_level is TruthLevel.OBSERVED for e in files)
    assert all(e.source == "workbuddy:changes-index" for e in files)


def test_command_started_has_no_command_text(adapter):
    """Truthful Theatre: the SDK log never exposes the command, so we must not
    invent one."""
    evs = adapter.observe()
    cmds = [e for e in evs if e.event_type is EventType.COMMAND_STARTED]
    assert cmds
    for e in cmds:
        assert "command" not in e.payload


def test_every_event_has_a_source(adapter):
    evs = adapter.observe()
    assert evs
    for e in evs:
        assert e.source and ":" in e.source


def test_focus_follows_active_session(adapter):
    adapter.observe()
    assert adapter.focus_session == SID


def test_health_reports_capabilities(adapter):
    adapter.observe()
    hc = adapter.health_check()
    caps = {c.value for c in hc.capabilities}
    assert "TASK_LIFECYCLE" in caps
    assert "COMMAND_ACTIVITY" in caps
    assert hc.level.value in ("full", "degraded")


def test_sensitive_paths_are_never_emitted(tmp_path):
    root = _build_root(tmp_path)
    idx = root / "changes-index"
    data = json.loads((idx / f"{SID}.json").read_text(encoding="utf-8"))
    data["changes"][0]["files"].append({"path": ".env", "additions": 1,
                                        "deletions": 0})
    (idx / f"{SID}.json").write_text(json.dumps(data), encoding="utf-8")
    a = WorkBuddyAdapter(root=root, tail_from_start=False)
    a._processes = [{"pid": 1, "name": "WorkBuddy.exe", "exe": "x"}]
    for k in a._next_at:
        a._next_at[k] = 0.0
    a.observe()
    evs = a.observe()
    paths = {e.payload.get("path") for e in evs
             if e.event_type is EventType.FILE_CHANGED}
    assert ".env" not in paths
