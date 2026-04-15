"""MkDocs gen-files hook: orchestrate scan -> render -> nav.

Static authored content lives in ``docs-src/``. This hook synthesizes dynamic
pages: sdd/ and examples/ scans, template fills, wrapper pages, assets, and
``SUMMARY.md``. See :mod:`scripts.docs` for the helpers and
``sdd/adrs/0007-docs-src-literate-nav.md`` for the design.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = ROOT / "docs-src"

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from docs import nav as nav_mod  # noqa: E402
from docs import render, scan  # noqa: E402
from docs.link import LinkResolver, build_source_map  # noqa: E402


def _writer(virtual_path: str, text: str) -> None:
    with mkdocs_gen_files.open(virtual_path, "w") as f:
        f.write(text)


def _binary_writer(virtual_path: str, data: bytes) -> None:
    with mkdocs_gen_files.open(virtual_path, "wb") as f:
        f.write(data)


# --- 1. Scan ----------------------------------------------------------------

sdd_entries = scan.scan_all_sdd(ROOT)
categories = scan.load_categories(ROOT / "examples" / "_categories.yml")
examples = scan.scan_examples(ROOT / "examples", categories)
link_entries = scan.load_link_map(DOCS_SRC / "_link_map.yml", ROOT)
include_pairs = scan.scan_include_wrappers(DOCS_SRC)

resolver = LinkResolver(
    build_source_map(
        ROOT,
        sdd_entries=sdd_entries,
        link_entries=link_entries,
        include_pairs=include_pairs,
    ),
    repo_root=ROOT,
    github_blob_url="https://github.com/haalfi/remote-store/blob/master",
)

# --- 2. Render --------------------------------------------------------------

render.render_sdd_indexes(DOCS_SRC, _writer, sdd_entries)
render.render_sdd_wrappers(_writer, sdd_entries, resolver)
render.render_rfc_template(ROOT, _writer, resolver)
render.render_link_rewritten(_writer, link_entries, resolver)
render.copy_assets(ROOT / "assets", _binary_writer)
render.render_example_pages(_writer, examples)
render.render_medallion_page(ROOT, _writer, resolver)
render.render_example_index(_writer, examples, categories)

# --- 3. Nav -----------------------------------------------------------------

sections = nav_mod.scanned_sections_from(sdd_entries, examples, categories)
_writer("SUMMARY.md", nav_mod.build_summary(DOCS_SRC, sections))
