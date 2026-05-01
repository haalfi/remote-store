"""Tests for scripts/docs/scan.py documentation framework (DOCFRAME-001..003).

Spec: sdd/specs/047-docs-framework-tooling.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def scan_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import docs.scan as _scan

    return _scan


# ---------------------------------------------------------------------------
# DOCFRAME-002: Classification Parser Contract
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-002")
def test_marker_parses_dual_with_dest(scan_mod, tmp_path):
    md = tmp_path / "test.md"
    md.write_text("<!-- doc: dual dest=explanation/design/authoring.md -->\n# Title\n")
    result = scan_mod._parse_marker(md.read_text())
    assert result == ("dual", "explanation/design/authoring.md")


@pytest.mark.spec("DOCFRAME-002")
def test_marker_parses_repo_only_no_dest(scan_mod, tmp_path):
    md = tmp_path / "test.md"
    md.write_text("<!-- doc: repo-only -->\n# Title\n")
    result = scan_mod._parse_marker(md.read_text())
    assert result == ("repo-only", None)


@pytest.mark.spec("DOCFRAME-002")
def test_marker_absent_defaults_to_dual_in_sdd_subdir(scan_mod, tmp_path):
    adrs_dir = tmp_path / "sdd" / "adrs"
    adrs_dir.mkdir(parents=True)
    md = adrs_dir / "0001-test-decision.md"
    md.write_text("# ADR-0001: Test Decision\n\nContent.\n")
    klass, dest = scan_mod._classify_file(md, tmp_path)
    assert klass == "dual"
    assert dest == "explanation/design/adrs/0001-test-decision.md"


@pytest.mark.spec("DOCFRAME-002")
@pytest.mark.spec("G-01")
def test_marker_absent_in_repo_root_is_an_error(scan_mod, tmp_path):
    md = tmp_path / "UNCLASSIFIED.md"
    md.write_text("# Some Document\n\nContent.\n")
    with pytest.raises(ValueError, match="G-01"):
        scan_mod._classify_file(md, tmp_path)


# ---------------------------------------------------------------------------
# DOCFRAME-001 + DOCFRAME-003: scan_dual_files / DualEntry
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-001")
@pytest.mark.spec("DOCFRAME-003")
def test_scan_dual_files_yields_only_dual_class(scan_mod, tmp_path):
    adrs_dir = tmp_path / "sdd" / "adrs"
    adrs_dir.mkdir(parents=True)
    adr = adrs_dir / "0001-test.md"
    adr.write_text("# ADR-0001: Test\n\nContent.\n")

    (tmp_path / "docs-src").mkdir()

    readme = tmp_path / "README.md"
    readme.write_text("<!-- doc: dual dest=index.md -->\n# Readme\n")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("<!-- doc: repo-only -->\n# Claude\n")

    entries = list(scan_mod.scan_dual_files(tmp_path))

    assert all(isinstance(e, scan_mod.DualEntry) for e in entries)
    sources = {e.source for e in entries}
    assert adr.resolve() in sources
    assert readme.resolve() in sources
    assert claude_md.resolve() not in sources
