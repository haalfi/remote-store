"""Measure CI wait in a window: run durations, next-push gaps, merge waits.

Throwaway research (ID-266). Reads ``fetch.py``'s output.

Usage: python sdd/research/id-266-ci-wait/measure.py tmp/ci-wait 2026-07-11 2026-10-11T12:40:00Z
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

CODE_MIN_S = 150  # shorter completed runs are docs-only fan-outs
BIN_S = 180  # next-push gap histogram bin
MERGE_WAIT_S = 300  # a merge this soon after the final run ended waited on it


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0.0


def waiting(pairs: list, what: str) -> None:
    """Print the gap histogram for (run, next event) pairs, the first-bin excess
    and an upper bound on what a fast lane could save on those waits."""
    hist: Counter = Counter()
    first = []
    for r, t in pairs:
        gap = t - r["t1"]
        k = -1 if gap < 0 else min(int(gap // BIN_S), 10)
        hist[k] += 1
        if k == 0:
            first.append(r["dur"])
    for k in range(-1, 11):
        label = "before end" if k < 0 else (f"{k * 3}-{k * 3 + 3}m" if k < 10 else "30m+")
        print(f"  {label:>10}: {hist[k]}")
    excess = round(max(0.0, hist[0] - (hist[1] + hist[2]) / 2))
    # A waited-on run saves at most its own duration, and no excess of first-bin
    # runs can outlast its longest members: sum the `excess` longest.
    bound = sum(sorted(first, reverse=True)[:excess])
    print(f"first-bin excess over the next two bins' mean: {excess} {what}")
    print(f"upper bound on fast-lane saving: the {excess} longest first-bin runs = {bound / 3600:.1f} h")


def main() -> None:
    d, since, until = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    runs = [
        r
        for r in json.loads((d / "runs.json").read_text(encoding="utf-8"))
        if since <= r["created"] and r["updated"] <= until
    ]
    for r in runs:
        r["t0"] = ts(r["started"] or r["created"])
        r["t1"] = ts(r["updated"])
        r["dur"] = r["t1"] - r["t0"]
    done = [r for r in runs if r["conclusion"] in ("success", "failure")]
    code = [r["dur"] for r in done if r["dur"] >= CODE_MIN_S]
    print(f"window {since} .. {until}: {(ts(until) - ts(since + 'T00:00:00Z')) / 86400:.0f} days")
    print(
        f"runs {len(runs)}, completed {len(done)}, cancelled "
        f"{sum(r['conclusion'] == 'cancelled' for r in runs)}, code-sized {len(code)}"
    )
    print(f"code-sized duration p50 {q(code, 0.5) / 60:.1f}m p90 {q(code, 0.9) / 60:.1f}m")

    by_branch = defaultdict(list)
    for r in runs:
        by_branch[r["branch"]].append(r)
    for rs in by_branch.values():
        rs.sort(key=lambda r: r["created"])
    prs = [p for p in json.loads((d / "prs.json").read_text(encoding="utf-8")) if since <= p["mergedAt"] <= until]

    # Gap from a completed run's end to the branch's next push. Waiting on CI
    # shows as an excess in the first bin over the smooth decay after it.
    pairs = []
    for rs in by_branch.values():
        for i, r in enumerate(rs[:-1]):
            if r["conclusion"] in ("success", "failure"):
                pairs.append((r, ts(rs[i + 1]["created"])))
    red = sum(r["conclusion"] == "failure" for r, _ in pairs)
    print(f"\ncompleted runs followed by another push: {len(pairs)}, red {red}")
    waiting(pairs, "pushes")

    # A /ship round reads CI, then replies to threads, before its next push
    # (ship SKILL § Close each round), so a wait there shows in the first PR
    # activity of any kind after the push that started the run. Only the
    # branches of PRs merged in the window carry activity.
    act = defaultdict(list)
    for a in json.loads((d / "activity.json").read_text(encoding="utf-8")):
        act[a["branch"]].append(ts(a["at"]))
    pairs = []
    for p in prs:
        rs = by_branch.get(p["headRefName"], [])
        for i, r in enumerate(rs):
            if r["conclusion"] not in ("success", "failure"):
                continue
            after = [t for t in act[p["headRefName"]] if ts(r["created"]) < t < ts(p["mergedAt"])]
            if i + 1 < len(rs):
                after.append(ts(rs[i + 1]["created"]))
            if after:
                pairs.append((r, min(after)))
    print(f"\ncompleted runs followed by a push, comment, reply or review: {len(pairs)}")
    waiting(pairs, "next events")

    waits = []
    for p in prs:
        mt = ts(p["mergedAt"])
        before = [r for r in done if r["branch"] == p["headRefName"] and r["t0"] <= mt]
        if not before:
            continue
        final = max(before, key=lambda r: r["t0"])
        if 0 <= mt - final["t1"] <= MERGE_WAIT_S:
            waits.append(min(final["dur"], mt - final["t0"]))
    print(
        f"\nmerged PRs {len(prs)}; merged within {MERGE_WAIT_S // 60} min of the final run's end: "
        f"{len(waits)}, median wait {q(waits, 0.5) / 60:.1f}m, total {sum(waits) / 3600:.1f} h"
    )


if __name__ == "__main__":
    main()
