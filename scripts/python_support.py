"""BK-375: the one home for which interpreters we support and until when.

Three mechanisms need the same two answers and must not each hold their own copy
of them: the chart on the dependency-policy page (``gen_python_support.py``), the
weekly calendar report (``drift_report.py``), and the release-time floor check
(``check_support_windows.py``, for the dependency half of the window). The
answers are:

* **which** interpreters we claim to support — derived from the
  ``Programming Language :: Python`` classifiers in ``pyproject.toml``;
* **until when** — each version's initial release date plus the window.

Authority, per ``sdd/DRIFT-RULES.md`` Rule 4: the **classifiers govern** the
supported set. They are what PyPI shows a user, so they are the canonical
statement of a published support claim. ``requires-python`` is a floor with no
ceiling and cannot name the top of the set; ``ci.yml``'s ``ALL_PYTHONS`` is a CI
matrix rather than a published promise. Neither is co-equal, and nothing here
reads them. The declaration lives beside the classifiers themselves in
``pyproject.toml``; this module is its implementation, not its home.

The release dates are the one **hand-kept** input, and the trade is deliberate:
a past release date is immutable, so the table only grows, and it grows exactly
when a classifier is added — already a deliberate act. Nothing here reaches the
network, which is what lets the generator above it run in ``preflight``.

This module carries no drift-gate declaration block, and that is a decision
rather than an oversight: it is a library, not a wired mechanism, and its stem
does not match ``gen_gate_inventory``'s ``^(check|gen|drift|report)_`` backstop.
The three mechanisms that read it carry the declarations.

Bounds:

* The claim space is **minor versions**, because that is what a classifier
  names. Nothing here says anything about patch releases, and nothing here
  reads ``requires-python``.
* A classifier with no row in ``PYTHON_RELEASES`` raises
  ``UnknownInterpreterError`` rather than being skipped. That is the failure the
  enumeration exists to catch: a skipped classifier would silently shrink a
  published claim, and a new interpreter's classifier is added at about the time
  its release date becomes knowable.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the oldest supported interpreter only
    import tomli as tomllib  # type: ignore[no-redef]

__all__ = [
    "DEPENDENCY_WINDOW_MONTHS",
    "PYTHON_RELEASES",
    "SECURITY_SUPPORT_YEARS",
    "SPEC0_WINDOW_YEARS",
    "SupportWindow",
    "UnknownInterpreterError",
    "dependency_cutoff",
    "spec0_end",
    "support_end",
    "supported_versions",
    "windows",
]

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Each version's `x.y.0 final` date, taken from that version's own
# release-schedule PEP — the PEP is the authoritative schedule, and a downloads
# page reflects it rather than the other way round. Derivation, per version:
# fetch `raw.githubusercontent.com/python/peps/main/peps/pep-0<n>.rst` and read
# the `- x.y.0 final: <Weekday>, <date>` line.
#
#   3.10 -> PEP 619  "- 3.10.0 final: Monday, 2021-10-04"
#   3.11 -> PEP 664  "- 3.11.0 final: Monday, 2022-10-24"
#   3.12 -> PEP 693  "- 3.12.0 final: Monday, 2023-10-02"
#   3.13 -> PEP 719  "- 3.13.0 final: Monday, 2024-10-07"
#   3.14 -> PEP 745  "- 3.14.0 final: Tuesday, 2025-10-07"
#
# Add a row in the same change that adds a classifier; `supported_versions()`
# raises on a classifier this table does not cover.
PYTHON_RELEASES: dict[str, date] = {
    "3.10": date(2021, 10, 4),
    "3.11": date(2022, 10, 24),
    "3.12": date(2023, 10, 2),
    "3.13": date(2024, 10, 7),
    "3.14": date(2025, 10, 7),
}

# What we promise: support for as long as CPython ships security fixes for that
# version. Every release-schedule PEP above states the same lifetime — "security
# updates (source only) will be released until 5 years after the release of
# x.y.0 final", with PEP 745 (3.14) spelling the number "five" — and gives the
# end only as a month ("approximately October 2026" for 3.10), so the exact day
# is this arithmetic rather than a second hand-kept column.
SECURITY_SUPPORT_YEARS = 5

# The ecosystem floor beneath that promise: SPEC 0's time-based support window,
# which the dependency policy adopts as the minimum anyone can rely on. Drawn on
# the chart so a reader can see the two windows at once. Nothing decides on it.
SPEC0_WINDOW_YEARS = 3

# SPEC 0's window for a *dependency* version, which the interpreter change above
# does not touch: Rule 9 of the dependency policy is about the packages behind
# the extras, not about interpreters.
DEPENDENCY_WINDOW_MONTHS = 24

# `Programming Language :: Python :: 3.12`, and deliberately not
# `:: 3` or `:: 3 :: Only` — those name the language line, not a version we
# date. The trailing anchor is what excludes `:: 3 :: Only`.
_CLASSIFIER_RE = re.compile(r"^Programming Language :: Python :: (?P<version>\d+\.\d+)$")


class UnknownInterpreterError(Exception):
    """A classifier names a version ``PYTHON_RELEASES`` has no date for."""


@dataclass(frozen=True)
class SupportWindow:
    """One interpreter's dates, and where today falls in them.

    ``days_remaining`` is negative once the window has closed, so a caller
    reporting "past" and one reporting "left" read the same field rather than
    two that can disagree.
    """

    version: str
    released: date
    spec0_ends: date
    ends: date
    days_remaining: int

    @property
    def past(self) -> bool:
        """Whether security support has ended as of the day this was built."""
        return self.days_remaining < 0


def _add_years(start: date, years: int) -> date:
    """``start`` plus whole ``years``, clamping 29 February onto 28 February.

    Only the leap-day case needs the clamp, and none of the five dates in
    ``PYTHON_RELEASES`` is 29 February — the clamp is here so a future row
    cannot make this raise ``ValueError`` on a date nobody thought about.
    """
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, month=2, day=28)


def supported_versions(pyproject: Path = PYPROJECT) -> list[str]:
    """The supported minor versions, oldest first, from the classifiers.

    Args:
        pyproject: Path to the ``pyproject.toml`` to read the classifiers from.

    Returns:
        Version strings such as ``["3.10", "3.11"]``, sorted **numerically** —
        a lexical sort puts ``3.9`` after ``3.10`` and would reverse the chart's
        rows the first time a single-digit minor appeared.

    Raises:
        UnknownInterpreterError: If a classifier names a version
            ``PYTHON_RELEASES`` has no date for.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    found: list[str] = []
    for classifier in data["project"]["classifiers"]:
        match = _CLASSIFIER_RE.match(classifier)
        if match:
            found.append(match.group("version"))

    undated = sorted(v for v in found if v not in PYTHON_RELEASES)
    if undated:
        raise UnknownInterpreterError(
            f"{pyproject} declares {', '.join(undated)} but PYTHON_RELEASES has no release date for "
            f"{'them' if len(undated) > 1 else 'it'}. Add the row from that version's release-schedule "
            f"PEP (see the comment on PYTHON_RELEASES in scripts/python_support.py)."
        )
    return sorted(found, key=_version_key)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def support_end(version: str) -> date:
    """When CPython's security support for ``version`` ends.

    Raises:
        UnknownInterpreterError: If ``version`` has no release date.
    """
    return _add_years(_released(version), SECURITY_SUPPORT_YEARS)


