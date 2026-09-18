#!/usr/bin/env python3
"""BK-377: derive Rule 9's two-year test instead of remembering it at release.

Rule 9 of the published dependency policy says a floor may be raised in any
release, including a patch, as long as every version it newly excludes is itself
at least two years past its own release; excluding a version younger than that
is a breaking change. Until this script existed nothing derived that. The
release checklist said so in terms — *"Nothing derives this, the published
promise is the only record, which is why it is a checklist line rather than a
gate"* — and a checklist line is a person remembering.

What it does, per user-facing extra and then per package:

1. read the declared floors at a base revision and at the working tree;
2. for each floor that went **up**, ask PyPI which releases the raise newly
   excludes, take the newest of them, and read its upload date;
3. compare that date against the two-year cutoff and say which side it falls
   on. Older than the cutoff is patch-eligible. Younger is a breaking change,
   and the CHANGELOG entry owes a ``**Breaking**`` marker and a migration
   section.

**Not in ``preflight``, ``lint`` or ``docs-gate``, and the reason is the
network.** Step 2 fetches ``pypi.org/pypi/<name>/json``. A gate a contributor
runs offline, or that CI runs on every pull request, cannot depend on a third
party being reachable, and a support-window answer is needed once per release
rather than once per diff. So this is named from ``CONTRIBUTING.md``'s Phase 0
checklist and run by hand as ``hatch run check-support-windows``.
``sdd/DRIFT-RULES.md`` Rule 5 asks an advisory check to record that reason
rather than leave it inferred; this paragraph is the record.

**The floors come from one place.** ``check_conda_recipe_pins.declared_constraints``
already collapses every user-facing extra's declarations into the strictest
specifier per package, and it is imported rather than reimplemented — Rule 1
prefers one driver, and a second specifier parser is a second thing to get
wrong. ``gen_features._EXCLUDE_EXTRAS`` decides which extras are user-facing,
reached through that same function.

Bounds, because an unstated one gets trusted past its range:

* **Pre-releases are excluded from the claim space.** Otherwise the newest
  version a raise newly excludes is typically a pre-release of the new floor's
  own line — a ``14.0.0rc1`` uploaded days before ``14.0.0`` — and every raise
  would read as breaking. This repository does live with such versions
  (its drift guard resolves with ``--pre``), so the exclusion is a choice about
  what Rule 9 promises: a range's *stable* releases.
* **A release is yanked only when every file of it is.** PyPI carries ``yanked``
  per file with no per-release flag, so a partially yanked release still counts
  and is dated from its live files. ``info.yanked`` describes only the latest
  version and is not read.
* **A version with no files is skipped, and that is right rather than a gap.**
  PyPI has plenty of them (``pyarrow 0.1.0``, several early ``urllib3``
  releases): registered versions with no distribution and so no upload date. No
  resolver could have installed one, so excluding it strands nobody, and the
  test belongs on the newest version a user could actually have resolved to.
  The same reasoning covers a fully yanked release. What the check cannot do is
  tell you a version *was* skipped; it reports the answer it reached, not the
  candidates it discarded.
* **A version with live files and no upload timestamp is UNDECIDED, not
  skipped.** That justification does not extend to it: such a release is
  installable, so leaving it out of the claim space would hand the test to an
  older release and report **patch-eligible** for a raise that strands somebody.
  Surveyed over the whole claim space — all **19** packages ``floors()`` returns
  for the committed ``pyproject.toml``, 2617 registered versions between them,
  of which 1991 are stable, non-yanked and dateable — PyPI produced this shape
  **zero** times, so the branch is defensive. It is kept loud rather than
  removed because the failure it prevents is a false pass. (An earlier count
  said "the five packages this repository declares floors for"; five was a spot
  check, and the widened survey only strengthens the result.)
* **Only ``>=`` floors are compared.** The collapse this borrows refuses
  anything else rather than guessing, and reports the package it refused on.
* **A package that appears for the first time is not a raise**, and neither is
  a floor that went down. Both are reported as context, not judged.
* **The extras are classified by the *current* exclusion list**, applied to both
  revisions. An extra that was user-facing at the base revision and is dev-only
  now is read as dev-only on both sides.
* **It says nothing about whether the CHANGELOG actually carries the marker.**
  It says which marker is owed. The link between a marker and its migration
  section is ``scripts/check_breaking_migration_link.py``.

Drift-gate::

    kind:       pair
    compares: the declared dependency floors at a base git revision and in the working tree ↔ the
        PyPI upload dates of the releases each raised floor newly excludes, over the packages named
        by every user-facing extra
    domain:     process
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.version import InvalidVersion, Version

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_conda_recipe_pins import (  # noqa: E402  — one driver for the floor collapse
    IrreconcilableExtras,
    UnsupportedSpecifier,
    declared_constraints,
)
from python_support import DEPENDENCY_WINDOW_MONTHS, dependency_cutoff  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPI_JSON = "https://pypi.org/pypi/{name}/json"


@dataclass(frozen=True)
class Raise:
    """One package's floor moving up between two revisions."""

    package: str
    old: Version
    new: Version


