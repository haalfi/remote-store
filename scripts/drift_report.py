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
  ``infra/drift-locks/KNOWN-FINDINGS.md`` with an unexpired ``Review by``:
  somebody owns it, so it renders with its owner and does not hold the issue
  open. Version drift is never suppressed this way.
* A supported interpreter **past its security-support window** with no unexpired
  row in ``infra/drift-locks/PYTHON-SUPPORT.md`` → create-or-update, but only on
  an **unnarrowed** run: every lane *and* every extra, not the lane half alone
  (``SupportWindowState`` says why). That half of the watch fires on the calendar
  rather than on anything a run uploaded, which is why it is attached to
  ``Reports`` before the emptiness guard and why a narrowed dispatch cannot let
  it rewrite the body.
* Everything clean in both lanes, and no unowned crossing → comment "drift
  cleared" on the open issue (if any) and close it; no-op if no issue is open.
* Everything clean but only **one** lane ran → leave the issue alone. A
  single-lane dispatch has not seen what the other lane would have found, and a
  closed issue is not recoverable the way a rewritten body is.
* Everything clean, both lanes, but an **unowned crossing** a narrowed run may
  not act on → leave the issue alone, for that same reason. Withholding the
  update while permitting the close would take the worse half of the trade: the
  body is recoverable, a closed issue is not. So a narrowed run neither rewrites
  nor closes, and the next unnarrowed run decides.

``Review by`` is read by code in **both** registers, through one predicate: past
its date a row stops silencing its finding and the finding reappears as new. It
used to be read by nothing, which ``KNOWN-FINDINGS.md`` recorded as a hazard it
did not enforce.

``--dry-run`` renders the body and touches no issue, so a dispatch from a
branch is observable without writing to the issue the scheduled runs own.

Drift-gate::

    kind:       report
    surfaces:   the current per-extra dependency state in both lanes — the newest resolution's
        drift against the committed baselines, the declared floors' resolution, and each lane's
        smoke verdict — plus each supported interpreter's standing against the security-support
        window Rule 8 publishes, as a rolling GitHub issue it opens, updates or closes; it acts
        on that state rather than asserting anything, so nothing it FINDS makes it exit non-zero.
        What does is an input it cannot interpret — a `Review by`, a `--today`, an `--expect-extras`
        — since guessing would silence a finding, drop the window section or misreport which legs
        ran. Every one of them is reported rather than raised, which a test pins structurally rather
        than by listing them. Stated as a class on purpose: earlier revisions of this block counted
        the cases, and every count was falsified by the next input added. Beyond the inputs, a
        failing `gh` call still exits non-zero as a traceback
    domain:     process
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

from drift_check import list_extras  # noqa: E402  — one driver for the extras claim space
from python_support import SupportWindow, UnknownInterpreterError, windows  # noqa: E402  — sibling module


@dataclass(frozen=True)
class SupportWindowState:
    """Where each supported interpreter stands, and which crossings nobody owns.

    ``rows`` is every supported interpreter, so the section renders on a clean
    week too: how many days a version has *left* is the thing a reader cannot
    compute from the policy page's prose, which is the whole reason the chart
    exists, arriving
    on the issue instead.

    ``unregistered`` is the subset past its window with no live row in
    ``infra/drift-locks/PYTHON-SUPPORT.md``. ``holds_issue`` is whether those may
    hold the rolling issue open, and it is **not** simply ``bool(unregistered)``:
    a crossing is true on every run, including a narrowed ``workflow_dispatch``,
    and a narrowed non-dry run re-renders the whole issue body from its slice and
    drops every other row (BUG-282). So a crossing counts as a signal only on an
    **unnarrowed** run — every lane and every extra. Without that, adding this
    signal would have turned every single-extra dispatch into a body-destroying
    rewrite.

    Both halves of "unnarrowed" are load-bearing and the lane half alone is not
    enough: `extra: s3, lane: all` passes a lanes-only test and is exactly the
    single-extra rewrite the warning is about.

    **What a narrowed run would otherwise do is close the issue, not leave it
    alone.** Measured on that same `extra: s3, lane: all` shape with both lanes
    clean and 3.10 one day past its window: ``_lanes_present`` is complete, so
    with no signal ``decide`` reached ``close``. Withholding the update alone
    therefore bought the recoverable outcome by permitting the unrecoverable
    one, which is the opposite of the ranking ``decide`` already states. So
    ``decide`` refuses to close over an ``unregistered`` crossing as well, and
    this flag means only "may this force an update", never "may this be
    ignored".
    """

    rows: tuple[SupportWindow, ...] = ()
    unregistered: tuple[str, ...] = ()
    holds_issue: bool = False


