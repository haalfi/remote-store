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

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_graph_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import gen_graph

    return gen_graph


@pytest.mark.spec("DGM-012")
def test_graph_deterministic_in_process(gen_graph_module):
    """Two successive in-process calls to build_graph() must produce byte-identical JSON.

    Guards against non-deterministic data structures (unsorted sets, etc.).
    Cross-run stability is anchored by the committed graph.json snapshot.
    """
    build_graph = gen_graph_module.build_graph

    first = json.dumps(build_graph(), sort_keys=True, indent=2) + "\n"
    second = json.dumps(build_graph(), sort_keys=True, indent=2) + "\n"

    assert first == second, "build_graph() is not deterministic"


@pytest.mark.spec("DGM-001,DGM-002,DGM-003,DGM-010")
def test_graph_schema(gen_graph_module):
    """graph.json must satisfy the RFC-0012 schema invariants."""
    graph = gen_graph_module.build_graph()

    with open(ROOT / "pyproject.toml", "rb") as f:
        expected_version = tomllib.load(f)["project"]["version"]

    assert graph["schema_version"] == "1.4"
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

    # ID-224: null/derivable keys are not emitted. ``condition`` is omitted when
    # unconditional (absent == null); a non-null value is reserved for future
    # conditional declares (ID-140, schema 1.3). The key must never be present-and-null.
    for edge in edges:
        assert "condition" not in edge or edge["condition"] is not None, f"Edge carries a null 'condition': {edge}"

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
    assert "contains" in edge_kinds


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
        assert isinstance(n["file"], str), f"file not str on {n['id']!r}"
        assert n["file"], f"file is empty on {n['id']!r}"


def test_get_folder_info_dual_gate(gen_graph_module):
    """get_folder_info has two runtime gates: METADATA (max_depth=None) and LIST (depth-limited).

    The generator special-cases this method to emit both req: nodes.
    Asserts that both gates are present so a future refactor cannot silently drop one.
    """
    graph = gen_graph_module.build_graph()
    gfi_mtd = "mtd:remote_store._store.Store.get_folder_info"

    gates_edges = [e for e in graph["edges"] if e["kind"] == "gates" and e["dst"] == gfi_mtd]
    assert len(gates_edges) == 2, f"expected 2 gates edges for get_folder_info, got {len(gates_edges)}"
    sources = {e["src"] for e in gates_edges}
    assert sources == {
        "req:remote_store._store.Store.get_folder_info.gate",
        "req:remote_store._store.Store.get_folder_info.gate_depth",
    }

    of_depth = [
        e
        for e in graph["edges"]
        if e["kind"] == "of" and e["src"] == "req:remote_store._store.Store.get_folder_info.gate_depth"
    ]
    assert of_depth == [
        {
            "dst": "cap:LIST",
            "index": 0,
            "kind": "of",
            "src": "req:remote_store._store.Store.get_folder_info.gate_depth",
        }
    ]


def test_mirrors_edge_carries_capability_delta(gen_graph_module):
    """ID-162: mirrors edges must report async-only / sync-only capability differences.

    AsyncMemoryBackend declares LAZY_READ; MemoryBackend does not. The delta
    lets graph consumers present accurate sync/async asymmetries instead of
    treating peers as equivalent.
    """
    graph = gen_graph_module.build_graph()
    async_uri = "cls:remote_store.aio.backends._memory.AsyncMemoryBackend"
    sync_uri = "cls:remote_store.backends._memory.MemoryBackend"

    edge = next(
        (e for e in graph["edges"] if e["kind"] == "mirrors" and {e["src"], e["dst"]} == {async_uri, sync_uri}),
        None,
    )
    assert edge is not None, "expected a mirrors edge between AsyncMemoryBackend and MemoryBackend"
    assert "capability_delta" in edge, f"mirrors edge missing capability_delta: {edge}"

    delta = edge["capability_delta"]
    assert set(delta.keys()) == {"async_only", "sync_only"}
    assert delta["async_only"] == ["LAZY_READ"]
    assert delta["sync_only"] == []

    # Symmetric peers (no capability difference) must report empty lists, not
    # be omitted. Pinning the AsyncAzureBackend pair guards against accidental
    # capability drift on either side.
    async_azure = "cls:remote_store.aio.backends._azure.AsyncAzureBackend"
    sync_azure = "cls:remote_store.backends._azure.AzureBackend"
    azure_edge = next(
        (e for e in graph["edges"] if e["kind"] == "mirrors" and {e["src"], e["dst"]} == {async_azure, sync_azure}),
        None,
    )
    assert azure_edge is not None, "expected a mirrors edge between AsyncAzureBackend and AzureBackend"
    assert azure_edge["capability_delta"] == {"async_only": [], "sync_only": []}

    # Every mirrors edge must carry a well-formed delta with sorted lists.
    for mirror_edge in (e for e in graph["edges"] if e["kind"] == "mirrors"):
        d = mirror_edge.get("capability_delta")
        assert isinstance(d, dict), f"mirrors edge missing capability_delta dict: {mirror_edge}"
        assert set(d.keys()) == {"async_only", "sync_only"}
        for key in ("async_only", "sync_only"):
            assert isinstance(d[key], list)
            assert all(isinstance(x, str) for x in d[key])
            assert d[key] == sorted(d[key]), f"{key} not sorted in {mirror_edge}"


