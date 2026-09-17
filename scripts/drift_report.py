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

Logic, as ``decide`` implements it:

* Any diff with ``status`` ``drift`` / ``needs_refresh`` / ``error``, any floor
  that failed to resolve, any red smoke in either lane, any artefact that could
  not be read or placed, or any leg that did not report both a resolution and a
  verdict → create-or-update the issue.
* **Except** a floor error or red smoke whose ``(extra, lane)`` is in
  ``infra/drift-locks/KNOWN-FINDINGS.md``: somebody owns it, so it renders with
  its owner and does not hold the issue open. Version drift is never suppressed
  this way.
* Everything clean in both lanes → comment "drift cleared" on the open issue
  (if any) and close it; no-op if no issue is open.
* Everything clean but only **one** lane ran → leave the issue alone. A
  single-lane dispatch has not seen what the other lane would have found, and a
  closed issue is not recoverable the way a rewritten body is.

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
from dataclasses import dataclass, field
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
    unreadable: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.diffs or self.floors or self.smokes or self.unreadable)


def _load_reports(dir_: Path) -> Reports:
    """Split every uploaded JSON by **shape**, not by filename.

    All three shapes carry ``"extra"``, and the matrix uploads several files
    per extra, so keying one flat dict on that field would silently keep
    whichever file sorted last. The discriminators are the fields themselves:
    a ``smoke`` key makes it a smoke verdict, ``lane == "floor"`` a floor
    report, and anything else the newest-lane diff.

    rglob (not glob): an artefact is rooted at the least common ancestor of the
    files it was given, so a *single*-file upload lands that file at the
    artefact root while a multi-file one keeps a directory prefix. rglob handles
    both — and every basename a run produces is unique across extra, lane *and*
    kind, because with the directory discarded that basename is all
    ``merge-multiple`` has to keep two uploads apart. ``_incomplete_legs``
    is the backstop for the half of that failure which is silent.

    A file that will not parse, or that parses into something this script
    cannot place, is **named and skipped**, not raised. One unusable artefact
    used to abort the whole report, which loses every other extra's rows for a
    reason that has nothing to do with them — the failure ``_atomic_write``
    exists to prevent, arriving from the other side.

    **Unusable is wider than unparseable, and the difference is a silent
    close.** A resolution report without ``status`` parses and carries
    ``extra``, so an earlier fix let it through — and then every section keyed
    on ``status`` skipped it, ``_incomplete_legs`` saw both halves present, and
    ``has_signal`` returned False. The run closed the rolling issue with that
    extra's lane never reported on at all. Tolerating a bad artefact has to mean
    *naming* it; tolerating it into silence is worse than the loud abort it
    replaced, because the issue is this gate's only channel.
    """
    diffs: dict[str, dict] = {}
    floors: dict[str, dict] = {}
    smokes: dict[tuple[str, str], dict] = {}
    unreadable: list[str] = []
    for path in sorted(dir_.rglob("*.json")):
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            extra = data["extra"]
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            print(f"::warning::unreadable drift report {path}: {exc}", file=sys.stderr)
            unreadable.append(path.name)
            continue
        if "smoke" in data:
            smokes[(extra, data.get("lane", "newest"))] = data
            continue
        if "status" not in data:
            # A resolution report with no `status` is unplaceable: every section
            # below keys on it. Naming it here is what keeps it out of the
            # silent-close path.
            print(f"::warning::drift report {path} has no 'status'", file=sys.stderr)
            unreadable.append(path.name)
        elif data.get("lane") == "floor":
            floors[extra] = data
        else:
            diffs[extra] = data
    return Reports(diffs=diffs, floors=floors, smokes=smokes, unreadable=sorted(unreadable))


