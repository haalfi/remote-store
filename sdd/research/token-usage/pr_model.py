"""Bridge PR size and activity to measured units, then project units over the whole PR history.

The calibration PRs are the work items in ``results/work_items.json`` that are
not review-only, with their measured units. For each PR feature a one-feature
log-log fit ``units = a * (x + 1)^b`` is scored by leave-one-out; the best
feature then projects estimated units for every merged PR, summed by month.
With n = 6 the absolute figures are orders of magnitude; before the earliest
calibration PR the projection is outside its domain.

Reads ``--data/prs.json``, ``--data/corpus.json`` (trace_corpus.py) and
``results/work_items.json``; writes ``results/pr_model.json``.
"""

from __future__ import annotations

import collections
import json
import math
import statistics as st
from datetime import datetime

import _common as c

FEATURES = ["commits", "threads", "reviews", "lines", "files", "open_h"]


def hours(p):
    a = datetime.fromisoformat(p["created"].replace("Z", "+00:00"))
    b = datetime.fromisoformat(p["merged"].replace("Z", "+00:00"))
    return (b - a).total_seconds() / 3600


def feat(p, k):
    return {"lines": p["add"] + p["del"], "open_h": hours(p)}.get(k, p.get(k))


def fit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False)) / sxx if sxx else 0
    return my - b * mx, b


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))
    prs = {p["number"]: p for p in c.load_prs(args.data)}
    corpus = json.loads((args.data / "corpus.json").read_text(encoding="utf-8"))
    work = json.loads((args.results / "work_items.json").read_text(encoding="utf-8"))["items"]
    measured = {v["prs"][0]: v["units_m"] * 1e6 for k, v in work.items() if "review only" not in k}

    scores = {}
    for k in FEATURES:
        xs = [math.log(feat(prs[n], k) + 1) for n in measured]
        ys = [math.log(u) for u in measured.values()]
        _, b = fit(xs, ys)
        errs = []
        for i in range(len(xs)):
            a2, b2 = fit(xs[:i] + xs[i + 1 :], ys[:i] + ys[i + 1 :])
            errs.append(abs(ys[i] - (a2 + b2 * xs[i])))
        scores[k] = {
            "b": round(b, 2),
            "r": round(st.correlation(xs, ys), 2),
            "loo_error_factor": round(math.exp(st.median(errs)), 2),
        }
    best = min(scores, key=lambda k: scores[k]["loo_error_factor"])
    a, b = fit([math.log(feat(prs[n], best) + 1) for n in measured], [math.log(u) for u in measured.values()])

    def est(p):
        return math.exp(a) * (feat(p, best) + 1) ** b

    by_m = collections.defaultdict(list)
    for p in prs.values():
        by_m[p["created"][:7]].append(p)
    monthly = {
        m: {
            "prs": len(ps),
            "commits_median": st.median(p["commits"] for p in ps),
            "review_threads_mean": round(st.mean(p["threads"] for p in ps), 1),
            "open_hours_median": round(st.median(hours(p) for p in ps), 1),
            "est_units_m": round(sum(est(p) for p in ps) / 1e6),
            "est_units_per_pr_m": round(sum(est(p) for p in ps) / len(ps) / 1e6, 1),
        }
        for m, ps in sorted(by_m.items())
    }
    idx = collections.defaultdict(list)
    for r in corpus:
        if isinstance(r["rounds"], int) and r["id"]:
            idx[str(r["id"]).upper()].append(r["rounds"])
    pairs = [
        (max(idx[t]), p["commits"])
        for p in prs.values()
        if (t := p["title"].split(":")[0].split(",")[0].strip().upper()) in idx
    ]
    ranked = sorted((est(p) for p in prs.values()), reverse=True)
    payload = {
        "calibration_prs": sorted(measured),
        "features": scores,
        "best_feature": best,
        "monthly": monthly,
        "rounds_vs_commits": {"pairs": len(pairs), "r": round(st.correlation(*zip(*pairs, strict=False)), 2)},
        "top_10pct_share_of_est_units_pct": c.pct(sum(ranked[: len(ranked) // 10]), sum(ranked), 0),
    }
    inputs = {
        "prs.json": args.data / "prs.json",
        "corpus.json": args.data / "corpus.json",
        "work_items.json": args.results / "work_items.json",
    }
    c.write_result(args.results, "pr_model", "pr_model", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