def test_enables_edge_resolves_re_exported_subpackage_class(gen_graph_module):
    """A backend re-exported from a deeper sub-package keeps its enables edge.

    ``aio/backends/__init__.py`` imports ``GraphBackend`` from the ``_graph``
    *package* (``from ...aio.backends._graph import GraphBackend``), so the
    import-derived qname is ``..._graph.GraphBackend`` while the canonical
    griffe node is ``..._graph.backend.GraphBackend``. The extra→backend join
    must resolve that mismatch, otherwise the ``xtr:graph`` extra is silently
    orphaned (node present, no enables edge) and Graph drops out of the
    generated FEATURES tables.
    """
    graph = gen_graph_module.build_graph()
    graph_uri = "cls:remote_store.aio.backends._graph.backend.GraphBackend"

    # The node and extra both exist.
    node_ids = {n["id"] for n in graph["nodes"]}
    assert graph_uri in node_ids
    assert "xtr:graph" in node_ids

    # The enables edge connecting them must exist.
    enables = [e for e in graph["edges"] if e["kind"] == "enables" and e["dst"] == graph_uri]
    assert enables == [{"kind": "enables", "src": "xtr:graph", "dst": graph_uri}], (
        f"xtr:graph → GraphBackend enables edge missing or malformed: {enables}"
    )

    # No extra node should be left without any enables edge (orphan guard).
    enabled_extras = {e["src"] for e in graph["edges"] if e["kind"] == "enables"}
    extra_nodes = {n["id"] for n in graph["nodes"] if n["kind"] == "extra"}
    assert extra_nodes <= enabled_extras, f"orphaned extra nodes: {sorted(extra_nodes - enabled_extras)}"


@pytest.mark.spec("BE-027")
def test_backend_gating_keys_match_backend_members(gen_graph_module):
    """Every key in _BACKEND_GATING must be a real member of the Backend class.

    Guards against stale entries after a Backend method is renamed or removed.
    Without this test the dict lives far from the class it describes, so a
    rename would only surface at the next ``gen-graph-check`` CI run.
    """
    import griffe

    sys.path.insert(0, str(ROOT / "src"))
    pkg = griffe.load("remote_store")
    backend_members = set(pkg["_backend"]["Backend"].members)

    for method_name in gen_graph_module._BACKEND_GATING:
        assert method_name in backend_members, (
            f"_BACKEND_GATING key {method_name!r} not found in Backend.members — "
            "update _BACKEND_GATING in scripts/gen_graph.py"
        )


def test_store_gating_keys_match_store_members(gen_graph_module):
    """Every key in Store._GATING must be a real member of the Store class.

    Sync sibling of ``test_backend_gating_keys_match_backend_members`` and
    ``test_async_store_gating_keys_match_async_store_members``. The runtime
    drift guard in build_graph() catches the same kind of bug, but a unit
    test fails earlier and closer to where the dict is defined.
    """
    import griffe

    from remote_store._store import _GATING as STORE_GATING

    sys.path.insert(0, str(ROOT / "src"))
    pkg = griffe.load("remote_store")
    store_members = set(pkg["_store"]["Store"].members)

    for method_name in STORE_GATING:
        assert method_name in store_members, (
            f"_GATING key {method_name!r} not found in Store.members — update _GATING in src/remote_store/_store.py"
        )


