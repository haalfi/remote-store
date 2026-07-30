"""Aggregate sdd/traces/*.yml to size a rulebook-usefulness experiment.

Run from the repo root.
"""

from __future__ import annotations

import glob
import os
import sys
from collections import Counter

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import COMPILED  # noqa: E402

files = sorted(p for p in glob.glob("sdd/traces/[!_]*.yml"))
gate_files: Counter[str] = Counter()
all_files: Counter[str] = Counter()
per_trace = []

for path in files:
    with open(path) as fh:
        t = yaml.safe_load(fh)
    steps = [s for ph in t.get("phases", []) for s in ph.get("steps", [])]
    gates = [s for s in steps if s.get("read_type") == "gate"]
    in_scope = [s for s in gates if s["file"] in COMPILED]
    for s in steps:
        all_files[s["file"]] += 1
    for s in gates:
        gate_files[s["file"]] += 1
    per_trace.append((t["id"], len(steps), len(gates), len(in_scope), path))

print(f"traces={len(files)}")
tot_steps = sum(p[1] for p in per_trace)
tot_gates = sum(p[2] for p in per_trace)
tot_scope = sum(p[3] for p in per_trace)
print(f"steps={tot_steps} gates={tot_gates} gates_in_rulebook_scope={tot_scope}")
pct = 100 * tot_scope / tot_gates if tot_gates else 0
print(f"rulebook coverage ceiling on gates: {pct:.0f}%")

print("\ntop gate files:")
for f, n in gate_files.most_common(14):
    mark = "IN " if f in COMPILED else "out"
    print(f"  {mark} {n:4d}  {f}")

print("\nbest candidates (most in-scope gates):")
for tid, ns, ng, nsc, path in sorted(per_trace, key=lambda p: -p[3])[:12]:
    print(f"  {tid:10s} steps={ns:3d} gates={ng:3d} in_scope={nsc:3d}  {path}")
