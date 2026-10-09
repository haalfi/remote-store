"""Unit tests for scripts/sdd_lookup.py (BK-414).

Fixture files pin each command's output shape and the tool's two own
boundaries (ID-less entries, Detailed row extent); the ``TestLive`` class
resolves every open ID, every anchor and every ripple trigger in the real
files, which is what fails when a file's shape outgrows the parse.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_ripple_parity  # noqa: E402
import gen_backlogid  # noqa: E402
import sdd_lookup as _mod  # noqa: E402

_OPEN = """\
# Development Backlog

<a id="how-this-file-works"></a>
## How this file works

- [ ] **BK-900 — Rules prose that looks like an item**

---

<a id="first"></a>
## 1. First promise

**Promise:** one.

- [ ] **BK-001 — First open item**
  spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api
  Diagnosis line mentioning BK-002.
  Detail: [dossier](backlog/bk-001-first.md)

- [~] **BUG-002 — Second item, in progress**
  spec: BE-0210 · effort: M · audience: user.api
  Another diagnosis about listings.

---

<a id="second"></a>
## 2. Second promise

**Promise:** two.

- [ ] **ID-003 — Third item**
  spec: — · effort: S · audience: contributor.tooling
  Listings and listings again; listings.
"""

_DONE = """\
# Development Backlog — Done

<a id="decided-against"></a>
## Decided against

- [x] **BK-010 — Entry above an ID-less one**
  Its only body line.
- [x] **— A gate binding a `**Breaking**` entry** *(never had an ID)*
  Why it was refused.

## Unreleased

- [x] **BK-011 — Shipped thing**
  spec: BE-021 · effort: S · audience: user.api
  Dossier: [BK-011](backlog/bk-011-shipped.md).

  A second paragraph after a blank line.

## v0.1.0

- [x] **BK-012b — Old thing**

A section note at column 0, not part of the entry.

## Bugs

- [x] **BK-012b — Old thing, released duplicate**
"""

_REFERENCE = """\
# Claude Code Reference

---

<a id="ripple-check-table"></a>
## Ripple-check table

<a id="pre-work-index"></a>
### Pre-work index

#### Code surface

| Trigger | Ripples |
|---|---|
| Backend | README table |
| `_GATING` dict | spec, tests |
| `_BACKEND_GATING` dict | spec BE-027 |

<a id="detailed-checklist"></a>
### Detailed checklist

#### Code surface

| Trigger | Also check |
|---|---|
| **Backend** | README backends table, |
| | `pyproject.toml` extras |
| **`_GATING` dict** | sync spec |
| (sync) | tests |
| **`_GATING` dict** (async) | async spec |
| **`_BACKEND_GATING` dict** | BE-027 |

Paragraph after the table.

---

<a id="pr-gates"></a>
## PR validation gates

Gate text.

### Sub step

Sub text.

<a id="next-anchor"></a>
## Repository layout

