# AgentPet — Product Goal

## One sentence

AgentPet makes a local coding agent's invisible work **visible as a living creature** on
your desktop — without ever touching your code.

## The feeling we are shipping

> "My AI agent actually lives inside my computer."

Not a dashboard. Not a widget. A creature that notices, walks over, watches, reacts,
gets bored, sleeps, and celebrates.

## What it is

- A Windows desktop **observer** that detects local coding agents (V0.1: WorkBuddy).
- A **digital pet** that reacts to what those agents really do, in real time.
- A **transparent overlay world** with a pet, a Mini Terminal, a Mini Editor, Git
  animations and a task bubble.

## What it is not

- Not a coding agent.
- Not a controller. It never runs a command, never edits a file, never commits.
- Not a cloud product. V0.1 runs fully offline with zero API dependency (§3).
- Not a screenshot toy. It is driven by real events or it shows nothing.

## The core principle: Truthful Theatre

> Visuals may dramatize. Events may not fabricate facts.

| Allowed (theatre) | Forbidden (fabrication) |
|---|---|
| Pretend to pull out a Mini Terminal | Print a command string we did not observe |
| Pretend to type on a keyboard | Show a file path we did not observe |
| Turn a real commit into a "carrying boxes" animation | Show a commit hash that does not exist |
| Get frustrated when tests fail | Claim "tests passed" when we only inferred activity |
| Celebrate a detected task completion | Invent a task completion |

When the fact is unknown, the UI shows an abstract state:
`Working...`, `Running command...`, `Updating files...`, `Testing...`.

## V0.1 scope: WorkBuddy First

- **P0:** WorkBuddy — detection, observation, normalization, behavior, animation,
  timeline, real task completion.
- **P1 (architecture-ready only):** Codex, Claude Code, Cursor, DeepSeek Harness.
  Adapter interface + process-presence detection. No deep activity detection.
- **P2 (later):** Hermes, others.

## Success criteria (the only ones that count)

1. A real WorkBuddy session runs a real coding task; AgentPet observes it and the
   observed timeline matches what actually happened.
2. The pet walks between real interaction areas (terminal / editor) rather than
   standing in a corner looping an idle animation.
3. Nothing in the UI is a fabricated development fact (Truth Audit, §54).
4. Idle: CPU < 2%, memory < 300 MB (§37).
5. Zero development-control capability (§2, verified by security test §55).

## Explicit non-goals for V0.1

- Multi-agent deep observation.
- Any LLM/API-driven personality.
- Sound, themes, plugin ecosystem, user accounts, telemetry, cloud sync, billing.
