"""Section-level coverage: of gates hitting compiled docs, how many cite a
section RULEBOOK.md actually carries (## Rules) vs one it drops (## Guides)?

Run from the repo root.
"""

from __future__ import annotations

import glob
import os
import re
import sys
from collections import Counter

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import CLAUDE_MD_DROPPED, COMPILED, CONTRIBUTING_CARRIED, key  # noqa: E402


def dropped_sections(path: str) -> set[str]:
    """Heading texts in `path` that RULEBOOK.md does not carry.

    For the eight process docs that is everything outside the `## Rules` block.
    `CLAUDE.md` and `CONTRIBUTING.md` have no such block, so their carried and
    dropped sets are enumerated in `_common`.
    """
    if path == "CLAUDE.md":
        return set(CLAUDE_MD_DROPPED)

    out: set[str] = set()
    if path == "CONTRIBUTING.md":
        with open(path) as fh:
            for line in fh:
                m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
                if m and m.group(1).strip().lower() not in CONTRIBUTING_CARRIED:
                    out.add(m.group(1).strip().lower())
        return out

    with open(path) as fh:
        lines = fh.read().splitlines()
    in_rules = False
    for line in lines:
        m2 = re.match(r"^##\s+(.+?)\s*$", line)
        if m2:
            in_rules = m2.group(1).strip().lower() == "rules"
            if not in_rules:
                out.add(m2.group(1).strip().lower())
            continue
        m3 = re.match(r"^###\s+(.+?)\s*$", line)
        if m3 and not in_rules:
            out.add(m3.group(1).strip().lower())
    return out


DROPPED = {p: dropped_sections(p) for p in COMPILED}


def classify(file: str, section: str) -> str:
    head = key(section)
    if head == "FULL":
        return "whole-doc"
    if head == "RULES":
        return "served"
    if head in DROPPED.get(file, set()):
        return "dropped"
    # heading not found outside the Rules block -> assume inside it
    return "served"


counts: Counter[str] = Counter()
dropped_hits: Counter[str] = Counter()
n_traces = 0

for path in sorted(glob.glob("sdd/traces/[!_]*.yml")):
    n_traces += 1
    with open(path) as fh:
        t = yaml.safe_load(fh)
    for ph in t.get("phases", []):
        for s in ph.get("steps", []):
            if s.get("read_type") != "gate" or s["file"] not in COMPILED:
                continue
            c = classify(s["file"], s["section"])
            counts[c] += 1
            if c == "dropped":
                dropped_hits[f"{s['file']} :: {s['section'].split(' / ')[0]}"] += 1

tot = sum(counts.values())
print(f"traces scanned: {n_traces}")
print(f"in-scope gate steps: {tot}")
for k, v in counts.most_common():
    print(f"  {k:10s} {v:4d}  ({100 * v / tot:.0f}%)")

print("\nmost-cited gate sections the rulebook DROPS:")
for k, v in dropped_hits.most_common(14):
    print(f"  {v:3d}  {k}")
