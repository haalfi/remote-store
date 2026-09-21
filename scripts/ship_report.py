#!/usr/bin/env python3
"""BK-378: every figure about a `/ship` loop, derived after it (RFC-0015 D4).

D4's rule is that **no hand-written figure about the loop exists while the loop
runs**. BK-348 declined a script for this because "it guards nothing"; the hand
enumerations since went stale eleven times across four traces, and every
staleness was a review round. So the figures are derived here, once, and pasted
rather than composed.

This script is the single producer of two artifacts:

* the `/ship` **Step 5 report** — what the loop cost and what it found; and
* the trace's **`review:` block** — the same numbers as YAML, pasted verbatim
  under one key so `sdd/traces/_schema.yml` can name its derivation instead of
  asking an author to enumerate commits by hand.

Mid-loop it is run with ``--out tmp/ship-report-<PR>.md`` (``tmp/`` is
gitignored) and a brief quotes the per-file distribution and the origin counts
from it. That is RFC-0015's Open Question 5 answered: nothing durable holds the
mid-loop output, because a PR comment primes nobody — reviewers never fetch
comments, which is the discipline that keeps unprimed passes unprimed — and the
durable copy is the `review:` block written at the close.

What it reuses, and why that matters
------------------------------------
``sdd/rfcs/rfc-0015-findings.py`` already classifies a PR's findings: it walks
``pulls/<N>/comments`` paged, groups by ``pull_request_review_id``, orders the
groups by each submission's ``submitted_at``, blames ``original_line`` at the
head the reviewer saw to tag origin, and reads the first reply in each thread
for triage. Every one of those definitions is load-bearing for RFC-0015's
tables, so this script **imports** them rather than restating them
([`CLAUDE.md` principle 4](../CLAUDE.md#principles)). Two implementations of
"which round is this finding in" would eventually disagree, and the RFC's
acceptance criterion is measured with one of them.

The import is by path, because ``rfc-0015-findings.py`` is not a Python
identifier and ``import`` cannot name it. That is the cost of leaving the
classifier where the RFC's derivation line points; moving it to ``scripts/``
would falsify the command every figure in the RFC cites.

What it adds
------------
* **Per-file distribution**, replacing `/ship` brief requirement 3's two-call
  recipe. That recipe's three shaping decisions are preserved here because each
  fixed a measured regression:
  **only rows with no ``in_reply_to_id`` are findings** — the endpoint returns
  the fixer's replies alongside them, and the inflation is loop-dependent, one
  row on one PR and a doubling on another;
  **the changed-file list is paged too** — it is the *minuend*, and a truncated
  one drops a file out of both the touched and untouched sets, which is
  invisible, where a truncated subtrahend merely over-reports neglect;
  **untouched is the changed-file list minus the union across all pages**, never
  minus page 1's.
* **Review-driven commits**, as the schema's ``review_rounds`` means them:
  commits in ``<base>..<head>`` whose **author date** is later than the first
  review submission that carried a finding. That is the same boundary
  ``origin()`` uses to call a line ``loop-introduced``, so the commit count and
  the origin tags cannot disagree about when the loop started. Author dates
  survive rebases; commit identity does not.
* **Per-pass durations**, from consecutive ``submitted_at`` deltas, with the
  first pass measured from the PR's ``created_at``.
* **CI's verdict on the head**. Measured on this repo: a merge commit carried
  39 check runs of which 15 were ``skipped`` and several names repeated, so a
  bare conclusion count misreads. Runs are reduced to the latest per name, and
  ``queued`` / ``in_progress`` are reported as **pending, not green** — `/ship`'s
  own rule that a still-running matrix is not a green one.

Bounds (DRIFT-RULES Rule 7)
---------------------------
* **It reports the record, it does not judge it.** Nothing here is true or false
  of an artifact, which is why its ``Drift-gate::`` kind is ``report``: a
  ``rule:`` cell would claim a check nobody is making.
* **Advisory by construction (Rule 5).** It is wired as an alias and belongs to
  no gate bundle. Its exit code says whether it could *read* the PR, never
  anything about what it found — a loop with 40 findings and one with none both
  exit 0. Gating on a measurement would make the number worth managing.
* **It inherits every bound the classifier states**, including that a finding
  with no blameable line is ``unclassifiable-*`` under one of four causes, and
  that triage is a heuristic over free text whose under-classification shows up
  as ``unknown`` while mis-classification does not.
* **A review with no ``submitted_at``** has no place in the order; the
  classifier sorts it last and this script reports the count rather than hiding
  it.
* **Durations are wall-clock between submissions**, so a pass that waited on a
  human reads as a long pass. It measures the loop's elapsed time, not work.
* **``review_rounds`` is a count of commits, not of review submissions.** The
  two measure different things and this script prints both, because the trace
  schema's field means the first and a reader reaching for "how many reviews"
  wants the second.

Run with::

    hatch run ship-report 1025
    hatch run ship-report 1025 --out tmp/ship-report-1025.md
    python scripts/ship_report.py 1025 --trace-block-only

Requires ``gh`` authenticated and the base ref fetched.

Drift-gate::

    kind:       report
    surfaces: one pull request's review record — findings per submission, their per-file
        distribution, each finding's origin tag, the review-driven commits, per-pass durations and
        CI's verdict on the head — as the /ship Step 5 report and the trace's review: block
    domain:     process
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_CLASSIFIER = ROOT / "sdd" / "rfcs" / "rfc-0015-findings.py"


def _load_classifier(path: Path = _CLASSIFIER) -> Any:
    """Import RFC-0015's finding classifier, whose filename is not an identifier.

    Loud on absence: a silently re-implemented classifier is the defect this
    import exists to prevent, so there is no fallback path.
    """
    spec = importlib.util.spec_from_file_location("rfc0015_findings", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load the RFC-0015 classifier from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fnd = _load_classifier()

# Conclusions that mean the head is not green. `skipped` and `neutral` are
# absent deliberately: this repo's CI path-filters heavily, and 15 of 39 runs
# on a measured merge commit were `skipped`.
_CI_BAD = ("failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale")
_CI_PENDING = ("queued", "in_progress", "waiting", "pending", "requested")


def _gh_one(path: str) -> dict[str, Any]:
    """A single object from the REST API. Not every endpoint returns an array."""
    out = subprocess.run(["gh", "api", f"repos/{fnd.REPO}/{path}"], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def _gh_wrapped(path: str, key: str) -> list[dict[str, Any]]:
    """Page an endpoint that wraps its array in an object.

    ``fnd._gh`` pages the array-returning endpoints and is reused for those.
    ``commits/<sha>/check-runs`` is not one of them: it answers
    ``{"total_count": N, "check_runs": [...]}``, and feeding that to a reader
    expecting a list extends it with the object's *keys*. Same paging rule — a
    short page ends the walk — applied one level in.
    """
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _gh_one(f"{path}?per_page=100&page={page}").get(key, [])
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def pr_meta(pr: int) -> dict[str, Any]:
    """The PR's own row: head sha, base ref, creation time, state."""
    return _gh_one(f"pulls/{pr}")


