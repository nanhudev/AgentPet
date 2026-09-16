# Real WorkBuddy Acceptance Test — Results (§49-§51)

- **Date:** 2026-09-16, 01:20–01:25 (UTC+8)
- **Host:** Windows, WorkBuddy at `D:\workbuddy`, AgentPet at `D:\AgentPet`
- **App under test:** `apps/desktop/main.py` (live adapter → bus → world →
  behavior → overlay), no simulation.

## Real task executed in sandbox

Workspace `D:\AgentPet\agentpet-e2e-workspace` (git repo). The live WorkBuddy
session (this agent) actually performed:

1. `Write calculator.py` (with an intentional divide bug) + `Write
   test_calculator.py` (4 tests)
2. `pytest` → **1 failed** (test_divide: 20 != 5)
3. `Edit calculator.py` → fix divide (+ ZeroDivisionError guard)
4. `pytest` → **4 passed**
5. `Write README.md`, `git add + commit` → real commit
   **`8dfc87d8` "feat: add calculator with divide fix after failed test"**

## Observed timeline (from AgentPet's own SQLite timeline)

62 events recorded during the window, all truth_level OBSERVED, including:

- `AGENT_STARTED / AGENT_DISCOVERED` (process:psutil) — on launch
- `SESSION_STARTED ×11` + `TASK_DETECTED` (workbuddy.db sessions)
- `THINKING / PLANNING` (sdk-log state-machine:transition, conf 0.95)
- `COMMAND_STARTED` burst pattern matching each real tool call — timestamps
  align with the actual pytest/Write/Edit/git invocations above
- `APP_CONTEXT_CHANGED` (window observer)

## Round-2 UX revision (found during acceptance)

- ✅ Round 1 proved detection; it also exposed that the pet *ran across the
  screen* for every event and that panels floated disconnected. Fixed by the
  **Workbench redesign** (pet-docked panels, deploy burst, stay-at-station).
- ✅ Freshness gate added to the sessions poll: stale rows stay "working"
  forever in WorkBuddy's DB; without the gate every old session demanded its
  own pet (false-positive staging, §52).

## False negatives (§53, recorded honestly)

| Missed signal | Root cause (verified) | Status |
|---|---|---|
| FILE_CHANGED during round 1 | WorkBuddy writes changes-index lazily; e2e repo was outside the observed session workspace | Round 1 run: recorded; product watches the session workspace by design |
| COMMAND text / stdout | SDK log `event-machine:dispatch` carries counters only — no text (probe_wb4) | Terminal streams abstract templates; real text shown when a source exists |
| TEST_FAILED/PASSED in round 1 | pytest cache observer attached only to session workspace | Round 2 fixture attaches observers to repos the agent touches (read-only) |
| GIT_COMMIT in round 1 | git observer bound to session workspace | Same fix as above; commit animation verified with real `8dfc87d8` in round 2 manual run |

## Screenshots

`docs/testing/screenshots/*_overlay_raw.png` — raw overlay-layer captures
(transparent background, overlay content only; no desktop content is committed
for privacy). Coverage: idle, sim QA frames, workbench deploy sequence,
streaming terminal, two-pet staging, avoidance dodge/dim, final panel scaling.

## Round-3 / Round-4 UX revisions (user-reported)

| Report | Fix | Evidence |
|---|---|---|
| Too many pets, screen cluttered | Pet staging limited (`MAX_PETS`), freshness gate 120s, only concurrent *active* sessions stage a second pet | `07_avoid*`, `08_avoid2*` show 1–2 pets |
| Terminal showed only `Running command…` + text overflow | `renderer/stream.py` abstract streaming templates (typewriter + flow dots + caret), elide to panel width | `04_stream*` frames |
| Wanted "real-feeling" but cheap | **No copying of real agent text** — templates are `VISUAL_ONLY`; real text renders only when a source actually provides it (Truthful Theatre) | timeline truth counters below |
| Window遮挡 (display priority too high) | `observation/winrect.py` (read-only `EnumWindows`) + `behavior/avoid.py` — `auto / dodge / dim / behind / off`; window is draggable, scalable (pet + panel scale), closable, park + hotkeys (`Ctrl+Alt+P/M`) | `07_avoid*`, `08_avoid2*`, `09_final*` |
| Vertical 864×1488 monitor overflow | Workbench `panel_scale = (width-80)/912` clamped 0.55–1.15, `BASE_W/BASE_H` + `set_scale()` | `09_final*` fits fully on screen |

## 12-hour soak run (stability)

- Window: 2026-09-16 01:43 → 13:35 (UTC+8), **12h 14m**, live adapter, no
  simulation, unattended.
- **1,134 events** recorded in that window:
  `OBSERVED 1021 / VISUAL_ONLY 92 / INFERRED 21`.
- Top types: `COMMAND_STARTED 348`, `PLANNING 273`, `THINKING 251`,
  `SESSION_STARTED 89`, `COMMAND_OUTPUT 25`, `FILE_CHANGED 21`,
  `TEST_STARTED/PASSED/FAILED 33`, `GIT_COMMIT_DETECTED 6`.
- Process exited cleanly: **no traceback** in `data/acceptance_run2.txt`
  (0 bytes of stderr), **no leftover `python.exe`** holding the overlay,
  DB `data/agentpet.db` 425 KB (no unbounded growth), idle CPU ≈ 0%.
- Long-run observation: pet count stays at 1 for single active session; no
  layout drift or off-screen placement after 12h of continuous rescan.

## Result

**PASS (PARTIAL for file-path latency)** — detection, session/task lifecycle,
command activity, and pet behavior verified against a real WorkBuddy session;
12h unattended soak clean; known gaps are recorded above with root causes, not
hidden.
