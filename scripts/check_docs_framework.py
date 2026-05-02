"""PR-time gate for the documentation framework (DOCFRAME-004, Spec 047).

Checks G-01 through G-06.  G-07 (``mkdocs build --strict``) is handled
separately by ``hatch run docs-build``.

Exit 0 when all checks pass.  Non-zero on failure; one line per violation
printed to stderr, sorted by path for stable diffs.

Run with:
    hatch run docs-check
    python scripts/check_docs_framework.py
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = ROOT / "docs-src"

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from docs.scan import (  # noqa: E402
    _classify_file,
    _git_repo_markdown,
    scan_dual_files,
)

_JINJA_RE = re.compile(r"\{[%{]")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_INCLUDE_MARKDOWN_RE = re.compile(r"include-markdown")

# Directories excluded from G-01: infrastructure trees outside the docs
# framework (Claude Code skills, GitHub templates).
_G01_EXCLUDE_DIRS = frozenset({".claude", ".github"})

# Expected URL prefixes per top-level nav section.  Sections absent from this
# table are not checked (e.g. Tutorial, Home).
_SECTION_PREFIXES: dict[str, tuple[str, ...]] = {
    "Guides": ("guides/",),
    "Reference": ("reference/",),
    "Explanation": ("explanation/",),
}


def _strip_inline_code(line: str) -> str:
    """Remove backtick-delimited inline code spans from *line*."""
    return _INLINE_CODE_RE.sub("", line)


def _is_in_fence(line: str, in_fence: bool) -> bool:
    """Return updated fence state after processing *line*."""
    stripped = line.strip()
    if stripped.startswith(("```", "~~~")):
        return not in_fence
    return in_fence


# ---------------------------------------------------------------------------
# G-01: every .md resolves to exactly one class
# ---------------------------------------------------------------------------


def _check_g01(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in _git_repo_markdown(repo_root):
            rel = path.relative_to(repo_root)
            # Infrastructure dirs are outside the docs framework; skip.
            if any(part in _G01_EXCLUDE_DIRS for part in rel.parts):
                continue
            try:
                _classify_file(path, repo_root)
            except ValueError as exc:
                errors.append(f"G-01 {rel}: {exc}")
    return sorted(errors)


# ---------------------------------------------------------------------------
# G-02: injective source→dest map
# ---------------------------------------------------------------------------


def _check_g02(repo_root: Path) -> list[str]:
    errors: list[str] = []
    dest_to_sources: dict[str, list[Path]] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for entry in scan_dual_files(repo_root):
            dest_to_sources.setdefault(entry.dest, []).append(entry.source)
    for dest, sources in sorted(dest_to_sources.items()):
        if len(sources) > 1:
            rel_sources = sorted(str(s.relative_to(repo_root)) for s in sources)
            errors.append(f"G-02 {dest}: multiple sources → {rel_sources}")
    return errors


# ---------------------------------------------------------------------------
# G-03: no Jinja syntax in dual files
# ---------------------------------------------------------------------------


def _check_g03(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        entries = list(scan_dual_files(repo_root))
    for entry in entries:
        text = entry.source.read_text(encoding="utf-8")
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            in_fence = _is_in_fence(line, in_fence)
            if in_fence:
                continue
            cleaned = _strip_inline_code(line)
            if _JINJA_RE.search(cleaned):
                rel = entry.source.relative_to(repo_root)
                errors.append(f"G-03 {rel}:{lineno}: Jinja-like syntax: {line.strip()!r}")
    return sorted(errors)


# ---------------------------------------------------------------------------
# G-04: no include-markdown in docs-src; no _link_map.yml
# ---------------------------------------------------------------------------


def _check_g04(repo_root: Path) -> list[str]:
    errors: list[str] = []
    link_map = repo_root / "docs-src" / "_link_map.yml"
    if link_map.exists():
        errors.append("G-04 docs-src/_link_map.yml: file must not exist (AUTHORING Rule 4)")
    docs_src = repo_root / "docs-src"
    if docs_src.is_dir():
        for md in sorted(docs_src.rglob("*.md")):
            text = md.read_text(encoding="utf-8")
            in_fence = False
            for lineno, line in enumerate(text.splitlines(), 1):
                in_fence = _is_in_fence(line, in_fence)
                if in_fence:
                    continue
                cleaned = _strip_inline_code(line)
                if _INCLUDE_MARKDOWN_RE.search(cleaned):
                    rel = md.relative_to(repo_root)
                    errors.append(f"G-04 {rel}:{lineno}: include-markdown directive (AUTHORING Rule 4)")
    return sorted(errors)


# ---------------------------------------------------------------------------
# G-05: relative links in dual files resolve on disk
# ---------------------------------------------------------------------------


def _check_g05(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        entries = list(scan_dual_files(repo_root))
    for entry in entries:
        text = entry.source.read_text(encoding="utf-8")
        base = entry.source.parent
        in_fence = False
        for line in text.splitlines():
            in_fence = _is_in_fence(line, in_fence)
            if in_fence:
                continue
            cleaned = _strip_inline_code(line)
            for m in _LINK_RE.finditer(cleaned):
                target = m.group(1)
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                clean = target.split("#")[0]
                if not clean:
                    continue
                if not (base / clean).resolve().exists():
                    rel = entry.source.relative_to(repo_root)
                    errors.append(f"G-05 {rel}: broken link → {target!r}")
    return sorted(errors)


# ---------------------------------------------------------------------------
# G-06: URL prefix matches nav section
# ---------------------------------------------------------------------------


def _iter_nav_pages(node: object, docs_src: Path, prefix: str = "") -> list[str]:
    """Recursively collect page paths from a literate-nav node.

    Returns paths relative to the root ``docs-src/`` directory.  Directory
    entries (ending with ``/``) are resolved via child ``_nav.yml`` files when
    they exist; otherwise the directory path itself is returned.
    """
    pages: list[str] = []
    if isinstance(node, str):
        full = prefix + node
        if node.endswith("/"):
            child_nav = docs_src / node.rstrip("/") / "_nav.yml"
            if child_nav.exists():
                child = yaml.safe_load(child_nav.read_text(encoding="utf-8")) or []
                child_docs_src = docs_src / node.rstrip("/")
                for item in child if isinstance(child, list) else [child]:
                    pages.extend(_iter_nav_pages(item, child_docs_src, full))
            else:
                pages.append(full)
        else:
            pages.append(full)
    elif isinstance(node, dict):
        for child in node.values():
            pages.extend(_iter_nav_pages(child, docs_src, prefix))
    elif isinstance(node, list):
        for item in node:
            pages.extend(_iter_nav_pages(item, docs_src, prefix))
    return pages


def _check_g06(repo_root: Path) -> list[str]:
    nav_file = repo_root / "docs-src" / "_nav.yml"
    if not nav_file.exists():
        return ["G-06 docs-src/_nav.yml: not found"]

    nav = yaml.safe_load(nav_file.read_text(encoding="utf-8")) or []
    docs_src = repo_root / "docs-src"
    errors: list[str] = []

    for section_item in nav if isinstance(nav, list) else []:
        if not isinstance(section_item, dict):
            continue
        for section_label, section_content in section_item.items():
            allowed = _SECTION_PREFIXES.get(section_label)
            if allowed is None:
                continue
            for page in _iter_nav_pages(section_content, docs_src):
                if "/" not in page:
                    continue  # root-level pages are exempt
                if not any(page.startswith(pfx) for pfx in allowed):
                    errors.append(
                        f"G-06 {page}: under {section_label!r} but does not start with "
                        + " or ".join(repr(p) for p in allowed)
                    )

    return sorted(errors)


# ---------------------------------------------------------------------------
# G-07: legacy api/ directory must not exist
# ---------------------------------------------------------------------------


def _check_g07(repo_root: Path) -> list[str]:
    legacy = repo_root / "docs-src" / "api"
    if legacy.exists():
        return [
            "G-07 docs-src/api/: legacy directory exists — API reference must live "
            "under docs-src/reference/api/ (Rule 7)"
        ]
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_CHECKS = [
    ("G-01", _check_g01),
    ("G-02", _check_g02),
    ("G-03", _check_g03),
    ("G-04", _check_g04),
    ("G-05", _check_g05),
    ("G-06", _check_g06),
    ("G-07", _check_g07),
]


def main() -> int:
    all_errors: list[str] = []
    for _check_id, fn in _CHECKS:
        try:
            all_errors.extend(fn(ROOT))
        except Exception as exc:  # noqa: BLE001
            all_errors.append(f"{_check_id} (internal error): {exc}")

    if all_errors:
        for line in all_errors:
            print(line, file=sys.stderr)
        return 1

    print(f"docs-framework check passed ({len(_CHECKS)} checks: G-01..G-07).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
