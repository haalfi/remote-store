#!/usr/bin/env python3
"""Generate the docs/ directory from source content.

docs/ is a build artifact — every file is either a wrapper directive or a
generated index page.  Source of truth lives in README.md, guides/, sdd/,
examples/, and Python source code.

See: sdd/adrs/0006-documentation-architecture.md

Usage:
    python scripts/generate_docs.py          # generate docs/
    python scripts/generate_docs.py --clean  # remove docs/ first
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


# ---------------------------------------------------------------------------
# Page definitions
# ---------------------------------------------------------------------------


class IncludeMarkdown(NamedTuple):
    """Wrap a source .md file via include-markdown."""

    docs_path: str  # relative to docs/
    source: str  # relative to the docs file's location
    rewrite_urls: bool = True


class MkdocstringsPage(NamedTuple):
    """Auto-generated API reference page from docstrings."""

    docs_path: str
    heading: str
    directives: list[str]  # e.g. ["remote_store.Store"]


class SnippetPage(NamedTuple):
    """Example page that includes a Python file via pymdownx.snippets."""

    docs_path: str
    title: str
    description: str
    snippet_path: str  # relative to repo root (pymdownx.snippets base_path)


class LiteralPage(NamedTuple):
    """Page with literal content (indices, landing pages)."""

    docs_path: str
    content: str


class GuideInclude(NamedTuple):
    """Include a guide .md and append mkdocstrings API reference."""

    docs_path: str
    source: str  # relative to the docs file's location
    api_directives: list[str]  # appended as ::: blocks


# ---------------------------------------------------------------------------
# Content registry — single source of all docs/ pages
# ---------------------------------------------------------------------------

# The ADR-0006 index page needs to include 0006 itself now.
# Scan sdd/adrs/ for all ADR files to build the table dynamically.


def _adr_entries() -> list[tuple[str, str, str]]:
    """Return (number, slug, title) for each ADR in sdd/adrs/."""
    adrs_dir = ROOT / "sdd" / "adrs"
    entries = []
    for p in sorted(adrs_dir.glob("*.md")):
        num = p.stem.split("-", 1)[0]  # "0001"
        # Read first line to get the title
        first_line = p.read_text().split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
        # Strip the "ADR-NNNN: " prefix if present
        if title.startswith(f"ADR-{num}:"):
            title = title[len(f"ADR-{num}:") :].strip()
        entries.append((num, p.stem, title))
    return entries


def _spec_entries() -> list[tuple[str, str, str]]:
    """Return (number, slug, title) for each spec in sdd/specs/."""
    specs_dir = ROOT / "sdd" / "specs"
    entries = []
    for p in sorted(specs_dir.glob("*.md")):
        num = p.stem.split("-", 1)[0]  # "001"
        first_line = p.read_text().split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
        # Strip spec number prefixes like "Spec 001: " or "001: "
        for prefix in [f"Spec {num}: ", f"Spec-{num}: ", f"{num}: "]:
            if title.startswith(prefix):
                title = title[len(prefix) :]
                break
        entries.append((num, p.stem, title))
    return entries


def _rfc_entries() -> list[tuple[str, str, str]]:
    """Return (number, slug, title) for each RFC in sdd/rfcs/."""
    rfcs_dir = ROOT / "sdd" / "rfcs"
    entries = []
    for p in sorted(rfcs_dir.glob("rfc-*.md")):
        if p.stem == "rfc-template":
            continue
        # e.g. "rfc-0001-azure-backend" → num="0001"
        parts = p.stem.split("-", 2)  # ["rfc", "0001", "azure-backend"]
        num = parts[1] if len(parts) > 1 else p.stem
        first_line = p.read_text().split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
        entries.append((num, p.stem, title))
    return entries


def _rewrite_links(text: str, replacements: dict[str, str]) -> str:
    """Replace relative link targets in markdown text."""
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _build_pages() -> list:
    """Build the complete list of page definitions."""
    adr_entries = _adr_entries()
    spec_entries = _spec_entries()
    rfc_entries = _rfc_entries()

    # --- ADR index ---
    adr_rows = "\n".join(
        f"| {num} | [{title}]({slug}.md) | Accepted |"
        for num, slug, title in adr_entries
    )
    adr_index_content = (
        "# Architecture Decision Records\n\n"
        "ADRs capture significant design decisions and their rationale.\n\n"
        "| # | ADR | Status |\n"
        "|---|-----|--------|\n"
        f"{adr_rows}\n"
    )

    # --- Spec index ---
    spec_rows = "\n".join(
        f"| {num} | [{title}]({slug}.md) |"
        for num, slug, title in spec_entries
    )
    spec_index_content = (
        "# Specifications\n\n"
        "Every feature in `remote-store` is defined by a specification "
        "before implementation begins. Specs are the single source of "
        "truth for behavior.\n\n"
        "| # | Spec |\n"
        "|---|------|\n"
        f"{spec_rows}\n"
    )

    # --- Design index ---
    spec_links = "\n".join(
        f"- [{num}: {title}](specs/{slug}.md)"
        for num, slug, title in spec_entries
    )
    adr_links = "\n".join(
        f"- [{num}: {title}](adrs/{slug}.md)"
        for num, slug, title in adr_entries
    )
    design_index_content = (
        "# Design\n\n"
        "`remote-store` follows **Spec-Driven Development (SDD)**: every "
        "feature starts as a specification before any code is written. "
        "Architecture decisions are recorded as ADRs.\n\n"
        "## Documents\n\n"
        "- [Design Document](design-spec.md) -- the overall design and conventions\n"
        "- [Process](process.md) -- the SDD methodology\n\n"
        "## Specifications\n\n"
        f"{spec_links}\n\n"
        "## Architecture Decision Records\n\n"
        f"{adr_links}\n"
    )

    # --- API index ---
    api_index_content = """\
