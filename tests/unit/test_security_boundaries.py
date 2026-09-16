"""Security tests (§2, §55).

AgentPet must be provably incapable of acting on the user's machine. These tests
grep the shipped package, so a future "temporary" shortcut fails the suite.
"""
import re
from pathlib import Path

import pytest

from agentpet.core.proc import SecurityViolation, run_readonly

PKG = Path(__file__).resolve().parents[2] / "agentpet"
ALLOWED_SUBPROCESS = {"core/proc.py"}

FORBIDDEN_PATTERNS = {
    "shell=True": re.compile(r"shell\s*=\s*True"),
    "os.system": re.compile(r"\bos\.system\s*\("),
    "os.popen": re.compile(r"\bos\.popen\s*\("),
    "subprocess": re.compile(r"\bsubprocess\.(run|Popen|call|check_output|check_call)\b"),
    "pty": re.compile(r"\bpty\.(spawn|fork)\b"),
    "key injection": re.compile(r"\b(SendInput|keybd_event|mouse_event)\b"),
    "process injection": re.compile(
        r"\b(WriteProcessMemory|CreateRemoteThread|VirtualAllocEx)\b"),
    "keyboard hook": re.compile(r"\b(SetWindowsHookEx)\b"),
}

MUTATING_GIT = re.compile(
    r"\b(add|commit|push|checkout|reset|clean|merge|rebase|stash|restore)\b")


def _py_files():
    return [p for p in PKG.rglob("*.py") if "__pycache__" not in str(p)]


def test_package_contains_no_dangerous_calls_outside_proc_gate():
    offenders = []
    for p in _py_files():
        rel = p.relative_to(PKG).as_posix()
        if rel in ALLOWED_SUBPROCESS:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for name, pat in FORBIDDEN_PATTERNS.items():
            for m in pat.finditer(text):
                line = text[:m.start()].count("\n") + 1
                offenders.append(f"{rel}:{line} {name}")
    assert not offenders, "dangerous call(s) found:\n" + "\n".join(offenders)


def test_proc_gate_rejects_non_git():
    with pytest.raises(SecurityViolation):
        run_readonly(["cmd", "/c", "echo hi"])


def test_proc_gate_rejects_mutating_git():
    for args in (["git", "commit", "-m", "x"], ["git", "add", "."],
                 ["git", "push"], ["git", "checkout", "-b", "x"],
                 ["git", "reset", "--hard"], ["git", "clean", "-fd"],
                 ["git", "status", "--porcelain", "--force"]):
        with pytest.raises(SecurityViolation):
            run_readonly(args)


def test_proc_gate_accepts_readonly_git():
    # must not raise the security gate (git may still be absent on the box)
    try:
        run_readonly(["git", "rev-parse", "HEAD"], cwd=str(PKG))
    except SecurityViolation:
        pytest.fail("read-only git was rejected")
    except Exception:
        pass  # git missing / not a repo: fine


def test_no_network_egress_imports():
    banned = {"requests", "urllib.request", "http.client", "socket",
              "httpx", "aiohttp"}
    offenders = []
    for p in _py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)",
                             text, re.M):
            mod = m.group(1).split(".")[0]
            if mod in banned:
                offenders.append(f"{p.relative_to(PKG).as_posix()} imports {mod}")
    assert not offenders, "network-capable import(s):\n" + "\n".join(offenders)
