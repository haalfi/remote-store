"""Check markdown links in the repo.

Two rules, both enforced by ``main`` over every git-tracked ``.md`` file:

* On-disk links (BK-171, DOCFRAME-008): every relative ``](path)`` link
  must resolve to an on-disk repo file. No docs-only carve-out; no
  separate site-mode pass. The mkdocs build hook (``mkdocs_hooks.py``)
  rewrites docs-only links to docs-site URLs at build time, so authors
  write on-disk paths and both presentations work.

* Docs-site links (BK-236, DOCFRAME-009): every absolute
  ``https://docs.remotestore.dev/stable/<path>/`` (or ``/latest/``) link
  must resolve to a page the docs site actually builds. The valid page
  set is derived from ``build_source_map`` — the same source→docs-URL
  map the mkdocs bridge uses — so a stale or mistyped path segment
  (``/stable/api/store/`` for ``/stable/reference/api/store/``) fails the
  gate offline, with no live HTTP request and no docs build.

Exit 0 = clean.  Exit 1 = broken links found.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Same pattern as link.py: matches ](target) and ](target "title").
_LINK_RE = re.compile(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "ftp://")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# Host of the published docs site (mkdocs.yml site_url).
_DOCS_SITE_HOST = "docs.remotestore.dev"
# mike publishes versioned docs; "stable" and "latest" are the moving
# aliases. A link pinned to a numbered version (/0.25/...) points at a
# frozen snapshot the current docs-src/ tree cannot vouch for, so it is
# left unchecked.
_DOCS_VERSION_ALIASES = ("stable", "latest")


@dataclass(frozen=True)
class BrokenLink:
    source: Path  # absolute path of the file containing the link
    line: int  # 1-based line number
    raw: str  # link target as written
    resolved: str  # what the link should have resolved to, but did not


def _iter_link_targets(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(1-based line number, raw target)`` for every inline link.

    Skips fenced code blocks (``` / ~~~) and inline code spans (`...`).
    External-URL and anchor filtering is left to the caller.
    """
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        clean = _INLINE_CODE_RE.sub("", line)
        for m in _LINK_RE.finditer(clean):
            yield lineno, m.group(1)


