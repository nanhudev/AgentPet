"""Read-only Git observer (§14 GitObserver, §27).

Allowed: rev-parse, log, status --porcelain, branch, show --stat.
Forbidden: add, commit, push, checkout, reset, clean, ... — enforced by
core.proc.run_readonly, which is the ONLY way this module can spawn a process.

Push detection: deliberately conservative. We can see that a remote-tracking ref
moved by reading .git/refs/remotes/*, but that is indistinguishable from a fetch.
So no PUSH event is emitted unless the remote ref moves *and* the local branch is
the same — and even then V0.1 leaves it disabled by default (see README
limitations). Better no push animation than a fake one.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from ..core.proc import git_lines

STATUS_CAP = 400


class GitObserver:
    def __init__(self, detect_push: bool = False) -> None:
        self.workspace: Optional[Path] = None
        self.is_repo = False
        self.last_head: Optional[str] = None
        self.last_status_count: Optional[int] = None
        self.last_branch: Optional[str] = None
        self.detect_push = detect_push
        self.last_error = ""

    def attach(self, workspace: str) -> bool:
        ws = Path(workspace)
        if not ws.is_dir():
            self.is_repo = False
            return False
        self.workspace = ws
        self.is_repo = bool(git_lines(["rev-parse", "--is-inside-work-tree"],
                                      cwd=str(ws)))
        self.last_head = None
        self.last_status_count = None
        return self.is_repo

    def _head(self) -> Optional[str]:
        if not self.workspace:
            return None
        lines = git_lines(["rev-parse", "HEAD"], cwd=str(self.workspace))
        return lines[0].strip() if lines else None

    def _branch(self) -> Optional[str]:
        if not self.workspace:
            return None
        lines = git_lines(["branch", "--show-current"], cwd=str(self.workspace))
        return lines[0].strip() if lines else None

    def _status_count(self) -> int:
        if not self.workspace:
            return 0
        lines = git_lines(["status", "--porcelain"], cwd=str(self.workspace))
        return len(lines[:STATUS_CAP])

    def _head_message(self) -> str:
        if not self.workspace:
            return ""
        lines = git_lines(["log", "-1", "--format=%s"], cwd=str(self.workspace))
        return lines[0].strip() if lines else ""

    def poll(self) -> List[Dict[str, object]]:
        """Return raw git observations; the adapter/fusion layer turns them into events."""
        out: List[Dict[str, object]] = []
        if not self.is_repo or not self.workspace:
            return out
        try:
            head = self._head()
            if head and self.last_head is not None and head != self.last_head:
                out.append({"kind": "commit", "sha": head[:9],
                            "message": self._head_message()[:120],
                            "repo": str(self.workspace)})
            if head:
                self.last_head = head

            branch = self._branch()
            if branch and branch != self.last_branch:
                if self.last_branch is not None:
                    out.append({"kind": "branch", "branch": branch,
                                "repo": str(self.workspace)})
                self.last_branch = branch

            count = self._status_count()
            if self.last_status_count is not None and count != self.last_status_count:
                out.append({"kind": "status", "changed_files": count,
                            "repo": str(self.workspace)})
            self.last_status_count = count
        except Exception as exc:  # never propagate
            self.last_error = f"{type(exc).__name__}: {exc}"
        return out

    # --- repository detection helper for the workspace ------------------
    @staticmethod
    def looks_like_repo(path: str) -> bool:
        return (Path(path) / ".git").exists()
