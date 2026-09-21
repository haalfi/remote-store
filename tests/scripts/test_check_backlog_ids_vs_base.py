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
import subprocess
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

    def test_a_dropped_message_names_the_base_actually_read(self) -> None:
        (problem,) = _mod.compare(
            _open_items(), _done_items(), _open_items("BUG-291"), _done_items(), set(), base="origin/release"
        )
        assert "origin/release" in problem.format()
        assert "origin/master" not in problem.format()

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

    def test_the_message_names_the_base_actually_read(self) -> None:
        """Rule 2: naming a side the run never read is the defect, not a cosmetic slip.

        `main` honours `--base` in the reads, so a hardcoded `origin/master` in
        the prose would send a reader to diff the wrong ref.
        """
        (problem,) = _mod.compare(
            _open_items(), _done_items("BK-101"), _open_items("BK-101"), _done_items(), set(), base="origin/release"
        )
        assert "origin/release" in problem.format()
        assert "origin/master" not in problem.format()

    def test_a_split_id_is_matched(self) -> None:
        """BK-167a — the trailing-letter form _schema.yml allows for split items."""
        assert _mod.subject_ids("BK-167a: do the first half") == {"BK-167a"}
        assert _mod.subject_ids("BK-167a do the first half") == {"BK-167a"}


class TestCommitIdGrammar:
    """The arbitrator: which IDs this branch's commits claim."""

    @pytest.mark.parametrize(
        ("subject", "expected"),
        [
            ("BK-378: Build RFC-0015's D1 and D4", {"BK-378"}),
            ("BUG-254: The store root meets BE-029", {"BUG-254"}),
            ("ID-182 drift-guard helpers", {"ID-182"}),
            ("AF-008: Add credential masking", {"AF-008"}),
            ("BL-011: something", {"BL-011"}),
            # The shape that made every co-shipped branch report POACHED. Each of
            # these is a real `origin/master` subject from the forty before this PR.
            ("BK-375, BK-373, BK-377: derive the published support windows", {"BK-375", "BK-373", "BK-377"}),
            ("BK-369, BK-372, BK-374: watch both ends of every declared range", {"BK-369", "BK-372", "BK-374"}),
            ("BK-376, BK-377: File the llmstxt sections gap", {"BK-376", "BK-377"}),
            # A range claims only what it spells: 284-286 carry no prefix, and
            # inventing them would make the gate trust a number nobody wrote.
            ("BUG-283..286: Correct five dependency floors", {"BUG-283"}),
            # Only the run before the colon; a body mention is not a claim.
            ("BK-001: fix the BK-002 regression", {"BK-001"}),
        ],
    )
    def test_a_subject_claims_every_id_it_names(self, subject: str, expected: set[str]) -> None:
        assert _mod.subject_ids(subject) == expected

    @pytest.mark.parametrize(
        "subject",
        [
            "Fix the thing (BK-378)",  # not leading
            "Merge branch 'master' into bk-378",  # no PREFIX-NNN token
            "BK378: missing the hyphen",
            "XX-001: not an allocated prefix",
            "BK-378Build: no separator",
            "Release v0.32.0",
            "Chore(deps): Bump actions/setup-java from 5 to 6",
        ],
    )
    def test_non_conforming_subjects_claim_nothing(self, subject: str) -> None:
        assert _mod.subject_ids(subject) == set()

    def test_the_prefix_set_is_gen_backlogids(self) -> None:
        """Reused, not re-spelled — a second copy of the allocation set is drift."""
        assert set(_mod._PREFIXES) == {"BK", "BUG", "ID", "AF", "BL"}

    def test_the_commit_grammar_and_the_header_grammar_agree_on_one_id(self) -> None:
        """Set membership arbitrates, so the two must produce the same *string*.

        A header yielding `BK-167ab` against a commit yielding `BK-167a` reads
        as POACHED. The number was spelled `(\\d+[a-z]?)` here and
        `(\\d+[a-z]*)` in the allocator until this was pinned.
        """
        header_ids = _mod._flatten(_mod._extract_ids("- [x] **BK-167ab — a twice-split item**\n", "x"))
        assert header_ids == {"BK-167ab"}
        assert _mod.subject_ids("BK-167ab: do the second half") == header_ids


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


@pytest.fixture
def repo(tmp_path: Path):
    """A real two-side git repo: a base ref, a head, and a working tree.

    Replaces a `skipif` on `origin/master`. That mark skipped four of this
    class's five tests in `tooling-tests` — the only CI job that runs
    `tests/scripts/` — because it checks out at `actions/checkout@v7`'s default
    depth and has no `origin/master`. So the success half of the gate's I/O
    layer was never executed anywhere it mattered, and the 95% floor could not
    notice: `pyproject.toml` measures `--cov=remote_store`, so nothing under
    `scripts/` is counted at all.

    Building the repo instead of reaching for this repo's own history costs a
    fixture and buys assertions that run everywhere and say something.
    """

    def run(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True).stdout

    def write(rel: str, body: str) -> None:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    run("init", "-q", "-b", "main")
    run("config", "user.email", "guard@example.invalid")
    run("config", "user.name", "Guard")

    write("sdd/BACKLOG.md", _open_items("BK-100", "BK-101"))
    write("sdd/BACKLOG-DONE.md", _done_items("BK-099"))
    run("add", "-A")
    run("commit", "-q", "-m", "base state")
    # A real remote-tracking ref, which is what `git show origin/master:<path>`
    # and `git log origin/master..HEAD` resolve against.
    run("update-ref", "refs/remotes/origin/master", "HEAD")
    return tmp_path, run, write


