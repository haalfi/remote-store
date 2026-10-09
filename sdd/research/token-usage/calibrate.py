"""Calibrate characters to tokens, and units to dollars.

1. **Tokens per character.** Between two consecutive calls of one transcript
   and segment, context grows by what entered between them. A least-squares
   fit without intercept of that growth on the characters that entered (tool
   results; attachments and user text; visible assistant output) plus the
   previous call's hidden output tokens gives one coefficient per kind. These
   are ``_common.COEF``.
2. **Dollars per unit.** Claude Code's ``cost-state`` records give dollars
   and token counts per model per session. With the class ratios fixed
   (read 0.1, output 5) and the write weight searched on a grid, a fit per
   model gives the input-token price. These are ``_common.PRICE``.

Reads ``--data``, writes ``results/calibration.json``.
"""

from __future__ import annotations

import collections
import statistics as st

import _common as c


def solve(X, Y):
    n = len(X[0])
    A = [
        [sum(x[i] * x[j] for x in X) for j in range(n)] + [sum(x[i] * y for x, y in zip(X, Y, strict=False))]
        for i in range(n)
    ]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        for r in range(n):
            if r != i:
                f = A[r][i] / A[i][i]
                A[r] = [x - f * y for x, y in zip(A[r], A[i], strict=False)]
    return [A[i][n] / A[i][i] for i in range(n)]


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))
    calls, items, S = c.load_extract(args.data)
    bycall = c.by_file(calls)
    entered = collections.defaultdict(collections.Counter)
    visible = collections.Counter()
    for it in items:
        k = it["kind"]
        # Visible thinking text is left out of the regressors (the hidden-output term covers
        # thinking) but still counts as visible output when deriving the hidden part.
        if k == "assistant_thinking":
            g = "thinking"
        elif k.startswith("assistant"):
            g = "assistant"
        else:
            g = "tool_result" if k.startswith("tool_result") else "other"
        entered[(it["file"], it["enter"])][g] += it["chars"]
        if k.startswith("assistant"):
            visible[(it["file"], it["enter"])] += it["chars"]
    X, Y = [], []
    for f, cs in bycall.items():
        for a, b in zip(cs, cs[1:], strict=False):
            if b["seg"] != a["seg"] or b["ctx"] < a["ctx"]:
                continue
            e = entered[(f, b["idx"])]
            hidden = max(0, a["out"] - visible[(f, b["idx"])] / 4)
            X.append([e["tool_result"], e["other"], e["assistant"], hidden])
            Y.append(b["ctx"] - a["ctx"])
    coef = solve(X, Y)
    pred = [sum(k * x for k, x in zip(coef, xx, strict=False)) for xx in X]
    my = st.mean(Y)
    r2 = 1 - sum((y - p) ** 2 for y, p in zip(Y, pred, strict=False)) / sum((y - my) ** 2 for y in Y)
    names = ["tool_result", "attachment_and_user", "assistant_visible", "hidden_output"]

    rows = collections.defaultdict(list)
    for s in S.values():
        for m, v in ((s["cost"] or {}).get("modelUsage") or {}).items():
            if v.get("costUSD", 0) > 0.05:
                x = [
                    v.get(k, 0)
                    for k in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
                ]
                rows[m].append((x, v["costUSD"]))
    prices = {}
    for m, rs in rows.items():

        def units(x, w):
            return x[0] + 0.1 * x[1] + w * x[2] + 5 * x[3]

        best = None
        for w in [1.25 + 0.05 * i for i in range(16)]:
            p = sum(cost * units(x, w) for x, cost in rs) / sum(units(x, w) ** 2 for x, cost in rs)
            err = sum((cost - p * units(x, w)) ** 2 for x, cost in rs)
            if best is None or err < best[0]:
                best = (err, w, p)
        _, w, p = best
        mape = st.mean(abs(cost - p * units(x, w)) / cost for x, cost in rs)
        prices[m] = {
            "n": len(rs),
            "usd_per_mtok_input": round(p * 1e6, 2),
            "write_weight": round(w, 2),
            "mean_abs_error_pct": round(mape * 100, 1),
        }

    payload = {
        "pairs": len(X),
        "r2": round(r2, 3),
        "tokens_per_char": {n: round(k, 3) for n, k in zip(names[:3], coef[:3], strict=False)},
        "chars_per_token": {n: round(1 / k, 2) for n, k in zip(names[:3], coef[:3], strict=False)},
        "context_per_hidden_output_token": round(coef[3], 3),
        "price_fit": prices,
    }
    c.write_result(args.results, "calibration", "calibrate", c.extract_inputs(args.data), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