```text
# not a heading
```
"""


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sdd = tmp_path / "sdd"
    (sdd / "backlog").mkdir(parents=True)
    (sdd / "BACKLOG.md").write_text(_OPEN, encoding="utf-8")
    (sdd / "BACKLOG-DONE.md").write_text(_DONE, encoding="utf-8")
    (sdd / "CLAUDE-REFERENCE.md").write_text(_REFERENCE, encoding="utf-8")
    (sdd / "backlog" / "bk-001-first.md").write_text("# BK-001 — First open item\n\nEvidence listings.\n", "utf-8")
    (sdd / "backlog" / "bk-011-shipped.md").write_text("# BK-011 — Shipped thing\n\nShipped body.\n", "utf-8")
    monkeypatch.setattr(_mod, "ROOT", tmp_path)
    monkeypatch.setattr(_mod, "BACKLOG", sdd / "BACKLOG.md")
    monkeypatch.setattr(_mod, "BACKLOG_DONE", sdd / "BACKLOG-DONE.md")
    monkeypatch.setattr(_mod, "DOSSIERS", sdd / "backlog")
    monkeypatch.setattr(_mod, "REFERENCE", sdd / "CLAUDE-REFERENCE.md")
    return tmp_path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = _mod.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


class TestImportedGrammar:
    def test_grammar_is_the_gates_own_objects(self):
        # The point of importing: a shape change that breaks the parse fails the gate first.
        assert _mod._HEADER_RE is gen_backlogid._HEADER_RE
        assert _mod._sections is gen_backlogid._sections
        assert _mod._parse_detailed is check_ripple_parity._parse_detailed
        assert _mod._parse_pre_work is check_ripple_parity._parse_pre_work


class TestShow:
    def test_open_item_verbatim_after_location_line(self, tree, capsys):
        code, out, _ = _run(capsys, "show", "bk-001")
        assert code == 0
        assert out.splitlines() == [
            "BK-001 · open · sdd/BACKLOG.md:15 · § 1. First promise",
            "- [ ] **BK-001 — First open item**",
            "  spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api",
            "  Diagnosis line mentioning BK-002.",
            "  Detail: [dossier](backlog/bk-001-first.md)",
        ]

    def test_in_progress_status_and_section(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "BUG-002")
        assert out.splitlines()[0] == "BUG-002 · in progress · sdd/BACKLOG.md:20 · § 1. First promise"

    def test_rules_header_is_not_a_section(self, tree, capsys):
        code, _, err = _run(capsys, "show", "BK-900")
        assert code == 1
        assert "BK-900" in err

    def test_entry_above_an_id_less_entry_stops_before_it(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "BK-010")
        assert out.splitlines() == [
            "BK-010 · done · sdd/BACKLOG-DONE.md:6 · § Decided against",
            "- [x] **BK-010 — Entry above an ID-less one**",
            "  Its only body line.",
        ]

    def test_entry_keeps_indented_paragraph_after_blank_line(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "BK-011")
        assert out.splitlines()[1:] == [
            "- [x] **BK-011 — Shipped thing**",
            "  spec: BE-021 · effort: S · audience: user.api",
            "  Dossier: [BK-011](backlog/bk-011-shipped.md).",
            "",
            "  A second paragraph after a blank line.",
        ]

    def test_released_duplicate_with_suffix_prints_both_with_sections(self, tree, capsys):
        # The suffix letter is lowercase in the file; the key is matched case-insensitively.
        code, out, _ = _run(capsys, "show", "BK-012B")
        assert code == 0
        heads = [line for line in out.splitlines() if line.startswith("BK-012b ·")]
        assert "A section note" not in out
        assert heads == [
            "BK-012b · done · sdd/BACKLOG-DONE.md:21 · § v0.1.0",
            "BK-012b · done · sdd/BACKLOG-DONE.md:27 · § Bugs",
        ]

    def test_several_ids_one_unknown_prints_known_and_exits_1(self, tree, capsys):
        code, out, err = _run(capsys, "show", "BK-001", "BK-999")
        assert code == 1
        assert out.startswith("BK-001 · open")
        assert "BK-999" in err
        assert "BK-001" not in err

    def test_prose_mention_is_not_a_header(self, tree, capsys):
        # BK-002 appears only inside BK-001's diagnosis.
        code, out, _ = _run(capsys, "show", "BK-002")
        assert (code, out) == (1, "")

    def test_dossier_from_link_appended_with_authority_banner(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "BK-001", "--dossier")
        lines = out.splitlines()
        banner = lines.index(
            "--- dossier sdd/backlog/bk-001-first.md "
            "(evidence: dated record; prescription: advisory, re-derive before acting) ---"
        )
        assert lines[banner + 1 :] == ["# BK-001 — First open item", "", "Evidence listings."]

    def test_done_entry_dossier_link_resolves(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "BK-011", "--dossier")
        assert "--- dossier sdd/backlog/bk-011-shipped.md" in out
        assert out.rstrip().endswith("Shipped body.")

    def test_no_dossier_says_so(self, tree, capsys):
        _, out, _ = _run(capsys, "show", "ID-003", "--dossier")
        assert out.splitlines()[-1] == "--- dossier: none for ID-003 ---"


class TestFind:
    def test_one_line_per_item_not_per_matching_line(self, tree, capsys):
        code, out, _ = _run(capsys, "find", "LISTINGS", "--open")
        assert code == 0
        assert out.splitlines() == [
            "BUG-002 · in progress · sdd/BACKLOG.md:20 · Second item, in progress ⟶ Another diagnosis about listings.",
            "ID-003 · open · sdd/BACKLOG.md:31 · Third item ⟶ Listings and listings again; listings.",
        ]

    def test_header_match_carries_no_arrow(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "first open", "--open")
        assert out.splitlines() == ["BK-001 · open · sdd/BACKLOG.md:15 · First open item"]

    def test_default_scope_covers_open_done_and_dossiers(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "shipped")
        assert out.splitlines() == [
            "BK-011 · done · sdd/BACKLOG-DONE.md:13 · Shipped thing",
            "sdd/backlog/bk-011-shipped.md:1 · BK-011 — Shipped thing ⟶ # BK-011 — Shipped thing",
        ]

    def test_id_less_entry_is_found_with_dash_for_id(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "refused", "--done")
        assert out.splitlines() == [
            "— · done · sdd/BACKLOG-DONE.md:8 · — A gate binding a `**Breaking**` entry ⟶ Why it was refused."
        ]

    def test_dossiers_scope_only(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "listings", "--dossiers")
        assert out.splitlines() == ["sdd/backlog/bk-001-first.md:3 · BK-001 — First open item ⟶ Evidence listings."]

    def test_cap_reports_the_remainder(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "listings", "--max", "1")
        lines = out.splitlines()
        assert len(lines) == 2
        assert lines[1] == "… 2 more; narrow the pattern or raise --max."

    def test_no_match_exits_1(self, tree, capsys):
        code, out, err = _run(capsys, "find", "zzz-nothing")
        assert (code, out) == (1, "")
        assert "/zzz-nothing/" in err

    @pytest.mark.parametrize(
        ("argv", "message"),
        [
            (["find"], "needs a pattern"),
            (["find", "x", "--spec", "BE-021", "--done"], "open items only"),
            (["find", "--spec", "BE-021", "--dossiers"], "open items only"),
            (["find", "("], "invalid regex"),
        ],
    )
    def test_usage_errors_exit_2(self, tree, capsys, argv, message):
        with pytest.raises(SystemExit) as exc:
            _mod.main(argv)
        assert exc.value.code == 2
        assert message in capsys.readouterr().err


class TestFindSpec:
    def test_spec_alone_shows_the_attribute_line(self, tree, capsys):
        code, out, _ = _run(capsys, "find", "--spec", "be-021")
        assert code == 0
        assert out.splitlines() == [
            "BK-001 · open · sdd/BACKLOG.md:15 · First open item"
            " ⟶ spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api"
        ]

    def test_spec_is_a_whole_token_not_a_prefix(self, tree, capsys):
        # BE-0210 on BUG-002 must not match BE-021, nor BE-021 match BE-0210.
        _, out, _ = _run(capsys, "find", "--spec", "BE-0210")
        assert [line.split(" · ")[0] for line in out.splitlines()] == ["BUG-002"]

    def test_repeated_spec_matches_any(self, tree, capsys):
        _, out, _ = _run(capsys, "find", "--spec", "SQL-BLOB-012", "--spec", "BE-0210")
        assert [line.split(" · ")[0] for line in out.splitlines()] == ["BK-001", "BUG-002"]

    def test_spec_and_pattern_both_apply(self, tree, capsys):
        code, out, _ = _run(capsys, "find", "listings", "--spec", "BE-021", "--spec", "BE-0210")
        assert code == 0
        assert [line.split(" · ")[0] for line in out.splitlines()] == ["BUG-002"]

    def test_spec_searches_open_items_only(self, tree, capsys):
        # BK-011 is a done entry whose attribute line names BE-021; --spec skips it by scope.
        code, out, _ = _run(capsys, "find", "--spec", "BE-021")
        assert code == 0
        assert [line.split(" · ")[0] for line in out.splitlines()] == ["BK-001"]

    def test_dash_spec_matches_nothing(self, tree, capsys):
        code, _, _ = _run(capsys, "find", "--spec", "BE-999")
        assert code == 1


class TestOutline:
    def test_sections_with_counts(self, tree, capsys):
        _, out, _ = _run(capsys, "outline")
        assert out.splitlines() == [
            "sdd/BACKLOG.md:11 ## 1. First promise · 2 entries",
            "sdd/BACKLOG.md:27 ## 2. Second promise · 1 entries",
        ]

    def test_done_section_lists_entries_including_id_less(self, tree, capsys):
        _, out, _ = _run(capsys, "outline", "--done", "--section", "DECIDED")
        assert out.splitlines() == [
            "sdd/BACKLOG-DONE.md:4 ## Decided against",
            "  BK-010 · done · sdd/BACKLOG-DONE.md:6 · Entry above an ID-less one",
            "  — · done · sdd/BACKLOG-DONE.md:8 · — A gate binding a `**Breaking**` entry",
        ]

    def test_unknown_section_lists_sections(self, tree, capsys):
        code, out, err = _run(capsys, "outline", "--section", "nope")
        assert (code, out) == (1, "")
        assert "  1. First promise" in err.splitlines()


class TestRefShow:
    def test_anchor_returns_section_to_next_same_level_heading(self, tree, capsys):
        code, out, _ = _run(capsys, "ref-show", "pr-gates")
        assert code == 0
        assert out.splitlines() == [
            "sdd/CLAUDE-REFERENCE.md:38-44 · PR validation gates",
            "## PR validation gates",
            "",
            "Gate text.",
            "",
            "### Sub step",
            "",
            "Sub text.",
        ]

    def test_trailing_rule_and_anchor_are_trimmed(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-show", "#detailed-checklist")
        lines = out.splitlines()
        assert lines[0] == "sdd/CLAUDE-REFERENCE.md:20-33 · Detailed checklist"
        assert lines[-1] == "Paragraph after the table."

    def test_heading_text_exact_match_prints_every_hit(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-show", "code surface")
        assert [line for line in out.splitlines() if line.startswith("sdd/")] == [
            "sdd/CLAUDE-REFERENCE.md:11-17 · Code surface",
            "sdd/CLAUDE-REFERENCE.md:22-33 · Code surface",
        ]

    def test_unique_substring_resolves(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-show", "sub st")
        assert out.splitlines() == ["sdd/CLAUDE-REFERENCE.md:42-44 · Sub step", "### Sub step", "", "Sub text."]

    def test_fenced_hash_line_is_not_a_heading(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-show", "Repository layout")
        assert out.splitlines()[-2:] == ["# not a heading", "```"]

    def test_ambiguous_substring_exits_1_with_candidates(self, tree, capsys):
        code, out, err = _run(capsys, "ref-show", "check")
        assert (code, out) == (1, "")
        assert err.startswith("2 headings contain")
        assert "  ### Detailed checklist #detailed-checklist" in err.splitlines()

    def test_unknown_key_exits_1_listing_every_heading(self, tree, capsys):
        code, _, err = _run(capsys, "ref-show", "nothing-like-this")
        assert code == 1
        assert "  ## PR validation gates #pr-gates" in err.splitlines()

    def test_list(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-show", "--list")
        assert "sdd/CLAUDE-REFERENCE.md:38 ## PR validation gates #pr-gates · 7 lines" in out.splitlines()


class TestRefRows:
    def test_pre_work_and_detailed_rows_with_continuations(self, tree, capsys):
        code, out, _ = _run(capsys, "ref-rows", "backend")
        assert code == 0
        groups = out.split("\n\n")
        assert groups[0].splitlines() == [
            "[pre-work] sdd/CLAUDE-REFERENCE.md:15",
            "| Backend | README table |",
            "[detailed] sdd/CLAUDE-REFERENCE.md:26-27",
            "| **Backend** | README backends table, |",
            "| | `pyproject.toml` extras |",
        ]

    def test_expansion_has_no_pre_work_row(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-rows", "(async)")
        assert out.splitlines() == [
            "[pre-work] none: expansion row",
            "[detailed] sdd/CLAUDE-REFERENCE.md:30",
            "| **`_GATING` dict** (async) | async spec |",
        ]

    def test_stem_over_matches_and_prints_every_match(self, tree, capsys):
        # Backticks and ** are ignored; `_GATING dict` is also inside `_BACKEND_GATING dict`.
        _, out, _ = _run(capsys, "ref-rows", "_gating DICT")
        detailed = [line for line in out.splitlines() if line.startswith("[detailed]")]
        assert detailed == [
            "[detailed] sdd/CLAUDE-REFERENCE.md:28-29",
            "[detailed] sdd/CLAUDE-REFERENCE.md:30",
            "[detailed] sdd/CLAUDE-REFERENCE.md:31",
        ]

    def test_last_trigger_stops_at_the_table_end(self, tree, capsys):
        _, out, _ = _run(capsys, "ref-rows", "_BACKEND_GATING")
        assert "Paragraph after the table." not in out

    def test_unknown_text_exits_1_listing_triggers(self, tree, capsys):
        code, out, err = _run(capsys, "ref-rows", "nope")
        assert (code, out) == (1, "")
        assert "  Code surface · `_GATING` dict (async)" in err.splitlines()


class TestLive:
    """Every key the live files define resolves: the parse still fits their shape."""

    def test_every_open_id_shows(self, capsys):
        text = _mod.BACKLOG.read_text(encoding="utf-8")
        ids = [f"{m.group(2)}-{m.group(3)}" for m in gen_backlogid._HEADER_RE.finditer(text) if m.group(1) in " ~"]
        assert ids
        code, out, _ = _run(capsys, "show", *ids)
        assert code == 0
        for item in ids:
            assert f"\n{item} · " in f"\n{out}"

    def test_every_done_id_shows(self, capsys):
        text = _mod.BACKLOG_DONE.read_text(encoding="utf-8")
        ids = sorted({f"{m.group(2)}-{m.group(3)}" for m in gen_backlogid._HEADER_RE.finditer(text)})
        assert any(item[-1].isalpha() for item in ids)  # the suffixed IDs this test exists for
        code, out, _ = _run(capsys, "show", *ids)
        assert code == 0
        for item in ids:
            assert f"\n{item} · " in f"\n{out}"

    def test_every_anchor_shows(self, capsys):
        # Enumerated apart from `_headings`, so an anchor it fails to attach still fails here.
        text = _mod.REFERENCE.read_text(encoding="utf-8")
        anchors = re.findall(r'<a id="([^"]+)"></a>', text)
        assert "pr-validation-gates" in anchors
        for anchor in anchors:
            code, out, _ = _run(capsys, "ref-show", anchor)
            assert code == 0, anchor
            assert out.count("\nsdd/CLAUDE-REFERENCE.md:") == 0, anchor  # exactly one section

    def test_every_trigger_in_both_presentations_resolves(self, capsys):
        text = _mod.REFERENCE.read_text(encoding="utf-8")
        pre_block, det_block = check_ripple_parity._blocks(text)
        triggers = [*check_ripple_parity._parse_pre_work(pre_block), *check_ripple_parity._parse_detailed(det_block)]
        assert triggers
        for t in triggers:
            code, out, _ = _run(capsys, "ref-rows", t.name)
            assert code == 0, t.name
            assert f"sdd/CLAUDE-REFERENCE.md:{t.line}" in out, t.name
