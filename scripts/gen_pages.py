"""MkDocs gen-files hook: generates dynamic pages and navigation.

Runs during the MkDocs build via mkdocs-gen-files.  Static authored content
lives in docs-src/ (the docs_dir).  This script handles only:

  1. Scanning sdd/ for specs, ADRs, and RFCs
  2. Filling .tmpl templates with dynamic rows
  3. Creating include-wrapper pages for each spec/ADR/RFC
  4. Rewriting links in contributing.md and design/process.md
  5. Copying assets/ into the virtual filesystem
  6. Generating SUMMARY.md for mkdocs-literate-nav

See: sdd/adrs/0006-documentation-architecture.md
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = ROOT / "docs-src"

# ---------------------------------------------------------------------------
# 1. Scan sdd/ for specs, ADRs, RFCs
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
        first_line = p.read_text().split("\n", 1)[0]
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

# ---------------------------------------------------------------------------
# 2. Fill .tmpl templates → write as virtual pages
# ---------------------------------------------------------------------------

# --- design/adrs/index.md ---
adr_rows = "\n".join(
    f"| {num} | [{title}]({slug}.md) | Accepted |"
    for num, slug, title in adr_entries
)
tmpl = (DOCS_SRC / "design" / "adrs" / "_index.tmpl").read_text()
with mkdocs_gen_files.open("design/adrs/index.md", "w") as f:
    f.write(tmpl.replace("{{ adr_rows }}", adr_rows))

# --- design/specs/index.md ---
spec_rows = "\n".join(
    f"| {num} | [{title}]({slug}.md) |" for num, slug, title in spec_entries
)
tmpl = (DOCS_SRC / "design" / "specs" / "_index.tmpl").read_text()
with mkdocs_gen_files.open("design/specs/index.md", "w") as f:
    f.write(tmpl.replace("{{ spec_rows }}", spec_rows))

# --- design/index.md ---
spec_links = "\n".join(
    f"- [{num}: {title}](specs/{slug}.md)" for num, slug, title in spec_entries
)
adr_links = "\n".join(
    f"- [{num}: {title}](adrs/{slug}.md)" for num, slug, title in adr_entries
)
tmpl = (DOCS_SRC / "design" / "_index.tmpl").read_text()
with mkdocs_gen_files.open("design/index.md", "w") as f:
    f.write(tmpl.replace("{{ spec_links }}", spec_links).replace("{{ adr_links }}", adr_links))

# ---------------------------------------------------------------------------
# 3. Create wrapper pages for each spec, ADR, RFC
#
#    Virtual files cannot use include-markdown (paths would resolve against a
#    temp directory), so we read the source content and write it directly.
# ---------------------------------------------------------------------------

for _num, slug, _title in spec_entries:
    content = (ROOT / "sdd" / "specs" / f"{slug}.md").read_text()
    with mkdocs_gen_files.open(f"design/specs/{slug}.md", "w") as f:
        f.write(content)

for _num, slug, _title in adr_entries:
    content = (ROOT / "sdd" / "adrs" / f"{slug}.md").read_text()
    with mkdocs_gen_files.open(f"design/adrs/{slug}.md", "w") as f:
        f.write(content)

for _num, slug, _title in rfc_entries:
    content = (ROOT / "sdd" / "rfcs" / f"{slug}.md").read_text()
    with mkdocs_gen_files.open(f"design/rfcs/{slug}.md", "w") as f:
        f.write(content)

# RFC template (linked from CONTRIBUTING.md)
with mkdocs_gen_files.open("design/rfcs/rfc-template.md", "w") as f:
    f.write((ROOT / "sdd" / "rfcs" / "rfc-template.md").read_text())

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
    (ROOT / "CONTRIBUTING.md").read_text(),
    {
        "](sdd/000-process.md)": "](design/process.md)",
        "](sdd/rfcs/rfc-template.md)": "](design/rfcs/rfc-template.md)",
        "](sdd/DESIGN.md#11-code-style)": "](design/design-spec.md#11-code-style)",
    },
)
with mkdocs_gen_files.open("contributing.md", "w") as f:
    f.write(contributing_text)

# sdd/000-process.md → design/process.md
process_text = _rewrite_links(
    (ROOT / "sdd" / "000-process.md").read_text(),
    {
        "](../CONTRIBUTING.md#versioning)": "](../contributing.md#versioning)",
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
# 6. Generate SUMMARY.md for literate-nav
# ---------------------------------------------------------------------------

nav = mkdocs_gen_files.Nav()

nav["Home"] = "index.md"
nav["Getting Started"] = "getting-started.md"

# Examples
nav["Examples"] = "examples/index.md"
nav["Examples", "Quickstart"] = "examples/quickstart.md"
nav["Examples", "File Operations"] = "examples/file-operations.md"
nav["Examples", "Streaming I/O"] = "examples/streaming-io.md"
nav["Examples", "Atomic Writes"] = "examples/atomic-writes.md"
nav["Examples", "Configuration"] = "examples/configuration.md"
nav["Examples", "Error Handling"] = "examples/error-handling.md"

# API Reference
nav["API Reference"] = "api/index.md"
nav["API Reference", "Store"] = "api/store.md"
nav["API Reference", "Registry"] = "api/registry.md"
nav["API Reference", "Backend"] = "api/backend.md"
nav["API Reference", "Config"] = "api/config.md"
nav["API Reference", "Models"] = "api/models.md"
nav["API Reference", "RemotePath"] = "api/path.md"
nav["API Reference", "Capabilities"] = "api/capabilities.md"
nav["API Reference", "Errors"] = "api/errors.md"

# Backends
nav["Backends"] = "backends/index.md"
nav["Backends", "Local"] = "backends/local.md"
nav["Backends", "S3"] = "backends/s3.md"
nav["Backends", "S3-PyArrow"] = "backends/s3-pyarrow.md"
nav["Backends", "SFTP"] = "backends/sftp.md"

# Performance
nav["Performance"] = "performance.md"

# Design
nav["Design"] = "design/index.md"
nav["Design", "Design Document"] = "design/design-spec.md"
nav["Design", "Process"] = "design/process.md"

nav["Design", "Specs"] = "design/specs/index.md"
for num, slug, title in spec_entries:
    nav["Design", "Specs", f"{num}: {title}"] = f"design/specs/{slug}.md"

nav["Design", "ADRs"] = "design/adrs/index.md"
for num, slug, title in adr_entries:
    nav["Design", "ADRs", f"{num}: {title}"] = f"design/adrs/{slug}.md"

# Bottom-level pages
nav["Contributing"] = "contributing.md"
nav["Changelog"] = "changelog.md"
nav["Development Story"] = "development-story.md"

with mkdocs_gen_files.open("SUMMARY.md", "w") as f:
    f.writelines(nav.build_literate_nav())
