#!/usr/bin/env python3
"""Derivation for RFC-0015 Tables 2, 3 and 4: where a PR's review findings sit.

For each PR number given, walk ``pulls/<N>/comments`` (``per_page=100``,
paged until a short page). Rows with no ``in_reply_to_id`` are *findings*;
rows with one are the fixer's *replies* to them (``/rvw-pr`` never reads or
answers comments, so every reply in a thread is the fix pass speaking).
Findings are grouped by ``pull_request_review_id``; ``pulls/<N>/reviews``
supplies each submission's ``submitted_at`` and the groups are **sorted by
it**, so the round index is submission order by construction, not by the
order the comments endpoint happens to return rows. A review with no
``submitted_at`` sorts last and is reported.

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
  which commit identity does not. A finding has no blameable line, and is
  counted under one of four separate ``unclassifiable-*`` causes, when its
  ``subject_type`` is ``file``, when it was posted on the ``LEFT`` (base) side
  of a deleted line, when ``original_line`` is null, or when ``git blame``
  fails at that head; a head absent locally is fetched by SHA.
  Bound: a commit authored before round 1 but pushed after it would read as
  ``original``; this repo's loop pushes before spawning reviewers, so the case
  is not expected and is not measured here.
* **Triage** (Table 4): the first reply in the finding's thread is read for the
  fixer's verdict. This repo's replies open with the verdict, so the opening
  word decides where it is present: a reply that *starts* with "Must-fix" is
  ``must-fix`` whatever follows (a must-fix reply often goes on to say what was
  refuted), one that starts with "Filed as" is ``filed``, one that starts with
  "Refuted", "Not a defect", "Declined", "Rejected" or "Decided" is
  ``refuted``. Otherwise the whole reply is searched with word boundaries, in
  the order filed, refuted, must-fix: ``\\bFiled as\\b`` or a minted ID;
  ``\\brefut``, ``\\bnot a defect\\b``, ``\\bdeclin``, ``\\brejected\\b``,
  ``\\bstays\\b``; then ``\\bFixed in\\b``, ``\\bConfirmed\\b``, ``\\bCorrect\\b``,
  ``\\bTaken\\b``, ``\\bAdded\\b``, ``\\bAnnotated\\b``. ``unknown`` otherwise,
  including threads with no reply. A heuristic over free text, stated as one:
  under-classification shows up as ``unknown``; mis-classification does not,
  and an earlier revision without word boundaries counted "incorrect" as
  ``must-fix``.

Also printed:

* the share of sampled PRs whose first push (merge-base to the round-1 head,
  first-parent) had more than one commit — the bound on the single-commit
  premise an earlier revision of this script assumed;
* per PR, whether the comments endpoint's row order disagreed with submission
  order, so the sorting above is seen to matter or not;
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

_OPEN_MUST_FIX = re.compile(r"^\s*\**Must-fix", re.I)
_OPEN_FILED = re.compile(r"^\s*\**Filed as\b", re.I)
_OPEN_REFUTED = re.compile(r"^\s*\**(?:Refut|Not a defect|Declin|Rejected|Decided)", re.I)
_FILED = re.compile(r"\bFiled as\b|\b(?:BK|BUG|ID)-\d+\b.{0,20}\b(?:filed|minted)\b", re.I)
_REFUTED = re.compile(r"\brefut|\bnot a defect\b|\bdeclin|\brejected\b|\bstays\b", re.I)
_MUST_FIX = re.compile(r"\bFixed in\b|\bConfirmed\b|\bCorrect\b|\bTaken\b|\bAdded\b|\bAnnotated\b", re.I)

UNCLASSIFIABLE = ("unclassifiable-file", "unclassifiable-left", "unclassifiable-noline", "unclassifiable-blame")


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
    if r.get("subject_type") == "file":
        return "unclassifiable-file"
    if r.get("side") == "LEFT":
        return "unclassifiable-left"
    line = r.get("original_line")
    if line is None:
        return "unclassifiable-noline"
    head = r["original_commit_id"]
    ensure_commit(head)
    blame = _git("blame", "-l", "-L", f"{line},{line}", head, "--", r["path"], check=False)
    if blame.returncode != 0:
        return "unclassifiable-blame"
    blamed = blame.stdout.split()[0].lstrip("^")
    if _git("merge-base", "--is-ancestor", blamed, "origin/master", check=False).returncode == 0:
        return "pre-existing"
    authored = int(_git("show", "-s", "--format=%at", blamed).stdout.strip())
    return "original" if authored < first_review_ts else "loop-introduced"


def triage(reply: str | None) -> str:
    if reply is None:
        return "unknown"
    if _OPEN_MUST_FIX.search(reply):
        return "must-fix"
    if _OPEN_FILED.search(reply):
        return "filed"
    if _OPEN_REFUTED.search(reply):
        return "refuted"
    if _FILED.search(reply):
        return "filed"
    if _REFUTED.search(reply):
        return "refuted"
    if _MUST_FIX.search(reply):
        return "must-fix"
    return "unknown"


def main(prs: list[int]) -> None:
    by_index: dict[int, Counter[str]] = {}
    grand: Counter[str] = Counter()
    multi_commit_first_push = 0
    reordered: list[int] = []
    fired = {"classified": Counter(), "unclassifiable-as-loop": Counter(), "share>=80%,n>=2": Counter()}
    for pr in prs:
        comments = _gh(f"pulls/{pr}/comments")
        findings = [c for c in comments if c.get("in_reply_to_id") is None]
        first_reply: dict[int, str] = {}
        for c in sorted((c for c in comments if c.get("in_reply_to_id")), key=lambda c: c["created_at"]):
            first_reply.setdefault(c["in_reply_to_id"], c["body"])
        review_ts = {rv["id"]: _ts(rv["submitted_at"]) for rv in _gh(f"pulls/{pr}/reviews") if rv.get("submitted_at")}
        seen: OrderedDict[int, list[dict]] = OrderedDict()
        for f in findings:
            seen.setdefault(f["pull_request_review_id"], []).append(f)
        unsubmitted = [rid for rid in seen if rid not in review_ts]
        ordered = sorted(seen, key=lambda rid: review_ts.get(rid, float("inf")))
        if ordered != list(seen):
            reordered.append(pr)
        rounds: OrderedDict[int, list[dict]] = OrderedDict((rid, seen[rid]) for rid in ordered)
        first_review_ts = min(review_ts[rid] for rid in rounds if rid in review_ts)
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
                if o.startswith("unclassifiable"):
                    c["unclassifiable"] += 1
                c[t] += 1
                if t == "must-fix":
                    c[f"mf-{o}"] += 1
                    if o.startswith("unclassifiable"):
                        c["mf-unclassifiable"] += 1
            by_index.setdefault(i, Counter()).update(c)
            grand.update(c)
            cells.append(
                f"r{i}: {c['code']}c/{c['prose']}p o{c['original']} l{c['loop-introduced']} "
                f"p{c['pre-existing']} u{c['unclassifiable']} | mf o{c['mf-original']} l{c['mf-loop-introduced']} "
                f"p{c['mf-pre-existing']} u{c['mf-unclassifiable']} | filed {c['filed']} refuted {c['refuted']} ?{c['unknown']}"
            )
            # D5 dry run, three readings
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
        note = f", {len(unsubmitted)} review(s) without submitted_at" if unsubmitted else ""
        print(
            f"PR #{pr}: {len(rounds)} submissions, {len(findings)} findings, first push {first_push} commit(s){note} | "
            + "  ".join(cells)
        )
    n = len(prs)
    print(
        f"TOTAL: {grand['submissions']} submissions; code {grand['code']}, prose {grand['prose']} "
        f"(record {grand['record']}); original {grand['original']}, loop-introduced {grand['loop-introduced']}, "
        f"pre-existing {grand['pre-existing']}, unclassifiable {grand['unclassifiable']} "
        f"(file {grand['unclassifiable-file']}, left {grand['unclassifiable-left']}, "
        f"noline {grand['unclassifiable-noline']}, blame {grand['unclassifiable-blame']}); "
        f"triage must-fix {grand['must-fix']}, filed {grand['filed']}, refuted {grand['refuted']}, unknown {grand['unknown']}"
    )
    print(f"FIRST PUSH >1 COMMIT: {multi_commit_first_push} of {n} PRs")
    print(f"ROUND ORDER: comments-endpoint order differed from submission order in {len(reordered)} PR(s) {reordered}")
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