def test_async_store_gating_keys_match_async_store_members(gen_graph_module):
    """Every key in AsyncStore._GATING must be a real member of the AsyncStore class.

    Mirrors ``test_backend_gating_keys_match_backend_members``. Guards
    against stale entries after an AsyncStore method is renamed or removed.
    """
    import griffe

    from remote_store.aio._async_store import _GATING as ASYNC_GATING

    sys.path.insert(0, str(ROOT / "src"))
    pkg = griffe.load("remote_store")
    async_store_members = set(pkg["aio"]["_async_store"]["AsyncStore"].members)

    for method_name in ASYNC_GATING:
        assert method_name in async_store_members, (
            f"_GATING key {method_name!r} not found in AsyncStore.members — "
            "update _GATING in src/remote_store/aio/_async_store.py"
        )


@pytest.mark.spec("ASYNC-045a")
def test_async_backend_gating_keys_match_async_backend_members(gen_graph_module):
    """Every key in _ASYNC_BACKEND_GATING must be a real member of AsyncBackend.

    Async sibling of ``test_backend_gating_keys_match_backend_members`` (ID-172).
    Guards against stale entries after an AsyncBackend method is renamed or
    removed; the dict lives in gen_graph.py (static-extraction only), so without
    this test a rename would only surface at the next ``gen-graph-check`` run.
    """
    import griffe

    sys.path.insert(0, str(ROOT / "src"))
    pkg = griffe.load("remote_store")
    async_backend_members = set(pkg["aio"]["_async_backend"]["AsyncBackend"].members)

    for method_name in gen_graph_module._ASYNC_BACKEND_GATING:
        assert method_name in async_backend_members, (
            f"_ASYNC_BACKEND_GATING key {method_name!r} not found in AsyncBackend.members — "
            "update _ASYNC_BACKEND_GATING in scripts/gen_graph.py"
        )


def test_async_backend_gating_mirrors_backend_minus_async_gaps(gen_graph_module):
    """_ASYNC_BACKEND_GATING is the sync map minus methods AsyncBackend lacks.

    AsyncBackend has no ``read_seekable`` / ``open_atomic`` (no async
    equivalents); every other entry must agree with _BACKEND_GATING so the two
    ABCs cannot drift to different capability requirements for the same method.
    """
    sync = gen_graph_module._BACKEND_GATING
    async_ = gen_graph_module._ASYNC_BACKEND_GATING

    assert set(sync) - set(async_) == {"read_seekable", "open_atomic"}
    for method_name, cap in async_.items():
        assert sync[method_name] == cap, f"{method_name}: async gate {cap!r} != sync gate {sync[method_name]!r}"


def test_async_store_method_nodes_emitted(gen_graph_module):
    """gen_graph.py must emit method/req/gates/of edges for every AsyncStore _GATING entry.

    Sibling of ``test_method_nodes_carry_introspection_fields`` (which
    covers the generic node shape) — this test pins the existence of the
    async-method nodes and one representative is_async=True example.
    """
    from remote_store.aio._async_store import _GATING as ASYNC_GATING

    graph = gen_graph_module.build_graph()
    node_ids = {n["id"] for n in graph["nodes"]}

    for method_name in ASYNC_GATING:
        mtd_uri = f"mtd:remote_store.aio._async_store.AsyncStore.{method_name}"
        req_uri = f"req:remote_store.aio._async_store.AsyncStore.{method_name}.gate"
        assert mtd_uri in node_ids, f"missing async method node {mtd_uri!r}"
        assert req_uri in node_ids, f"missing async req node {req_uri!r}"

    # read_bytes is a genuine `async def` -> is_async must be True.
    read_bytes_node = next(
        n for n in graph["nodes"] if n["id"] == "mtd:remote_store.aio._async_store.AsyncStore.read_bytes"
    )
    assert read_bytes_node["is_async"] is True
    assert read_bytes_node["summary"] == "read_bytes"
    assert read_bytes_node["file"] == "src/remote_store/aio/_async_store.py"


