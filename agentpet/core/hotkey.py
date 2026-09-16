"""Global hotkeys (Windows) — a quick way to get the pet out of the way.

Only registers hotkeys; it never listens to keystrokes (§2: no input capture).
If registration fails for any reason the feature is silently disabled.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable, Dict, Optional

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class HotkeyManager:
    """Binds Ctrl+Alt+<key> combos to callables via a hidden message window."""

    def __init__(self, bindings: Dict[str, Callable[[], None]]) -> None:
        self.bindings = bindings
        self.enabled = False
        self._ids: Dict[int, Callable[[], None]] = {}
        self._widget = None
        self._filter = None
        if os.name != "nt" or not bindings:
            return
        try:
            from PySide6.QtCore import QAbstractNativeEventFilter
            from PySide6.QtWidgets import QWidget

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            w = QWidget()
            w.setWindowTitle("AgentPet hotkeys")
            hwnd = wintypes.HWND(int(w.winId()))

            mods = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
            ok = True
            for i, (key, fn) in enumerate(bindings.items(), start=1):
                vk = user32.VkKeyScanW(ord(key.upper())) & 0xFF
                if not user32.RegisterHotKey(hwnd, i, mods, vk):
                    ok = False
                    break
                self._ids[i] = fn
            if not ok or not self._ids:
                for i in list(self._ids):
                    user32.UnregisterHotKey(hwnd, i)
                self._ids = {}
                return

            class _Filter(QAbstractNativeEventFilter):
                def __init__(self, owner) -> None:
                    super().__init__()
                    self.owner = owner

                def nativeEventFilter(self, event_type, message):  # noqa: N802
                    try:
                        msg = ctypes.cast(int(message),
                                          ctypes.POINTER(MSG)).contents
                    except Exception:
                        return False, 0
                    if msg.message == WM_HOTKEY:
                        fn = self.owner._ids.get(int(msg.wParam))
                        if fn is not None:
                            try:
                                fn()
                            except Exception:
                                pass
                            return True, 0
                    return False, 0

            from PySide6.QtGui import QGuiApplication
            self._widget = w
            self._filter = _Filter(self)
            QGuiApplication.instance().installNativeEventFilter(self._filter)
            self.enabled = True
        except Exception:
            self.enabled = False

    @property
    def help(self) -> str:
        if not self.enabled:
            return ""
        keys = " / ".join(f"Ctrl+Alt+{k.upper()}" for k in self.bindings)
        return keys

    def shutdown(self) -> None:
        if not self.enabled:
            return
        try:
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            hwnd = wintypes.HWND(int(self._widget.winId()))
            for i in list(self._ids):
                user32.UnregisterHotKey(hwnd, i)
        except Exception:
            pass
