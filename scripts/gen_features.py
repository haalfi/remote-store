"""Project graph.json → mechanical sections of FEATURES.md (ID-163).

Run with:  hatch run gen-features
           hatch run python scripts/gen_features.py [--check]

--check exits 1 if FEATURES.md would change; use in CI or pre-commit.

Backend rows and install-extras entries are sorted alphabetically by type
string / extra name (ID-169).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"
FEATURES = ROOT / "FEATURES.md"

# Capabilities shown in the flags table rather than the main capabilities column.
_FLAGS_CAPS: frozenset[str] = frozenset({"USER_METADATA", "WRITE_RESULT_NATIVE"})

# Backend×capability pairs that need a special note in the flags table.
_FLAGS_NOTES: dict[tuple[str, str], str] = {
    ("sql-blob", "WRITE_RESULT_NATIVE"): "Yes (requires `modified_at` column)",
    ("sql-blob", "USER_METADATA"): "Yes (requires `user_metadata` column)",
}

# Pip install line comments for known extras.  Add a new entry here when a new
# extra is introduced; the entry is omitted (no comment) if the key is absent.
_EXTRA_COMMENTS: dict[str, str] = {
    "s3": "S3 via s3fs",
    "s3-pyarrow": "S3 via PyArrow C++ filesystem",
    "sftp": "SFTP via paramiko",
    "azure": "Azure ADLS Gen2 via Azure SDK",
    "graph": "Microsoft Graph (OneDrive / SharePoint / Teams) via httpx + msal",
    "sql": "SQL blob store via SQLAlchemy",
    "sql-query": "SQL query store via SQLAlchemy + PyArrow",
    "arrow": "PyArrow filesystem bridge + Parquet extension",
    "otel": "OpenTelemetry distributed tracing",
    "pydantic": "Pydantic settings integration",
    "yaml": "YAML config loading",
    "dagster": "Dagster IO manager",
    "toml": "TOML config (stdlib on Python 3.11+)",
    "requests": "requests HTTP adapter for ReadOnlyHttpBackend",
    "httpx": "httpx HTTP adapter for ReadOnlyHttpBackend",
}

# Extras omitted from the install extras section (dev / build / CI tooling).
_EXCLUDE_EXTRAS: frozenset[str] = frozenset({"bench", "dev", "docs", "mutate"})

# URI prefixes for the sync Store facade (the Store API projections walk these).
_STORE_MTD_PREFIX = "mtd:remote_store._store.Store."
_STORE_REQ_PREFIX = "req:remote_store._store.Store."

# Curated Returns/Description prose for the ungated Store methods. The graph
# (schema 1.4) owns the *membership* of this set — every Store method node with
# ``gated == false`` (DGM-014) — but carries no return type or description
# (DGM-002 defers those), so the prose is curated here and the *set* is
# drift-guarded against the graph in project_store_api_ungated(). Insertion order
# is the logical doc order (existence checks, lifecycle, then key/backend access).
_UNGATED_STORE_DETAILS: dict[str, tuple[str, str, str]] = {
    "exists": ("exists(path)", "`bool`", "Whether a file exists at the path"),
    "is_file": ("is_file(path)", "`bool`", "Whether the path resolves to a file (not a folder)"),
    "is_folder": ("is_folder(path)", "`bool`", "Whether the path resolves to a folder"),
    "ping": ("ping()", "`None`", "Health check — raises `BackendUnavailable` if unreachable"),
    "close": ("close()", "`None`", "Release backend resources"),
    "child": ("child(subpath)", "`Store`", "Scoped sub-store rooted at `subpath`"),
    "unwrap": ("unwrap(type_hint)", "`T`", "Extract the underlying backend by type"),
    "resolve": ("resolve(key)", "`ResolutionPlan`", "Resolution plan for a key (type, resolved path, options)"),
    "native_path": ("native_path(key)", "`str`", "Backend-native path string for a store key"),
    "to_key": ("to_key(path)", "`str`", "Convert a native path back to a store key"),
    "supports": ("supports(capability)", "`bool`", "Query whether a capability is active"),
}

# Override the auto-derived Extra cell for backends whose install story cannot be
# expressed as a single pip extra (e.g. stdlib-first with optional adapters).
_EXTRA_CELL_OVERRIDES: dict[str, str] = {
    "http": "— (stdlib; `requests`/`httpx` optional)",
}

# --- ID-227 Phase 1: retryability + atomicity matrices ---------------------

# Status → (disposition, surfaced-as typed error) for the retry-classification
# table. The retried/terminal *split* is imported live from remote_store._retry
# (RETRYABLE_STATUSES / TERMINAL_STATUSES); this dict only supplies the
# human-readable disposition + the typed error each status surfaces as, and is
# drift-guarded so its keys equal RETRYABLE_STATUSES | TERMINAL_STATUSES.
_STATUS_DETAIL: dict[int, tuple[str, str]] = {
    429: ("Retried — honours `Retry-After`", "`BackendUnavailable`"),
    500: ("Retried", "`BackendUnavailable`"),
    502: ("Retried", "`BackendUnavailable`"),
    503: ("Retried", "`BackendUnavailable`"),
    504: ("Retried", "`BackendUnavailable`"),
    403: ("Not retried", "`PermissionDenied`"),
    404: ("Not retried", "`NotFound`"),
    409: ("Not retried", "`AlreadyExists`"),
    423: ("Not retried", "`ResourceLocked`"),
    507: ("Not retried", "`BackendUnavailable`"),
}

# Per-backend transport retry mechanism, keyed by registry ``type`` string. The
# mechanism is not a graph node, so the prose is curated here; the key-set is
# drift-guarded against the registry order in project_retryability().
# Prose only — spec-clause IDs (RET-014, SFTP-009, …) stay out of the rendered
# cells because FEATURES.md is a published surface (check_no_tracker_refs).
_RETRY_MECHANISM: dict[str, str] = {
    "local": "— (no `retry` parameter)",
    "memory": "— (no `retry` parameter)",
    "http": "Hand-rolled loop over the shared backoff helpers",
    "azure": "Azure SDK `ExponentialRetry` (all five `RetryPolicy` fields)",
    "s3": "botocore `standard` mode — honours `max_attempts` only",
    "s3-pyarrow": "`AwsStandardS3RetryStrategy` — honours `max_attempts` only",
    "sftp": "`tenacity` — connection-scope only (reconnect, not per-request)",
    "sql-blob": "— (errors mapped, not retried)",
    "sql-query": "— (errors mapped, not retried)",
}

# Per-backend × per-op atomicity, keyed by registry ``type`` string then op.
# Cells name the mechanism: "Atomic" for an atomic op, the non-atomic mechanism
# otherwise, and "— (read-only)" for backends that reject the op. read/list/
# metadata are non-mutating (atomicity N/A) and delete / folder ops are a
# documented gap (no backend specifies their atomicity) — both are intentionally
# omitted rather than guessed. The ``move`` cell is cross-checked against the
# graph's ATOMIC_MOVE capability in project_atomicity(); the two
# mechanism-atomic-but-undeclared cases (Azure HNS, SFTP posix_rename) read
# "Copy+delete†" and carry the † footnote.
_ATOMICITY: dict[str, dict[str, str]] = {
    "local": {"write": "Direct", "write_atomic": "Atomic", "move": r"Atomic\*", "copy": "Copy+delete"},
    "memory": {"write": "Atomic", "write_atomic": "Atomic", "move": "Atomic", "copy": "Atomic"},
    "http": {
        "write": "— (read-only)",
        "write_atomic": "— (read-only)",
        "move": "— (read-only)",
        "copy": "— (read-only)",
    },
    "azure": {"write": "Atomic§", "write_atomic": "Atomic", "move": "Copy+delete†", "copy": "Copy+delete"},
    "s3": {"write": "Atomic", "write_atomic": "Atomic", "move": "Copy+delete", "copy": "Copy+delete"},
    "s3-pyarrow": {"write": "Streamed‡", "write_atomic": "Atomic", "move": "Copy+delete", "copy": "Copy+delete"},
    "sftp": {"write": "Streamed", "write_atomic": "Atomic", "move": "Copy+delete†", "copy": "Copy+delete"},
    "sql-blob": {"write": "Atomic", "write_atomic": "Atomic", "move": "Atomic", "copy": "Atomic"},
    "sql-query": {
        "write": "— (read-only)",
        "write_atomic": "— (read-only)",
        "move": "— (read-only)",
        "copy": "— (read-only)",
    },
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


# --- ID-227 Phase 2: read-after-write consistency matrix -------------------

# Per-backend read-after-write consistency, keyed by registry ``type`` string.
# ``raw`` = a read/head after a write, overwrite, or delete reflects the change;
# ``listing`` = a listing/enumeration taken after the call returns reflects it.
# Every read/write backend normalises to strong read-after-write; read-only
# backends have no write surface. The consistency *class* is a vendor/OS fact,
# not a code constant, so cells are curated here and the key-set is drift-guarded
# against the registry. The one in-repo cross-check — S3's listings-cache-off
# default, which backs the ``*`` footnote — is guarded live in
# project_consistency() against remote_store.backends._s3_base.
_CONSISTENCY: dict[str, dict[str, str]] = {
    "local": {"raw": "Strong", "listing": "Strong"},
    "memory": {"raw": "Strong", "listing": "Strong"},
    "http": {"raw": "— (read-only)", "listing": "— (read-only)"},
    "azure": {"raw": "Strong", "listing": "Strong"},
    "s3": {"raw": "Strong", "listing": r"Strong\*"},
    "s3-pyarrow": {"raw": "Strong", "listing": r"Strong\*"},
    "sftp": {"raw": "Strong", "listing": "Strong"},
    "sql-blob": {"raw": "Strong", "listing": "Strong"},
    "sql-query": {"raw": "— (read-only)", "listing": "— (read-only)"},
}

# Native async backends, keyed by class name (no registry ``type`` string).
# AsyncAzure / AsyncMemory mirror their sync peer; the async-only GraphBackend's
# read-your-writes holds, but ``copy`` (always) and a large / cross-folder
# ``move`` (sometimes) run server-side and are monitor-polled to completion
# before the call returns — the ``†`` footnote. Key-set drift-guarded against the
# graph's async backend nodes.
_CONSISTENCY_ASYNC: dict[str, dict[str, str]] = {
    "AsyncAzureBackend": {"raw": "Strong", "listing": "Strong"},
    "AsyncMemoryBackend": {"raw": "Strong", "listing": "Strong"},
    "GraphBackend": {"raw": "Strong†", "listing": "Strong†"},
}


# --- ID-227 Phase 3: per-operation cost model ------------------------------

# Structural cost of the three read-path operations, keyed by registry ``type``
# string. ``read`` is the streaming-vs-materialised class and is cross-checked
# live against the graph's LAZY_READ capability in project_cost() (a cell starts
# with "Streaming" iff LAZY_READ is declared) — the one machine-harvestable cost
# signal, mirroring phase 1's ATOMIC_MOVE cross-check on the ``move`` cell.
# ``metadata`` / ``list`` are structural facts no capability encodes, curated
# here with a registry key-set membership guard. Cells name the mechanism so the
# cost class is visible at a glance. This is the *structural* cost (what the API
# shape forces per call), distinct from the measured benchmark overhead in
# explanation/performance.md.
_COST: dict[str, dict[str, str]] = {
    "local": {"read": "Streaming", "metadata": "`stat` syscall", "list": "`scandir` walk"},
    "memory": {"read": r"Buffered in memory\*", "metadata": "Dict lookup", "list": "Dict scan"},
    "http": {"read": "Streaming", "metadata": "1 HEAD", "list": "— (no `LIST`)"},
    "azure": {"read": "Streaming", "metadata": "1 HEAD", "list": "Paginated `LIST`"},
    "s3": {"read": "Streaming", "metadata": "1 HEAD", "list": "Paginated `LIST`"},
    "s3-pyarrow": {"read": "Streaming", "metadata": "1 HEAD", "list": "Paginated `LIST`"},
    "sftp": {"read": "Streaming", "metadata": "1 `stat` round-trip", "list": "Directory walk"},
    "sql-blob": {"read": r"Full BLOB into memory\*", "metadata": "1 `SELECT`", "list": "1 `SELECT`"},
    "sql-query": {"read": r"Query run, buffered\*", "metadata": "Registry lookup", "list": "Registry scan"},
}

# Native async backends, keyed by class name (mirrors _CONSISTENCY_ASYNC). The
# async-only GraphBackend streams reads (LAZY_READ) but blocks copy/move on a
# server-side monitor — a latency captured in the table's lead-in prose, not a
# read/metadata/list column. Key-set drift-guarded against the graph's async
# backend nodes. Note AsyncMemoryBackend DOES stream (it declares LAZY_READ)
# where its sync mirror buffers — the read/LAZY_READ cross-check keeps the two
# rows from silently converging.
_COST_ASYNC: dict[str, dict[str, str]] = {
    "AsyncAzureBackend": {"read": "Streaming", "metadata": "1 HEAD", "list": "Paginated `LIST`"},
    "AsyncMemoryBackend": {"read": "Streaming", "metadata": "Dict lookup", "list": "Dict scan"},
    "GraphBackend": {"read": "Streaming", "metadata": "1 GET", "list": "Paginated GETs"},
}


def _load_graph() -> dict:
    with open(GRAPH, encoding="utf-8") as f:
        return json.load(f)


def _load_pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# Graph query helpers
# ---------------------------------------------------------------------------


def _parse_registry_order() -> list[tuple[str, str]]:
    """Return [(type_string, class_name)] in register_backend() declaration order."""
    source = (SRC / "remote_store" / "_registry.py").read_text(encoding="utf-8")
    pattern = re.compile(r'register_backend\(\s*"([^"]+)"\s*,\s*(\w+)\s*\)')
    return [(m.group(1), m.group(2)) for m in pattern.finditer(source)]


def _cls_qname_map(graph: dict) -> dict[str, str]:
    """Return {class_name → qualified_name} for sync backend nodes."""
    result: dict[str, str] = {}
    for node in graph["nodes"]:
        if node["kind"] == "class" and node.get("role") == "backend" and node.get("runtime") == "sync":
            qname = node["id"].removeprefix("cls:")
            cls_name = qname.rsplit(".", 1)[-1]
            result[cls_name] = qname
    return result


def _async_backend_nodes(graph: dict) -> list[tuple[str, str]]:
    """Return [(class_name, cls_uri)] for native async backend nodes, sorted by name.

    Native async backends carry no RegistryConfig ``type=`` string (there is no
    async config registry — they are constructed directly via
    ``AsyncStore(backend=...)``), so they are keyed by class name rather than
    by the sync registry order.
    """
    result: list[tuple[str, str]] = []
    for node in graph["nodes"]:
        if node["kind"] == "class" and node.get("role") == "backend" and node.get("runtime") == "async":
            cls_uri = node["id"]
            # Native backends live under ``remote_store.aio.backends.*``; this
            # excludes the ``AsyncBackend`` ABC (``aio._async_backend``) and the
            # ``SyncBackendAdapter`` bridge (``aio._sync_adapter``), mirroring how
            # the sync table is filtered to registered backends only.
            if ".aio.backends." not in cls_uri:
                continue
            cls_name = cls_uri.removeprefix("cls:").rsplit(".", 1)[-1]
            result.append((cls_name, cls_uri))
    return sorted(result)


def _async_backend_extras(graph: dict) -> dict[str, str]:
    """Return {cls_uri → extra_name} for async backends (``.aio.`` enables edges)."""
    extras: dict[str, str] = {}
    for edge in graph["edges"]:
        if edge["kind"] == "enables" and ".aio." in edge["dst"]:
            extras[edge["dst"]] = edge["src"].removeprefix("xtr:")
    return extras


def _build_lookups(
    graph: dict,
) -> tuple[dict[str, frozenset[str]], dict[str, str]]:
    """Return (backend_declares, backend_extras):
    - backend_declares: {cls_uri → frozenset of cap names}
    - backend_extras: {cls_uri → extra_name}  (sync backends only)
    """
    backend_declares: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        if edge["kind"] == "declares":
            backend_declares.setdefault(edge["src"], set()).add(edge["dst"].removeprefix("cap:"))

    backend_extras: dict[str, str] = {}
    for edge in graph["edges"]:
        if edge["kind"] == "enables" and ".aio." not in edge["dst"]:
            backend_extras[edge["dst"]] = edge["src"].removeprefix("xtr:")

    return {k: frozenset(v) for k, v in backend_declares.items()}, backend_extras


def _baseline_caps(graph: dict) -> list[str]:
    """Ordered non-flag capability names (alphabetical, same order as graph nodes)."""
    return [
        n["id"].removeprefix("cap:")
        for n in graph["nodes"]
        if n["kind"] == "capability" and n["id"].removeprefix("cap:") not in _FLAGS_CAPS
    ]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_caps(declared: frozenset[str], baseline: list[str]) -> str:
    """Format a backend's declared capabilities relative to the baseline."""
    present = [c for c in baseline if c in declared]
    missing = [c for c in baseline if c not in declared]

    if not missing:
        return "All"
    if len(present) > len(missing):
        return "All except " + ", ".join(f"`{c}`" for c in missing)
    return ", ".join(f"`{c}`" for c in present)


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