def test_async_backend_method_nodes_emitted(gen_graph_module):
    """gen_graph.py must emit method/req/gates/of edges for every _ASYNC_BACKEND_GATING entry.

    Async sibling of ``test_async_store_method_nodes_emitted`` (ID-172). Pins
    the existence of the AsyncBackend gate nodes and one representative
    is_async=True example.
    """
    graph = gen_graph_module.build_graph()
    node_ids = {n["id"] for n in graph["nodes"]}

    for method_name in gen_graph_module._ASYNC_BACKEND_GATING:
        mtd_uri = f"mtd:remote_store.aio._async_backend.AsyncBackend.{method_name}"
        req_uri = f"req:remote_store.aio._async_backend.AsyncBackend.{method_name}.gate"
        assert mtd_uri in node_ids, f"missing async backend method node {mtd_uri!r}"
        assert req_uri in node_ids, f"missing async backend req node {req_uri!r}"

    # read is an `async def` abstractmethod -> is_async must be True.
    read_node = next(n for n in graph["nodes"] if n["id"] == "mtd:remote_store.aio._async_backend.AsyncBackend.read")
    assert read_node["is_async"] is True
    assert read_node["summary"] == "read"
    assert read_node["file"] == "src/remote_store/aio/_async_backend.py"


def test_async_backend_has_no_dual_gate_for_get_folder_info(gen_graph_module):
    """AsyncBackend mirrors sync Backend: get_folder_info gates on METADATA only.

    Unlike Store/AsyncStore (which dual-gate on LIST when ``max_depth`` is set),
    the Backend ABCs carry a single METADATA gate. This pins the symmetry so a
    future refactor cannot silently add an async-only dual gate.
    """
    graph = gen_graph_module.build_graph()
    gfi_mtd = "mtd:remote_store.aio._async_backend.AsyncBackend.get_folder_info"

    gates_edges = [e for e in graph["edges"] if e["kind"] == "gates" and e["dst"] == gfi_mtd]
    assert len(gates_edges) == 1, f"expected 1 gates edge for AsyncBackend.get_folder_info, got {len(gates_edges)}"


def test_async_store_get_folder_info_dual_gate(gen_graph_module):
    """AsyncStore.get_folder_info mirrors Store: METADATA (max_depth=None) and LIST (depth-limited).

    Async sibling of ``test_get_folder_info_dual_gate``. Asserts both
    req: nodes exist so a future refactor cannot silently drop one.
    """
    graph = gen_graph_module.build_graph()
    gfi_mtd = "mtd:remote_store.aio._async_store.AsyncStore.get_folder_info"

    gates_edges = [e for e in graph["edges"] if e["kind"] == "gates" and e["dst"] == gfi_mtd]
    assert len(gates_edges) == 2, f"expected 2 gates edges for AsyncStore.get_folder_info, got {len(gates_edges)}"
    sources = {e["src"] for e in gates_edges}
    assert sources == {
        "req:remote_store.aio._async_store.AsyncStore.get_folder_info.gate",
        "req:remote_store.aio._async_store.AsyncStore.get_folder_info.gate_depth",
    }

    of_depth = [
        e
        for e in graph["edges"]
        if e["kind"] == "of" and e["src"] == "req:remote_store.aio._async_store.AsyncStore.get_folder_info.gate_depth"
    ]
    assert of_depth == [
        {
            "dst": "cap:LIST",
            "index": 0,
            "kind": "of",
            "src": "req:remote_store.aio._async_store.AsyncStore.get_folder_info.gate_depth",
        }
    ]


_ABC_URIS = {
    "cls:remote_store._backend.Backend",
    "cls:remote_store.aio._async_backend.AsyncBackend",
}
_FACADE_URIS = {
    "cls:remote_store._store.Store",
    "cls:remote_store.aio._async_store.AsyncStore",
    "cls:remote_store.aio._sync_adapter.SyncBackendAdapter",
}


