"""MkDocs gen-files hook: generates dynamic pages and navigation.

Runs during the MkDocs build via mkdocs-gen-files.  Static authored content
lives in docs-src/ (the docs_dir).  This script handles only:

  1. Scanning sdd/ for specs, ADRs, RFCs, and research docs
  2. Filling .tmpl templates with dynamic rows
  3. Creating include-wrapper pages for each spec/ADR/RFC
  4. Rewriting links in contributing.md and design/process.md
  5. Copying assets/ into the virtual filesystem
  5b. Scanning examples/ and generating wrapper pages (ID-058)
  6. Assembling SUMMARY.md from per-section _nav.yml files

See: sdd/adrs/0007-docs-src-literate-nav.md
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import mkdocs_gen_files
import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = ROOT / "docs-src"

# ---------------------------------------------------------------------------
# 1. Scan sdd/ for specs, ADRs, RFCs, and research docs
# ---------------------------------------------------------------------------


def _scan_entries(
    directory: Path,
    glob_pattern: str,
    prefix_patterns: list[str] | None = None,
    skip_stems: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Return (number, stem, title) for each markdown file in *directory*."""
    skip = skip_stems or set()
    entries: list[tuple[str, str, str]] = []
    for p in sorted(directory.glob(glob_pattern)):
        if p.stem in skip:
            continue
        # Extract number from the filename
        if p.stem.startswith("rfc-"):
            parts = p.stem.split("-", 2)
            num = parts[1] if len(parts) > 1 else p.stem
        else:
            num = p.stem.split("-", 1)[0]
        # Read title from first heading
        first_line = p.read_text(encoding="utf-8").split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
        # Strip conventional prefixes like "ADR-0001: " or "Spec 001: "
        if prefix_patterns:
            for pattern in prefix_patterns:
                pfx = pattern.replace("{num}", num)
                if title.startswith(pfx):
                    title = title[len(pfx) :].strip()
                    break
        entries.append((num, p.stem, title))
    return entries


adr_entries = _scan_entries(
    ROOT / "sdd" / "adrs",
    "*.md",
    prefix_patterns=["ADR-{num}: "],
)
spec_entries = _scan_entries(
    ROOT / "sdd" / "specs",
    "*.md",
    prefix_patterns=["Spec {num}: ", "Spec-{num}: ", "{num}: "],
)
rfc_entries = _scan_entries(
    ROOT / "sdd" / "rfcs",
    "rfc-*.md",
    skip_stems={"rfc-template"},
)
research_entries = _scan_entries(
    ROOT / "sdd" / "research",
    "research-*.md",
    prefix_patterns=["Research: "],
)

# ---------------------------------------------------------------------------
# 2. Fill .tmpl templates → write as virtual pages
# ---------------------------------------------------------------------------

# --- design/adrs/index.md ---
adr_rows = "\n".join(f"| {num} | [{title}]({slug}.md) | Accepted |" for num, slug, title in adr_entries)
tmpl = (DOCS_SRC / "design" / "adrs" / "_index.tmpl").read_text(encoding="utf-8")
with mkdocs_gen_files.open("design/adrs/index.md", "w") as f:
    f.write(tmpl.replace("{{ adr_rows }}", adr_rows))

# --- design/specs/index.md ---
spec_rows = "\n".join(f"| {num} | [{title}]({slug}.md) |" for num, slug, title in spec_entries)
tmpl = (DOCS_SRC / "design" / "specs" / "_index.tmpl").read_text(encoding="utf-8")
with mkdocs_gen_files.open("design/specs/index.md", "w") as f:
    f.write(tmpl.replace("{{ spec_rows }}", spec_rows))

# --- design/rfcs/index.md ---
rfc_rows = "\n".join(f"| {num} | [{title}]({slug}.md) | Proposed |" for num, slug, title in rfc_entries)
tmpl = (DOCS_SRC / "design" / "rfcs" / "_index.tmpl").read_text(encoding="utf-8")
with mkdocs_gen_files.open("design/rfcs/index.md", "w") as f:
    f.write(tmpl.replace("{{ rfc_rows }}", rfc_rows))

# --- design/research/index.md ---
research_rows = "\n".join(f"| {title} | [{title}]({slug}.md) |" for _num, slug, title in research_entries)
tmpl = (DOCS_SRC / "design" / "research" / "_index.tmpl").read_text(encoding="utf-8")
with mkdocs_gen_files.open("design/research/index.md", "w") as f:
    f.write(tmpl.replace("{{ research_rows }}", research_rows))

