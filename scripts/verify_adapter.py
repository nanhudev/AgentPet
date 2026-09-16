"""Verify the WorkBuddy adapter against the REAL, currently running session.

Read-only. Prints every normalized event it can observe, with source + truth
level, so we can see exactly what is OBSERVED vs what we cannot know.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentpet.adapters.workbuddy import WorkBuddyAdapter  # noqa: E402
from agentpet.events.schema import EventType  # noqa: E402

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
FROM_START = "--from-start" in sys.argv


def main() -> int:
    a = WorkBuddyAdapter(tail_from_start=FROM_START)
    print("identify():", a.identify())
    procs = a.get_processes()
    print(f"processes: {len(procs)}")
    for p in procs[:6]:
        print(f"  pid={p['pid']} {p['name']}  {str(p['cmdline'])[:90]}")

    seen = Counter()
    end = time.time() + SECONDS
    while time.time() < end:
        for ev in a.observe():
            seen[ev.event_type] += 1
            print(f"  {time.strftime('%H:%M:%S', time.localtime(ev.timestamp))} "
                  f"{ev.short()}  {str(ev.payload)[:70]}")
        time.sleep(0.5)

    print("\n--- summary ---")
    for et, n in seen.most_common():
        print(f"  {et.value:<24} {n}")
    hc = a.health_check()
    print("\nhealth:", hc.level.value, "|", hc.detail)
    print("capabilities:", sorted(c.value for c in hc.capabilities))
    print("sessions:")
    for s in hc.sessions:
        print("   ", s["id"][:8], s["status"], s["cwd"])
    if hc.last_error:
        print("last_error:", hc.last_error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
