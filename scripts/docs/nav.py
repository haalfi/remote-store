"""SUMMARY.md assembly from ``_nav.yml`` files plus scanned sections.

Literate navigation: each section directory may carry a ``_nav.yml`` listing
its entries. Leaves are files; entries ending with ``"/"`` are subsections;
dict leaves with a list value act as virtual groups (sidebar heading, no
page). Sections without a ``_nav.yml`` can be auto-populated from scanned
records — flat (specs, adrs, ...) or grouped (examples by category).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import mkdocs_gen_files
import yaml

from .scan import SDD_KINDS

if TYPE_CHECKING:
    from pathlib import Path

    from .scan import ExampleCategory, ExampleEntry, SddEntry


@dataclass(frozen=True)
class ScannedSections:
    flat: dict[str, list[tuple[str, str]]]
    grouped: dict[str, list[tuple[str, list[tuple[str, str]]]]]


def scanned_sections_from(
    sdd_entries: dict[str, list[SddEntry]],
    examples: list[ExampleEntry],
    categories: list[ExampleCategory],
) -> ScannedSections:
    flat: dict[str, list[tuple[str, str]]] = {}
    for kind in SDD_KINDS:
        entries = sdd_entries.get(kind.slug, [])
        flat[f"design/{kind.slug}"] = [
            (
                f"{e.number}: {e.title}" if kind.numbered else e.title,
                f"design/{kind.slug}/{e.slug}.md",
            )
            for e in entries
        ]

    example_groups: list[tuple[str, list[tuple[str, str]]]] = []
    for cat in categories:
        items = [(e.title, f"examples/{e.slug}.md") for e in examples if e.subdir == cat.subdir]
        example_groups.append((cat.label, items))
    example_groups.append(("Showcases", [("Medallion + Dagster Showcase", "examples/medallion-dagster.md")]))

    return ScannedSections(flat=flat, grouped={"examples": example_groups})


def build_summary(docs_src: Path, sections: ScannedSections) -> str:
    """Walk ``docs-src/_nav.yml`` recursively and build ``SUMMARY.md`` text."""
    nav = mkdocs_gen_files.Nav()

    def load(nav_file: Path, section_dir: str, nav_path: tuple[str, ...]) -> None:
        entries = yaml.safe_load(nav_file.read_text(encoding="utf-8")) or []
        process(entries, section_dir, nav_path)

    def process(
        entries: list[dict[str, Any]],
        section_dir: str,
        nav_path: tuple[str, ...],
    ) -> None:
        for entry in entries:
            for label, target in entry.items():
                if isinstance(target, list):
                    process(target, section_dir, nav_path + (label,))
                elif isinstance(target, str) and target.endswith("/"):
                    subdir_name = target.rstrip("/")
                    full_dir = f"{section_dir}/{subdir_name}" if section_dir else subdir_name
                    child_path = nav_path + (label,)
                    nav[child_path] = f"{full_dir}/index.md"

                    child_nav = docs_src / full_dir / "_nav.yml"
                    if child_nav.exists():
                        load(child_nav, full_dir, child_path)
                    elif full_dir in sections.grouped:
                        for group_label, group_items in sections.grouped[full_dir]:
                            group_path = child_path + (group_label,)
                            for scan_label, scan_file in group_items:
                                nav[group_path + (scan_label,)] = scan_file
                    elif full_dir in sections.flat:
                        for scan_label, scan_file in sections.flat[full_dir]:
                            nav[child_path + (scan_label,)] = scan_file
                else:
                    full_path = f"{section_dir}/{target}" if section_dir else target
                    leaf = nav_path + (label,) if nav_path else (label,)
                    nav[leaf] = full_path

    load(docs_src / "_nav.yml", "", ())
    return "".join(nav.build_literate_nav())
