# GitHub Reference Research

Research phase (PHASE 0). Purpose: know the landscape, borrow **ideas**, copy **no code**
unless the licence is permissive *and* verified. Every row states the licence as observed
on the project page; where a project's licence is ambiguous it is marked
`DO-NOT-COPY` and used for architecture reading only.

Scope of search: desktop pets / companions, transparent overlay technique, agent
activity observation, filesystem watchers.

---

## 1. Desktop pet / companion projects

| # | Project | URL | Licence (observed) | Architecture | Useful idea | Unsuitable idea | Referenced | Code copied | Licence risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Shimeji-ee (Kilkakon fork, JDK25 port by DalekCraft2) | https://github.com/DalekCraft2/Shimeji-Desktop | `other` (README has a dedicated *Licensing* section; upstream Shimeji is by Yuki Yamada / Group Finity, 2009; a Chinese mirror fork declares GPLv3) | Java/Swing, one transparent `JWindow` per mascot, XML-defined `actions.xml` + `behaviors.xml`, image-set driven | **Data-driven behavior**: actions and transitions live in config, not in code — directly motivates our asset-independent `AnimationKey` mapping (§30). Multi-mascot manager. Per-mascot tray menu. | Image-set-per-folder sprite model; XML config sprawl; no notion of observing an external program | Yes (architecture) | **No** | Medium if code were copied — therefore **nothing is copied** |
| 2 | Shimeji (original, Yuki Yamada / Group Finity) | http://www.group-finity.com/Shimeji/ (archived: https://web.archive.org/web/20160901003054/http://www.group-finity.com/Shimeji/) | Historical/freeware, not a permissive OSS licence | Java 6, per-mascot window, gravity + window-edge walking | The canonical "pet interacts with real desktop geometry" idea: climb window borders, sit on taskbar | Single-sprite-per-state rigidity | Yes (concept) | **No** | n/a |
| 3 | my-shimeji (pedrozoalencar) | https://github.com/pedrozoalencar/my-shimeji | **MIT OR Apache-2.0** | Rust + GTK4 + `gtk4-layer-shell`, modules: `core/ ui/ physics/ ai/ gnome/` | Clean module split `physics` vs `ai` (behavior state machine) vs `ui`; explicit **multi-pet** support; documented *architectural decisions* file incl. sprite-vs-collision-box offset pitfall | Wayland/GNOME-only — not portable to the Windows target; heavy shell integration | Yes (module split + the documented "visual offset" pitfall) | **No** | Low (MIT/Apache) but not needed — we target Win32 |
| 4 | Shimeji (GPLv3 mirror fork) | https://github.com/a1098832322/shimeji | **GPL-3.0** | Maven/Java desktop pet with online update | Auto-update mechanism (out of scope for us) | GPL → viral if copied | Read only | **No** | **High if copied — avoided entirely** |

**Conclusion for AgentPet:** the *desktop-pet* genre gives us two durable ideas —
(1) behavior must be data-driven and asset-independent, (2) multi-pet must be designed
in from day one (`PetManager` + `PetInstance[]`, §21). Nothing from genre projects is
copied; AgentPet's mascot and renderer are written from scratch.

---

## 2. Overlay / transparency technique

| # | Project / tech | URL | Licence | Useful idea | Verdict |
|---|---|---|---|---|---|
| 5 | Tauri 2 | https://github.com/tauri-apps/tauri | MIT OR Apache-2.0 | Webview-based transparent windows, Rust core | **Evaluated, rejected for V0.1** — see ADR-001 (no Rust toolchain on this machine, C: install forbidden, IPC overhead for no capability gain) |
| 6 | Electron `setIgnoreMouseEvents` | https://www.electronjs.org/docs/latest/api/browser-window | MIT | Click-through toggling | Rejected: ships Chromium, violates §37 memory/CPU goals |
| 7 | Qt 6 (`Qt.FramelessWindowHint` + `WA_TranslucentBackground` + `WS_EX_TRANSPARENT` / `WS_EX_LAYERED`) | https://doc.qt.io/qt-6/ | LGPLv3 (PySide6) | Per-pixel alpha, layered windows, native DPI awareness, `QGuiApplication.screens()` for multi-monitor | **Chosen** — see ADR-001 |

## 3. Runtime dependencies (not vendored, installed via pip)