def project_backends_main(graph: dict) -> str:
    """Return the generated backends capability table (Markdown)."""
    qname_map = _cls_qname_map(graph)
    declares, extras = _build_lookups(graph)
    baseline = _baseline_caps(graph)
    registry = _parse_registry_order()

    lines = [
        "| Type | Class | Extra | Capabilities |",
        "|---|---|---|---|",
    ]
    for type_str, cls_name in sorted(registry):
        qname = qname_map.get(cls_name)
        if qname is None:
            continue
        cls_uri = f"cls:{qname}"
        declared = declares.get(cls_uri, frozenset())
        extra = extras.get(cls_uri)
        extra_cell = _EXTRA_CELL_OVERRIDES.get(type_str, f"`remote-store[{extra}]`" if extra else "—")
        caps_cell = _format_caps(declared, baseline)
        lines.append(f"| `{type_str}` | `{cls_name}` | {extra_cell} | {caps_cell} |")

    return "\n".join(lines)


def project_backends_flags(graph: dict) -> str:
    """Return the generated write-result flags table (Markdown)."""
    qname_map = _cls_qname_map(graph)
    declares, _ = _build_lookups(graph)
    registry = _parse_registry_order()

    lines = [
        "| Backend | `WRITE_RESULT_NATIVE` | `USER_METADATA` |",
        "|---|---|---|",
    ]
    for type_str, cls_name in sorted(registry):
        qname = qname_map.get(cls_name)
        if qname is None:
            continue
        cls_uri = f"cls:{qname}"
        declared = declares.get(cls_uri, frozenset())

        def _cell(cap: str, _ts: str = type_str, _d: frozenset = declared) -> str:
            note = _FLAGS_NOTES.get((_ts, cap))
            return note if note else ("Yes" if cap in _d else "—")

        lines.append(f"| `{type_str}` | {_cell('WRITE_RESULT_NATIVE')} | {_cell('USER_METADATA')} |")

    return "\n".join(lines)