def changed_files(pr: int) -> list[str]:
    """Every file the PR changes. Paged — this is the minuend (see the docstring)."""
    return [row["filename"] for row in fnd._gh(f"pulls/{pr}/files")]


def rounds_with_findings(pr: int) -> tuple[OrderedDict[int, list[dict]], dict[int, int], dict[int, str], list[int]]:
    """Findings grouped by submission and ordered by submission time.

    Returns ``(rounds, review_ts, first_reply, unsubmitted)`` — the same
    construction ``rfc-0015-findings.py`` makes, kept in one place so the round
    index here is the round index there.
    """
    comments = fnd._gh(f"pulls/{pr}/comments")
    findings = [c for c in comments if c.get("in_reply_to_id") is None]

    first_reply: dict[int, str] = {}
    for c in sorted((c for c in comments if c.get("in_reply_to_id")), key=lambda c: c["created_at"]):
        first_reply.setdefault(c["in_reply_to_id"], c["body"])

    review_ts = {
        rv["id"]: fnd._ts(rv["submitted_at"]) for rv in fnd._gh(f"pulls/{pr}/reviews") if rv.get("submitted_at")
    }

    seen: OrderedDict[int, list[dict]] = OrderedDict()
    for f in findings:
        seen.setdefault(f["pull_request_review_id"], []).append(f)
    unsubmitted = [rid for rid in seen if rid not in review_ts]
    ordered = sorted(seen, key=lambda rid: review_ts.get(rid, float("inf")))
    rounds: OrderedDict[int, list[dict]] = OrderedDict((rid, seen[rid]) for rid in ordered)
    return rounds, review_ts, first_reply, unsubmitted


