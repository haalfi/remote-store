"""Tests for scripts/check_sdd_index.py — the sdd index-shape gate.

Both rules guard a silent failure, so each is tested by seeding the defect and
asserting the gate names the offending file (DRIFT-RULES Rule 2), not merely
that it fails:

R1  a document of a dated kind with no parseable ``**Date:**`` header
R2  a kind's ``_index.tmpl`` header declaring fewer columns than a row emits

The gate exists because neither defect can reach pytest on the diff that
introduces it: ``ci.yml``'s ``CODE_PAT`` has no ``^sdd/``, so a PR adding only
a research doc skips every test job. These tests therefore prove the gate
works; ``docs-gate`` is what makes it run.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gate():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_sdd_index as mod

    return mod


@pytest.fixture
def tree(gate, tmp_path):
    """A minimal repo: the real templates, plus one well-formed research doc."""
    for kind in gate.SDD_KINDS:
        dest = tmp_path / "docs-src" / "explanation" / "design" / kind.slug
        dest.mkdir(parents=True)
        shutil.copy(ROOT / "docs-src" / "explanation" / "design" / kind.slug / "_index.tmpl", dest / "_index.tmpl")
        (tmp_path / kind.source_dir).mkdir(parents=True, exist_ok=True)
    (tmp_path / "sdd" / "research" / "research-ok.md").write_text(
        "# Research: Ok\n\n**Date:** 2026-05-01\n", encoding="utf-8"
    )
    return tmp_path


def test_clean_tree_passes(gate, tree):
    """Positive control: without a seeded defect the gate must stay quiet."""
    assert gate.check(tree) == []


def test_live_repo_passes(gate):
    """Positive control against the real tree — the shape the gate ships guarding."""
    assert gate.check(ROOT) == []


# ---------------------------------------------------------------------------
# R1: dated kinds must carry a header date
# ---------------------------------------------------------------------------


def test_r1_flags_undated_doc_of_a_dated_kind(gate, tree):
    (tree / "sdd" / "research" / "research-undated.md").write_text("# Research: U\n\nNo date.\n", encoding="utf-8")
    errors = gate.check(tree)
    assert len(errors) == 1
    assert errors[0].startswith("R1 sdd/research/research-undated.md:")
    assert "**Date:** YYYY-MM-DD" in errors[0]


def test_r1_flags_unparseable_date_format(gate, tree):
    """A header date the renderer cannot read is the same defect as none at all."""
    (tree / "sdd" / "research" / "research-loose.md").write_text(
        "# Research: L\n\n**Date:** March 2026\n", encoding="utf-8"
    )
    assert [e for e in gate.check(tree) if "research-loose" in e]


def test_r1_ignores_undated_kinds(gate, tree):
    """ADRs carry no `dated:` flag, so a dateless ADR is not a violation."""
    (tree / "sdd" / "adrs" / "0001-test.md").write_text("# ADR-0001: Test\n\nNo date.\n", encoding="utf-8")
    assert gate.check(tree) == []


# ---------------------------------------------------------------------------
# R2: template header arity must match the emitted row
# ---------------------------------------------------------------------------


def test_r2_flags_narrow_header_for_dated_kind(gate, tree):
    """The `dated: true`-without-widening-the-template case, which renders green."""
    tmpl = tree / "docs-src" / "explanation" / "design" / "research" / "_index.tmpl"
    tmpl.write_text("| Topic | Document |\n|---|---|\n{{ research_rows }}\n", encoding="utf-8")
    errors = [e for e in gate.check(tree) if e.startswith("R2")]
    assert len(errors) == 1
    assert "header has 2 column(s), rows emit 3" in errors[0]
    assert "flags: dated" in errors[0]
    assert "docs-src/explanation/design/research/_index.tmpl" in errors[0]


def test_r2_flags_status_kind_mismatch(gate, tree):
    """`status:` carries the identical coupling; the gate covers it too."""
    tmpl = tree / "docs-src" / "explanation" / "design" / "adrs" / "_index.tmpl"
    tmpl.write_text("| # | ADR |\n|---|---|\n{{ adr_rows }}\n", encoding="utf-8")
    errors = [e for e in gate.check(tree) if e.startswith("R2")]
    assert len(errors) == 1
    assert "header has 2 column(s), rows emit 3" in errors[0]
    assert "flags: status" in errors[0]


def test_r2_flags_missing_template(gate, tree):
    (tree / "docs-src" / "explanation" / "design" / "rfcs" / "_index.tmpl").unlink()
    errors = [e for e in gate.check(tree) if e.startswith("R2")]
    assert len(errors) == 1
    assert "missing index template" in errors[0]


def test_r2_flags_template_without_a_table(gate, tree):
    tmpl = tree / "docs-src" / "explanation" / "design" / "specs" / "_index.tmpl"
    tmpl.write_text("# Specs\n\nProse only.\n", encoding="utf-8")
    errors = [e for e in gate.check(tree) if e.startswith("R2")]
    assert len(errors) == 1
    assert "no table header row found" in errors[0]


def test_expected_columns_counts_both_flags(gate):
    """The arity formula the docstring states: 2 + bool(status) + bool(dated)."""
    from docs.scan import SddKind

    assert gate._expected_columns(SddKind("k", "sdd/k", "K")) == 2
    assert gate._expected_columns(SddKind("k", "sdd/k", "K", status="Accepted")) == 3
    assert gate._expected_columns(SddKind("k", "sdd/k", "K", dated=True)) == 3
    assert gate._expected_columns(SddKind("k", "sdd/k", "K", status="Accepted", dated=True)) == 4


def test_main_reports_and_exits_nonzero_on_violation(gate, tree, monkeypatch, capsys):
    (tree / "sdd" / "research" / "research-undated.md").write_text("# Research: U\n\nNo date.\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tree)
    assert gate.main() == 1
    assert "research-undated" in capsys.readouterr().out


def test_main_exits_zero_on_clean_tree(gate, tree, monkeypatch, capsys):
    monkeypatch.setattr(gate, "ROOT", tree)
    assert gate.main() == 0
    assert "research" in capsys.readouterr().out