@dataclass(frozen=True)
class Reports:
    """Everything this run has to say, keyed for rendering.

    ``diffs`` and ``floors`` hold one report per extra; ``smokes`` is keyed
    ``(extra, lane)`` because an extra has a verdict per lane.

    ``windows`` is the odd one out, and it is here rather than beside the call
    that needs it **because of** ``__bool__``. ``main`` returns early when this
    object is falsy, and the calendar half of the support-window watch comes from
    no artefact at all — so on a run where the download produced nothing, a
    window crossing would be unreachable: no body, no issue, exit 0. That is the
    silent-close failure ``_load_reports`` was hardened against, arriving through
    the guard instead. Putting the state in the thing ``main`` tests makes the
    guard correct by construction rather than by remembering.
    """

    diffs: dict[str, dict]
    floors: dict[str, dict]
    smokes: dict[tuple[str, str], dict]
    unreadable: list[str] = field(default_factory=list)
    windows: SupportWindowState = field(default_factory=SupportWindowState)

    def __bool__(self) -> bool:
        # `holds_issue`, **not** `unregistered`. A crossing is true on every run,
        # so keying the guard on `unregistered` makes this object truthy on a
        # narrowed dispatch too — and then `main` proceeds, `_incomplete_legs`
        # reports the extras the slice did not cover as lost, and `decide`
        # answers `update`, re-rendering the whole rolling issue from that
        # slice. That is BUG-282, and a regression against the behaviour this
        # guard had before the calendar signal existed. Measured on a
        # one-extra-of-fourteen dispatch with an empty reports directory and a
        # crossing: `holds_issue=False`, `unregistered=('3.10',)`, and the run
        # created the issue. `test_a_narrowed_dispatch_with_no_artefacts_leaves_the_issue_alone`
        # pins it.
        return bool(self.diffs or self.floors or self.smokes or self.unreadable or self.windows.holds_issue)


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
        # Every shape assumption this loop makes is checked HERE, in one place,
        # rather than where each one is first used. The docstring above promises
        # that a file which "parses into something this script cannot place" is
        # named and skipped; it was false twice over, and both were measured:
        # `[1, 2]` raised `TypeError: list indices must be integers` on
        # `data["extra"]`, and `{"extra": ["s3"], …}` raised
        # `TypeError: unhashable type: 'list'` two branches later, at
        # `diffs[extra]`. Catching the first without the second is how the fix
        # for a class becomes another instance of it: the assumptions are that
        # the document is an object and that `extra` and `lane` are strings, so
        # those are what this guard states.
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError(f"expected a JSON object, got {type(data).__name__}")
            extra = data["extra"]
            lane = data.get("lane", "newest")
            for field, value in (("extra", extra), ("lane", lane)):
                if not isinstance(value, str):
                    raise TypeError(f"{field!r} must be a string, got {type(value).__name__}")
        except (json.JSONDecodeError, KeyError, OSError, TypeError) as exc:
            print(f"::warning::unreadable drift report {path}: {exc}", file=sys.stderr)
            unreadable.append(path.name)
            continue
        if "smoke" in data:
            smokes[(extra, lane)] = data
            continue
        if "status" not in data:
            # A resolution report with no `status` is unplaceable: every section
            # below keys on it. Naming it here is what keeps it out of the
            # silent-close path.
            print(f"::warning::drift report {path} has no 'status'", file=sys.stderr)
            unreadable.append(path.name)
        elif lane == "floor":
            floors[extra] = data
        else:
            diffs[extra] = data
    return Reports(diffs=diffs, floors=floors, smokes=smokes, unreadable=sorted(unreadable))


