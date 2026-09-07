#!/usr/bin/env python3
"""Derivation for RFC-0015 Tables 2 and 3: where a PR's review findings sit.

For each PR number given, walk ``pulls/<N>/comments`` (``per_page=100``,
paged until a short page), keep the rows with no ``in_reply_to_id`` (findings,
not replies), and group them by ``pull_request_review_id`` in first-seen order,
which is submission order.

Two classifications per finding:

* **Artifact class** (Table 3): ``code`` when ``path`` starts with ``src/`` or
  ``tests/``, ``prose`` otherwise; ``record`` marks the prose subset on
  ``sdd/traces/``, ``sdd/BACKLOG.md`` or ``sdd/BACKLOG-DONE.md``.
* **Origin** (Table 2): ``git blame`` of ``original_line`` at
  ``original_commit_id`` (the head the reviewer saw), classified against that
  head's own history — ``base`` is its merge-base with ``origin/master``,
  ``first`` the first commit after ``base`` on its first-parent line, i.e. the
  implementation push. ``original`` when the blamed commit is ``first``;
  ``pre-existing`` when it is reachable from ``base``; ``loop-introduced``
  otherwise (a fix-pass commit). A finding with ``subject_type == "file"``, no
  ``original_line`` or ``side == "LEFT"`` has no blameable line and is
  ``unclassifiable``. Bounds are computed per head because a rebase moves both
  ``base`` and ``first``; a head absent locally is fetched by SHA.

Requires ``gh`` authenticated and ``origin/master`` fetched.

Usage::

    python sdd/rfcs/rfc-0015-findings.py 964 965 968 971 972 973 974 976 977 \\
        978 983 986 987 989 990 991 992 994 996
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO = "haalfi/remote-store"
ROOT = Path(__file__).resolve().parents[2]

_HEADS: dict[str, tuple[str, str]] = {}


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check, capture_output=True, text=True)


def fetch_findings(pr: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        out = subprocess.run(
            ["gh", "api", f"repos/{REPO}/pulls/{pr}/comments?per_page=100&page={page}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        batch = json.loads(out)
        rows.extend(r for r in batch if r.get("in_reply_to_id") is None)
        if len(batch) < 100:
            return rows
        page += 1


def artifact_class(path: str) -> str:
    return "code" if path.startswith(("src/", "tests/")) else "prose"


def is_record(path: str) -> bool:
    return path.startswith("sdd/traces/") or path in ("sdd/BACKLOG.md", "sdd/BACKLOG-DONE.md")


def head_bounds(sha: str) -> tuple[str, str]:
    if sha not in _HEADS:
        if _git("cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
            _git("fetch", "-q", "origin", sha)
        base = _git("merge-base", "origin/master", sha).stdout.strip()
        first = _git("rev-list", "--first-parent", "--reverse", f"{base}..{sha}").stdout.split()[0]
        _HEADS[sha] = (base, first)
    return _HEADS[sha]


def origin(r: dict) -> str:
    line = r.get("original_line")
    if r.get("subject_type") == "file" or line is None or r.get("side") == "LEFT":
        return "unclassifiable"
    base, first = head_bounds(r["original_commit_id"])
    blame = _git("blame", "-l", "-L", f"{line},{line}", r["original_commit_id"], "--", r["path"], check=False)
    if blame.returncode != 0:
        return "unclassifiable"
    blamed = blame.stdout.split()[0].lstrip("^")
    if blamed == first:
        return "original"
    if _git("merge-base", "--is-ancestor", blamed, base, check=False).returncode == 0:
        return "pre-existing"
    return "loop-introduced"


def main(prs: list[int]) -> None:
    by_index: dict[int, Counter[str]] = {}
    grand: Counter[str] = Counter()
    for pr in prs:
        rounds: OrderedDict[int, list[dict]] = OrderedDict()
        for r in fetch_findings(pr):
            rounds.setdefault(r["pull_request_review_id"], []).append(r)
        cells = []
        for i, rs in enumerate(rounds.values(), 1):
            c: Counter[str] = Counter()
            for r in rs:
                c[artifact_class(r["path"])] += 1
                c["record"] += is_record(r["path"])
                c[origin(r)] += 1
            by_index.setdefault(i, Counter()).update(c)
            grand.update(c)
            cells.append(
                f"r{i}: {c['code']}c/{c['prose']}p"
                f" o{c['original']} l{c['loop-introduced']} p{c['pre-existing']} u{c['unclassifiable']}"
            )
        grand["submissions"] += len(rounds)
        print(
            f"PR #{pr}: {len(rounds)} submissions, {sum(len(v) for v in rounds.values())} findings | "
            + "  ".join(cells)
        )
    print(
        f"TOTAL: {grand['submissions']} submissions; code {grand['code']}, prose {grand['prose']} "
        f"(record {grand['record']}); original {grand['original']}, loop-introduced {grand['loop-introduced']}, "
        f"pre-existing {grand['pre-existing']}, unclassifiable {grand['unclassifiable']}"
    )
    print("BY ROUND INDEX: original / loop-introduced / loop share of classified | unclassifiable")
    for i in sorted(by_index):
        c = by_index[i]
        classified = c["original"] + c["loop-introduced"] + c["pre-existing"]
        share = f"{c['loop-introduced'] / classified:.0%}" if classified else "-"
        print(f"  r{i}: {c['original']} / {c['loop-introduced']} / {share} | {c['unclassifiable']}")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
