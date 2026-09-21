"""Unit tests for scripts/check_no_retrospective.py.

The gate exists because RFC-0015 D1 measured the cost of one file carrying both
the deliverable and the loop's diary: a quarter of the findings in its sample sat
on the record surface, and the rule that was supposed to keep them apart was
review-enforced and did not hold.

**This file is why the gate exempts itself.** It sits at
``tests/scripts/test_check_no_retrospective.py``, which matches the surface's
``tests/**/*.py`` glob, and it cannot test a phrase matcher without spelling the
phrases. Without the exemption the gate fails on its own guard, so the exemption
is a consequence of the surface's shape rather than a carve-out someone wanted;
``TestSelfExemption`` pins both halves — that the exemption applies to this file,
and that it is narrow enough not to blanket the tree this file sits in.

The bound case matters as much as the failing ones. ``TestStatedBound`` pins the
phrase set's reach *downward*: a retrospective written in other words is not
caught, and the gate's docstring says so rather than implying coverage it does
not have. A test that only proved the hits would let the bound rot.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_retrospective.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_no_retrospective", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_no_retrospective", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()

# One surface glob is enough for most cases; the tree is built under tmp_path.
_ONE_GLOB: tuple[str, ...] = ("sdd/BACKLOG*.md",)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestPhraseSet:
    """Every alternation branch in RFC-0015's phrase set is reached."""

    # Each case is (label, line). The set is the RFC's, so a branch losing its
    # test is a branch that can be deleted from the regex unnoticed.
    CASES = [
        ("retrospective-heading", "  **Retrospective:** what the loop learned."),
        ("annotated-after-upper", "  Annotated after round 3, for the record."),
        ("annotated-after-lower", "  This was annotated after the fix landed."),
        ("until-round-n", "  The count said five until round 2, wrongly."),
        ("earlier-revision", "  ...which an earlier revision of this paragraph claimed."),
        ("this-sentence-said", "  An earlier copy of this sentence said 21 instead."),
        ("this-line-read", "  this line read until round 5: the arm hands back a value."),
        ("this-figure-was", "  this figure was wrong four times before it settled."),
        ("this-step-read", "  this step read as a no-op before the correction."),
        ("corrected-in-round", "  The attribution was corrected in round 4."),
        ("round-n-caught", "  Round 5 caught three copies of this clause."),
        ("round-n-found", "  Round 2 found the split between guide and spec."),
        ("round-n-corrected", "  Round 3 corrected the arithmetic."),
    ]

    @pytest.mark.parametrize(("label", "line"), CASES, ids=[c[0] for c in CASES])
    def test_each_phrase_is_a_hit(self, tmp_path: Path, label: str, line: str) -> None:
        _write(tmp_path, "sdd/BACKLOG.md", f"# Backlog\n\n- [ ] **BK-001 — item**\n{line}\n")
        hits = _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset())
        assert len(hits) == 1, f"{label}: expected exactly one hit, got {[h.format() for h in hits]}"
        assert hits[0].text == line.strip()

    def test_phrase_set_is_the_rfc_spelling(self) -> None:
        """Compared against **the RFC**, not against a copy of it.

        RFC-0015 § References states the alternation, and the RFC states its
        figures over that exact set — so an edit on either side re-bases every
        count that cites it. An earlier form of this test compared the script's
        constant against a *third* hand-copy inside the test, which forced a
        two-place edit and could not detect the one drift it named: the script
        moving away from the RFC.
        """
        rfc = (_REPO_ROOT / "sdd" / "rfcs" / "rfc-0015-ship-two-surfaces.md").read_text(encoding="utf-8")
        spelt = [line for line in rfc.splitlines() if line.startswith("  `Retrospective|")]
        assert len(spelt) == 1, f"expected one backticked phrase set in the RFC, found {len(spelt)}"
        assert spelt[0].strip().strip("`") == _mod.PHRASES