class TestGitReads:
    """The I/O layer, against a synthetic repo — so it runs in CI, not around it."""

    def test_read_base_returns_content_for_a_tracked_file(self, repo) -> None:
        root, _run, _write = repo
        assert "BK-100" in _mod.read_base("sdd/BACKLOG.md", root=root)

    def test_read_base_returns_empty_for_an_absent_path(self, repo) -> None:
        """Empty rather than raising: a file absent from the base carries no IDs.

        Meaningful only against a base that exists — otherwise the empty string
        comes from the missing *ref* rather than the missing *path*, and the
        test is green for the wrong reason.
        """
        root, _run, _write = repo
        assert _mod.read_base("sdd/BACKLOG.md", root=root) != ""
        assert _mod.read_base("sdd/nope.md", root=root) == ""

    def test_branch_commit_ids_reads_every_id_a_subject_claims(self, repo) -> None:
        """Behavioural, not `isinstance`: the IDs, from real commit subjects."""
        root, run, write = repo
        write("a.txt", "one\n")
        run("add", "-A")
        run("commit", "-q", "-m", "BK-101: did the work")
        write("b.txt", "two\n")
        run("add", "-A")
        run("commit", "-q", "-m", "BK-375, BK-373, BK-377: derive the windows")
        write("c.txt", "three\n")
        run("add", "-A")
        run("commit", "-q", "-m", "Merge branch 'main' into bk-378")
        assert _mod.branch_commit_ids(root=root) == {"BK-101", "BK-375", "BK-373", "BK-377"}

    def test_a_clean_head_agrees_with_the_base(self, repo, capsys: pytest.CaptureFixture[str]) -> None:
        root, _run, _write = repo
        assert _mod.main(["--root", str(root)]) == 0
        assert "agree with origin/master" in capsys.readouterr().out

    def test_a_dropped_item_fails_end_to_end(self, repo, capsys: pytest.CaptureFixture[str]) -> None:
        """Through `main`, not `compare` — the reporting path is the part no test ran."""
        root, run, write = repo
        write("sdd/BACKLOG.md", _open_items("BK-100"))
        run("add", "-A")
        run("commit", "-q", "-m", "BK-100: unrelated work")
        assert _mod.main(["--root", str(root)]) == 1
        err = capsys.readouterr().err
        assert "DROPPED: BK-101" in err
        assert "origin/master has it open and the head has it nowhere" in err
        assert "restore it to sdd/BACKLOG.md" in err

    def test_a_poached_close_fails_end_to_end(self, repo, capsys: pytest.CaptureFixture[str]) -> None:
        root, run, write = repo
        write("sdd/BACKLOG.md", _open_items("BK-100"))
        write("sdd/BACKLOG-DONE.md", _done_items("BK-099", "BK-101"))
        run("add", "-A")
        run("commit", "-q", "-m", "BK-100: unrelated work")
        assert _mod.main(["--root", str(root)]) == 1
        assert "POACHED: BK-101" in capsys.readouterr().err

    def test_the_same_close_passes_when_a_commit_claims_it(self, repo, capsys: pytest.CaptureFixture[str]) -> None:
        """The asymmetry that keeps the gate usable, proved end to end."""
        root, run, write = repo
        write("sdd/BACKLOG.md", _open_items("BK-100"))
        write("sdd/BACKLOG-DONE.md", _done_items("BK-099", "BK-101"))
        run("add", "-A")
        run("commit", "-q", "-m", "BK-101: did the work")
        assert _mod.main(["--root", str(root)]) == 0

    def test_a_multi_id_subject_claims_all_of_its_closes(self, repo) -> None:
        """The regression that made every co-shipped branch report POACHED.

        Four of the forty commits before this PR used this subject shape.
        """
        root, run, write = repo
        write("sdd/BACKLOG.md", _open_items())
        write("sdd/BACKLOG-DONE.md", _done_items("BK-099", "BK-100", "BK-101"))
        run("add", "-A")
        run("commit", "-q", "-m", "BK-100, BK-101: closed together")
        assert _mod.main(["--root", str(root)]) == 0

    def test_an_unknown_base_fails_loudly(self, repo, capsys: pytest.CaptureFixture[str]) -> None:
        """A stale or absent ref is the bound the docstring names; never silent."""
        root, _run, _write = repo
        assert _mod.main(["--base", "origin/no-such-branch-xyz", "--root", str(root)]) == 1
        assert "is not a ref here" in capsys.readouterr().err

    def test_a_base_without_backlog_files_is_refused_not_reported_clean(
        self, repo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A ref that resolves but carries no backlog made the gate pass having compared nothing.

        `base_open` empty makes both disagreement sets empty by construction, so
        the gate printed "Backlog ID sets agree" and exited 0 — the same words
        it uses for a real pass.
        """
        root, run, _write = repo
        run("rm", "-r", "-q", "sdd")
        run("commit", "-q", "-m", "strip the backlog")
        run("update-ref", "refs/remotes/origin/empty", "HEAD")
        run("reset", "-q", "--hard", "HEAD~1")
        assert _mod.main(["--base", "origin/empty", "--root", str(root)]) == 1
        assert "carries neither" in capsys.readouterr().err
