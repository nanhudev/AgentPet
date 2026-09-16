"""Public top-level window title observation (§14 WindowObserver).

Only EnumWindows + GetWindowText on visible top-level windows. No hooks, no
message interception, no keystroke capture.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterable, List

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
_user32 = ctypes.windll.user32  # type: ignore[attr-defined]


def _enum_titles() -> List[str]:
    titles: List[str] = []

    def cb(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value:
            titles.append(buf.value)
        return True

    _user32.EnumWindows(EnumWindowsProc(cb), 0)
    return titles


def visible_window_titles(needles: Iterable[str] = ()) -> List[str]:
    try:
        titles = _enum_titles()
    except Exception:
        return []
    if not needles:
        return titles
    low = [n.lower() for n in needles]
    return [t for t in titles if any(n in t.lower() for n in low)]
