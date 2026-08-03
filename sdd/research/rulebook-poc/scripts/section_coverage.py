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


def headings(path: str) -> list[tuple[int, str]]:
    """Real Markdown headings in `path` as (level, lowercased text), in order.

    Fence-aware. `sdd/000-process.md` line 29 is `## <PREFIX>-NNN: <Rule Title>`
    inside a fenced spec-format template; treating that as a heading silently
    reset the section walker and misfiled every heading after it.
    """
    out: list[tuple[int, str]] = []
    fenced = False
    with open(path) as fh:
        for line in fh:
            if re.match(r"^\s*(```|~~~)", line):
                fenced = not fenced
                continue
            if fenced:
                continue
            m = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
            if m:
                out.append((len(m.group(1)), m.group(2).strip().lower()))
    return out


def _block(path: str, name: str) -> set[str]:
    """Sub-headings under the `## <name>` block of `path`."""
    out: set[str] = set()
    inside = False
    for level, text in headings(path):
        if level == 2:
            inside = text == name
            continue
        if inside:
            out.add(text)
    return out


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
        return {t for _lvl, t in headings(path) if t not in CONTRIBUTING_CARRIED}

    in_rules = False
    for level, text in headings(path):
        if level == 2:
            in_rules = text == "rules"
            if not in_rules:
                out.add(text)
            continue
        if not in_rules:
            out.add(text)
    return out


def guides_sections(path: str) -> set[str]:
    """Heading texts living under this file's `## Guides` block.

    `dropped` and `Guides` are different predicates: `CONTRIBUTING.md` has no
    Guides block at all, and `TESTING.md :: Test Subpackage Placement` sits
    between Intent & Scope and Rules. Both are dropped; neither is Guides.
    """
    if path in ("CLAUDE.md", "CONTRIBUTING.md"):
        return set()
    return _block(path, "guides")


def all_headings(path: str) -> set[str]:
    return {t for _lvl, t in headings(path)}


DROPPED = {p: dropped_sections(p) for p in COMPILED}
GUIDES = {p: guides_sections(p) for p in COMPILED}
HEADINGS = {p: all_headings(p) for p in COMPILED}


def classify(file: str, section: str) -> str:
    head = key(section)
    if head == "FULL":
        return "whole-doc"
    if head == "RULES":
        return "served"
    if head in DROPPED.get(file, set()):
        return "dropped-guides" if head in GUIDES.get(file, set()) else "dropped-other"
    if head not in HEADINGS.get(file, set()):
        # No heading matches. Counted as served, which is generous to the
        # artefact; reported separately so the bound is measured, not assumed.
        return "served-unmatched"
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
            if c.startswith("dropped"):
                label = "Guides" if c == "dropped-guides" else "other"
                dropped_hits[f"[{label}] {s['file']} :: {s['section'].split(' / ')[0]}"] += 1

tot = sum(counts.values())
served = counts["served"] + counts["served-unmatched"]
dropped = counts["dropped-guides"] + counts["dropped-other"]
print(f"traces scanned: {n_traces}")
print(f"in-scope gate steps: {tot}")
print(
    f"  served     {served:4d}  ({100 * served / tot:.0f}%)  "
    f"of which {counts['served-unmatched']} matched no heading (see bound below)"
)
print(
    f"  dropped    {dropped:4d}  ({100 * dropped / tot:.0f}%)  "
    f"= {counts['dropped-guides']} Guides + {counts['dropped-other']} other non-Rules"
)
print(f"  whole-doc  {counts['whole-doc']:4d}  ({100 * counts['whole-doc'] / tot:.0f}%)")

print("\nmost-cited gate sections the rulebook DROPS:")
for k, v in dropped_hits.most_common(14):
    print(f"  {v:3d}  {k}")

print(
    "\nBound (DRIFT-RULES rule 7): a cited section matching no literal heading is\n"
    "counted as served, and `key()` collapses numbered citations to RULES, which is\n"
    "served unconditionally. Both push the same way, so `dropped` is a lower bound."
)
