"""Unit tests for scripts/check_changelog_unreleased.py.

The gate exists because a duplicated `[Unreleased]` entry reached master and
contradicted itself: two copies of one item four lines apart, the lower one
pre-amendment, so the section called an item open two lines below the entry
that closed it. The regression cases below reproduce that class — a duplicate,
a paragraph where a stub belongs, a user-facing completed item with no entry —
and the clean baseline proves the gate does not fire on the shape the section
is supposed to have.

The advisory case matters as much as the failing ones, and it is narrower than
it first looks. An entry with no completed item is legitimate — an open item
that shipped one bullet — and a gate that failed on it would be wrong about the
repo rather than the repo being wrong about itself. But such an entry is
*silent* rather than reported, because its ID is a live open item and that is a
register with an owner already; only an ID the backlog knows nowhere draws a
note. Both halves are pinned below, in `TestAudienceRule`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_changelog_unreleased.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_changelog_unreleased", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_changelog_unreleased", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _changelog(entries: str) -> str:
    return (
        "# Changelog\n\nIntro prose.\n\n## [Unreleased]\n\n"
        + entries
        + "\n## [0.30.0] - 2026-07-19\n\n### Changed\n\n"
        + "- Released prose that no rule here applies to, at whatever length it likes.\n"
    )


def _backlog_done(items: str) -> str:
    return "# Completed\n\n## Unreleased\n\n" + items + "\n## v0.30.0\n\n- [x] **BK-001 — old**\n  audience: user.api\n"


def _line_of(tmp_path: Path, needle: str) -> int:
    """1-indexed line of the first CHANGELOG line containing *needle*.

    Derived from the written fixture rather than counted by hand: the fixture's
    preamble is not what these tests are about, and a hand count of it goes
    wrong when the preamble changes.
    """
    lines = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8").split("\n")
    return next(i + 1 for i, line in enumerate(lines) if needle in line)


def _tree(tmp_path: Path, entries: str, items: str) -> Path:
    (tmp_path / "CHANGELOG.md").write_text(_changelog(entries), encoding="utf-8")
    (tmp_path / "sdd").mkdir(exist_ok=True)
    (tmp_path / "sdd" / "BACKLOG-DONE.md").write_text(_backlog_done(items), encoding="utf-8")
    return tmp_path


# One user-facing item and one that is not, each with its entry where the rule
# asks for one. Reused as the clean baseline the mutation cases bend.
_ENTRIES = "- BK-100: **Fix** — the thing now does the thing\n- BK-101: Tooling change nobody outside the repo sees\n"
_ITEMS = (
    "- [x] **BK-100 — The thing did not do the thing**\n"
    "  spec: — · effort: S · audience: user.api, contributor.process\n"
    "  Body prose.\n"
    "- [x] **BK-101 — Rework a hatch script**\n"
    "  spec: — · effort: S · audience: contributor.tooling\n"
)


class TestCleanBaseline:
    def test_a_well_formed_section_passes(self, tmp_path: Path) -> None:
        violations, notes = _mod.collect(_tree(tmp_path, _ENTRIES, _ITEMS))
        assert violations == []
        assert notes == []

    def test_released_sections_are_not_read(self, tmp_path: Path) -> None:
        """The fixture's [0.30.0] section carries a `###` heading and a bullet
        leading with no ID, both of which the shape rule would report. Neither
        may be, and the `###` must not trip the release-window stand-down
        either: the parser stops at the next `## [`."""
        violations, _ = _mod.collect(_tree(tmp_path, _ENTRIES, _ITEMS))
        assert violations == []


class TestUniqueness:
    def test_a_duplicated_id_fails_naming_both_lines(self, tmp_path: Path) -> None:
        entries = _ENTRIES + "- BK-100: **Fix** — the pre-amendment wording that a keep-both merge left behind\n"
        violations, _ = _mod.collect(_tree(tmp_path, entries, _ITEMS))
        assert len(violations) == 1
        assert "BK-100" in violations[0].message
        # Localized on both ends (DRIFT-RULES Rule 2): the duplicate's own line,
        # and the line of the copy it duplicates.
        assert violations[0].line == _line_of(tmp_path, "pre-amendment wording")
        assert f"line {_line_of(tmp_path, 'the thing now does the thing')}" in violations[0].message

    def test_the_shipped_defect_reproduces(self, tmp_path: Path) -> None:
        """Two items each duplicated once is the state that reached master."""
        entries = _ENTRIES + "- BK-100: earlier wording\n- BK-101: earlier wording\n"
        tree = _tree(tmp_path, entries, _ITEMS)
        violations, _ = _mod.collect(tree)
        assert sorted(v.line for v in violations) == [
            _line_of(tmp_path, "- BK-100: earlier wording"),
            _line_of(tmp_path, "- BK-101: earlier wording"),
        ]


class TestShape:
    def test_an_over_long_entry_fails(self, tmp_path: Path) -> None:
        long_entry = "- BK-100: " + "x" * _mod._MAX_ENTRY_CHARS + "\n"
        violations, _ = _mod.collect(_tree(tmp_path, long_entry + "- BK-101: fine\n", _ITEMS))
        assert len(violations) == 1
        assert str(_mod._MAX_ENTRY_CHARS) in violations[0].message

    def test_an_entry_at_the_budget_passes(self, tmp_path: Path) -> None:
        """The boundary is inclusive, so the constant means what it says."""
        exact = "- BK-100: " + "x" * (_mod._MAX_ENTRY_CHARS - len("- BK-100: ")) + "\n"
        assert len(exact.rstrip("\n")) == _mod._MAX_ENTRY_CHARS
        violations, _ = _mod.collect(_tree(tmp_path, exact + "- BK-101: fine\n", _ITEMS))
        assert violations == []

    def test_a_link_target_is_not_charged_to_the_budget(self, tmp_path: Path) -> None:
        """A URL is not prose, and counting it priced a breaking entry out of
        linking to the migration section it owes — measured: two of four
        breaking entries busted the budget on the link alone."""
        url = "https://docs.remotestore.dev/stable/reference/migration/#v0300-to-v0310"
        entry = "- BK-100: " + "x" * 250 + f" See the [migration guide]({url}).\n"
        assert len(entry.rstrip("\n")) > _mod._MAX_ENTRY_CHARS
        violations, _ = _mod.collect(_tree(tmp_path, entry + "- BK-101: fine\n", _ITEMS))
        assert violations == []

    def test_a_long_link_label_is_charged(self, tmp_path: Path) -> None:
        """The other half of the discount rule, and the half a mutant survived.

        `_LINK_RE.sub(r"\\1", …)` keeps the link *text* and drops only the
        target. Widening it to `sub("", …)` — one token — makes an arbitrarily
        long reader-visible label free, which is the budget defeated, and the
        two tests above both still passed under that mutant: one got further
        under budget, the other was already over from its own padding.
        """
        label = "A" * 400
        entry = f"- BK-100: [{label}](https://example.com)\n"
        violations, _ = _mod.collect(_tree(tmp_path, entry + "- BK-101: fine\n", _ITEMS))
        assert len(violations) == 1
        assert "characters of prose" in violations[0].message

    def test_prose_around_a_link_is_still_charged(self, tmp_path: Path) -> None:
        """The discount is the target only — a paragraph does not become a stub
        by having a link in it."""
        entry = "- BK-100: " + "x" * _mod._MAX_ENTRY_CHARS + " [see](https://example.com).\n"
        violations, _ = _mod.collect(_tree(tmp_path, entry + "- BK-101: fine\n", _ITEMS))
        assert len(violations) == 1
        assert "characters of prose" in violations[0].message

    def test_a_wrapped_entry_fails(self, tmp_path: Path) -> None:
        entries = "- BK-100: a title that someone\n  wrapped onto a second line\n- BK-101: fine\n"
        violations, _ = _mod.collect(_tree(tmp_path, entries, _ITEMS))
        assert len(violations) == 1
        assert violations[0].line == _line_of(tmp_path, "wrapped onto a second line")

    def test_a_compound_prefix_entry_is_an_entry(self, tmp_path: Path) -> None:
        """One line, one verdict, across both parsers of this section.

        `check_breaking_migration_link.py` admits `[A-Z][A-Z0-9-]*-\\d+`, and its
        own tests pin the compound form. Spelling this gate's prefix `[A-Z]+`
        made `- SQL-BLOB-020: …` a valid entry there and a stray line here, so a
        single `hatch run lint` returned two answers about one line — the
        disagreement both modules say they exist to prevent one level up.
        """
        entries = "- SQL-BLOB-020: a compound-prefix entry\n- BK-101: fine\n"
        section = _mod.parse_unreleased(_tree(tmp_path, entries, _ITEMS) / "CHANGELOG.md")
        assert [e.item_id for e in section.entries] == ["SQL-BLOB-020", "BK-101"]
        assert section.stray == []


class TestReleaseWindow:
    """CONTRIBUTING.md § Release Phase 1 condenses `[Unreleased]` in place, and
    Phase 2 is what renames the heading — so the released shape lives under
    `[Unreleased]` for that whole span, and Phase 3 runs `hatch run all` over
    it. A gate that fails there blocks the release it serves."""

    def test_a_grouped_section_stands_down_instead_of_failing(self, tmp_path: Path) -> None:
        """Reproduces the release window: run against it before this behaviour
        existed, the gate reported every condensed line as a stray and every
        completed item as entry-less, and its remediation told the release
        manager to do Phase 2 early."""
        condensed = (
            "### Fixed\n\n"
            "- **A condensed release entry** carrying prose at whatever length it\n"
            "  likes, wrapped over lines, naming no ID at the start.\n"
        )
        violations, notes = _mod.collect(_tree(tmp_path, condensed, _ITEMS))
        assert violations == []
        assert len(notes) == 1
        assert notes[0].startswith(_mod._STOOD_DOWN)

    def test_the_stand_down_is_printed_and_not_called_a_pass(self, tmp_path: Path, capsys) -> None:
        """The cost of standing down is that a stray `###` switches three rules
        off; the only thing that keeps that visible is saying so on a green run.
        A run that checked nothing must not print the sentence claiming it did."""
        condensed = "### Fixed\n\n- **A condensed release entry** with no leading ID.\n"
        rc = _mod.main(["--repo-root", str(_tree(tmp_path, condensed, _ITEMS))])
        out = capsys.readouterr().out
        assert rc == 0
        assert "stood down" in out
        assert "unique, stub-shaped and complete" not in out

    def test_the_audience_rule_stands_down_with_the_rest(self, tmp_path: Path) -> None:
        """Not three independent stand-downs: the audience rule keys on the same
        `- <ID>:` lines, so a section with none reports every completed
        user-facing item as missing one. BK-100 is user-facing in `_ITEMS`."""
        violations, _ = _mod.collect(_tree(tmp_path, "### Fixed\n\n- prose, no ID.\n", _ITEMS))
        assert violations == []

    def test_the_rules_come_back_once_the_grouping_goes(self, tmp_path: Path) -> None:
        """The stand-down is keyed on the grouping, not latched: a section that
        never had one is checked, and this is what a mid-cycle stray `###`
        costs until it is removed."""
        entries = _ENTRIES + "- BK-100: a duplicate the stand-down would have hidden\n"
        with_heading, _ = _mod.collect(_tree(tmp_path, "### Added\n\n" + entries, _ITEMS))
        assert with_heading == []
        without_heading, _ = _mod.collect(_tree(tmp_path, entries, _ITEMS))
        assert [v.line for v in without_heading] == [_line_of(tmp_path, "would have hidden")]


class TestAudienceRule:
    def test_a_user_facing_item_without_an_entry_fails(self, tmp_path: Path) -> None:
        violations, _ = _mod.collect(_tree(tmp_path, "- BK-101: tooling\n", _ITEMS))
        assert len(violations) == 1
        assert violations[0].path == "sdd/BACKLOG-DONE.md"
        assert "BK-100" in violations[0].message

    def test_a_non_user_tag_is_recognised_as_user_facing(self, tmp_path: Path) -> None:
        """The schema's predicate is the `user.` prefix, not the literal
        `user.api`. Testing for the latter drops the items whose only user tag
        is `user.site` or `user.discoverability.llm` — which is exactly how a
        hand count of the same parse came out three short."""
        items = "- [x] **BK-100 — a docs change**\n  spec: — · effort: S · audience: user.discoverability.llm\n"
        violations, _ = _mod.collect(_tree(tmp_path, "- BK-101: unrelated\n", items))
        assert len(violations) == 1
        assert "user.discoverability.llm" in violations[0].message

    def test_an_item_with_no_audience_line_is_reported(self, tmp_path: Path) -> None:
        """Unevaluable is a finding, not a silent pass."""
        items = "- [x] **BK-100 — no metadata line at all**\n  Body prose.\n"
        violations, _ = _mod.collect(_tree(tmp_path, "- BK-100: fine\n", items))
        assert len(violations) == 1
        assert "no `audience:` line" in violations[0].message

    def test_body_prose_mentioning_audience_is_not_a_metadata_line(self, tmp_path: Path) -> None:
        """The silent direction of the same defect, and the one the previous
        test could not reach.

        These bodies argue about audience routinely — the ID-252 entry argues
        about its own — so an item with no metadata line whose prose contains
        the word was handed whatever that sentence parsed to, and escaped the
        rule entirely if none of it began with `user.`. Anchoring the pattern to
        the metadata line is what prevents it; taking only the first match never
        did.
        """
        items = (
            "- [x] **BK-100 — no metadata line, but the body discusses it**\n"
            "  This item's audience: contributor.tooling was argued about at length.\n"
        )
        violations, _ = _mod.collect(_tree(tmp_path, "- BK-101: unrelated\n", items))
        assert len(violations) == 1
        assert "no `audience:` line" in violations[0].message

    def test_an_entry_without_a_completed_item_is_advisory(self, tmp_path: Path) -> None:
        """The authority direction: the completed-item side governs, so an extra
        entry is reported and does not fail."""
        entries = _ENTRIES + "- ID-999: an ID the backlog knows nowhere\n"
        violations, notes = _mod.collect(_tree(tmp_path, entries, _ITEMS))
        assert violations == []
        assert len(notes) == 1
        assert "ID-999" in notes[0]

    def test_an_entry_for_an_open_item_is_silent(self, tmp_path: Path) -> None:
        """The register (DRIFT-RULES Rule 6). An open item that shipped one
        bullet is a tolerated divergence with an owner already — the item — so
        it draws no note. Without this, the live instance would print on every
        green run until it closed, which is how a passing gate's output becomes
        something readers skip."""
        tree = _tree(tmp_path, _ENTRIES + "- ID-999: one bullet of a still-open item\n", _ITEMS)
        (tree / "sdd" / "BACKLOG.md").write_text(
            "# Backlog\n\n- [ ] **ID-999 — still open**\n  spec: — · effort: S · audience: user.api\n",
            encoding="utf-8",
        )
        violations, notes = _mod.collect(tree)
        assert violations == []
        assert notes == []

    def test_a_tilde_item_also_registers(self, tmp_path: Path) -> None:
        """`[~]` is the in-progress marker CLAUDE.md principle 1 mandates, and it
        is live — narrowing the register to `[ ]` would start nagging about a
        partially-shipped item, which is the case the register exists for."""
        tree = _tree(tmp_path, _ENTRIES + "- ID-999: one bullet of a [~] item\n", _ITEMS)
        (tree / "sdd" / "BACKLOG.md").write_text(
            "# Backlog\n\n- [~] **ID-999 — in progress**\n  spec: — · effort: S · audience: user.api\n",
            encoding="utf-8",
        )
        violations, notes = _mod.collect(tree)
        assert violations == []
        assert notes == []

    def test_a_completed_item_in_the_open_backlog_still_notes(self, tmp_path: Path) -> None:
        """The register keys on *open*, so widening it to any status would
        suppress the note for an `[x]` bullet left in BACKLOG.md — an item that
        belongs in BACKLOG-DONE and whose entry nothing has accounted for."""
        tree = _tree(tmp_path, _ENTRIES + "- ID-999: an entry nothing accounts for\n", _ITEMS)
        (tree / "sdd" / "BACKLOG.md").write_text(
            "# Backlog\n\n- [x] **ID-999 — done, but filed in the wrong place**\n",
            encoding="utf-8",
        )
        violations, notes = _mod.collect(tree)
        assert violations == []
        assert len(notes) == 1
        assert "ID-999" in notes[0]

    def test_a_suffixed_id_parses_as_itself(self, tmp_path: Path) -> None:
        """IDs may carry a letter suffix — BK-139d, ID-118b and ID-013b are live
        in the backlog, and `gen_backlogid.py` spells the number `\\d+[a-z]*`.

        Spelling it `[A-Z]+-\\d+` was wrong twice over: a legitimate suffixed
        stub was failed as a stray line, and the completed-item pattern silently
        truncated `BK-139a` to `BK-139`, so the audience rule would demand an
        entry for an ID that does not exist and accept an unrelated one.
        """
        entries = "- BK-139a: **Fix** — a suffixed item\n"
        items = "- [x] **BK-139a — a suffixed item**\n  spec: — · effort: S · audience: user.api\n"
        violations, notes = _mod.collect(_tree(tmp_path, entries, items))
        assert violations == []
        assert notes == []

    def test_a_parenthetical_bullet_parses(self, tmp_path: Path) -> None:
        """`**BK-167b (partial) — …` is a live shape that gen_backlogid tolerates."""
        entries = "- BK-167b: **Fix** — the partial one\n"
        items = "- [x] **BK-167b (partial) — the partial one**\n  spec: — · effort: S · audience: user.api\n"
        violations, _ = _mod.collect(_tree(tmp_path, entries, items))
        assert violations == []

    def test_a_non_x_status_is_not_a_completed_item(self, tmp_path: Path) -> None:
        """Completed means `[x]`, matching BACKLOG-DONE's own preamble and
        gen_backlogid.py. Two parsers over one artifact disagreeing about what
        counts is the defect this gate and check_breaking_migration_link.py
        both say they exist to avoid one level up."""
        items = "- [~] **BK-100 — shipped one bullet**\n  spec: — · effort: S · audience: user.api\n"
        violations, _ = _mod.collect(_tree(tmp_path, "- BK-101: unrelated\n", items))
        assert violations == []

    def test_a_non_x_bullet_still_ends_the_item_above_it(self, tmp_path: Path) -> None:
        """The test above reads a `[~]` item alone, and passes either way. The
        defect needs the interleaving.

        `_ITEM_RE` matches `[x]` only, so a `[~]` bullet did not end the item
        above it and its `audience:` line was credited upward. Measured: this
        fixture returned `DoneItem('BK-100', audience=('user.api',))` — BK-100
        both escaped the "carries no `audience:` line" finding it is owed and
        was judged against tags belonging to another item. Deciding *what is a
        completed item* and deciding *where one ends* are two questions, and one
        pattern answered both.
        """
        items = (
            "- [x] **BK-100 — a completed item with no metadata line**\n"
            "- [~] **BK-200 — an in-progress item that does carry one**\n"
            "  spec: — · effort: S · audience: user.api\n"
        )
        parsed = _mod.parse_done_unreleased(_tree(tmp_path, "- BK-100: fine\n", items) / "sdd" / "BACKLOG-DONE.md")
        assert [(i.item_id, i.audience) for i in parsed] == [("BK-100", ())]

        violations, _ = _mod.collect(_tree(tmp_path, "- BK-100: fine\n", items))
        assert len(violations) == 1
        assert "BK-100 carries no `audience:` line" in violations[0].message


class TestCannotFailSilently:
    """The failure mode that made round 1's only bug finding.

    Returning an empty item list for "the heading is gone" made the audience
    rule evaluate nothing while the gate printed success and exited 0 — and
    Phase 2 renames that exact heading, so the silent case sat on the release
    path.
    """

    def test_a_renamed_done_heading_raises(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, _ENTRIES, _ITEMS)
        done = tree / "sdd" / "BACKLOG-DONE.md"
        done.write_text(
            done.read_text(encoding="utf-8").replace("## Unreleased", "## v0.31.0"),
            encoding="utf-8",
        )
        with pytest.raises(_mod.DerivationError, match="no `## Unreleased` heading"):
            _mod.collect(tree)

    def test_a_missing_done_file_raises(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, _ENTRIES, _ITEMS)
        (tree / "sdd" / "BACKLOG-DONE.md").unlink()
        with pytest.raises(_mod.DerivationError, match="cannot read"):
            _mod.collect(tree)

    def test_main_exits_nonzero_rather_than_reporting_success(self, tmp_path: Path, capsys) -> None:
        """The half that matters: the CLI must not print the success line."""
        tree = _tree(tmp_path, _ENTRIES, _ITEMS)
        (tree / "sdd" / "BACKLOG-DONE.md").unlink()
        assert _mod.main(["--repo-root", str(tree)]) == 1
        captured = capsys.readouterr()
        assert "stub-shaped and complete" not in captured.out
        assert "cannot derive the claim" in captured.err

    def test_a_missing_changelog_raises_rather_than_blaming_the_heading(self, tmp_path: Path) -> None:
        """The two failures are different and were reported as one: an
        unreadable file came back as "no `## [Unreleased]` heading (was it
        renamed early?)", sending the reader to Phase 2 to look for a renamed
        heading in a file that is not there."""
        tree = _tree(tmp_path, _ENTRIES, _ITEMS)
        (tree / "CHANGELOG.md").unlink()
        with pytest.raises(_mod.DerivationError, match="cannot read"):
            _mod.collect(tree)

    def test_a_missing_unreleased_heading_is_reported(self, tmp_path: Path) -> None:
        """The CHANGELOG side already reported this; pinned so it stays that way."""
        tree = _tree(tmp_path, _ENTRIES, _ITEMS)
        changelog = tree / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text(encoding="utf-8").replace("## [Unreleased]", "## [0.31.0] - 2026-09-01"),
            encoding="utf-8",
        )
        violations, _ = _mod.collect(tree)
        assert len(violations) == 1
        assert "no `## [Unreleased]` heading" in violations[0].message


class TestAgainstTheRepo:
    def test_the_repo_passes_its_own_gate(self) -> None:
        violations, _ = _mod.collect(_REPO_ROOT)
        assert violations == []

    def test_main_returns_zero_on_the_repo(self, capsys) -> None:
        assert _mod.main(["--repo-root", str(_REPO_ROOT)]) == 0

    def test_main_renders_a_violation(self, tmp_path: Path, capsys) -> None:
        """The exit-1 branch is the one a developer actually meets, and its
        message is the whole user-facing value of this gate — it is where the
        reader is sent to CONTRIBUTING and the ripple-check row. `scripts/` is
        outside `--cov=remote_store`, so nothing else would notice it breaking.
        """
        entries = _ENTRIES + "- BK-100: a duplicate\n"
        assert _mod.main(["--repo-root", str(_tree(tmp_path, entries, _ITEMS))]) == 1
        captured = capsys.readouterr()
        assert "CHANGELOG.md:" in captured.err
        assert "1 violation(s)" in captured.err
        assert "ripple-check row" in captured.err
        assert "stub-shaped and complete" not in captured.out

    def test_main_prints_the_advisory_note_and_still_passes(self, tmp_path: Path, capsys) -> None:
        entries = _ENTRIES + "- ID-999: an ID the backlog knows nowhere\n"
        assert _mod.main(["--repo-root", str(_tree(tmp_path, entries, _ITEMS))]) == 0
        captured = capsys.readouterr()
        assert "ID-999" in captured.out
        assert "stub-shaped and complete" in captured.out
