"""Golden test for scripts/gen_graph_viz.py (ID-165).

Verifies that the committed graph_viz.html matches a fresh generate() call.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_graph_viz_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import gen_graph_viz

    return gen_graph_viz


@pytest.fixture(scope="module")
def viz_html(gen_graph_viz_module):
    """The generated page from the committed graph (the real 1.4 artifact)."""
    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    return gen_graph_viz_module.generate(graph)


@pytest.mark.os_sensitive
def test_graph_viz_html_is_up_to_date(gen_graph_viz_module):
    """Committed graph_viz.html must match a fresh generate() call.

    Fails if the script was modified but the output file was not regenerated.
    Run:  hatch run gen-graph-viz
    """
    committed = gen_graph_viz_module.OUT.read_bytes()
    committed_lf = committed.replace(b"\r\n", b"\n")

    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    fresh = gen_graph_viz_module.generate(graph)
    fresh_bytes = fresh.encode("utf-8")

    assert committed_lf == fresh_bytes, "graph_viz.html is out of date. Run:  hatch run gen-graph-viz"


def test_generate_raises_when_d3_vendor_missing(gen_graph_viz_module, monkeypatch, tmp_path):
    """generate() must raise FileNotFoundError when D3_VENDOR is absent."""
    monkeypatch.setattr(gen_graph_viz_module, "D3_VENDOR", tmp_path / "nonexistent.js")
    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    with pytest.raises(FileNotFoundError):
        gen_graph_viz_module.generate(graph)


def test_generate_raises_on_token_contamination(gen_graph_viz_module):
    """generate() must raise RuntimeError when a replacement value re-introduces a token.

    source_version == "__GRAPH_DATA__": re.sub fills the __VERSION__ slot with the
    string "__GRAPH_DATA__", which survives in the output (re.sub does not rescan
    replacement values). The post-substitution guard must catch this.
    """
    graph = {
        "source_version": "__GRAPH_DATA__",
        "schema_version": "1.1",
        "nodes": [],
        "edges": [],
    }
    with pytest.raises(RuntimeError, match="survived substitution"):
        gen_graph_viz_module.generate(graph)


@pytest.mark.os_sensitive
def test_d3_script_src_resolves_to_vendored_sibling(gen_graph_viz_module):
    """The emitted ``<script src>`` must resolve to the committed vendored D3 file.

    D3 is referenced (not inlined) as a sibling asset (ID-224), so the page has a
    hard runtime dependency on that file being served next to it. Resolve the
    emitted relative src against the page's committed location and assert it is the
    vendored ``D3_VENDOR`` — a rename of either the vendored file or the
    ``explanation/`` page dir would 404 the viz, and this fails the suite first.
    The ``mkdocs build --strict`` docs-gate separately proves the asset is copied
    into ``site/``.
    """
    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    html = gen_graph_viz_module.generate(graph)

    srcs = re.findall(r'<script\s+src="([^"]+)"></script>', html)
    assert len(srcs) == 1, f"expected exactly one external <script src>, found {srcs}"

    resolved = (gen_graph_viz_module.OUT.parent / srcs[0]).resolve()
    assert resolved == gen_graph_viz_module.D3_VENDOR.resolve(), (
        f"D3 <script src> {srcs[0]!r} resolves to {resolved}, not the vendored {gen_graph_viz_module.D3_VENDOR}"
    )
    assert resolved.exists(), f"referenced D3 asset is missing: {resolved}"


# ---------------------------------------------------------------------------
# ID-223: role-aware, explorable viz. These pin the wiring of each feature so a
# silent regression fails a targeted unit test, not only the byte-level golden.
# Behaviour (clicks, force layout, facet composition) is verified out-of-band in
# a headless browser; here we assert the generated page carries the machinery.
# ---------------------------------------------------------------------------


def test_repo_blob_base_single_sourced_from_pyproject(gen_graph_viz_module):
    """Deep-link base is read from pyproject [project.urls].Repository, not hardcoded."""
    base = gen_graph_viz_module._repo_blob_base()
    assert base.startswith("https://github.com/"), base
    assert base.endswith("/blob/master/"), base
    assert "remote-store" in base, base


def test_blob_base_injected_and_no_token_survives(gen_graph_viz_module, viz_html):
    """The page embeds the resolved blob base and leaves no __BLOB_BASE__ token."""
    base = gen_graph_viz_module._repo_blob_base()
    assert f'const BLOB_BASE = "{base}"' in viz_html
    assert "__BLOB_BASE__" not in viz_html


def test_role_aware_node_rendering(viz_html):
    """Class nodes are coloured by role (DGM-004); Store/AsyncStore stand out by URI."""
    assert "const ROLE_COLOR = {backend:" in viz_html
    for role in ("backend", "abc", "facade"):
        assert f"{role}:" in viz_html
    assert "function nodeColor(" in viz_html
    assert "function isStoreFacade(" in viz_html
    # Store/AsyncStore are distinguished by URI label, not a separate role (DGM-007).
    assert r"/\.(Async)?Store$/.test(n.id)" in viz_html
    assert ".node.store circle" in viz_html


def test_method_collapse_and_contains_clustering(viz_html):
    """Methods collapse into their class by default; contains drives clustering (DGM-008)."""
    assert "const expandedClasses" in viz_html
    assert "const classOfMethod" in viz_html
    assert "const methodsOfClass" in viz_html
    # collapse rule: a method is hidden unless its class is expanded
    assert "expandedClasses.has(c)" in viz_html
    # structural contains links cluster methods-in-class and classes-in-package
    assert "function computeActiveLinks(" in viz_html
    assert "Expand all" in viz_html
    assert "Collapse all" in viz_html


def test_gate_label_disambiguation(viz_html):
    """Gate labels are disambiguated as Class.method via gates+contains (DGM-008)."""
    assert "const reqLabel" in viz_html
    assert "gate_depth" in viz_html
    assert "(depth)" in viz_html


def test_detail_panel_deep_links(viz_html):
    """Node detail shows deep links to source, spec, and the docs page (DGM-009)."""
    assert "function deepLinks(" in viz_html
    assert "function docHref(" in viz_html
    for label in ("Source", "Spec", "Docs"):
        assert f"label:'{label}'" in viz_html
    # source/spec go to GitHub blob; docs page stays site-relative
    assert "BLOB_BASE+n.file" in viz_html
    assert "docHref(cls.doc)" in viz_html
    assert 'target="_blank"' in viz_html


def test_edge_detail_panel(viz_html):
    """Selecting an *edge* shows its metadata incl. mirror capability delta."""
    assert "function showEdgeDetail(" in viz_html
    assert "l.capability_delta" in viz_html
    assert "async only" in viz_html
    assert "sync only" in viz_html
    # edge endpoints are cross-references that select the endpoint node
    assert "function selectNodeById(" in viz_html
    assert 'class="xref"' in viz_html


def test_faceted_filter_controls(viz_html):
    """Composable facets: text search, node kind/role, edge kind, runtime, capability, dependency."""
    for control_id in (
        "search",
        "node-legend",
        "role-legend",
        "edge-legend",
        "runtime-legend",
        "cap-legend",
        "iso-toggle",
    ):
        assert f'id="{control_id}"' in viz_html, control_id
    for state in (
        "visibleNodeKinds",
        "visibleRoles",
        "visibleEdgeKinds",
        "visibleRuntimes",
        "selectedCaps",
        "searchQuery",
    ):
        assert state in viz_html, state
    # capability facet keeps a capability's gate/declare chain; dependency facet
    # isolates a directed up/down cone (not an undirected closure that leaks).
    assert "function capabilityKeep(" in viz_html
    assert "const walk=(forward)=>" in viz_html
