"""The ONLY sanctioned way for AgentPet to start another process.

Security boundary §2 / §55: AgentPet never executes anything on behalf of a task.
The single exception is reading Git state, which is inherently a subprocess and is
restricted here to a hard allow-list of read-only subcommands.

Nothing else in the package may call subprocess.* — tests/unit/
test_security_boundaries.py enforces that.
"""
from __future__ import annotations

import subprocess
from typing import List, Optional, Sequence

GIT_READONLY_SUBCOMMANDS = {
    "rev-parse", "log", "status", "branch", "show", "diff", "config", "remote",
}

# Arguments that would mutate repository state — rejected on sight.
FORBIDDEN_TOKENS = {
    "add", "commit", "push", "pull", "checkout", "switch", "reset", "clean",
    "merge", "rebase", "cherry-pick", "restore", "stash", "tag", "apply",
    "am", "gc", "prune", "fetch", "init", "mv", "rm", "--force", "-f",
    "worktree", "submodule", "filter-branch",
}


class SecurityViolation(RuntimeError):
    pass


def _find_git() -> Optional[str]:
    import shutil
    return shutil.which("git")


def run_readonly(args: Sequence[str], cwd: Optional[str] = None,
                 timeout: float = 8.0) -> subprocess.CompletedProcess:
    """Run an allow-listed read-only git command. Raises on anything else."""
    if not args:
        raise SecurityViolation("empty command")
    if args[0] != "git":
        raise SecurityViolation(f"only 'git' may be executed, got {args[0]!r}")

    sub = next((a for a in args[1:] if not a.startswith("-")), "")
    if sub not in GIT_READONLY_SUBCOMMANDS:
        raise SecurityViolation(f"git subcommand not allow-listed: {sub!r}")

    for token in args[1:]:
        if token in FORBIDDEN_TOKENS:
            raise SecurityViolation(f"mutating git argument rejected: {token!r}")

    exe = _find_git()
    if not exe:
        raise SecurityViolation("git executable not found")

    return subprocess.run(
        [exe, *args[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,          # never a shell
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def git_lines(args: Sequence[str], cwd: Optional[str] = None,
              timeout: float = 8.0) -> List[str]:
    try:
        cp = run_readonly(["git", *args], cwd=cwd, timeout=timeout)
    except Exception:
        return []
    if cp.returncode != 0:
        return []
    return [ln for ln in cp.stdout.splitlines() if ln.strip()]