# --- design/index.md ---
spec_links = "\n".join(f"- [{num}: {title}](specs/{slug}.md)" for num, slug, title in spec_entries)
adr_links = "\n".join(f"- [{num}: {title}](adrs/{slug}.md)" for num, slug, title in adr_entries)
rfc_links = "\n".join(f"- [{num}: {title}](rfcs/{slug}.md)" for num, slug, title in rfc_entries)
research_links = "\n".join(f"- [{title}](research/{slug}.md)" for _num, slug, title in research_entries)
tmpl = (DOCS_SRC / "design" / "_index.tmpl").read_text(encoding="utf-8")
with mkdocs_gen_files.open("design/index.md", "w") as f:
    f.write(
        tmpl.replace("{{ spec_links }}", spec_links)
        .replace("{{ adr_links }}", adr_links)
        .replace("{{ rfc_links }}", rfc_links)
        .replace("{{ research_links }}", research_links)
    )

# ---------------------------------------------------------------------------
# 3. Create wrapper pages for each spec, ADR, RFC
#
#    Virtual files cannot use include-markdown (paths would resolve against a
#    temp directory), so we read the source content and write it directly.
# ---------------------------------------------------------------------------

for _num, slug, _title in spec_entries:
    content = (ROOT / "sdd" / "specs" / f"{slug}.md").read_text(encoding="utf-8")
    with mkdocs_gen_files.open(f"design/specs/{slug}.md", "w") as f:
        f.write(content)

for _num, slug, _title in adr_entries:
    content = (ROOT / "sdd" / "adrs" / f"{slug}.md").read_text(encoding="utf-8")
    with mkdocs_gen_files.open(f"design/adrs/{slug}.md", "w") as f:
        f.write(content)

for _num, slug, _title in rfc_entries:
    content = (ROOT / "sdd" / "rfcs" / f"{slug}.md").read_text(encoding="utf-8")
    with mkdocs_gen_files.open(f"design/rfcs/{slug}.md", "w") as f:
        f.write(content)

for _num, slug, _title in research_entries:
    content = (ROOT / "sdd" / "research" / f"{slug}.md").read_text(encoding="utf-8")
    with mkdocs_gen_files.open(f"design/research/{slug}.md", "w") as f:
        f.write(content)

