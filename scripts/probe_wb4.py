"""AgentPet PHASE 0 - probe SDK conversation event log structure.
Only extracts shape (event names + key names), never full content.
"""
import json
import os
from collections import Counter
from pathlib import Path

LOGDIR = Path.home() / ".workbuddy" / "logs" / "2026-09-16" / "sdk" / "conversations"
res = {}

for fn in sorted(os.listdir(LOGDIR)):
    if not fn.endswith(".log"):
        continue
    fp = LOGDIR / fn
    if fp.stat().st_size > 8_000_000:
        res[fn] = {"skipped": "too large", "size": fp.stat().st_size}
        continue
    kinds = Counter()
    shapes = {}
    n = 0
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.rstrip("\n")
                if not ln.strip():
                    continue
                n += 1
                parts = ln.split(" ", 2)
                if len(parts) < 3:
                    continue
                ts, kind = parts[0], parts[1]
                kinds[kind] += 1
                blob = parts[2]
                if kind not in shapes and blob.startswith("{"):
                    try:
                        obj = json.loads(blob)
                        if isinstance(obj, dict):
                            shapes[kind] = {
                                "keys": sorted(obj.keys())[:18],
                                "input": obj.get("input"),
                            }
                    except Exception:
                        pass
    except Exception as e:  # noqa
        res[fn] = {"error": str(e)}
        continue
    res[fn] = {"lines": n, "kinds": kinds.most_common(20), "shapes": shapes}

# deeper: for tool_call / tool events, what fields describe the tool?
target = LOGDIR / "396cdbb6-e96c-4c39-b349-dc4321d96a8a.log"
samples = []
if target.exists():
    with open(target, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if "tool" in ln[:200].lower():
                parts = ln.split(" ", 2)
                if len(parts) < 3:
                    continue
                try:
                    obj = json.loads(parts[2])
                except Exception:
                    continue
                if isinstance(obj, dict) and "input" in obj:
                    samples.append({
                        "kind": parts[1],
                        "input": obj.get("input"),
                        "keys": sorted(obj.keys()),
                        "payload_keys": sorted(obj.keys()),
                    })
                if len(samples) > 400:
                    break
res["_tool_samples"] = samples[:40]
res["_tool_input_types"] = Counter(s.get("input") for s in samples).most_common(30)

Path(r"D:\AgentPet\docs\research\_probe4_out.txt").write_text(
    json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print("ok")
