"""Unit tests: sensitive-file filter (§25) and log hygiene (§64)."""
import os

from agentpet.core import safety


def test_env_files_are_sensitive():
    for p in [".env", ".env.local", "secrets.json", "id_rsa", "token.txt",
              "credentials.json", "auth.yaml", ".npmrc", "server.key",
              ".ssh/config", "aws/credentials"]:
        assert safety.is_sensitive(p), p


def test_normal_source_files_are_not_sensitive():
    for p in ["calculator.py", "tests/test_calculator.py", "README.md",
              "src/app/main.ts", "docs/architecture.md"]:
        assert not safety.is_sensitive(p), p


def test_ignore_dirs():
    assert safety.is_ignored_dir(os.path.join("proj", "node_modules", "x.js"))
    assert safety.is_ignored_dir(os.path.join("proj", ".git", "objects"))
    assert not safety.is_ignored_dir(os.path.join("proj", "src", "main.py"))


def test_title_hash_is_stable_and_short():
    h1 = safety.title_hash("build a calculator")
    h2 = safety.title_hash("build a calculator")
    assert h1 == h2 and len(h1) == 10
    assert h1 != safety.title_hash("other")


def test_safe_relpath():
    assert safety.safe_relpath("/w/src/a.py", "/w") == "src/a.py"
    assert safety.safe_relpath("/other/a.py", "/w") == "<outside workspace>"
