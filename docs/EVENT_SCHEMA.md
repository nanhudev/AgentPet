# Event Schema

All agent activity is normalized into one strongly-typed event shape before anything
reaches the UI.

## 1. `NormalizedEvent`

| Field | Type | Notes |
|---|---|---|
| `event_id` | str (uuid4) | unique |
| `timestamp` | float | epoch seconds, local |
| `agent_id` | str | adapter id, e.g. `workbuddy` |
| `agent_type` | str | same as adapter id; future multi-instance may differ |
| `session_id` | str \| None | agent session, when knowable |
| `task_id` | str \| None | maps to `session_id` for WorkBuddy V0.1 |
| `workspace_id` | str \| None | normalized workspace path |
| `event_type` | `EventType` | see §3 |
| `confidence` | float 0..1 | see §2 |
| `source` | str | **machine-readable provenance**, e.g. `workbuddy:sdk-log:state-machine:transition` |
| `payload` | dict | event-specific, must be JSON-serializable |
| `truth_level` | `TruthLevel` | `OBSERVED` \| `INFERRED` \| `VISUAL_ONLY` |
| `dedup_key` | str | computed; used to collapse bursts |

## 2. Confidence ladder (§12)

| Value | Meaning |
|---|---|
| 1.00 | Direct structured record from the agent's own log/DB |
| 0.95 | Known WorkBuddy structured event with a verified mapping |
| 0.85 | Git state confirmation (HEAD changed, new commit exists) |
| 0.75 | Filesystem pattern inside a known agent workspace |
| 0.60 | Process hierarchy inference |
| 0.40 | Weak heuristic |

Every `INFERRED` event carries confidence `<= 0.75` by construction
(`events/schema.py` enforces this) — an inference may never claim near-certainty.

## 3. Event types (§11)

Lifecycle: `AGENT_DISCOVERED`, `AGENT_STARTED`, `AGENT_STOPPED`,
`SESSION_STARTED`, `SESSION_ENDED`,
`TASK_DETECTED`, `TASK_STARTED`, `TASK_PROGRESS`, `TASK_COMPLETED`, `TASK_FAILED`

Cognition: `THINKING`, `PLANNING`

Files: `READING_FILE`, `FILE_OPENED`, `FILE_CHANGED`, `FILE_CREATED`,
`FILE_DELETED`, `WRITING_FILE`

Commands: `COMMAND_STARTED`, `COMMAND_OUTPUT`, `COMMAND_COMPLETED`, `COMMAND_FAILED`

Tests: `TEST_STARTED`, `TEST_PROGRESS`, `TEST_PASSED`, `TEST_FAILED`

Debug: `DEBUGGING_STARTED`, `DEBUGGING_ENDED`

Git: `GIT_REPOSITORY_DETECTED`, `GIT_STATUS_CHANGED`, `GIT_COMMIT_DETECTED`,
`GIT_PUSH_DETECTED`

Misc: `APP_CONTEXT_CHANGED`, `ERROR_DETECTED`, `IDLE`, `ACTIVE`

## 4. Payload contract per event (V0.1, WorkBuddy)

| Event | Required payload keys | Source | Truth |
|---|---|---|---|
| `AGENT_DISCOVERED` | `executable`, `pid_count` | process observer | OBSERVED (1.00) |
| `SESSION_STARTED` | `session_id`, `cwd`, `title_hash`, `model` | `workbuddy.db:sessions` | OBSERVED (1.00) |
| `TASK_STARTED` | `session_id` | sdk log `PROMPT_SENT` | OBSERVED (1.00) |
| `TASK_COMPLETED` | `session_id` | sdk log `TURN_COMPLETED` + `to:idle` | OBSERVED (1.00) |
| `TASK_FAILED` | `session_id`, `reason_kind` | `TURN_ERROR` / `applyStopReason` | OBSERVED (1.00) |
| `PLANNING` | `session_id` | `PHASE_PLANNING` | OBSERVED (1.00) |
| `THINKING` | `session_id` | `PHASE_WORKING` | OBSERVED (0.95) |
| `COMMAND_STARTED` | `session_id` — **no command text** | sdk log `tool_call` | OBSERVED (0.95) |
| `COMMAND_OUTPUT` | `session_id`, `bytes` | `terminal_output_chunk` | OBSERVED (0.95) |
| `FILE_CHANGED` | `path`, `additions`, `deletions` | `changes-index` | OBSERVED (1.00) |
| `WRITING_FILE` | `path` | fusion: FILE_CHANGED + active | INFERRED (0.75) |
| `TEST_STARTED` / `TEST_PASSED` / `TEST_FAILED` | `session_id` | fusion of command output + heuristics | INFERRED (<=0.75) |
| `GIT_COMMIT_DETECTED` | `sha`, `message?`, `repo` | git `rev-parse`/`log` | OBSERVED (0.85) |
| `GIT_PUSH_DETECTED` | `repo`, `remote_ref` | only when genuinely observed | OBSERVED (>=0.85) |

### Deliberate gaps (documented, not hidden)

- **Command text is unknowable** from the WorkBuddy SDK log — it records that a tool
  call occurred but not its name or arguments. So `COMMAND_STARTED` carries no
  command string and the Mini Terminal renders `Running command...`.
- **Test results are inferred, never observed.** V0.1 marks them `INFERRED` and the
  UI labels them as such in the debug panel. A "tests passed" celebration is only
  triggered when the inferred confidence clears the configured threshold.
- **PUSH is only emitted when genuinely observed** (remote-tracking ref moved), which
  V0.1 usually cannot confirm — so normally no push animation appears. That is correct
  behaviour, not a missing feature.
