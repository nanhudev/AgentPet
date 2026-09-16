"""Local persistence (§36): settings, timeline, diagnostics. SQLite, tiny."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from ..core.paths import DB_FILE
from ..events.schema import NormalizedEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    agent_id TEXT,
    session_id TEXT,
    event_type TEXT,
    truth_level TEXT,
    confidence REAL,
    source TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_timeline_ts ON timeline(ts);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: Path = DB_FILE) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=3.0)
        self.con.executescript(SCHEMA)
        self.con.commit()

    def append(self, ev: NormalizedEvent) -> None:
        try:
            self.con.execute(
                "INSERT INTO timeline (ts, agent_id, session_id, event_type,"
                " truth_level, confidence, source, payload) VALUES (?,?,?,?,?,?,?,?)",
                (ev.timestamp, ev.agent_id, ev.session_id, ev.event_type.value,
                 ev.truth_level.value, ev.confidence, ev.source,
                 json.dumps(ev.payload, ensure_ascii=False)[:2000]))
        except Exception:
            pass

    def commit(self) -> None:
        try:
            self.con.commit()
        except Exception:
            pass

    def prune(self, days: int = 7) -> int:
        cutoff = time.time() - days * 86400
        try:
            cur = self.con.execute("DELETE FROM timeline WHERE ts < ?", (cutoff,))
            self.con.commit()
            return cur.rowcount or 0
        except Exception:
            return 0

    def recent(self, limit: int = 200) -> List[tuple]:
        try:
            return list(self.con.execute(
                "SELECT ts, agent_id, event_type, truth_level, confidence, source"
                " FROM timeline ORDER BY id DESC LIMIT ?", (limit,)))
        except Exception:
            return []

    def set_meta(self, k: str, v: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, v))
        self.con.commit()

    def get_meta(self, k: str, default: Optional[str] = None) -> Optional[str]:
        row = self.con.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return row[0] if row else default

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:
            pass
