"""Unit tests for scripts/check_backlog_ids_vs_base.py.

The gate exists because PR #997 did both things it catches, in rounds 5 and 7,
and neither had a gate: a rebase dropped a live item out of ``sdd/BACKLOG.md``,
and the PR claimed to close an item belonging to another branch.
``gen_backlogid.py --check`` cannot see either — it compares open IDs against
*done* ones, so an item that simply vanishes passes, and so do two open items
sharing a number.

``compare()`` is pure, which is what makes this suite offline: the two failures
are exercised over synthetic file bodies and a synthetic commit-ID set, with no
``git``, no network and no second worktree. ``TestGitReads`` covers the thin I/O
layer separately, against the real repository.

The asymmetry is the thing to keep pinned. A head that closes an item is the
*normal* case and must never fail; what makes it a failure is the branch's
commits not naming it. ``TestPoached`` pins both directions, because a gate that
failed on legitimate closure would be switched off within a day.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_backlog_ids_vs_base.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_backlog_ids_vs_base", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_backlog_ids_vs_base", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _open_items(*ids: str) -> str:
    """A BACKLOG.md body holding one open item header per ID."""
    head = "# Backlog\n\n## Section\n\n"
    return head + "\n".join(
        f"- [ ] **{item} — a title**\n  spec: — · effort: S · audience: contributor.process\n" for item in ids
    )


def _done_items(*ids: str) -> str:
    """A BACKLOG-DONE.md body holding one completed item header per ID."""
    head = "# Completed\n\n## Unreleased\n\n"
    return head + "\n".join(
        f"- [x] **{item} — a title**\n  spec: — · effort: S · audience: contributor.process\n" for item in ids
    )


class TestClean:
    def test_identical_sides_agree(self) -> None:
        backlog, done = _open_items("BK-100", "BK-101"), _done_items("BK-099")
        assert _mod.compare(backlog, done, backlog, done, set()) == []

    def test_an_item_this_branch_opened_is_not_a_disagreement(self) -> None:
        """A new item on the head that master has never seen is ordinary work."""
        problems = _mod.compare(
            _open_items("BK-100", "BK-382"), _done_items(), _open_items("BK-100"), _done_items(), {"BK-382"}
        )
        assert problems == []

    def test_an_item_closed_on_master_and_absent_from_the_head_is_silent(self) -> None:
        """Only *open* IDs on the base are live; a done one leaving is not a drop."""
        problems = _mod.compare(
            _open_items("BK-100"), _done_items(), _open_items("BK-100"), _done_items("BK-050"), set()
        )
        assert problems == []


class TestDropped:
    """Failure 1: a rebase resolved a conflict by losing a live item."""

    def test_an_open_id_missing_from_the_head_is_reported(self) -> None:
        problems = _mod.compare(
            _open_items("BK-100"), _done_items(), _open_items("BK-100", "BK-101"), _done_items(), set()
        )
        assert len(problems) == 1
        assert problems[0].item_id == "BK-101"
        assert problems[0].kind == "DROPPED"

    def test_the_message_names_the_id_and_the_side(self) -> None:
        """Rule 2: report which element differs, and which side to fix."""
        (problem,) = _mod.compare(_open_items(), _done_items(), _open_items("BUG-291"), _done_items(), set())
        text = problem.format()
        assert "BUG-291" in text
        assert "origin/master" in text
        assert "sdd/BACKLOG.md" in text

    def test_an_id_the_head_moved_to_done_is_not_dropped(self) -> None:
        """Closing it is a different verdict from losing it, and may be legitimate."""
        problems = _mod.compare(_open_items(), _done_items("BK-101"), _open_items("BK-101"), _done_items(), {"BK-101"})
        assert problems == []

    def test_several_dropped_ids_are_all_reported_sorted(self) -> None:
        problems = _mod.compare(
            _open_items(), _done_items(), _open_items("BK-103", "BK-101", "BUG-200"), _done_items(), set()
        )
        assert [p.item_id for p in problems] == ["BK-101", "BK-103", "BUG-200"]
        assert {p.kind for p in problems} == {"DROPPED"}


class TestPoached:
    """Failure 2, and the asymmetry that keeps it usable."""

    def test_closing_an_item_no_commit_names_is_reported(self) -> None:
        problems = _mod.compare(
            _open_items("BK-100"), _done_items("BK-101"), _open_items("BK-100", "BK-101"), _done_items(), set()
        )
        assert len(problems) == 1
        assert problems[0].item_id == "BK-101"
        assert problems[0].kind == "POACHED"

    def test_closing_an_item_this_branch_did_is_clean(self) -> None:
        """The normal case. A gate failing here would be switched off, not obeyed."""
        problems = _mod.compare(
            _open_items("BK-100"), _done_items("BK-101"), _open_items("BK-100", "BK-101"), _done_items(), {"BK-101"}
        )
        assert problems == []

    def test_the_message_says_what_to_do(self) -> None:
        (problem,) = _mod.compare(_open_items(), _done_items("ID-259"), _open_items("ID-259"), _done_items(), set())
        text = problem.format()
        assert "ID-259" in text
        assert "no commit on this branch names it" in text

    def test_a_split_id_is_matched(self) -> None:
        """BK-167a — the trailing-letter form _schema.yml allows for split items."""
        assert _mod._COMMIT_ID_RE.match("BK-167a: do the first half") is not None
        assert _mod._COMMIT_ID_RE.match("BK-167a do the first half") is not None


class TestCommitIdGrammar:
    """The arbitrator: which IDs this branch's commits claim."""

    @pytest.mark.parametrize(
        ("subject", "expected"),
        [
            ("BK-378: Build RFC-0015's D1 and D4", "BK-378"),
            ("BUG-254: The store root meets BE-029", "BUG-254"),
            ("ID-182 drift-guard helpers", "ID-182"),
            ("AF-008: Add credential masking", "AF-008"),
            ("BL-011: something", "BL-011"),
        ],
    )
    def test_leading_token_is_the_item(self, subject: str, expected: str) -> None:
        match = _mod._COMMIT_ID_RE.match(subject)
        assert match is not None
        assert f"{match.group(1)}-{match.group(2)}" == expected

    @pytest.mark.parametrize(
        "subject",
        [
            "Fix the thing (BK-378)",  # not leading
            "Merge branch 'master' into bk-378",  # no PREFIX-NNN token
            "BK378: missing the hyphen",
            "XX-001: not an allocated prefix",
            "BK-378Build: no separator",
        ],
    )
    def test_non_conforming_subjects_claim_nothing(self, subject: str) -> None:
        assert _mod._COMMIT_ID_RE.match(subject) is None

    def test_the_prefix_set_is_gen_backlogids(self) -> None:
        """Reused, not re-spelled — a second copy of the allocation set is drift."""
        assert set(_mod._PREFIXES) == {"BK", "BUG", "ID", "AF", "BL"}


