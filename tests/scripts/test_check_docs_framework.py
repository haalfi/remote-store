"""Tests for scripts/check_docs_framework.py DOCFRAME-004 gate (G-02..G-06).

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
