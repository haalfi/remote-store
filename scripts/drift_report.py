"""ID-182: compose the rolling-issue body from per-extra drift reports.

Reads every JSON a run uploaded, renders a markdown summary, and reconciles
a single rolling GitHub issue with the resulting state via the ``gh`` CLI
(preinstalled on GitHub-hosted runners).

Three shapes arrive, and they are told apart by their own fields rather than
by filename (several files per extra share the ``extra`` key):

* a **diff** report from ``drift_check.py diff`` — the newest lane;
* a **floor** report from ``drift_check.py floor`` (``lane: "floor"``);
* a **smoke verdict** from the ``drift-smoke`` composite action (``smoke``),
  one per extra per lane.

Logic:

* Any diff with ``status`` ``drift`` / ``needs_refresh`` / ``error``, any floor
  that failed to resolve, or any red smoke in either lane
  → create-or-update the issue.
* Everything clean in both lanes → comment "drift cleared" on the open issue
  (if any) and close it; no-op if no issue is open.

``--dry-run`` renders the body and touches no issue, so a dispatch from a
branch is observable without writing to the issue the scheduled runs own.

Drift-gate::

    kind:       report
    surfaces:   the current per-extra dependency state in both lanes — the newest resolution's
        drift against the committed baselines, the declared floors' resolution, and each lane's
        smoke verdict — as a rolling GitHub issue it opens, updates or closes; it acts on that
        state rather than asserting anything, and exits 0 either way
    domain:     process
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Reports:
    """The three JSON shapes a run produces, keyed for rendering.

    ``diffs`` and ``floors`` hold one report per extra; ``smokes`` is keyed
    ``(extra, lane)`` because an extra has a verdict per lane.
    """

    diffs: dict[str, dict]
    floors: dict[str, dict]
    smokes: dict[tuple[str, str], dict]

    def __bool__(self) -> bool:
        return bool(self.diffs or self.floors or self.smokes)


def _load_reports(dir_: Path) -> Reports:
    """Split every uploaded JSON by **shape**, not by filename.

    All three shapes carry ``"extra"``, and the matrix uploads several files
    per extra, so keying one flat dict on that field would silently keep
    whichever file sorted last. The discriminators are the fields themselves:
    a ``smoke`` key makes it a smoke verdict, ``lane == "floor"`` a floor
    report, and anything else the newest-lane diff.

    rglob (not glob): upload-artifact preserves the workspace-relative
    directory prefix of `path:` inside the artefact, so the matrix uploads are
    extracted one level deeper than a flat layout. rglob handles both shapes.
    """
    diffs: dict[str, dict] = {}
    floors: dict[str, dict] = {}
    smokes: dict[tuple[str, str], dict] = {}
    for path in sorted(dir_.rglob("*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        extra = data["extra"]
        if "smoke" in data:
            smokes[(extra, data.get("lane", "newest"))] = data
        elif data.get("lane") == "floor":
            floors[extra] = data
        else:
            diffs[extra] = data
    return Reports(diffs=diffs, floors=floors, smokes=smokes)


def _render_isolation_findings(reports: Reports) -> list[str]:
    """Extras that failed on the newest lane before the smoke ever ran.

    An extra is a promise that installing it alone gives you a working
    backend, and nothing standing tested that promise: CI installs an
    aggregate whose members cover for each other, so an extra can be missing a
    dependency and every gate stays green. These rows are what that promise
    failing looks like — the extra installed and its own declared packages did
    not import, or it did not install at all, with nothing else in the
    environment to supply what it forgot to declare.
    """
    failures = {
        extra: v
        for extra, v in _smoke_failures(reports, "newest").items()
        if v.get("phase") in ("install-extra", "import-extra")
    }
    if not failures:
        return []
    lines = ["## Isolated install failed", ""]
    lines.append(
        "These extras were installed **alone**, at the resolution recorded "
        "above, and could not stand up on their own. A package one of them "
        "needs but does not declare is invisible in any environment where "
        "another extra happens to supply it."
    )
    lines.append("")
    for extra in sorted(failures):
        verdict = failures[extra]
        lines.append(f"**`[{extra}]`** — {verdict.get('phase')}")
        lines.append("")
        reason = verdict.get("reason")
        if reason:
            lines.append("```")
            lines.append(str(reason).strip())
            lines.append("```")
            lines.append("")
    return lines


FLOOR_REGISTER = Path(__file__).resolve().parent.parent / "infra" / "drift-locks" / "FLOOR-REGISTER.md"

_REGISTER_ROW_RE = re.compile(r"^\|\s*`\[(?P<extra>[\w-]+)\]`\s*\|(?P<owner>[^|]*)\|[^|]*\|(?P<review>[^|]*)\|")


def load_floor_register(path: Path = FLOOR_REGISTER) -> dict[str, tuple[str, str]]:
    """``{extra: (owner, review_by)}`` from the committed floor register.

    A floor finding nobody has decided about and one somebody owns look
    identical on a rolling issue, so after a few weeks both read as furniture.
    The register is what separates them, and it is committed rather than
    inferred so that removing a row is a reviewable act.
    """
    if not path.exists():
        return {}
    register: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _REGISTER_ROW_RE.match(line.strip())
        if match:
            register[match.group("extra")] = (match.group("owner").strip(), match.group("review").strip())
    return register


def _render_floor_lane(reports: Reports, register: dict[str, tuple[str, str]]) -> list[str]:
    """The floor lane's findings, split by the phase that failed.

    The split is the whole value of the section: the three causes take three
    different actions, and a leg that merely says "red" costs a log read to
    tell them apart.
    """
    floor_smoke = _smoke_failures(reports, "floor")
    refused = sorted(
        {e for e, r in reports.floors.items() if r.get("status") == "error"}
        | {e for e, v in floor_smoke.items() if v.get("phase") == "install-extra"}
    )
    broke = sorted(e for e, v in floor_smoke.items() if v.get("phase") in ("smoke", "import-extra"))
    harness = sorted(e for e, v in floor_smoke.items() if v.get("phase") == "install-plugins")
    if not (refused or broke or harness):
        return []

    lines = ["## Floor lane", ""]
    lines.append(
        "Each extra installed at the floor of every range it declares, on the "
        "oldest supported interpreter, then smoked. Findings below are "
        "advisory: the legs exit 0 and no release is blocked on them. An extra "
        "marked _known_ is in `infra/drift-locks/FLOOR-REGISTER.md` with an "
        "owner; one that is not is new since the register was last edited."
    )
    lines.append("")

    if broke:
        lines.append("### Floor installs, then breaks")
        lines.append("")
        lines.append(
            "The declared floor admits a release that resolves cleanly and "
            "fails when the code runs against it. This is the class the lane "
            "exists to find — the floor is too low and wants raising."
        )
        lines.append("")
        lines.extend(_floor_rows(reports, broke, floor_smoke, register))

    if refused:
        lines.append("### Floor does not install")
        lines.append("")
        lines.append(
            "The floor cannot be installed at all on the oldest supported "
            "interpreter, so nothing was smoked. A user on that interpreter "
            "meets the same refusal, which makes this a decision rather than a "
            "silent risk: raise the floor to the oldest release that installs, "
            "or record why it stands as written."
        )
        lines.append("")
        lines.extend(_floor_rows(reports, refused, floor_smoke, register))

    if harness:
        lines.append("### Test plugins cannot coexist with the floor")
        lines.append("")
        lines.append(
            "The extra installed at its floor and the smoke's own pytest "
            "plugins then could not be installed under the same constraints. "
            "That is a harness gap, not a finding about the floor: fix the "
            "plugin set, then read the re-run."
        )
        lines.append("")
        lines.extend(_floor_rows(reports, harness, floor_smoke, register))

    return lines


def _floor_rows(
    reports: Reports,
    extras: list[str],
    floor_smoke: dict[str, dict],
    register: dict[str, tuple[str, str]],
) -> list[str]:
    lines: list[str] = []
    for extra in extras:
        report = reports.floors.get(extra, {})
        lines.append(f"**`[{extra}]`**")
        lines.append("")
        if extra in register:
            owner, review = register[extra]
            lines.append(f"_Known: owned by {owner}, review by {review}._")
            lines.append("")
        pins = report.get("floor") or {}
        if pins:
            lines.append("| Package | Resolved at floor |")
            lines.append("|---|---|")
            for package in sorted(pins):
                lines.append(f"| `{package}` | `{pins[package]}` |")
            lines.append("")
        reason = report.get("reason") or floor_smoke.get(extra, {}).get("reason")
        if reason:
            lines.append("```")
            lines.append(str(reason).strip())
            lines.append("```")
            lines.append("")
    return lines


def _render_smoke_verdicts(reports: Reports) -> list[str]:
    """One row per extra, one column per lane.

    The verdict used to live only in the run's job conclusions, so reading it
    meant leaving the issue. It is the thing that decides whether a drift is
    safe to accept, which makes the issue the wrong place for it to be absent.
    """
    if not reports.smokes:
        return []
    lanes = ["newest", "floor"]
    extras = sorted({extra for extra, _ in reports.smokes})
    lines = ["## Smoke verdicts", ""]
    lines.append("| Extra | " + " | ".join(lane.capitalize() for lane in lanes) + " |")
    lines.append("|---" * (len(lanes) + 1) + "|")
    for extra in extras:
        cells = []
        for lane in lanes:
            verdict = reports.smokes.get((extra, lane))
            if verdict is None:
                cells.append("—")
                continue
            smoke = verdict.get("smoke", "?")
            phase = verdict.get("phase")
            cells.append(f"{smoke} ({phase})" if smoke == "fail" and phase else smoke)
        lines.append(f"| `[{extra}]` | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("`skipped` means no resolution existed to pin the smoke to, not that it passed.")
    lines.append("")
    return lines


def _smoke_failures(reports: Reports, lane: str) -> dict[str, dict]:
    """Extras whose smoke went red in *lane*, keyed by extra."""
    return {extra: v for (extra, ln), v in sorted(reports.smokes.items()) if ln == lane and v.get("smoke") == "fail"}


def has_signal(reports: Reports, register: dict[str, tuple[str, str]] | None = None) -> bool:
    """Whether this run has anything a maintainer has not already decided about.

    A red smoke counts even when the resolution itself is clean: the isolated
    per-extra install is the only thing that exercises an extra's declared set
    alone, so its verdict is a finding in its own right. Before it reached this
    predicate a red smoke reached only a red run, which the durable-TODO
    principle in ``sdd/CI-OPERATIONS.md`` says is not enough to rely on.

    A floor finding already in the register does **not** count. Its owner and
    its rationale are committed, so holding the issue open for it would make
    every week's issue look identical and train the reader to skip it.
    """
    known = set(register or {})
    if any(r.get("status") in ("drift", "needs_refresh", "error") for r in reports.diffs.values()):
        return True
    if any(e not in known and r.get("status") == "error" for e, r in reports.floors.items()):
        return True
    return any(
        v.get("smoke") == "fail" and not (lane == "floor" and extra in known)
        for (extra, lane), v in reports.smokes.items()
    )


def _render_body(reports: Reports, run_url: str, register: dict[str, tuple[str, str]] | None = None) -> str:
    lines: list[str] = []
    lines.append("Weekly drift check across every `[<extra>]` in `pyproject.toml`.")
    lines.append("")
    lines.append(f"Last run: [{run_url}]({run_url})")
    lines.append("")

    diffs = reports.diffs
    needs_refresh = [e for e, r in diffs.items() if r["status"] == "needs_refresh"]
    if needs_refresh:
        lines.append("## Baselines awaiting first population")
        lines.append("")
        lines.append(
            "The following extras have stub baselines. Run "
            "`hatch run drift-check refresh-baseline <extra>` on Linux with the "
            "primary Python — a lock is OS- as well as Python-specific — and "
            "commit `infra/drift-locks/<extra>.txt` (plus the regenerated "
            "`docs-src/reference/tested-versions.md`). A stub cannot be "
            "reconstructed from this issue (no rows to apply); use this run's "
            "`candidate-baseline-<extra>` artifact if you cannot resolve "
            "locally. See `infra/drift-locks/README.md` § Refreshing:"
        )
        lines.append("")
        for extra in needs_refresh:
            lines.append(f"- `[{extra}]`")
        lines.append("")

    drift_extras = [e for e, r in diffs.items() if r["status"] == "drift"]
    if drift_extras:
        lines.append("## Drift detected")
        lines.append("")
        for extra in drift_extras:
            r = diffs[extra]
            lines.append(f"### `[{extra}]`")
            lines.append("")
            lines.append(
                f"Baseline captured {r.get('captured', '?')} on Python "
                f"{r.get('python_baseline', '?')}; "
                f"resolved on Python {r.get('python_run', '?')}."
            )
            lines.append("")
            stable = r.get("stable_drift", [])
            if stable:
                lines.append("**Stable-version drift:**")
                lines.append("")
                lines.append("| Package | Baseline | Resolved |")
                lines.append("|---|---|---|")
                for d in stable:
                    lines.append(f"| `{d['package']}` | `{d['baseline'] or '—'}` | `{d['resolved'] or '—'}` |")
                lines.append("")
            pre = r.get("prerelease_drift", [])
            if pre:
                lines.append("**Pre-release drift (informational):**")
                lines.append("")
                lines.append("| Package | Baseline | Resolved |")
                lines.append("|---|---|---|")
                for d in pre:
                    lines.append(f"| `{d['package']}` | `{d['baseline'] or '—'}` | `{d['resolved'] or '—'}` |")
                lines.append("")

    errors = [e for e, r in diffs.items() if r.get("status") == "error"]
    if errors:
        lines.append("## Errors")
        lines.append("")
        lines.append(
            "The drift check could not complete for these extras. The most "
            "common cause is a transient PyPI failure; if the next scheduled "
            "run still shows the same extra here, investigate."
        )
        lines.append("")
        for extra in errors:
            r = diffs[extra]
            lines.append(f"- `[{extra}]` — `{r.get('reason', 'unknown')}`")
        lines.append("")

    lines.extend(_render_isolation_findings(reports))
    lines.extend(_render_floor_lane(reports, register or {}))
    lines.extend(_render_smoke_verdicts(reports))

    # Clear means clear in both lanes. An extra whose newest resolution is `ok`
    # while its floor will not install, or while either lane's smoke is red, is
    # not a clean extra — listing it here is what would let the finding pass.
    floor_bad = set(reports.floors) - {e for e, r in reports.floors.items() if r.get("status") == "resolved"}
    smoke_bad = {e for (e, _), v in reports.smokes.items() if v.get("smoke") == "fail"}
    clear = [e for e, r in diffs.items() if r["status"] == "ok" and e not in floor_bad and e not in smoke_bad]
    if clear:
        lines.append("## Clear")
        lines.append("")
        lines.append("Both lanes clean: " + ", ".join(f"`[{e}]`" for e in clear))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "This issue is managed by `.github/workflows/drift-guard.yml`. The body "
        "is fully regenerated on every run and the issue auto-closes when "
        "drift clears. Do not edit the body by hand."
    )
    return "\n".join(lines)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports_dir", type=Path)
    parser.add_argument("--repo", required=True, help='e.g. "haalfi/remote-store"')
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--floor-register",
        type=Path,
        default=FLOOR_REGISTER,
        help="Path to the floor-lane register (default: infra/drift-locks/FLOOR-REGISTER.md).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Render the body to stdout and touch no issue. The route a branch "
            "uses to see what a run would write before it can write it."
        ),
    )
    args = parser.parse_args(argv)

    reports = _load_reports(args.reports_dir)
    if not reports:
        print("No drift reports found; nothing to reconcile.", file=sys.stderr)
        return 0

    register = load_floor_register(args.floor_register)
    body = _render_body(reports, args.run_url, register)
    if args.dry_run:
        # Before any `gh` call, so a dry run cannot reach the issue even to
        # read it: a dispatch from a branch must be observable without leaving
        # a trace on the rolling issue the scheduled runs own.
        print(body)
        print(
            f"(dry run — would {'create/update' if has_signal(reports, register) else 'close'} "
            f"the issue titled {args.title!r})",
            file=sys.stderr,
        )
        return 0

    existing = _find_open_issue(args.repo, args.title)

    if has_signal(reports, register):
        if existing is None:
            print(f"Creating new issue: {args.title}", file=sys.stderr)
            _gh(
                "issue",
                "create",
                "--repo",
                args.repo,
                "--title",
                args.title,
                "--body-file",
                "-",
                input_=body,
            )
        else:
            print(f"Updating issue #{existing}", file=sys.stderr)
            _gh(
                "issue",
                "edit",
                str(existing),
                "--repo",
                args.repo,
                "--body-file",
                "-",
                input_=body,
            )
        return 0

    # All clear.
    if existing is None:
        print("All extras clear; no open issue. No-op.", file=sys.stderr)
        return 0
    print(f"All clear — closing issue #{existing}", file=sys.stderr)
    _gh(
        "issue",
        "comment",
        str(existing),
        "--repo",
        args.repo,
        "--body",
        f"Drift cleared on this run.\n\n{args.run_url}",
    )
    _gh("issue", "close", str(existing), "--repo", args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