@dataclass(frozen=True)
class Verdict:
    """What Rule 9 says about one raise, and what the answer was derived from."""

    package: str
    old: Version
    new: Version
    excluded: Version | None
    released: date | None
    breaking: bool
    note: str
    # Set when the check could not reach an answer at all, which is a third
    # outcome rather than a shade of the other two: `breaking=False` on its own
    # would read as compliant. Inferring it from `excluded`/`released` was the
    # first spelling and it could not tell "nothing to exclude" (a pass) from
    # "could not be dated" (not an answer).
    undecided: bool = False


def floors(pyproject: Path) -> dict[str, Version]:
    """The ``>=`` lower bound per package across every user-facing extra."""
    out: dict[str, Version] = {}
    for package, spec in declared_constraints(pyproject).items():
        lower = [clause for clause in spec if clause.operator == ">="]
        if lower:
            out[package] = max(Version(clause.version) for clause in lower)
    return out


def raised(base: dict[str, Version], head: dict[str, Version]) -> list[Raise]:
    """Packages whose floor went up, sorted by name so the report is stable."""
    return sorted(
        (
            Raise(package, base[package], head[package])
            for package in head
            if package in base and head[package] > base[package]
        ),
        key=lambda r: r.package,
    )


def read_pyproject_at(revision: str, workdir: Path) -> Path:
    """``pyproject.toml`` as of ``revision``, written to a file to be parsed.

    ``declared_constraints`` takes a path, and borrowing it unchanged is worth
    one temporary file.
    """
    blob = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{revision}:pyproject.toml"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    path = workdir / "pyproject.toml"
    path.write_text(blob, encoding="utf-8")
    return path


def previous_tag() -> str:
    """The most recent tag reachable from HEAD, which is the previous release.

    Tags are not in a fresh shallow clone; ``git fetch --tags`` first if this
    cannot find one.
    """
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "describe", "--tags", "--abbrev=0"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def fetch_releases(name: str) -> dict[Version, date | None]:
    """``{version: earliest upload date}`` for every stable release, ``None`` when undateable.

    Skips pre-releases, fully yanked releases and versions with no files at
    all, per the bounds in the module docstring. A version string PyPI carries
    that ``packaging`` cannot parse is skipped too: it cannot take part in a
    specifier comparison either way.

    A version with **live files and no upload timestamp** is kept with a
    ``None`` date rather than skipped. It is installable, so dropping it would
    silently hand ``judge`` an older release to test.
    """
    with urllib.request.urlopen(PYPI_JSON.format(name=name), timeout=60) as response:
        payload = json.load(response)

    out: dict[Version, date | None] = {}
    for raw, files in payload["releases"].items():
        live = [f for f in files if not f.get("yanked")]
        if not live:
            continue
        try:
            version = Version(raw)
        except InvalidVersion:
            continue
        if version.is_prerelease:
            continue
        stamps = [f["upload_time_iso_8601"] for f in live if f.get("upload_time_iso_8601")]
        out[version] = date.fromisoformat(min(stamps)[:10]) if stamps else None
    return out


def judge(item: Raise, releases: dict[Version, date | None], cutoff: date) -> Verdict:
    """Rule 9's answer for one raise, from the releases the raise newly excludes."""
    newly_excluded = [v for v in releases if item.old <= v < item.new]
    if not newly_excluded:
        return Verdict(
            package=item.package,
            old=item.old,
            new=item.new,
            excluded=None,
            released=None,
            breaking=False,
            note=(
                "no stable release sits between the old and new floor, so the raise excludes nothing "
                "a user could have resolved to"
            ),
        )
    newest = max(newly_excluded)
    released = releases[newest]
    if released is None:
        # Undecided, not compliant. The newest release the raise strands is the
        # one the answer depends on, so an undateable one is no answer at all.
        return Verdict(
            package=item.package,
            old=item.old,
            new=item.new,
            excluded=newest,
            released=None,
            breaking=False,
            undecided=True,
            note=f"cannot date {newest}, the newest release the raise newly excludes",
        )
    breaking = released > cutoff
    return Verdict(
        package=item.package,
        old=item.old,
        new=item.new,
        excluded=newest,
        released=released,
        breaking=breaking,
        # A word, not a sign. `(cutoff - released).days` is positive for a
        # release OLDER than the cutoff, so "+606 days relative to the cutoff"
        # read as 606 days past it while meaning 606 days before it -- and the
        # breaking case printed a negative number, which reads as the safe one.
        # The label beside it was the only thing keeping a reader right.
        note=(
            f"{newest} was uploaded {released}, "
            f"{abs((cutoff - released).days)} days "
            f"{'younger' if released > cutoff else 'older'} than the cutoff"
        ),
    )


