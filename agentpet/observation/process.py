"""Read-only process observation (§14 ProcessObserver).

Public process information only: pid, ppid, name, executable, command line,
CPU times. No memory reading, no injection, no termination.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - fallback keeps AgentPet alive
    psutil = None  # type: ignore

_CACHE: Dict[int, float] = {}


def _match(pinfo: Dict[str, object], needles: Tuple[str, ...]) -> bool:
    """Match on process *identity* (name / executable), not on any path that
    merely mentions the agent. Matching on cmdline would sweep in every node.exe
    launched from a folder that happens to contain 'workbuddy'.
    """
    name = str(pinfo.get("name") or "").lower()
    exe = str(pinfo.get("exe") or "").lower()
    cmd = str(pinfo.get("cmdline") or "").lower()
    for n in needles:
        n = n.lower()
        if n in name or n in exe:
            return True
        # a child launched as the agent binary itself keeps it in argv[0]
        if cmd.startswith(f"{n}.exe") or f"\\{n}.exe" in cmd.split(" ")[0]:
            return True
    return False


def find_processes(needles: Iterable[str]) -> List[Dict[str, object]]:
    """Return public info for processes matching any needle."""
    needles = tuple(needles)
    out: List[Dict[str, object]] = []
    if psutil is None:
        return out
    for p in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline"]):
        try:
            info = p.info  # type: ignore[attr-defined]
        except Exception:
            continue
        rec = {
            "pid": info.get("pid"),
            "ppid": info.get("ppid"),
            "name": info.get("name") or "",
            "exe": info.get("exe") or "",
            "cmdline": " ".join(info.get("cmdline") or [])[:400],
        }
        if _match(rec, needles):
            out.append(rec)
    return out


def process_alive(pid: int) -> bool:
    if psutil is None:
        return False
    try:
        return psutil.pid_exists(pid)
    except Exception:
        return False


def cpu_percent(pid: Optional[int] = None, interval: float = 0.0) -> float:
    """CPU sample. When pid is None returns our own process usage."""
    if psutil is None:
        return 0.0
    try:
        if pid is None:
            import os
            pid = os.getpid()
        p = psutil.Process(pid)
        return float(p.cpu_percent(interval=interval))
    except Exception:
        return 0.0


def memory_mb(pid: Optional[int] = None) -> float:
    if psutil is None:
        return 0.0
    try:
        import os
        p = psutil.Process(pid if pid is not None else os.getpid())
        return p.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0
