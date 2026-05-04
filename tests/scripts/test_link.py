"""Tests for scripts/docs/link.py — build_source_map coverage.

Spec: sdd/specs/047-docs-framework-tooling.md (DOCFRAME-008).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def link_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import docs.link as mod

    return mod


@pytest.fixture(scope="module")
def scan_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import docs.scan as mod

    return mod


@pytest.mark.spec("DOCFRAME-008")
def test_build_source_map_includes_sdd_kind_dirs(link_mod, scan_mod, tmp_path):
    """Kind source directories map to their generated index pages.

    Docs-src links that point at a kind directory (e.g. ``../../sdd/adrs``) get
    rewritten to the in-site index URL rather than falling through to GitHub.
    """
    kind = scan_mod.SddKind(slug="adrs", source_dir="sdd/adrs", nav_label="ADRs")
    kind_dir = tmp_path / "sdd" / "adrs"
    kind_dir.mkdir(parents=True)
    src_file = kind_dir / "0001-foo.md"
    src_file.write_text("# ADR-0001\n")
    entry = scan_mod.SddEntry(number="0001", slug="0001-foo", title="Foo", source=src_file, kind=kind)

    result = link_mod.build_source_map(
        tmp_path,
        sdd_entries={"adrs": [entry]},
        dual_entries=[],
    )

    assert kind_dir.resolve() in result
    assert result[kind_dir.resolve()] == "explanation/design/adrs/index.md"


@pytest.mark.spec("DOCFRAME-008")
def test_build_source_map_includes_example_sources(link_mod, scan_mod, tmp_path):
    """Example .py sources map to their wrapper page at tutorial/examples/<slug>.md."""
    py_file = tmp_path / "quickstart.py"
    py_file.write_text('"""Quickstart -- minimal example."""\n')
    entry = scan_mod.ExampleEntry(
        rel_key="getting_started/quickstart.py",
        subdir="getting_started",
        stem="quickstart",
        slug="quickstart",
        title="Quickstart",
        description="minimal example",
        source=py_file,
    )

    result = link_mod.build_source_map(
        tmp_path,
        sdd_entries={},
        dual_entries=[],
        example_entries=[entry],
    )

    assert py_file.resolve() in result
    assert result[py_file.resolve()] == "tutorial/examples/quickstart.md"
