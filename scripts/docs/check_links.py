"""Check internal markdown links in the repo.

Single rule (BK-171): every relative ``](path)`` link in every git-tracked
``.md`` file must resolve to an on-disk repo file. No docs-only carve-out;
no separate site-mode pass. The mkdocs build hook (``mkdocs_hooks.py``)
rewrites docs-only links to docs-site URLs at build time, so authors write
on-disk paths and both presentations work.

Exit 0 = clean.  Exit 1 = broken links found.
"""

from __future__ import annotations

import argparse
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
    resolved: str  # absolute on-disk path that did not exist


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

    parser = argparse.ArgumentParser(description="Check internal markdown links.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    broken = check_repo_links(repo_root)

    if broken:
        print(_format_broken(broken, repo_root), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
