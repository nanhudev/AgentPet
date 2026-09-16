# WorkBuddy Adapter — implementation notes

All paths/structures below were **discovered by probing this machine**
(`scripts/probe_wb*.py`), not assumed.

## Observation sources (V0.1)

| Source | Path | Events | Truth |
|---|---|---|---|
| Process tree | psutil scan (`WorkBuddy.exe`, `codebuddy*` children, name/exe-anchored matching) | AGENT_STARTED / AGENT_DISCOVERED / AGENT_STOPPED | OBSERVED 1.0 |
| Sessions DB | `~/.workbuddy/workbuddy.db` `sessions(id, cwd, title, status, created_at, updated_at, last_activity_at, model)` — opened read-only URI | SESSION_STARTED / SESSION_ENDED / TASK_DETECTED | OBSERVED 1.0 |
| SDK conversation log | `~/.workbuddy/logs/<LOCAL-date>/sdk/conversations/<sid>.log` — incremental byte-offset tailer with rotation + truncation handling | TASK_STARTED / TASK_COMPLETED / TASK_FAILED / PLANNING / THINKING (state-machine:transition), COMMAND_STARTED / COMMAND_OUTPUT (event-machine:dispatch, debounced 1.5 s), ERROR_DETECTED (resource-effect:failed) | OBSERVED 0.95 |
| changes-index | `~/.workbuddy/changes-index/<sid>.json` → files with real paths + additions/deletions | FILE_CHANGED | OBSERVED 1.0 |
| Window | EnumWindows top-level titles (no hooks) | APP_CONTEXT_CHANGED | OBSERVED 1.0 |

## Key facts discovered

- Log directories are named by **local** date, not UTC.
- `state-machine:transition` inputs: `PROMPT_SENT`, `PHASE_PLANNING`,
  `PHASE_WORKING`, `TURN_COMPLETED`, `TURN_ERROR`.
- dispatch inputs: `tool_call`, `tool_call_update`, `terminal_output_chunk`,
  `terminal_update`, `session_info_update`, `usage_update` — **all counters,
  no command text, no stdout** (hence abstract streaming in the terminal).
- `updated_at`/`last_activity_at` are **ms**; stale rows keep `status=
  "working"` forever → freshness gate (120 s) before focus/TASK emission.
- changes-index flush is lazy — FILE_CHANGED may lag actual writes.

## Session focus & multi-session

The adapter follows the most recently *fresh* working session for log tailing
and changes-index; other fresh sessions still emit TASK events so the
behavior engine can stage a second pet for genuinely concurrent work.

## Capability levels

full: process + window + log + changes + sessions-db
degraded: process + sessions-db (log parsing failed)
minimal: process only
