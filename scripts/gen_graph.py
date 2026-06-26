"""Generate docs-src/_data/graph/graph.json from source.

Run with:  hatch run python scripts/gen_graph.py
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

import griffe

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "docs-src" / "_data" / "graph" / "graph.json"


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


def _norm_pip(spec: str) -> str:
    """Strip version specifier and normalize pip package name."""
    return re.split(r"[>=<!;]|\[", spec)[0].strip().lower().replace("_", "-")


def _load_pyproject() -> dict[str, Any]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _extras_to_names(pyproject: dict[str, Any]) -> dict[str, frozenset[str]]:
    """Return {extra_name: frozenset of normalized pip package names}."""
    opt = pyproject.get("project", {}).get("optional-dependencies", {})
    result: dict[str, frozenset[str]] = {}
    for extra, deps in opt.items():
        pkgs: set[str] = set()
        for dep in deps:
            normalized = _norm_pip(dep)
            if normalized.startswith("remote-store") or normalized.startswith("remote_store"):
                continue
            pkgs.add(normalized)
        result[extra] = frozenset(pkgs)
    return result


def _parse_optional_blocks(init_file: Path) -> list[tuple[str, list[str]]]:
    """Parse try/except ImportError blocks in a backends __init__.py.

    Returns a list of (module_qname, [class_names]) pairs in source order.
    """
    source = init_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    blocks: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        is_import_err = any(isinstance(h.type, ast.Name) and h.type.id == "ImportError" for h in node.handlers)
        if not is_import_err:
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module:
                classes = [alias.name for alias in stmt.names]
                blocks.append((stmt.module, classes))
    return blocks


def _derive_extra(module_suffix: str, cls_name: str, available_extras: dict[str, frozenset[str]]) -> str | None:
    """Determine the pip extra for a single backend class.

    Two-source join:
    1. Module suffix → canonical extra name (strip leading _, replace _ with -).
    2. If no direct match, use class-name disambiguation for known cases where
       one module provides multiple capability tiers (e.g. sqlalchemy → sql/sql-query).
    """
    canonical = module_suffix.lstrip("_").replace("_", "-")
    if canonical in available_extras:
        return canonical

    # sqlalchemy uses abbreviated extra names ('sql', 'sql-query') that don't
    # directly correspond to the module name 'sqlalchemy'. Disambiguate by
    # class name: the only working discriminator is 'Query' (SQLQueryBackend).
    if "sqlalchemy" in canonical:
        if "Query" in cls_name:
            return "sql-query" if "sql-query" in available_extras else None
        return "sql" if "sql" in available_extras else None

    return None


def _build_extras_map(
    optional_blocks: list[tuple[str, list[str]]],
    extras_roots: dict[str, frozenset[str]],
) -> dict[str, str]:
    """Return {class_qname: extra_name} for all optionally-guarded classes.

    Two-source join over:
    1. optional_blocks: (module_qname, [class_names]) from backends/__init__.py AST
    2. extras_roots: {extra_name: frozenset[import_root]} from pyproject.toml
    """
    result: dict[str, str] = {}
    for module_qname, classes in optional_blocks:
        module_suffix = module_qname.split(".")[-1]
        for cls_name in classes:
            extra = _derive_extra(module_suffix, cls_name, extras_roots)
            if extra is not None:
                result[f"{module_qname}.{cls_name}"] = extra
    return result


# ---------------------------------------------------------------------------
# Node / edge builders
# ---------------------------------------------------------------------------


def _first_line(docstring: str | None) -> str:
    if not docstring:
        return ""
    for line in docstring.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _class_uri(griffe_cls: griffe.Class) -> str:
    return f"cls:{griffe_cls.path}"


def _rel_path(filepath: Path | None) -> str:
    if filepath is None:
        return ""
    try:
        return str(Path(filepath).relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(filepath).replace("\\", "/")


def _collect_backend_classes(pkg: griffe.Module) -> list[griffe.Class]:
    """Walk Griffe module tree and return all classes with a CAPABILITIES attribute."""
    result: list[griffe.Class] = []
    _walk_module(pkg, result)
    return result


def _walk_module(mod: griffe.Module, out: list[griffe.Class]) -> None:
    for member in mod.members.values():
        if isinstance(member, griffe.Class):
            if "CAPABILITIES" in member.members:
                out.append(member)
        elif isinstance(member, griffe.Module):
            _walk_module(member, out)


def _runtime(griffe_cls: griffe.Class) -> str:
    """Return 'async' if the class is in the aio sub-package, else 'sync'."""
    return "async" if ".aio." in griffe_cls.path else "sync"


def _import_class(griffe_cls: griffe.Class) -> type | None:
    """Try to import and return the runtime class object."""
    module_path = griffe_cls.module.path
    cls_name = griffe_cls.name
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name, None)
    except ImportError:
        return None


# Class-role taxonomy (DGM-004). ``Backend``/``AsyncBackend`` are ABCs; the three
# facades present a Store/Backend-shaped surface but delegate rather than declaring
# storage capabilities of their own.
_ABC_NAMES = frozenset({"Backend", "AsyncBackend"})
_FACADE_QNAMES = frozenset(
    {
        "remote_store._store.Store",
        "remote_store.aio._async_store.AsyncStore",
        "remote_store.aio._sync_adapter.SyncBackendAdapter",
    }
)

# Curated class → (governing spec, API docs page) link metadata (DGM-009). Paths
# are repo-relative from ROOT, consistent with the ``file`` node field. The spec
# and docs structure is editorial, so unlike the extras→backend join there is no
# second machine source to join against — a curated table is the honest form.
# build_graph() asserts every target exists, so a stale entry fails generation.
_CLASS_LINKS: dict[str, dict[str, str]] = {
    "remote_store._store.Store": {
        "spec": "sdd/specs/001-store-api.md",
        "doc": "docs-src/reference/api/store.md",
    },
    "remote_store._backend.Backend": {
        "spec": "sdd/specs/003-backend-adapter-contract.md",
        "doc": "docs-src/reference/api/backend.md",
    },
    "remote_store.backends._local.LocalBackend": {
        "spec": "sdd/specs/003-backend-adapter-contract.md",
        "doc": "docs-src/reference/api/backends/local.md",
    },
    "remote_store.backends._memory.MemoryBackend": {
        "spec": "sdd/specs/013-memory-backend.md",
        "doc": "docs-src/reference/api/backends/memory.md",
    },
    "remote_store.backends._s3.S3Backend": {
        "spec": "sdd/specs/008-s3-backend.md",
        "doc": "docs-src/reference/api/backends/s3.md",
    },
    "remote_store.backends._s3_pyarrow.S3PyArrowBackend": {
        "spec": "sdd/specs/011-s3-pyarrow-backend.md",
        "doc": "docs-src/reference/api/backends/s3-pyarrow.md",
    },
    "remote_store.backends._azure.AzureBackend": {
        "spec": "sdd/specs/012-azure-backend.md",
        "doc": "docs-src/reference/api/backends/azure.md",
    },
    "remote_store.backends._sftp.SFTPBackend": {
        "spec": "sdd/specs/009-sftp-backend.md",
        "doc": "docs-src/reference/api/backends/sftp.md",
    },
    "remote_store.backends._http.ReadOnlyHttpBackend": {
        "spec": "sdd/specs/032-http-backend.md",
        "doc": "docs-src/reference/api/backends/http.md",
    },
    "remote_store.backends._sqlalchemy.SQLBlobBackend": {
        "spec": "sdd/specs/040-sql-blob-backend.md",
        "doc": "docs-src/reference/api/backends/sql-blob.md",
    },
    "remote_store.backends._sqlalchemy.SQLQueryBackend": {
        "spec": "sdd/specs/041-sql-query-backend.md",
        "doc": "docs-src/reference/api/backends/sql-query.md",
    },
    "remote_store.aio._async_store.AsyncStore": {
        "spec": "sdd/specs/029-async-store-backend-api.md",
        "doc": "docs-src/reference/api/aio/store.md",
    },
    "remote_store.aio._async_backend.AsyncBackend": {
        "spec": "sdd/specs/029-async-store-backend-api.md",
        "doc": "docs-src/reference/api/aio/backend.md",
    },
    "remote_store.aio._sync_adapter.SyncBackendAdapter": {
        "spec": "sdd/specs/029-async-store-backend-api.md",
        "doc": "docs-src/reference/api/aio/adapters.md",
    },
    "remote_store.aio.backends._azure.AsyncAzureBackend": {
        "spec": "sdd/specs/012-azure-backend.md",
        "doc": "docs-src/reference/api/aio/backends/azure.md",
    },
    "remote_store.aio.backends._memory.AsyncMemoryBackend": {
        "spec": "sdd/specs/013-memory-backend.md",
        "doc": "docs-src/reference/api/aio/backends/memory.md",
    },
    "remote_store.aio.backends._graph.backend.GraphBackend": {
        "spec": "sdd/specs/044-graph-backend.md",
        "doc": "docs-src/reference/api/aio/backends/graph.md",
    },
}

# Class nodes that legitimately carry no link metadata: a proof-of-concept with
# no dedicated spec or API page. Every other abc/backend/facade class must appear
# in _CLASS_LINKS (drift-guarded by test_class_nodes_carry_link_metadata).
_LINKS_EXEMPT = frozenset({"remote_store.backends._s3_boto3.S3Boto3Backend"})


def _class_role(path: str, rt_cls: type | None) -> str:
    """Resolve a class node's role (DGM-004): abc · backend · facade."""
    if path in _FACADE_QNAMES:
        return "facade"
    caps = getattr(rt_cls, "CAPABILITIES", None) if rt_cls is not None else None
    name = path.rsplit(".", 1)[-1]
    # The ABCs carry a ``CAPABILITIES: ClassVar`` annotation with no value, so a
    # Griffe member-name check misclassifies them; resolve the runtime value.
    if name in _ABC_NAMES and caps is None:
        return "abc"
    return "backend"


