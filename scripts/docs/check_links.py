"""Check markdown links in the repo.

Three rules, all enforced by ``main`` over every git-tracked ``.md`` file:

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

* Fragment resolution (ID-180): every ``[text](path.md#fragment)`` link
  whose consumer is not on the historical denylist must resolve to either
  an explicit ``<a id="fragment">`` tag in ``path.md`` or a heading whose
  GitHub-style slug equals ``fragment``. Anchor uniqueness (M2) and
  heading-adjacency (M3) of every ``<a id>`` in a target file are checked
  in the same pass.

Two further rules extend the same offline machinery to the repo's
non-Markdown discovery files (BK-307, BK-317), which the ``.md``-only walk
above never sees:

* context7 manifest paths (BK-307): every entry in the root
  ``context7.json`` ``folders`` / ``excludeFolders`` / ``excludeFiles``
  lists must resolve to a real on-disk path, so a directory rename cannot
  silently drop a folder from context7 indexing. Per the context7 schema,
  ``folders`` / ``excludeFolders`` are repo-root-relative paths while
  ``excludeFiles`` matches by *filename only* (basename); the context7.com
  ``url`` is external and out of scope.

* context7 manifest caps (BK-317): the root ``context7.json`` and the
  docs-site ``docs-src/context7.json`` must stay within Context7's per-field
  maxima (``folders`` <= 5, ``excludeFolders`` <= 50, ``excludeFiles`` <= 100,
  ``rules`` <= 50 of <= 255 chars each). Context7 silently rejects a manifest
  that exceeds one on save / re-parse, so the entry stops tracking its source;
  this fails that offline instead.

Exit 0 = clean.  Exit 1 = broken links found.
"""

from __future__ import annotations

import argparse
import json
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

# ID-180 fragment resolution.
# Matches <a id="anchor"></a> — the carrier this repo uses for stable section IDs.
_ANCHOR_RE = re.compile(r'<a\s+id="([^"]+)"\s*>\s*</a>')
# Matches a Markdown ATX heading (# .. ######). Captures level and text.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Repo-relative paths whose outbound fragment refs are NOT validated.
# Historical / append-only docs; referenced anchors may name sections that
# existed at the time the entry was written.
_FRAGMENT_CONSUMER_DENYLIST = (
    "CHANGELOG.md",
    "sdd/BACKLOG-DONE.md",
    "sdd/audits/",
    "sdd/research/",
    "sdd/traces/",
)

# Host of the published docs site (mkdocs.yml site_url).
_DOCS_SITE_HOST = "docs.remotestore.dev"
# mike publishes versioned docs; "stable" and "latest" are the moving
# aliases. A link pinned to a numbered version (/0.25/...) points at a
# frozen snapshot the current docs-src/ tree cannot vouch for, so it is
# left unchecked.
_DOCS_VERSION_ALIASES = ("stable", "latest")
# Machine-readable discovery artifacts served at each version root but NOT built
# as mkdocs pages: the mkdocs-llmstxt plugin emits ``llms.txt`` / ``llms-full.txt``
# (ID-220), and Read the Docs emits ``llms-api.txt`` at build time (ID-226). They
# have no entry in the docs-site page set, so links to them are checked for the
# well-known filename rather than against ``build_source_map``.
_DOCS_GENERATED_ROOT_FILES = frozenset({"llms.txt", "llms-full.txt", "llms-api.txt"})


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


def _slugify_heading(text: str) -> str:
    """Slug for a Markdown heading, in the dialect both GitHub and mkdocs accept.

    Lowercase, drop punctuation, each space becomes a single dash. Both the
    strict GitHub form (consecutive dashes preserved) and the collapsed form
    (consecutive dashes merged — what python-markdown / mkdocs produce) are
    returned, so a consumer reference written in either style resolves.

    Strips backticks and asterisks (Markdown emphasis markers) but preserves
    underscores, which are valid identifier characters and appear in headings
    like ``S3-011: delete_folder Recursive``. A trailing kramdown / pymdown
    attr-list block (``{ #id .class }``) is stripped before slugging; the
    explicit ID is captured separately by the caller.

    Returns the strict form; ``_slug_variants`` yields both.
    """
    s = re.sub(r"\{[^}]*\}\s*$", "", text)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # [text](url) → text
    s = re.sub(r"[`*]", "", s)
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = s.replace(" ", "-")
    return s.strip("-")


def _slug_variants(text: str) -> tuple[str, ...]:
    """Yield both the strict and dash-collapsed slug forms for *text*."""
    strict = _slugify_heading(text)
    if not strict:
        return ()
    collapsed = re.sub(r"-+", "-", strict)
    if collapsed == strict:
        return (strict,)
    return (strict, collapsed)


