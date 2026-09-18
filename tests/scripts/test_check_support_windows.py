"""Tests for scripts/check_support_windows.py (BK-377).

The network half is stubbed at `fetch_releases`, because what needs pinning is
the judgement rather than the HTTP: which releases a raise newly excludes, which
of them is newest, and which side of the cutoff its upload date falls on.

**All three verdicts are exercised**, because `Verdict.undecided` is a third
outcome rather than a shade of the other two — `breaking=False` on its own reads
as compliant, which is the false pass it exists to prevent. A check whose
**Breaking** branch never runs is an obligation with no evidence behind it, and
that branch is the one carrying the migration obligation. The two dated cases use
real measured dates so the tests and the documented exercise cannot drift apart:

* `pyarrow` 14.0.0 -> 16 newly excludes 15.0.2, uploaded 2024-03-18, which is
  older than a 2026-09-17 cutoff of 2024-09-17. Patch-eligible.
* `pyarrow` 14.0.0 -> 21 newly excludes 20.0.0, uploaded 2025-04-27, which is
  younger. Breaking.
* A newest exclusion PyPI cannot date, and a fetch that fails outright.
  Undecided — reported and non-zero, never quietly compliant.

Note the floors are the **collapsed** ones: `declared_constraints` takes the
greatest lower bound across every user-facing extra, so `[arrow]`'s
`pyarrow>=12.0.0` beside `[s3-pyarrow]`'s `pyarrow>=14.0.0` is a 14.0.0 floor —
which is the version a user actually resolves against, and so the one Rule 9 is
about.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"

TODAY = date(2026, 9, 17)
CUTOFF = date(2024, 9, 17)

# Measured from pypi.org/pypi/pyarrow/json: earliest `upload_time_iso_8601`
# over each release's non-yanked files. Re-derived 2026-09-17 over every file
# of each release (29, 36, 36, 36, 55 and 43 respectively, none yanked in any):
# `21.0.0` read `2025-07-16` until then, two days off an earliest stamp of
# `2025-07-18T00:54:34.755518Z`. No assertion consumed that entry, which is how
# a wrong figure survived in the table this module treats as its measured
# record. The line above is a query to re-run, not a provenance note.
PYARROW = {
    Version("13.0.0"): date(2023, 8, 23),
    Version("14.0.0"): date(2023, 11, 1),
    Version("15.0.2"): date(2024, 3, 18),
    Version("16.0.0"): date(2024, 4, 20),
    Version("20.0.0"): date(2025, 4, 27),
    Version("21.0.0"): date(2025, 7, 18),
}


@pytest.fixture(scope="module")
def check_support_windows():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_support_windows

    return check_support_windows


def _raise(mod, package: str, old: str, new: str):
    return mod.Raise(package=package, old=Version(old), new=Version(new))


class TestJudge:
    """Rule 9's verdict for one raise."""

    def test_excluding_only_old_releases_is_patch_eligible(self, check_support_windows):
        """The raise BUG-287 proposes, as of today: 15.0.2 is 30 months old."""
        verdict = check_support_windows.judge(_raise(check_support_windows, "pyarrow", "14.0.0", "16"), PYARROW, CUTOFF)
        assert verdict.excluded == Version("15.0.2")
        assert verdict.released == date(2024, 3, 18)
        assert verdict.breaking is False

    def test_excluding_a_young_release_is_breaking(self, check_support_windows):
        """20.0.0 (2025-04-27) is inside its own two-year window."""
        verdict = check_support_windows.judge(_raise(check_support_windows, "pyarrow", "14.0.0", "21"), PYARROW, CUTOFF)
        assert verdict.excluded == Version("20.0.0")
        assert verdict.released == date(2025, 4, 27)
        assert verdict.breaking is True

    def test_the_newest_excluded_release_decides_not_the_oldest(self, check_support_windows):
        """14.0.0 -> 21 excludes 14.0.0, 15.0.2, 16.0.0 and 20.0.0.

        Judging on the oldest would call it patch-eligible on 14.0.0's 2023
        date. The rule asks about *every* version newly excluded, so the newest
        is the one that can fail the test.
        """
        verdict = check_support_windows.judge(_raise(check_support_windows, "pyarrow", "14.0.0", "21"), PYARROW, CUTOFF)
        assert verdict.excluded == Version("20.0.0")

    def test_the_new_floor_itself_is_not_excluded(self, check_support_windows):
        """The range is half-open: raising to 16 does not exclude 16.0.0."""
        verdict = check_support_windows.judge(
            _raise(check_support_windows, "pyarrow", "14.0.0", "16.0.0"), PYARROW, CUTOFF
        )
        assert verdict.excluded == Version("15.0.2")

    def test_a_release_exactly_on_the_cutoff_is_outside_its_window(self, check_support_windows):
        """The boundary is inclusive on the compliant side, so it is pinned."""
        releases = {Version("1.0"): CUTOFF, Version("2.0"): date(2026, 1, 1)}
        verdict = check_support_windows.judge(_raise(check_support_windows, "p", "1.0", "2.0"), releases, CUTOFF)
        assert verdict.released == CUTOFF
        assert verdict.breaking is False

    def test_a_release_one_day_inside_the_cutoff_is_breaking(self, check_support_windows):
        """The other side of the same boundary; without this the test above
        would pass against a `>=` that should be `>`."""
        one_day_later = date(2024, 9, 18)
        releases = {Version("1.0"): one_day_later, Version("2.0"): date(2026, 1, 1)}
        verdict = check_support_windows.judge(_raise(check_support_windows, "p", "1.0", "2.0"), releases, CUTOFF)
        assert verdict.breaking is True

    def test_the_old_floor_itself_is_newly_excluded(self, check_support_windows):
        """Raising off a floor strands whoever was resolving to exactly that floor.

        `judge`'s range is `old <= v < new`, so the old floor is in it. That is
        the right answer, not an off-by-one: a user pinned at `16.0.0` cannot
        satisfy `>=20.0.0`. Here it is patch-eligible only because `16.0.0`'s
        own upload date predates the cutoff, which is what makes this case
        worth pinning separately from the genuinely-excludes-nothing one below.
        """
        verdict = check_support_windows.judge(
            _raise(check_support_windows, "pyarrow", "16.0.0", "20.0.0"),
            {Version("16.0.0"): date(2024, 4, 20), Version("20.0.0"): date(2025, 4, 27)},
            CUTOFF,
        )
        assert verdict.excluded == Version("16.0.0")
        assert verdict.released == date(2024, 4, 20)
        assert verdict.breaking is False

    def test_the_note_says_which_side_of_the_cutoff_the_release_falls_on(self, check_support_windows):
        """The figure beside the verdict, in both directions.

        It printed `(cutoff - released).days` with a sign and called it "days
        relative to the cutoff", so a breaking release read as a negative
        number and a patch-eligible one as a positive -- each the opposite of
        how the sentence scans. Nothing asserted the note, which is why it
        shipped that way for a round. A word cannot be read backwards, so the
        word is what is pinned. Both counts derived against `CUTOFF`
        (2024-09-17): 2025-04-27 is 222 days after it, 2023-08-23 is 391
        before.
        """
        breaking = check_support_windows.judge(
            _raise(check_support_windows, "pyarrow", "16.0.0", "21.0.0"),
            {Version("16.0.0"): date(2024, 4, 20), Version("20.0.0"): date(2025, 4, 27)},
            CUTOFF,
        )
        assert breaking.breaking is True
        assert "222 days younger than the cutoff" in breaking.note

        eligible = check_support_windows.judge(
            _raise(check_support_windows, "pyarrow", "13.0.0", "14.0.0"),
            {Version("13.0.0"): date(2023, 8, 23)},
            CUTOFF,
        )
        assert eligible.breaking is False
        assert "391 days older than the cutoff" in eligible.note

    def test_an_undateable_newest_exclusion_is_undecided_rather_than_compliant(self, check_support_windows):
        """The `judge` half of the dateless case, which `fetch_releases`'s test cannot reach.

        The dates decide, and the newest release the raise strands is the one
        they are read from. With that release undateable the answer is absent,
        so reporting `breaking=False` would spend the check's credibility on a
        release it never examined. The older release present here is the trap:
        it is old enough to read as patch-eligible.
        """
        verdict = check_support_windows.judge(
            check_support_windows.Raise("p", Version("1.0"), Version("3.0")),
            {Version("1.0"): date(2020, 1, 1), Version("2.0"): None},
            date(2024, 9, 17),
        )
        assert verdict.undecided is True
        assert verdict.breaking is False
        assert verdict.excluded == Version("2.0")
        assert "cannot date 2.0" in verdict.note

    def test_the_old_floor_being_young_makes_the_raise_breaking(self, check_support_windows):
        """The other direction of the same case, so the date is what decides it
        rather than the old floor being special."""
        verdict = check_support_windows.judge(
            _raise(check_support_windows, "pyarrow", "20.0.0", "21.0.0"),
            PYARROW,
            CUTOFF,
        )
        assert verdict.excluded == Version("20.0.0")
        assert verdict.breaking is True

    def test_no_release_at_all_in_range_is_reported_not_judged(self, check_support_windows):
        verdict = check_support_windows.judge(
            _raise(check_support_windows, "p", "5.0", "6.0"), {Version("6.0"): date(2026, 1, 1)}, CUTOFF
        )
        assert verdict.excluded is None
        assert verdict.breaking is False
        assert "excludes nothing" in verdict.note


