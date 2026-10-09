"""Before and after ``/ship`` (2026-08-05): entries leaving the backlog by prefix, and review activity per PR.

An entry leaves the backlog in the month its ``- [x] **PREFIX-NNN`` header
first appears in ``sdd/BACKLOG-DONE.md`` (``git log -p``, oldest first; a
header that moves within the file is not counted again). That is every exit,
done, absorbed or decided against, dated by commit, not by release.

Reads git, ``--data/prs.json`` and ``--data/corpus.json``; writes
``results/ship_era.json``.
"""

from __future__ import annotations

import collections
import json
import re
import statistics as st
import subprocess

import _common as c

SHIP = "2026-08-05"
HEADER = re.compile(r"^\+- \[x\] \*\*((BUG|BK|ID)-\d+[a-z]?)")


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(args.repo_root), *a], capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout

    seen: set = set()
    left = collections.defaultdict(collections.Counter)
    month = None
    log = git("log", "--reverse", "--format=@%aI", "-p", "--unified=0", "--", "sdd/BACKLOG-DONE.md")
    for line in log.splitlines():
        if line.startswith("@") and not line.startswith("@@"):
            month = line[1:8]
            continue
        m = HEADER.match(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            left[month][m.group(2)] += 1
    ids = {
        m: {**dict(cnt), "bug_share_pct": c.pct(cnt["BUG"], sum(cnt.values()), 0)} for m, cnt in sorted(left.items())
    }
    prs = c.load_prs(args.data)
    era = collections.defaultdict(list)
    for p in prs:
        if p["created"] >= SHIP:
            era["after /ship"].append(p)
        elif p["created"] >= "2026-05-01":
            era["May-Jul"].append(p)
    eras = {
        e: {
            "prs": len(ps),
            "review_threads_median": st.median(p["threads"] for p in ps),
            "commits_median": st.median(p["commits"] for p in ps),
        }
        for e, ps in era.items()
    }
    corpus = json.loads((args.data / "corpus.json").read_text(encoding="utf-8"))
    bym = collections.defaultdict(list)
    for r in corpus:
        bym[r["month"]].append(r)
    followups = {m: round(st.mean(r["disc"] for r in rs), 2) for m, rs in sorted(bym.items())}
    head = git("rev-parse", "--short", "HEAD").strip()
    payload = {"backlog_exits_by_month": ids, "eras": eras, "discovery_followups_per_trace": followups}
    inputs = {
        "BACKLOG-DONE.md history at commit": head,
        "prs.json": args.data / "prs.json",
        "corpus.json": args.data / "corpus.json",
    }
    c.write_result(args.results, "ship_era", "ship_era", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