def _known_note(register: dict[tuple[str, str], tuple[str, str]], key: tuple[str, str], today: date) -> str | None:
    """The "somebody owns this" sentence for a finding, or ``None`` if nobody does.

    One home **for the prose sections** — ``_render_isolation_findings`` and
    ``_floor_rows`` both take it from here, so the expiry cannot be shown in one
    and omitted in the other. A row past its ``Review by`` still names its
    owner — dropping the mention would lose the only pointer a reader has — but
    says the date has passed, which is the same fact ``has_signal`` acted on
    when it let the finding hold the issue open.

    **It is not the only place that sentence is built**, and a reader adding a
    detail here should know that. ``_render_smoke_verdicts`` builds an
    owner-plus-expiry cell inline for the same ``(extra, lane)`` register,
    because a table cell cannot carry a sentence, and
    ``_render_support_windows`` builds a third for the *interpreter* register,
    which is keyed differently. All three agree today because they were written
    together; nothing makes them agree by construction, so a change here needs
    the other two checked by hand.
    """
    if key not in register:
        return None
    owner, review = register[key]
    if is_expired(review, today):
        return f"_Known: owned by {owner}, but the review date {review} has passed, so it is reported as new again._"
    return f"_Known: owned by {owner}, review by {review}._"


def _render_isolation_findings(
    reports: Reports,
    register: dict[tuple[str, str], tuple[str, str]],
    today: date,
) -> list[str]:
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
        note = _known_note(register, (extra, "newest"), today)
        if note:
            lines.append(note)
            lines.append("")
        reason = verdict.get("reason")
        if reason:
            lines.append("```")
            lines.append(str(reason).strip())
            lines.append("```")
            lines.append("")
    return lines


