"""Markdown link rewriting for repo-rooted files served into the docs tree.

When we inline a repo file (sdd/research/x.md, CONTRIBUTING.md, ...) as a
virtual page at some other path, its relative links break. :class:`LinkResolver`
walks each ``](target)`` link and:

1. leaves absolute URLs and pure anchors alone;
2. resolves the target against the *source* file's directory;
3. if the resolved path is a known doc (source map hit), rewrites to the
   correct relative path from the *dest* virtual path;
4. else, if the resolved path is inside the repo, rewrites to a GitHub blob
   URL (so ``--strict`` builds don't fail);
5. otherwise leaves the link alone.

This replaces hand-maintained ``{old_string: new_string}`` rewrite tables.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_LINK_RE = re.compile(r"\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")


class LinkResolver:
    """Rewrite markdown links using a repo-source → docs-dest map."""

    def __init__(
        self,
        source_map: dict[Path, str],
        repo_root: Path,
        github_blob_url: str,
    ) -> None:
        self._map = {src.resolve(): dest for src, dest in source_map.items()}
        self._repo_root = repo_root.resolve()
        self._blob = github_blob_url.rstrip("/")

    def rewrite(self, text: str, source: Path, dest: str) -> str:
        """Rewrite links in *text*, originally from *source*, served at *dest*."""
        source = source.resolve()

        def repl(match: re.Match[str]) -> str:
            href = match.group(1)
            title = match.group(2) or ""
            if href.startswith(("http://", "https://", "mailto:", "#")):
                return match.group(0)

            path_part, sep, frag = href.partition("#")
            if not path_part:
                return match.group(0)

            try:
                target = (source.parent / path_part).resolve()
            except (OSError, ValueError):
                return match.group(0)

            new_href = self._lookup(target)
            if new_href is None:
                return match.group(0)

            # Virtual docs destinations are relative; external URLs are absolute.
            if new_href.startswith(("http://", "https://")):
                return f"]({new_href}{sep}{frag}{title})"
            rel = _rel_posix(dest, new_href)
            return f"]({rel}{sep}{frag}{title})"

        return _LINK_RE.sub(repl, text)

    def _lookup(self, target: Path) -> str | None:
        if target in self._map:
            return self._map[target]
        try:
            rel = target.relative_to(self._repo_root).as_posix()
        except ValueError:
            return None
        return f"{self._blob}/{rel}"


def _rel_posix(from_dest: str, to_dest: str) -> str:
    """Relative posix path from one virtual doc to another."""
    from_dir = posixpath.dirname(from_dest)
    if not from_dir:
        return to_dest
    rel = posixpath.relpath(to_dest, from_dir)
    return rel.replace("\\", "/")


def build_source_map(
    repo_root: Path,
    *,
    sdd_entries: dict[str, list],  # kind_slug -> list[SddEntry]
    link_entries: list,  # unused after DOCFRAME-005; kept for API compat
    include_pairs: list[tuple[Path, str]],  # unused after DOCFRAME-005; kept for API compat
) -> dict[Path, str]:
    """Assemble the absolute-source → virtual-dest map for the resolver."""
    source_map: dict[Path, str] = {}

    for kind_slug, entries in sdd_entries.items():
        for e in entries:
            source_map[e.source.resolve()] = f"explanation/design/{kind_slug}/{e.slug}.md"

    # docs-src/ files are served at their path relative to docs-src/.
    # Including them lets the resolver rewrite repo-relative links that point
    # into docs-src/ (e.g. from dual files under examples/ or root).
    docs_src = repo_root / "docs-src"
    if docs_src.is_dir():
        for md in docs_src.rglob("*.md"):
            source_map.setdefault(md.resolve(), md.relative_to(docs_src).as_posix())

    for entry in link_entries:
        source_map[entry.source] = entry.dest

    for src, dest in include_pairs:
        source_map.setdefault(src, dest)

    return source_map