# API Reference

Complete reference for all public exports of `remote-store`.

## Core

| Class | Description |
|-------|-------------|
| [Store](store.md) | Main entry point for all file operations |
| [Registry](registry.md) | Creates and manages backend instances and stores |
| [Backend](backend.md) | Abstract base class for storage backends |

## Configuration

| Class | Description |
|-------|-------------|
| [RegistryConfig](config.md#remote_store.RegistryConfig) | Top-level configuration holding backends and stores |
| [BackendConfig](config.md#remote_store.BackendConfig) | Configuration for a single backend |
| [StoreProfile](config.md#remote_store.StoreProfile) | Configuration for a single store |

## Path & Models

| Class | Description |
|-------|-------------|
| [RemotePath](path.md) | Validated, immutable path value object |
| [FileInfo](models.md#remote_store.FileInfo) | Metadata for a file (name, size, modified time) |
| [FolderInfo](models.md#remote_store.FolderInfo) | Metadata for a folder |
| [RemoteFile](models.md#remote_store.RemoteFile) | Context manager wrapping a readable binary stream |
| [RemoteFolder](models.md#remote_store.RemoteFolder) | Iterable of files and subfolders |

## Capabilities

| Class | Description |
|-------|-------------|
| [Capability](capabilities.md#remote_store.Capability) | Enum of backend capabilities |
| [CapabilitySet](capabilities.md#remote_store.CapabilitySet) | Set of capabilities a backend supports |

## Errors

| Class | Description |
|-------|-------------|
| [RemoteStoreError](errors.md#remote_store.RemoteStoreError) | Base exception |
| [NotFound](errors.md#remote_store.NotFound) | File or folder not found |
| [AlreadyExists](errors.md#remote_store.AlreadyExists) | File already exists (no overwrite) |
| [PermissionDenied](errors.md#remote_store.PermissionDenied) | Insufficient permissions |
| [InvalidPath](errors.md#remote_store.InvalidPath) | Path validation failed |
| [CapabilityNotSupported](errors.md#remote_store.CapabilityNotSupported) | Backend lacks required capability |
| [BackendUnavailable](errors.md#remote_store.BackendUnavailable) | Backend could not be reached |

## Functions

| Function | Description |
|----------|-------------|
| [register_backend](registry.md#remote_store.register_backend) | Register a custom backend type |
"""

    # --- Examples index ---
    examples_index_content = """\
# Examples

Runnable example scripts demonstrating every feature of `remote-store`. \
Each example is self-contained and uses a temporary directory so you can \
run them directly.

| Example | Description |
|---------|-------------|
| [Quickstart](quickstart.md) | Minimal config, write, and read |
| [File Operations](file-operations.md) | Full Store API: read, write, delete, move, copy, list, metadata |
| [Streaming I/O](streaming-io.md) | Streaming writes and reads with `BytesIO` |
| [Atomic Writes](atomic-writes.md) | Atomic writes and overwrite semantics |
| [Configuration](configuration.md) | Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs |
| [Error Handling](error-handling.md) | Catching `NotFound`, `AlreadyExists`, and more |

Interactive Jupyter notebooks are also available in the
[`examples/notebooks/`](https://github.com/haalfi/remote-store/tree/master/examples/notebooks)
directory of the repository.
"""

    # --- Landing page ---
    index_content = """\
---
hide:
  - navigation
---

{%
   include-markdown "../README.md"
%}
"""

    # --- Getting started (wraps README) ---
    getting_started_content = """\
# Getting Started

{%
   include-markdown "../README.md"
   start="## Installation"
   end="## Contributing"
%}
"""

    # --- Rewritten content pages ---
    # CONTRIBUTING.md links to sdd/ paths that don't exist in the docs tree.
    # We read the file, rewrite links to their docs-tree equivalents, and
    # emit as a LiteralPage so links work on both GitHub and in MkDocs.
    contributing_text = _rewrite_links(
        (ROOT / "CONTRIBUTING.md").read_text(),
        {
            "](sdd/000-process.md)": "](design/process.md)",
            "](sdd/rfcs/rfc-template.md)": "](design/rfcs/rfc-template.md)",
            "](sdd/DESIGN.md#11-code-style)": "](design/design-spec.md#11-code-style)",
        },
    )

    # sdd/000-process.md links to ../CONTRIBUTING.md (uppercase) which maps
    # to contributing.md (lowercase) in the docs tree.
    process_text = _rewrite_links(
        (ROOT / "sdd" / "000-process.md").read_text(),
        {
            "](../CONTRIBUTING.md#versioning)": "](../contributing.md#versioning)",
        },
    )

    pages: list = [
        # --- Landing & top-level ---
        LiteralPage("index.md", index_content),
        LiteralPage("getting-started.md", getting_started_content),
        LiteralPage("contributing.md", contributing_text),
        IncludeMarkdown("changelog.md", "../CHANGELOG.md"),
        IncludeMarkdown("development-story.md", "../DEVELOPMENT_STORY.md"),
        # --- Examples ---
        LiteralPage("examples/index.md", examples_index_content),
        SnippetPage(
            "examples/quickstart.md",
            "Quickstart",
            "Minimal config, write, and read.",
            "examples/quickstart.py",
        ),
        SnippetPage(
            "examples/file-operations.md",
            "File Operations",
            "Full Store API: read, write, delete, move, copy, list, "
            "metadata, type checks, capabilities, to_key.",
            "examples/file_operations.py",
        ),
        SnippetPage(
            "examples/streaming-io.md",
            "Streaming I/O",
            "Streaming writes and reads with `BytesIO`.",
            "examples/streaming_io.py",
        ),
        SnippetPage(
            "examples/atomic-writes.md",
            "Atomic Writes",
            "Atomic writes and overwrite semantics.",
            "examples/atomic_writes.py",
        ),
        SnippetPage(
            "examples/configuration.md",
            "Configuration",
            "Config-as-code, `from_dict()`, multiple stores, "
            "S3/SFTP backend configs.",
            "examples/configuration.py",
        ),
        SnippetPage(
            "examples/error-handling.md",
            "Error Handling",
            "Catching `NotFound`, `AlreadyExists`, and more.",
            "examples/error_handling.py",
        ),
        # --- API reference ---
        LiteralPage("api/index.md", api_index_content),
        MkdocstringsPage(
            "api/store.md",
            "Store",
            ["remote_store.Store"],
        ),
        MkdocstringsPage(
            "api/registry.md",
            "Registry",
            ["remote_store.Registry", "remote_store.register_backend"],
        ),
        MkdocstringsPage(
            "api/backend.md",
            "Backend",
            ["remote_store.Backend"],
        ),
        MkdocstringsPage(
            "api/config.md",
            "Configuration",
            [
                "remote_store.RegistryConfig",
                "remote_store.BackendConfig",
                "remote_store.StoreProfile",
            ],
        ),
        MkdocstringsPage(
            "api/models.md",
            "Models",
            [
                "remote_store.FileInfo",
                "remote_store.FolderInfo",
                "remote_store.RemoteFile",
                "remote_store.RemoteFolder",
            ],
        ),
        MkdocstringsPage(
            "api/path.md",
            "RemotePath",
            ["remote_store.RemotePath"],
        ),
        MkdocstringsPage(
            "api/capabilities.md",
            "Capabilities",
            ["remote_store.Capability", "remote_store.CapabilitySet"],
        ),
        MkdocstringsPage(
            "api/errors.md",
            "Errors",
            [
                "remote_store.RemoteStoreError",
                "remote_store.NotFound",
                "remote_store.AlreadyExists",
                "remote_store.PermissionDenied",
                "remote_store.InvalidPath",
                "remote_store.CapabilityNotSupported",
                "remote_store.BackendUnavailable",
            ],
        ),
        # --- Backends (guides + API ref) ---
        GuideInclude(
            "backends/index.md",
            "../../guides/backends/index.md",
            api_directives=[],
        ),
        GuideInclude(
            "backends/local.md",
            "../../guides/backends/local.md",
            api_directives=["remote_store.backends.LocalBackend"],
        ),
        GuideInclude(
            "backends/s3.md",
            "../../guides/backends/s3.md",
            api_directives=["remote_store.backends.S3Backend"],
        ),
        GuideInclude(
            "backends/s3-pyarrow.md",
            "../../guides/backends/s3-pyarrow.md",
            api_directives=["remote_store.backends.S3PyArrowBackend"],
        ),
        GuideInclude(
            "backends/sftp.md",
            "../../guides/backends/sftp.md",
            api_directives=["remote_store.backends.SFTPBackend"],
        ),
        # --- Design ---
        LiteralPage("design/index.md", design_index_content),
        IncludeMarkdown(
            "design/design-spec.md",
            "../../sdd/DESIGN.md",
        ),
        LiteralPage("design/process.md", process_text),
        # --- Specs ---
        LiteralPage("design/specs/index.md", spec_index_content),
    ]

    # Add all spec wrapper pages
    for _num, slug, _title in spec_entries:
        pages.append(
            IncludeMarkdown(
                f"design/specs/{slug}.md",
                f"../../../sdd/specs/{slug}.md",
                rewrite_urls=False,
            )
        )

    # Add all ADR wrapper pages
    for _num, slug, _title in adr_entries:
        pages.append(
            IncludeMarkdown(
                f"design/adrs/{slug}.md",
                f"../../../sdd/adrs/{slug}.md",
                rewrite_urls=False,
            )
        )

    # ADR index
    pages.append(LiteralPage("design/adrs/index.md", adr_index_content))

    # Add RFC wrapper pages (linked from specs, e.g. 012-azure-backend → rfcs/)
    for _num, slug, _title in rfc_entries:
        pages.append(
            IncludeMarkdown(
                f"design/rfcs/{slug}.md",
                f"../../../sdd/rfcs/{slug}.md",
                rewrite_urls=False,
            )
        )
    # RFC template (linked from CONTRIBUTING.md)
    pages.append(
        IncludeMarkdown(
            "design/rfcs/rfc-template.md",
            "../../../sdd/rfcs/rfc-template.md",
            rewrite_urls=False,
        )
    )

    return pages


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render(page) -> str:  # noqa: ANN001
    if isinstance(page, IncludeMarkdown):
        rewrite = (
            ""
            if page.rewrite_urls
            else "\n   rewrite-relative-urls=false"
        )
        return (
            "{%\n"
            f'   include-markdown "{page.source}"{rewrite}\n'
            "%}\n"
        )

    if isinstance(page, MkdocstringsPage):
        lines = [f"# {page.heading}\n"]
        for directive in page.directives:
            lines.append(f"::: {directive}\n")
        return "\n".join(lines)

    if isinstance(page, SnippetPage):
        return (
            f"# {page.title}\n\n"
            f"{page.description}\n\n"
            f"```python\n"
            f'--8<-- "{page.snippet_path}"\n'
            f"```\n"
        )

    if isinstance(page, LiteralPage):
        return page.content

    if isinstance(page, GuideInclude):
        # URL rewriting is disabled because guides use relative links
        # (e.g. s3-pyarrow.md → s3.md) that already resolve correctly
        # in docs/ since the directory structure mirrors guides/.
        # If guides ever link outside their own directory, this will
        # need a rewrite strategy similar to _rewrite_links().
        parts = [
            "{%\n"
            f'   include-markdown "{page.source}"\n'
            "   rewrite-relative-urls=false\n"
            "%}\n"
        ]
        if page.api_directives:
            parts.append("\n## API Reference\n")
            for directive in page.api_directives:
                parts.append(f"\n::: {directive}\n")
        return "\n".join(parts)

    raise TypeError(f"Unknown page type: {type(page)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate(*, clean: bool = False) -> None:
    if clean and DOCS.exists():
        shutil.rmtree(DOCS)

    # Copy assets
    assets_src = ROOT / "assets"
    assets_dst = DOCS / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    for asset in assets_src.iterdir():
        shutil.copy2(asset, assets_dst / asset.name)

    # Generate all pages
    pages = _build_pages()
    for page in pages:
        docs_path = page.docs_path
        out = DOCS / docs_path
        out.parent.mkdir(parents=True, exist_ok=True)
        content = _render(page)
        # Only write if content changed (avoid unnecessary rebuilds)
        if out.exists() and out.read_text() == content:
            continue
        out.write_text(content)
        print(f"  generated: docs/{docs_path}")

    print(f"\n  {len(pages)} pages ready in docs/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove docs/ before generating",
    )
    args = parser.parse_args()
    generate(clean=args.clean)
