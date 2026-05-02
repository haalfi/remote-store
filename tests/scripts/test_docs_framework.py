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
# DOCFRAME-002: error paths
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-002")
def test_marker_rejects_dual_without_dest(scan_mod):
    with pytest.raises(ValueError, match="requires dest="):
        scan_mod._parse_marker("<!-- doc: dual -->\n# Title\n")


@pytest.mark.spec("DOCFRAME-002")
def test_marker_rejects_non_dual_with_dest(scan_mod):
    with pytest.raises(ValueError, match="must not have dest="):
        scan_mod._parse_marker("<!-- doc: repo-only dest=foo.md -->\n# Title\n")


@pytest.mark.spec("DOCFRAME-002")
def test_marker_rejects_multiple_markers(scan_mod):
    text = "<!-- doc: repo-only -->\n<!-- doc: repo-only -->\n# Title\n"
    with pytest.raises(ValueError, match="Multiple"):
        scan_mod._parse_marker(text)


@pytest.mark.spec("DOCFRAME-002")
def test_marker_rejects_same_line_duplicate_markers(scan_mod):
    text = "<!-- doc: repo-only --><!-- doc: repo-only -->\n# Title\n"
    with pytest.raises(ValueError, match="Multiple"):
        scan_mod._parse_marker(text)


@pytest.mark.spec("DOCFRAME-002")
def test_marker_rejects_unrecognised_class(scan_mod):
    with pytest.raises(ValueError, match="Unrecognised"):
        scan_mod._parse_marker("<!-- doc: duel dest=x.md -->\n# Title\n")


# ---------------------------------------------------------------------------
# DOCFRAME-002: additional happy paths and directory defaults
# ---------------------------------------------------------------------------


@pytest.mark.spec("DOCFRAME-002")
def test_marker_parses_docs_only_no_dest(scan_mod):
    result = scan_mod._parse_marker("<!-- doc: docs-only -->\n# Title\n")
    assert result == ("docs-only", None)


@pytest.mark.spec("DOCFRAME-002")
def test_classify_file_docs_src_is_docs_only(scan_mod, tmp_path):
    docs_src = tmp_path / "docs-src" / "guides"
    docs_src.mkdir(parents=True)
    md = docs_src / "my-guide.md"
    md.write_text("# My Guide\n\nContent.\n")
    klass, dest = scan_mod._classify_file(md, tmp_path)
    assert klass == "docs-only"
    assert dest is None


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


@pytest.mark.spec("DOCFRAME-002")
@pytest.mark.spec("DOCFRAME-003")
def test_scan_dual_files_skip_stems_not_yielded(scan_mod, tmp_path):
    rfcs_dir = tmp_path / "sdd" / "rfcs"
    rfcs_dir.mkdir(parents=True)
    template = rfcs_dir / "rfc-template.md"
    template.write_text("# RFC Template\n\nContent.\n")
    real_rfc = rfcs_dir / "rfc-0001-something.md"
    real_rfc.write_text("# RFC-0001: Something\n\nContent.\n")

    entries = list(scan_mod.scan_dual_files(tmp_path))
    sources = {e.source for e in entries}
    assert template.resolve() not in sources
    assert real_rfc.resolve() in sources


@pytest.mark.spec("DOCFRAME-001")
def test_scan_dual_files_skips_vcs_dirs(scan_mod, tmp_path):
    # .git/ is in _VCS_DIRS; excluded by both git ls-files and the rglob fallback.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    phantom = git_dir / "notes.md"
    phantom.write_text("<!-- doc: dual dest=phantom.md -->\n# Notes\n")

    entries = list(scan_mod.scan_dual_files(tmp_path))
    sources = {e.source for e in entries}
    assert phantom.resolve() not in sources


@pytest.mark.spec("DOCFRAME-002")
@pytest.mark.spec("G-01")
def test_classify_file_skip_stem_raises_G01(scan_mod, tmp_path):
    rfcs_dir = tmp_path / "sdd" / "rfcs"
    rfcs_dir.mkdir(parents=True)
    template = rfcs_dir / "rfc-template.md"
    template.write_text("# RFC Template\n\nContent.\n")
    with pytest.raises(ValueError, match="G-01"):
        scan_mod._classify_file(template, tmp_path)


@pytest.mark.spec("DOCFRAME-002")
def test_marker_dest_does_not_capture_comment_closer(scan_mod):
    result = scan_mod._parse_marker("<!-- doc: dual dest=explanation/design/authoring.md -->\n# Title\n")
    assert result == ("dual", "explanation/design/authoring.md")


@pytest.mark.spec("DOCFRAME-001")
@pytest.mark.spec("DOCFRAME-003")
def test_scan_dual_files_no_double_yield_for_sdd_with_explicit_marker(scan_mod, tmp_path):
    adrs_dir = tmp_path / "sdd" / "adrs"
    adrs_dir.mkdir(parents=True)
    adr = adrs_dir / "0001-test.md"
    adr.write_text("<!-- doc: dual dest=custom/path.md -->\n# ADR-0001: Test\n\nContent.\n")

    entries = list(scan_mod.scan_dual_files(tmp_path))
    adr_abs = adr.resolve()
    assert [e.source for e in entries].count(adr_abs) == 1
    assert next(e for e in entries if e.source == adr_abs).dest == "custom/path.md"


@pytest.mark.spec("DOCFRAME-001")
def test_scan_dual_files_malformed_marker_warns_and_skips(scan_mod, tmp_path):
    malformed = tmp_path / "BROKEN.md"
    malformed.write_text("<!-- doc: duel dest=typo.md -->\n# Broken\n")

    with pytest.warns(UserWarning, match="Malformed"):
        entries = list(scan_mod.scan_dual_files(tmp_path))
    assert malformed.resolve() not in {e.source for e in entries}
