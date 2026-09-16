# Agent Adapter Spec (§9, §75)

Every agent integration implements `agentpet/adapters/base.AgentAdapter` and is
registered in `agentpet/adapters/registry.AdapterRegistry`. The core never
branches on a specific agent id.

## Interface

```
identify() -> detection info
get_identity() -> id, display_name, version, confidence
get_processes() -> [{pid, ppid, name, exe, cpu, memory}]
get_sessions() -> [{session_id, workspace, status, title_hash}]
observe() -> List[NormalizedEvent]   # poll-driven, self-throttled
get_capabilities() -> {PROCESS_DETECTION, WINDOW_DETECTION, LOG_OBSERVATION,
                       FILE_ACTIVITY, COMMAND_ACTIVITY, TEST_ACTIVITY,
                       GIT_ACTIVITY, TASK_LIFECYCLE}
health_check() -> {status: online|degraded|offline, level: full|degraded|minimal,
                   last_error}
shutdown()
```

## Rules

1. Adapters only **read**. Any subprocess must go through
   `agentpet.core.proc.run_readonly` (git allow-list) — enforced by
   `tests/unit/test_security_boundaries.py`.
2. Every event carries `source`, `confidence` and `truth_level`.
3. Capabilities are honest: if the log has no command text, the adapter does
   not emit one (WorkBuddy case).
4. P1 presence adapters (`adapters/presence.py`) only detect processes for
   Codex / Claude Code / Cursor / DeepSeek Harness — deep observation lands in
   V0.2 per the roadmap.

## Adding an agent (V0.2+)

Create `agentpet/adapters/<agent>.py`, implement the interface, register it in
`all_p1_adapters()` (or a plugin manifest later). UI/behavior consume only the
normalized event stream, so nothing else changes.
