"""Summarise the H replay into plan.md's metrics, per variant.

Throwaway research (RFC-0019 Phase 0). FULL counts as 100% in every share.
Usage: python sdd/research/bk-403-phase-0/summarize_h.py <h_replay.jsonl> <out.json>
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path


def reason_class(reason: str) -> str:
    r = reason.split(": ", 1)[1] if ": " in reason else reason
    r = re.sub(r"\(.*?\)", "", r).strip()
    r = re.sub(r"reaches fixture infrastructure \S+", "reaches fixture infrastructure", r)
    r = re.sub(r"script imported by \S+", "script imported by another module", r)
    r = re.sub(r"script with no mapped test.*", "script with no mapped test", r)
    return r


def main() -> None:
    rows = [json.loads(x) for x in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
    out: dict = {"derivation": f"summarize_h.py {sys.argv[1]}", "variants": {}}
    for v in ("pilot", "precision", "precision-literal"):
        rs = [r for r in rows if r["variant"] == v]
        full = [r for r in rs if r["mode"] == "FULL"]
        sel = [r for r in rs if r["mode"] == "SELECTED"]
        reasons = Counter()
        first_reason = Counter()
        for r in full:
            classes = {reason_class(x) for x in r["full_reasons"]}
            reasons.update(classes)
            first_reason[reason_class(r["full_reasons"][0])] += 1
        src = [r for r in rs if r["src_touched"]]
        nonsrc = [r for r in rs if not r["src_touched"]]

        def med(xs, key):
            return statistics.median(x[key] for x in xs) if xs else None

        out["variants"][v] = {
            "n": len(rs),
            "full": len(full),
            "full_rate": len(full) / len(rs),
            "median_wall_share": med(rs, "wall_share"),
            "mean_wall_share": statistics.fmean(r["wall_share"] for r in rs),
            "median_selected_share": med(rs, "selected_share"),
            "median_wall_share_selected_only": med(sel, "wall_share"),
            "median_wall_share_src_prs": med(src, "wall_share"),
            "median_wall_share_non_src_prs": med(nonsrc, "wall_share"),
            "n_src_prs": len(src),
            "full_src_prs": sum(1 for r in src if r["mode"] == "FULL"),
            "median_jobs_selected": med(sel, "n_jobs"),
            "jobs_hist_selected": dict(sorted(Counter(r["n_jobs"] for r in sel).items())),
            "full_reasons_any": dict(reasons.most_common()),
            "full_reason_first": dict(first_reason.most_common()),
            "imputed_rows": sum(1 for r in rs if r["imputed_files"]),
        }
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
    for v, m in out["variants"].items():
        print(
            v,
            {
                k: (round(x, 3) if isinstance(x, float) else x)
                for k, x in m.items()
                if k not in ("full_reasons_any", "jobs_hist_selected")
            },
        )
        print("  reasons(any):", m["full_reasons_any"])


if __name__ == "__main__":
    main()
