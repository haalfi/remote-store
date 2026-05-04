"""MkDocs hook: apply :class:`LinkResolver` to docs-src files.

Static `docs-src/` Markdown is read by MkDocs directly and not routed through
``gen_pages.py``. The bridge already rewrites links in dual sources (sdd files,
CHANGELOG, CONTRIBUTING, ...) when emitting their virtual pages. This hook
extends the same rewriter to docs-src files so that authors can write every
relative link as an on-disk repo path — a path that resolves on GitHub and
gets rewritten to the rendered URL here.

BK-171: with the docs-only carve-out removed from ``check-links``, every link
in every ``.md`` file must resolve on disk. This hook lets docs-src files
satisfy that rule by linking to repo sources (``../../sdd/specs/X.md``,
``../../examples/foo/bar.py``) without breaking on the docs site.

Spec: DOCFRAME-008.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files
    from mkdocs.structure.pages import Page

ROOT = Path(__file__).resolve().parent.parent  # scripts/ → repo root
SCRIPTS = Path(__file__).resolve().parent  # scripts/
DOCS_SRC = ROOT / "docs-src"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Lazy: defer constructing the resolver until first use so that import-time
# failures (missing optional deps in subset envs) don't kill MkDocs config
# parsing. The resolver caches the source map for the build.
_resolver = None


def _get_resolver():
    global _resolver
    if _resolver is None:
        from docs.link import LinkResolver, build_source_map
        from docs.scan import load_categories, scan_all_sdd, scan_dual_files, scan_examples

        sdd_entries = scan_all_sdd(ROOT)
        dual_entries = list(scan_dual_files(ROOT))
        categories = load_categories(ROOT / "examples" / "_categories.yml")
        example_entries = scan_examples(ROOT / "examples", categories)
        source_map = build_source_map(
            ROOT,
            sdd_entries=sdd_entries,
            dual_entries=dual_entries,
            example_entries=example_entries,
        )
        _resolver = LinkResolver(
            source_map=source_map,
            repo_root=ROOT,
            github_blob_url="https://github.com/haalfi/remote-store/blob/master",
        )
    return _resolver


def on_page_markdown(
    markdown: str,
    page: Page,
    config: MkDocsConfig,
    files: Files,
) -> str:
    """Rewrite links in docs-src files; pass everything else through.

    Dual virtual pages emitted by ``render_dual_pages`` are already rewritten
    upstream (in ``gen_pages.py``); we identify them by their ``abs_src_path``
    pointing into the gen-files temp dir rather than ``docs-src/``.
    """
    abs_src = getattr(page.file, "abs_src_path", None)
    if abs_src is None:
        return markdown
    src_path = Path(abs_src).resolve()
    try:
        src_path.relative_to(DOCS_SRC.resolve())
    except ValueError:
        # Outside docs-src/: gen-files virtual pages, pre-rewritten upstream.
        return markdown
    dest = page.file.src_uri
    return _get_resolver().rewrite(markdown, src_path, dest)
