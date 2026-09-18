"""Tests for scripts/python_support.py (BK-375).

The tests split by what each function answers: what the module reads out of the
classifiers, what it computes from a release date, and — a third thing, keyed to
neither — where `dependency_cutoff` puts Rule 9's line, which is about
dependencies rather than interpreters and shares only the calendar arithmetic.
Two things get pinned harder than the rest because they fail silently rather
than loudly:

* **the sort** — lexically, ``"3.9" > "3.10"``, so a lexical sort reverses the
  chart's rows the first time a single-digit minor is in the set. No current
  classifier exposes it, which is exactly why it needs a test with one that
  does;
* **the undated classifier** — a skipped row would shrink a published support
  claim in silence, so the refusal is pinned in both directions: it raises when
  a date is missing, and it does *not* raise for the committed file.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def python_support():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import python_support

    return python_support


def _pyproject(tmp_path: Path, *versions: str, extra_classifiers: tuple[str, ...] = ()) -> Path:
    """A minimal pyproject carrying only the classifiers under test."""
    classifiers = [f'  "Programming Language :: Python :: {v}",' for v in versions]
    classifiers += [f'  "{c}",' for c in extra_classifiers]
    body = "[project]\nname = 'x'\nclassifiers = [\n" + "\n".join(classifiers) + "\n]\n"
    path = tmp_path / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestSupportedVersions:
    """What the classifiers say, and what is deliberately not a version."""

    def test_reads_the_committed_classifiers(self, python_support):
        """The real file parses, and every version it names has a date.

        The other half of the undated-classifier pin below: without this, a
        table that had drifted behind the classifiers would only be caught by a
        gate nobody had run yet.
        """
        assert python_support.supported_versions() == ["3.10", "3.11", "3.12", "3.13", "3.14"]

    def test_sorts_numerically_not_lexically(self, python_support, tmp_path):
        """``3.9`` sorts before ``3.10``; a string sort puts it after ``3.14``."""
        python_support.PYTHON_RELEASES["3.9"] = date(2020, 10, 5)
        try:
            found = python_support.supported_versions(_pyproject(tmp_path, "3.11", "3.9", "3.10"))
        finally:
            del python_support.PYTHON_RELEASES["3.9"]
        assert found == ["3.9", "3.10", "3.11"]

    def test_language_line_classifiers_are_not_versions(self, python_support, tmp_path):
        """``:: 3`` and ``:: 3 :: Only`` name the language, not a dated version.

        ``:: 3 :: Only`` is in the committed file, so a regex without the
        trailing anchor would read ``3`` as a version and raise on every call.
        """
        path = _pyproject(
            tmp_path,
            "3.12",
            extra_classifiers=(
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3 :: Only",
                "Development Status :: 4 - Beta",
            ),
        )
        assert python_support.supported_versions(path) == ["3.12"]

    def test_undated_classifier_raises_and_names_it(self, python_support, tmp_path):
        """A classifier with no release date is a refusal, never a skip."""
        path = _pyproject(tmp_path, "3.12", "3.99")
        with pytest.raises(python_support.UnknownInterpreterError, match="3.99"):
            python_support.supported_versions(path)

    def test_every_undated_classifier_is_named(self, python_support, tmp_path):
        """Two missing rows both appear, so one fix per run is not the shape."""
        path = _pyproject(tmp_path, "3.98", "3.99")
        with pytest.raises(python_support.UnknownInterpreterError) as excinfo:
            python_support.supported_versions(path)
        assert "3.98" in str(excinfo.value)
        assert "3.99" in str(excinfo.value)


class TestWindowArithmetic:
    """Release date plus a window, and where today falls in it."""

    def test_support_end_is_five_years_after_release(self, python_support):
        """3.10's own PEP says "approximately October 2026"; this is the day."""
        assert python_support.support_end("3.10") == date(2026, 10, 4)
        assert python_support.SECURITY_SUPPORT_YEARS == 5

    def test_spec0_end_is_three_years_after_release(self, python_support):
        """The floor beneath the promise, drawn on the chart and never decided on."""
        assert python_support.spec0_end("3.10") == date(2024, 10, 4)
        assert python_support.SPEC0_WINDOW_YEARS == 3

    def test_unknown_version_raises_rather_than_guessing(self, python_support):
        with pytest.raises(python_support.UnknownInterpreterError, match="3.9"):
            python_support.support_end("3.9")

    def test_leap_day_release_clamps_to_28_february(self, python_support):
        """No current row is 29 February; the clamp is so a future one cannot raise."""
        python_support.PYTHON_RELEASES["3.99"] = date(2024, 2, 29)
        try:
            assert python_support.support_end("3.99") == date(2029, 2, 28)
        finally:
            del python_support.PYTHON_RELEASES["3.99"]

    def test_windows_are_oldest_first_and_carry_both_ends(self, python_support):
        rows = python_support.windows(date(2026, 9, 17))
        assert [r.version for r in rows] == ["3.10", "3.11", "3.12", "3.13", "3.14"]
        assert rows[0].released == date(2021, 10, 4)
        assert rows[0].spec0_ends == date(2024, 10, 4)
        assert rows[0].ends == date(2026, 10, 4)

    def test_days_remaining_is_signed_so_past_and_left_agree(self, python_support):
        """One field, not two that can disagree: negative means past."""
        rows = {r.version: r for r in python_support.windows(date(2026, 9, 17))}
        assert rows["3.10"].days_remaining == 17
        assert rows["3.10"].past is False

        later = {r.version: r for r in python_support.windows(date(2026, 10, 5))}
        assert later["3.10"].days_remaining == -1
        assert later["3.10"].past is True

    def test_the_window_closes_the_day_after_it_ends(self, python_support):
        """On the end date itself support has not lapsed; the next day it has."""
        on_the_day = {r.version: r for r in python_support.windows(date(2026, 10, 4))}
        assert on_the_day["3.10"].days_remaining == 0
        assert on_the_day["3.10"].past is False


