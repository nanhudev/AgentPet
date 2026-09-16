"""Read-only window geometry — the data behind "stay out of the way".

Security note (§2): this only *reads* public window rectangles through
EnumWindows / GetWindowRect. No hooks, no message interception, no input
capture, no window manipulation. AgentPet never moves, resizes, focuses or
closes another application's window.

The desktop shell itself (Progman / WorkerW / Shell_TrayWnd) is filtered out,
otherwise "the desktop is a full-screen window" would make every avoidance
decision meaningless.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

ShellRect = Tuple[float, float, float, float]   # left, top, right, bottom

_IGNORED_CLASSES = {
    "progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
    "dv2windowhost", "windows.ui.core.corewindow", "applicationframewindow",
    "toastnotificationwindow", "shelldlgdefdummy",
}

_WS_MAXIMIZE = 0x01000000
_GWL_STYLE = -16
_DWMWA_CLOAKED = 14


@dataclass(frozen=True)
class WinInfo:
    rect: ShellRect
    maximized: bool = False

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


def _load_user32():
    if os.name != "nt":
        return None
    try:
        return ctypes.windll.user32  # type: ignore[attr-defined]
    except Exception:
        return None


_user32 = _load_user32()
EnumWindowsProc = (ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                   if _user32 is not None else None)


def _is_cloaked(hwnd) -> bool:
    """UWP/virtual-desktop windows report themselves visible while hidden."""
    try:
        dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    except Exception:
        return False
    try:
        val = wintypes.DWORD()
        hr = dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), wintypes.DWORD(_DWMWA_CLOAKED),
                                       ctypes.byref(val), ctypes.sizeof(val))
        return hr == 0 and val.value != 0
    except Exception:
        return False


def _class_name(hwnd) -> str:
    if _user32 is None:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value.lower()
    except Exception:
        return ""


def _rect_of(hwnd) -> Optional[ShellRect]:
    if _user32 is None:
        return None
    r = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    if r.right <= r.left or r.bottom <= r.top:
        return None
    return (float(r.left), float(r.top), float(r.right), float(r.bottom))


def _accept(hwnd, self_pid: int) -> bool:
    if _user32 is None:
        return False
    try:
        if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return False
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self_pid:
            return False                      # our own overlay / dialogs
        cls = _class_name(hwnd)
        if cls in _IGNORED_CLASSES:
            return False
        return not _is_cloaked(hwnd)
    except Exception:
        return False


def visible_windows(self_pid: Optional[int] = None,
                    min_size: int = 180) -> List[WinInfo]:
    """Rectangles of real, visible application windows (excl. shell + AgentPet)."""
    if _user32 is None or EnumWindowsProc is None:
        return []
    if self_pid is None:
        self_pid = os.getpid()
    out: List[WinInfo] = []

    def cb(hwnd, lparam):
        try:
            if not _accept(hwnd, self_pid):
                return True
            rect = _rect_of(hwnd)
            if rect is None:
                return True
            if (rect[2] - rect[0]) < min_size or (rect[3] - rect[1]) < min_size:
                return True                    # tray popups, tooltips, …
            style = _user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
            out.append(WinInfo(rect, bool(style & _WS_MAXIMIZE)))
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(EnumWindowsProc(cb), 0)
    except Exception:
        return []
    return out


def foreground_window(self_pid: Optional[int] = None) -> Optional[WinInfo]:
    """The window the user is actually working in right now."""
    if _user32 is None:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        if not _accept(hwnd, self_pid if self_pid is not None else os.getpid()):
            return None
        rect = _rect_of(hwnd)
        if rect is None:
            return None
        style = _user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        return WinInfo(rect, bool(style & _WS_MAXIMIZE))
    except Exception:
        return None


def screen_coverage(win: WinInfo, bounds: ShellRect) -> float:
    """How much of a screen/monitor rectangle a window covers (0..1)."""
    l, t, r, b = win.rect
    bl, bt, br, bb = bounds
    iw = max(0.0, min(r, br) - max(l, bl))
    ih = max(0.0, min(b, bb) - max(t, bt))
    area = max(1.0, (br - bl) * (bb - bt))
    return (iw * ih) / area
