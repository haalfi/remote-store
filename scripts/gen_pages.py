"""MkDocs gen-files hook: generates dynamic pages and navigation.

Runs during the MkDocs build via mkdocs-gen-files.  Static authored content
lives in docs-src/ (the docs_dir).  This script handles only:

  1. Scanning sdd/ for specs, ADRs, RFCs, and research docs
  2. Filling .tmpl templates with dynamic rows
  3. Creating include-wrapper pages for each spec/ADR/RFC
  4. Rewriting links in contributing.md and design/process.md
  5. Copying assets/ into the virtual filesystem
  6. Assembling SUMMARY.md from per-section _nav.yml files

See: sdd/adrs/0007-docs-src-literate-nav.md
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files
import yaml

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
research_rows = "\n".join(f"| {title} | [{slug}]({slug}.md) |" for _num, slug, title in research_entries)
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
        "](sdd/DESIGN.md#11-code-style)": "](design/design-spec.md#11-code-style)",
        "](sdd/adrs/0008-extension-architecture.md)": "](design/adrs/0008-extension-architecture.md)",
    },
)
with mkdocs_gen_files.open("contributing.md", "w") as f:
    f.write(contributing_text)

# sdd/000-process.md → design/process.md
process_text = _rewrite_links(
    (ROOT / "sdd" / "000-process.md").read_text(encoding="utf-8"),
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