def review_driven_commits(base: str, head: str, first_review_ts: int | None) -> list[tuple[str, int, str]]:
    """``(sha, author_ts, subject)`` for commits authored after the first review.

    The schema's ``review_rounds`` means "commits that exist specifically
    because review feedback was incorporated". Author date is the discriminator
    for the same reason ``origin()`` uses it: it survives a rebase, and commit
    identity does not. With no review yet, the answer is none.
    """
    if first_review_ts is None:
        return []
    raw = fnd._git("log", "--format=%H%x00%at%x00%s", f"{base}..{head}").stdout.splitlines()
    out: list[tuple[str, int, str]] = []
    for line in raw:
        if not line.strip():
            continue
        sha, at, subject = line.split("\x00", 2)
        if int(at) > first_review_ts:
            out.append((sha, int(at), subject))
    out.reverse()  # oldest first, the order a reader follows the loop in
    return out


def ci_verdict(sha: str) -> dict[str, Any]:
    """Latest run per check name, reduced to a verdict the loop can act on."""
    runs = _gh_wrapped(f"commits/{sha}/check-runs", "check_runs")
    latest: dict[str, dict] = {}
    for run in runs:
        name = run["name"]
        stamp = run.get("completed_at") or run.get("started_at") or ""
        if name not in latest or stamp >= (latest[name].get("completed_at") or latest[name].get("started_at") or ""):
            latest[name] = run

    counts: Counter[str] = Counter()
    failed: list[str] = []
    pending: list[str] = []
    for name, run in latest.items():
        status, conclusion = run.get("status"), run.get("conclusion")
        if status in _CI_PENDING or conclusion is None:
            pending.append(name)
            counts["pending"] += 1
            continue
        counts[conclusion] += 1
        if conclusion in _CI_BAD:
            failed.append(name)

    if failed:
        verdict = "RED"
    elif pending:
        verdict = "PENDING"
    elif counts:
        verdict = "GREEN"
    else:
        verdict = "NO CHECKS"
    return {
        "verdict": verdict,
        "counts": dict(sorted(counts.items())),
        "failed": sorted(failed),
        "pending": sorted(pending),
        "total_runs": len(runs),
        "distinct_names": len(latest),
    }


def _hours(seconds: int) -> float:
    return round(seconds / 3600, 2)


def collect(pr: int) -> dict[str, Any]:
    """Every figure this report states, derived once."""
    meta = pr_meta(pr)
    head = meta["head"]["sha"]
    base_ref = f"origin/{meta['base']['ref']}"
    fnd.ensure_commit(head)

    rounds, review_ts, first_reply, unsubmitted = rounds_with_findings(pr)
    first_review_ts = min((review_ts[rid] for rid in rounds if rid in review_ts), default=None)

    by_round: list[dict[str, Any]] = []
    per_file: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    previous_ts = fnd._ts(meta["created_at"])

    for index, (rid, group) in enumerate(rounds.items(), 1):
        origins: Counter[str] = Counter()
        triages: Counter[str] = Counter()
        for f in group:
            tag = fnd.origin(f, first_review_ts) if first_review_ts is not None else "unclassifiable-noline"
            verdict = fnd.triage(first_reply.get(f["id"]))
            origins[tag] += 1
            triages[verdict] += 1
            per_file[f["path"]] += 1
            rows.append(
                {
                    "round": index,
                    "path": f["path"],
                    "line": f.get("original_line"),
                    "origin": tag,
                    "triage": verdict,
                    "artifact": fnd.artifact_class(f["path"]),
                    "record": fnd.is_record(f["path"]),
                }
            )
        submitted = review_ts.get(rid)
        duration = _hours(submitted - previous_ts) if submitted is not None else None
        if submitted is not None:
            previous_ts = submitted
        by_round.append(
            {
                "round": index,
                "findings": len(group),
                "origin": dict(sorted(origins.items())),
                "triage": dict(sorted(triages.items())),
                "duration_hours": duration,
            }
        )

    changed = changed_files(pr)
    touched = set(per_file)
    commits = review_driven_commits(base_ref, head, first_review_ts)

    return {
        "pr": pr,
        "title": meta["title"],
        "head": head,
        "base_ref": base_ref,
        "state": "merged" if meta.get("merged_at") else meta["state"],
        "submissions": len(rounds),
        "findings": sum(len(g) for g in rounds.values()),
        "unsubmitted_reviews": len(unsubmitted),
        "by_round": by_round,
        "rows": rows,
        "per_file": dict(sorted(per_file.items(), key=lambda kv: (-kv[1], kv[0]))),
        "changed_files": sorted(changed),
        "untouched_files": sorted(set(changed) - touched),
        "review_driven_commits": commits,
        "ci": ci_verdict(head),
    }


