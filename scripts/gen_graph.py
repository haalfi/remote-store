"""Generate docs-src/_data/graph/graph.json from source.

Run with:  hatch run python scripts/gen_graph.py
"""

from __future__ import annotations

import argparse
import ast
import importlib
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


def _collect_abc_classes(pkg: griffe.Module) -> list[griffe.Class]:
    """Walk Griffe module tree and return Backend/AsyncBackend ABC classes."""
    result: list[griffe.Class] = []
    _walk_module_abc(pkg, result)
    return result


def _walk_module(mod: griffe.Module, out: list[griffe.Class]) -> None:
    for member in mod.members.values():
        if isinstance(member, griffe.Class):
            if "CAPABILITIES" in member.members:
                out.append(member)
        elif isinstance(member, griffe.Module):
            _walk_module(member, out)


def _walk_module_abc(mod: griffe.Module, out: list[griffe.Class]) -> None:
    _ABC_NAMES = frozenset({"Backend", "AsyncBackend"})
    for member in mod.members.values():
        if isinstance(member, griffe.Class):
            if member.name in _ABC_NAMES and "CAPABILITIES" not in member.members:
                out.append(member)
        elif isinstance(member, griffe.Module):
            _walk_module_abc(member, out)


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


def _capability_enum() -> type:
    from remote_store._capabilities import Capability

    return Capability


def _store_gating() -> dict[str, Any]:
    from remote_store._store import _GATING

    return _GATING


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

    backend_classes = _collect_backend_classes(pkg)
    abc_classes = _collect_abc_classes(pkg)

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

    # --- ABC class nodes ---
    for griffe_cls in abc_classes:
        uri = _class_uri(griffe_cls)
        nodes.append(
            {
                "id": uri,
                "kind": "class",
                "role": "abc",
                "runtime": _runtime(griffe_cls),
                "file": _rel_path(griffe_cls.filepath),
                "line": griffe_cls.lineno,
                "summary": _first_line(griffe_cls.docstring.value if griffe_cls.docstring else None),
            }
        )

    # --- backend class nodes + declares edges ---
    for griffe_cls in backend_classes:
        uri = _class_uri(griffe_cls)
        runtime = _runtime(griffe_cls)

        nodes.append(
            {
                "id": uri,
                "kind": "class",
                "role": "backend",
                "runtime": runtime,
                "file": _rel_path(griffe_cls.filepath),
                "line": griffe_cls.lineno,
                "summary": _first_line(griffe_cls.docstring.value if griffe_cls.docstring else None),
            }
        )

        # declares, mirrors, and inherits edges emitted in second pass below
        _rt_cls = _import_class(griffe_cls)

    # --- second pass: declares / mirrors / inherits edges (needs full node set) ---
    node_ids: set[str] = {n["id"] for n in nodes}

    for griffe_cls in backend_classes + abc_classes:
        uri = _class_uri(griffe_cls)
        rt_cls = _import_class(griffe_cls)

        if rt_cls is not None:
            # declares edges
            caps_set = getattr(rt_cls, "CAPABILITIES", None)
            if caps_set is not None:
                for cap in caps_set:
                    edges.append(
                        {
                            "kind": "declares",
                            "src": uri,
                            "dst": f"cap:{cap.name}",
                            "condition": None,
                        }
                    )

            # mirrors edges (both directions; symmetric pair dedup happens below)
            mirror = getattr(rt_cls, "__mirror__", None)
            if mirror is not None and isinstance(mirror, type):
                mirror_uri = f"cls:{mirror.__module__}.{mirror.__qualname__}"
                edges.append({"kind": "mirrors", "src": uri, "dst": mirror_uri})
                edges.append({"kind": "mirrors", "src": mirror_uri, "dst": uri})

            # inherits edges (runtime __bases__, only when target is in the graph)
            for base in rt_cls.__bases__:
                if base.__module__ and base.__module__ != "builtins":
                    base_uri = f"cls:{base.__module__}.{base.__qualname__}"
                    if base_uri in node_ids:
                        edges.append({"kind": "inherits", "src": uri, "dst": base_uri})

    # --- extra nodes + enables edges ---
    seen_extras: set[str] = set()
    for class_qname, extra_name in class_extra_map.items():
        if extra_name not in seen_extras:
            nodes.append({"id": f"xtr:{extra_name}", "kind": "extra", "kind_of": "backend"})
            seen_extras.add(extra_name)
        backend_uri = f"cls:{class_qname}"
        if backend_uri in node_ids:
            edges.append({"kind": "enables", "src": f"xtr:{extra_name}", "dst": backend_uri})

    # --- Store method nodes + gates/of edges ---
    # Today _GATING targets Store only. To extend to AsyncStore, also walk
    # pkg.members["aio"].members["_async_store"].members["AsyncStore"].
    store_cls = pkg["_store"]["Store"]
    for method_name, cap in gating.items():
        if method_name not in store_cls.members:
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
        "schema_version": "1.1",
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
