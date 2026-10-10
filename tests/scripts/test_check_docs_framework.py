"""Tests for scripts/check_docs_framework.py DOCFRAME-004 gate (G-02..G-06, G-08).

Spec: sdd/specs/047-docs-framework-tooling.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gate_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_docs_framework as _gate

    return _gate


# ---------------------------------------------------------------------------
# G-02: injective source→dest map
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_dest_collision_fails(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-first.md").write_text("<!-- doc: dual dest=explanation/design/shared.md -->\n# ADR-0001\n")
    (adrs / "0002-second.md").write_text("<!-- doc: dual dest=explanation/design/shared.md -->\n# ADR-0002\n")

    errors = gate_mod._check_g02(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-02")
    assert "explanation/design/shared.md" in errors[0]


# ---------------------------------------------------------------------------
# G-03: no Jinja syntax in dual files
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_jinja_in_dual_file_fails(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-jinja.md").write_text(
        "<!-- doc: dual dest=explanation/design/jinja.md -->\n# ADR-0001\n\n{{ var }}\n"
    )

    errors = gate_mod._check_g03(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-03")
    assert "Jinja-like syntax" in errors[0]


# ---------------------------------------------------------------------------
# G-04: no include-markdown in docs-src
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_include_markdown_in_docs_src_fails(gate_mod, tmp_path):
    guides = tmp_path / "docs-src" / "guides"
    guides.mkdir(parents=True)
    (guides / "page.md").write_text("# Guide\n\n{% include-markdown 'snippet.md' %}\n")

    errors = gate_mod._check_g04(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-04")
    assert "include-markdown" in errors[0]


@pytest.mark.spec("DOCFRAME-004")
def test_link_map_yml_in_docs_src_fails(gate_mod, tmp_path):
    docs_src = tmp_path / "docs-src"
    docs_src.mkdir(parents=True)
    (docs_src / "_link_map.yml").write_text("# legacy link map\n")

    errors = gate_mod._check_g04(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-04")
    assert "_link_map.yml" in errors[0]


# ---------------------------------------------------------------------------
# G-05: relative links in dual files resolve on disk
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_broken_repo_link_in_dual_fails(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-broken.md").write_text(
        "<!-- doc: dual dest=explanation/design/broken.md -->\n# ADR-0001\n\nSee [missing](./nonexistent.md).\n"
    )

    errors = gate_mod._check_g05(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-05")
    assert "nonexistent.md" in errors[0]


# ---------------------------------------------------------------------------
# G-06: URL prefix matches nav section
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_url_nav_misalignment_fails(gate_mod, tmp_path):
    docs_src = tmp_path / "docs-src"
    docs_src.mkdir(parents=True)
    (docs_src / "_nav.yml").write_text("- Guides:\n    - wrong/page.md\n")

    errors = gate_mod._check_g06(tmp_path)

    assert len(errors) == 1
    assert errors[0].startswith("G-06")
    assert "wrong/page.md" in errors[0]
    assert "Guides" in errors[0]


# ---------------------------------------------------------------------------
# G-08: nested list markers indented for Python-Markdown
# ---------------------------------------------------------------------------

# GitHub nests the sub-bullet (it sits in the item's content column);
# Python-Markdown needs 4 spaces and flattens it into the outer list.
_FLAT_NESTED = "1. **Rule.**\n   Body.\n   - sub one\n   - sub two\n\n2. **Next.**\n"
_FIXED_NESTED = "1. **Rule.**\n   Body.\n    - sub one\n    - sub two\n\n2. **Next.**\n"


def _write_dual(tmp_path: Path, body: str) -> None:
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-list.md").write_text(f"<!-- doc: dual dest=explanation/design/list.md -->\n# ADR-0001\n\n{body}")


@pytest.mark.spec("DOCFRAME-004")
def test_fixture_flattens_under_python_markdown():
    """Anchors G-08 to the renderer: the failing fixture really flattens, the fixed one nests."""
    import markdown

    assert "<ul>" not in markdown.markdown(_FLAT_NESTED)
    assert "<ol>\n<li>\n<p><strong>Rule.</strong>" in markdown.markdown(_FIXED_NESTED)
    assert "<ul>" in markdown.markdown(_FIXED_NESTED)


@pytest.mark.spec("DOCFRAME-004")
def test_nested_list_under_four_spaces_fails(gate_mod, tmp_path):
    _write_dual(tmp_path, _FLAT_NESTED)

    errors = gate_mod._check_g08(tmp_path)

    assert errors == [
        "G-08 sdd/adrs/0001-list.md:6: nested list marker indented 3, Python-Markdown needs 4",
        "G-08 sdd/adrs/0001-list.md:7: nested list marker indented 3, Python-Markdown needs 4",
    ]


@pytest.mark.spec("DOCFRAME-004")
def test_two_space_bullet_nesting_fails(gate_mod, tmp_path):
    _write_dual(tmp_path, "- a\n  - b\n    - c\n")

    errors = gate_mod._check_g08(tmp_path)

    assert [e.split(": ", 1)[1] for e in errors] == [
        "nested list marker indented 2, Python-Markdown needs 4",
        "nested list marker indented 4, Python-Markdown needs 8",
    ]


@pytest.mark.spec("DOCFRAME-004")
def test_nested_list_in_docs_src_fails(gate_mod, tmp_path):
    guides = tmp_path / "docs-src" / "guides"
    guides.mkdir(parents=True)
    (guides / "page.md").write_text("# Guide\n\n- a\n  - b\n")

    errors = gate_mod._check_g08(tmp_path)

    assert errors == ["G-08 docs-src/guides/page.md:4: nested list marker indented 2, Python-Markdown needs 4"]


# A table GitHub keeps in the item; Python-Markdown ends the list at it, so
# the 4-space bullets after it become a code block.
_FLAT_BLOCK = "- **Item.**\n\n  | a | b |\n  | - | - |\n  | 1 | 2 |\n\n    - sub\n"
_FIXED_BLOCK = "- **Item.**\n\n    | a | b |\n    | - | - |\n    | 1 | 2 |\n\n    - sub\n"


@pytest.mark.spec("DOCFRAME-004")
def test_block_fixture_leaves_list_under_python_markdown():
    import markdown

    flat = markdown.markdown(_FLAT_BLOCK, extensions=["tables"])
    fixed = markdown.markdown(_FIXED_BLOCK, extensions=["tables"])
    assert "</ul>\n<table>" in flat
    assert "<pre><code>- sub" in flat
    assert "<li>\n<p><strong>Item.</strong></p>\n<table>" in fixed
    assert "<pre>" not in fixed


@pytest.mark.spec("DOCFRAME-004")
def test_under_indented_list_item_block_fails(gate_mod, tmp_path):
    _write_dual(tmp_path, _FLAT_BLOCK)

    errors = gate_mod._check_g08(tmp_path)

    assert errors == [
        "G-08 sdd/adrs/0001-list.md:6: nested list-item block indented 2, Python-Markdown needs 4",
    ]


@pytest.mark.spec("DOCFRAME-004")
def test_g08_skips_lazy_continuation(gate_mod, tmp_path):
    # Without a blank line, a short-indented line continues the paragraph in both renderers.
    _write_dual(tmp_path, "1. a long\n  wrapped line\n    - sub\n")

    assert gate_mod._check_g08(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_nesting_after_column_zero_lazy_line_fails(gate_mod, tmp_path):
    # A column-0 lazy line keeps the item open in both renderers, so the
    # 3-space marker after it still nests on GitHub and flattens here.
    import markdown

    body = "1. a long\nwrapped at col 0\n   - sub\n"
    assert "<ul>" not in markdown.markdown(body)
    _write_dual(tmp_path, body)

    assert gate_mod._check_g08(tmp_path) == [
        "G-08 sdd/adrs/0001-list.md:6: nested list marker indented 3, Python-Markdown needs 4",
    ]


@pytest.mark.spec("DOCFRAME-004")
def test_g08_skips_list_glued_to_paragraph(gate_mod, tmp_path):
    # Python-Markdown starts no list right after paragraph text, so a
    # 2-space block under it is not lost nesting (and 4 spaces would be code).
    import markdown

    body = "**Label:**\n- item\n\n  | a | b |\n  | - | - |\n"
    assert "<li>" not in markdown.markdown(body, extensions=["tables"])
    _write_dual(tmp_path, body)

    assert gate_mod._check_g08(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g08_skips_fence_body_inside_item(gate_mod, tmp_path):
    # The fence sits inside the open item, so only the fence skip keeps
    # `  - x` (depth 1, under 4 spaces) from being reported.
    _write_dual(tmp_path, "- a\n\n    ```text\n  - x\n    ```\n")

    assert gate_mod._check_g08(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g08_new_list_after_paragraph_break(gate_mod, tmp_path):
    # Text after a blank line closes the list, so a 2-space list after the
    # next blank line is a new top-level list in both renderers, not nesting.
    import markdown

    body = "- a\n\nText.\n\n  - b\n"
    assert markdown.markdown(body).count("<ul>") == 2
    _write_dual(tmp_path, body)

    assert gate_mod._check_g08(tmp_path) == []


# ---------------------------------------------------------------------------
# Positive controls: clean fixtures return no errors
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-004")
def test_g02_no_collision_passes(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-first.md").write_text("<!-- doc: dual dest=explanation/design/first.md -->\n# ADR-0001\n")
    (adrs / "0002-second.md").write_text("<!-- doc: dual dest=explanation/design/second.md -->\n# ADR-0002\n")

    assert gate_mod._check_g02(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g03_no_jinja_passes(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-clean.md").write_text(
        "<!-- doc: dual dest=explanation/design/clean.md -->\n# ADR-0001\n\nClean content.\n"
    )

    assert gate_mod._check_g03(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g04_no_violations_passes(gate_mod, tmp_path):
    guides = tmp_path / "docs-src" / "guides"
    guides.mkdir(parents=True)
    (guides / "page.md").write_text("# Guide\n\nClean content.\n")

    assert gate_mod._check_g04(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g05_valid_link_passes(gate_mod, tmp_path):
    adrs = tmp_path / "sdd" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "0001-doc.md").write_text(
        "<!-- doc: dual dest=explanation/design/doc.md -->\n# ADR-0001\n\nSee [other](./0002-other.md).\n"
    )
    (adrs / "0002-other.md").write_text("<!-- doc: dual dest=explanation/design/other.md -->\n# ADR-0002\n")

    assert gate_mod._check_g05(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g06_correct_prefix_passes(gate_mod, tmp_path):
    docs_src = tmp_path / "docs-src"
    docs_src.mkdir(parents=True)
    (docs_src / "_nav.yml").write_text("- Guides:\n    - guides/page.md\n")

    assert gate_mod._check_g06(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g08_four_space_nesting_passes(gate_mod, tmp_path):
    _write_dual(tmp_path, _FIXED_NESTED + "\n- a\n    - b\n        - c\n\n" + _FIXED_BLOCK)

    assert gate_mod._check_g08(tmp_path) == []


@pytest.mark.spec("DOCFRAME-004")
def test_g08_against_live_repo(gate_mod):
    assert gate_mod._check_g08(ROOT) == []
