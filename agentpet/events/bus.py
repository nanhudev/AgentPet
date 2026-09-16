"""Thread-safe normalized event bus.

Observers (worker threads) publish. The GUI thread drains on a timer. Dedup and
hysteresis live here so no consumer has to re-implement them.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict
from typing import Callable, Dict, Iterable, List, Optional

from .schema import NormalizedEvent


class EventBus:
    def __init__(self, maxlen: int = 2000, dedup_window: float = 0.4) -> None:
        self._q: "queue.Queue[NormalizedEvent]" = queue.Queue(maxsize=maxlen)
        self._subs: List[Callable[[NormalizedEvent], None]] = []
        self._lock = threading.Lock()
        self._recent: "OrderedDict[str, float]" = OrderedDict()
        self._dedup_window = dedup_window
        self._history: List[NormalizedEvent] = []
        self._history_max = 500
        self.dropped = 0
        self.deduped = 0
        self.emitted = 0

    # --- producer side -------------------------------------------------
    def publish(self, ev: NormalizedEvent) -> bool:
        """Publish unless an identical dedup_key arrived inside the window."""
        now = time.time()
        with self._lock:
            last = self._recent.get(ev.dedup_key)
            if last is not None and (now - last) < self._dedup_window:
                self.deduped += 1
                return False
            self._recent[ev.dedup_key] = now
            # bound the dedup map
            while len(self._recent) > 512:
                self._recent.popitem(last=False)
        try:
            self._q.put_nowait(ev)
            self.emitted += 1
            with self._lock:
                self._history.append(ev)
                if len(self._history) > self._history_max:
                    del self._history[:-self._history_max]
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def publish_many(self, events: Iterable[NormalizedEvent]) -> int:
        return sum(1 for e in events if self.publish(e))

    # --- consumer side -------------------------------------------------
    def drain(self, limit: int = 200) -> List[NormalizedEvent]:
        out: List[NormalizedEvent] = []
        while len(out) < limit:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        for sub in list(self._subs):
            for ev in out:
                try:
                    sub(ev)
                except Exception:  # a bad subscriber must not kill the drain loop
                    pass
        return out

    def subscribe(self, fn: Callable[[NormalizedEvent], None]) -> None:
        with self._lock:
            self._subs.append(fn)

    # --- introspection -------------------------------------------------
    def history(self, n: int = 100) -> List[NormalizedEvent]:
        with self._lock:
            return list(self._history[-n:])

    def pending(self) -> int:
        return self._q.qsize()

    def stats(self) -> Dict[str, int]:
        return {"emitted": self.emitted, "deduped": self.deduped,
                "dropped": self.dropped, "pending": self.pending()}