def _q(value: str) -> str:
    """A YAML string scalar that cannot be re-read as something else.

    ``json.dumps`` is the right tool because YAML 1.2 is a JSON superset, so a
    JSON string literal is already a valid double-quoted YAML scalar with
    quotes, backslashes and unicode handled. Unquoted is not safe here: an
    all-digit short SHA (``3153683``) parses back as an **integer**, which the
    schema caught the first time this block was validated. A ``%r`` would not
    have fixed it either — Python's repr escapes a backslash as ``\\\\``, and a
    single-quoted YAML scalar does not process escapes, so the value would
    round-trip wrong.
    """
    return json.dumps(value)


def _yaml_list(items: list[str], indent: str) -> str:
    return "\n".join(f"{indent}- {_q(item)}" for item in items) if items else f"{indent}[]"


def trace_block(data: dict[str, Any]) -> str:
    """The trace's ``review:`` key, pasted verbatim. ``review_rounds`` stays at
    a findable indent so ``rfc-0015-rounds.py`` still reads it."""
    # Hoisted rather than nested in the f-string below: a same-quote nested
    # f-string needs PEP 701 (3.12), and this repo supports 3.10.
    command = "hatch run ship-report {}".format(data["pr"])
    lines = [
        "review:",
        f"  # Derived by `{command}` at head {data['head'][:7]}.",
        "  # Do not hand-edit: RFC-0015 D4 makes this script the only producer.",
        f"  derivation: {_q(command)}",
        f"  review_rounds: {len(data['review_driven_commits'])}",
        f"  submissions: {data['submissions']}",
        f"  findings: {data['findings']}",
        # Every sequence key below emits `[]` when empty. A bare `by_round:`
        # header with no items is YAML *null*, not an empty list, and the
        # schema's `type: array` rejects it — reachable on any PR whose review
        # posted no inline findings, which is the ordinary shape of a clean one.
        "  by_round:" if data["by_round"] else "  by_round: []",
    ]
    for entry in data["by_round"]:
        lines.append(f"    - round: {entry['round']}")
        lines.append(f"      findings: {entry['findings']}")
        lines.append(f"      origin: {{{', '.join(f'{k}: {v}' for k, v in entry['origin'].items())}}}")
        lines.append(f"      triage: {{{', '.join(f'{k}: {v}' for k, v in entry['triage'].items())}}}")
        # `null`, not Python's `None`: YAML reads a bare `None` as the *string*
        # "None", which the schema's `[number, "null"]` rejects — so the nullable
        # branch could never validate. Reachable through the `unsubmitted` path
        # the module docstring says is reported rather than hidden.
        duration = entry["duration_hours"]
        lines.append(f"      duration_hours: {'null' if duration is None else duration}")
    lines.append("  by_file:" if data["per_file"] else "  by_file: []")
    for path, count in data["per_file"].items():
        lines.append(f"    - path: {_q(path)}")
        lines.append(f"      findings: {count}")
    lines.append("  untouched_files:")
    lines.append(_yaml_list(data["untouched_files"], "    "))
    lines.append("  review_driven_commits:")
    if data["review_driven_commits"]:
        for sha, _at, subject in data["review_driven_commits"]:
            lines.append(f"    - sha: {_q(sha[:7])}")
            lines.append(f"      subject: {_q(subject)}")
    else:
        lines.append("    []")
    ci = data["ci"]
    lines.append(f"  ci: {{verdict: {ci['verdict']}, failed: {len(ci['failed'])}, pending: {len(ci['pending'])}}}")
    return "\n".join(lines) + "\n"


