"""Incremental log tailer with rotation, size caps and backpressure (§14)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

MAX_CHUNK = 512 * 1024          # never read more than 512 KB in one tick
MAX_LINE = 8000                 # truncate pathological lines


class LogTailer:
    """Reads only bytes appended since the last call.

    Handles: rotation (file shrank), replacement (inode changed), truncation,
    and unreadable/transient states — all without raising.
    """

    def __init__(self, path: Path, start_at_end: bool = True) -> None:
        self.path = Path(path)
        self.offset = 0
        self.inode: Optional[int] = None
        self._partial = ""
        if start_at_end:
            try:
                st = self.path.stat()
                self.offset = st.st_size
                self.inode = getattr(st, "st_ino", None)
            except Exception:
                self.offset = 0

    def _stat(self):
        try:
            return self.path.stat()
        except Exception:
            return None

    def read_new(self) -> List[str]:
        st = self._stat()
        if st is None:
            return []
        ino = getattr(st, "st_ino", None)
        if ino is not None and self.inode is not None and ino != self.inode:
            self.offset = 0            # file replaced
        self.inode = ino
        if st.st_size < self.offset:
            self.offset = 0            # rotated / truncated
        if st.st_size == self.offset:
            return []
        to_read = min(st.st_size - self.offset, MAX_CHUNK)
        self.offset += to_read
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset - to_read)
                raw = f.read(to_read)
                self.offset = f.tell()          # byte offset, comparable to st_size
        except Exception:
            return []
        combined = self._partial + raw.decode("utf-8", "replace")
        lines = combined.split("\n")
        self._partial = lines.pop() if not combined.endswith("\n") else ""
        return [ln[:MAX_LINE] for ln in lines if ln.strip()]
