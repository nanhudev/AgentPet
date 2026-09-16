# Behavior Engine (§18-§21)

## Avoidance layer — "never be in the user's way" (§40)

Right-click / tray → **Avoid programs** (setting `avoid_mode`):

| mode | behaviour |
|------|-----------|
| `auto` (default) | dodge + dim + behind |
| `dodge` | while idle, walk to the nearest x not covered by an app window or another pet's open workbench |
| `behind` | while a maximised / ≥92 %-coverage app holds the foreground, drop always-on-top so the pet sits *behind* the app |
| `off` | always on top, never move |

Guarantees:

- **dim** — a docked panel covering ≥25 % of any visible window fades to
  `panel_dim` (default 0.35) until the overlap clears.
- **pinned** — after the user drags the pet, dodge is suppressed for 25 s.
- **multi-monitor** — only windows on the pet's own screen count.
- **degradation** — dodge search: bench width → pet width → tight gap; if the
  band is fully occupied the pet holds still (dim/behind still apply).
- **mini mode** — pet only, the workbench never deploys.
- Window geometry is read-only `EnumWindows`/`GetWindowRect`
  (`observation/winrect.py`); AgentPet never moves/resizes/focuses another
  app's window. Hotkeys: `Ctrl+Alt+P` hide/show, `Ctrl+Alt+M` mini mode.
- Panels auto-scale to narrow/portrait screens (`panel_scale`, §39) so the
  docked bench always fits.

## Station model (Workbench)

Work activity no longer teleports the pet around the screen. Events route to
a pet; the pet **deploys its docked workbench where it stands** (a reposition
hop only if the panels would leave the screen) and stays at its station:

- `TASK_STARTED/DETECTED` → notice → deploy bench
- `FILE_CHANGED` → face editor, grab-file chip (debounced 1.2 s)
- `COMMAND_STARTED` → face terminal, prompt line + abstract stream
- `COMMAND_OUTPUT` → grab-output chips; real text replaces stream for 6 s
- `TEST_STARTED/PASSED/FAILED` → testing / success / confused at station
- `GIT_COMMIT` → box + "Commit detected <sha>" above the pet
- `TASK_COMPLETED` → celebrate → bench retracts after 3.5 s
- quiet > 20 s → retract bench, resume autonomous idle (walk/sit/look/sleep)

## Session→pet routing (multi-task)

- unknown session → primary pet if free
- primary busy with another fresh session → claim a free pet, spawn up to
  `MAX_PETS = 2`
- station conflict avoidance: a second pet deploys only if a full second
  station fits ≥ 920 px away; otherwise it stays docked and reacts with
  bubbles/gestures only (screens must not get cluttered)

## Priorities

P0 critical (errors, task completion) interrupts everything; P1 active work;
P2 navigation; P3 weighted-random idle shaped by personality. Interrupts go
through the pet FSM (TRANSITIONS map + wake path); debounces: file 1.2 s,
command-start 1.5 s, dwell per state.
