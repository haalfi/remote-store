"""What the sessions between two `/ship` runs cost, by purpose and by PR.

Every local session that started inside ``--since``/``--until`` is read with
its subagents. Each assistant record's units are bucketed by the record's
``gitBranch``, because one session often served several PRs. A class map
then assigns each session, and optionally each of its branches, a class and
a PR:

    {"<session id>": {"class": "a", "pr": 1105, "label": "BK-419 gate lock",
                      "branches": {"<branch>": {"class": "c", "pr": 1101}}},
     "_exclude": ["<session id>", ...]}

Classes: ``a`` means that act on later deliveries, ``b`` measurement and
analysis, ``c`` experiment setup, ``d`` unrelated work in the same window. The
map is keyed by session ID, so like the extracts it stays in ``--data`` and
only its hash is recorded; ``label`` is the only text from it that reaches
the result, so labels must not hold IDs or paths.

    python prep_cost.py --data DIR --since ISO --until ISO [--name prep_cost]

Writes ``results/<--name>.json``: totals per class and per PR, and the
costliest sessions by label. A session the map does not name is an error.
"""

from __future__ import annotations

import collections
import json
from typing import TYPE_CHECKING

import _common as c

if TYPE_CHECKING:
    from pathlib import Path


def units(u: dict) -> float:
    cc = u.get("cache_creation") or {}
    w5 = cc.get("ephemeral_5m_input_tokens", 0) if cc else u.get("cache_creation_input_tokens", 0)
    w1h = cc.get("ephemeral_1h_input_tokens", 0) if cc else 0
    return (
        c.W["input"] * u.get("input_tokens", 0)
        + c.W["read"] * u.get("cache_read_input_tokens", 0)
        + c.W["w5"] * w5
        + c.W["w1h"] * w1h
        + c.W["out"] * u.get("output_tokens", 0)
    )


def session(main: Path) -> dict:
    """Units per git branch, dollars, calls and peak main context, over a main transcript and its subagents."""
    files = [main] + sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))
    by_branch: dict[str, float] = collections.defaultdict(float)
    seen, calls, usd, peak, compactions = set(), 0, 0.0, 0, 0
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if f == main and r.get("type") == "system" and r.get("subtype") == "compact_boundary":
                compactions += 1
            m = r.get("message")
            if r.get("type") != "assistant" or not isinstance(m, dict):
                continue
            u, mid = m.get("usage"), m.get("id")
            if not isinstance(u, dict) or m.get("model") == "<synthetic>" or mid in seen:
                continue
            seen.add(mid)
            x = units(u)
            calls += 1
            by_branch[r.get("gitBranch") or "?"] += x
            usd += x * c.PRICE.get(m.get("model") or "", c.PRICE["claude-opus-5-5"])
            if f == main:
                ctx = (
                    u.get("input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0)
                )
                peak = max(peak, ctx)
    return {"by_branch": by_branch, "calls": calls, "usd": usd, "peak_ctx": peak, "compactions": compactions}


def first_ts(path: Path) -> str | None:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                t = json.loads(line).get("timestamp")
            except json.JSONDecodeError:
                continue
            if t:
                return t
    return None


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--classes", default="prep_classes.json", help="class map file inside --data")
    ap.add_argument("--since", required=True, help="ISO timestamp: first session start counted")
    ap.add_argument("--until", required=True, help="ISO timestamp: sessions starting after it are left out")
    ap.add_argument("--name", default="prep_cost", help="result file name")
    args = c.resolve(ap.parse_args(argv))
    cmap_path = args.data / args.classes
    cmap = json.loads(cmap_path.read_text(encoding="utf-8"))
    exclude = set(cmap.get("_exclude", []))

    rows = []
    for d in c.default_transcripts(args.repo_root):
        for p in d.glob("*.jsonl"):
            t = first_ts(p)
            if not t or not (args.since <= t <= args.until) or p.stem in exclude:
                continue
            s = session(p)
            if not s["calls"]:
                continue
            if p.stem not in cmap:
                raise SystemExit(f"session {p.stem} is not in the class map")
            rows.append((p.stem, s, p))

    by_class: dict[str, float] = collections.defaultdict(float)
    by_pr: dict = collections.defaultdict(lambda: {"units": 0.0, "classes": set(), "sessions": 0})
    for sid, s, _ in rows:
        e = cmap[sid]
        for br, u in s["by_branch"].items():
            o = e.get("branches", {}).get(br, {})
            cls, pr = o.get("class", e["class"]), o.get("pr", e.get("pr"))
            by_class[cls] += u
            if pr:
                by_pr[pr]["units"] += u
                by_pr[pr]["classes"].add(cls)
        for pr in {o.get("pr") for o in e.get("branches", {}).values()} | {e.get("pr")}:
            if pr:
                by_pr[pr]["sessions"] += 1

    rate = c.PRICE["claude-opus-5-5"]
    total = sum(by_class.values())
    prep = by_class["a"] + by_class["b"] + by_class["c"]
    top = sorted(rows, key=lambda r: -sum(r[1]["by_branch"].values()))[:5]
    payload = {
        "window": {"since": args.since, "until": args.until},
        "sessions": len(rows),
        "calls": sum(s["calls"] for _, s, _ in rows),
        "sessions_compacted": sum(1 for _, s, _ in rows if s["compactions"]),
        "units_m_by_class": {k: round(by_class[k] / 1e6, 2) for k in "abcd"},
        "usd_by_class": {k: round(by_class[k] * rate, 2) for k in "abcd"},
        "preparation_units_m": round(prep / 1e6, 2),
        "preparation_usd": round(prep * rate, 2),
        "all_units_m": round(total / 1e6, 2),
        "by_pr": {
            str(pr): {
                "units_m": round(v["units"] / 1e6, 2),
                "classes": sorted(v["classes"]),
                "sessions": v["sessions"],
            }
            for pr, v in sorted(by_pr.items())
        },
        "costliest": [
            {
                "label": cmap[sid].get("label", ""),
                "units_m": round(sum(s["by_branch"].values()) / 1e6, 2),
                "peak_ctx_k": round(s["peak_ctx"] / 1e3),
                "compactions": s["compactions"],
            }
            for sid, s, _ in top
        ],
    }
    inputs: dict[str, Path | str] = {"class map": cmap_path}
    inputs.update({f"transcript {i}": p for i, (_, _, p) in enumerate(rows)})
    c.write_result(args.results, args.name, "prep_cost", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