def _extract_links(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, raw target) for internal inline links.

    Skips external URLs (http/https/mailto/ftp), anchor-only (#…) targets,
    fenced code blocks (``` / ~~~), and inline code spans (`...`).
    """
    out: list[tuple[int, str]] = []
    for lineno, raw in _iter_link_targets(text):
        if any(raw.startswith(p) for p in _EXTERNAL_PREFIXES):
            continue
        if raw.startswith("#"):
            continue
        out.append((lineno, raw))
    return out


def _strip_fragment(target: str) -> str:
    return target.split("#")[0]


def check_repo_links(repo_root: Path) -> list[BrokenLink]:
    """On-disk check: every internal link in every git-tracked ``.md`` resolves.

    BK-171: this includes docs-only files under ``docs-src/``. The mkdocs hook
    rewrites their on-disk targets to docs-site URLs at build time, so authors
    write on-disk paths everywhere.
    """
    from docs.scan import _git_repo_markdown  # type: ignore[import]

    broken: list[BrokenLink] = []
    for md in _git_repo_markdown(repo_root):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, raw in _extract_links(text):
            target = _strip_fragment(raw)
            if not target:
                continue
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                broken.append(
                    BrokenLink(
                        source=md,
                        line=lineno,
                        raw=raw,
                        resolved=str(resolved),
                    )
                )
    return broken


def _normalize_docs_dest(dest: str) -> str:
    """Map a docs-root-relative source path to its directory-URL page path.

    MkDocs serves with ``use_directory_urls``: ``index.md`` pages collapse
    onto their directory, other pages drop the ``.md`` suffix, and
    non-page assets keep their path verbatim. ``index.md`` (the site root)
    becomes the empty string.
    """
    if dest == "index.md":
        return ""
    if dest.endswith("/index.md"):
        return dest[: -len("/index.md")]
    if dest.endswith(".md"):
        return dest[: -len(".md")]
    return dest


def _docs_site_pages(repo_root: Path) -> set[str]:
    """Return every path the docs site serves, in directory-URL form.

    Built from ``build_source_map`` — the single source→docs-URL map the
    mkdocs bridge uses — so the valid set stays in lockstep with the real
    site. Each served page also contributes every ancestor directory: a
    section directory has an index page (``mkdocs-section-index`` plus
    literate-nav), so ``reference/api/store`` makes ``reference`` and
    ``reference/api`` valid section URLs too.
    """
    from docs.link import build_source_map  # type: ignore[import]
    from docs.scan import (  # type: ignore[import]
        load_categories,
        scan_all_sdd,
        scan_dual_files,
        scan_examples,
    )

    categories = load_categories(repo_root / "examples" / "_categories.yml")
    source_map = build_source_map(
        repo_root,
        sdd_entries=scan_all_sdd(repo_root),
        dual_entries=list(scan_dual_files(repo_root)),
        example_entries=scan_examples(repo_root / "examples", categories),
    )

    pages: set[str] = {""}  # the site root (docs-src/index.md)
    for dest in source_map.values():
        page = _normalize_docs_dest(dest)
        pages.add(page)
        parts = page.split("/")
        for depth in range(1, len(parts)):
            pages.add("/".join(parts[:depth]))
    return pages


def _resolve_docs_site_path(url: str) -> str | None:
    """Map a docs-site URL to the page path to validate, or ``None`` to skip.

    Returns the directory-URL page path (``""`` for the site root) for
    ``https://docs.remotestore.dev/<alias>/<path>`` links where ``<alias>``
    is a moving version alias. Anything else — a different host, the bare
    site root (which redirects to the default version), or a
    numbered-version snapshot — is out of scope and yields ``None``.
    """
    if not url.startswith(("http://", "https://")):
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.netloc != _DOCS_SITE_HOST:
        return None
    path = parts.path.strip("/")
    if not path:
        return None  # bare site root: redirects to the default version
    segments = path.split("/")
    if segments[0] not in _DOCS_VERSION_ALIASES:
        return None  # numbered-version snapshot, or no version prefix
    return "/".join(segments[1:])


def _find_broken_docs_site_links(text: str, source: Path, valid_pages: set[str]) -> list[BrokenLink]:
    """Flag docs-site links in *text* whose target page is not in *valid_pages*."""
    broken: list[BrokenLink] = []
    for lineno, raw in _iter_link_targets(text):
        page = _resolve_docs_site_path(raw)
        if page is None or page in valid_pages:
            continue
        broken.append(
            BrokenLink(
                source=source,
                line=lineno,
                raw=raw,
                resolved=f"no docs-site page: {page or '(root)'}",
            )
        )
    return broken


def check_docs_site_links(repo_root: Path) -> list[BrokenLink]:
    """Docs-site check: every ``docs.remotestore.dev`` stable/latest link resolves.

    BK-236 (DOCFRAME-009): an absolute link into the published docs site
    is validated against the page set the site actually builds, so a
    mistyped or stale path segment fails the gate offline.
    """
    from docs.scan import _git_repo_markdown  # type: ignore[import]

    valid_pages = _docs_site_pages(repo_root)
    broken: list[BrokenLink] = []
    for md in _git_repo_markdown(repo_root):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        broken.extend(_find_broken_docs_site_links(text, md, valid_pages))
    return broken


def _format_broken(broken: list[BrokenLink], repo_root: Path) -> str:
    lines: list[str] = []
    for b in sorted(broken, key=lambda b: (str(b.source), b.line)):
        rel = b.source.relative_to(repo_root)
        lines.append(f"{rel}:{b.line}: {b.raw!r} → {b.resolved}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # When run directly via `python scripts/docs/check_links.py`, scripts/ may
    # not be on sys.path.  Add it so docs.* imports resolve.
    _scripts = str(Path(__file__).resolve().parent.parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    parser = argparse.ArgumentParser(description="Check markdown links.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    broken = check_repo_links(repo_root) + check_docs_site_links(repo_root)

    if broken:
        print(_format_broken(broken, repo_root), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