def report(verdicts: list[Verdict], *, today: date, cutoff: date, base: str, context: list[str]) -> int:
    """Print the findings and return the exit code. Localizes per package."""
    print(f"Rule 9 support-window check: floors at {base} against the working tree.")
    # State the day the answer was computed on. A verdict pasted into a pull
    # request outlives its truth otherwise, which is how this check's own
    # specification came to name a stale expected answer.
    print(f"Computed on {today}; the {DEPENDENCY_WINDOW_MONTHS}-month cutoff is {cutoff}.")
    print()

    for line in context:
        print(f"note: {line}")
    if context:
        print()

    if not verdicts:
        print("No floor was raised. Rule 9 has nothing to say about this release.")
        return 0

    breaking = [v for v in verdicts if v.breaking]
    undecided = [v for v in verdicts if v.undecided]
    for verdict in verdicts:
        if verdict.breaking:
            label = "BREAKING"
        elif verdict.undecided:
            label = "UNDECIDED"
        else:
            label = "patch-eligible"
        print(f"{label}: {verdict.package} {verdict.old} -> {verdict.new}")
        print(f"    {verdict.note}")

    print()
    if breaking:
        print(
            f"{len(breaking)} raise(s) exclude a release younger than {DEPENDENCY_WINDOW_MONTHS} months. "
            "Each one's CHANGELOG entry owes a `**Breaking**` marker and a section in "
            "docs-src/reference/migration.md (Rule 11), and the release is a minor bump rather than a patch."
        )
    if undecided:
        print(f"{len(undecided)} raise(s) could not be dated. Investigate rather than assuming compliance.")
    if not breaking and not undecided:
        print("Every raise excludes only releases past their own support window, so the release stays patch-eligible.")
    return 1 if (breaking or undecided) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base",
        default=None,
        help="Revision to compare against (default: the most recent tag reachable from HEAD).",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Date to measure the window from, as YYYY-MM-DD (default: today). Mostly for tests.",
    )
    args = parser.parse_args(argv)

    # Reported rather than tracebacked, like every other failure path here: the
    # maintainer running this reads the exit code and the text, not a stack.
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"--today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
        return 1
    cutoff = dependency_cutoff(today)
    try:
        base = args.base or previous_tag()
    except subprocess.CalledProcessError:
        print(
            "Could not find a tag to compare against. Run `git fetch --tags`, or pass --base <revision>.",
            file=sys.stderr,
        )
        return 1

    context: list[str] = []
    try:
        head_floors = floors(REPO_ROOT / "pyproject.toml")
        with TemporaryDirectory() as tmp:
            base_floors = floors(read_pyproject_at(base, Path(tmp)))
    except (UnsupportedSpecifier, IrreconcilableExtras) as exc:
        print(f"Cannot read the declared floors: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print(f"Could not read pyproject.toml at {base!r}.", file=sys.stderr)
        return 1

    for package in sorted(set(head_floors) - set(base_floors)):
        context.append(f"{package} declares a floor for the first time since {base}; not a raise")
    for package in sorted(p for p in head_floors if p in base_floors and head_floors[p] < base_floors[p]):
        context.append(f"{package} floor went down ({base_floors[package]} -> {head_floors[package]}); not a raise")

    verdicts: list[Verdict] = []
    for item in raised(base_floors, head_floors):
        try:
            releases = fetch_releases(item.package)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            verdicts.append(
                Verdict(
                    package=item.package,
                    old=item.old,
                    new=item.new,
                    excluded=None,
                    released=None,
                    breaking=False,
                    undecided=True,
                    note=f"could not read release dates from PyPI: {exc}",
                )
            )
            continue
        verdicts.append(judge(item, releases, cutoff))

    return report(verdicts, today=today, cutoff=cutoff, base=base, context=context)


if __name__ == "__main__":
    raise SystemExit(main())
