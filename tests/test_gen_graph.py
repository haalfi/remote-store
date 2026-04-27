"""Golden test for scripts/gen_graph.py (ID-159).

RFC-0012 determinism requirement: generate twice, assert byte-identical output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

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

    with open(ROOT / "pyproject.toml", "rb") as f:
        expected_version = tomllib.load(f)["project"]["version"]

    assert graph["schema_version"] == "1.1"
    assert graph["source_version"] == expected_version
    assert graph["snapshot"] == expected_version

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


def test_method_nodes_carry_introspection_fields(gen_graph_module):
    """RFC-0012 method node taxonomy: is_abstract, is_async, file, line (ID-164).

    is_abstract reflects whether the method body has @abstractmethod,
    not whether it gates an abstract operation in the underlying backend.
    Store.read_bytes is a concrete sync method, so all four flags are known.
    """
    graph = gen_graph_module.build_graph()
    node = next(
        (n for n in graph["nodes"] if n["id"] == "mtd:remote_store._store.Store.read_bytes"),
        None,
    )
    assert node is not None, "method node for Store.read_bytes not found"
    assert node["summary"] == "read_bytes"
    assert node["is_abstract"] is False
    assert node["is_async"] is False
    assert node["file"] == "src/remote_store/_store.py"
    assert isinstance(node["line"], int)
    assert node["line"] > 0

    # Every method node carries all five taxonomy fields with correct types
    method_nodes = [n for n in graph["nodes"] if n["kind"] == "method"]
    assert method_nodes, "no method nodes in graph"
    for n in method_nodes:
        for key in ("summary", "is_abstract", "is_async", "file", "line"):
            assert key in n, f"method node {n['id']!r} missing field {key!r}"
        assert isinstance(n["is_abstract"], bool), f"is_abstract not bool on {n['id']!r}"
        assert isinstance(n["is_async"], bool), f"is_async not bool on {n['id']!r}"
        assert isinstance(n["line"], int), f"line not int on {n['id']!r}"


def test_graph_json_is_up_to_date(gen_graph_module):
    """Committed graph.json must match a fresh build_graph() call.

    Fails if the script was modified but the output file was not regenerated.
    Run:  hatch run gen-graph
    """
    committed = (ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes()
    committed_lf = committed.replace(b"\r\n", b"\n")

    fresh = json.dumps(gen_graph_module.build_graph(), sort_keys=True, indent=2) + "\n"
    fresh_bytes = fresh.encode("utf-8")

    assert committed_lf == fresh_bytes, "graph.json is out of date. Run:  hatch run gen-graph"