def _render_isolation_findings(reports: Reports, register: dict[tuple[str, str], tuple[str, str]]) -> list[str]:
    """Extras that failed on the newest lane before the smoke ever ran.

    An extra is a promise that installing it alone gives you a working
    backend, and nothing standing tested that promise: CI installs an
    aggregate whose members cover for each other, so an extra can be missing a
    dependency and every gate stays green. These rows are what that promise
    failing looks like — the extra installed and its own declared packages did
    not import, or it did not install at all, with nothing else in the
    environment to cover for it.

    **Two causes reach this section and the phase does not separate them.** A
    package the extra forgot to declare is the one isolation exists to catch.
    But a package it *does* declare, failing to import against a transitive that
    has just moved, lands here identically — BUG-287's shape arriving at the top
    of the range rather than the bottom, and a version finding rather than a
    declaration one. Only the traceback tells them apart, which is why the
    reason text is rendered rather than summarised.
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
        "above, and could not stand up on their own. Two causes land here and "
        "the phase does not separate them: a package one of them needs but does "
        "not declare, which is invisible in any environment where another extra "
        "happens to supply it; or a package it *does* declare that stopped "
        "importing against a transitive that moved. The traceback below "
        "separates them."
    )
    lines.append("")
    for extra in sorted(failures):
        verdict = failures[extra]
        lines.append(f"**`[{extra}]`** — {verdict.get('phase')}")
        lines.append("")
        if (extra, "newest") in register:
            owner, review = register[(extra, "newest")]
            lines.append(f"_Known: owned by {owner}, review by {review}._")
            lines.append("")
        reason = verdict.get("reason")
        if reason:
            lines.append("```")
            lines.append(str(reason).strip())
            lines.append("```")
            lines.append("")
    return lines


KNOWN_FINDINGS = Path(__file__).resolve().parent.parent / "infra" / "drift-locks" / "KNOWN-FINDINGS.md"

_REGISTER_ROW_RE = re.compile(
    r"^\|\s*`\[(?P<extra>[\w-]+)\]`\s*\|(?P<lane>[^|]*)\|(?P<owner>[^|]*)\|[^|]*\|(?P<review>[^|]*)\|"
)


def load_known_findings(path: Path = KNOWN_FINDINGS) -> dict[tuple[str, str], tuple[str, str]]:
    """``{(extra, lane): (owner, review_by)}`` from the committed register.

    A finding nobody has decided about and one somebody owns look identical on
    a rolling issue, so after a few weeks both read as furniture. The register
    is what separates them, and it is committed rather than inferred so that
    removing a row is a reviewable act.

    Keyed on lane as well as extra because the two lanes make different claims
    about the same extra: a known-bad floor says nothing about whether the
    newest resolution still works, and registering one must not silence the
    other.
    """
    if not path.exists():
        return {}
    register: dict[tuple[str, str], tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _REGISTER_ROW_RE.match(line.strip())
        if match:
            key = (match.group("extra"), match.group("lane").strip())
            register[key] = (match.group("owner").strip(), match.group("review").strip())
    return register


def _render_floor_lane(reports: Reports, register: dict[tuple[str, str], tuple[str, str]]) -> list[str]:
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
        "marked _known_ is in `infra/drift-locks/KNOWN-FINDINGS.md` with an "
        "owner; one that is not is new since the register was last edited."
    )
    lines.append("")

    if broke:
        lines.append("### Floor installs, then breaks")
        lines.append("")
        lines.append(
            "The declared floor admits a release that resolves cleanly and "
            "fails when the code runs against it. This is the class the lane "
            "exists to find. Usually the floor is too low and wants raising — "
            "but `lowest-direct` leaves transitives newest, so it can equally "
            "be a floor that was fine until something under it moved. The "
            "reason text is what separates them, and the second shape is a "
            "finding about the combination rather than about the floor."
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
    register: dict[tuple[str, str], tuple[str, str]],
) -> list[str]:
    lines: list[str] = []
    for extra in extras:
        report = reports.floors.get(extra, {})
        lines.append(f"**`[{extra}]`**")
        lines.append("")
        if (extra, "floor") in register:
            owner, review = register[(extra, "floor")]
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


def _render_smoke_verdicts(
    reports: Reports,
    register: dict[tuple[str, str], tuple[str, str]],
    lanes: list[str] | None = None,
) -> list[str]:
    """One row per extra, one column per lane.

    The verdict used to live only in the run's job conclusions, so reading it
    meant leaving the issue. It is the thing that decides whether a drift is
    safe to accept, which makes the issue the wrong place for it to be absent.

    **This table is where a registered finding renders, in every lane and
    every phase.** The two prose sections above it are phase-scoped by
    construction — ``_render_isolation_findings`` takes the newest lane's
    install and import phases, ``_render_floor_lane`` takes the floor — so a
    registered newest-lane *smoke* failure reached neither, and the one such
    row the register actually carries (`[sql]`, a pytest failure) rendered as a
    bare `fail (smoke)` with no owner. Three artifacts state that a registered
    finding renders with its owner; before this it was true of some phases.
    """
    if not reports.smokes:
        return []
    # The lanes the run was dispatched for, not both by default. A `lane: floor`
    # dispatch rendered a full `Newest` column of `—` for legs nobody ran, in
    # the one section `/drift` sends a triager to first — and `—` is defined
    # nowhere in the legend, so it read as a verdict rather than as an absence.
    # `_lanes_present`'s own docstring states the principle: a body that does
    # not say a lane was skipped reads as a statement about both.
    lanes = list(lanes or LANES)
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
            cell = f"{smoke} ({phase})" if smoke == "fail" and phase else smoke
            if smoke == "fail" and (extra, lane) in register:
                cell += f" — known, {register[(extra, lane)][0]}"
            cells.append(cell)
        lines.append(f"| `[{extra}]` | " + " | ".join(cells) + " |")
    lines.append("")
    if set(lanes) != set(LANES):
        lines.append(f"This run covered the {', '.join(sorted(lanes))} lane only; the other lane was not dispatched.")
        lines.append("")
    lines.append("`skipped` means no resolution existed to pin the smoke to, not that it passed.")
    lines.append("")
    lines.append(
        "A cell marked _known_ names the item that owns it in "
        "`infra/drift-locks/KNOWN-FINDINGS.md`; one that is not is new since "
        "the register was last edited."
    )
    lines.append("")
    return lines


def _smoke_failures(reports: Reports, lane: str) -> dict[str, dict]:
    """Extras whose smoke went red in *lane*, keyed by extra."""
    return {extra: v for (extra, ln), v in sorted(reports.smokes.items()) if ln == lane and v.get("smoke") == "fail"}


LANES = ("newest", "floor")


def _incomplete_leg_rows(
    reports: Reports,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
) -> list[tuple[str, str]]:
    """``(extra, sentence)`` per leg that did not report everything it owes.

    Every leg writes a resolution and a smoke verdict, `skipped` included, so a
    missing half means a leg died mid-way, two uploads landed on one filename,
    or the smoke was skipped because its docker services never came up. The
    second happened twice while this lane was being built, and the third is
    deliberate — the workflow would rather lose a leg than publish an
    infrastructure failure as a wrong floor. All three share a signature: a row
    that is quietly absent rather than wrong.

    ``expected`` closes the case the halves cannot see between them: a leg that
    produced **nothing** contributes no key on either side, so comparing the
    two sides finds it complete. The claim space has to come from the extras
    the run was asked to cover — [`DRIFT-RULES.md` Rule 3](../sdd/DRIFT-RULES.md)
    wants it derived from the canonical artefact, and the dispatched slice is
    that artefact for a run that was deliberately narrowed. A missing row and a
    clean row look identical on the issue, which is why this is said out loud
    rather than inferred.

    **A leg is ``(extra, lane)``, and the claim space has to be too.** Keying
    it on the extra alone hides the commonest shape of the failure it exists to
    catch: one lane of one extra lost while the other lane reports for the same
    extra. That extra stays in ``covered``, contributes no incomplete row, and
    — because the other lane's rows are clean — is then named under `Clear` as
    a lane nobody ran. Measured on a synthetic run: `[sql]` with its whole floor
    leg absent rendered "Both lanes clean: `[arrow]`, `[sql]`, `[yaml]`" and the
    dry run would have closed the issue.
    """
    rows: list[tuple[str, str]] = []
    lanes = list(lanes or LANES)
    for extra in sorted(expected or []):
        for lane in lanes:
            source = reports.diffs if lane == "newest" else reports.floors
            if extra not in source and (extra, lane) not in reports.smokes:
                rows.append((extra, f"`[{extra}]` {lane}: reported nothing at all — no resolution and no verdict"))
    for extra in sorted(reports.diffs):
        if (extra, "newest") not in reports.smokes:
            rows.append((extra, f"`[{extra}]` newest: a diff report with no smoke verdict"))
    for extra in sorted(reports.floors):
        if (extra, "floor") not in reports.smokes:
            rows.append((extra, f"`[{extra}]` floor: a floor report with no smoke verdict"))
    for extra, lane in sorted(reports.smokes):
        source = reports.diffs if lane == "newest" else reports.floors
        if extra not in source:
            rows.append((extra, f"`[{extra}]` {lane}: a smoke verdict with no report"))
    return rows


def _incomplete_legs(
    reports: Reports,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
) -> list[str]:
    """The sentences ``_incomplete_leg_rows`` produces, without their extras."""
    return [text for _, text in _incomplete_leg_rows(reports, expected, lanes)]


def _parse_expected(raw: str) -> list[str]:
    """The extras or lanes a run was asked to cover, as JSON or a comma list.

    The workflow already computes and validates both sets in `setup`; they are
    passed through verbatim rather than recomputed, so a dispatch narrowed to
    one extra does not report the other thirteen as lost, and one narrowed to
    one lane does not report the other lane's fourteen legs as lost either.
    """
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part.strip() for part in text.split(",") if part.strip()]


def _lanes_present(reports: Reports) -> set[str]:
    """Which lanes this run actually produced reports for.

    A dispatch can select one lane, and a body that does not say so reads as a
    statement about both. Derived from the reports themselves rather than from
    the dispatch input, so it stays true when a lane runs and produces nothing.
    """
    lanes = {lane for _, lane in reports.smokes}
    if reports.diffs:
        lanes.add("newest")
    if reports.floors:
        lanes.add("floor")
    return lanes


def has_signal(
    reports: Reports,
    register: dict[tuple[str, str], tuple[str, str]] | None = None,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
) -> bool:
    """Whether this run has anything a maintainer has not already decided about.

    A red smoke counts even when the resolution itself is clean: the isolated
    per-extra install is the only thing that exercises an extra's declared set
    alone, so its verdict is a finding in its own right. Before it reached this
    predicate a red smoke reached only a red run, which the durable-TODO
    principle in ``sdd/CI-OPERATIONS.md`` says is not enough to rely on.

    A finding already in the register does **not** count, in whichever lane it
    was registered for. Its owner and its rationale are committed, so holding
    the issue open for it would make every week's issue look identical and
    train the reader to skip it. **Version drift is never suppressed** — a row
    registers a *verdict* somebody owns, not the movement of a package, and the
    movement is what the newest lane exists to report.
    """
    known = set(register or {})
    if any(r.get("status") in ("drift", "needs_refresh", "error") for r in reports.diffs.values()):
        return True
    if reports.unreadable or _incomplete_legs(reports, expected, lanes):
        return True
    if any((e, "floor") not in known and r.get("status") == "error" for e, r in reports.floors.items()):
        return True
    return any(v.get("smoke") == "fail" and (extra, lane) not in known for (extra, lane), v in reports.smokes.items())


def _drift_row(entry: dict) -> str:
    """One `| package | baseline | resolved |` row, tolerant of a partial entry.

    `.get` rather than subscripts for the reason `_load_reports` gives: a
    malformed artefact costs its own rows, never the whole body. Measured before
    this existed — a `stable_drift` entry missing `package` raised `KeyError`
    out of `_render_body`, the step exited 1, and every other extra's rows went
    with it, one function after the load was hardened against that exact class.
    """
    return f"| `{entry.get('package', '?')}` | `{entry.get('baseline') or '—'}` | `{entry.get('resolved') or '—'}` |"


def decide(
    reports: Reports,
    register: dict[tuple[str, str], tuple[str, str]] | None = None,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
) -> tuple[str, str]:
    """What this run would do to the rolling issue, and the reason.

    Returns ``("update" | "close" | "leave", reason)``.

    **One decision, consulted by both paths.** The dry run and the real run used
    to derive their verdict separately — the dry run from ``has_signal`` alone,
    the real one from ``has_signal`` *and* the both-lanes guard below — so on a
    single-lane dispatch the preview said "would close the issue" while the run
    it previewed would have left the issue alone. Measured on an all-clean
    newest-only run. A preview that disagrees with the thing it previews is
    worse than no preview, and the only fix that stays fixed is having one
    function for both to consult.
    """
    if has_signal(reports, register, expected, lanes):
        return "update", "something in this run is unresolved"
    # All clear — but only a run that covered BOTH lanes may close the issue.
    # A single-lane dispatch sees none of the other lane's findings, so closing
    # on its say-so discards the scheduled run's state: the issue disappears and
    # the findings that opened it are neither fixed nor recorded anywhere. The
    # header's warning about a single-lane dispatch rewriting the body does not
    # cover this, because the body is recoverable and a closed issue is not.
    covered = _lanes_present(reports)
    if covered != set(LANES):
        return "leave", f"all clear in {sorted(covered)}, but this run did not cover both lanes"
    return "close", "all clear in both lanes"


def _render_body(
    reports: Reports,
    run_url: str,
    register: dict[tuple[str, str], tuple[str, str]] | None = None,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("Weekly drift check across every `[<extra>]` in `pyproject.toml`.")
    lines.append("")
    lines.append(f"Last run: [{run_url}]({run_url})")
    lines.append("")

    # `.get` for every field this function reads, for the reason
    # `_load_reports` names: a report that parses but is missing a key must cost
    # its own rows, never every other extra's. `status` itself is no longer
    # among them — a report without one never reaches here, because
    # `_load_reports` now names it unreadable rather than letting it through to
    # be skipped by every section in silence.
    diffs = reports.diffs
    needs_refresh = [e for e, r in diffs.items() if r.get("status") == "needs_refresh"]
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

    drift_extras = [e for e, r in diffs.items() if r.get("status") == "drift"]
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
                    lines.append(_drift_row(d))
                lines.append("")
            pre = r.get("prerelease_drift", [])
            if pre:
                lines.append("**Pre-release drift (informational):**")
                lines.append("")
                lines.append("| Package | Baseline | Resolved |")
                lines.append("|---|---|---|")
                for d in pre:
                    lines.append(_drift_row(d))
                lines.append("")

    incomplete = _incomplete_legs(reports, expected, lanes)
    if incomplete:
        lines.append("## Incomplete legs")
        lines.append("")
        lines.append(
            "Each leg writes both a report and a smoke verdict, `skipped` "
            "included, so a missing half has one of three causes: the leg died "
            "before uploading, two uploads landed on one filename, or the "
            "docker services the smoke needs did not come up — the workflow "
            "skips the smoke in that case **on purpose**, because publishing a "
            "connection-refused failure as a dependency finding would send a "
            "maintainer to raise a floor that is fine. The run log says which. "
            "Rows these legs would have contributed are absent from everything "
            "above — and an absent row reads exactly like a clean one."
        )
        lines.append("")
        for entry in incomplete:
            lines.append(f"- {entry}")
        lines.append("")

    if reports.unreadable:
        lines.append("## Unreadable reports")
        lines.append("")
        lines.append(
            "These uploads could not be parsed, or parsed into something with "
            "no `status` to place it by, and were skipped — so the rows they "
            "would have contributed are missing from everything above. "
            "The usual cause is two artefacts landing on one filename: an "
            "artefact is rooted at the least common ancestor of its files, so "
            "a single-file upload contributes that file at the artefact root "
            "and `merge-multiple` has no directory to keep them apart."
        )
        lines.append("")
        for name in reports.unreadable:
            lines.append(f"- `{name}`")
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

    lines.extend(_render_isolation_findings(reports, register or {}))
    lines.extend(_render_floor_lane(reports, register or {}))
    lines.extend(_render_smoke_verdicts(reports, register or {}, lanes))

    # Clear means clear in both lanes. An extra whose newest resolution is `ok`
    # while its floor will not install, or while either lane's smoke is red, is
    # not a clean extra — listing it here is what would let the finding pass.
    # An extra with an incomplete leg is excluded for the same reason one lane
    # down: the lane that did not report cannot be called clean, and this list
    # is the sentence a reader takes away.
    floor_bad = set(reports.floors) - {e for e, r in reports.floors.items() if r.get("status") == "resolved"}
    smoke_bad = {e for (e, _), v in reports.smokes.items() if v.get("smoke") == "fail"}
    lost = {extra for extra, _ in _incomplete_leg_rows(reports, expected, lanes)}
    clear = [
        e
        for e, r in diffs.items()
        if r.get("status") == "ok" and e not in floor_bad and e not in smoke_bad and e not in lost
    ]
    if clear:
        lines.append("## Clear")
        lines.append("")
        # Name the lanes that actually ran. A single-lane dispatch that claimed
        # "both lanes clean" would report a check nobody performed, which is
        # worse than reporting nothing.
        ran = _lanes_present(reports)
        scope = "Both lanes clean" if ran == {"newest", "floor"} else f"Clean ({', '.join(sorted(ran))} lane only)"
        lines.append(f"{scope}: " + ", ".join(f"`[{e}]`" for e in clear))
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
        "--expect-extras",
        default="",
        help=(
            "JSON array or comma-separated list of the extras this run was asked "
            "to cover. An extra named here that reported nothing at all is a lost "
            "leg, which is otherwise indistinguishable from a clean one."
        ),
    )
    parser.add_argument(
        "--expect-lanes",
        default="",
        help=(
            "JSON array or comma-separated list of the lanes this run was asked "
            "to cover (newest, floor). A leg is (extra, lane), so the claim space "
            "needs both halves: without this an extra that reported on one lane "
            "and lost the other reads as complete. Defaults to both lanes."
        ),
    )
    parser.add_argument(
        "--known-findings",
        type=Path,
        default=KNOWN_FINDINGS,
        help="Path to the known-findings register (default: infra/drift-locks/KNOWN-FINDINGS.md).",
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

    register = load_known_findings(args.known_findings)
    expected = _parse_expected(args.expect_extras)
    lanes = _parse_expected(args.expect_lanes) or list(LANES)
    body = _render_body(reports, args.run_url, register, expected, lanes)
    if args.dry_run:
        # Before any `gh` call, so a dry run cannot reach the issue even to
        # read it: a dispatch from a branch must be observable without leaving
        # a trace on the rolling issue the scheduled runs own.
        print(body)
        action, reason = decide(reports, register, expected, lanes)
        would = {"update": "create/update", "close": "close", "leave": "leave alone"}[action]
        print(
            f"(dry run — would {would} the issue titled {args.title!r}: {reason})",
            file=sys.stderr,
        )
        return 0

    action, reason = decide(reports, register, expected, lanes)
    existing = _find_open_issue(args.repo, args.title)

    if action == "update":
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

    if action == "leave":
        print(f"{reason.capitalize()}; leaving the issue alone.", file=sys.stderr)
        return 0

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