class TestRaised:
    """Which floor movements are raises at all."""

    def test_only_upward_movement_counts(self, check_support_windows):
        base = {"a": Version("1.0"), "b": Version("2.0"), "c": Version("3.0")}
        head = {"a": Version("1.1"), "b": Version("1.0"), "c": Version("3.0")}
        assert [r.package for r in check_support_windows.raised(base, head)] == ["a"]

    def test_a_new_package_is_not_a_raise(self, check_support_windows):
        """It excludes nothing a previous release admitted."""
        assert check_support_windows.raised({}, {"new": Version("1.0")}) == []

    def test_raises_are_sorted_so_the_report_is_stable(self, check_support_windows):
        base = {"z": Version("1.0"), "a": Version("1.0")}
        head = {"z": Version("2.0"), "a": Version("2.0")}
        assert [r.package for r in check_support_windows.raised(base, head)] == ["a", "z"]


class TestFloors:
    """Reading the declared floors, through the collapse it borrows."""

    def test_committed_pyproject_collapses_pyarrow_to_the_strictest_floor(self, check_support_windows):
        """`[arrow]` says >=12.0.0 and `[s3-pyarrow]` says >=14.0.0.

        14.0.0 is what a user resolving both gets, so it is the floor Rule 9 is
        about. Judging on 12.0.0 would ask about releases nobody could install.
        """
        found = check_support_windows.floors(ROOT / "pyproject.toml")
        assert found["pyarrow"] == Version("14.0.0")

    def test_a_package_with_no_lower_bound_is_absent_rather_than_zero(self, check_support_windows, tmp_path):
        """An unbounded declaration has no floor to raise, so it has no row."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\nname='x'\n[project.optional-dependencies]\nthing = [\"boto3\"]\n",
            encoding="utf-8",
        )
        assert check_support_windows.floors(pyproject) == {}


class TestFetchReleases:
    """The PyPI payload's shape, over a stubbed response.

    **Three of the four skips are measured properties of the real API**, not
    defensive guesses: `pyarrow 0.1.0` has an empty file list, `urllib3 2.0.0`
    is fully yanked, and the drift guard resolves with `--pre` so pre-releases
    are real. An unparseable version string is the fourth and has no live
    example either way.

    The dateless case below is the one deliberate exception — surveyed at zero
    occurrences and kept anyway, because what it prevents is a false pass
    rather than a crash. Its own docstring says so; this class claim used to
    say every skip was measured, which that test contradicted two screens
    down.
    """

    def _payload(self, releases: dict) -> dict:
        return {"releases": releases}

    def _stub(self, monkeypatch, check_support_windows, payload):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                import json

                return json.dumps(payload).encode()

        monkeypatch.setattr(check_support_windows.urllib.request, "urlopen", lambda *a, **k: Response())

    def test_takes_the_earliest_upload_across_a_releases_files(self, monkeypatch, check_support_windows):
        """A release has no single date; pyarrow 15.0.2 alone carries 36 files."""
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "1.0": [
                        {"upload_time_iso_8601": "2024-03-18T20:00:00Z"},
                        {"upload_time_iso_8601": "2024-03-18T16:53:30Z"},
                    ]
                }
            ),
        )
        assert check_support_windows.fetch_releases("p") == {Version("1.0"): date(2024, 3, 18)}

    def test_a_fully_yanked_release_is_skipped(self, monkeypatch, check_support_windows):
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "1.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z", "yanked": True, "yanked_reason": "bad"}],
                    "1.1": [{"upload_time_iso_8601": "2024-02-01T00:00:00Z", "yanked": False}],
                }
            ),
        )
        assert set(check_support_windows.fetch_releases("p")) == {Version("1.1")}

    def test_a_partially_yanked_release_counts_and_is_dated_from_its_live_files(
        self, monkeypatch, check_support_windows
    ):
        """Yanked is per file; the rule applied is all-files-yanked, stated here."""
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "1.0": [
                        {"upload_time_iso_8601": "2024-01-01T00:00:00Z", "yanked": True},
                        {"upload_time_iso_8601": "2024-01-05T00:00:00Z", "yanked": False},
                    ]
                }
            ),
        )
        assert check_support_windows.fetch_releases("p") == {Version("1.0"): date(2024, 1, 5)}

    def test_a_version_with_no_files_is_skipped(self, monkeypatch, check_support_windows):
        """pyarrow 0.1.0 is the live example: registered, no distribution, no date."""
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload({"0.1.0": [], "1.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}]}),
        )
        assert set(check_support_windows.fetch_releases("p")) == {Version("1.0")}

    def test_prereleases_are_excluded_from_the_claim_space(self, monkeypatch, check_support_windows):
        """Otherwise a `14.0.0rc1` days before `14.0.0` makes every raise breaking."""
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "14.0.0rc1": [{"upload_time_iso_8601": "2026-01-01T00:00:00Z"}],
                    "13.0.0": [{"upload_time_iso_8601": "2023-08-23T00:00:00Z"}],
                }
            ),
        )
        assert set(check_support_windows.fetch_releases("p")) == {Version("13.0.0")}

    def test_a_release_with_files_but_no_timestamp_is_dateless_rather_than_absent(
        self, monkeypatch, check_support_windows
    ):
        """The one skip that is defensive, so it must not read as a pass.

        The other skips are justified by nobody being stranded: a version with
        no files, or with every file yanked, is one no resolver could have
        installed. A version with *live* files and no `upload_time_iso_8601`
        is installable, so dropping it from the claim space hands `judge` the
        next-oldest release and a raise over a recent version reads
        **patch-eligible**. Surveyed over the whole claim space — all 19
        packages `floors()` returns for the committed `pyproject.toml`, 2617
        registered versions between them — PyPI produced this shape zero times.
        Defensive, and loud rather than silent, because a silent verification
        step is worse than none.
        """
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "1.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
                    "2.0": [{"filename": "p-2.0.tar.gz"}],
                }
            ),
        )
        assert check_support_windows.fetch_releases("p") == {
            Version("1.0"): date(2024, 1, 1),
            Version("2.0"): None,
        }

    def test_an_unparseable_version_is_skipped(self, monkeypatch, check_support_windows):
        """It could not take part in a specifier comparison either way."""
        self._stub(
            monkeypatch,
            check_support_windows,
            self._payload(
                {
                    "not-a-version": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
                    "1.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
                }
            ),
        )
        assert set(check_support_windows.fetch_releases("p")) == {Version("1.0")}


class TestReport:
    """The output and the exit code, since both are what a release reads."""

    def _verdict(self, mod, **kw):
        defaults = {
            "package": "pyarrow",
            "old": Version("14.0.0"),
            "new": Version("16"),
            "excluded": Version("15.0.2"),
            "released": date(2024, 3, 18),
            "breaking": False,
            "undecided": False,
            "note": "note",
        }
        return mod.Verdict(**{**defaults, **kw})

    def test_no_raise_exits_zero_and_says_so(self, check_support_windows, capsys):
        assert check_support_windows.report([], today=TODAY, cutoff=CUTOFF, base="v0.32.0", context=[]) == 0
        assert "No floor was raised" in capsys.readouterr().out

    def test_patch_eligible_exits_zero(self, check_support_windows, capsys):
        code = check_support_windows.report(
            [self._verdict(check_support_windows)], today=TODAY, cutoff=CUTOFF, base="v0.32.0", context=[]
        )
        assert code == 0
        assert "patch-eligible: pyarrow" in capsys.readouterr().out

    def test_breaking_exits_one_and_names_the_obligation(self, check_support_windows, capsys):
        code = check_support_windows.report(
            [self._verdict(check_support_windows, breaking=True, excluded=Version("20.0.0"))],
            today=TODAY,
            cutoff=CUTOFF,
            base="v0.32.0",
            context=[],
        )
        assert code == 1
        out = capsys.readouterr().out
        assert "BREAKING: pyarrow" in out
        assert "`**Breaking**`" in out
        assert "migration.md" in out

    def test_an_undateable_raise_fails_rather_than_passing_quietly(self, check_support_windows, capsys):
        """A raise nobody could date is not a compliant raise.

        `undecided` is an explicit field rather than something inferred from an
        absent date, because "nothing to exclude" is also dateless and is a
        pass. The two cases are pinned side by side below.
        """
        code = check_support_windows.report(
            [
                self._verdict(
                    check_support_windows,
                    excluded=None,
                    released=None,
                    undecided=True,
                    note="could not read release dates from PyPI",
                )
            ],
            today=TODAY,
            cutoff=CUTOFF,
            base="v0.32.0",
            context=[],
        )
        assert code == 1
        assert "UNDECIDED" in capsys.readouterr().out

    def test_a_raise_excluding_nothing_is_dateless_and_still_passes(self, check_support_windows, capsys):
        """The case an inferred `undecided` could not tell from the one above."""
        code = check_support_windows.report(
            [
                self._verdict(
                    check_support_windows,
                    excluded=None,
                    released=None,
                    note="no stable release sits between the old and new floor",
                )
            ],
            today=TODAY,
            cutoff=CUTOFF,
            base="v0.32.0",
            context=[],
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "patch-eligible: pyarrow" in out
        assert "UNDECIDED" not in out

    def test_the_report_states_the_day_it_was_computed_on(self, check_support_windows, capsys):
        """A verdict pasted into a pull request otherwise outlives its truth.

        This check's own specification arrived carrying an expected answer that
        had been correct six months earlier, which is the failure the line
        prevents.
        """
        check_support_windows.report([], today=TODAY, cutoff=CUTOFF, base="v0.32.0", context=[])
        out = capsys.readouterr().out
        assert "2026-09-17" in out
        assert "2024-09-17" in out

    def test_context_lines_are_reported_without_affecting_the_verdict(self, check_support_windows, capsys):
        code = check_support_windows.report(
            [], today=TODAY, cutoff=CUTOFF, base="v0.32.0", context=["boto3 floor went down; not a raise"]
        )
        assert code == 0
        assert "note: boto3 floor went down" in capsys.readouterr().out


class TestMainWiring:
    """`main` end to end, over a stubbed `fetch_releases`.

    Everything above tests a function; this tests that they are joined up. The
    branch that matters is the network failure, because it is the **only**
    producer of an `undecided` verdict in practice and the whole reason this
    check is not gated. A regression turning a PyPI timeout into
    `breaking=False, undecided=False` would report **patch-eligible** for a
    raise nobody dated — the exact false pass the field exists to prevent, and
    one a maintainer reading the exit code could not see.
    """

    def test_a_failed_fetch_is_undecided_and_exits_non_zero(self, check_support_windows, monkeypatch, capsys):
        import urllib.error

        def explode(name: str):
            raise urllib.error.URLError("timed out")

        monkeypatch.setattr(check_support_windows, "fetch_releases", explode)
        monkeypatch.setattr(
            check_support_windows,
            "raised",
            lambda base, head: [_raise(check_support_windows, "pyarrow", "14.0.0", "21")],
        )
        monkeypatch.setattr(check_support_windows, "floors", lambda path: {})
        monkeypatch.setattr(check_support_windows, "read_pyproject_at", lambda rev, workdir: workdir / "pyproject.toml")

        code = check_support_windows.main(["--base", "v0.32.0", "--today", "2026-09-17"])
        out = capsys.readouterr().out
        assert code == 1, "an undated raise must not report as compliant"
        assert "UNDECIDED: pyarrow" in out
        assert "could not read release dates from PyPI" in out
        assert "timed out" in out, "DRIFT-RULES Rule 2: say what failed, not that something did"

    def test_a_dated_fetch_reaches_the_verdict_through_main(self, check_support_windows, monkeypatch, capsys):
        """The control, so the clause above is not "main always exits 1"."""
        monkeypatch.setattr(check_support_windows, "fetch_releases", lambda name: PYARROW)
        monkeypatch.setattr(
            check_support_windows,
            "raised",
            lambda base, head: [_raise(check_support_windows, "pyarrow", "14.0.0", "16")],
        )
        monkeypatch.setattr(check_support_windows, "floors", lambda path: {})
        monkeypatch.setattr(check_support_windows, "read_pyproject_at", lambda rev, workdir: workdir / "pyproject.toml")

        code = check_support_windows.main(["--base", "v0.32.0", "--today", "2026-09-17"])
        assert code == 0
        assert "patch-eligible: pyarrow" in capsys.readouterr().out

    def test_a_bad_today_is_reported_rather_than_tracebacked(self, check_support_windows, capsys):
        """The flag this change introduced, held to the file's own standard.

        Every other failure path here prints and returns 1; this one raised
        `ValueError: Invalid isoformat string: 'next Monday'` out of `main`,
        which names no remedy and no flag.
        """
        assert check_support_windows.main(["--base", "v0.32.0", "--today", "next Monday"]) == 1
        assert "--today must be YYYY-MM-DD" in capsys.readouterr().err

    def test_no_tag_to_compare_against_is_reported_rather_than_tracebacked(
        self, check_support_windows, monkeypatch, capsys
    ):
        """`previous_tag` shells out to `git describe`, which fails in a shallow
        clone — the state a fresh CI checkout is in until `git fetch --tags`."""
        import subprocess

        def no_tag() -> str:
            raise subprocess.CalledProcessError(128, ["git", "describe"])

        monkeypatch.setattr(check_support_windows, "previous_tag", no_tag)
        assert check_support_windows.main(["--today", "2026-09-17"]) == 1
        assert "git fetch --tags" in capsys.readouterr().err, "say the remedy, not just the failure"