def project_backends_async(graph: dict) -> str:
    """Return the generated native-async-backend capability table (Markdown)."""
    declares, _ = _build_lookups(graph)
    extras = _async_backend_extras(graph)
    baseline = _baseline_caps(graph)

    lines = [
        "| Class | Extra | Capabilities |",
        "|---|---|---|",
    ]
    for cls_name, cls_uri in _async_backend_nodes(graph):
        declared = declares.get(cls_uri, frozenset())
        extra = extras.get(cls_uri)
        extra_cell = f"`remote-store[{extra}]`" if extra else "—"
        caps_cell = _format_caps(declared, baseline)
        lines.append(f"| `{cls_name}` | {extra_cell} | {caps_cell} |")

    return "\n".join(lines)


def project_backends_async_flags(graph: dict) -> str:
    """Return the generated native-async-backend write-result flags table (Markdown)."""
    declares, _ = _build_lookups(graph)

    lines = [
        "| Class | `WRITE_RESULT_NATIVE` | `USER_METADATA` |",
        "|---|---|---|",
    ]
    for cls_name, cls_uri in _async_backend_nodes(graph):
        declared = declares.get(cls_uri, frozenset())
        wrn = "Yes" if "WRITE_RESULT_NATIVE" in declared else "—"
        um = "Yes" if "USER_METADATA" in declared else "—"
        lines.append(f"| `{cls_name}` | {wrn} | {um} |")

    return "\n".join(lines)


