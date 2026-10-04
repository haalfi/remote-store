"""Over-selection: selected tests vs the coverage-context minimal set.

Throwaway research (RFC-0019 Phase 0, § Roadmap "over-selection ... computed
once locally"). Input: ``coverage json --show-contexts`` from one Stage-1 run
with ``--cov-context=test``, and the H replay. For each SELECTED H diff that
touches ``src/``, the minimal set is every test whose context executed a line
of a changed ``src/`` file (outside import-phase lines, which carry the empty
context), plus every test in a changed test file. The ratio is selected /
minimal. Contexts are from today's tree, so a historical diff is measured
against today's coverage of the same files.

Usage: python sdd/research/bk-403-phase-0/oversel.py <coverage.json> <universe.json> <h.jsonl> <out.json>
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from metrics import Universe
from p0tree import Tree
from selector import Readers, changed_paths, select


def main() -> None:
    cov_path, upath, hpath, out = sys.argv[1:5]
    cov = json.loads(Path(cov_path).read_text(encoding="utf-8"))
    by_src: dict[str, set[str]] = defaultdict(set)
    for fname, data in cov["files"].items():
        rel = fname.replace("\\", "/")
        rel = rel[rel.index("src/") :] if "src/" in rel else rel
        for ctxs in data.get("contexts", {}).values():
            for c in ctxs:
                if c:
                    by_src[rel].add(c.split("|", 1)[0])
    U = Universe(Path(upath))
    readers = Readers.load()
    rows = []
    for line in Path(hpath).read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["variant"] != "precision" or rec["mode"] != "SELECTED" or not rec["src_touched"]:
            continue
        sha = rec["sha"]
        changes = changed_paths(f"{sha}^", sha)
        res = select(Tree(f"{sha}^"), Tree(sha), changes, "precision", readers=readers)
        sel, _, _ = U.expand(res)
        minimal: set[str] = set()
        for _, p in changes:
            if p.startswith("src/"):
                minimal |= by_src.get(p, set())
            elif p.startswith("tests/") and p in U.by_file:
                minimal |= set(U.by_file[p])
        minimal &= set(U.cost)
        missing = minimal - sel
        rows.append(
            {
                "pr": rec["pr"],
                "selected": len(sel),
                "minimal": len(minimal),
                "ratio": (len(sel) / len(minimal)) if minimal else None,
                "minimal_not_selected": len(missing),
                "sample_missing": sorted(missing)[:10],
            }
        )
    ratios = [r["ratio"] for r in rows if r["ratio"] is not None]
    summary = {
        "derivation": f"oversel.py {cov_path} {upath} {hpath}",
        "diffs": len(rows),
        "median_ratio": statistics.median(ratios) if ratios else None,
        "max_ratio": max(ratios) if ratios else None,
        "diffs_with_minimal_not_selected": sum(1 for r in rows if r["minimal_not_selected"]),
        "rows": rows,
    }
    Path(out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "rows"})


if __name__ == "__main__":
    main()
