"""Tests for scripts/gen_conda_feedstock.py.

The generator performs exactly one transformation, so that is what these pin:
the header above ``context:`` is replaced, and every byte below it survives. The
second half is the one worth a test that cannot pass by accident -- a
"copies the body" assertion that compares a re-rendered body to itself would
hold for a generator that reformatted everything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import gen_conda_feedstock

    return gen_conda_feedstock


SOURCE = """\
# internal header, replaced on the way out
# tracked as BK-999, which must not ship
#
# more internal notes

context:
  version: "1.2.3"

build:
  number: 0

about:
  summary: "x"
"""


class TestRender:
    def test_the_internal_header_is_gone(self, gen):
        out = gen.render(SOURCE)
        assert "internal header" not in out
        assert "BK-999" not in out

    def test_the_shipped_header_is_first(self, gen):
        assert gen.render(SOURCE).startswith(gen.SHIPPED_HEADER)

    def test_the_body_survives_byte_for_byte(self, gen):
        """Compared against the SOURCE's own bytes, not a re-render.

        Re-rendering both sides would pass for a generator that reformatted
        the body, which is the failure this assertion exists to exclude.
        """
        body = SOURCE[SOURCE.index("context:") :]
        assert gen.render(SOURCE) == gen.SHIPPED_HEADER + body

    def test_a_body_coordinate_is_carried_not_stripped(self, gen):
        """The generator does not clean anything -- the gate does.

        ``check_no_tracker_refs`` holds the source body free of coordinates, so
        a second stripper here would be a second description of the same rule
        (DRIFT-RULES Rule 1) and would hide a gate failure rather than surface
        it.
        """
        source = SOURCE.replace('  version: "1.2.3"', '  version: "1.2.3"\n  # BUG-998')
        assert "BUG-998" in gen.render(source)

    def test_a_source_without_the_marker_is_refused(self, gen):
        """Reported, never guessed at.

        With the marker gone there is no boundary: copying the file whole ships
        this repo's internal header to conda-forge and copying nothing ships an
        empty recipe. Neither should have to be inferred from a surprising diff.
        """
        with pytest.raises(gen.MissingMarkerError):
            gen.render("package:\n  name: x\n")

    def test_an_indented_context_is_not_the_marker(self, gen):
        """``context:`` is a top-level key; the same word indented is a value."""
        with pytest.raises(gen.MissingMarkerError):
            gen.render("about:\n  context: something\n")

    def test_the_header_carries_no_date_or_commit(self, gen):
        """The output has to be byte-stable across commits.

        Anything varying per commit makes ``--check`` fail on every one of
        them, which retires the gate by making it noise. Asserted against the
        header's **content**: an earlier version of this test compared
        ``render(SOURCE)`` to itself, which is true of any pure function and so
        could not fail.
        """
        import re

        assert not re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", gen.SHIPPED_HEADER), "an ISO date"
        assert not re.search(r"\b[0-9a-f]{7,40}\b", gen.SHIPPED_HEADER), "a commit sha"


class TestCheck:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "gen_conda_feedstock.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_the_committed_copy_is_current(self):
        """Integration guard: the shipped file matches a fresh render."""
        result = self._run("--check")
        assert result.returncode == 0, result.stderr

    def test_a_stale_copy_fails_and_shows_the_difference(self, gen, tmp_path):
        source = tmp_path / "recipe.yaml"
        source.write_text(SOURCE, encoding="utf-8")
        out = tmp_path / "feedstock" / "recipe.yaml"
        out.parent.mkdir()
        out.write_text(gen.render(SOURCE).replace('version: "1.2.3"', 'version: "9.9.9"'), encoding="utf-8")
        result = self._run("--check", "--source", str(source), "--out", str(out))
        assert result.returncode == 1
        assert "9.9.9" in result.stderr
        assert "hatch run gen-conda-feedstock" in result.stderr

    def test_an_absent_copy_fails(self, tmp_path):
        source = tmp_path / "recipe.yaml"
        source.write_text(SOURCE, encoding="utf-8")
        result = self._run("--check", "--source", str(source), "--out", str(tmp_path / "nope.yaml"))
        assert result.returncode == 1

    def test_check_writes_nothing(self, tmp_path):
        source = tmp_path / "recipe.yaml"
        source.write_text(SOURCE, encoding="utf-8")
        out = tmp_path / "feedstock" / "recipe.yaml"
        self._run("--check", "--source", str(source), "--out", str(out))
        assert not out.exists()

    def test_writing_then_checking_is_clean(self, tmp_path):
        source = tmp_path / "recipe.yaml"
        source.write_text(SOURCE, encoding="utf-8")
        out = tmp_path / "feedstock" / "recipe.yaml"
        assert self._run("--source", str(source), "--out", str(out)).returncode == 0
        assert self._run("--check", "--source", str(source), "--out", str(out)).returncode == 0


class TestExitCodes:
    """Every non-zero path, because the docstring enumerates them.

    The Exit codes block said ``1`` meant "under ``--check``, the copy is
    stale or absent", which was false of three of the four ways this script
    exits 1: an unreadable source, a marker-less source and a failed write
    are none of them ``--check`` and none of them a stale copy.
    """

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "gen_conda_feedstock.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_an_unreadable_source_exits_one_without_check(self, tmp_path):
        result = self._run("--source", str(tmp_path / "absent.yaml"), "--out", str(tmp_path / "out.yaml"))
        assert result.returncode == 1
        assert "cannot read" in result.stderr

    def test_a_marker_less_source_exits_one_without_check(self, tmp_path):
        source = tmp_path / "recipe.yaml"
        source.write_text("package:\n  name: x\n", encoding="utf-8")
        result = self._run("--source", str(source), "--out", str(tmp_path / "out.yaml"))
        assert result.returncode == 1
        assert "context:" in result.stderr

    def test_an_unwritable_destination_is_reported_not_tracebacked(self, tmp_path):
        """A gate that dies with a traceback says less than the sentence it could write.

        ``drift_feedstock.main`` already takes this posture for the same
        failure; this script reached ``write_text`` unguarded.
        """
        source = tmp_path / "recipe.yaml"
        source.write_text(SOURCE, encoding="utf-8")
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory\n", encoding="utf-8")
        result = self._run("--source", str(source), "--out", str(blocker / "recipe.yaml"))
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert "cannot write" in result.stderr


class TestCommittedCopy:
    def test_it_agrees_with_the_source_below_context(self, gen):
        """The two committed files, compared directly rather than through the script."""
        source = gen.SOURCE.read_text(encoding="utf-8")
        shipped = gen.GENERATED.read_text(encoding="utf-8")
        marker = "\ncontext:"
        assert source[source.index(marker) :] == shipped[shipped.index(marker) :]

    def test_it_carries_no_internal_coordinate(self):
        """What the whole inversion is for: the shipped bytes are publishable.

        Asserted with ``_scan_lines`` -- the gate's whole scanner -- rather than
        ``_TRACKER_RE`` alone. The pattern is one of three the gate applies, and
        an earlier version of this test used it by itself: ``PR #1023`` and
        ``spec 003`` were measured invisible to that assertion and visible to
        the gate, in the one part of this file the gate never sees.

        That part is the point. ``check_no_tracker_refs`` scans the **source**
        recipe below ``context:``; everything below ``context:`` here is those
        same bytes, but ``SHIPPED_HEADER`` is written in this module and reaches
        conda-forge without passing the gate at all. This is what covers it.
        """
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import check_no_tracker_refs as tracker
        import gen_conda_feedstock as gen

        text = gen.GENERATED.read_text(encoding="utf-8")
        found = tracker._scan_lines(text.splitlines(), path=gen.GENERATED)
        assert [v.match for v in found] == []

    def test_the_shipped_header_is_held_to_the_gate_it_never_passes(self, gen):
        """The header specifically, not merely the file that mostly repeats the source."""
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import check_no_tracker_refs as tracker

        found = tracker._scan_lines(gen.SHIPPED_HEADER.splitlines(), path=gen.GENERATED)
        assert [v.match for v in found] == []

    @pytest.mark.parametrize("leak", ["see PR #1023", "tracked as BK-370", "spec 003 covers it"])
    def test_that_assertion_can_fail(self, gen, leak):
        """Mutation guard: the scanner catches what the narrower one missed.

        Two of the three forms here are invisible to ``_TRACKER_RE`` alone, so
        this is what stops the assertion above silently weakening again.
        """
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import check_no_tracker_refs as tracker

        found = tracker._scan_lines([f"# {leak}"], path=gen.GENERATED)
        assert [v.match for v in found] != []
