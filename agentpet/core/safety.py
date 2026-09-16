"""Sensitive-file filter and privacy helpers (§25, §33, §64).

Anything that would be rendered into the Mini Editor or a file-change event passes
through here first. When in doubt, block.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Iterable, List

SENSITIVE_GLOBS: List[str] = [
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.keystore",
    "id_rsa", "id_rsa.*", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.*", "secrets", "secrets.*",
    "token", "token.*", "tokens.*", "auth", "auth.*",
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".htpasswd",
    "*.secret", "*secret*.json", "*credential*",
]

SENSITIVE_DIR_PARTS = {".ssh", ".aws", ".gnupg", ".kube", "credentialmanager",
                       "secrets", ".docker"}

# Never watch these — prevents event storms (§56).
IGNORE_DIRS = {".git", "node_modules", "venv", ".venv", "dist", "build", "cache",
               "__pycache__", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
               "target", "bin", "obj", ".tox", ".gradle", "coverage"}


def _parts(path: str) -> Iterable[str]:
    return [p.lower() for p in Path(path).parts]


def is_sensitive(path: str) -> bool:
    """True if this path must never be shown or read by AgentPet."""
    try:
        p = Path(path)
        name = p.name.lower()
        for pat in SENSITIVE_GLOBS:
            if fnmatch.fnmatch(name, pat.lower()):
                return True
        for part in _parts(path):
            if part in SENSITIVE_DIR_PARTS:
                return True
        return False
    except Exception:
        return True  # unparseable -> treat as sensitive


def is_ignored_dir(path: str) -> bool:
    return any(part in IGNORE_DIRS for part in _parts(path))


def safe_relpath(path: str, workspace: str) -> str:
    """Workspace-relative display path, or '<outside workspace>'."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(workspace))
    except Exception:
        return "<outside workspace>"
    if rel.startswith(".."):
        return "<outside workspace>"
    return rel.replace("\\", "/")


def title_hash(text: str) -> str:
    """Non-reversible task identifier — never store the raw prompt (§28, §64)."""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:10]


def truncate(text: str, n: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


def redact(text: str, n: int = 80) -> str:
    """Preview for logs: structure yes, secrets no."""
    return truncate(text, n)