def step5_report(data: dict[str, Any]) -> str:
    """The `/ship` Step 5 report, with every figure naming its derivation."""
    ci = data["ci"]
    out = [
        f"# /ship report — PR #{data['pr']} ({data['state']})",
        "",
        f"*{data['title']}*",
        "",
        f"Derived by `hatch run ship-report {data['pr']}` at head `{data['head'][:7]}`, "
        f"base `{data['base_ref']}`. Classification comes from "
        "`sdd/rfcs/rfc-0015-findings.py`, imported rather than reimplemented.",
        "",
        "## Rounds and findings",
        "",
        f"{data['submissions']} review submission(s) carrying {data['findings']} finding(s).",
    ]
    if data["unsubmitted_reviews"]:
        out.append(f"{data['unsubmitted_reviews']} review(s) had no `submitted_at` and sort last.")
    out += [
        "",
        "| Round | Findings | Origin | Triage | Elapsed (h) |",
        "|---|---|---|---|---|",
    ]
    for entry in data["by_round"]:
        origin = ", ".join(f"{k} {v}" for k, v in entry["origin"].items()) or "—"
        triage = ", ".join(f"{k} {v}" for k, v in entry["triage"].items()) or "—"
        out.append(
            f"| {entry['round']} | {entry['findings']} | {origin} | {triage} | "
            f"{entry['duration_hours'] if entry['duration_hours'] is not None else '—'} |"
        )

    out += [
        "",
        "## Per-file distribution",
        "",
        "Replaces the two-call brief recipe. Findings are rows with no `in_reply_to_id`; "
        "both endpoints are paged, and *untouched* is the changed-file list minus the union "
        "across every page.",
        "",
        "| File | Findings |",
        "|---|---|",
    ]
    for path, count in data["per_file"].items():
        out.append(f"| `{path}` | {count} |")
    out += [
        "",
        f"**Untouched by review** ({len(data['untouched_files'])} of {len(data['changed_files'])} changed files):",
        "",
    ]
    out += [f"- `{path}`" for path in data["untouched_files"]] or ["- —"]

    out += [
        "",
        "## Origin tag per finding",
        "",
        "| Round | File | Line | Origin | Triage |",
        "|---|---|---|---|---|",
    ]
    for row in data["rows"]:
        out.append(
            f"| {row['round']} | `{row['path']}` | {row['line'] if row['line'] is not None else '—'} | "
            f"{row['origin']} | {row['triage']} |"
        )

    commits = data["review_driven_commits"]
    out += [
        "",
        "## Review-driven commits",
        "",
        f"**{len(commits)}** — commits in `{data['base_ref']}..{data['head'][:7]}` authored after the "
        "first review submission, the same boundary the origin tag uses for `loop-introduced`. "
        "This is the trace's `review_rounds` value.",
        "",
    ]
    out += [f"- `{sha[:7]}` {subject}" for sha, _at, subject in commits] or ["- —"]

    out += [
        "",
        "## CI on the head",
        "",
        f"**{ci['verdict']}** — {ci['distinct_names']} distinct check name(s) from {ci['total_runs']} run(s); "
        f"{', '.join(f'{k} {v}' for k, v in ci['counts'].items()) or '—'}.",
    ]
    if ci["failed"]:
        out.append("")
        out += [f"- FAILED: `{name}`" for name in ci["failed"]]
    if ci["pending"]:
        out.append("")
        out += [f"- PENDING: `{name}`" for name in ci["pending"]]

    out += ["", "## Trace `review:` block", "", "```yaml", trace_block(data).rstrip("\n"), "```", ""]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("pr", type=int, help="pull request number")
    parser.add_argument("--out", type=Path, help="also write the report here (use tmp/, which is gitignored)")
    parser.add_argument(
        "--trace-block-only", action="store_true", help="print only the trace's review: block, for pasting"
    )
    args = parser.parse_args(argv)

    data = collect(args.pr)
    text = trace_block(data) if args.trace_block_only else step5_report(data)
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"\nWritten to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
