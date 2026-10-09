"""Per review round: how many findings, where they land (code or prose), and whether the loop caused them.

Two sources:

1. **Origin per round** from the derived ``review:`` blocks in
   ``sdd/traces`` (``by_round[].origin``): a finding is *loop-introduced* when
   an earlier fix in the same loop caused it. Rounds 9 and above are pooled.
2. **Where findings land**, from the GitHub review comments of the same PRs:
   top-level comments only (replies carry a ``replyTo``), each review
   submission with comments counted as one round in submission order, each
   comment's path classed as code/test, prose or trace.

The comment cache (path and category prefix per comment, no bodies) is kept
in ``--data/round_comments.json``; PRs already in it are not fetched again.
Writes ``results/rounds.json``.
"""

from __future__ import annotations

import collections
import json
import re
import statistics as st
import subprocess

import _common as c
import yaml

PROSE = re.compile(r"(\.md$|\.yml$|\.yaml$|\.txt$|^sdd/|^docs-src/|\.claude/skills/|\.claude/agents/|CHANGELOG|README)")
CODE = re.compile(r"^(src/|tests/|scripts/|examples/|\.claude/hooks/|\.github/)|\.py$|\.sh$|\.dfy$|\.tla$")
Q = (
    "query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){"
    "reviews(first:100){nodes{submittedAt comments(first:100){nodes{path body replyTo{id}}}}}}}}"
)


def kind(path):
    if not path:
        return "pr-level"
    if path.startswith("sdd/traces/"):
        return "trace"
    if CODE.search(path) and not path.endswith(".md"):
        return "code/test"
    return "prose" if PROSE.search(path) else "other"


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--repo", default="haalfi/remote-store", help="GitHub owner/name")
    args = c.resolve(ap.parse_args(argv))
    owner, name = args.repo.split("/")
    blocks = []
    for f in sorted((args.repo_root / "sdd" / "traces").glob("*.yml")):
        if f.name.startswith("_"):
            continue
        rv = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("review")
        if isinstance(rv, dict) and rv.get("pr") and rv.get("findings"):
            blocks.append(rv)

    origin = collections.defaultdict(collections.Counter)
    for rv in blocks:
        for r in rv.get("by_round") or []:
            for k, v in (r.get("origin") or {}).items():
                origin[min(r["round"], 9)][k] += v

    cache = args.data / "round_comments.json"
    data = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    for rv in blocks:
        pr = str(rv["pr"])
        if pr in data:
            continue
        out = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={Q}", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"n={pr}"],
            capture_output=True, text=True, encoding="utf-8",
        ).stdout  # fmt: skip
        try:
            nodes = json.loads(out)["data"]["repository"]["pullRequest"]["reviews"]["nodes"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        revs = []
        for n in nodes:
            if not n["submittedAt"]:
                continue
            cs = [
                {"path": x["path"], "cat": (re.match(r"\s*\**\s*([A-Za-z-]+)\s*:", x["body"] or "") or [None, "?"])[1]}
                for x in n["comments"]["nodes"]
                if not x.get("replyTo")
            ]
            if cs:
                revs.append({"at": n["submittedAt"], "comments": cs})
        data[pr] = revs
    args.data.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")

    where = collections.defaultdict(collections.Counter)
    tail = []
    for revs in data.values():
        revs = sorted(revs, key=lambda r: r["at"])
        for i, rv in enumerate(revs, 1):
            for x in rv["comments"]:
                where[min(i, 9)][kind(x["path"])] += 1
        if revs:
            code_idx = [i for i, r in enumerate(revs, 1) if any(kind(x["path"]) == "code/test" for x in r["comments"])]
            tail.append(len(revs) - (max(code_idx) if code_idx else 0))
    total = collections.Counter()
    for cnt in where.values():
        total.update(cnt)

    def label(b):
        return str(b) if b < 9 else "9+"

    payload = {
        "trace_review_blocks": len(blocks),
        "origin_by_round": {
            label(b): {
                "findings": sum(cnt.values()),
                "loop_introduced_pct": c.pct(cnt["loop-introduced"], sum(cnt.values()), 0),
            }
            for b, cnt in sorted(origin.items())
        },
        "comments": {"prs": len(data), "top_level": sum(total.values()), "by_kind": dict(total)},
        "prose_and_trace_share_by_round_pct": {
            label(b): c.pct(cnt["prose"] + cnt["trace"], sum(cnt.values()), 0) for b, cnt in sorted(where.items())
        },
        "rounds_after_last_code_finding": {
            "median": st.median(tail),
            "share_two_or_more_pct": c.pct(sum(1 for x in tail if x >= 2), len(tail), 0),
            "prs": len(tail),
        },
    }
    c.write_result(args.results, "rounds", "rounds", {"round_comments.json": cache}, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