# mkdocs attr-list explicit anchor: trailing { #id ... }.
_ATTR_LIST_RE = re.compile(r"\{\s*#([^\s}]+)[^}]*\}\s*$")


@dataclass(frozen=True)
class _AnchorIndex:
    """Set of fragment IDs a target Markdown file exposes."""

    ids: frozenset[str]
    duplicate_ids: tuple[str, ...]
    duplicate_heading_slugs: tuple[str, ...]
    orphan_ids: tuple[tuple[int, str], ...]


def _extract_anchors(text: str) -> _AnchorIndex:
    """Collect every <a id> and heading slug in *text*.

    Returns the set of resolvable fragment IDs, plus duplicate-anchor and
    orphan-anchor diagnostics. An orphan is an ``<a id>`` not immediately
    followed by a Markdown heading (after optional blank lines), per M3.

    Duplicate detection separates two shapes:

    - ``duplicate_ids`` — the same ``<a id="X">`` tag appears on more than
      one line. Always a bug; the author typed the same identifier twice.
    - ``duplicate_heading_slugs`` — two distinct headings produce the same
      strict slug (e.g. two ``## Rules`` in one file). Both render as
      ``#rules`` on GitHub but only the first resolves, so any consumer
      reference is ambiguous. Common in pages with intentional structural
      duplication (async + sync API on one page, two-presentation ripple
      tables), so the caller decides whether to surface these — typically
      only when at least one live consumer references the colliding slug.

    The deliberate redundancy pattern — ``<a id="rules">`` immediately
    followed by ``## Rules`` (same value) — is not flagged: the anchor
    and the heading slug target the same location, so the id is not
    ambiguous. Authors use this to freeze the section identity against
    future heading-text edits.
    """
    in_fence = False
    ids: set[str] = set()
    duplicate_anchors: list[str] = []
    duplicate_headings: list[str] = []
    orphans: list[tuple[int, str]] = []
    seen: set[str] = set()
    heading_slugs_seen: set[str] = set()

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Headings: collect their GitHub slug plus any attr-list explicit anchor.
        m = _HEADING_RE.match(line)
        if m:
            heading_text = m.group(2)
            attr_m = _ATTR_LIST_RE.search(heading_text)
            if attr_m:
                ids.add(attr_m.group(1))
            variants = _slug_variants(heading_text)
            # Track only the strict slug for collision detection — the
            # collapsed variant is a consumer-side fallback, not an
            # independent identity.
            if variants:
                strict = variants[0]
                if strict in heading_slugs_seen:
                    duplicate_headings.append(strict)
                heading_slugs_seen.add(strict)
            for variant in variants:
                ids.add(variant)
            continue
        # Explicit <a id> tags.
        for am in _ANCHOR_RE.finditer(line):
            anchor = am.group(1)
            if anchor in seen:
                duplicate_anchors.append(anchor)
            seen.add(anchor)
            ids.add(anchor)
            # M3 (orphan check) applies only to anchors on their own line — an
            # inline anchor inside a list item or heading is co-located with
            # its semantic target and need not be followed by a heading.
            stripped = line.strip()
            anchor_only_line = bool(_ANCHOR_RE.fullmatch(stripped))
            if not anchor_only_line:
                continue
            j = idx + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                # Another anchor-only line is allowed; keep looking.
                if _ANCHOR_RE.fullmatch(nxt):
                    j += 1
                    continue
                break
            if j >= len(lines) or not _HEADING_RE.match(lines[j]):
                orphans.append((idx + 1, anchor))
    return _AnchorIndex(
        ids=frozenset(ids),
        duplicate_ids=tuple(duplicate_anchors),
        duplicate_heading_slugs=tuple(duplicate_headings),
        orphan_ids=tuple(orphans),
    )


def _is_denylisted_consumer(rel_path: str) -> bool:
    """True when fragment refs from this file are exempt from M1.

    Historical / append-only docs (CHANGELOG, BACKLOG-DONE, audits, research,
    traces) describe the repo as it was at write time; reanchoring them on
    every rename would distort history.
    """
    rel = rel_path.replace("\\", "/")
    return any(rel == p or rel.startswith(p) for p in _FRAGMENT_CONSUMER_DENYLIST)


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


