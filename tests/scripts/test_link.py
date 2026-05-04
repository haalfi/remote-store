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
def test_build_source_map_kind_dir_unconditional(link_mod, tmp_path):
    """Kind-dir mapping is added even when the kind has no entries.

    Regression guard for the entries-gated ``if entries:`` pattern: a kind
    directory that exists but contains no matching files must still resolve
    to its generated index page rather than falling through to GitHub.
    """
    kind_dir = (tmp_path / "sdd" / "adrs").resolve()
    result = link_mod.build_source_map(
        tmp_path,
        sdd_entries={"adrs": []},
        dual_entries=[],
    )
    assert kind_dir in result
    assert result[kind_dir] == "explanation/design/adrs/index.md"


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


@pytest.mark.spec("DOCFRAME-008")
def test_build_source_map_includes_docs_src_images(link_mod, tmp_path):
    """Image assets under docs-src/ are included in the source map.

    The LinkResolver hook rewrites every ``](…)`` token, including image
    syntax ``![alt](path)``. Image files must appear in the source map so
    they resolve to their in-site path rather than falling back to a GitHub
    blob URL, which renders as a broken image.
    """
    img_dir = tmp_path / "docs-src" / "img" / "benchmarks"
    img_dir.mkdir(parents=True)
    svg_file = img_dir / "overhead.svg"
    svg_file.write_text("<svg></svg>")

    result = link_mod.build_source_map(
        tmp_path,
        sdd_entries={},
        dual_entries=[],
    )

    assert svg_file.resolve() in result
    assert result[svg_file.resolve()] == "img/benchmarks/overhead.svg"


@pytest.mark.spec("DOCFRAME-008")
def test_link_resolver_rewrites_image_syntax_to_in_site_path(link_mod, tmp_path):
    """Image syntax rewrites to an in-site relative path, not a GitHub blob URL.

    The LinkResolver processes every ``](…)`` token including ``![alt](path)``.
    Without image types in the source map the rewriter falls through to the
    GitHub blob URL fallback; this test exercises that exact code path so the
    bug cannot silently re-emerge from a future change to ``_LINK_RE`` or the
    source map assembly.
    """
    docs_src = tmp_path / "docs-src"
    img_dir = docs_src / "img" / "benchmarks"
    img_dir.mkdir(parents=True)
    (img_dir / "overhead.svg").write_text("<svg></svg>")
    src_file = docs_src / "explanation" / "performance.md"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("")

    source_map = link_mod.build_source_map(tmp_path, sdd_entries={}, dual_entries=[])
    resolver = link_mod.LinkResolver(
        source_map=source_map,
        repo_root=tmp_path,
        github_blob_url="https://github.com/owner/repo/blob/master",
    )

    result = resolver.rewrite(
        "![Abstraction overhead by backend](../img/benchmarks/overhead.svg)",
        source=src_file,
        dest="explanation/performance.md",
    )

    assert result == "![Abstraction overhead by backend](../img/benchmarks/overhead.svg)"


@pytest.mark.spec("DOCFRAME-008")
def test_build_source_map_includes_docs_src_html(link_mod, tmp_path):
    """HTML files under docs-src/ are included in the source map.

    Regression guard: graph_viz.html was rewritten to a GitHub blob URL after
    BK-171 because only *.md files were indexed. Non-Markdown static assets
    served from docs-src/ must resolve to their in-site path.
    """
    docs_src = tmp_path / "docs-src" / "explanation"
    docs_src.mkdir(parents=True)
    html_file = docs_src / "graph_viz.html"
    html_file.write_text("<html></html>")

    result = link_mod.build_source_map(
        tmp_path,
        sdd_entries={},
        dual_entries=[],
    )

    assert html_file.resolve() in result
    assert result[html_file.resolve()] == "explanation/graph_viz.html"