# Either register's key type: `(extra, lane)` for the dependency table, a bare
# version for the interpreter one. `silencing` is one rule over both.
_RegisterKey = TypeVar("_RegisterKey")

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
    # `is_file`, not `exists`: a path that is a directory passes `exists()` and
    # then raises `IsADirectoryError` out of `read_text`, which is an input this
    # script cannot interpret arriving as a traceback. Absent stays an empty
    # register -- neither register is required -- while a path that is there and
    # unreadable is reported, because silently reading a typo as "no register"
    # would un-silence every finding without saying why.
    if not path.exists():
        return {}
    if not path.is_file():
        raise UnusableInputError(f"{path} is not a file, so it cannot be read as a register")
    register: dict[tuple[str, str], tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _REGISTER_ROW_RE.match(line.strip())
        if match:
            key = (match.group("extra"), match.group("lane").strip())
            review = match.group("review").strip()
            _review_date(review, where=f"{path}, row `[{key[0]}]` / {key[1]}")
            register[key] = (match.group("owner").strip(), review)
    return register


PYTHON_SUPPORT_REGISTER = Path(__file__).resolve().parent.parent / "infra" / "drift-locks" / "PYTHON-SUPPORT.md"

# `| `3.10` | owner | rationale | 2026-12-31 |` — four cells, and the first is a
# BACKTICKED minor version. Both halves keep it provably disjoint from
# `_REGISTER_ROW_RE` above, which needs a bracketed `[extra]` first cell and
# five cells. Measured before the two registers were split into separate files:
# a four-cell loader written like this one, pointed at KNOWN-FINDINGS.md, matched
# all seven of its dependency rows plus the header and the separator, inventing
# seven "interpreters" whose `Review by` was a prose paragraph. `Review by` is
# date-compared below, so that would have been a crash or a row that never
# expires. Separate files remove the collision; the row shapes make it
# unreachable even if the files are ever merged.
_PYTHON_REGISTER_ROW_RE = re.compile(
    r"^\|\s*`(?P<version>\d+\.\d+)`\s*\|(?P<owner>[^|]*)\|[^|]*\|(?P<review>[^|]*)\|\s*$"
)


class UnusableInputError(Exception):
    """An argument this script cannot interpret, so it reports instead of guessing.

    Same posture as ``RegisterDateError`` and ``python_support``'s
    ``UnknownInterpreterError``: a value that should be a list or a date and is
    not would otherwise reach ``main`` as a traceback, and a traceback on the
    weekly run says less than the sentence the raiser can write. The workflow
    interpolates ``--expect-extras`` and ``--expect-lanes`` from another job's
    outputs, so a malformed one is the failure most likely to arrive from a
    template rather than from a person.
    """


class RegisterDateError(Exception):
    """A register row's ``Review by`` is not a date this can compare.

    Raised by the **loaders**, not by ``is_expired``, and that placement is the
    whole point: a loader knows the file it is reading and the row it is on, so
    the message can name both. ``is_expired`` sees a bare string and could only
    ever say which *value* was bad, which does not localize, and
    ``sdd/DRIFT-RULES.md`` [Rule 2](../sdd/DRIFT-RULES.md#localize) asks a
    mechanism to name the element rather than the fact of a difference.

    The argument is about finding a row, not about how many there are: with two
    files a bad value does not say which one to open, and that is true of the
    first row as much as the hundredth. So no count appears here — an earlier
    revision hedged one ("eight-odd rows") and was wrong about both the total
    and its distribution.
    """


def _review_date(value: str, *, where: str) -> date:
    """``value`` as a date, or a ``RegisterDateError`` naming where it came from."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegisterDateError(
            f"{where}: `Review by` is {value!r}, which is not an ISO date (YYYY-MM-DD). A row whose date "
            f"cannot be compared would silence its finding forever, so this is a hard failure rather than "
            f"a row that never expires."
        ) from exc


def load_python_support_register(path: Path = PYTHON_SUPPORT_REGISTER) -> dict[str, tuple[str, str]]:
    """``{version: (owner, review_by)}`` from the interpreter register.

    Keyed on the interpreter alone: unlike a dependency finding there is no lane
    to distinguish, because a window crossing is a fact about the calendar
    rather than about a resolution.
    """
    if not path.exists():
        return {}
    if not path.is_file():  # same reason as the dependency loader above
        raise UnusableInputError(f"{path} is not a file, so it cannot be read as a register")
    register: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _PYTHON_REGISTER_ROW_RE.match(line.strip())
        if match:
            version = match.group("version")
            review = match.group("review").strip()
            _review_date(review, where=f"{path}, row `{version}`")
            register[version] = (match.group("owner").strip(), review)
    return register


def is_expired(review_by: str, today: date) -> bool:
    """Whether a register row has passed its ``Review by`` date.

    **One predicate for both registers**, which is the point. Before this,
    ``KNOWN-FINDINGS.md``'s date was read by nothing — the file said so itself,
    as a hazard it did not enforce — so a row past its date kept silencing its
    finding until somebody noticed. Now the date is the mechanism in both files
    and there is one rule for the column rather than one per table.

    Every caller reaches this with a value a loader already validated, so the
    unparseable case is refused earlier and with the file and row named -- see
    ``RegisterDateError``. The re-raise here is the backstop for a caller that
    hands over a string from somewhere else.

    Raises:
        RegisterDateError: If the cell is not an ISO date.
    """
    return _review_date(review_by, where="a register row") < today


def silencing(register: dict[_RegisterKey, tuple[str, str]], today: date) -> set[_RegisterKey]:
    """The register keys still entitled to present their finding as known.

    Expired rows are dropped here and nowhere else, so every caller that asks
    "is this owned?" gets the same answer. Generic in the key because the two
    registers key differently -- ``(extra, lane)`` and a bare version -- while
    the expiry rule over them is one rule.
    """
    return {key for key, (_owner, review) in register.items() if not is_expired(review, today)}


def support_window_state(
    today: date,
    register: dict[str, tuple[str, str]] | None = None,
    *,
    holds_issue: bool = True,
) -> SupportWindowState:
    """The calendar half of the support-window watch, as of ``today``.

    Args:
        today: The day to measure against, passed rather than read so a dry run
            and its own tests describe the same day.
        register: ``load_python_support_register()``'s result, or ``None`` for an
            empty register.
        holds_issue: Whether a crossing on this run may hold the rolling issue
            open. False for a narrowed dispatch — see ``SupportWindowState``.
    """
    register = register or {}
    live = silencing(register, today)
    rows = tuple(windows(today))
    unregistered = tuple(row.version for row in rows if row.past and row.version not in live)
    return SupportWindowState(rows=rows, unregistered=unregistered, holds_issue=holds_issue and bool(unregistered))


def _render_floor_lane(
    reports: Reports,
    register: dict[tuple[str, str], tuple[str, str]],
    today: date,
) -> list[str]:
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
        lines.extend(_floor_rows(reports, broke, floor_smoke, register, today))

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
        lines.extend(_floor_rows(reports, refused, floor_smoke, register, today))

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
        lines.extend(_floor_rows(reports, harness, floor_smoke, register, today))

    return lines


def _floor_rows(
    reports: Reports,
    extras: list[str],
    floor_smoke: dict[str, dict],
    register: dict[tuple[str, str], tuple[str, str]],
    today: date,
) -> list[str]:
    lines: list[str] = []
    for extra in extras:
        report = reports.floors.get(extra, {})
        lines.append(f"**`[{extra}]`**")
        lines.append("")
        note = _known_note(register, (extra, "floor"), today)
        if note:
            lines.append(note)
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
    *,  # keyword-only for the same reason as `_render_body`
    today: date | None = None,
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
                owner, review = register[(extra, lane)]
                expired = ", review date passed" if is_expired(review, today or date.today()) else ""
                cell += f" — known, {owner}{expired}"
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


def _parse_expected(raw: str, *, allowed: set[str] | None = None) -> list[str]:
    """The extras or lanes a run was asked to cover, as JSON or a comma list.

    The workflow already computes and validates both sets in `setup`; they are
    passed through verbatim rather than recomputed, so a dispatch narrowed to
    one extra does not report the other thirteen as lost, and one narrowed to
    one lane does not report the other lane's fourteen legs as lost either.

    Args:
        raw: The flag's value, as JSON or a comma-separated list.
        allowed: When given, the closed set every name must belong to. Passed for
            lanes, whose vocabulary is ``LANES``; omitted for extras, whose set
            is ``pyproject.toml``'s and is compared elsewhere.

    Raises:
        UnusableInputError: If the value opens like JSON and does not parse, if
            it is not a list, if any element is not a string, or if ``allowed``
            is given and a name is outside it. Naming the value is the point —
            the caller is a workflow expression, so the operator needs to see
            what arrived rather than a decoder traceback or, worse, a rendered
            issue built from it.

            **Each of those four is a measured failure, not a precaution.** The
            first revision checked nothing: `[bad` tracebacked. The second
            checked the container only, and its own docstring claimed it checked
            "a list of names" — so `--expect-extras '[1,2]'` was coerced through
            `str()` and rewrote the rolling issue with `[1]` and `[2]` as
            fabricated incomplete legs. And `--expect-lanes bogus` was accepted
            whole: the body announced "This run covered the bogus lane only",
            printed a `Bogus` verdict column, and `_incomplete_leg_rows` mapped
            the unknown lane onto the floor lane, so the run read as complete.
    """
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnusableInputError(f"{text!r} starts like JSON but does not parse: {exc}") from exc
        if not isinstance(items, list):
            raise UnusableInputError(f"{text!r} parsed to {type(items).__name__}, not a list of names")
        for item in items:
            if not isinstance(item, str):
                raise UnusableInputError(f"{text!r} contains {item!r}, which is not a name")
        names = list(items)
    else:
        names = [part.strip() for part in text.split(",") if part.strip()]
    if allowed is not None:
        unknown = [name for name in names if name not in allowed]
        if unknown:
            raise UnusableInputError(f"{', '.join(map(repr, unknown))} is not one of {sorted(allowed)}")
    return names


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
    *,
    today: date | None = None,
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

    **A row past its ``Review by`` stops counting as decided**, so it starts
    holding the issue open again. That is what ``today`` is for; it defaults to
    the day this runs, and is passed explicitly by the tests and by anything
    that needs a reproducible answer.

    An unowned **support-window crossing** counts too, on the terms
    ``SupportWindowState.holds_issue`` sets.
    """
    today = today or date.today()
    known = silencing(register or {}, today)
    if any(r.get("status") in ("drift", "needs_refresh", "error") for r in reports.diffs.values()):
        return True
    if reports.unreadable or _incomplete_legs(reports, expected, lanes):
        return True
    if reports.windows.holds_issue:
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
    *,
    today: date | None = None,
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
    if has_signal(reports, register, expected, lanes, today=today):
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
    # The same trade, applied to the calendar signal. `holds_issue=False`
    # withholds the *update* on a narrowed run, because a narrowed update
    # rewrites the body from its slice. It must withhold the *close* too, or the
    # narrowing takes the worse half of what this function already states: the
    # body is recoverable, a closed issue is not. Measured before this clause on
    # `extra: s3, lane: all` with both lanes clean and 3.10 one day past its
    # window -- the verdict was `close`, so the issue vanished while an
    # interpreter sat past its window with nobody named.
    #
    # **This covers the crossing, not the close in general.** The guard above is
    # the lane half of "narrowed" only, so a one-extra all-clean run with no
    # crossing still closes on one extra's evidence. That is pre-existing, filed
    # as BUG-291, and deliberately not widened here: it changes when the issue
    # auto-closes for every dispatch, which is its own change with its own
    # tests.
    if reports.windows.unregistered:
        return "leave", (
            f"all clear in both lanes, but {', '.join(reports.windows.unregistered)} "
            "is past its support window with nobody named, and this run was too narrow to say so on the issue"
        )
    return "close", "all clear in both lanes"


def _render_support_windows(
    state: SupportWindowState,
    register: dict[str, tuple[str, str]],
    today: date,
) -> list[str]:
    """Where every supported interpreter stands against its support window.

    **Renders on every run, not only when something has crossed.** A dependency
    row is worth printing only when it moved; a support window is worth printing
    because the number a reader cannot compute is how much time is *left*. That
    is the same argument the generated chart on the policy page makes, arriving
    where a maintainer already looks.

    Weekly is the resolution rather than a habit: what invalidates this section
    is a date passing, plus the two events that change its inputs — a new CPython
    final release, which happens each October, and a classifier edit. A window
    closing is not a breakage on the day it happens, so seven days of latency
    costs nothing; anything longer and a release could ship past a window nobody
    had looked at.
    """
    if not state.rows:
        return []
    lines = ["## Support windows", ""]
    lines.append(
        "Each supported interpreter, and how long we have promised to keep it. "
        "The window is CPython's own security-support lifetime, which is what "
        "Rule 8 of the dependency policy publishes. **A closed window licenses "
        "a drop; it never requires one** — nothing is broken on the day one "
        "closes, which is why this is a report rather than a gate."
    )
    lines.append("")
    lines.append("| Python | Released | Security support ends | Status |")
    lines.append("|---|---|---|---|")
    for row in state.rows:
        if not row.past:
            status = f"{row.days_remaining} days left"
        elif row.version in register:
            owner, review = register[row.version]
            expired = " — **review date passed**" if is_expired(review, today) else ""
            status = f"{-row.days_remaining} days past — known, {owner}, review by {review}{expired}"
        else:
            status = f"**{-row.days_remaining} days past, unregistered**"
        lines.append(f"| `{row.version}` | {row.released} | {row.ends} | {status} |")
    lines.append("")
    if state.unregistered:
        # `holds_issue`, not `unregistered`, decides which sentence is true. On a
        # narrowed dispatch a crossing renders but cannot force the rewrite, and
        # telling a reader it "holds this issue open" would send them looking for
        # an issue this run was never going to reopen -- the reading half of the
        # same distinction `Reports.__bool__` gets wrong when it keys on
        # `unregistered`. It does still stop this run closing the issue
        # (`decide`), so the narrowed sentence says both halves: a reader who is
        # told only what the run will not do cannot tell that from "no effect".
        holds = (
            "holds this issue open"
            if state.holds_issue
            else (
                "would hold this issue open on a full run; this one covered only part of the matrix, so it does not — "
                "it does stop this run closing the issue"
            )
        )
        lines.append(
            "An interpreter past its window with no row in "
            f"`infra/drift-locks/PYTHON-SUPPORT.md` {holds}. Decide "
            "it: drop the version, or add a row naming who owns keeping it and "
            "when that decision is re-read. A row whose `Review by` has passed "
            "stops silencing and reappears here."
        )
        lines.append("")
    if not state.unregistered and any(row.past for row in state.rows):
        lines.append("Every closed window above is registered, so none of them is holding this issue open.")
        lines.append("")
    return lines


def _render_body(
    reports: Reports,
    run_url: str,
    register: dict[tuple[str, str], tuple[str, str]] | None = None,
    expected: list[str] | None = None,
    lanes: list[str] | None = None,
    python_register: dict[str, tuple[str, str]] | None = None,
    # Keyword-only, like `has_signal` and `decide`, so the reproducibility guard
    # in `tests/scripts/test_drift_report.py` can police it by looking for a
    # `today=` keyword. A positional pass here would read as an omission to that
    # guard, and an omission is the defect it exists to catch.
    *,
    today: date | None = None,
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

    lines.extend(_render_isolation_findings(reports, register or {}, today or date.today()))
    lines.extend(_render_floor_lane(reports, register or {}, today or date.today()))
    lines.extend(_render_smoke_verdicts(reports, register or {}, lanes, today=today or date.today()))
    lines.extend(_render_support_windows(reports.windows, python_register or {}, today or date.today()))

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
        "--python-support-register",
        type=Path,
        default=PYTHON_SUPPORT_REGISTER,
        help=(
            "Path to the interpreter support-window register "
            "(default: infra/drift-locks/PYTHON-SUPPORT.md). A separate file from the "
            "known-findings register: the two are keyed differently and one loader per file "
            "is what keeps them from reading each other's rows."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Day to measure the support windows and the register review dates against, "
            "as YYYY-MM-DD (default: today). Mostly for tests and for reproducing a run."
        ),
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

    # Reported, not tracebacked, for the same reason as the registers below: a
    # flag this script introduced should not be the one failure path that says
    # `Invalid isoformat string` with no remedy.
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"::error::--today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
        return 1
    # A malformed `Review by` is a hard failure -- both register files say so,
    # since a date that cannot be compared silences its finding forever -- but a
    # hard failure is still a report rather than a traceback. The loaders name
    # the file and the row.
    try:
        register = load_known_findings(args.known_findings)
        python_register = load_python_support_register(args.python_support_register)
    except (RegisterDateError, UnusableInputError) as exc:
        print(f"::error::unusable register: {exc}", file=sys.stderr)
        return 1
    # Same posture again, for the two arguments the workflow interpolates from
    # another job's outputs rather than a person typing them.
    try:
        expected = _parse_expected(args.expect_extras)
        lanes = _parse_expected(args.expect_lanes, allowed=set(LANES)) or list(LANES)
    except UnusableInputError as exc:
        print(f"::error::unusable --expect-extras/--expect-lanes: {exc}", file=sys.stderr)
        return 1

    # The calendar state is attached BEFORE the emptiness guard below, which is
    # the whole point of it living on `Reports`: a run whose download produced
    # nothing must still be able to report a window crossing.
    #
    # A crossing may hold the issue only on an UNNARROWED run. The claim space
    # for "every extra" is `drift_check.list_extras()`, derived from
    # pyproject.toml rather than restated here (DRIFT-RULES Rule 3); the
    # workflow passes the dispatched slice in `--expect-extras`, so comparing
    # the two is what tells a full run from a narrowed one. An absent
    # `--expect-extras` reads as narrowed, which is the safe direction: the
    # section still renders, it just does not rewrite the issue the scheduled
    # runs own.
    unnarrowed = set(lanes) == set(LANES) and bool(expected) and set(expected) == set(list_extras())
    try:
        window_state = support_window_state(today, python_register, holds_issue=unnarrowed)
    except UnknownInterpreterError as exc:
        # The second hard failure, reported rather than tracebacked, for the
        # same reason as the register above: a classifier with no release date
        # makes the whole section uncomputable, and a traceback on the weekly
        # run says less than the message `python_support` already writes.
        # `preflight`'s `gen_python_support.py --check` refuses the same state,
        # so reaching this means a commit bypassed it.
        print(f"::error::undated interpreter classifier: {exc}", file=sys.stderr)
        return 1
    reports = dataclasses.replace(_load_reports(args.reports_dir), windows=window_state)
    if not reports:
        # Say what this run saw, not what a run could see. `Reports.__bool__`
        # keys on `holds_issue`, so a narrowed dispatch whose legs uploaded
        # nothing is falsy even with an interpreter past its window -- and the
        # old wording then denied a crossing this same run had just computed.
        # This is the third reader of the `holds_issue` / `unregistered`
        # distinction, after `__bool__` and the rendered section, and it is the
        # line a maintainer reads in a dispatch's step log.
        if reports.windows.unregistered:
            print(
                f"No drift reports found. {', '.join(reports.windows.unregistered)} is past its support window "
                "with nobody named, but this run was too narrow to act on it; the next full run will.",
                file=sys.stderr,
            )
        else:
            print("No drift reports found and no support window crossed; nothing to reconcile.", file=sys.stderr)
        return 0

    body = _render_body(reports, args.run_url, register, expected, lanes, python_register, today=today)
    if args.dry_run:
        # Before any `gh` call, so a dry run cannot reach the issue even to
        # read it: a dispatch from a branch must be observable without leaving
        # a trace on the rolling issue the scheduled runs own.
        print(body)
        action, reason = decide(reports, register, expected, lanes, today=today)
        would = {"update": "create/update", "close": "close", "leave": "leave alone"}[action]
        print(
            f"(dry run — would {would} the issue titled {args.title!r}: {reason})",
            file=sys.stderr,
        )
        return 0

    action, reason = decide(reports, register, expected, lanes, today=today)
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
