# ADR-001: Desktop Stack Selection

- **Status:** Accepted
- **Date:** 2026-09-16
- **Deciders:** AgentPet core (DeepSeek V4.1 role = Core Engineer, Hunyuan 4 role = Reviewer)
- **Scope:** V0.1

## Decision

AgentPet V0.1 is built with **PySide6 (Qt 6) + Python 3.13**, single process, on Windows.

```
PySide6 (frameless translucent overlay, QPainter-rendered pet)
        + Python runtime (adapters, observers, behavior engine, persistence)
        + watchdog (filesystem) / psutil (process) / git.exe subprocess (read-only)
```

No Rust, no Node, no Electron, no Tauri, no browser engine, no cloud, no LLM API.

## Why PySide6 and not Tauri

The master prompt states a preference for `Tauri + web frontend + Rust/Python sidecar`
*if it can be implemented stably*. It was evaluated against this machine and rejected
for V0.1 for concrete, machine-specific reasons — not for speed of typing:

| Criterion | Tauri 2 + Web + Python sidecar | PySide6 |
|---|---|---|
| Toolchain present on this machine | **No.** No Rust/MSVC toolchain verified; adding one = large install on C: (user forbids C: use) | Python 3.13.12 present, venv created on D: |
| Transparent click-through overlay | Needs `window-shadows` / `tao` + Windows WS_EX_LAYERED workarounds | First-class: `Qt.FramelessWindowHint`, `WA_TranslucentBackground`, `WS_EX_TRANSPARENT` via `ctypes` |
| Multi-monitor + DPI | Manual per-webview handling | `QGuiApplication.screens()`, `devicePixelRatio()` built in |
| Sidecar complexity | IPC boundary between Rust/Web/Python = extra failure surface | Single process, direct function calls; simpler = fewer P0 bugs |
| Idle CPU | WebView compositor wakes on animation; harder to keep <2% | Full control of the repaint loop; can idle at 0 repaints |
| Packaging | Rust build + NSIS, slow iteration | PyInstaller one-folder, fast iteration |
| WorkBuddy observation | Same Python code either way | Same code, zero IPC |

The single strongest argument: **the entire observability layer for WorkBuddy is
Python-shaped** (sqlite read, JSONL tailing, Windows process walk, watchdog, git
subprocess). Putting a Rust/WebView in front of it buys no new capability and adds
a second language, an IPC protocol, and a build chain we cannot install on D: cleanly.

## Why not Electron

- Ships a full Chromium (~150-250 MB resident) — violates the "< 200-300 MB" and
  "idle CPU < 2%" performance goals of §37.
- Transparent click-through on Windows requires `setIgnoreMouseEvents` plus
  constant re-application on focus changes; known to flicker.
- Conflicts conceptually with the product: AgentPet must feel *lighter* than the
  agent it observes.

## Why not Tkinter

- No real compositing/alpha canvas; animations are repaint-hacks that tear.
- No per-pixel transparency, no smooth easing, no DPI-aware scene graph.
- Would fail the "视觉表现好 / 精致" requirement in §6 and §65.

## Architecture consequences

1. Rendering uses `QPainter` on a `QWidget` with `WA_TranslucentBackground`, not
   QGraphicsScene, to keep the paint path cheap and predictable.
2. A single `QTimer` drives the world tick at 30 FPS when animating and **stops
   entirely** when the world is static (idle CPU target).
3. Observers run in `QThread` workers and never touch widgets directly; they push
   into a thread-safe event queue drained on the GUI thread.
4. The renderer is asset-independent (§30): behavior emits `AnimationKey`, the
   renderer maps keys to draw routines. Swapping in sprites later does not touch
   behavior code.

## Revisit triggers

Move to Tauri/Rust only if a future phase needs any of:
- per-pixel shader effects / WebGL particles,
- a Live2D or Rive runtime that only ships a web/wasm build,
- shipping a <20 MB installer where a Python runtime is unacceptable.

None of these are in V0.1 scope.
