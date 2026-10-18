"""Tests for scripts/docs/scan.py:_load_sdd_kinds failure modes and shape.

The YAML-loader hoist (BK-171) replaced a hardcoded tuple with a runtime
config read. This file covers the failure modes the hoist introduced:
FileNotFoundError, missing required field (KeyError), and the empty-list
case, plus a positive-control that guards against shape regressions in
``docs-src/_path_rules.yml`` itself.

Spec: sdd/specs/047-docs-framework-tooling.md (DOCFRAME-008).
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
    import docs.scan as mod

    return mod


@pytest.mark.spec("DOCFRAME-008")
def test_load_sdd_kinds_positive(scan_mod):
    """Positive control: real _path_rules.yml loads all expected kinds."""
    kinds = scan_mod._load_sdd_kinds()
    slugs = {k.slug for k in kinds}
    assert slugs == {"adrs", "specs", "rfcs", "audits", "research"}
    assert len(kinds) == 5
    by_slug = {k.slug: k for k in kinds}
    assert by_slug["adrs"].status is True
    assert by_slug["rfcs"].status is True
    assert by_slug["specs"].status is False
    assert by_slug["audits"].glob == "audit-*.md"
    assert by_slug["research"].numbered is False


@pytest.mark.spec("DOCFRAME-008")
def test_load_sdd_kinds_filenotfound(scan_mod, tmp_path):
    """FileNotFoundError branch: missing file raises a friendly message."""
    missing = tmp_path / "no_such_dir" / "_path_rules.yml"
    with pytest.raises(FileNotFoundError, match="_path_rules.yml"):
        scan_mod._load_sdd_kinds(missing)


@pytest.mark.spec("DOCFRAME-008")
def test_load_sdd_kinds_missing_required_field(scan_mod, tmp_path):
    """Missing required field raises KeyError (documents the failure mode)."""
    bad = tmp_path / "_path_rules.yml"
    bad.write_text("sdd_kinds:\n  - source_dir: sdd/adrs\n    nav_label: ADRs\n", encoding="utf-8")
    with pytest.raises(KeyError, match="slug"):
        scan_mod._load_sdd_kinds(bad)


@pytest.mark.spec("DOCFRAME-008")
def test_load_sdd_kinds_empty_list_raises(scan_mod, tmp_path):
    """Empty sdd_kinds list raises ValueError (misconfiguration, not valid state)."""
    empty = tmp_path / "_path_rules.yml"
    empty.write_text("sdd_kinds: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sdd_kinds"):
        scan_mod._load_sdd_kinds(empty)


@pytest.mark.spec("DOCFRAME-010")
def test_load_sdd_kinds_rejects_a_constant_status(scan_mod, tmp_path):
    """`status: Accepted` is the pre-BUG-338 constant; a string is no longer a value."""
    bad = tmp_path / "_path_rules.yml"
    bad.write_text(
        "sdd_kinds:\n  - slug: rfcs\n    source_dir: sdd/rfcs\n    nav_label: RFCs\n    status: Proposed\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rfcs.*status.*true or false"):
        scan_mod._load_sdd_kinds(bad)


@pytest.mark.spec("DOCFRAME-010")
def test_load_sdd_kinds_rejects_status_kind_without_a_parser(scan_mod, tmp_path):
    """A status column on a kind no parser reads would render `—` in every row."""
    bad = tmp_path / "_path_rules.yml"
    bad.write_text(
        "sdd_kinds:\n  - slug: audits\n    source_dir: sdd/audits\n    nav_label: Audits\n    status: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="audits.*no status parser"):
        scan_mod._load_sdd_kinds(bad)
