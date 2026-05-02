"""Check internal markdown links in the repo.

Two modes:
  repo  — raw on-disk targets for every non-docs-only repo-tracked .md file
  site  — post-rewrite (LinkResolver) targets for dual files only
  all   — both (default)

Exit 0 = clean.  Exit 1 = broken links found.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Same pattern as link.py: matches ](target) and ](target "title").
_LINK_RE = re.compile(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "ftp://")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class BrokenLink:
    source: Path  # absolute path of the file containing the link
    line: int  # 1-based line number
    raw: str  # link target as written
    resolved: str  # what was resolved / attempted
    mode: str  # "repo" | "site"


def _extract_links(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, raw target) for internal inline links.

    Skips external URLs (http/https/mailto/ftp), anchor-only (#…) targets,
    fenced code blocks (``` / ~~~), and inline code spans (`...`).
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        clean = _INLINE_CODE_RE.sub("", line)
        for m in _LINK_RE.finditer(clean):
            raw = m.group(1)
            if any(raw.startswith(p) for p in _EXTERNAL_PREFIXES):
                continue
            if raw.startswith("#"):
                continue
            out.append((lineno, raw))
    return out


def _strip_fragment(target: str) -> str:
    return target.split("#")[0]


def _is_docs_only(path: Path, docs_src: Path) -> bool:
    """Return True if *path* is docs-only (lives under docs-src/)."""
    try:
        path.relative_to(docs_src)
        return True
    except ValueError:
        return False


def check_repo_links(repo_root: Path) -> list[BrokenLink]:
    """Raw on-disk check: every internal link in every non-docs-only .md must resolve.

    Docs-only files (docs-src/**) are skipped: their links reference virtual
    paths that exist only after the MkDocs build.  Those are verified instead
    by ``mkdocs build --strict`` (G-07).
    """
    from docs.scan import _git_repo_markdown  # type: ignore[import]

    docs_src = (repo_root / "docs-src").resolve()
    broken: list[BrokenLink] = []
    for md in _git_repo_markdown(repo_root):
        if _is_docs_only(md, docs_src):
            continue
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
                        mode="repo",
                    )
                )
    return broken


def _build_known_dests(repo_root: Path, source_map: dict[Path, str]) -> set[str]:
    dests: set[str] = set(source_map.values())
    docs_src = repo_root / "docs-src"
    if docs_src.is_dir():
        for md in docs_src.rglob("*.md"):
            dests.add(md.relative_to(docs_src).as_posix())
    return dests


def check_site_links(repo_root: Path) -> list[BrokenLink]:
    """Site-side check: post-rewrite links in dual files must resolve to known docs dests.

    The LinkResolver rewrites any link whose target is inside the repo root to
    either a relative site path (source-map hit) or an absolute GitHub blob URL
    (repo file not on the docs site).  A rewritten link is only a relative path
    when the resolver found the target in the source map — and that dest is by
    construction in ``known_dests``.

    The case this catches is therefore links whose target resolves **outside**
    the repo root: ``_lookup`` returns ``None``, the link is left unchanged, and
    the original repo-relative href does not match any known docs destination.
    """
    from docs.link import LinkResolver, build_source_map  # type: ignore[import]
    from docs.scan import scan_all_sdd, scan_dual_files  # type: ignore[import]

    dual_entries = list(scan_dual_files(repo_root))
    source_map: dict[Path, str] = build_source_map(
        repo_root,
        sdd_entries=scan_all_sdd(repo_root),
        dual_entries=dual_entries,
    )

    known_dests = _build_known_dests(repo_root, source_map)
    resolver = LinkResolver(
        source_map=source_map,
        repo_root=repo_root,
        github_blob_url="https://github.com/placeholder/blob/main",
    )

    broken: list[BrokenLink] = []
    for entry in dual_entries:
        try:
            text = entry.source.read_text(encoding="utf-8")
        except OSError:
            continue
        rewritten = resolver.rewrite(text, entry.source, entry.dest)
        for lineno, raw in _extract_links(rewritten):
            target = _strip_fragment(raw)
            if not target:
                continue
            resolved_dest = posixpath.normpath(posixpath.join(posixpath.dirname(entry.dest), target))
            if resolved_dest not in known_dests:
                broken.append(
                    BrokenLink(
                        source=entry.source,
                        line=lineno,
                        raw=raw,
                        resolved=resolved_dest,
                        mode="site",
                    )
                )
    return broken


def _format_broken(broken: list[BrokenLink], repo_root: Path) -> str:
    lines: list[str] = []
    for b in sorted(broken, key=lambda b: (str(b.source), b.line)):
        rel = b.source.relative_to(repo_root)
        lines.append(f"{rel}:{b.line}: {b.raw!r} → {b.resolved}  ({b.mode})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # When run directly via `python scripts/docs/check_links.py`, scripts/ may
    # not be on sys.path.  Add it so docs.* imports resolve.
    _scripts = str(Path(__file__).resolve().parent.parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    parser = argparse.ArgumentParser(description="Check internal markdown links.")
    parser.add_argument("--mode", choices=["repo", "site", "all"], default="all")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    broken: list[BrokenLink] = []
    if args.mode in ("repo", "all"):
        broken.extend(check_repo_links(repo_root))
    if args.mode in ("site", "all"):
        broken.extend(check_site_links(repo_root))

    if broken:
        print(_format_broken(broken, repo_root), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
