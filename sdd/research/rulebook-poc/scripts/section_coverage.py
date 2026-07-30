"""Section-level coverage: of gates hitting compiled docs, how many cite a
section RULEBOOK.md actually carries (## Rules) vs one it drops (## Guides)?"""

from __future__ import annotations

import glob
import re
from collections import Counter

import yaml

COMPILED = [
    "CLAUDE.md",
    "sdd/000-process.md",
    "sdd/DESIGN.md",
    "sdd/TESTING.md",
    "sdd/AUTHORING.md",
    "sdd/DOCUMENTATION.md",
    "sdd/CONTENT-RULES.md",
    "sdd/DRIFT-RULES.md",
    "sdd/CI-OPERATIONS.md",
    "CONTRIBUTING.md",
]


def dropped_sections(path: str) -> set[str]:
    """Heading texts in `path` that live OUTSIDE the ## Rules block."""
    if path == "CLAUDE.md":
        return set()  # compiled near-entirely
    if path == "CONTRIBUTING.md":
        keep = {"authoritative document format"}
        out = set()
        for line in open(path):
            m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
            if m and m.group(1).strip().lower() not in keep:
                out.add(m.group(1).strip().lower())
        return out

    lines = open(path).read().splitlines()
    in_rules = False
    out: set[str] = set()
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
    head = section.split(" / ")[0].strip().lower()
    if head in ("(full)", "(item)", "(full — being authored)"):
        return "whole-doc"
    if head.startswith("rules") or re.match(r"^\d+[\s.(]", head) or head == "principles":
        return "served"
    if head in DROPPED.get(file, set()):
        return "dropped"
    # heading not found outside Rules -> assume inside Rules
    return "served"


counts: Counter[str] = Counter()
dropped_hits: Counter[str] = Counter()

for path in sorted(glob.glob("sdd/traces/[!_]*.yml")):
    t = yaml.safe_load(open(path))
    for ph in t.get("phases", []):
        for s in ph.get("steps", []):
            if s.get("read_type") != "gate" or s["file"] not in COMPILED:
                continue
            c = classify(s["file"], s["section"])
            counts[c] += 1
            if c == "dropped":
                dropped_hits[f"{s['file']} :: {s['section'].split(' / ')[0]}"] += 1

tot = sum(counts.values())
print(f"in-scope gate steps: {tot}")
for k, v in counts.most_common():
    print(f"  {k:10s} {v:4d}  ({100 * v / tot:.0f}%)")

print("\nmost-cited gate sections the rulebook DROPS:")
for k, v in dropped_hits.most_common(12):
    print(f"  {v:3d}  {k}")
