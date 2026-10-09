"""Totals, cost by token class, context-size bands, cache behaviour and cost scaling.

Reads ``--data`` (extract.py's output), writes ``results/inventory.json``.
Session groups (a main session plus its subagents) are labelled with the work
item they served (``_common.work_groups``) or ``other``, never by session ID.
"""

from __future__ import annotations

import collections
import itertools
import math
import statistics as st
from datetime import datetime

import _common as c


def slope(points):
    lx = [math.log(x) for x, _ in points]
    ly = [math.log(y) for _, y in points]
    mx, my = st.mean(lx), st.mean(ly)
    return sum((x - mx) * (y - my) for x, y in zip(lx, ly, strict=False)) / sum((x - mx) ** 2 for x in lx)


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))
    calls, _items, S = c.load_extract(args.data)
    bycall = c.by_file(calls)
    U = sum(x["units"] for x in calls)
    tot = collections.Counter()
    for x in calls:
        for k in c.W:
            tot[k] += x[k]
    usd_model = collections.Counter()
    usd_class = collections.Counter()
    usd_kind = collections.Counter()
    for x in calls:
        p = c.PRICE[x["model"]]
        usd_model[x["model"]] += x["units"] * p
        usd_kind["subagent" if x["is_sub"] else "main"] += x["units"] * p
        for k in c.W:
            usd_class[k] += c.W[k] * x[k] * p
    active = [f for f in S if f in bycall]

    # context bands
    ctxs = sorted(x["ctx"] for x in calls)
    q = lambda p: ctxs[int(p * (len(ctxs) - 1))]  # noqa: E731
    bands = []
    for lo, hi in ((0, 50e3), (50e3, 100e3), (100e3, 200e3), (200e3, 400e3), (400e3, math.inf)):
        sel = [x for x in calls if lo <= x["ctx"] < hi]
        bands.append(
            {
                "band": f"{lo / 1e3:.0f}k-" + ("" if hi == math.inf else f"{hi / 1e3:.0f}k"),
                "calls_pct": c.pct(len(sel), len(calls)),
                "units_pct": c.pct(sum(x["units"] for x in sel), U),
            }
        )

    # Cache rebuilds: cache read below half the previous call's context. Gaps and the
    # previous call are recomputed over real calls, because extract.py measured them
    # against Claude Code's <synthetic> records too, and those carry no usage.
    gaps = []
    for cs in bycall.values():
        for a, b in zip(cs, cs[1:], strict=False):
            g = (
                datetime.fromisoformat(b["ts"].replace("Z", "+00:00"))
                - datetime.fromisoformat(a["ts"].replace("Z", "+00:00"))
            ).total_seconds()
            gaps.append(g)
            b["gap"], b["prev_ctx"], b["prev_model"] = g, a["ctx"], a["model"]
            b["miss"] = b["read"] < 0.5 * a["ctx"] and a["ctx"] > 10000
        cs[0]["miss"] = False
    rebuild = collections.Counter()
    rebuild_units = 0.0
    for x in calls:
        if not x["miss"]:
            continue
        w = x["w5"] + x["w1h"]
        extra = c.W["w5"] * x["w5"] + c.W["w1h"] * x["w1h"] - 0.1 * w
        rebuild_units += min(extra, x["prev_ctx"] * (1.25 - 0.1) if x["w1h"] == 0 else x["prev_ctx"] * 1.9)
        if x["prev_model"] and x["prev_model"] != x["model"]:
            rebuild["model switch"] += 1
        elif x["gap"] is not None and x["gap"] > 3600:
            rebuild["gap > 1h"] += 1
        elif x["gap"] is not None and x["gap"] > 300:
            rebuild["gap 5m-1h"] += 1
        else:
            rebuild["gap < 5m"] += 1

    # scaling: units ~ calls^b over transcripts with at least five calls
    main_pts = [
        (len(cs), sum(x["units"] for x in cs)) for f, cs in bycall.items() if not S[f]["is_sub"] and len(cs) >= 5
    ]
    sub_pts = [(len(cs), sum(x["units"] for x in cs)) for f, cs in bycall.items() if S[f]["is_sub"] and len(cs) >= 5]
    longest = []
    mains = [cs for f, cs in bycall.items() if not S[f]["is_sub"]]
    for cs in sorted(mains, key=len, reverse=True)[:4]:
        total = sum(x["units"] for x in cs)
        half = next(i for i, acc in enumerate(itertools.accumulate(x["units"] for x in cs)) if acc >= total / 2)
        longest.append(
            {
                "calls": len(cs),
                "ctx_growth_per_call": round((cs[-1]["ctx"] - cs[0]["ctx"]) / max(1, len(cs) - 1)),
                "half_units_after_call_pct": c.pct(half, len(cs), 0),
            }
        )

    # session groups, labelled by the work item they served
    label = {}
    for name, parents in c.work_groups(S, c.load_prs(args.data)).items():
        for p in parents:
            label[p] = name
    # Per session group, so BK-397's five /rvw-pr sessions are not added to its /ship session here.
    per_parent = collections.Counter()
    for f in active:
        per_parent[S[f]["parent"]] += sum(x["units"] for x in bycall[f])
    top_groups = [
        {"item": label.get(p, "other"), "units_m": round(u / 1e6, 1), "units_pct": c.pct(u, U, 0)}
        for p, u in per_parent.most_common(4)
    ]

    skill = collections.Counter()
    for x in calls:
        skill[x["skill"] or ("(subagent)" if x["is_sub"] else "(none)")] += x["units"]

    payload = {
        "window_days": sorted({x["ts"][:10] for x in calls}),
        "calls_by_model": dict(collections.Counter(x["model"] for x in calls)),
        "transcripts": {
            "with_calls": len(active),
            "main": sum(1 for f in active if not S[f]["is_sub"]),
            "subagent": sum(1 for f in active if S[f]["is_sub"]),
        },
        "calls": len(calls),
        "tokens": dict(tot),
        "tokens_total": sum(tot.values()),
        "units_total": round(U),
        "tokens_pct": {k: c.pct(v, sum(tot.values())) for k, v in tot.items()},
        "units_pct": {k: c.pct(c.W[k] * v, U) for k, v in tot.items()},
        "usd_estimate": {
            "total": round(sum(usd_model.values())),
            "by_model": {k: round(v) for k, v in usd_model.items()},
            "by_class": {k: round(v) for k, v in usd_class.items()},
            "by_kind": {k: round(v) for k, v in usd_kind.items()},
        },
        "usd_cost_state_main_sessions": round(
            sum((S[f]["cost"] or {}).get("totalCostUSD") or 0 for f in S if not S[f]["is_sub"]), 1
        ),
        "context_per_call": {"p50": q(0.5), "p90": q(0.9), "max": ctxs[-1], "mean": round(st.mean(ctxs))},
        "context_bands": bands,
        "cache": {
            "rebuilds": sum(rebuild.values()),
            "rebuilds_by_cause": dict(rebuild),
            "rebuild_units_pct": c.pct(rebuild_units, U),
            "gaps_over_5m": sum(g > 300 for g in gaps),
            "gaps_over_1h": sum(g > 3600 for g in gaps),
            "write_tokens_main": {
                "w5": sum(x["w5"] for x in calls if not x["is_sub"]),
                "w1h": sum(x["w1h"] for x in calls if not x["is_sub"]),
            },
            "write_tokens_subagent": {
                "w5": sum(x["w5"] for x in calls if x["is_sub"]),
                "w1h": sum(x["w1h"] for x in calls if x["is_sub"]),
            },
        },
        "scaling": {
            "main_n": len(main_pts),
            "main_exponent": round(slope(main_pts), 2),
            "subagent_n": len(sub_pts),
            "subagent_exponent": round(slope(sub_pts), 2),
            "longest_main_transcripts": longest,
        },
        "top_session_groups": top_groups,
        "subagent_units_pct": c.pct(sum(x["units"] for x in calls if x["is_sub"]), U),
        "skill_attribution_units_pct": {k: c.pct(v, U) for k, v in skill.most_common()},
    }
    c.write_result(
        args.results,
        "inventory",
        "inventory",
        c.extract_inputs(args.data) | {"prs.json": args.data / "prs.json"},
        payload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
