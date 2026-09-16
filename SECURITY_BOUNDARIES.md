# Security Boundaries

AgentPet is an **Observer, not a Controller**. This document is normative: if code
contradicts it, the code is wrong.

## 1. Hard prohibitions (never implemented, never "temporarily" added)

AgentPet must never:

- execute shell commands (`cmd`, `powershell`, `bash`, `sh`) on behalf of a task;
- execute `subprocess` with `shell=True`;
- create/delete/modify any file outside its own data directory (`D:\AgentPet\data`);
- modify, write or delete any file inside a user project or workspace;
- simulate keyboard or mouse input (`SendInput`, `keybd_event`, `mouse_event`);
- automate the UI of another program to perform development actions;
- control, drive, script or inject into WorkBuddy / Codex / Claude / Cursor / any agent;
- call any coding agent's CLI or API to make it do work;
- run `git add / commit / push / reset / checkout / clean / branch / merge / rebase`;
- install dependencies;
- close or open other applications to accomplish a task;
- inject DLLs, read or write another process's memory;
- install global keyboard hooks or keyloggers;
- read passwords, tokens, API keys, or credential files;
- upload source code or any user data anywhere (there is no network egress path).

## 2. Permitted observations

- Enumerate public process information (name, PID, parent PID, command line of
  processes the user already owns).
- Check whether a process exists; sample CPU/memory of our own and of agents.
- Read **public top-level window titles** via `EnumWindows` / `GetWindowText`.
  No hooks, no message interception, no keystroke capture.
- Watch filesystem changes **only inside workspaces the agent itself reports**
  (from `sessions.cwd`) — never a default watch on `C:\` or the whole home directory.
- Read **read-only** Git state: `rev-parse`, `log`, `status --porcelain`,
  `branch --show-current`, `show --stat`. Never a mutating subcommand.
- Incrementally tail log files the agent itself produces under the user's own
  `~/.workbuddy` directory, with rotation, dedup, backpressure and size caps.
- Maintain AgentPet's own local database and logs under `D:\AgentPet\data`.
- Draw anything it likes on its own overlay, as long as drawn facts have a source.

## 3. Enforcement in code

1. **No spawn helper exists.** The codebase contains exactly one way to run a
   subprocess: `agentpet/core/proc.py::run_readonly()`, which takes a fixed
   allow-list of executables (`git`) and a fixed allow-list of subcommands, and
   rejects anything else. It is constructed with `shell=False`, no shell.
2. **A test guards it.** `tests/unit/test_security_boundaries.py` greps the shipped
   package for `shell=True`, `os.system`, `subprocess.Popen/...` outside
   `core/proc.py`, `ctypes` input-injection APIs, and mutating git subcommands,
   and fails the suite if any appear outside the sanctioned module.
3. **Sensitive file filter** (`agentpet/core/safety.py`) blocks Mini Editor and
   file-change rendering for: `.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`,
   `credentials*`, `secrets*`, `token*`, `auth*`, `*.pfx`, `*.p12`,
   `.npmrc`, `.git-credentials`, `*.keystore`, and anything under `.ssh/`.
4. **Privacy mode** (§33) hides filenames, commands, commit messages and task text,
   showing only abstract activity.
5. **Log hygiene** (§64): AgentPet's own logs never dump file contents, prompts,
   tokens or full stdout. Only counts, kinds, hashes and truncated previews.

## 4. Degradation, not escalation

If an observer fails, AgentPet degrades its declared capability and keeps running:

```
full  -> process + session + log + files + git
degraded -> process + session + files
minimal  -> process only
offline  -> nothing detected
```

It never retries in a tight loop, never escalates privileges, and never attempts a
workaround that would cross a boundary above.

## 5. Truth discipline as a security property

Fabricated facts are treated as a security defect, not a cosmetic one. An event with
no source must be either (a) marked `VISUAL_ONLY` and rendered abstractly, or
(b) not rendered at all. The Truth Audit (§54) is run before delivery.