@pytest.mark.spec("DGM-004")
def test_abc_classes_have_abc_role(gen_graph_module):
    """DGM-004: Backend/AsyncBackend are role 'abc', not 'backend'.

    Both ABCs carry a value-less ``CAPABILITIES: ClassVar`` annotation, so a
    Griffe member-name check misclassifies them as backends; the generator must
    resolve the runtime value (None) to classify them as ABCs.
    """
    graph = gen_graph_module.build_graph()
    by_id = {n["id"]: n for n in graph["nodes"]}
    for uri in _ABC_URIS:
        assert by_id[uri]["role"] == "abc", f"{uri} should be role 'abc', got {by_id[uri]['role']!r}"


@pytest.mark.spec("DGM-004")
def test_backend_role_is_concrete_backends_only(gen_graph_module):
    """DGM-004: role='backend' selects only concrete backends — no ABCs, no facades.

    This is the precondition ID-222 relies on for its backend capability table.
    """
    graph = gen_graph_module.build_graph()
    backend_uris = {n["id"] for n in graph["nodes"] if n["kind"] == "class" and n["role"] == "backend"}

    assert _ABC_URIS.isdisjoint(backend_uris), "an ABC leaked into role='backend'"
    assert _FACADE_URIS.isdisjoint(backend_uris), "a facade leaked into role='backend'"
    # A representative concrete backend is classified as such.
    assert "cls:remote_store.backends._s3.S3Backend" in backend_uris


@pytest.mark.spec("DGM-005")
def test_inherits_reaches_backend_through_private_base(gen_graph_module):
    """DGM-005: backends behind a private base still emit inherits → Backend.

    S3Backend/S3PyArrowBackend (via _S3Base) and SQLBlobBackend/SQLQueryBackend
    (via _SQLAlchemyBaseBackend) reach the sync Backend ABC through the MRO walk,
    even though _S3Base / _SQLAlchemyBaseBackend are not themselves graph nodes.
    """
    graph = gen_graph_module.build_graph()
    backend_abc = "cls:remote_store._backend.Backend"
    inherits = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "inherits"}

    for cls in (
        "cls:remote_store.backends._s3.S3Backend",
        "cls:remote_store.backends._s3_pyarrow.S3PyArrowBackend",
        "cls:remote_store.backends._sqlalchemy.SQLBlobBackend",
        "cls:remote_store.backends._sqlalchemy.SQLQueryBackend",
    ):
        assert (cls, backend_abc) in inherits, f"{cls} must inherit {backend_abc} via the MRO walk"

    # Each class emits at most one inherits edge (nearest ancestor only).
    srcs = [e["src"] for e in graph["edges"] if e["kind"] == "inherits"]
    assert len(srcs) == len(set(srcs)), "a class emitted more than one inherits edge"


@pytest.mark.spec("DGM-006")
def test_facade_declares_suppressed(gen_graph_module):
    """DGM-006: no declares edge originates from a facade-role class.

    SyncBackendAdapter declares the universal capability set at runtime (it
    forwards to whatever backend it wraps); emitting that as 14 declares edges
    made it look like a backend that natively supports everything.
    """
    graph = gen_graph_module.build_graph()
    facade_uris = {n["id"] for n in graph["nodes"] if n["kind"] == "class" and n["role"] == "facade"}
    assert facade_uris == _FACADE_URIS

    declares_srcs = {e["src"] for e in graph["edges"] if e["kind"] == "declares"}
    assert declares_srcs.isdisjoint(facade_uris), "a facade emitted declares edges"
    # SyncBackendAdapter keeps its inherits edge to AsyncBackend — suppression is
    # declares-only, not a wholesale removal from the hierarchy.
    inherits = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "inherits"}
    assert (
        "cls:remote_store.aio._sync_adapter.SyncBackendAdapter",
        "cls:remote_store.aio._async_backend.AsyncBackend",
    ) in inherits