def _store_gate_lookup(graph: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Walk ``cap:X ←(of)— req:*.gate —(gates)→ mtd:*`` for the Store facade.

    Returns ``(primary, depth)``:
    - ``primary`` maps each gating capability name → sorted Store method names
      gated by it through a ``.gate`` requirement (the method's primary gate).
    - ``depth`` maps a Store method name → the capability of its ``.gate_depth``
      secondary requirement (only ``get_folder_info`` → ``LIST`` at 1.4). These
      become the dual-gate footnote rather than a primary table row.
    """
    of_cap: dict[str, str] = {e["src"]: e["dst"].removeprefix("cap:") for e in graph["edges"] if e["kind"] == "of"}
    primary: dict[str, set[str]] = {}
    depth: dict[str, str] = {}
    for edge in graph["edges"]:
        if edge["kind"] != "gates":
            continue
        req, mtd = edge["src"], edge["dst"]
        if not mtd.startswith(_STORE_MTD_PREFIX) or not req.startswith(_STORE_REQ_PREFIX):
            continue
        method = mtd.removeprefix(_STORE_MTD_PREFIX)
        cap = of_cap[req]
        if req.endswith(".gate_depth"):
            depth[method] = cap
        else:
            primary.setdefault(cap, set()).add(method)
    return {cap: sorted(methods) for cap, methods in primary.items()}, depth


def project_store_api_gated(graph: dict) -> str:
    """Return the generated capability→gated-method table for the Store API."""
    primary, depth = _store_gate_lookup(graph)

    lines = [
        "| Capability | Gated methods |",
        "|---|---|",
    ]
    for cap in sorted(primary):
        cells = []
        for method in primary[cap]:
            marker = r"\*" if method in depth else ""
            cells.append(f"`{method}()`{marker}")
        lines.append(f"| `{cap}` | {', '.join(cells)} |")

    # Dual-gate footnote (DGM-014 / get_folder_info): a method with a secondary
    # ``.gate_depth`` requirement is additionally gated on that capability when
    # called with ``max_depth``.
    for method in sorted(depth):
        lines.append("")
        lines.append(
            rf"\* `{method}()` is additionally gated on `{depth[method]}` when called with "
            "`max_depth` (depth-limited traversal)."
        )

    return "\n".join(lines)


def project_store_api_ungated(graph: dict) -> str:
    """Return the generated ungated ("always available") Store method table.

    Membership is graph-derived (Store method nodes with ``gated == false``,
    DGM-014); the Returns/Description prose is curated in ``_UNGATED_STORE_DETAILS``.
    A mismatch between the two fails generation, so adding or removing an ungated
    Store method forces both a graph regen and a prose update.
    """
    graph_ungated = {
        n["id"].removeprefix(_STORE_MTD_PREFIX)
        for n in graph["nodes"]
        if n["kind"] == "method" and n["id"].startswith(_STORE_MTD_PREFIX) and n.get("gated") is False
    }
    curated = set(_UNGATED_STORE_DETAILS)
    if graph_ungated != curated:
        raise ValueError(
            "Ungated Store methods drifted from _UNGATED_STORE_DETAILS.\n"
            f"  in graph but not curated: {sorted(graph_ungated - curated)}\n"
            f"  curated but not in graph: {sorted(curated - graph_ungated)}\n"
            "Update _UNGATED_STORE_DETAILS in scripts/gen_features.py and regenerate."
        )

    lines = [
        "| Method | Returns | Description |",
        "|---|---|---|",
    ]
    for signature, returns, description in _UNGATED_STORE_DETAILS.values():
        lines.append(f"| `{signature}` | {returns} | {description} |")

    return "\n".join(lines)


def project_async_backend_pairs(graph: dict) -> str:
    """Return the generated sync↔async backend equivalence table from ``mirrors`` edges.

    Each ``mirrors`` edge pairs an async backend (canonical ``src``) with its sync
    peer (``dst``) and carries ``capability_delta``; this renders that pairing
    mechanically, replacing the former hand-written prose. Async-only backends
    (e.g. ``GraphBackend``) have no mirror and are documented separately.
    """
    rows: list[tuple[str, str, str]] = []
    for edge in graph["edges"]:
        if edge["kind"] != "mirrors":
            continue
        async_name = edge["src"].removeprefix("cls:").rsplit(".", 1)[-1]
        sync_name = edge["dst"].removeprefix("cls:").rsplit(".", 1)[-1]
        delta = edge.get("capability_delta", {})
        parts = []
        if delta.get("async_only"):
            parts.append("async adds " + ", ".join(f"`{c}`" for c in delta["async_only"]))
        if delta.get("sync_only"):
            parts.append("sync adds " + ", ".join(f"`{c}`" for c in delta["sync_only"]))
        rows.append((sync_name, async_name, "; ".join(parts) if parts else "—"))

    lines = [
        "| Sync backend | Async backend | Capability delta |",
        "|---|---|---|",
    ]
    for sync_name, async_name, delta_cell in sorted(rows):
        lines.append(f"| `{sync_name}` | `{async_name}` | {delta_cell} |")

    return "\n".join(lines)


def project_install_extras(pyproject: dict) -> str:
    """Return the generated install extras code block (Markdown)."""
    opt_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    pkg = pyproject["project"]["name"]

    entries: list[tuple[str, str | None]] = []
    for extra in sorted(opt_deps):
        if extra in _EXCLUDE_EXTRAS:
            continue
        cmd = f"pip install {pkg}[{extra}]"
        entries.append((cmd, _EXTRA_COMMENTS.get(extra)))

    max_cmd = max((len(cmd) for cmd, _ in entries), default=0)

    lines = ["```"]
    for cmd, comment in entries:
        if comment:
            lines.append(f"{cmd:{max_cmd}}  # {comment}")
        else:
            lines.append(cmd)
    lines.append("```")

    return "\n".join(lines)


def project_retryability(graph: dict) -> str:
    """Return the retry-classification + per-backend transport-mechanism tables.

    The retried/terminal *split* is imported live from ``remote_store._retry``
    (``RETRYABLE_STATUSES`` / ``TERMINAL_STATUSES``) so it can never drift from the
    code; ``_STATUS_DETAIL`` only supplies the disposition + typed error and is
    guarded to cover exactly that union. The per-backend mechanism rows are curated
    (no graph node models transport retry) and their key-set is drift-guarded
    against the registry order.
    """
    from remote_store._retry import RETRYABLE_STATUSES, TERMINAL_STATUSES

    # The http backend extends the shared retryable set with 408 (a transport-
    # local addition, not part of _retry.RETRYABLE_STATUSES). Guard the extension
    # live so the http-row † footnote below can never silently drift from the
    # code: a new http-local status forces the footnote to be updated.
    from remote_store.backends._http import _TRANSIENT_STATUSES

    http_extra = _TRANSIENT_STATUSES - RETRYABLE_STATUSES
    if http_extra != {408}:
        raise ValueError(
            "http backend transient-status extension drifted from the footnote.\n"
            f"  _http._TRANSIENT_STATUSES - RETRYABLE_STATUSES = {sorted(http_extra)}, expected [408].\n"
            "Update the http `†` footnote in scripts/gen_features.py project_retryability()."
        )

    universe = RETRYABLE_STATUSES | TERMINAL_STATUSES
    if set(_STATUS_DETAIL) != universe:
        raise ValueError(
            "Retry status detail drifted from remote_store._retry.\n"
            f"  in code but not detailed: {sorted(universe - set(_STATUS_DETAIL))}\n"
            f"  detailed but not in code: {sorted(set(_STATUS_DETAIL) - universe)}\n"
            "Update _STATUS_DETAIL in scripts/gen_features.py."
        )

    status_lines = [
        "| Status | Disposition | Surfaced as |",
        "|---|---|---|",
    ]
    for status in sorted(RETRYABLE_STATUSES) + sorted(TERMINAL_STATUSES):
        disposition, error = _STATUS_DETAIL[status]
        status_lines.append(f"| `{status}` | {disposition} | {error} |")

    registry = _parse_registry_order()
    types = {t for t, _ in registry}
    if types != set(_RETRY_MECHANISM):
        raise ValueError(
            "Backend retry mechanisms drifted from the registry.\n"
            f"  registered but no mechanism: {sorted(types - set(_RETRY_MECHANISM))}\n"
            f"  mechanism but not registered: {sorted(set(_RETRY_MECHANISM) - types)}\n"
            "Update _RETRY_MECHANISM in scripts/gen_features.py."
        )

    mech_lines = [
        "| Backend | Transport retry mechanism |",
        "|---|---|",
    ]
    for type_str, _ in sorted(registry):
        marker = "†" if type_str == "http" else ""
        mech_lines.append(f"| `{type_str}` | {_RETRY_MECHANISM[type_str]}{marker} |")

    footnote = (
        "† `http` additionally retries `408 Request Timeout` (classified as "
        "`BackendUnavailable`) — a transport-local extension of the shared "
        "retryable set above."
    )

    return "\n".join(status_lines) + "\n\n" + "\n".join(mech_lines) + "\n\n" + footnote


def project_atomicity(graph: dict) -> str:
    """Return the per-backend × per-op atomicity matrix.

    Atomicity mostly lives in prose, not a graph node, so the cells are curated in
    ``_ATOMICITY``; the backend key-set is drift-guarded against the registry, and
    each ``move`` cell is cross-checked against the graph's ``ATOMIC_MOVE``
    capability so a curated "Atomic" move cannot contradict the advertised
    capability (the two mechanism-atomic-but-undeclared cases — Azure HNS, SFTP
    ``posix_rename`` — read "Copy+delete†" and are covered by the † footnote).
    """
    qname_map = _cls_qname_map(graph)
    declares, _ = _build_lookups(graph)
    registry = _parse_registry_order()

    types = {t for t, _ in registry}
    if types != set(_ATOMICITY):
        raise ValueError(
            "Atomicity rows drifted from the registry.\n"
            f"  registered but no row: {sorted(types - set(_ATOMICITY))}\n"
            f"  row but not registered: {sorted(set(_ATOMICITY) - types)}\n"
            "Update _ATOMICITY in scripts/gen_features.py."
        )

    ops = ("write", "write_atomic", "move", "copy")
    lines = [
        "| Backend | `write` | `write_atomic` | `move` | `copy` |",
        "|---|---|---|---|---|",
    ]
    for type_str, cls_name in sorted(registry):
        cells = _ATOMICITY[type_str]
        qname = qname_map.get(cls_name)
        declared = declares.get(f"cls:{qname}", frozenset()) if qname else frozenset()
        move_atomic = cells["move"].startswith("Atomic")
        if move_atomic != ("ATOMIC_MOVE" in declared):
            raise ValueError(
                f"Atomicity 'move' cell for {type_str!r} disagrees with the graph's "
                f"ATOMIC_MOVE capability: cell={cells['move']!r}, ATOMIC_MOVE="
                f"{'declared' if 'ATOMIC_MOVE' in declared else 'absent'}. "
                "Reconcile _ATOMICITY in scripts/gen_features.py with the backend's caps."
            )
        row = " | ".join(cells[op] for op in ops)
        lines.append(f"| `{type_str}` | {row} |")

    lines.append("")
    lines.append(
        r"\* `local` `move` is atomic within one filesystem (`os.rename`); a "
        "cross-filesystem move falls back to copy-then-delete."
    )
    lines.append(
        "† Azure and SFTP `move` use a native rename that is atomic (Azure HNS "
        "`rename_file`, SFTP `posix_rename`), but `ATOMIC_MOVE` is not advertised "
        "because it cannot be guaranteed across all configurations (non-HNS Azure "
        "accounts, non-POSIX SFTP servers)."
    )
    lines.append(
        "‡ `s3-pyarrow` plain `write` streams straight to a multipart upload; "
        "PyArrow's stream exposes no abort, so a mid-stream failure finalises a "
        "*truncated* object. `write_atomic` buffers the body first, so a failure "
        "leaves no object."
    )
    lines.append(
        "§ `azure` `write` commits atomically on flat (non-HNS) accounts; on "
        "hierarchical-namespace accounts use `write_atomic` for a guaranteed "
        "atomic replace."
    )

    return "\n".join(lines)


def project_consistency(graph: dict) -> str:
    """Return the per-backend read-after-write consistency matrix (sync + async).

    Two dimensions per backend: ``raw`` (a read/head after a write, overwrite, or
    delete reflects the change) and ``listing`` (a listing after the call returns
    reflects it). The class is a vendor/OS fact, so the cells are curated in
    ``_CONSISTENCY`` / ``_CONSISTENCY_ASYNC`` and their key-sets are drift-guarded
    against the registry and the graph's async backend nodes. The single in-repo
    cross-check — S3's listings-cache-off default backing the ``*`` footnote — is
    guarded live against ``_s3_base._DEFAULT_USE_LISTINGS_CACHE`` so flipping the
    default forces the footnote to be rewritten.
    """
    from remote_store.backends._s3_base import _DEFAULT_USE_LISTINGS_CACHE

    if _DEFAULT_USE_LISTINGS_CACHE is not False:
        raise ValueError(
            "S3 default use_listings_cache flipped on; the consistency `*` footnote "
            "(s3 / s3-pyarrow listings strong by default) is now wrong: "
            f"_DEFAULT_USE_LISTINGS_CACHE={_DEFAULT_USE_LISTINGS_CACHE!r}. "
            "Update project_consistency() in scripts/gen_features.py."
        )

    registry = _parse_registry_order()
    types = {t for t, _ in registry}
    if types != set(_CONSISTENCY):
        raise ValueError(
            "Consistency rows drifted from the registry.\n"
            f"  registered but no row: {sorted(types - set(_CONSISTENCY))}\n"
            f"  row but not registered: {sorted(set(_CONSISTENCY) - types)}\n"
            "Update _CONSISTENCY in scripts/gen_features.py."
        )

    async_names = {name for name, _ in _async_backend_nodes(graph)}
    if async_names != set(_CONSISTENCY_ASYNC):
        raise ValueError(
            "Async consistency rows drifted from the graph's async backends.\n"
            f"  in graph but no row: {sorted(async_names - set(_CONSISTENCY_ASYNC))}\n"
            f"  row but not in graph: {sorted(set(_CONSISTENCY_ASYNC) - async_names)}\n"
            "Update _CONSISTENCY_ASYNC in scripts/gen_features.py."
        )

    sync_lines = [
        "| Backend | Read-after-write | Listing consistency |",
        "|---|---|---|",
    ]
    for type_str, _ in sorted(registry):
        cells = _CONSISTENCY[type_str]
        sync_lines.append(f"| `{type_str}` | {cells['raw']} | {cells['listing']} |")

    async_lines = [
        "The async-native backends inherit their sync peer's consistency; the "
        "async-only `GraphBackend` is the one distinct case.",
        "",
        "| Async backend | Read-after-write | Listing consistency |",
        "|---|---|---|",
    ]
    for cls_name in sorted(_CONSISTENCY_ASYNC):
        cells = _CONSISTENCY_ASYNC[cls_name]
        async_lines.append(f"| `{cls_name}` | {cells['raw']} | {cells['listing']} |")

    footnotes = [
        r"\* `s3` / `s3-pyarrow` listings are strongly consistent by default: the "
        "backend leaves the s3fs directory cache **off** (`use_listings_cache=False`), "
        "so a listing taken after a write reflects it. Opting into "
        "`client_options['use_listings_cache']` trades this for a cache that never "
        "expires — a listing can then stay blind to a cross-writer change until the "
        "backend is rebuilt.",
        "† `GraphBackend` read-your-writes holds on one instance (a write is committed "
        "to two datacentre regions before it is acknowledged). `copy` (always) and a "
        "large or cross-folder `move` (sometimes) run server-side and are polled to "
        "completion before the call returns, so a read or listing afterwards reflects "
        "the result.",
    ]

    return "\n".join(sync_lines) + "\n\n" + "\n".join(async_lines) + "\n\n" + "\n".join(footnotes)


def project_cost(graph: dict) -> str:
    """Return the per-backend per-operation cost matrix (sync + async).

    Three read-path operations: ``read`` (streaming vs full materialisation),
    ``metadata`` (a head / exists probe), and ``list`` (enumeration). The ``read``
    cell is cross-checked live against the graph's ``LAZY_READ`` capability — it
    must start with "Streaming" exactly when the backend declares ``LAZY_READ`` —
    the one machine-harvestable cost signal (mirrors ``project_atomicity``'s
    ``ATOMIC_MOVE`` cross-check). ``metadata`` / ``list`` are curated structural
    facts with a registry / async-node key-set membership guard.
    """
    qname_map = _cls_qname_map(graph)
    declares, _ = _build_lookups(graph)
    registry = _parse_registry_order()

    types = {t for t, _ in registry}
    if types != set(_COST):
        raise ValueError(
            "Cost rows drifted from the registry.\n"
            f"  registered but no row: {sorted(types - set(_COST))}\n"
            f"  row but not registered: {sorted(set(_COST) - types)}\n"
            "Update _COST in scripts/gen_features.py."
        )

    async_names = {name for name, _ in _async_backend_nodes(graph)}
    if async_names != set(_COST_ASYNC):
        raise ValueError(
            "Async cost rows drifted from the graph's async backends.\n"
            f"  in graph but no row: {sorted(async_names - set(_COST_ASYNC))}\n"
            f"  row but not in graph: {sorted(set(_COST_ASYNC) - async_names)}\n"
            "Update _COST_ASYNC in scripts/gen_features.py."
        )

    def _check_read_vs_lazy(name: str, cell: str, cls_uri: str | None) -> None:
        declared = declares.get(cls_uri, frozenset()) if cls_uri else frozenset()
        if cell.startswith("Streaming") != ("LAZY_READ" in declared):
            raise ValueError(
                f"Cost 'read' cell for {name!r} disagrees with the graph's LAZY_READ "
                f"capability: cell={cell!r}, LAZY_READ="
                f"{'declared' if 'LAZY_READ' in declared else 'absent'}. "
                "Reconcile _COST / _COST_ASYNC in scripts/gen_features.py with the backend's caps."
            )

    ops = ("read", "metadata", "list")
    sync_lines = [
        "| Backend | `read` | `metadata` | `list` |",
        "|---|---|---|---|",
    ]
    for type_str, cls_name in sorted(registry):
        cells = _COST[type_str]
        qname = qname_map.get(cls_name)
        _check_read_vs_lazy(type_str, cells["read"], f"cls:{qname}" if qname else None)
        row = " | ".join(cells[op] for op in ops)
        sync_lines.append(f"| `{type_str}` | {row} |")

    async_lines = [
        "The async-native backends inherit their sync peer's per-op cost; the "
        "async-only `GraphBackend` streams reads but blocks `copy` (always) and a "
        "large or cross-folder `move` on a server-side monitor polled to completion "
        "— a per-call latency the columns below do not show.",
        "",
        "| Async backend | `read` | `metadata` | `list` |",
        "|---|---|---|---|",
    ]
    for cls_name, cls_uri in _async_backend_nodes(graph):
        cells = _COST_ASYNC[cls_name]
        _check_read_vs_lazy(cls_name, cells["read"], cls_uri)
        row = " | ".join(cells[op] for op in ops)
        async_lines.append(f"| `{cls_name}` | {row} |")

    footnote = (
        r"\* `memory` (sync), `sql-blob`, and `sql-query` do not stream a read "
        "(`LAZY_READ` absent): each holds the whole object in memory before `read()` "
        "returns — `sql-blob` loads the full BLOB, `sql-query` buffers the serialised "
        "query result, and sync `memory` keeps the value resident (its async peer "
        "`AsyncMemoryBackend` yields chunks and *does* stream). `sql-blob` likewise "
        "buffers the entire body before the write `INSERT`/`UPDATE`. For objects "
        "larger than process memory use a streaming backend (Local, S3, Azure, SFTP)."
    )

    return "\n".join(sync_lines) + "\n\n" + "\n".join(async_lines) + "\n\n" + footnote


def project_all(graph: dict, pyproject: dict) -> dict[str, str]:
    """Return all projections keyed by region name."""
    return {
        "store_api_gated": project_store_api_gated(graph),
        "store_api_ungated": project_store_api_ungated(graph),
        "backends_main": project_backends_main(graph),
        "backends_flags": project_backends_flags(graph),
        "backends_async": project_backends_async(graph),
        "backends_async_flags": project_backends_async_flags(graph),
        "async_backend_pairs": project_async_backend_pairs(graph),
        "retryability": project_retryability(graph),
        "atomicity": project_atomicity(graph),
        "consistency": project_consistency(graph),
        "cost": project_cost(graph),
        "install_extras": project_install_extras(pyproject),
    }


# ---------------------------------------------------------------------------
# Region replacement
# ---------------------------------------------------------------------------

_REGION_RE = re.compile(
    r"(<!-- BEGIN_GENERATED:(\w+) -->)\n.*?\n(<!-- END_GENERATED:\2 -->)",
    re.DOTALL,
)


def _replace_regions(text: str, projections: dict[str, str]) -> str:
    matched: set[str] = set()

    def _sub(m: re.Match) -> str:
        name = m.group(2)
        if name not in projections:
            return m.group(0)
        matched.add(name)
        return f"{m.group(1)}\n{projections[name]}\n{m.group(3)}"

    result = _REGION_RE.sub(_sub, text)
    missing = set(projections) - matched
    if missing:
        raise ValueError(f"Projection keys not found in document: {sorted(missing)}")
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Project graph.json → mechanical sections of FEATURES.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if FEATURES.md would change; do not write.",
    )
    args = parser.parse_args()

    graph = _load_graph()
    pyproject = _load_pyproject()
    projections = project_all(graph, pyproject)

    original = FEATURES.read_text(encoding="utf-8")
    # Normalise CRLF → LF so comparisons are platform-neutral.
    original_lf = original.replace("\r\n", "\n")
    updated = _replace_regions(original_lf, projections)

    if args.check:
        if original_lf != updated:
            print(
                "FEATURES.md generated regions are out of date.\nRun:  hatch run gen-features",
                file=sys.stderr,
            )
            sys.exit(1)
        print("FEATURES.md is up to date.")
        return

    if original_lf != updated:
        FEATURES.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Updated {FEATURES.relative_to(ROOT)}")
    else:
        print("FEATURES.md is already up to date.")


if __name__ == "__main__":
    main()
