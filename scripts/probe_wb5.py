"""Probe state-machine transition vocabulary (task lifecycle signals)."""
import json
import os
from collections import Counter
from pathlib import Path

base = Path.home() / ".workbuddy" / "logs"
inputs, frm, to, outputs = Counter(), Counter(), Counter(), Counter()
samples = []
for d in sorted(os.listdir(base)):
    sdk = base / d / "sdk" / "conversations"
    if not sdk.is_dir():
        continue
    for fn in os.listdir(sdk):
        if not fn.endswith(".log"):
            continue
        fp = sdk / fn
        if fp.stat().st_size > 12_000_000:
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if "state-machine:transition" not in ln:
                        continue
                    parts = ln.split(" ", 2)
                    if len(parts) < 3:
                        continue
                    try:
                        o = json.loads(parts[2])
                    except Exception:
                        continue
                    inputs[o.get("input")] += 1
                    frm[o.get("from")] += 1
                    to[o.get("to")] += 1
                    for k in (o.get("output") or {}):
                        outputs[k] += 1
                    if len(samples) < 6:
                        samples.append({k: o.get(k) for k in
                                        ("from", "to", "input", "declaredTo", "valid", "actions")})
        except Exception:
            pass

# event-machine dispatch input vocabulary across a big session
dinputs = Counter()
for d in sorted(os.listdir(base)):
    sdk = base / d / "sdk" / "conversations"
    if not sdk.is_dir():
        continue
    for fn in os.listdir(sdk):
        if not fn.endswith(".log"):
            continue
        fp = sdk / fn
        if fp.stat().st_size > 12_000_000:
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if "event-machine:dispatch" not in ln:
                        continue
                    parts = ln.split(" ", 2)
                    if len(parts) < 3:
                        continue
                    try:
                        o = json.loads(parts[2])
                    except Exception:
                        continue
                    dinputs[o.get("input")] += 1
                    for k in (o.get("output") or {}):
                        outputs["dispatch." + k] += 1
        except Exception:
            pass

out = {
    "transition_inputs": inputs.most_common(40),
    "transition_from": frm.most_common(25),
    "transition_to": to.most_common(25),
    "dispatch_inputs": dinputs.most_common(40),
    "output_keys": outputs.most_common(40),
    "samples": samples,
}
Path(r"D:\AgentPet\docs\research\_probe5_out.txt").write_text(
    json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(out, indent=2, ensure_ascii=False, default=str)[:4000])
