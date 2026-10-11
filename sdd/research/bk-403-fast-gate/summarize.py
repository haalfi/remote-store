"""Summarize replay.jsonl: per-PR and per-commit FULL rate, modelled gate seconds, FULL reasons.

Usage: python sdd/research/bk-403-fast-gate/summarize.py results/replay.jsonl
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay import FULL_GATE  # noqa: E402


def report(name: str, rows: list[dict]) -> None:
    n = len(rows)
    secs = [r["seconds"] for r in rows]
    tests = Counter(r["tests"] for r in rows)
    print(f"== {name}: {n} units")
    print(
        f"  tests: FULL {tests['FULL']} ({tests['FULL'] / n:.1%}), selected {tests['selected']}, none {tests['none']}"
    )
    med, mean = statistics.median(secs), statistics.mean(secs)
    print(f"  modelled gate seconds: median {med:.1f}, mean {mean:.1f}, full gate {FULL_GATE:.1f}")
    print(f"  median share of full gate: {med / FULL_GATE:.1%}; total {sum(secs) / (n * FULL_GATE):.1%}")
    sel = [r["share"] for r in rows if r["tests"] == "selected"]
    if sel:
        print(f"  selected runs: median test share {statistics.median(sel):.1%}")
    reasons = Counter()
    for r in rows:
        fr = r.get("full_reason")
        if r["tests"] == "FULL" and fr:
            p = fr.split(":", 1)[0]
            reasons[p if fr != "cutoff" and "cutoff" not in fr else "cutoff (>50%)"] += 1
    print("  FULL reasons (first per unit):")
    for k, v in reasons.most_common(12):
        print(f"    {v:4d}  {k}")


def main() -> None:
    rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line]
    report("per PR (Phase 0's unit)", [r["pr_level"] for r in rows])
    report("per commit (gate run per round)", [c for r in rows for c in r["per_commit"]])


if __name__ == "__main__":
    main()
