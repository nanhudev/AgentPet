"""AgentPet PHASE 0 - third probe: exact parse targets for the WorkBuddy adapter."""
import json
import os
import re
import sqlite3
from pathlib import Path

WB = Path.home() / ".workbuddy"
CUR = "f8f3c175-6830-4516-b719-fdd048d5979e"
res = {}

# 1. current session row
try:
    con = sqlite3.connect(f"file:{(WB / 'workbuddy.db').as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM sessions")]
    res["sessions_table"] = [
        {k: (v[:80] if isinstance(v, str) else v)
         for k, v in r.items()
         if k in ("id", "cwd", "title", "status", "created_at", "updated_at",
                  "last_activity_at", "mode", "model", "source_mode", "permission_mode")}
        for r in rows
    ]
    con.close()
except Exception as e:  # noqa
    res["sessions_error"] = str(e)

# 2. SessionRunStateMachine lines
logs = WB / "logs"
sm = []
for d in sorted(os.listdir(logs))[-2:]:
    dp = logs / d
    if not dp.is_dir():
        continue
    for f in os.listdir(dp):
        if not f.endswith(".log"):
            continue
        fp = dp / f
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if "SessionRunStateMachine" in ln:
                        sm.append(ln.rstrip()[:400])
        except Exception:
            pass
        if len(sm) > 25:
            break
res["state_machine_lines"] = sm[:25]

# 3. tool-ish log lines (what other structured signals exist)
pats = ["tool", "Tool", "Bash", "exec", "pytest", "git ", "Write(", "Edit("]
other = {}
for d in sorted(os.listdir(logs))[-1:]:
    dp = logs / d
    if not dp.is_dir():
        continue
    for f in os.listdir(dp):
        if not f.endswith(".log"):
            continue
        fp = dp / f
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    for p in pats:
                        if p in ln:
                            other.setdefault(p, []).append(ln.rstrip()[:300])
        except Exception:
            pass
for k in other:
    other[k] = other[k][:5]
res["other_signals"] = other

# 4. sdk/conversations
sdk = WB / "logs" / "2026-09-16" / "sdk" / "conversations"
if sdk.exists():
    res["sdk_conversations"] = sorted(os.listdir(sdk))[:10]
    for f in sorted(os.listdir(sdk))[:2]:
        fp = sdk / f
        if fp.is_dir():
            res[f"sdk::{f}"] = sorted(os.listdir(fp))[:10]
        else:
            res[f"sdk::{f}"] = fp.read_text(encoding="utf-8", errors="replace")[:300]

# 5. changes-detail file entry shape
cd = WB / "changes-detail" / CUR
if cd.exists():
    files = sorted(os.listdir(cd))
    res["changes_detail_files"] = files[:5]
    if files:
        data = json.loads((cd / files[0]).read_text(encoding="utf-8", errors="replace"))
        res["changes_detail_keys"] = list(data.keys())[:20] if isinstance(data, dict) else type(data).__name__
        if isinstance(data, dict) and "files" in data:
            f0 = data["files"][0]
            res["changes_detail_file0"] = {k: str(v)[:160] for k, v in f0.items()} if isinstance(f0, dict) else str(f0)[:200]

Path(r"D:\AgentPet\docs\research\_probe3_out.txt").write_text(
    json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print("ok")
