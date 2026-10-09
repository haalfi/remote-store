"""Aggregate the prose-finding classification by round band, checkability and target kind.

Each prose finding was classified once, LLM-assisted, against a fixed rubric:

* ``cls``: SCOPE (an overstated "every"/"all", a missing case or bound),
  FACT (a wrong count, path, line reference or behaviour claim), MIRROR (two
  artifacts or two places disagree), RULE (a written rule broken), DESIGN
  (disagreement with the decision itself), CLARITY (wording, structure,
  placement).
* ``checkable``: mechanical (a command, grep, count or link check settles
  it), enumeration (settled by listing the cases), judgment.
* ``loop_ref``: the finding says an earlier fix of the same PR caused it.
* ``target_kind``: the kind of file it is on.

The classification cannot be re-run identically, so the labels are the
committed record (``results/prose_labels.json``: key, PR, round and the four
labels, no comment text). ``--build`` creates that file from
``--data/prose_findings.json`` (prose_fetch.py) and the classifier's batch
outputs ``--data/prose_cls_*.json``; without it, this script only
aggregates the committed labels. A fixed-seed sample of ten keys is printed
with their bodies, when ``prose_findings.json`` is present, for a spot check.

Writes ``results/prose_classes.json``.
"""

from __future__ import annotations

import collections
import json
import random

import _common as c

FIELDS = ("cls", "checkable", "loop_ref", "target_kind")


def band(r: int) -> str:
    return "rounds 1-2" if r <= 2 else "rounds 3-4" if r <= 4 else "rounds 5-8" if r <= 8 else "rounds 9+"


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--build", action="store_true", help="rebuild prose_labels.json from --data first")
    args = c.resolve(ap.parse_args(argv))
    labels_path = args.results / "prose_labels.json"
    findings_path = args.data / "prose_findings.json"
    src = {f["key"]: f for f in json.loads(findings_path.read_text(encoding="utf-8"))} if findings_path.exists() else {}
    if args.build:
        cls = {}
        for p in sorted(args.data.glob("prose_cls_*.json")):
            for x in json.loads(p.read_text(encoding="utf-8")):
                cls[x["key"]] = x
        rows = [
            {"key": k, "pr": src[k]["pr"], "round": src[k]["round"], **{f: cls[k][f] for f in FIELDS}}
            for k in src
            if k in cls
        ]
        inputs = {"prose_findings.json": findings_path} | {
            p.name: p for p in sorted(args.data.glob("prose_cls_*.json"))
        }
        c.write_result(
            args.results,
            "prose_labels",
            "prose_classes",
            inputs,
            {"unlabelled": len(set(src) - set(cls)), "labels": rows},
        )
    rows = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]

    def table(keyf, field):
        t = collections.defaultdict(collections.Counter)
        for r in rows:
            t[keyf(r)][r[field]] += 1
        return {
            k: {v: c.pct(n, sum(cnt.values()), 0) for v, n in sorted(cnt.items())} | {"n": sum(cnt.values())}
            for k, cnt in sorted(t.items())
        }

    total = len(rows)
    payload = {
        "findings": total,
        "prs": len({r["pr"] for r in rows}),
        "class_counts": dict(collections.Counter(r["cls"] for r in rows).most_common()),
        "checkable_counts": dict(collections.Counter(r["checkable"] for r in rows).most_common()),
        "class_pct": {k: c.pct(v, total, 0) for k, v in collections.Counter(r["cls"] for r in rows).most_common()},
        "checkable_pct": {
            k: c.pct(v, total, 0) for k, v in collections.Counter(r["checkable"] for r in rows).most_common()
        },
        "class_by_round_band_pct": table(lambda r: band(r["round"]), "cls"),
        "loop_ref_by_round_band_pct": {
            b: c.pct(
                sum(1 for r in rows if band(r["round"]) == b and r["loop_ref"]),
                sum(1 for r in rows if band(r["round"]) == b),
                0,
            )
            for b in sorted({band(r["round"]) for r in rows})
        },
        "findings_by_target_kind": dict(collections.Counter(r["target_kind"] for r in rows).most_common()),
    }
    random.seed(7)
    sample = random.sample(rows, 10)
    payload["spot_check_keys"] = [r["key"] for r in sample]
    for r in sample:
        body = " ".join((src.get(r["key"], {}).get("body") or "(body not in --data)").split())[:300]
        print(f"[{r['key']}] {r['cls']}/{r['checkable']} loop={r['loop_ref']} :: {body}\n")
    c.write_result(args.results, "prose_classes", "prose_classes", {"prose_labels.json": labels_path}, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
