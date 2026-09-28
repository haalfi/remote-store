"""Unit tests for the done-register entry-length report.

Hermetic ``tmp_path`` registers pin the counting rule (an entry runs from its
``- [x] **ID`` header to the next header or heading) and the dossier split.
One test runs against the live file and asserts structure only, never counts:
the register grows on every merge.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

# Writes registers to disk and reads them back as UTF-8, so the cross-platform
# legs select it, as they do the sibling report's tests.
pytestmark = pytest.mark.os_sensitive

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "report_done_length.py"


def _load():
    spec = importlib.util.spec_from_file_location("report_done_length", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("report_done_length", mod)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()

_REGISTER = textwrap.dedent(
    """\
    # Development Backlog — Done

    Preamble prose with a [link](backlog/x.md) that is no entry.

    ## Absorbed

    - [x] **BK-001 — absorbed one** → **BK-002**

    ## Unreleased

    - [x] **BK-010 — short with dossier**
      Shipped a thing.
      Detail: [dossier](backlog/bk-010-thing.md)
    - [x] **BK-011 — long without dossier**
      one two three four five six seven eight nine ten
    ### A sub-heading ends the entry
    words here belong to no entry

    ## v0.2.0

    - [x] **ID-005 — alpha**
    - [x] **ID-006 — beta gamma**
    """
)


class TestParse:
    def test_sections_keep_file_order_and_skip_sectionless_text(self) -> None:
        sections = _mod.parse(_REGISTER)
        assert list(sections) == ["Absorbed", "Unreleased", "v0.2.0"]

    def test_entry_ends_at_any_heading_not_only_at_the_next_header(self) -> None:
        long = _mod.parse(_REGISTER)["Unreleased"][1]
        # Header is 7 str.split() tokens, body 10; the text under the ###
        # heading is not counted.
        assert long.words == 17
        assert long.has_dossier is False

    def test_dossier_link_anywhere_in_entry_marks_it(self) -> None:
        short = _mod.parse(_REGISTER)["Unreleased"][0]
        assert short.has_dossier is True
        assert short.words == 7 + 3 + 2

    def test_absorbed_form_link_counts_as_dossier(self) -> None:
        text = "## Absorbed\n\n- [x] **BUG-1 — t** → **BL-1**. Dossier: [BUG-1](backlog/bug-1-t.md).\n"
        assert _mod.parse(text)["Absorbed"][0].has_dossier is True

    def test_link_to_another_items_dossier_is_not_a_link(self) -> None:
        # Citing a neighbour's dossier neither gives an item a dossier nor
        # satisfies its own link; the second entry must read as Unlinked.
        text = (
            "## v1\n\n- [x] **BK-1 — a** cites [x](backlog/bk-2-b.md)\n"
            "- [x] **BK-3 — c** cites [x](backlog/bk-2-b.md)\n"
        )
        plain, unlinked = _mod.parse(text, frozenset({"BK-3"}))["v1"]
        assert (plain.has_dossier, plain.linked) == (False, False)
        assert (unlinked.has_dossier, unlinked.linked) == (True, False)

    def test_id_less_entry_counts(self) -> None:
        # Decided-against entries that never had an ID carry a dash in its place.
        text = "## Decided against\n\n- [x] **— never had an ID** *(refused)*\n  why\n"
        assert _mod.parse(text)["Decided against"] == [_mod.Entry(9, False, False)]

    def test_repeated_heading_gets_its_own_row(self) -> None:
        text = "## Bug Fixes\n\n- [x] **A-1 — a**\n\n## v1\n\n## Bug Fixes\n\n- [x] **A-2 — b c**\n"
        sections = _mod.parse(text)
        assert list(sections) == ["Bug Fixes", "v1", "Bug Fixes (2)"]
        assert [e.words for e in sections["Bug Fixes (2)"]] == [6]

    def test_dossier_file_without_link_counts_as_dossier_and_unlinked(self) -> None:
        # The entry that breaks ADR-0041 worst (long, link omitted) must stay in
        # the with-dossier figure, not fall into the without half.
        long = _mod.parse(_REGISTER, frozenset({"BK-011"}))["Unreleased"][1]
        assert (long.has_dossier, long.linked) == (True, False)

    def test_link_written_another_way_reads_as_unlinked(self) -> None:
        # A documented miss of the docstring's bound, pinned so it stays known.
        text = "## v1\n\n- [x] **BK-3 — c** [d](../backlog/bk-3-c.md)\n"
        entry = _mod.parse(text, frozenset({"BK-3"}))["v1"][0]
        assert (entry.has_dossier, entry.linked) == (True, False)

    def test_dossier_ids_from_filenames(self, tmp_path: Path) -> None:
        # A file renamed off the "<id>-" prefix is not seen (the other miss).
        for name in ("bk-011-thing.md", "id-259-other.md", "README.md", "bk-012-x.txt"):
            (tmp_path / name).write_text("", encoding="utf-8")
        assert _mod.dossier_ids(tmp_path) == frozenset({"BK-011", "ID-259"})
        assert _mod.dossier_ids(tmp_path / "absent") == frozenset()

    def test_non_entry_bullet_does_not_start_an_entry(self) -> None:
        text = "## v1\n\n- [ ] **BK-9 — open**\n- plain bullet\n"
        assert _mod.parse(text)["v1"] == []


class TestSummarize:
    def test_split_medians_and_empty_half_is_none(self) -> None:
        rows = {r.section: r for r in _mod.summarize(_mod.parse(_REGISTER))}
        unrel = rows["Unreleased"]
        assert (unrel.n, unrel.median) == (2, 14.5)
        assert (unrel.n_dossier, unrel.median_dossier, unrel.n_unlinked) == (1, 12.0, 0)
        assert (unrel.n_plain, unrel.median_plain) == (1, 17.0)
        rel = rows["v0.2.0"]
        assert (rel.n_dossier, rel.median_dossier) == (0, None)
        assert rel.median == 5.5

    def test_section_without_entries_is_omitted(self) -> None:
        rows = _mod.summarize(_mod.parse("## Empty\n\nprose only\n## v1\n\n- [x] **A-1 — t**\n"))
        assert [r.section for r in rows] == ["v1"]


class TestMain:
    def test_exit_code_is_zero_whatever_it_finds(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "BACKLOG-DONE.md"
        path.write_text(_REGISTER, encoding="utf-8")
        assert _mod.main([str(path)]) == 0
        out = capsys.readouterr().out
        # Exact rows pin the column order the release reading depends on:
        # all, with dossier, unlinked, without. An empty half renders as the
        # N/A dash.
        assert "| Unreleased | 2 | 14.5 | 1 | 12 | 0 | 1 | 17 |" in out
        assert "| v0.2.0 | 2 | 5.5 | 0 | — | 0 | 2 | 5.5 |" in out

    def test_sibling_dossier_dir_moves_an_unlinked_entry(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "BACKLOG-DONE.md"
        path.write_text(_REGISTER, encoding="utf-8")
        (tmp_path / "backlog").mkdir()
        (tmp_path / "backlog" / "bk-011-long.md").write_text("", encoding="utf-8")
        assert _mod.main([str(path)]) == 0
        assert "| Unreleased | 2 | 14.5 | 2 | 14.5 | 1 | 0 | — |" in capsys.readouterr().out

    def test_missing_file_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod.main([str(tmp_path / "absent.md")]) == 2
        assert "absent.md" in capsys.readouterr().err

    def test_live_register_structure(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod.main([]) == 0
        out = capsys.readouterr().out
        # Not "Unreleased": right after a release it holds no entry, and
        # sections without entries are omitted.
        assert "| Section | Entries | Median |" in out
        # Release sections are named vX.Y.Z; at least one has shipped.
        assert "| v0." in out