| Package | URL | Licence | Use in AgentPet | Code copied |
|---|---|---|---|---|
| PySide6 (Qt for Python) | https://wiki.qt.io/Qt_for_Python | LGPLv3 | Overlay window, painting, timers, tray | No (import only) |
| psutil | https://github.com/giampaolo/psutil | BSD-3-Clause | Read-only process enumeration, CPU sampling | No (import only) |
| watchdog | https://github.com/gorakhargosh/watchdog | Apache-2.0 (per repo LICENSE) | Native filesystem event watcher, debounced | No (import only) |
| pytest | https://github.com/pytest-dev/pytest | MIT | Unit / integration tests | No (dev only) |

`git` is invoked as the user's existing `git.exe` through `subprocess`, **read-only
subcommands only** (`rev-parse`, `log`, `status --porcelain`, `branch`, `show`). No
libgit2 / GitPython runtime dependency is added.

---

## 4. Observation-source research (WorkBuddy-specific, done on this machine)

This section is **primary research**, not literature. Findings from
`scripts/audit_env.py`, `scripts/probe_wb_surface.py`, `scripts/probe_wb2.py`,
`scripts/probe_wb3.py`, `scripts/probe_wb5.py` (all read-only):

| Artifact | Path (discovered dynamically, never hard-coded) | What it proves | Truth level |
|---|---|---|---|
| Process tree | `WorkBuddy.exe` + children running `cli\bin\codebuddy --session/--prompt/--print/--resume` | WorkBuddy is running; a *coding child process exists* | OBSERVED |
| Session DB | `~/.workbuddy/workbuddy.db` → table `sessions(id, cwd, title, status, created_at, updated_at, last_activity_at, model, mode)` | session identity, workspace path, task title, task lifecycle status (`working` / `completed` / `archived`) | OBSERVED |
| SDK conversation log | `~/.workbuddy/logs/<UTC-date>/sdk/conversations/<sessionId>.log` | Real-time event stream (see below) | OBSERVED |
| — `state-machine:transition` | `{from,to,input,declaredTo,valid}` with inputs `PROMPT_SENT`, `PHASE_PLANNING`, `PHASE_WORKING`, `PHASE_IDLE`, `PHASE_WAITING`, `TURN_COMPLETED`, `TURN_ERROR`, `PERMISSION_REQUESTED`, `PERMISSION_RESOLVED` | Task lifecycle and thought phase | OBSERVED (conf 1.00 direct structured log) |
| — `event-machine:dispatch` | `{input, requestId, messageId, output}` with inputs `tool_call`, `tool_call_update`, `terminal_output_chunk`, `terminal_update`, `usage_update`, `session_info_update`, `session_end` | A tool call happened; terminal output was produced. **The log deliberately contains no tool name or arguments** | OBSERVED for the *fact* of the call; **no command text is knowable** → Mini Terminal must show `Running command...` |
| — `resource-effect:failed` | `{type, error, requestId}` | An operation failed | OBSERVED |
| — `runtime.applyStopReason` | `{stopReason, hasFatalError, hasTurnError}` | Turn ended, possibly with error | OBSERVED |
| Change index | `~/.workbuddy/changes-index/<sessionId>.json` → `changes[].{files[], fileCount, additions, deletions, summary, createdAt, detailRef}` | **Real file paths** of files the agent changed, with +/- line counts | OBSERVED (real filenames) |
| Change detail | `~/.workbuddy/changes-detail/<sessionId>/cd_*.json` | Per-change file records | OBSERVED |
| Audit log | `~/.workbuddy/audit-log/<date>.jsonl` | `sessionId`, `eventType` (`file-safety.*`), `commandPreview` | Security-relevant command activity only | OBSERVED (narrow) |
| Window titles | `EnumWindows` + `GetWindowText` (public top-level info only) | Whether WorkBuddy has a visible window | OBSERVED |

### Consequence for Truthful Theatre

Because the SDK log exposes *that* a tool ran but never *what* it ran, AgentPet V0.1
**cannot and must not** print a concrete command string. It renders
`Running command...` (§23). Filenames are the one concrete fact we do get — from
`changes-index` — so the Mini Editor shows real filenames and real +/- counts.

---

## 5. Not found / gaps

- No open-source project found that observes a *coding agent* and dramatises it as a
  desktop pet. That is the original contribution of AgentPet; nothing to copy.
- No public WorkBuddy adapter/observer SDK exists. The adapter in this repo is derived
  from direct observation of this machine's artifacts (§13: "do not assume paths").
