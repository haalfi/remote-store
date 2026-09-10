#!/usr/bin/env python3
"""Derivation for RFC-0015 Tables 2, 3 and 4: where a PR's review findings sit.

For each PR number given, walk ``pulls/<N>/comments`` (``per_page=100``,
paged until a short page). Rows with no ``in_reply_to_id`` are *findings*;
rows with one are the fixer's *replies* to them (``/rvw-pr`` never reads or
answers comments, so every reply in a thread is the fix pass speaking). Findings
are grouped by ``pull_request_review_id`` in first-seen order, which is
submission order; ``pulls/<N>/reviews`` supplies each submission's time.

Three classifications per finding:

* **Artifact class** (Table 3): ``code`` when ``path`` starts with ``src/`` or
  ``tests/``, ``prose`` otherwise; ``record`` marks the prose subset on
  ``sdd/traces/``, ``sdd/BACKLOG.md`` or ``sdd/BACKLOG-DONE.md``.
* **Origin** (Table 2): ``git blame`` of ``original_line`` at
  ``original_commit_id`` (the head the reviewer saw) names the commit that last
  touched the line. ``pre-existing`` when that commit is reachable from
  ``origin/master`` (untouched code, or a merge from master). Otherwise the
  commit's **author date** is compared with the submission time of the PR's
  first review that carried a finding: earlier is ``original`` (written before
  any review began, whatever the number of commits in the first push), later
  is ``loop-introduced`` (a fix-pass commit). Author dates survive rebases,
  which commit identity does not. A finding with ``subject_type == "file"``,
  no ``original_line`` or ``side == "LEFT"`` has no blameable line and is
  ``unclassifiable``; a head absent locally is fetched by SHA.
  Bound: a commit authored before round 1 but pushed after it would read as
  ``original``; this repo's loop pushes before spawning reviewers, so the case
  is not expected and is not measured here.
* **Triage** (Table 4): the first reply in the finding's thread is read for the
  fixer's verdict — ``must-fix`` when it says "Must-fix", "Fixed in",
  "Confirmed", "Correct", "Taken", "Added" or "Annotated"; ``filed`` when it
  says "Filed as" or mints an ID; ``refuted`` when it says "refut",
  "not a defect", "declin", "rejected" or "stays"; ``unknown`` otherwise,
  including threads with no reply. A heuristic over free text, stated as one:
  the counts it yields are bounded by the share it leaves ``unknown``.

Also printed:

* the share of sampled PRs whose first push (merge-base to the round-1 head,
  first-parent) had more than one commit — the bound on the single-commit
  premise an earlier revision of this script assumed;
* a dry run of RFC-0015 D5's retraction trigger over the sample, under three
  readings. ``classified``: a round "fires" when it and the previous round each
  carry at least one classified must-fix finding and none of theirs is
  ``original`` or ``pre-existing``. ``unclassifiable-as-loop``: the same, with
  unclassifiable must-fix findings counted as loop-introduced.
  ``share>=80%,n>=2``: both rounds have at least two classified must-fix
  findings and at least 80% of them are loop-introduced.

Requires ``gh`` authenticated and ``origin/master`` fetched.

Usage::

    python sdd/rfcs/rfc-0015-findings.py 964 965 968 971 972 973 974 976 977 \\
        978 983 986 987 989 990 991 992 994 996
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

REPO = "haalfi/remote-store"
ROOT = Path(__file__).resolve().parents[2]

_MUST_FIX = re.compile(r"Must-fix|Fixed in|Confirmed|Correct|Taken|Added|Annotated", re.I)
_FILED = re.compile(r"Filed as|\b(?:BK|BUG|ID)-\d+ (?:now|filed|minted)", re.I)
_REFUTED = re.compile(r"refut|not a defect|declin|rejected|\bstays\b", re.I)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check, capture_output=True, text=True)


def _gh(path: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        out = subprocess.run(
            ["gh", "api", f"repos/{REPO}/{path}?per_page=100&page={page}"], check=True, capture_output=True, text=True
        ).stdout
        batch = json.loads(out)
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())


def artifact_class(path: str) -> str:
    return "code" if path.startswith(("src/", "tests/")) else "prose"


def is_record(path: str) -> bool:
    return path.startswith("sdd/traces/") or path in ("sdd/BACKLOG.md", "sdd/BACKLOG-DONE.md")


def ensure_commit(sha: str) -> None:
    if _git("cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
        _git("fetch", "-q", "origin", sha)


def origin(r: dict, first_review_ts: int) -> str:
    line = r.get("original_line")
    if r.get("subject_type") == "file" or line is None or r.get("side") == "LEFT":
        return "unclassifiable"
    head = r["original_commit_id"]
    ensure_commit(head)
    blame = _git("blame", "-l", "-L", f"{line},{line}", head, "--", r["path"], check=False)
    if blame.returncode != 0:
        return "unclassifiable"
    blamed = blame.stdout.split()[0].lstrip("^")
    if _git("merge-base", "--is-ancestor", blamed, "origin/master", check=False).returncode == 0:
        return "pre-existing"
    authored = int(_git("show", "-s", "--format=%at", blamed).stdout.strip())
    return "original" if authored < first_review_ts else "loop-introduced"


def triage(reply: str | None) -> str:
    if reply is None:
        return "unknown"
    if _MUST_FIX.search(reply):
        return "must-fix"
    if _FILED.search(reply):
        return "filed"
    if _REFUTED.search(reply):
        return "refuted"
    return "unknown"


def main(prs: list[int]) -> None:
    by_index: dict[int, Counter[str]] = {}
    grand: Counter[str] = Counter()
    multi_commit_first_push = 0
    fired = {"classified": Counter(), "unclassifiable-as-loop": Counter(), "share>=80%,n>=2": Counter()}
    for pr in prs:
        comments = _gh(f"pulls/{pr}/comments")
        findings = [c for c in comments if c.get("in_reply_to_id") is None]
        first_reply: dict[int, str] = {}
        for c in sorted((c for c in comments if c.get("in_reply_to_id")), key=lambda c: c["created_at"]):
            first_reply.setdefault(c["in_reply_to_id"], c["body"])
        review_ts = {rv["id"]: _ts(rv["submitted_at"]) for rv in _gh(f"pulls/{pr}/reviews") if rv.get("submitted_at")}
        rounds: OrderedDict[int, list[dict]] = OrderedDict()
        for f in findings:
            rounds.setdefault(f["pull_request_review_id"], []).append(f)
        first_review_ts = min(review_ts[rid] for rid in rounds)
        first_head = next(iter(rounds.values()))[0]["original_commit_id"]
        ensure_commit(first_head)
        base = _git("merge-base", "origin/master", first_head).stdout.strip()
        first_push = len(_git("rev-list", "--first-parent", f"{base}..{first_head}").stdout.split())
        multi_commit_first_push += first_push > 1

        cells = []
        prev: dict[str, Counter[str] | None] = {k: None for k in fired}
        for i, rs in enumerate(rounds.values(), 1):
            c: Counter[str] = Counter()
            for f in rs:
                o = origin(f, first_review_ts)
                t = triage(first_reply.get(f["id"]))
                c[artifact_class(f["path"])] += 1
                c["record"] += is_record(f["path"])
                c[o] += 1
                c[t] += 1
                if t == "must-fix":
                    c[f"mf-{o}"] += 1
            by_index.setdefault(i, Counter()).update(c)
            grand.update(c)
            cells.append(
                f"r{i}: {c['code']}c/{c['prose']}p o{c['original']} l{c['loop-introduced']} "
                f"p{c['pre-existing']} u{c['unclassifiable']} | mf o{c['mf-original']} l{c['mf-loop-introduced']} "
                f"p{c['mf-pre-existing']} u{c['mf-unclassifiable']} | filed {c['filed']} refuted {c['refuted']} ?{c['unknown']}"
            )
            # D5 dry run, two readings
            for reading in fired:
                loop = c["mf-loop-introduced"] + (c["mf-unclassifiable"] if reading == "unclassifiable-as-loop" else 0)
                clean = c["mf-original"] + c["mf-pre-existing"]
                this = Counter(loop=loop, clean=clean)
                p = prev[reading]
                if reading == "share>=80%,n>=2":
                    hot = lambda x: (x["loop"] + x["clean"]) >= 2 and x["loop"] / (x["loop"] + x["clean"]) >= 0.8  # noqa: E731
                    if p is not None and hot(p) and hot(this):
                        fired[reading][pr] += 1
                elif p is not None and p["loop"] > 0 and p["clean"] == 0 and this["loop"] > 0 and this["clean"] == 0:
                    fired[reading][pr] += 1
                prev[reading] = this
        grand["submissions"] += len(rounds)
        print(
            f"PR #{pr}: {len(rounds)} submissions, {len(findings)} findings, first push {first_push} commit(s) | "
            + "  ".join(cells)
        )
    n = len(prs)
    print(
        f"TOTAL: {grand['submissions']} submissions; code {grand['code']}, prose {grand['prose']} "
        f"(record {grand['record']}); original {grand['original']}, loop-introduced {grand['loop-introduced']}, "
        f"pre-existing {grand['pre-existing']}, unclassifiable {grand['unclassifiable']}; "
        f"triage must-fix {grand['must-fix']}, filed {grand['filed']}, refuted {grand['refuted']}, unknown {grand['unknown']}"
    )
    print(f"FIRST PUSH >1 COMMIT: {multi_commit_first_push} of {n} PRs")
    print(
        "BY ROUND INDEX: all findings original / loop-introduced / loop share | unclassifiable || must-fix only: o / l / share | u"
    )
    for i in sorted(by_index):
        c = by_index[i]
        cl = c["original"] + c["loop-introduced"] + c["pre-existing"]
        mcl = c["mf-original"] + c["mf-loop-introduced"] + c["mf-pre-existing"]
        share = f"{c['loop-introduced'] / cl:.0%}" if cl else "-"
        mshare = f"{c['mf-loop-introduced'] / mcl:.0%}" if mcl else "-"
        print(
            f"  r{i}: {c['original']} / {c['loop-introduced']} / {share} | {c['unclassifiable']} || "
            f"{c['mf-original']} / {c['mf-loop-introduced']} / {mshare} | {c['mf-unclassifiable']}"
        )
    for reading, counter in fired.items():
        print(
            f"D5 TRIGGER ({reading}): fires in {len(counter)} of {n} PRs, {sum(counter.values())} round(s) total: "
            + ", ".join(f"#{pr}x{k}" for pr, k in sorted(counter.items()))
        )


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