@pytest.mark.spec("DGM-007")
def test_store_facade_nodes_present(gen_graph_module):
    """DGM-007: Store/AsyncStore facade nodes exist so no method node is orphaned."""
    graph = gen_graph_module.build_graph()
    by_id = {n["id"]: n for n in graph["nodes"]}

    for uri in ("cls:remote_store._store.Store", "cls:remote_store.aio._async_store.AsyncStore"):
        assert uri in by_id, f"missing facade class node {uri}"
        assert by_id[uri]["role"] == "facade"

    # Every method node's containing class node is present (orphan guard).
    class_uris = {n["id"] for n in graph["nodes"] if n["kind"] == "class"}
    for n in graph["nodes"]:
        if n["kind"] == "method":
            cls_uri = f"cls:{n['id'].removeprefix('mtd:').rsplit('.', 1)[0]}"
            assert cls_uri in class_uris, f"orphaned method node {n['id']!r}: no class node {cls_uri}"


@pytest.mark.spec("DGM-008")
def test_contains_class_to_method(gen_graph_module):
    """DGM-008: every method node is contained by exactly its URI-derived class."""
    graph = gen_graph_module.build_graph()
    contains = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "contains"}

    for n in graph["nodes"]:
        if n["kind"] == "method":
            cls_uri = f"cls:{n['id'].removeprefix('mtd:').rsplit('.', 1)[0]}"
            assert (cls_uri, n["id"]) in contains, f"method {n['id']!r} not contained by {cls_uri}"

    # Requirement nodes are gate groups, not containment members.
    req_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "requirement"}
    contained = {dst for _, dst in contains}
    assert req_ids.isdisjoint(contained), "a requirement node was placed in the containment tree"


@pytest.mark.spec("DGM-008")
def test_contains_package_to_class(gen_graph_module):
    """DGM-008: every class node is contained by its runtime package."""
    graph = gen_graph_module.build_graph()
    contains = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "contains"}

    for n in graph["nodes"]:
        if n["kind"] == "class":
            pkg_id = "pkg:remote_store.aio" if n["runtime"] == "async" else "pkg:remote_store"
            assert (pkg_id, n["id"]) in contains, f"class {n['id']!r} not contained by {pkg_id}"


@pytest.mark.spec("DGM-009")
def test_class_nodes_carry_link_metadata(gen_graph_module):
    """DGM-009: every abc/backend/facade class carries spec+doc (or is exempt).

    The drift guard mirrors the extras orphan guard: a new backend without a
    curated _CLASS_LINKS entry fails here instead of silently shipping a class
    node with no path to its authority.
    """
    graph = gen_graph_module.build_graph()
    exempt = gen_graph_module._LINKS_EXEMPT

    for n in graph["nodes"]:
        if n["kind"] != "class" or n["role"] not in {"abc", "backend", "facade"}:
            continue
        path = n["id"].removeprefix("cls:")
        if path in exempt:
            assert "spec" not in n, f"exempt class {path} unexpectedly carries 'spec'"
            assert "doc" not in n, f"exempt class {path} unexpectedly carries 'doc'"
            continue
        assert "spec" in n, f"class node {n['id']!r} missing 'spec' link metadata"
        assert "doc" in n, f"class node {n['id']!r} missing 'doc' link metadata"
        assert (ROOT / n["spec"]).exists(), f"{n['id']!r} spec target {n['spec']} does not exist"
        assert (ROOT / n["doc"]).exists(), f"{n['id']!r} doc target {n['doc']} does not exist"