def _assert_link_targets_exist() -> None:
    """Fail generation if any curated link-metadata path is stale (DGM-009)."""
    for path, links in _CLASS_LINKS.items():
        for key, rel in links.items():
            if not (ROOT / rel).exists():
                raise AssertionError(f"_CLASS_LINKS[{path!r}][{key!r}] -> {rel} does not exist")


def _capability_enum() -> type:
    from remote_store._capabilities import Capability

    return Capability


def _store_gating() -> dict[str, Any]:
    from remote_store._store import _GATING

    return _GATING


def _async_store_gating() -> dict[str, Any]:
    from remote_store.aio._async_store import _GATING

    return _GATING


# Capability-name strings for each gated Backend method.  Defined here
# (gen_graph.py is the only consumer) to avoid an unused-variable alert in
# _backend.py — Backend has no runtime _gate() equivalent, unlike Store.
_BACKEND_GATING: dict[str, str] = {
    "read": "READ",
    "read_bytes": "READ",
    "read_seekable": "READ",
    "write": "WRITE",
    "write_atomic": "ATOMIC_WRITE",
    "open_atomic": "ATOMIC_WRITE",
    "delete": "DELETE",
    "delete_folder": "DELETE",
    "list_files": "LIST",
    "list_folders": "LIST",
    "iter_children": "LIST",
    "glob": "GLOB",
    "get_file_info": "METADATA",
    "get_folder_info": "METADATA",
    "move": "MOVE",
    "copy": "COPY",
}


