"""Test-artifact observer — a *real* test signal instead of a guess.

The WorkBuddy SDK log proves that a command ran but never reveals its output, so
"tests passed/failed" cannot be read from it. What we *can* read truthfully is the
test runner's own cache on disk:

  <workspace>/.pytest_cache/v/cache/lastfailed   (exists / mtime changed -> failures)
  <workspace>/.pytest_cache/v/cache/nodeids      (mtime changed -> a run happened)

That is an OBSERVED filesystem fact, not an inference. JUnit XML (pytest --junitxml,
jest, vitest) is also parsed when present.
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MAX_AGE = 120.0   # only trust artifacts touched within this many seconds


class TestArtifactObserver:
    def __init__(self) -> None:
        self.workspace: Optional[Path] = None
        self._lastfailed_mtime: Optional[float] = None
        self._nodeids_mtime: Optional[float] = None
        self._junit_state: Dict[str, Tuple[float, int, int]] = {}
        self.last_error = ""

    def attach(self, workspace: str) -> None:
        self.workspace = Path(workspace) if workspace else None
        self._lastfailed_mtime = None
        self._nodeids_mtime = None
        self._junit_state.clear()

    def _mtime(self, p: Path) -> Optional[float]:
        try:
            return p.stat().st_mtime
        except Exception:
            return None

    def poll(self) -> List[Dict[str, object]]:
        """Return test facts observed on disk."""
        out: List[Dict[str, object]] = []
        if not self.workspace:
            return out
        try:
            import time as _t
            now = _t.time()

            lf = self.workspace / ".pytest_cache" / "v" / "cache" / "lastfailed"
            nid = self.workspace / ".pytest_cache" / "v" / "cache" / "nodeids"

            mt = self._mtime(nid)
            if mt is not None and (now - mt) <= _MAX_AGE:
                if self._nodeids_mtime is not None and mt != self._nodeids_mtime:
                    out.append({"kind": "test_run", "runner": "pytest",
                                "source": ".pytest_cache/v/cache/nodeids"})
                self._nodeids_mtime = mt

            mt = self._mtime(lf)
            if mt is not None and (now - mt) <= _MAX_AGE:
                if self._lastfailed_mtime is None or mt != self._lastfailed_mtime:
                    try:
                        data = json.loads(lf.read_text(encoding="utf-8",
                                                       errors="replace") or "{}")
                        count = len(data) if isinstance(data, dict) else 0
                    except Exception:
                        count = 0
                    out.append({"kind": "test_failed", "runner": "pytest",
                                "failed": count,
                                "source": ".pytest_cache/v/cache/lastfailed"})
                self._lastfailed_mtime = mt
            else:
                # no lastfailed file (or stale) while a run just happened => green
                pass
            out += self._junit(now)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        return out

    # --- junit xml -----------------------------------------------------
    def _junit_files(self) -> List[Path]:
        if not self.workspace:
            return []
        hits: List[Path] = []
        names = {"junit.xml", "pytest-junit.xml", "jest-junit.xml", "report.xml"}
        for dirpath, dirnames, filenames in os.walk(self.workspace):
            dirnames[:] = [d for d in dirnames if d not in
                           {"node_modules", ".git", "venv", ".venv", "dist", "build"}]
            for fn in filenames:
                if fn in names or (fn.endswith(".xml") and "junit" in fn.lower()):
                    hits.append(Path(dirpath) / fn)
            if len(hits) > 20:
                break
        return hits

    def _junit(self, now: float) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for fp in self._junit_files():
            mt = self._mtime(fp)
            if mt is None or (now - mt) > _MAX_AGE:
                continue
            try:
                root = ET.parse(fp).getroot()
            except Exception:
                continue
            suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
            failures = 0
            total = 0
            for s in suites:
                try:
                    total += int(s.attrib.get("tests", 0))
                    failures += int(s.attrib.get("failures", 0)) + \
                        int(s.attrib.get("errors", 0))
                except Exception:
                    pass
            key = str(fp)
            prev = self._junit_state.get(key)
            if prev is None or prev[0] != mt:
                self._junit_state[key] = (mt, total, failures)
                out.append({
                    "kind": "test_failed" if failures else "test_passed",
                    "runner": "junit-xml",
                    "total": total,
                    "failed": failures,
                    "source": os.path.relpath(fp, self.workspace),
                })
        return out
