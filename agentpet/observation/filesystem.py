"""Workspace filesystem observer (§14 FileObserver, §56 safety).

Never watches C:\\ or the whole home directory. Only a workspace the agent itself
reported. Ignored directories and sensitive files are filtered out.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..core import safety

try:
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
    _HAS_WATCHDOG = True
except Exception:  # pragma: no cover
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore
    _HAS_WATCHDOG = False


class _Handler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, sink: "FileObserver") -> None:
        self.sink = sink

    def on_any_event(self, event):  # noqa: D102
        if getattr(event, "is_directory", False):
            return
        self.sink._record(getattr(event, "src_path", "") or
                          getattr(event, "dest_path", ""))


class FileObserver:
    """Debounced file activity inside one workspace."""

    def __init__(self, debounce: float = 1.2) -> None:
        self.debounce = debounce
        self.workspace: Optional[Path] = None
        self._pending: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._observer = None
        self._last_flush = 0.0
        self.backend = "none"

    # --- lifecycle -----------------------------------------------------
    def watch(self, workspace: str) -> bool:
        ws = Path(workspace)
        if not ws.is_dir():
            return False
        if self.workspace == ws:
            return True
        self.stop()
        self.workspace = ws
        if _HAS_WATCHDOG:
            try:
                obs = Observer()
                obs.schedule(_Handler(self), str(ws), recursive=True)
                obs.daemon = True
                obs.start()
                self._observer = obs
                self.backend = "watchdog"
                return True
            except Exception:
                self._observer = None
        self.backend = "none"
        return False

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.5)
            except Exception:
                pass
            self._observer = None

    # --- recording -----------------------------------------------------
    def _record(self, path: str) -> None:
        if not path:
            return
        if safety.is_sensitive(path) or safety.is_ignored_dir(path):
            return
        with self._lock:
            self._pending[path] = time.time()

    # --- output --------------------------------------------------------
    def flush(self, now: Optional[float] = None) -> List[str]:
        """Return paths whose debounce window elapsed. Called from the GUI tick."""
        now = now if now is not None else time.time()
        ready: List[str] = []
        with self._lock:
            for path, ts in list(self._pending.items()):
                if now - ts >= self.debounce:
                    ready.append(path)
                    self._pending.pop(path, None)
        return ready

    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def health(self) -> str:
        if self.workspace is None:
            return "no workspace"
        return f"{self.backend} @ {self.workspace}"