def spec0_end(version: str) -> date:
    """When SPEC 0's window for ``version`` closes — the floor, not the promise.

    Raises:
        UnknownInterpreterError: If ``version`` has no release date.
    """
    return _add_years(_released(version), SPEC0_WINDOW_YEARS)


def _released(version: str) -> date:
    try:
        return PYTHON_RELEASES[version]
    except KeyError:
        raise UnknownInterpreterError(
            f"no release date for Python {version}; add the row from its release-schedule PEP "
            f"(see the comment on PYTHON_RELEASES in scripts/python_support.py)"
        ) from None


def windows(today: date, pyproject: Path = PYPROJECT) -> list[SupportWindow]:
    """One ``SupportWindow`` per supported version, oldest first.

    Args:
        today: The day to measure against. Required rather than defaulting to
            ``date.today()`` so every caller's output is reproducible and every
            test can pick its own day without patching the clock.
        pyproject: Path to the ``pyproject.toml`` holding the classifiers.

    Raises:
        UnknownInterpreterError: If a classifier has no release date.
    """
    return [
        SupportWindow(
            version=version,
            released=PYTHON_RELEASES[version],
            spec0_ends=spec0_end(version),
            ends=support_end(version),
            days_remaining=(support_end(version) - today).days,
        )
        for version in supported_versions(pyproject)
    ]


def dependency_cutoff(today: date) -> date:
    """The oldest upload date a floor raise may newly exclude without breaking.

    Rule 9's 2-year window, expressed as the date it puts the boundary on: a
    release uploaded on or before this date is outside its support window, so
    excluding it is patch-eligible.
    """
    months = today.month - 1 - DEPENDENCY_WINDOW_MONTHS
    year = today.year + months // 12
    month = months % 12 + 1
    day = min(today.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days
