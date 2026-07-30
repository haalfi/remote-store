"""Score replay results against the traces' recorded gates.

Run from the repo root. The ground-truth defect this used to patch in-process
(the BUG-199 trace citing `sdd/TESTING.md` for cassette sections that live in
`sdd/TESTING-RUNBOOK.md`) is fixed in the trace itself as of PR #942, so there is
no correction layer here any more: the answer key is correct at source.
"""

from __future__ import annotations

import glob
import os
import sys
from collections import defaultdict

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import COMPILED, key  # noqa: E402

TRACE = {
    "BK-167a": "sdd/traces/bk-167a-documentation-framework-tooling.yml",
    "BK-171": "sdd/traces/bk-171-link-validation.yml",
    "BK-167": "sdd/traces/bk-167-documentation-framework-defined.yml",
    "BUG-199": "sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml",
}


def gates(item: str) -> list[tuple[str, str]]:
    with open(TRACE[item]) as fh:
        t = yaml.safe_load(fh)
    return [
        (s["file"], key(s["section"]))
        for ph in t.get("phases", [])
        for s in ph.get("steps", [])
        if s.get("read_type") == "gate"
    ]


def parse(path: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    g: list[tuple[str, str]] = []
    e: list[tuple[str, str]] = []
    cur = g
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line == "###ESCAPES###":
                cur = e
                continue
            if not line or line == "NONE":
                continue
            f, _, sec = line.partition(" :: ")
            cur.append((f.strip(), key(sec)))
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


rows: defaultdict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
for path in sorted(glob.glob("sdd/research/rulebook-poc/results/*.txt")):
    arm, item, _run = os.path.basename(path)[:-4].split("_")
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
agg: defaultdict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
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
n = len({i for _, i in rows})
for arm in sorted(agg):
    a = agg[arm]
    print(
        f"ARM {arm}: recall(all)={a[0] / n:.0%}  recall(in-scope)={a[1] / n:.0%}  "
        f"escapes/run={a[2] / n:.1f}  cited/run={a[3] / n:.1f}"
    )
