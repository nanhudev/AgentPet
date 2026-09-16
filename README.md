# AgentPet — Organic Agent Companion (V0.1)

> **"AI 写代码的时候，宠物活了起来。"**
> A Windows desktop pet that *observes* your local coding agents (WorkBuddy first)
> and turns their real work into visible digital life. It never controls anything.

## What is AgentPet

AgentPet is a transparent desktop overlay with a small procedural mascot that
watches what your coding agent is *actually* doing — process tree, session DB,
SDK logs, file changes, git state, test artifacts — and reacts with theatrical
but truthful animations: it carries a **docked Mini Terminal & Mini Editor
(workbench)**, deploys them with a particle burst when work starts, grabs
output text as it streams, carries a box on real commits, celebrates when
tests pass, and goes back to its autonomous idle life when the world is quiet.

## Core principles

1. **Observer, not Controller** — zero development-control permissions (see
   `SECURITY_BOUNDARIES.md`; enforced by tests).
2. **True events, theatrical visuals** — every displayed fact has a source
   (`truth_level`: OBSERVED / INFERRED / VISUAL_ONLY). Unknowns are shown as
   abstract states, never fabricated.
3. **Pet first, dashboard second.**
4. **Local first, offline, zero LLM/API dependency.**
5. **WorkBuddy first** (P0), adapter-based for future agents.

## Features (V0.1)

- WorkBuddy detection: process tree (psutil), sessions DB, SDK conversation
  log tail (state-machine + event-machine events), window presence.
- File activity from WorkBuddy's changes-index (real paths, real +/- counts).
- Read-only git observation (HEAD/branch/status → commit animation only when
  a real commit is observed).
- Test signal from pytest artifacts (`.pytest_cache`).
- Pet workbench: Mini Terminal + Mini Editor docked to the pet with leash
  lines; deploy/retract with particle burst; output-grab text chips.
- Abstract streaming templates in the terminal (typewriter, VISUAL_ONLY).
- Multi-task staging: concurrent fresh sessions get their own pet (max 2);
  stale DB sessions are ignored (freshness gate); screens too small for a
  second station stay docked (no clutter).
- Event schema with confidence + truth level, event bus, fusion engine.
- Timeline persistence (SQLite, 7-day retention), Debug Panel, Privacy Mode,
  Simulation mode (clearly labelled, never used for acceptance), JSONL replay.

## Architecture

See `ARCHITECTURE.md` (with Mermaid diagram). Short version:

```
WorkBuddy → Adapter → Event Bus → World State → Behavior Engine → Overlay
                                    │                │
                                 Timeline        Workbench (docked panels)
```

## Supported agents

| Agent | Level | Signals |
|---|---|---|
| WorkBuddy | P0 — full | process, sessions, sdk-log, changes-index, window |
| Codex / Claude Code / Cursor / DeepSeek | P1 — presence-only | process detection via adapter registry |

## Privacy

- Watches only the WorkBuddy-observed workspace(s) it derives from the session
  DB — never the whole drive.
- Sensitive file filter blocks `.env*`, `*.pem`, `*.key`, `id_rsa*`,
  `credentials*`, `secrets*`, `token*`, `auth*`.
- Privacy Mode hides file names / commit messages / output text.
- Logs store summaries only. Nothing leaves the machine.

## Run

```powershell
D:\AgentPet\.venv\Scripts\python.exe apps\desktop\main.py
```

Deps: `PySide6 psutil watchdog` (pytest for development).
Right-click / double-click the pet → Settings, Debug panel, Simulate (demo),
Hide, Exit.

## Development

```powershell
D:\AgentPet\.venv\Scripts\python.exe -m pytest tests -q
```

- Adapter SDK: `agentpet/adapters/base.py` — implement `identify/observe/
  get_capabilities/health_check`; register in `registry.py`. No
  `if agent == "workbuddy"` outside the adapter.
- Event schema: `docs/EVENT_SCHEMA.md`.
- Truth rules: unknown command → `Running command...`; unknown file content →
  `Updating <name>...`; no push animation without an observed push.

## Known limitations (honest list)

- WorkBuddy's SDK log exposes **no command text and no stdout** (verified by
  probes), so the Mini Terminal streams *abstract* templates; real stdout is
  shown only if a future source provides it.
- changes-index is lazily flushed by WorkBuddy, so FILE_CHANGED can lag.
- Push detection is disabled by default (remote-ref movement is
  indistinguishable from a fetch).
- No packaging/installer yet (runs from source).

## Roadmap

- V0.2: Codex / Claude Code / Cursor / DeepSeek adapters (activity level)
- V0.3: themes, richer animation, multi-monitor staging refinement
- V0.4: optional local-LLM personality
- V0.5: third-party adapter plugins

## License

TBD (all rights reserved by the author until a LICENSE file is added).
