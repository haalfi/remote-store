"""Rendering helpers: fill templates, emit wrapper pages, write the index.

Each public function takes a ``writer`` callable ``(virtual_path, text) -> None``
so tests can substitute an in-memory capture.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from .scan import SDD_KINDS

if TYPE_CHECKING:
    from pathlib import Path

    from .link import LinkResolver
    from .scan import (
        ExampleCategory,
        ExampleEntry,
        LinkMapEntry,
        SddEntry,
        SddKind,
    )

Writer = Callable[[str, str], None]
BinaryWriter = Callable[[str, bytes], None]

REPO_URL = "https://github.com/haalfi/remote-store"

# Template placeholder stems differ from slugs only for "research" (no trailing 's').
_PLACEHOLDER_STEM = {
    "adrs": "adr",
    "specs": "spec",
    "rfcs": "rfc",
    "audits": "audit",
    "research": "research",
}


# ---------------------------------------------------------------------------
# sdd/ index pages and design landing page
# ---------------------------------------------------------------------------


def _index_row(kind: SddKind, e: SddEntry) -> str:
    first = e.number if kind.numbered else e.title
    cells = [first, f"[{e.title}]({e.slug}.md)"]
    if kind.status:
        cells.append(kind.status)
    return "| " + " | ".join(cells) + " |"


def _design_link(kind: SddKind, e: SddEntry) -> str:
    if kind.numbered:
        return f"- [{e.number}: {e.title}]({kind.slug}/{e.slug}.md)"
    return f"- [{e.title}]({kind.slug}/{e.slug}.md)"


def _fill_template(path: Path, replacements: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def render_sdd_indexes(
    docs_src: Path,
    writer: Writer,
    entries_by_kind: dict[str, list[SddEntry]],
) -> None:
    """Emit ``design/<kind>/index.md`` per kind, plus ``design/index.md``."""
    for kind in SDD_KINDS:
        entries = entries_by_kind.get(kind.slug, [])
        rows = "\n".join(_index_row(kind, e) for e in entries)
        placeholder = f"{{{{ {_PLACEHOLDER_STEM[kind.slug]}_rows }}}}"
        tmpl = docs_src / "design" / kind.slug / "_index.tmpl"
        writer(f"design/{kind.slug}/index.md", _fill_template(tmpl, {placeholder: rows}))

    landing_replacements = {
        f"{{{{ {_PLACEHOLDER_STEM[kind.slug]}_links }}}}": "\n".join(
            _design_link(kind, e) for e in entries_by_kind.get(kind.slug, [])
        )
        for kind in SDD_KINDS
    }
    writer(
        "design/index.md",
        _fill_template(docs_src / "design" / "_index.tmpl", landing_replacements),
    )


# ---------------------------------------------------------------------------
# Wrapper pages for sdd/ content
# ---------------------------------------------------------------------------


def render_sdd_wrappers(
    writer: Writer,
    entries_by_kind: dict[str, list[SddEntry]],
    resolver: LinkResolver,
) -> None:
    """Emit one virtual page per entry with links resolved to docs-tree paths."""
    for kind in SDD_KINDS:
        for e in entries_by_kind.get(kind.slug, []):
            dest = f"design/{kind.slug}/{e.slug}.md"
            content = e.source.read_text(encoding="utf-8")
            writer(dest, resolver.rewrite(content, e.source, dest))


def render_rfc_template(repo_root: Path, writer: Writer, resolver: LinkResolver) -> None:
    dest = "design/rfcs/rfc-template.md"
    source = repo_root / "sdd" / "rfcs" / "rfc-template.md"
    writer(dest, resolver.rewrite(source.read_text(encoding="utf-8"), source, dest))


# ---------------------------------------------------------------------------
# Link-rewritten pages (contributing.md, design/process.md)
# ---------------------------------------------------------------------------


def render_link_rewritten(
    writer: Writer,
    entries: list[LinkMapEntry],
    resolver: LinkResolver,
) -> None:
    for entry in entries:
        text = entry.source.read_text(encoding="utf-8")
        text = resolver.rewrite(text, entry.source, entry.dest)
        for old, new in entry.replacements.items():
            text = text.replace(old, new)
        writer(entry.dest, text)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


def copy_assets(assets_dir: Path, binary_writer: BinaryWriter) -> None:
    for asset in assets_dir.iterdir():
        if asset.is_file():
            binary_writer(f"assets/{asset.name}", asset.read_bytes())


# ---------------------------------------------------------------------------
# Example wrapper pages + index
# ---------------------------------------------------------------------------


def _example_page(entry: ExampleEntry) -> str:
    include_path = f"examples/{entry.subdir}/{entry.stem}.py"
    source_url = f"{REPO_URL}/blob/master/{include_path}"

    lines = [
        f"# {entry.title}",
        "",
        entry.description,
        "",
        "```python",
        f'--8<-- "{include_path}"',
        "```",
        "",
        "## See also",
        "",
    ]
    for sa in entry.see_also:
        lines.append(f"- [{sa.label}]({sa.url}) — {sa.note}")
    lines.append(f"- [Source: `{include_path}`]({source_url})")
    lines.append("")
    return "\n".join(lines)


def render_example_pages(writer: Writer, entries: Iterable[ExampleEntry]) -> None:
    for entry in entries:
        writer(f"examples/{entry.slug}.md", _example_page(entry))


def render_example_index(
    writer: Writer,
    entries: list[ExampleEntry],
    categories: list[ExampleCategory],
) -> None:
    """Emit ``examples/index.md`` — a table per category plus showcases."""
    lines = [
        "# Examples",
        "",
        "Runnable example scripts demonstrating every feature of `remote-store`. "
        "Each example is self-contained and uses a temporary directory so you can "
        "run them directly.",
        "",
    ]
    for i, cat in enumerate(categories):
        if i > 0:
            lines.append("")
        lines.append(f"## {cat.label}")
        lines.append("")
        if cat.blurb:
            lines.append(cat.blurb)
            lines.append("")
        lines.extend(["| Example | Description |", "|---------|-------------|"])
        for e in entries:
            if e.subdir == cat.subdir:
                lines.append(f"| [{e.title}]({e.slug}.md) | {e.description} |")

    lines.extend(
        [
            "",
            "## Showcases",
            "",
            "Full project examples demonstrating multiple extensions working together.",
            "",
            "| Example | Description |",
            "|---------|-------------|",
            "| [Medallion + Dagster Showcase](medallion-dagster.md) | "
            "End-to-end Bronze/Silver/Gold pipeline with Dagster and live MeteoSwiss data |",
            "",
            "Interactive Jupyter notebooks are also available in the",
            f"[`examples/notebooks/`]({REPO_URL}/tree/master/examples/notebooks)",
            "directory of the repository.",
            "",
        ]
    )
    writer("examples/index.md", "\n".join(lines))


# ---------------------------------------------------------------------------
# Medallion showcase (inlines README with heading offset)
# ---------------------------------------------------------------------------


def render_medallion_page(repo_root: Path, writer: Writer) -> None:
    readme = (repo_root / "examples" / "medallion_dagster" / "README.md").read_text(encoding="utf-8")
    body_lines: list[str] = []
    skipped_first = False
    in_code = False
    for line in readme.split("\n"):
        if line.startswith("```"):
            in_code = not in_code
        if not skipped_first and line.startswith("# "):
            skipped_first = True
            continue
        if not in_code and line.startswith("#"):
            line = "#" + line
        body_lines.append(line)
    body = "\n".join(body_lines)

    page = f"""\
# Medallion + Dagster Showcase

End-to-end Bronze/Silver/Gold pipeline with Dagster orchestration, \
demonstrating 4 remote-store extensions composing over live MeteoSwiss \
weather data.

{body}

## See also

- [Dagster](../dagster.md) — Dagster integration guide
- [Data Lake Patterns](../data-lake-patterns.md) — medallion architecture patterns
- [Architecture: Medallion + Dagster Showcase]\
(../design/research/research-medallion-dagster-showcase.md) — \
detailed design rationale, store topology, and Dagster asset graph
- [Source: `examples/medallion_dagster/`]\
(https://github.com/haalfi/remote-store/tree/master/examples/medallion_dagster/)
"""
    writer("examples/medallion-dagster.md", page)