class TestReuse:
    """DRIFT-RULES Rule 1 / CLAUDE.md principle 4: one header grammar, not two."""

    def test_header_parsing_comes_from_gen_backlogid(self) -> None:
        """The function object itself is the allocator's, not a same-named copy."""
        assert _mod._extract_ids.__module__ == "gen_backlogid"
        assert _mod._extract_ids.__qualname__ == "_extract_ids"

    def test_the_imported_parser_is_the_one_the_allocator_uses(self) -> None:
        """Pins the reuse by behaviour, not by name: both sides read one header grammar.

        A header shape ``gen_backlogid.py`` accepts and this gate did not would
        make the two disagree about what an item *is* — the drift Rule 1 is
        about — and a name-only assertion above would still pass.
        """
        body = "- [ ] **BK-167a — a split item**\n- [x] **BUG-291 — a done one**\n- [~] **ID-259 — partial**\n"
        assert _mod._flatten(_mod._extract_ids(body, " ~")) == {"BK-167a", "ID-259"}
        assert _mod._flatten(_mod._extract_ids(body, "x")) == {"BUG-291"}

    def test_this_module_defines_no_header_regex(self) -> None:
        """Only the commit-subject grammar is local; the header grammar is imported."""
        source = _SCRIPT.read_text(encoding="utf-8")
        assert "_HEADER_RE = " not in source


class TestGitReads:
    """The thin I/O layer, against the real repository."""

    def test_read_base_returns_content_for_a_tracked_file(self) -> None:
        text = _mod.read_base("sdd/BACKLOG.md")
        assert text.startswith("#")

    def test_read_base_returns_empty_for_an_absent_path(self) -> None:
        """Empty rather than raising: a file that does not exist on the base has no IDs."""
        assert _mod.read_base("sdd/does-not-exist-on-master.md") == ""

    def test_branch_commit_ids_returns_a_set(self) -> None:
        assert isinstance(_mod.branch_commit_ids(), set)

    def test_main_runs_end_to_end_and_returns_a_verdict(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Pins the I/O wiring — reads both files on both sides, reaches a verdict.

        Deliberately **not** "this branch is clean". That assertion would couple
        the suite to transient commit state: a branch that has closed an item in
        the working tree but not yet committed the commit naming it is POACHED
        by this gate's own definition, which is correct behaviour and a state
        every split legitimately passes through. `check_no_retrospective.py`'s
        guard can assert repo cleanliness because its subject is committed
        content; this one's subject includes `git log`, so the same shape would
        make the suite red mid-work and teach people to ignore it. The gate runs
        at push time, where that state cannot survive.
        """
        code = _mod.main([])
        assert code in (0, 1)
        out = capsys.readouterr()
        assert ("agree with origin/master" in out.out) or ("disagreement(s) with origin/master" in out.err)

    def test_an_unknown_base_fails_loudly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A stale or absent ref is the bound the docstring names; it must not pass silently."""
        assert _mod.main(["--base", "origin/no-such-branch-xyz"]) == 1
        assert "is not a ref here" in capsys.readouterr().err
