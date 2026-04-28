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

# Extras omitted from the install extras section (dev / build tooling).
_EXCLUDE_EXTRAS: frozenset[str] = frozenset({"bench", "dev", "docs"})

# Override the auto-derived Extra cell for backends whose install story cannot be
# expressed as a single pip extra (e.g. stdlib-first with optional adapters).
_EXTRA_CELL_OVERRIDES: dict[str, str] = {
    "http": "— (stdlib; `requests`/`httpx` optional)",
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


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


def project_all(graph: dict, pyproject: dict) -> dict[str, str]:
    """Return all projections keyed by region name."""
    return {
        "backends_main": project_backends_main(graph),
        "backends_flags": project_backends_flags(graph),
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