# RFC template (linked from CONTRIBUTING.md)
with mkdocs_gen_files.open("design/rfcs/rfc-template.md", "w") as f:
    f.write((ROOT / "sdd" / "rfcs" / "rfc-template.md").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# 4. Link-rewritten pages
#
#    These two source files contain relative links that target repo paths
#    (e.g. sdd/000-process.md) which differ from the docs-tree paths
#    (design/process.md).  We read, rewrite, and emit as virtual files.
# ---------------------------------------------------------------------------


def _rewrite_links(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# CONTRIBUTING.md → contributing.md
contributing_text = _rewrite_links(
    (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"),
    {
        "](sdd/000-process.md)": "](design/process.md)",
        "](sdd/rfcs/rfc-template.md)": "](design/rfcs/rfc-template.md)",
        "](sdd/DESIGN.md)": "](design/design-spec.md)",
        "](sdd/adrs/0008-extension-architecture.md)": "](design/adrs/0008-extension-architecture.md)",
        "](guides/custom-backend-guide.md)": "](custom-backend-guide.md)",
    },
)
with mkdocs_gen_files.open("contributing.md", "w") as f:
    f.write(contributing_text)

# sdd/000-process.md → design/process.md
process_text = _rewrite_links(
    (ROOT / "sdd" / "000-process.md").read_text(encoding="utf-8"),
    {
        "](../CONTRIBUTING.md#versioning)": "](../contributing.md#versioning)",
        "](BACKLOG.md)": "](https://github.com/haalfi/remote-store/blob/master/sdd/BACKLOG.md)",
        "](BACKLOG-DONE.md)": "](https://github.com/haalfi/remote-store/blob/master/sdd/BACKLOG-DONE.md)",
    },
)
with mkdocs_gen_files.open("design/process.md", "w") as f:
    f.write(process_text)

# ---------------------------------------------------------------------------
# 5. Copy assets
# ---------------------------------------------------------------------------

for asset in (ROOT / "assets").iterdir():
    if asset.is_file():
        with mkdocs_gen_files.open(f"assets/{asset.name}", "wb") as f:
            f.write(asset.read_bytes())

# ---------------------------------------------------------------------------
# 5b. Scan examples/ and generate wrapper pages + index  (ID-058)
#
#     Each example script has a module docstring whose first line becomes the
#     title, and the first paragraph becomes the description.  The generator
#     writes virtual pages so no hand-maintained docs-src/examples/*.md files
#     are needed.
# ---------------------------------------------------------------------------

REPO_URL = "https://github.com/haalfi/remote-store"

# Per-example "See also" guide links (label, relative-url, description).
# Only entries with guide links need to be listed here.
_EXAMPLE_SEE_ALSO: dict[str, list[tuple[str, str, str]]] = {
    "quickstart.py": [
        ("Getting Started", "../getting-started.md", "step-by-step guide"),
    ],
    "file_operations.py": [
        ("Getting Started", "../getting-started.md", "step-by-step guide"),
    ],
    "atomic_writes.py": [
        ("Concurrency", "../concurrency.md", "atomicity and overwrite semantics"),
    ],
    "configuration.py": [
        ("Choosing a Backend", "../choosing-a-backend.md", "backend selection guide"),
    ],
    "config_loaders.py": [
        ("Extensions", "../extensions.md", "extension modules overview"),
    ],
    "error_handling.py": [
        ("Troubleshooting", "../troubleshooting.md", "error diagnosis guide"),
    ],
    "capabilities_and_errors.py": [
        ("Capabilities Matrix", "../capabilities-matrix.md", "per-backend capability reference"),
    ],
    "memory_backend.py": [
        ("Memory Backend", "../backends/memory.md", "backend guide"),
    ],
    "batch_operations.py": [
        ("Batch Operations", "../batch-operations.md", "bulk operations guide"),
    ],
    "transfer_operations.py": [
        ("Transfer Operations", "../transfer-operations.md", "upload, download, and cross-store transfer guide"),
    ],
    "glob_pattern_matching.py": [
        ("Glob Pattern Matching", "../glob-pattern-matching.md", "pattern matching guide"),
    ],
    "observe_hooks.py": [
        ("Observe", "../observe.md", "instrumentation guide"),
    ],
    "otel_tracing.py": [
        ("Observe", "../observe.md", "instrumentation guide"),
    ],
    "caching.py": [
        ("Cache", "../cache.md", "caching guide"),
    ],
    "pyarrow_adapter.py": [
        ("PyArrow Adapter", "../pyarrow-adapter.md", "PyArrow filesystem integration guide"),
    ],
    "parquet_dataset.py": [
        ("Parquet Datasets", "../parquet-datasets.md", "managed Parquet dataset guide"),
        ("ext.parquet API", "../api/extensions/parquet.md", "API reference"),
    ],
    "dagster_io_manager.py": [
        ("Dagster", "../dagster.md", "Dagster integration guide"),
    ],
    "dagster_v2_resource.py": [
        ("Dagster", "../dagster.md", "Dagster integration guide"),
    ],
    "health_check.py": [
        ("Health Check", "../health-check.md", "health check guide"),
    ],
    "async_store.py": [
        ("Async Store", "../async.md", "async usage guide"),
        ("Async API", "../api/aio.md", "API reference"),
    ],
    "retry_policy.py": [
        ("Retry", "../retry.md", "retry configuration guide"),
    ],
    "backends/s3_backend.py": [
        ("S3 Backend", "../backends/s3.md", "backend guide"),
    ],
    "backends/s3_pyarrow_backend.py": [
        ("S3-PyArrow Backend", "../backends/s3-pyarrow.md", "backend guide"),
    ],
    "backends/s3_listing_strategies.py": [
        ("S3 Backend", "../backends/s3.md", "listing strategies and performance"),
    ],
    "backends/sftp_backend.py": [
        ("SFTP Backend", "../backends/sftp.md", "backend guide"),
    ],
    "backends/azure_backend.py": [
        ("Azure Backend", "../backends/azure.md", "backend guide"),
    ],
    "http_backend.py": [
        ("HTTP Backend", "../backends/http.md", "backend guide"),
    ],
    "backends/sql_blob_backend.py": [
        ("SQL Blob Backend", "../backends/sql-blob.md", "backend guide"),
    ],
}

# Custom descriptions override the docstring first-line for cases where the
# hand-authored wrapper had a better summary.
_EXAMPLE_DESCRIPTIONS: dict[str, str] = {
    "quickstart.py": "Minimal config, write, and read.",
    "error_handling.py": "Catching `NotFound`, `AlreadyExists`, and more.",
    "memory_backend.py": "In-process memory backend for testing and caching — no filesystem access needed.",
    "streaming_io.py": "Streaming writes and reads with `BytesIO`.",
    "store_child.py": "Runtime sub-scoping: create child stores that share a backend but isolate paths.",
    "http_backend.py": "Read-only access to files over HTTP/HTTPS — no credentials needed for public endpoints.",
    "caching.py": (
        "Store-level caching with `ext.cache` — cached reads, automatic invalidation on writes, and cache statistics."
    ),
    "observe_hooks.py": (
        "Callback-based instrumentation for Store operations — logging, metrics, auditing, and error tracking."
    ),
    "otel_tracing.py": "Instrument any Store with OpenTelemetry spans and metrics.",
    "glob_pattern_matching.py": (
        "Three-tier file filtering with `list_files(pattern=)`, `Store.glob()`, and `glob_files()`."
    ),
    "path_model.py": "`RemotePath` normalization, properties, validation, and the `/` operator.",
    "pyarrow_adapter.py": "Use any Store as a `pyarrow.fs.FileSystem` for Parquet, CSV, and dataset I/O.",
    "parquet_dataset.py": "Managed Parquet datasets with manifests, completion markers, and multi-part writes.",
    "dagster_io_manager.py": "Use any Store as a Dagster IOManager with pluggable serialization.",
    "dagster_v2_resource.py": "Config-driven Store construction with RemoteStoreIOManager.",
    "batch_operations.py": "Bulk delete, copy, and existence checks with error aggregation.",
    "transfer_operations.py": "Upload, download, and cross-store transfer with progress tracking.",
    "retry_policy.py": "Configure retry attempts, backoff, and jitter per-backend.",
    "health_check.py": "Startup gate pattern using `Store.ping()` to verify backend connectivity.",
    "async_store.py": "Async/await usage with `AsyncStore` -- streaming reads, async writes, child stores.",
    "configuration.py": "Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs.",
    "config_loaders.py": "Load registry configuration from TOML, YAML, and Pydantic models.",
    "capabilities_and_errors.py": "Capability querying, gating, and the structured error hierarchy.",
    "file_operations.py": (
        "Full Store API: read, write, delete, move, copy, list, metadata, type checks, capabilities, to_key."
    ),
    "atomic_writes.py": "Atomic writes and overwrite semantics.",
    "backends/s3_backend.py": "Connect to Amazon S3 or any S3-compatible service (MinIO, DigitalOcean Spaces, etc.).",
    "backends/s3_pyarrow_backend.py": (
        "High-throughput S3 via PyArrow's C++ filesystem. Drop-in swap from the S3 backend."
    ),
    "backends/sftp_backend.py": "Connect to any SSH/SFTP server with paramiko.",
    "backends/azure_backend.py": "Connect to Azure Blob Storage or Azure Data Lake Storage Gen2.",
    "backends/sql_blob_backend.py": "SQLite key-value store — zero-infrastructure persistent file storage.",
}


def _stem_to_slug(stem: str) -> str:
    """Convert a Python module stem to a kebab-case slug (e.g. 'file_operations' → 'file-operations')."""
    return stem.replace("_", "-")


def _extract_docstring(path: Path) -> str:
    """Extract the module docstring from a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return ast.get_docstring(tree) or ""


def _docstring_first_line(docstring: str) -> str:
    """Return the first non-empty line of a docstring, stripped of leading prefix.

    Handles patterns like 'Example: ...' or 'Quickstart — ...' by extracting
    the part after the em-dash or colon if they look like a title prefix.
    """
    for line in docstring.split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


def _make_title(stem: str, docstring_first: str) -> str:
    """Derive a page title from the filename stem and docstring first line.

    Uses the part before the em-dash/colon if the docstring looks like
    'Title — description', otherwise title-cases the stem.
    """
    # Try to extract title from docstring
    for sep in (" — ", " -- "):
        if sep in docstring_first:
            return docstring_first.split(sep, 1)[0].strip()
    # If the first line starts with "Example:" strip that
    if docstring_first.lower().startswith("example:"):
        rest = docstring_first[8:].strip()
        for sep in (" — ", " -- "):
            if sep in rest:
                return rest.split(sep, 1)[0].strip()
    # Fall back to title-casing the stem, with acronym fixups
    _ACRONYMS = {"Sftp": "SFTP", "Http": "HTTP", "S3": "S3", "Otel": "OTel", "Io": "IO"}
    title = stem.replace("_", " ").title()
    for wrong, right in _ACRONYMS.items():
        title = title.replace(wrong, right)
    return title


# Categorisation for the index page
_CORE_EXAMPLES = [
    "quickstart",
    "file_operations",
    "streaming_io",
    "atomic_writes",
    "configuration",
    "config_loaders",
    "error_handling",
    "capabilities_and_errors",
    "path_model",
    "memory_backend",
    "store_child",
    "async_store",
]
_BACKEND_EXAMPLES = [
    "backends/s3_backend",
    "backends/s3_pyarrow_backend",
    "backends/s3_listing_strategies",
    "backends/sftp_backend",
    "backends/azure_backend",
    "backends/sql_blob_backend",
    "http_backend",
]
_EXTENSION_EXAMPLES = [
    "batch_operations",
    "transfer_operations",
    "glob_pattern_matching",
    "caching",
    "observe_hooks",
    "otel_tracing",
    "pyarrow_adapter",
    "parquet_dataset",
    "dagster_io_manager",
    "dagster_v2_resource",
    "retry_policy",
    "health_check",
]
_SHOWCASE_EXAMPLES = [
    "medallion_dagster",
]


def _scan_example(rel_path: str, py_path: Path) -> tuple[str, str, str, str]:
    """Return (rel_key, slug, title, description) for one example script."""
    stem = py_path.stem
    slug = _stem_to_slug(stem)
    docstring = _extract_docstring(py_path)
    first_line = _docstring_first_line(docstring)
    title = _make_title(stem, first_line)
    description = _EXAMPLE_DESCRIPTIONS.get(rel_path, first_line)
    # Clean up description: if it starts with title + separator, keep only description
    for sep in (" — ", " -- "):
        if description.startswith(title + sep):
            description = description[len(title) + len(sep) :]
            break
    return rel_path, slug, title, description


# Scan all example files
_example_entries: list[tuple[str, str, str, str]] = []  # (rel_key, slug, title, desc)
_example_by_key: dict[str, tuple[str, str, str, str]] = {}

for py_file in sorted((ROOT / "examples").glob("*.py")):
    if py_file.stem == "__init__":
        continue
    rel_key = py_file.stem + ".py"
    entry = _scan_example(rel_key, py_file)
    _example_entries.append(entry)
    _example_by_key[rel_key] = entry

for py_file in sorted((ROOT / "examples" / "backends").glob("*.py")):
    if py_file.stem == "__init__":
        continue
    rel_key = f"backends/{py_file.stem}.py"
    entry = _scan_example(rel_key, py_file)
    _example_entries.append(entry)
    _example_by_key[rel_key] = entry


def _gen_example_page(rel_key: str, slug: str, title: str, description: str) -> str:
    """Generate the markdown content for one example wrapper page."""
    # Determine include path (from project root)
    include_path = f"examples/{rel_key.replace('.py', '')}.py"
    source_url = f"{REPO_URL}/blob/master/{include_path}"

    lines = [f"# {title}", "", description, ""]
    lines.append("```python")
    lines.append(f'--8<-- "{include_path}"')
    lines.append("```")
    lines.append("")

    # See also section
    see_also = _EXAMPLE_SEE_ALSO.get(rel_key, [])
    lines.append("## See also")
    lines.append("")
    for label, url, desc in see_also:
        lines.append(f"- [{label}]({url}) — {desc}")
    lines.append(f"- [Source: `{include_path}`]({source_url})")
    lines.append("")
    return "\n".join(lines)


def _gen_example_index(
    core: list[str],
    backends: list[str],
    extensions: list[str],
    showcases: list[str],
) -> str:
    """Generate examples/index.md from the categorised example lists."""
    lines = [
        "# Examples",
        "",
        "Runnable example scripts demonstrating every feature of `remote-store`. "
        "Each example is self-contained and uses a temporary directory so you can "
        "run them directly.",
        "",
        "## Core Examples",
        "",
        "These run locally with no external services or credentials.",
        "",
        "| Example | Description |",
        "|---------|-------------|",
    ]
    for key in core:
        entry = _example_by_key.get(key + ".py")
        if entry:
            _, slug, title, desc = entry
            lines.append(f"| [{title}]({slug}.md) | {desc} |")
        else:
            warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=2)

    lines.extend(
        [
            "",
            "## Backend Examples",
            "",
            "These require a running service (AWS, MinIO, an SFTP server, Azure, Azurite, etc.) "
            "and credentials supplied via environment variables. Each script prints a help message "
            "when the required variables are missing.",
            "",
            "| Example | Description |",
            "|---------|-------------|",
        ]
    )
    for key in backends:
        entry = _example_by_key.get(key + ".py")
        if entry:
            _, slug, title, desc = entry
            lines.append(f"| [{title}]({slug}.md) | {desc} |")
        else:
            warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=2)

    lines.extend(
        [
            "",
            "## Extension Examples",
            "",
            "| Example | Description |",
            "|---------|-------------|",
        ]
    )
    for key in extensions:
        entry = _example_by_key.get(key + ".py")
        if entry:
            _, slug, title, desc = entry
            lines.append(f"| [{title}]({slug}.md) | {desc} |")
        else:
            warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=2)

    lines.extend(
        [
            "",
            "## Showcases",
            "",
            "Full project examples demonstrating multiple extensions working together.",
            "",
            "| Example | Description |",
            "|---------|-------------|",
        ]
    )
    for key in showcases:
        if key == "medallion_dagster":
            lines.append(
                "| [Medallion + Dagster Showcase](medallion-dagster.md) | "
                "End-to-end Bronze/Silver/Gold pipeline with Dagster, 4 extensions, live MeteoSwiss data |"
            )

    lines.extend(
        [
            "",
            "Interactive Jupyter notebooks are also available in the",
            f"[`examples/notebooks/`]({REPO_URL}/tree/master/examples/notebooks)",
            "directory of the repository.",
            "",
        ]
    )
    return "\n".join(lines)


# --- Write example wrapper pages ---
for rel_key, slug, title, description in _example_entries:
    # Backend examples get the backend prefix in their slug for the docs
    doc_slug = _stem_to_slug(rel_key.split("/")[1].replace(".py", "")) if rel_key.startswith("backends/") else slug
    page_content = _gen_example_page(rel_key, doc_slug, title, description)
    with mkdocs_gen_files.open(f"examples/{doc_slug}.md", "w") as f:
        f.write(page_content)

# --- Medallion showcase (special case: directory with README, not a single script) ---
# Virtual files cannot use include-markdown, so we read and inline the README
# content with heading offset +1 (## → ###, etc.).
_medallion_readme = (ROOT / "examples" / "medallion_dagster" / "README.md").read_text(encoding="utf-8")
# Strip the first heading (duplicated in our wrapper) and offset remaining headings
_readme_lines = _medallion_readme.split("\n")
_readme_body_lines: list[str] = []
_skipped_first_heading = False
_in_code_fence = False
for _line in _readme_lines:
    if _line.startswith("```"):
        _in_code_fence = not _in_code_fence
    if not _skipped_first_heading and _line.startswith("# "):
        _skipped_first_heading = True
        continue
    # Offset headings by 1 level (only outside code fences)
    if not _in_code_fence and _line.startswith("#"):
        _line = "#" + _line
    _readme_body_lines.append(_line)
_readme_body = "\n".join(_readme_body_lines)

_medallion_page = f"""\
# Medallion + Dagster Showcase

End-to-end Bronze/Silver/Gold pipeline with Dagster orchestration, \
demonstrating 4 remote-store extensions composing over live MeteoSwiss \
weather data.

{_readme_body}

## See also

- [Dagster](../dagster.md) — Dagster integration guide
- [Data Lake Patterns](../data-lake-patterns.md) — medallion architecture patterns
- [Architecture: Medallion + Dagster Showcase]\
(../design/research/research-medallion-dagster-showcase.md) — \
detailed design rationale, store topology, and Dagster asset graph
- [Source: `examples/medallion_dagster/`]\
(https://github.com/haalfi/remote-store/tree/master/examples/medallion_dagster/)
"""
with mkdocs_gen_files.open("examples/medallion-dagster.md", "w") as f:
    f.write(_medallion_page)

# --- Write examples/index.md ---
index_content = _gen_example_index(
    _CORE_EXAMPLES,
    _BACKEND_EXAMPLES,
    _EXTENSION_EXAMPLES,
    _SHOWCASE_EXAMPLES,
)
with mkdocs_gen_files.open("examples/index.md", "w") as f:
    f.write(index_content)

# --- Build example nav entries for scanned_sections ---
_example_nav_entries: list[tuple[str, str]] = []

# Core examples
for key in _CORE_EXAMPLES:
    entry = _example_by_key.get(key + ".py")
    if entry:
        _, slug, title, _ = entry
        _example_nav_entries.append((title, f"examples/{slug}.md"))
    else:
        warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=1)

# Backend examples
for key in _BACKEND_EXAMPLES:
    entry = _example_by_key.get(key + ".py")
    if entry:
        _, slug, title, _ = entry
        doc_slug = _stem_to_slug(key.split("/")[-1]) if "/" in key else slug
        _example_nav_entries.append((title, f"examples/{doc_slug}.md"))
    else:
        warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=1)

# Extension examples
for key in _EXTENSION_EXAMPLES:
    entry = _example_by_key.get(key + ".py")
    if entry:
        _, slug, title, _ = entry
        _example_nav_entries.append((title, f"examples/{slug}.md"))
    else:
        warnings.warn(f"Example key {key!r} not found in scanned examples", stacklevel=1)

# Showcases
_example_nav_entries.append(("Medallion + Dagster Showcase", "examples/medallion-dagster.md"))

# ---------------------------------------------------------------------------
# 6. Assemble SUMMARY.md from per-section _nav.yml files
#
#    Each directory in docs-src/ may contain a _nav.yml listing its entries.
#    Entries ending with "/" are subsections (recurse into that directory).
#    Sections without a _nav.yml that match a scanned directory (specs, adrs)
#    are populated automatically from the filesystem scan.
# ---------------------------------------------------------------------------

# Scanned sections: directory prefix → list of (label, file) pairs
_scanned_sections: dict[str, list[tuple[str, str]]] = {
    "design/specs": [(f"{num}: {title}", f"design/specs/{slug}.md") for num, slug, title in spec_entries],
    "design/adrs": [(f"{num}: {title}", f"design/adrs/{slug}.md") for num, slug, title in adr_entries],
    "design/rfcs": [(f"{num}: {title}", f"design/rfcs/{slug}.md") for num, slug, title in rfc_entries],
    "design/research": [(title, f"design/research/{slug}.md") for _num, slug, title in research_entries],
    "examples": _example_nav_entries,
}

nav = mkdocs_gen_files.Nav()


def _process_entries(
    entries: list[dict[str, object]],
    section_dir: str,
    nav_path: tuple[str, ...],
) -> None:
    """Process a list of nav entries, handling leaves, directories, and groups."""
    for entry in entries:
        for label, target in entry.items():
            if isinstance(target, list):
                # Virtual group — label is a nav heading, target is child entries.
                # No corresponding directory; children resolve against same section_dir.
                child_path = nav_path + (label,)
                _process_entries(target, section_dir, child_path)
            elif isinstance(target, str) and target.endswith("/"):
                # Subsection — resolve its directory and recurse
                subdir_name = target.rstrip("/")
                full_dir = f"{section_dir}/{subdir_name}" if section_dir else subdir_name
                child_path = nav_path + (label,)
                # Point the section itself at its index page
                nav[child_path] = f"{full_dir}/index.md"
                # Check for a _nav.yml in the subsection
                child_nav = DOCS_SRC / full_dir / "_nav.yml"
                if child_nav.exists():
                    _load_nav_section(child_nav, full_dir, child_path)
                elif full_dir in _scanned_sections:
                    # Auto-populated from filesystem scan
                    for scan_label, scan_file in _scanned_sections[full_dir]:
                        nav[child_path + (scan_label,)] = scan_file
            else:
                # Leaf page
                full_path = f"{section_dir}/{target}" if section_dir else target
                if nav_path:
                    nav[nav_path + (label,)] = full_path
                else:
                    nav[(label,)] = full_path


def _load_nav_section(
    nav_file: Path,
    section_dir: str,
    nav_path: tuple[str, ...],
) -> None:
    """Read a _nav.yml and add its entries to *nav*, recursing into subsections."""
    entries = yaml.safe_load(nav_file.read_text(encoding="utf-8")) or []
    _process_entries(entries, section_dir, nav_path)


_load_nav_section(DOCS_SRC / "_nav.yml", "", ())

with mkdocs_gen_files.open("SUMMARY.md", "w") as f:
    f.writelines(nav.build_literate_nav())
