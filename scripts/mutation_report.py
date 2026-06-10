"""BK-273: per-scope mutation outcomes and the rolling ``[mutation]`` issue.

Gives ``mutation.yml`` the durable-TODO surface the drift guard proved out
(scheduled finding -> rolling GitHub issue -> triage skill), with one
deliberate divergence decided on run-history evidence (audit-018 C-DECISION /
A3): mutation has two outcomes and only one of them is a TODO.

* **Harness / implementation failure** — the run itself broke (a red
  ``mutate-<scope>`` leg, a leg that recorded no outcome, or a green leg
  that wrote no gremlins report). This is the class that used to reach the
  maintainer by email only (#763). -> the rolling issue is opened/updated,
  and the run stays red (the mutate leg propagates pytest's exit code).
* **Surviving mutants** — a test-coverage gap. pytest-gremlins never fails
  the run on survivors, strict coverage gates already run in CI, and run
  history shows survivors are not actioned as standalone TODOs. -> advisory
  only: counts land in the run-summary table and the HTML artifacts; they
  never open the issue (they are listed in the body only when harness
  failures opened it anyway).

Two subcommands, both invoked from ``.github/workflows/mutation.yml``:

``record <scope> --job-status … --gremlins-json … --out …``
    Runs at the end of every ``mutate-<scope>`` leg (``if: always()``).
    Combines the leg's ``job.status`` with the pytest-gremlins JSON report
    (``--gremlin-report=json`` writes ``coverage/gremlins/gremlins.json``)
    into one outcome JSON. Written atomically (tempfile + rename) so a
    mid-write failure leaves no truncated JSON for ``reconcile`` to crash
    on; a missing or corrupt gremlins report records ``counts: null``
    rather than failing the step.

``reconcile <outcomes-dir> --repo … --run-url … --title … --scopes … --full-run …``
    Runs in the ``summary`` job. Classifies every expected scope, appends a
    per-scope markdown table to ``$GITHUB_STEP_SUMMARY`` (when set), and
    reconciles the single rolling issue via the ``gh`` CLI (preinstalled on
    GitHub-hosted runners):

    * any harness failure -> create-or-update the issue;
    * all clear on a **full** run -> comment "healthy" and close it;
    * all clear on a **partial** run (single-scope dispatch) -> no-op — a
      partial run cannot vouch for the scopes it did not execute, so it
      never closes the issue (deliberate divergence from ``drift_report.py``,
      whose dispatch default re-checks everything).

    ``--scopes`` is the run's scope list JSON (``needs.setup.outputs.scopes``).
    An empty value with no outcomes means setup itself died before producing
    a scope list — that run broke too, and the issue says so.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_COUNT_KEYS = ("zapped", "survived", "timeout", "error")


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


def _load_counts(gremlins_json: Path) -> dict | None:
    """Summary counts from a pytest-gremlins JSON report, or None.

    None (missing/corrupt/shapeless report) is meaningful downstream: a green
    leg without counts classifies as a harness failure, because survivors are
    invisible to ``job.status`` and an unwritten report would hide them.
    """
    try:
        data = json.loads(gremlins_json.read_text(encoding="utf-8"))
        summary = data["summary"]
        return {key: int(summary[key]) for key in _COUNT_KEYS}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def record(scope: str, job_status: str, gremlins_json: Path, out: Path) -> int:
    outcome = {"scope": scope, "job_status": job_status, "counts": _load_counts(gremlins_json)}
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(outcome, f, indent=2)
        os.replace(tmp_name, out)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    print(f"Recorded outcome for {scope}: job_status={job_status}, counts={outcome['counts']}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #


def _load_outcomes(dir_: Path) -> dict[str, dict]:
    outcomes: dict[str, dict] = {}
    # rglob, not glob: download-artifact may preserve a directory level
    # inside each artefact (same gotcha drift_report.py documents).
    for path in sorted(dir_.rglob("*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        outcomes[data["scope"]] = data
    return outcomes


def classify_scopes(expected: list[str], outcomes: dict[str, dict]) -> dict[str, dict]:
    """Per-scope verdicts: harness_failure (reason) / survivors / ok.

    ``expected`` is the run's scope list; an expected scope without an
    outcome file means the leg died before its ``if: always()`` upload — a
    harness failure, not a skip.
    """
    classified: dict[str, dict] = {}
    for scope in expected:
        outcome = outcomes.get(scope)
        if outcome is None:
            classified[scope] = {
                "status": "harness_failure",
                "reason": "no outcome recorded for this scope",
                "counts": None,
            }
            continue
        counts = outcome.get("counts")
        if outcome.get("job_status") != "success":
            classified[scope] = {
                "status": "harness_failure",
                "reason": f"job ended with status `{outcome.get('job_status')}`",
                "counts": counts,
            }
        elif counts is None:
            classified[scope] = {
                "status": "harness_failure",
                "reason": "job was green but wrote no gremlins JSON report (reporting half broke)",
                "counts": None,
            }
        elif counts.get("survived", 0) > 0:
            classified[scope] = {"status": "survivors", "reason": None, "counts": counts}
        else:
            classified[scope] = {"status": "ok", "reason": None, "counts": counts}
    return classified


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def render_body(classified: dict[str, dict], run_url: str, full_run: bool) -> str:
    lines: list[str] = []
    lines.append("Weekly mutation-testing run health across the scopes in `scripts/mutate_scopes.py`.")
    lines.append("")
    lines.append(f"Last run: [{run_url}]({run_url})")
    if not full_run:
        lines.append("")
        lines.append("**Partial run** (single-scope dispatch) — scopes not listed below were not executed.")
    lines.append("")

    failures = [s for s, c in classified.items() if c["status"] == "harness_failure"]
    if failures:
        lines.append("## Harness / implementation failures")
        lines.append("")
        lines.append(
            "The run itself broke for these scopes — a regression in the "
            "mutation harness, the test baseline, or the workflow, not a "
            "surviving mutant. Triage with the `/mutation` skill."
        )
        lines.append("")
        for scope in failures:
            lines.append(f"- `{scope}` — {classified[scope]['reason']}")
        lines.append("")

    survivors = [s for s, c in classified.items() if c["status"] == "survivors"]
    if survivors:
        lines.append("## Surviving mutants (advisory)")
        lines.append("")
        lines.append(
            "Test-coverage gaps, listed for context only — survivors never open "
            "this issue and the run stays green on them. Fold into a "
            "coverage-hardening pass; details in the per-scope HTML report artifacts."
        )
        lines.append("")
        for scope in survivors:
            counts = classified[scope]["counts"]
            lines.append(f"- `{scope}` — {counts['survived']} survived / {counts['zapped']} zapped")
        lines.append("")

    clear = [s for s, c in classified.items() if c["status"] == "ok"]
    if clear:
        lines.append("## Clear")
        lines.append("")
        lines.append(", ".join(f"`{s}`" for s in clear))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "This issue is managed by `.github/workflows/mutation.yml`. The body is "
        "fully regenerated on every full run and the issue auto-closes when the "
        "run is healthy again. Do not edit the body by hand."
    )
    return "\n".join(lines)


def render_table(classified: dict[str, dict]) -> str:
    lines = ["## Mutation Testing Summary", ""]
    lines.append("| Scope | Verdict | Zapped | Survived | Timeout | Error |")
    lines.append("|-------|---------|--------|----------|---------|-------|")
    verdict_label = {"ok": "ok", "survivors": "survivors (advisory)", "harness_failure": "**harness failure**"}
    for scope, c in classified.items():
        counts = c["counts"] or {}
        cells = [str(counts[k]) if k in counts else "—" for k in _COUNT_KEYS]
        zapped, survived, timeout, error = cells
        lines.append(f"| `{scope}` | {verdict_label[c['status']]} | {zapped} | {survived} | {timeout} | {error} |")
    lines.append("")
    lines.append("Download per-scope HTML reports from the **Artifacts** section above.")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# gh plumbing (mirrors drift_report.py)
# --------------------------------------------------------------------------- #


def _gh(*args: str, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
        input=input_,
    )


def _find_open_issue(repo: str, title: str) -> int | None:
    result = _gh(
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--search",
        f'in:title "{title}"',
        "--json",
        "number,title",
        "--limit",
        "20",
    )
    for issue in json.loads(result.stdout):
        if issue["title"] == title:
            return int(issue["number"])
    return None


# --------------------------------------------------------------------------- #
# reconcile
# --------------------------------------------------------------------------- #


def reconcile(outcomes_dir: Path, repo: str, run_url: str, title: str, scopes_json: str, full_run: bool) -> int:
    outcomes = _load_outcomes(outcomes_dir)
    expected: list[str] = json.loads(scopes_json) if scopes_json.strip() else []
    if not expected:
        if outcomes:
            expected = sorted(outcomes)
        else:
            # The setup job died before emitting a scope list (the
            # ModuleNotFoundError class): nothing ran, and that is itself a
            # harness failure the issue must carry.
            expected = ["(setup)"]
            outcomes = {"(setup)": {"scope": "(setup)", "job_status": "failure", "counts": None}}

    classified = classify_scopes(expected, outcomes)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(render_table(classified))

    has_failure = any(c["status"] == "harness_failure" for c in classified.values())
    existing = _find_open_issue(repo, title)

    if has_failure:
        body = render_body(classified, run_url, full_run)
        if existing is None:
            print(f"Harness failure — creating issue: {title}", file=sys.stderr)
            _gh("issue", "create", "--repo", repo, "--title", title, "--body-file", "-", input_=body)
        else:
            print(f"Harness failure — updating issue #{existing}", file=sys.stderr)
            _gh("issue", "edit", str(existing), "--repo", repo, "--body-file", "-", input_=body)
        return 0

    # No harness failure. Survivors alone are advisory and never touch the issue.
    if existing is None:
        print("Run healthy; no open issue. No-op.", file=sys.stderr)
        return 0
    if not full_run:
        print(
            f"Partial run healthy, but issue #{existing} stays open — it cannot vouch for the other scopes.",
            file=sys.stderr,
        )
        return 0
    print(f"Full run healthy — closing issue #{existing}", file=sys.stderr)
    _gh(
        "issue",
        "comment",
        str(existing),
        "--repo",
        repo,
        "--body",
        f"Mutation run healthy on this run.\n\n{run_url}",
    )
    _gh("issue", "close", str(existing), "--repo", repo)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="write one scope's outcome JSON (runs in every mutate leg)")
    p_record.add_argument("scope")
    p_record.add_argument("--job-status", required=True, help="the leg's ${{ job.status }}")
    p_record.add_argument("--gremlins-json", required=True, type=Path, help="pytest-gremlins JSON report path")
    p_record.add_argument("--out", required=True, type=Path)

    p_rec = sub.add_parser("reconcile", help="classify outcomes and reconcile the rolling issue (summary job)")
    p_rec.add_argument("outcomes_dir", type=Path)
    p_rec.add_argument("--repo", required=True, help='e.g. "haalfi/remote-store"')
    p_rec.add_argument("--run-url", required=True)
    p_rec.add_argument("--title", required=True)
    p_rec.add_argument("--scopes", required=True, help="this run's scope list as JSON (may be empty if setup died)")
    p_rec.add_argument(
        "--full-run", required=True, choices=["true", "false"], help="schedule / dispatch-all vs single-scope dispatch"
    )

    args = parser.parse_args(argv)
    if args.command == "record":
        return record(args.scope, args.job_status, args.gremlins_json, args.out)
    return reconcile(args.outcomes_dir, args.repo, args.run_url, args.title, args.scopes, args.full_run == "true")


if __name__ == "__main__":
    sys.exit(main())