# Async counterpart of _BACKEND_GATING.  AsyncBackend mirrors the sync Backend
# gate map minus ``read_seekable`` / ``open_atomic``, which have no async
# equivalents (same delta the async-store _GATING applies; see the
# CLAUDE-REFERENCE ripple-check).  Like _BACKEND_GATING this lives here
# (graph-IR generation only) — AsyncBackend has no runtime _gate() equivalent.
_ASYNC_BACKEND_GATING: dict[str, str] = {
    "read": "READ",
    "read_bytes": "READ",
    "write": "WRITE",
    "write_atomic": "ATOMIC_WRITE",
    "delete": "DELETE",
    "delete_folder": "DELETE",
    "list_files": "LIST",
    "list_folders": "LIST",
    "iter_children": "LIST",
    "glob": "GLOB",
    "get_file_info": "METADATA",
    "get_folder_info": "METADATA",
    "move": "MOVE",
    "copy": "COPY",
}


def build_graph() -> dict[str, Any]:
    """Build and return the full graph dict."""
    pyproject = _load_pyproject()
    version: str = pyproject["project"]["version"]

    extras_roots = _extras_to_names(pyproject)

    # Optional-backend class→extra mapping (two-source join)
    sync_blocks = _parse_optional_blocks(SRC / "remote_store" / "backends" / "__init__.py")
    async_blocks = _parse_optional_blocks(SRC / "remote_store" / "aio" / "backends" / "__init__.py")
    all_blocks = sync_blocks + async_blocks

    class_extra_map = _build_extras_map(all_blocks, extras_roots)

    # Load Griffe package tree
    sys.path.insert(0, str(SRC))
    pkg = griffe.load("remote_store")

    _assert_link_targets_exist()

    # Classes with a CAPABILITIES member: concrete backends, the two ABCs (which
    # carry a value-less annotation), and the SyncBackendAdapter facade. The
    # Store/AsyncStore facades have no CAPABILITIES, so add them explicitly so
    # their gated-method nodes are not orphaned (DGM-007).
    backend_classes = _collect_backend_classes(pkg)
    store_griffe = pkg["_store"]["Store"]
    async_store_griffe = pkg["aio"]["_async_store"]["AsyncStore"]
    all_class_griffe = [*backend_classes, store_griffe, async_store_griffe]

    Capability = _capability_enum()
    gating = _store_gating()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # --- package nodes ---
    nodes.append({"id": "pkg:remote_store", "kind": "package", "runtime": "sync", "version": version})
    nodes.append({"id": "pkg:remote_store.aio", "kind": "package", "runtime": "async", "version": version})

    # --- capability nodes ---
    for cap in Capability:
        nodes.append({"id": f"cap:{cap.name}", "kind": "capability", "value": cap.value})

    # --- class nodes (abc / backend / facade) + link metadata ---
    class_role: dict[str, str] = {}
    for griffe_cls in all_class_griffe:
        uri = _class_uri(griffe_cls)
        role = _class_role(griffe_cls.path, _import_class(griffe_cls))
        class_role[uri] = role
        node = {
            "id": uri,
            "kind": "class",
            "role": role,
            "runtime": _runtime(griffe_cls),
            "file": _rel_path(griffe_cls.filepath),
            "line": griffe_cls.lineno,
            "summary": _first_line(griffe_cls.docstring.value if griffe_cls.docstring else None),
        }
        # Link metadata (DGM-009): governing spec + API docs page, when curated.
        node.update(_CLASS_LINKS.get(griffe_cls.path, {}))
        nodes.append(node)

    # --- second pass: declares / mirrors / inherits edges (needs full node set) ---
    node_ids: set[str] = {n["id"] for n in nodes}

    for griffe_cls in all_class_griffe:
        uri = _class_uri(griffe_cls)
        rt_cls = _import_class(griffe_cls)

        if rt_cls is not None:
            # declares edges — suppressed for facades (DGM-006): a facade's
            # CAPABILITIES describe whatever backend it wraps, not a static
            # declaration of its own.
            caps_set = getattr(rt_cls, "CAPABILITIES", None)
            if caps_set is not None and class_role[uri] != "facade":
                for cap in caps_set:
                    # ``condition`` is omitted when unconditional (absent == null),
                    # per RFC-0012 "Edge taxonomy" (declares row). A conditional
                    # declares (ID-140) carries a non-null ``condition``.
                    edges.append(
                        {
                            "kind": "declares",
                            "src": uri,
                            "dst": f"cap:{cap.name}",
                        }
                    )

            # mirrors edges (both directions; symmetric pair dedup happens below)
            mirror = getattr(rt_cls, "__mirror__", None)
            if mirror is not None and isinstance(mirror, type):
                mirror_uri = f"cls:{mirror.__module__}.{mirror.__qualname__}"
                # capability_delta (ID-162): names are anchored to the canonical
                # async->sync direction kept by the dedup pass below.
                async_caps = {c.name for c in (getattr(rt_cls, "CAPABILITIES", None) or ())}
                sync_caps = {c.name for c in (getattr(mirror, "CAPABILITIES", None) or ())}
                capability_delta = {
                    "async_only": sorted(async_caps - sync_caps),
                    "sync_only": sorted(sync_caps - async_caps),
                }
                edges.append({"kind": "mirrors", "src": uri, "dst": mirror_uri, "capability_delta": capability_delta})
                edges.append({"kind": "mirrors", "src": mirror_uri, "dst": uri, "capability_delta": capability_delta})

            # inherits edge (DGM-005): walk the MRO and link to the nearest
            # ancestor that is itself a node, so backends behind a private base
            # (_S3Base, _SQLAlchemyBaseBackend) still reach the Backend ABC.
            for ancestor in inspect.getmro(rt_cls)[1:]:
                ancestor_uri = f"cls:{ancestor.__module__}.{ancestor.__qualname__}"
                if ancestor_uri in node_ids:
                    edges.append({"kind": "inherits", "src": uri, "dst": ancestor_uri})
                    break

    # --- extra nodes + enables edges ---
    # class_extra_map keys are import-derived qnames (from the AST of the
    # backends __init__ re-exports), which equal the canonical griffe path for
    # single-module backends (e.g. ``_azure.AzureBackend``) but NOT for a class
    # re-exported from a deeper sub-package (e.g. the package import
    # ``_graph`` yields ``..._graph.GraphBackend`` while the canonical node is
    # ``..._graph.backend.GraphBackend``). Resolve each to the real backend node
    # by exact match, then by name within the import package.
    backend_uris: set[str] = {_class_uri(c) for c in backend_classes}
    backend_by_name: dict[str, list[str]] = {}
    for griffe_cls in backend_classes:
        backend_by_name.setdefault(griffe_cls.name, []).append(_class_uri(griffe_cls))

    seen_extras: set[str] = set()
    for class_qname, extra_name in class_extra_map.items():
        if extra_name not in seen_extras:
            nodes.append({"id": f"xtr:{extra_name}", "kind": "extra", "kind_of": "backend"})
            seen_extras.add(extra_name)
        exact = f"cls:{class_qname}"
        if exact in backend_uris:
            backend_uri: str | None = exact
        else:
            import_module, _, cls_name = class_qname.rpartition(".")
            candidates = [
                uri
                for uri in backend_by_name.get(cls_name, [])
                if uri.removeprefix("cls:").startswith(f"{import_module}.")
            ]
            backend_uri = candidates[0] if len(candidates) == 1 else None
        if backend_uri is not None:
            edges.append({"kind": "enables", "src": f"xtr:{extra_name}", "dst": backend_uri})

    # --- Store method nodes + gates/of edges ---
    store_cls = pkg["_store"]["Store"]
    for method_name, cap in gating.items():
        if method_name not in store_cls.members:  # pragma: no cover
            raise AssertionError(
                f"_GATING key {method_name!r} is not a Griffe member of Store; "
                "update Store or _GATING to keep them in sync."
            )
        mtd_uri = f"mtd:remote_store._store.Store.{method_name}"
        req_uri = f"req:remote_store._store.Store.{method_name}.gate"
        cap_uri = f"cap:{cap.name}"

        member = store_cls[method_name]
        nodes.append(
            {
                "id": mtd_uri,
                "kind": "method",
                "summary": method_name,
                "is_abstract": "abstractmethod" in member.labels,
                "is_async": "async" in member.labels,
                "file": _rel_path(member.filepath),
                "line": member.lineno or 0,
            }
        )
        nodes.append({"id": req_uri, "kind": "requirement", "mode": "all"})

        edges.append({"kind": "gates", "src": req_uri, "dst": mtd_uri})
        edges.append({"kind": "of", "src": req_uri, "dst": cap_uri, "index": 0})

    # Special-case: get_folder_info has a secondary depth-limited gate on LIST.
    # When max_depth is not None, Store._gate("list_files") is called instead.
    # See _store.py _GATING comment: "gen_graph.py must special-case this method."
    _gfi_mtd = "mtd:remote_store._store.Store.get_folder_info"
    _gfi_req2 = "req:remote_store._store.Store.get_folder_info.gate_depth"
    nodes.append({"id": _gfi_req2, "kind": "requirement", "mode": "all"})
    edges.append({"kind": "gates", "src": _gfi_req2, "dst": _gfi_mtd})
    edges.append({"kind": "of", "src": _gfi_req2, "dst": f"cap:{Capability.LIST.name}", "index": 0})

    # --- AsyncStore method nodes + gates/of edges ---
    async_store_cls = pkg["aio"]["_async_store"]["AsyncStore"]
    async_gating = _async_store_gating()
    for method_name, cap in async_gating.items():
        if method_name not in async_store_cls.members:  # pragma: no cover
            raise AssertionError(
                f"async _GATING key {method_name!r} is not a Griffe member of AsyncStore; "
                "update AsyncStore or aio/_async_store.py _GATING to keep them in sync."
            )
        mtd_uri = f"mtd:remote_store.aio._async_store.AsyncStore.{method_name}"
        req_uri = f"req:remote_store.aio._async_store.AsyncStore.{method_name}.gate"
        cap_uri = f"cap:{cap.name}"

        member = async_store_cls[method_name]
        nodes.append(
            {
                "id": mtd_uri,
                "kind": "method",
                "summary": method_name,
                "is_abstract": "abstractmethod" in member.labels,
                "is_async": "async" in member.labels,
                "file": _rel_path(member.filepath),
                "line": member.lineno or 0,
            }
        )
        nodes.append({"id": req_uri, "kind": "requirement", "mode": "all"})

        edges.append({"kind": "gates", "src": req_uri, "dst": mtd_uri})
        edges.append({"kind": "of", "src": req_uri, "dst": cap_uri, "index": 0})

    # Async dual gate for get_folder_info (METADATA primary; LIST when max_depth is set).
    _a_gfi_mtd = "mtd:remote_store.aio._async_store.AsyncStore.get_folder_info"
    _a_gfi_req2 = "req:remote_store.aio._async_store.AsyncStore.get_folder_info.gate_depth"
    nodes.append({"id": _a_gfi_req2, "kind": "requirement", "mode": "all"})
    edges.append({"kind": "gates", "src": _a_gfi_req2, "dst": _a_gfi_mtd})
    edges.append({"kind": "of", "src": _a_gfi_req2, "dst": f"cap:{Capability.LIST.name}", "index": 0})

    # --- Backend method nodes + gates/of edges ---
    backend_cls = pkg["_backend"]["Backend"]
    for method_name, cap_name in _BACKEND_GATING.items():
        if method_name not in backend_cls.members:  # pragma: no cover
            raise AssertionError(
                f"_BACKEND_GATING key {method_name!r} is not a Griffe member of Backend; "
                "update Backend or _BACKEND_GATING to keep them in sync."
            )
        mtd_uri = f"mtd:remote_store._backend.Backend.{method_name}"
        req_uri = f"req:remote_store._backend.Backend.{method_name}.gate"
        cap_uri = f"cap:{cap_name}"

        member = backend_cls[method_name]
        nodes.append(
            {
                "id": mtd_uri,
                "kind": "method",
                "summary": method_name,
                "is_abstract": "abstractmethod" in member.labels,
                "is_async": "async" in member.labels,
                "file": _rel_path(member.filepath),
                "line": member.lineno or 0,
            }
        )
        nodes.append({"id": req_uri, "kind": "requirement", "mode": "all"})

        edges.append({"kind": "gates", "src": req_uri, "dst": mtd_uri})
        edges.append({"kind": "of", "src": req_uri, "dst": cap_uri, "index": 0})

    # --- AsyncBackend method nodes + gates/of edges ---
    async_backend_cls = pkg["aio"]["_async_backend"]["AsyncBackend"]
    for method_name, cap_name in _ASYNC_BACKEND_GATING.items():
        if method_name not in async_backend_cls.members:  # pragma: no cover
            raise AssertionError(
                f"_ASYNC_BACKEND_GATING key {method_name!r} is not a Griffe member of AsyncBackend; "
                "update AsyncBackend or _ASYNC_BACKEND_GATING to keep them in sync."
            )
        mtd_uri = f"mtd:remote_store.aio._async_backend.AsyncBackend.{method_name}"
        req_uri = f"req:remote_store.aio._async_backend.AsyncBackend.{method_name}.gate"
        cap_uri = f"cap:{cap_name}"

        member = async_backend_cls[method_name]
        nodes.append(
            {
                "id": mtd_uri,
                "kind": "method",
                "summary": method_name,
                "is_abstract": "abstractmethod" in member.labels,
                "is_async": "async" in member.labels,
                "file": _rel_path(member.filepath),
                "line": member.lineno or 0,
            }
        )
        nodes.append({"id": req_uri, "kind": "requirement", "mode": "all"})

        edges.append({"kind": "gates", "src": req_uri, "dst": mtd_uri})
        edges.append({"kind": "of", "src": req_uri, "dst": cap_uri, "index": 0})

    # --- contains edges (DGM-008) ---
    # Containment tree: package → class (by runtime) and class → method (resolved
    # from the method URI). Requirement nodes are gate groups, not containment
    # members, so they are not contained.
    class_uris = {n["id"] for n in nodes if n["kind"] == "class"}
    for node in nodes:
        if node["kind"] == "class":
            pkg_id = "pkg:remote_store.aio" if node["runtime"] == "async" else "pkg:remote_store"
            edges.append({"kind": "contains", "src": pkg_id, "dst": node["id"]})
        elif node["kind"] == "method":
            cls_uri = f"cls:{node['id'].removeprefix('mtd:').rsplit('.', 1)[0]}"
            if cls_uri in class_uris:
                edges.append({"kind": "contains", "src": cls_uri, "dst": node["id"]})

    # --- Deduplicate mirrors edges ---
    # Each __mirror__ annotation produces one async→sync edge.  Dedup by
    # canonical pair so the graph contains exactly one edge per peer pair.
    # Canonical direction: async→sync (src URI sorts before dst after sort()).
    seen_mirrors: set[tuple[str, str]] = set()
    deduped_edges: list[dict[str, Any]] = []
    for edge in edges:
        if edge["kind"] == "mirrors":
            pair = tuple(sorted([edge["src"], edge["dst"]]))
            if pair in seen_mirrors:
                continue
            seen_mirrors.add(pair)  # type: ignore[arg-type]
        deduped_edges.append(edge)
    edges = deduped_edges

    # --- Sort ---
    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["kind"], e["src"], e["dst"]))

    return {
        "edges": edges,
        "nodes": nodes,
        "schema_version": "1.3",
        "snapshot": version,
        "source_version": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate docs-src/_data/graph/graph.json from source.")
    parser.add_argument("--check", action="store_true", help="Exit 1 if graph.json would change; do not write.")
    args = parser.parse_args()

    graph = build_graph()
    text = json.dumps(graph, sort_keys=True, indent=2) + "\n"
    text_bytes = text.encode("utf-8").replace(b"\r\n", b"\n")

    if args.check:
        existing_lf = OUT.read_bytes().replace(b"\r\n", b"\n") if OUT.exists() else b""
        if existing_lf != text_bytes:
            print("graph.json is out of date.\nRun:  hatch run gen-graph")
            raise SystemExit(1)
        return

    # Ensure LF line endings regardless of platform
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(text_bytes)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges)")


if __name__ == "__main__":
    main()