def check_repo_link_fragments(repo_root: Path) -> list[BrokenLink]:
    """ID-180 fragment-resolution gate.

    For every ``[text](path.md#fragment)`` link in every git-tracked ``.md``
    file (excluding the historical denylist), verify the ``#fragment``
    resolves to either an ``<a id="fragment">`` tag or a heading whose
    GitHub slug equals ``fragment`` in the target file.

    Also reports anchor uniqueness violations (M2) and orphan ``<a id>``
    tags not adjacent to a heading (M3), once per target file.
    """
    from docs.scan import _git_repo_markdown  # type: ignore[import]

    broken: list[BrokenLink] = []
    anchor_cache: dict[Path, _AnchorIndex] = {}
    # Per-target set of fragments referenced from non-denylisted consumers.
    # Used to surface heading-slug collisions lazily — only when at least one
    # live consumer actually points at the colliding fragment.
    referenced_frags: dict[Path, set[str]] = {}

    def _anchors_for(path: Path) -> _AnchorIndex | None:
        cached = anchor_cache.get(path)
        if cached is not None:
            return cached
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        idx = _extract_anchors(text)
        anchor_cache[path] = idx
        return idx

    # Two-pass: first populate the anchor cache for every Markdown file the
    # gate will diagnose, then walk consumer links. Populating M2/M3 only
    # from link-target visits would silently exempt files no live consumer
    # references — the orphan or duplicate would sit unnoticed until the
    # next time someone added a link into them.
    for md in _git_repo_markdown(repo_root):
        _anchors_for(md)

    for md in _git_repo_markdown(repo_root):
        rel = str(md.relative_to(repo_root))
        if _is_denylisted_consumer(rel):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, raw in _iter_link_targets(text):
            # Fragment gate uses _iter_link_targets directly (not _extract_links)
            # because in-page `#frag` refs — which _extract_links drops as
            # uninteresting to the on-disk gate — are exactly the shape this
            # gate needs to see. External URLs and fragmentless paths get
            # filtered here.
            if any(raw.startswith(p) for p in _EXTERNAL_PREFIXES):
                continue
            if "#" not in raw:
                continue
            target, _, frag = raw.partition("#")
            if not frag:
                continue
            # mkdocstrings symbol IDs (e.g. ``remote_store.Store.read``) are
            # generated at docs-build time and never appear in source `.md` as
            # `<a id>` tags or heading slugs. Detect by the Python-attribute
            # dot which GitHub slug rules would have stripped.
            if "." in frag:
                continue
            if not target:
                # In-page reference (`[text](#frag)`). Resolve against the
                # current file's own anchor index. Closes the in-page leg of
                # ID-180; cross-file form handled below.
                idx = _anchors_for(md)
                if idx is None:
                    continue
                referenced_frags.setdefault(md, set()).add(frag)
                if frag not in idx.ids:
                    broken.append(
                        BrokenLink(
                            source=md,
                            line=lineno,
                            raw=raw,
                            resolved=f"no anchor #{frag} in {md.relative_to(repo_root)}",
                        )
                    )
                continue
            tgt_path = (md.parent / target).resolve()
            if not tgt_path.exists() or tgt_path.suffix != ".md":
                # On-disk gate (above) already flags missing files; non-md
                # targets (e.g. .svg) have no anchor index.
                continue
            referenced_frags.setdefault(tgt_path, set()).add(frag)
            idx = _anchors_for(tgt_path)
            if idx is None:
                continue
            if frag not in idx.ids:
                broken.append(
                    BrokenLink(
                        source=md,
                        line=lineno,
                        raw=raw,
                        resolved=f"no anchor #{frag} in {tgt_path.relative_to(repo_root)}",
                    )
                )

    # M2 / M3 diagnostics — symmetric with M1's denylist. Historical /
    # append-only docs (CHANGELOG with per-version `## Added`, audits with
    # templated `## Description` / `## Reproduction`, research / RFCs with
    # repeated section names) carry legitimate heading-slug repeats; they
    # are not consumer targets for fragment links, so any ambiguity there
    # is invisible to live readers.
    #
    # Heading-slug collisions are reported lazily — only when at least one
    # live consumer references the colliding fragment. Pages with intentional
    # structural duplication (sync + async API on one page, two-presentation
    # ripple tables) carry collisions that are harmless until someone tries
    # to link into them.
    for path, idx in anchor_cache.items():
        rel_target = path.relative_to(repo_root)
        if _is_denylisted_consumer(str(rel_target)):
            continue
        for dup in idx.duplicate_ids:
            broken.append(
                BrokenLink(
                    source=path,
                    line=0,
                    raw=f'<a id="{dup}">',
                    resolved=f"duplicate anchor in {rel_target}",
                )
            )
        live_refs = referenced_frags.get(path, set())
        for dup in idx.duplicate_heading_slugs:
            if dup not in live_refs:
                continue
            broken.append(
                BrokenLink(
                    source=path,
                    line=0,
                    raw=f"## ... (slug {dup!r})",
                    resolved=(
                        f"duplicate heading slug #{dup} in {rel_target} "
                        "(two or more headings produce the same slug; "
                        "a live consumer references it ambiguously)"
                    ),
                )
            )
        for line_no, orphan in idx.orphan_ids:
            broken.append(
                BrokenLink(
                    source=path,
                    line=line_no,
                    raw=f'<a id="{orphan}">',
                    resolved=f"orphan anchor (no adjacent heading) in {rel_target}",
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
    page = "/".join(segments[1:])
    if page in _DOCS_GENERATED_ROOT_FILES:
        return None  # generated discovery artifact (llms*.txt), not a built page
    return page


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


def check_docs_site_links(repo_root: Path, valid_pages: set[str] | None = None) -> list[BrokenLink]:
    """Docs-site check: every ``docs.remotestore.dev`` stable/latest link resolves.

    BK-236 (DOCFRAME-009): an absolute link into the published docs site
    is validated against the page set the site actually builds, so a
    mistyped or stale path segment fails the gate offline.

    *valid_pages* is computed from the live tree when omitted; ``main`` computes
    a single ``_docs_site_pages`` scan once and passes it in, so the
    (build_source_map + sdd/examples) walk runs once per invocation.
    """
    from docs.scan import _git_repo_markdown  # type: ignore[import]

    if valid_pages is None:
        valid_pages = _docs_site_pages(repo_root)
    broken: list[BrokenLink] = []
    for md in _git_repo_markdown(repo_root):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        broken.extend(_find_broken_docs_site_links(text, md, valid_pages))
    return broken


# ---------------------------------------------------------------------------
# BK-307: non-Markdown discovery files (context7.json)
# ---------------------------------------------------------------------------
# The former ``docs-src/llms.txt`` docs-site-link gate was retired in ID-220:
# ``llms.txt`` is now generated by the ``mkdocs-llmstxt`` plugin from real page
# URIs, and ``mkdocs build --strict`` aborts on any missing section page — a
# stronger, build-time check than this static link scan.

# Root context7 manifest whose path lists are validated on disk.
_CONTEXT7_MANIFEST = "context7.json"

# A context7 path-list entry containing a glob wildcard is a pattern, not a
# literal path, so it is left unchecked (context7 allows globs in the folder
# lists, and a literal on-disk check cannot vouch for them). Only the glob
# metacharacters (``* ? [ ]``) qualify — regex-only metachars like ``()|^$``
# can appear in legitimate literal filenames (``report (1).pdf``), so treating
# those as patterns would silently skip real drift. A literal directory
# rename — the drift this gate targets — carries no glob meta, so it is caught.
_CONTEXT7_PATTERN_META = re.compile(r"[*?\[\]]")


def _git_repo_files(repo_root: Path) -> list[Path]:
    """Return every git-visible file under *repo_root* (mirrors _git_repo_markdown).

    Used only for context7 ``excludeFiles`` basename matching. Delegates to
    ``git ls-files`` so gitignore is honoured; falls back to ``rglob`` skipping
    VCS internals when the tree is not a git repository (test fixtures).
    """
    import subprocess

    from docs.scan import _VCS_DIRS  # type: ignore[import]  # single source for the VCS-dir set

    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode == 0:
        return [(repo_root / p).resolve() for p in result.stdout.splitlines()]
    return [
        p.resolve()
        for p in repo_root.rglob("*")
        if p.is_file() and not any(part in _VCS_DIRS for part in p.relative_to(repo_root).parts)
    ]


def check_context7_paths(repo_root: Path) -> list[BrokenLink]:
    """BK-307: every path-list entry in root ``context7.json`` resolves on disk.

    A directory rename otherwise silently drops a folder from context7
    indexing with nothing to catch it. Field semantics follow the context7
    schema:

    * ``folders`` — repo-root-relative paths to include (directories, plus the
      root-level files the manifest names explicitly, e.g. ``README.md``).
    * ``excludeFolders`` — repo-root-relative directories to exclude.
    * ``excludeFiles`` — matched by *filename only* (basename), never a full
      path, so a bare ``graph_viz.html`` legitimately names
      ``docs-src/explanation/graph_viz.html``.

    Glob / regex pattern entries (``_CONTEXT7_PATTERN_META``) are left
    unchecked. The context7.com ``url`` is external and out of scope (this gate
    is offline).
    """
    manifest = (repo_root / _CONTEXT7_MANIFEST).resolve()
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    broken: list[BrokenLink] = []

    def _flag(field: str, entry: str, why: str) -> None:
        broken.append(BrokenLink(source=manifest, line=0, raw=f"{field}: {entry}", resolved=why))

    def _literal_entries(field: str) -> Iterator[str]:
        for entry in data.get(field, []):
            if isinstance(entry, str) and not _CONTEXT7_PATTERN_META.search(entry):
                yield entry

    # folders: an include path; may be a directory or a root-level file.
    for entry in _literal_entries("folders"):
        if not (repo_root / entry).exists():
            _flag("folders", entry, f"no such path: {entry}")

    # excludeFolders: an exclude path; must be an existing directory.
    for entry in _literal_entries("excludeFolders"):
        if not (repo_root / entry).is_dir():
            _flag("excludeFolders", entry, f"no such directory: {entry}")

    # excludeFiles: matched by basename anywhere in the tree.
    basenames = {p.name for p in _git_repo_files(repo_root)}
    for entry in _literal_entries("excludeFiles"):
        if entry not in basenames:
            _flag("excludeFiles", entry, f"no file named {entry!r} in repo")

    return broken


# Context7 project-settings field caps, observed in the context7.com dashboard.
# A manifest that exceeds one is silently rejected by Context7 on save /
# re-parse, so the indexed entry stops tracking its source — "Folders to Include"
# growing to 7 (> 5) is exactly what blocked a re-parse and stranded an outdated
# tagline (BK-317). Rules additionally cap at 255 chars each (BK-311 hit this).
_CONTEXT7_LIST_CAPS = {
    "folders": 5,
    "excludeFolders": 50,
    "excludeFiles": 100,
    "rules": 50,
}
_CONTEXT7_RULE_MAX_CHARS = 255

# Both manifests Context7 treats as authoritative sources are subject to the
# caps: the repo-root manifest (the GitHub-repo entry) and the docs-site
# manifest (the docs-root website entry, served via the RTD /context7.json
# redirect). The docs manifest carries only ``rules`` — no folders/exclude*
# lists — which the shared loop skips automatically.
_CONTEXT7_CAP_MANIFESTS = ("context7.json", "docs-src/context7.json")


def check_context7_limits(repo_root: Path) -> list[BrokenLink]:
    """BK-317: every ``context7.json`` stays within Context7's dashboard caps.

    Context7 enforces per-field maxima ("Folders to Include" <= 5, "Folders to
    Exclude" <= 50, "Files to Exclude" <= 100, "Custom Rules" <= 50 of <= 255
    chars each). Exceeding one makes Context7's save / re-parse fail silently, so
    the indexed entry stops tracking its source — the failure mode this gate
    turns into an offline lint error. Runs over both the repo-root manifest and
    the docs-site ``docs-src/context7.json`` (the docs-root website entry, whose
    ``rules`` list is equally subject to the caps). Complements
    ``check_context7_paths`` (which checks the root manifest's path-list entries
    resolve, not that the lists fit).
    """
    broken: list[BrokenLink] = []
    for rel in _CONTEXT7_CAP_MANIFESTS:
        manifest = (repo_root / rel).resolve()
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for field, cap in _CONTEXT7_LIST_CAPS.items():
            value = data.get(field)
            if isinstance(value, list) and len(value) > cap:
                broken.append(
                    BrokenLink(
                        source=manifest,
                        line=0,
                        raw=field,
                        resolved=f"{len(value)} entries exceeds Context7 max of {cap}",
                    )
                )

        rules = data.get("rules", [])
        if isinstance(rules, list):
            for i, rule in enumerate(rules):
                if isinstance(rule, str) and len(rule) > _CONTEXT7_RULE_MAX_CHARS:
                    broken.append(
                        BrokenLink(
                            source=manifest,
                            line=0,
                            raw=f"rules[{i}]",
                            resolved=f"{len(rule)} chars exceeds Context7 max of {_CONTEXT7_RULE_MAX_CHARS}",
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

    parser = argparse.ArgumentParser(description="Check markdown links.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    # Compute the docs-site page set once for check_docs_site_links;
    # _docs_site_pages runs build_source_map + the sdd/examples scan, so a
    # second call would double that walk on every docs-gate / all run.
    docs_site_pages = _docs_site_pages(repo_root)
    broken = (
        check_repo_links(repo_root)
        + check_docs_site_links(repo_root, valid_pages=docs_site_pages)
        + check_repo_link_fragments(repo_root)
        + check_context7_paths(repo_root)
        + check_context7_limits(repo_root)
    )

    if broken:
        print(_format_broken(broken, repo_root), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