@pytest.mark.spec("DGM-014")
def test_ungated_facade_method_nodes(gen_graph_module):
    """DGM-014: Store/AsyncStore facades emit their ungated public methods.

    Schema 1.3 emitted only gated methods, so the always-available surface
    (exists, child, supports, …) was not derivable. At 1.4 each public,
    non-gated function member of a facade is a method node carrying
    ``gated: False``; gated method nodes keep emitting with no ``gated`` key
    (absent ⇒ gated, the omit-when-default convention of DGM-010). Ungated
    nodes carry no req:/gates/of edges but are contained by their class.
    """
    graph = gen_graph_module.build_graph()
    by_id = {n["id"]: n for n in graph["nodes"]}

    # Representative ungated Store methods are present and flagged.
    for name in ("exists", "child", "supports", "close", "ping"):
        uri = f"mtd:remote_store._store.Store.{name}"
        assert uri in by_id, f"missing ungated method node {uri!r}"
        assert by_id[uri]["gated"] is False, f"{uri} should carry gated=False"

    # Gated method nodes never carry the gated key (absent ⇒ gated).
    for n in graph["nodes"]:
        if n["kind"] == "method":
            assert n.get("gated") is not True, f"{n['id']!r} should omit gated (absent ⇒ gated)"

    # The ungated set is exactly the facades' public, non-_GATING methods.
    from remote_store._store import _GATING as STORE_GATING

    store_ungated = {
        n["id"].removeprefix("mtd:remote_store._store.Store.")
        for n in graph["nodes"]
        if n["kind"] == "method" and n["id"].startswith("mtd:remote_store._store.Store.") and n.get("gated") is False
    }
    assert store_ungated == {
        "exists",
        "is_file",
        "is_folder",
        "ping",
        "close",
        "child",
        "unwrap",
        "resolve",
        "native_path",
        "to_key",
        "supports",
    }
    assert store_ungated.isdisjoint(STORE_GATING), "an ungated node overlaps _GATING"

    # AsyncStore goes through the same generalized "public Function not in
    # _GATING" walk, so pin its ungated set exactly too — async-side drift
    # (e.g. a new public helper, or aclose vs close) then fails this targeted
    # unit test rather than only the regenerated golden.
    from remote_store.aio._async_store import _GATING as ASYNC_GATING

    async_prefix = "mtd:remote_store.aio._async_store.AsyncStore."
    async_store_ungated = {
        n["id"].removeprefix(async_prefix)
        for n in graph["nodes"]
        if n["kind"] == "method" and n["id"].startswith(async_prefix) and n.get("gated") is False
    }
    assert async_store_ungated == {
        "exists",
        "is_file",
        "is_folder",
        "ping",
        "aclose",
        "child",
        "unwrap",
        "resolve",
        "native_path",
        "to_key",
        "supports",
    }
    assert async_store_ungated.isdisjoint(ASYNC_GATING), "an ungated async node overlaps _GATING"

    # Ungated methods carry no gate chain but are contained by their class.
    contains = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "contains"}
    gated_dsts = {e["dst"] for e in graph["edges"] if e["kind"] == "gates"}
    exists_uri = "mtd:remote_store._store.Store.exists"
    assert exists_uri not in gated_dsts, "ungated method must have no gates edge"
    assert ("cls:remote_store._store.Store", exists_uri) in contains


@pytest.mark.spec("DGM-002,DGM-003")
def test_deferred_kinds_absent(gen_graph_module):
    """DGM-002/DGM-003: node and edge kinds deferred at 1.3 must not be emitted.

    Emitting a deferred kind before a consumer needs it inflates the golden diff;
    this pins the 1.3 boundary so a kind cannot creep in unannounced.
    """
    graph = gen_graph_module.build_graph()
    node_kinds = {n["kind"] for n in graph["nodes"]}
    edge_kinds = {e["kind"] for e in graph["edges"]}

    deferred_nodes = {
        "module",
        "data_model",
        "field",
        "error",
        "parameter",
        "type_ref",
        "predicate",
        "package_dep",
        "role",
    }
    deferred_edges = {
        "composes",
        "requires_cap",
        "played_by",
        "returns",
        "accepts",
        "has_param",
        "typed",
        "has_field",
        "raises",
        "requires_dep",
    }
    assert node_kinds.isdisjoint(deferred_nodes), f"deferred node kind emitted: {node_kinds & deferred_nodes}"
    assert edge_kinds.isdisjoint(deferred_edges), f"deferred edge kind emitted: {edge_kinds & deferred_edges}"


@pytest.mark.spec("DGM-011")
def test_extra_nodes_use_kind_of(gen_graph_module):
    """DGM-011: extra nodes carry their classification under 'kind_of', not 'kind'.

    'kind' is the reserved node-kind discriminator ('extra'); the RFC's 'kind'
    property is renamed to 'kind_of' to avoid the collision.
    """
    graph = gen_graph_module.build_graph()
    extras = [n for n in graph["nodes"] if n["kind"] == "extra"]
    assert extras, "no extra nodes in graph"
    for n in extras:
        assert n["kind"] == "extra"
        assert "kind_of" in n, f"extra node {n['id']!r} missing 'kind_of'"
        assert n["kind_of"] == "backend"


@pytest.mark.spec("DGM-013")
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
