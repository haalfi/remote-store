"""Score replay results against the traces' recorded gates."""

from __future__ import annotations

import glob
import os
import re
from collections import defaultdict

import yaml

TRACE = {
    "BK-167a": "sdd/traces/bk-167a-documentation-framework-tooling.yml",
    "BK-171": "sdd/traces/bk-171-link-validation.yml",
    "BK-167": "sdd/traces/bk-167-documentation-framework-defined.yml",
    "BUG-199": "sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml",
}

COMPILED = {
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
}


def key(section: str) -> str:
    s = section.split(" / ")[0].strip().lower()
    if s.startswith("rules") or re.match(r"^\d+[\s.(]", s):
        return "RULES"
    if s.startswith("(full") or s in ("whole file", "(item)"):
        return "FULL"
    return s


def correct(f: str, k: str) -> tuple[str, str]:
    """Ground-truth correction: the BUG-199 trace cites sdd/TESTING.md for the
    cassette sections, but that content lives in sdd/TESTING-RUNBOOK.md
    (lines 160, 277). Verified by grep. Without this both arms are marked wrong
    for citing the file that actually holds the content."""
    if f == "sdd/TESTING.md" and k.startswith("cassette"):
        return ("sdd/TESTING-RUNBOOK.md", k)
    return (f, k)


def gates(item: str) -> list[tuple[str, str]]:
    t = yaml.safe_load(open(TRACE[item]))
    return [
        correct(s["file"], key(s["section"]))
        for ph in t.get("phases", [])
        for s in ph.get("steps", [])
        if s.get("read_type") == "gate"
    ]


def parse(path: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    g, e, cur = [], [], "g"
    for line in open(path):
        line = line.strip()
        if line == "###ESCAPES###":
            cur = "e"
            continue
        if not line or line == "NONE":
            continue
        f, _, sec = line.partition(" :: ")
        (g if cur == "g" else e).append((f.strip(), key(sec)))
    return g, e


def hit(gt: tuple[str, str], cited: list[tuple[str, str]]) -> bool:
    f, k = gt
    for cf, ck in cited:
        if cf != f:
            continue
        if not f.endswith(".md"):
            return True  # code/test files: file-level match
        if k == ck or k == "FULL" or ck == "FULL":
            return True
    return False


rows = defaultdict(list)
for path in sorted(glob.glob("sdd/research/rulebook-poc/results/*.txt")):
    arm, item, run = os.path.basename(path)[:-4].split("_")
    cited, esc = parse(path)
    gt = gates(item)
    gt_in = [g for g in gt if g[0] in COMPILED]
    rows[(arm, item)].append(
        {
            "recall_all": sum(hit(g, cited) for g in gt) / len(gt),
            "recall_in": sum(hit(g, cited) for g in gt_in) / len(gt_in),
            "escapes": len(esc),
            "cited": len(cited),
        }
    )

print(f"{'arm':4} {'item':9} {'recall(all)':>12} {'recall(in-scope)':>17} {'escapes':>8} {'cited':>6}")
agg = defaultdict(lambda: [0.0, 0.0, 0, 0])
for (arm, item), rs in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    ra = sum(r["recall_all"] for r in rs) / len(rs)
    ri = sum(r["recall_in"] for r in rs) / len(rs)
    es = sum(r["escapes"] for r in rs) / len(rs)
    ct = sum(r["cited"] for r in rs) / len(rs)
    print(f"{arm:4} {item:9} {ra:11.0%} {ri:16.0%} {es:8.1f} {ct:6.1f}")
    a = agg[arm]
    a[0] += ra
    a[1] += ri
    a[2] += es
    a[3] += ct

print()
n = len(set(i for _, i in rows))
for arm in sorted(agg):
    a = agg[arm]
    print(
        f"ARM {arm}: recall(all)={a[0] / n:.0%}  recall(in-scope)={a[1] / n:.0%}  escapes/run={a[2] / n:.1f}  cited/run={a[3] / n:.1f}"
    )