class TestLocalization:
    """Rule 2: report which element differs, not that a difference exists."""

    def test_hit_names_file_and_line(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "sdd/BACKLOG.md",
            "# Backlog\n\nclean line\nanother clean line\nthe value said three until round 2, wrongly\nclean tail\n",
        )
        (hit,) = _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset())
        assert hit.path == "sdd/BACKLOG.md"
        assert hit.line == 5
        assert hit.format() == "sdd/BACKLOG.md:5: the value said three until round 2, wrongly"

    def test_every_hit_in_a_file_is_reported(self, tmp_path: Path) -> None:
        """Not just the first — a file with three diary lines owes three lines of output."""
        _write(
            tmp_path,
            "sdd/BACKLOG.md",
            "# Backlog\n\nRound 1 caught the first draft.\nclean\nRound 4 found the same thing.\n"
            "clean\ncorrected in round 6, finally.\n",
        )
        hits = _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset())
        assert [h.line for h in hits] == [3, 5, 7]

    def test_exit_code_and_stderr_on_a_hit(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The gate fails loudly on stderr, and prints the remedy, not just the count.

        Through `main`, which is the part that was never executed: an earlier
        form of this test named the exit code and stderr, requested `capsys`,
        read neither, and asserted a `Hit.format()` string instead. `main` took
        no root then, so the failure branch — the count line, the per-hit lines,
        the RFC-0015 remedy paragraph, `return 1` — could not be reached at all.
        """
        _write(tmp_path, "sdd/BACKLOG.md", "Round 2 caught it.\n")
        _write(tmp_path, "CHANGELOG.md", "clean\n")
        assert _mod.main(["--root", str(tmp_path)]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Found 1 retrospective line(s) in 1 file(s):" in captured.err
        assert "sdd/BACKLOG.md:1: Round 2 caught it." in captured.err
        assert "RFC-0015 D1" in captured.err
        assert "Keep the claim" in captured.err

    def test_the_scanned_count_excludes_the_exempt_files(self, tmp_path: Path) -> None:
        """The clean line reports what was read, not what was enumerated.

        `len(iter_surface_files())` counts the exempt files too, so the gate
        over-stated its own coverage by the size of the exemption — a figure in
        its output that did not match what produced it.
        """
        _write(tmp_path, "sdd/BACKLOG.md", "clean\n")
        _write(tmp_path, "CHANGELOG.md", "clean\n")
        _write(tmp_path, "tests/scripts/test_check_no_retrospective.py", "phrases: Round 2 caught it.\n")
        enumerated = len(_mod.iter_surface_files(tmp_path, _mod.SURFACE))
        scanned = _mod.scanned_count(tmp_path, _mod.SURFACE, _mod._EXEMPT)
        assert enumerated == 3
        assert scanned == 2, "the exempt guard is enumerated but not read"

    def test_the_clean_line_reports_the_scanned_count(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(tmp_path, "sdd/BACKLOG.md", "clean\n")
        _write(tmp_path, "tests/scripts/test_check_no_retrospective.py", "Round 2 caught it.\n")
        assert _mod.main(["--root", str(tmp_path)]) == 0
        assert "(1 files scanned)" in capsys.readouterr().out


class TestSurface:
    """What is on the deliverable surface, and what is deliberately off it."""

    def test_clean_surface_is_silent(self, tmp_path: Path) -> None:
        _write(tmp_path, "sdd/BACKLOG.md", "# Backlog\n\n- [ ] **BK-001 — item**\n  A durable claim.\n")
        assert _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset()) == []

    @pytest.mark.parametrize(
        "rel",
        [
            "CHANGELOG.md",
            "sdd/specs/009-sftp-backend.md",
            "sdd/BACKLOG.md",
            "sdd/BACKLOG-DONE.md",
            "src/remote_store/_store.py",
            "tests/backends/sftp/test_config.py",
            "examples/getting_started/quickstart.py",
            "examples/tutorial.md",
            "examples/notebooks/intro.ipynb",
            "docs-src/reference/migration.md",
        ],
    )
    def test_surface_reaches(self, tmp_path: Path, rel: str) -> None:
        """Each tree D1 names is genuinely scanned, including the migration guide."""
        _write(tmp_path, rel, "Round 3 caught it.\n")
        hits = _mod.scan(root=tmp_path, surface=_mod.SURFACE, exempt=frozenset())
        assert [h.path for h in hits] == [rel]

    @pytest.mark.parametrize(
        "rel",
        [
            "sdd/traces/bk-001-thing.yml",
            "sdd/rfcs/rfc-0015-ship-two-surfaces.md",
            "sdd/research/research-something.md",
            "sdd/adrs/0037-whole-file-gate.md",
            "scripts/some_gate.py",
            ".claude/skills/ship/SKILL.md",
        ],
    )
    def test_surface_excludes_the_record_and_scripts(self, tmp_path: Path, rel: str) -> None:
        """The record is where D1 *sends* the diary; failing on it would invert the rule.

        ``sdd/rfcs/`` is the sharpest case: RFC-0015 defines the phrase set, so a
        surface including it fails on the document that specifies the check.
        """
        _write(tmp_path, rel, "Round 3 caught it, and this is where that belongs.\n")
        assert _mod.scan(root=tmp_path, surface=_mod.SURFACE, exempt=frozenset()) == []

    def test_a_file_matched_by_two_globs_is_reported_once(self, tmp_path: Path) -> None:
        _write(tmp_path, "sdd/BACKLOG.md", "Round 3 caught it.\n")
        overlapping = ("sdd/BACKLOG*.md", "sdd/BACKLOG.md")
        hits = _mod.scan(root=tmp_path, surface=overlapping, exempt=frozenset())
        assert len(hits) == 1


class TestSelfExemption:
    """Forced by the surface's shape, and narrow enough to stay honest."""

    def test_the_guard_is_exempt(self) -> None:
        """This very file. Without it the gate fails on its own test fixtures."""
        assert "tests/scripts/test_check_no_retrospective.py" in _mod._EXEMPT
        assert "scripts/check_no_retrospective.py" in _mod._EXEMPT

    def test_the_exemption_is_two_files_not_a_tree(self) -> None:
        """A directory-wide exemption would blanket every guard under tests/scripts/."""
        assert len(_mod._EXEMPT) == 2
        assert all(entry.endswith(".py") for entry in _mod._EXEMPT)

    def test_exempt_paths_exist(self) -> None:
        """An exemption naming a moved file silently stops exempting anything."""
        for rel in _mod._EXEMPT:
            assert (_REPO_ROOT / rel).is_file(), f"{rel} is exempted but does not exist"

    def test_a_non_exempt_sibling_under_tests_scripts_is_still_scanned(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/scripts/test_something_else.py", "# Round 3 caught it.\n")
        hits = _mod.scan(root=tmp_path, surface=_mod.SURFACE, exempt=_mod._EXEMPT)
        assert [h.path for h in hits] == ["tests/scripts/test_something_else.py"]


class TestStatedBound:
    """DRIFT-RULES Rule 7: document what the check does not catch, and pin it."""

    def test_a_retrospective_in_other_words_is_missed(self, tmp_path: Path) -> None:
        """The shape the gate's first run missed, kept as a fixture.

        ``an earlier revision of this`` requires the ``of this``; this line says
        ``an earlier revision named three``. It is a retrospective in every sense
        D1 means and the gate does not reach it — the instance was in
        ``sdd/specs/009-sftp-backend.md``, found by reading the same files the
        gate had just reported 14 hits in, and cleaned by hand in that change.
        Pinned so the bound cannot quietly become false in either direction: if a
        later phrase-set edit catches it, this test fails and the docstring's
        bound gets rewritten rather than silently over-claiming.
        """
        missed = "naming them requires knowing what every guard does, an earlier revision named three of which"
        _write(tmp_path, "sdd/BACKLOG.md", missed + "\n")
        assert _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset()) == []

    def test_a_phrase_split_across_a_line_break_is_missed(self, tmp_path: Path) -> None:
        """Line-oriented, as the docstring says. Wrapped prose can hide a phrase."""
        _write(tmp_path, "sdd/BACKLOG.md", "the value stood at five until\nround 2, when it moved.\n")
        assert _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset()) == []

    def test_lower_case_retrospective_is_missed(self, tmp_path: Path) -> None:
        """Case-sensitive, verbatim as the RFC spells it."""
        _write(tmp_path, "sdd/BACKLOG.md", "a retrospective note about the previous draft\n")
        assert _mod.scan(root=tmp_path, surface=_ONE_GLOB, exempt=frozenset()) == []


class TestRepoIsClean:
    """The gate's whole point: master's deliverable surface carries no diary."""

    def test_the_real_surface_is_clean(self) -> None:
        hits = _mod.scan()
        assert hits == [], "Retrospectives on the deliverable surface:\n" + "\n".join(h.format() for h in hits)

    def test_main_reports_clean(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod.main([]) == 0
        assert "No retrospectives on the deliverable surface" in capsys.readouterr().out