class TestDependencyCutoff:
    """Rule 9's 2-year boundary, as the date it puts the line on."""

    def test_two_years_back(self, python_support):
        assert python_support.dependency_cutoff(date(2026, 9, 17)) == date(2024, 9, 17)
        assert python_support.DEPENDENCY_WINDOW_MONTHS == 24

    def test_a_release_older_than_the_cutoff_is_outside_its_window(self, python_support):
        """pyarrow 15.0.2 (2024-03-18) against today: outside, so patch-eligible.

        The measured case the release check is exercised on, pinned here so the
        boundary and the check cannot drift apart. **Not the boundary itself** —
        this date is 183 days before the cutoff, and the name used to claim
        otherwise, so a `<=` weakened to `<` would have left it green. The
        equal-to-the-cutoff case is `judge`'s to decide and is pinned where that
        decision lives, `test_check_support_windows.py`'s
        `test_a_release_exactly_on_the_cutoff_is_outside_its_window`.
        """
        assert date(2024, 3, 18) < python_support.dependency_cutoff(date(2026, 9, 17))

    def test_a_release_inside_the_window_is_after_the_cutoff(self, python_support):
        """pyarrow 20.0.0 (2025-04-27): inside, so excluding it is breaking."""
        assert date(2025, 4, 27) > python_support.dependency_cutoff(date(2026, 9, 17))

    def test_day_clamps_when_the_target_month_is_shorter(self, python_support):
        """29 February minus two years lands on a month with no 29th."""
        assert python_support.dependency_cutoff(date(2028, 2, 29)) == date(2026, 2, 28)

    def test_month_arithmetic_does_not_drift_across_january(self, python_support):
        """The month index is zero-based inside the helper; January is where that bites."""
        assert python_support.dependency_cutoff(date(2026, 1, 15)) == date(2024, 1, 15)
        assert python_support.dependency_cutoff(date(2026, 12, 31)) == date(2024, 12, 31)
