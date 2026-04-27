"""Golden test for scripts/gen_graph.py (ID-159).

RFC-0012 determinism requirement: generate twice, assert byte-identical output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_graph_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import gen_graph

    return gen_graph


def test_graph_deterministic_in_process(gen_graph_module):
    """Two successive in-process calls to build_graph() must produce byte-identical JSON.

    Guards against non-deterministic data structures (unsorted sets, etc.).
    Cross-run stability is anchored by the committed graph.json snapshot.
    """
    build_graph = gen_graph_module.build_graph

    first = json.dumps(build_graph(), sort_keys=True, indent=2) + "\n"
    second = json.dumps(build_graph(), sort_keys=True, indent=2) + "\n"

    assert first == second, "build_graph() is not deterministic"


def test_graph_schema(gen_graph_module):
    """graph.json must satisfy the RFC-0012 schema invariants."""
    graph = gen_graph_module.build_graph()

    assert graph["schema_version"] == "1.0"
    assert graph["snapshot"] == "unreleased"
    assert graph["source_version"] is None

    nodes = graph["nodes"]
    edges = graph["edges"]

    # Every node must have an 'id' and 'kind'
    node_ids = {n["id"] for n in nodes}
    for node in nodes:
        assert "id" in node, f"Node missing 'id': {node}"
        assert "kind" in node, f"Node missing 'kind': {node}"

    # Nodes must be sorted ascending by id
    node_id_list = [n["id"] for n in nodes]
    assert node_id_list == sorted(node_id_list), "nodes are not sorted by id"

    # Every edge must have 'kind', 'src', 'dst'
    for edge in edges:
        assert "kind" in edge, f"Edge missing 'kind': {edge}"
        assert "src" in edge, f"Edge missing 'src': {edge}"
        assert "dst" in edge, f"Edge missing 'dst': {edge}"

    # Edges must be sorted ascending by (kind, src, dst)
    edge_keys = [(e["kind"], e["src"], e["dst"]) for e in edges]
    assert edge_keys == sorted(edge_keys), "edges are not sorted by (kind, src, dst)"

    # All edge endpoints must reference known node ids (or cap:/req:/mtd: URIs in the graph)
    for edge in edges:
        assert edge["src"] in node_ids, f"Edge src not in nodes: {edge['src']}"
        assert edge["dst"] in node_ids, f"Edge dst not in nodes: {edge['dst']}"

    # Must have at least one node per expected kind
    kinds = {n["kind"] for n in nodes}
    assert "capability" in kinds
    assert "class" in kinds
    assert "extra" in kinds
    assert "method" in kinds
    assert "requirement" in kinds
    assert "package" in kinds

    # Must have the core edge kinds
    edge_kinds = {e["kind"] for e in edges}
    assert "declares" in edge_kinds
    assert "gates" in edge_kinds
    assert "inherits" in edge_kinds
    assert "of" in edge_kinds
    assert "enables" in edge_kinds
    assert "mirrors" in edge_kinds
