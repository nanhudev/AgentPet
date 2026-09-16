# Test Spec (§43-§48)

## Levels

1. **Unit** (`tests/unit/`) — event schema & dedup, confidence, FSM
   transitions + interrupts, behavior priorities & debounces, safety filters
   (sensitive paths, no-exec boundaries), replay loader, bus.
2. **Integration** (`tests/integration/`) — WorkBuddy adapter against a
   synthetic-but-real-shaped root (sessions DB, SDK log, changes-index):
   lifecycle parsing, real file paths, no-command-text truth rule, capability
   reporting, sensitive-path suppression.
3. **Replay/E2E** — recorded JSONL sessions replayed through the real bus
   (`agentpet/sim/replay.py`); simulation mode (`sim/simulator.py`) is a
   labelled developer tool and never used for acceptance.
4. **Real WorkBuddy acceptance** — see
   `docs/testing/REAL_WORKBUDDY_ACCEPTANCE.md`.

## Security invariants (always asserted)

- No `exec/eval/subprocess/shell=True/Command::new` in product code outside
  `core/proc.py`'s git allow-list.
- Watcher scope limited to authorized workspaces; ignore patterns for
  `node_modules`, `.git/objects`, caches, venvs.

## Current status

53 passed (unit + integration). Visible QA screenshots under
`docs/testing/screenshots/`.
