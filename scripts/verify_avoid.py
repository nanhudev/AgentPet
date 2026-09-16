"""Verify the "stay out of the way" layer against the real desktop."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from agentpet.core.config import Settings
from agentpet.behavior import avoid
from agentpet.behavior.pet import PetManager, Personality, PetState
from agentpet.observation import winrect
from agentpet.renderer.overlay import OverlayWindow


def main() -> int:
    app = QApplication(sys.argv)
    s = Settings.load()
    mgr = PetManager()
    ov = OverlayWindow(s, mgr)
    mgr.spawn(1, ov.home, Personality())

    print("=== visible windows (shell + AgentPet excluded) ===")
    wins = winrect.visible_windows()
    for w in wins[:10]:
        r = w.rect
        print(f"  {int(r[0]):>5},{int(r[1]):>5} -> {int(r[2]):>5},{int(r[3]):>5}"
              f"  ({int(w.width)}x{int(w.height)}) maximized={w.maximized}")
    print(f"  total={len(wins)}")

    fg = winrect.foreground_window()
    print(f"foreground: {fg.rect if fg else None} maximized={fg.maximized if fg else None}")
    print(f"screens covered>=92%: "
          f"{[winrect.screen_coverage(fg, (g.left(), g.top(), g.right(), g.bottom())) for g in (sc.availableGeometry() for sc in QGuiApplication.screens())] if fg else []}")
    print(f"avoid_mode={ov.avoid_mode} behind={ov.behind} topmost={ov._topmost}")

    # --- dodge: drop the pet right on top of a window and let it move --------
    pet = mgr.primary
    bounds = ov.bounds_tuple()
    band_t, band_b = avoid.band_for(ov.ground_y)
    spans = avoid.occupied_spans([w.rect for w in wins], band_t, band_b, bounds)
    print(f"occupied spans on the pet's band: {[(int(a), int(b)) for a, b in spans]}")

    if spans:
        mid = (spans[0][0] + spans[0][1]) / 2
        pet.x = mid
        pet.y = ov.ground_y
        pet.state = PetState.IDLE
        pet.pinned_until = 0.0
        print(f"placed pet inside a window at x={pet.x:.0f}")
        ov._dodge_cd = 0.0
        for _ in range(20):
            ov._avoidance(0.05)
            pet.update(0.05, bounds)
            app.processEvents()
        print(f"after dodge: x={pet.x:.0f} dest={pet.destination} "
              f"conflicts={avoid.conflicts(pet.x, spans, 60.0)}")
    # --- dodge with a synthetic gap (proves the walk-away works) --------
    pet.state = PetState.IDLE
    pet.pinned_until = 0.0
    ov._wins = [winrect.WinInfo((250.0, 400.0, 600.0, 1200.0))]
    ov._dodge_cd = 0.0
    pet.x = 420.0
    ov._avoidance(0.05)
    for _ in range(30):
        pet.update(0.05, bounds)
    print(f"synthetic window 250-600: pet at x={pet.x:.0f} "
          f"(start 420) conflicts="
          f"{avoid.conflicts(pet.x, avoid.occupied_spans([(250.,400.,600.,1200.)], band_t, band_b, bounds), 60.0)}")
    print(f"panel_scale={ov.panel_scale:.2f} bench_half={ov.bench_half_width(pet):.0f} "
          f"screen_width={bounds[2]-bounds[0]:.0f}")

    # --- dim: force a panel to overlap a window ------------------------------
    if ov._wins:
        wb = ov.workbench_for(pet)
        from PySide6.QtCore import QPointF
        wb.terminal.bounds.moveTopLeft(
            QPointF(ov._wins[0].rect[0] + 30, ov._wins[0].rect[1] + 30))
        wb.deploy_t = 1.0
        wb.state = "open"
        print(f"target dim with panel over a window: {ov._target_dim():.2f}")
        ov.avoid_mode = "off"
        print(f"target dim with avoidance off      : {ov._target_dim():.2f}")

    # --- behind: simulate a maximised foreground app --------------------------
    ov.avoid_mode = "auto"
    ov._fg = winrect.WinInfo((0.0, 0.0, 3000.0, 2000.0), True)
    ov._apply_window_state()
    print(f"maximised foreground -> behind={ov.behind} topmost={ov._topmost}")
    ov._fg = None
    ov._apply_window_state()
    print(f"no foreground        -> behind={ov.behind} topmost={ov._topmost}")
    return 0


if __name__ == "__main__":
    from PySide6.QtGui import QGuiApplication
    raise SystemExit(main())
