"""Discovery helpers: turn on-disk sources into typed records.

Record types:

:class:`SddKind`
    One row in :data:`SDD_KINDS`. Declarative config for each sdd subdir
    (adrs, specs, rfcs, audits, research): where to look, how to title,
    whether entries are numbered, optional status column.

:class:`SddEntry`
    One spec/ADR/RFC/audit/research document discovered under
    ``sdd/<kind.source_dir>/``.

:class:`ExampleEntry`
    One example script discovered under ``examples/<category>/``. Title,
    description, and optional ``see_also`` come from the module docstring.

:class:`ExampleCategory`
    One row of ``examples/_categories.yml``.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

_YAML_TAIL_RE = re.compile(r"\n---\n(see_also:.*?)\Z", re.DOTALL)
_ACRONYMS = {"Sftp": "SFTP", "Http": "HTTP", "S3": "S3", "Otel": "OTel", "Io": "IO"}


# ---------------------------------------------------------------------------
# sdd/ kinds and entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SddKind:
    """Declarative config for one sdd subdir."""

    slug: str  # "adrs" — docs path + nav key
    source_dir: str  # repo-relative, e.g. "sdd/adrs"
    nav_label: str  # "ADRs" — label in SUMMARY.md
    glob: str = "*.md"
    skip_stems: frozenset[str] = frozenset()
    title_prefixes: tuple[str, ...] = ()  # stripped when parsing first heading
    status: str | None = None  # adds a status column when set
    numbered: bool = True  # False → use title in place of number


SDD_KINDS: tuple[SddKind, ...] = (
    SddKind("adrs", "sdd/adrs", "ADRs", title_prefixes=("ADR-{num}: ",), status="Accepted"),
    SddKind("specs", "sdd/specs", "Specs", title_prefixes=("Spec {num}: ", "Spec-{num}: ", "{num}: ")),
    SddKind("rfcs", "sdd/rfcs", "RFCs", glob="rfc-*.md", skip_stems=frozenset({"rfc-template"}), status="Proposed"),
    SddKind("audits", "sdd/audits", "Audits", glob="audit-*.md", title_prefixes=("Audit {num} -- ", "Audit {num} — ")),
    SddKind(
        "research", "sdd/research", "Research", glob="research-*.md", title_prefixes=("Research: ",), numbered=False
    ),
)


@dataclass(frozen=True)
class SddEntry:
    """One spec/ADR/RFC/audit/research doc."""

    number: str
    slug: str
    title: str
    source: Path
    kind: SddKind


def _scan_kind(repo_root: Path, kind: SddKind) -> list[SddEntry]:
    directory = repo_root / kind.source_dir
    entries: list[SddEntry] = []
    for p in sorted(directory.glob(kind.glob)):
        if p.stem in kind.skip_stems:
            continue
        if p.stem.startswith(("rfc-", "audit-")):
            parts = p.stem.split("-", 2)
            num = parts[1] if len(parts) > 1 else p.stem
        else:
            num = p.stem.split("-", 1)[0]
        first_line = p.read_text(encoding="utf-8").split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
        for pattern in kind.title_prefixes:
            pfx = pattern.replace("{num}", num)
            if title.startswith(pfx):
                title = title[len(pfx) :].strip()
                break
        entries.append(SddEntry(number=num, slug=p.stem, title=title, source=p, kind=kind))
    return entries


def scan_all_sdd(repo_root: Path) -> dict[str, list[SddEntry]]:
    """Scan every :data:`SDD_KINDS` entry, keyed by ``kind.slug``."""
    return {kind.slug: _scan_kind(repo_root, kind) for kind in SDD_KINDS}


# ---------------------------------------------------------------------------
# examples/ entries and categories
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExampleSeeAlso:
    label: str
    url: str
    note: str


@dataclass(frozen=True)
class ExampleEntry:
    rel_key: str  # e.g. "getting_started/quickstart.py"
    subdir: str
    stem: str
    slug: str  # kebab-cased stem
    title: str
    description: str
    see_also: tuple[ExampleSeeAlso, ...] = ()
    source: Path | None = None


@dataclass(frozen=True)
class ExampleCategory:
    subdir: str
    label: str
    blurb: str
    order: int
    example_order: tuple[str, ...] = ()


def _stem_to_slug(stem: str) -> str:
    return stem.replace("_", "-")


def _title_case(stem: str) -> str:
    title = stem.replace("_", " ").title()
    for wrong, right in _ACRONYMS.items():
        title = title.replace(wrong, right)
    return title


def _parse_docstring(docstring: str, stem: str) -> tuple[str, str, tuple[ExampleSeeAlso, ...]]:
    """Extract ``(title, description, see_also)`` from a module docstring.

    Expected shape::

        Title -- Description sentence.

        Optional extra paragraphs.

        ---
        see_also:
          - label: ...
            url: ...
            note: ...

    The YAML tail is optional.
    """
    yaml_tail: list[ExampleSeeAlso] = []
    match = _YAML_TAIL_RE.search("\n" + docstring)
    body = docstring
    if match:
        body = docstring[: match.start()].rstrip()
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            warnings.warn(f"Invalid YAML in docstring for {stem}: {exc}", stacklevel=2)
            data = {}
        for item in data.get("see_also") or ():
            yaml_tail.append(
                ExampleSeeAlso(
                    label=str(item.get("label", "")),
                    url=str(item.get("url", "")),
                    note=str(item.get("note", "")),
                )
            )

    first_line = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
    title = _title_case(stem)
    description = first_line
    for sep in (" — ", " -- "):
        if sep in first_line:
            head, _, tail = first_line.partition(sep)
            title = head.strip()
            description = tail.strip()
            break
    if title == _title_case(stem) and first_line.lower().startswith("example:"):
        rest = first_line[len("example:") :].strip()
        for sep in (" — ", " -- "):
            if sep in rest:
                head, _, tail = rest.partition(sep)
                title = head.strip()
                description = tail.strip()
                break

    return title, description, tuple(yaml_tail)


def scan_examples(examples_root: Path, categories: list[ExampleCategory]) -> list[ExampleEntry]:
    """Scan each category's subdir for ``*.py`` scripts."""
    entries: list[ExampleEntry] = []
    for cat in categories:
        subdir_path = examples_root / cat.subdir
        discovered = {py.stem: py for py in subdir_path.glob("*.py") if py.stem != "__init__"}
        if cat.example_order:
            ordered: list[str] = []
            seen: set[str] = set()
            for stem in cat.example_order:
                if stem not in discovered:
                    warnings.warn(
                        f"{cat.subdir}: stem {stem!r} in _categories.yml is not on disk",
                        stacklevel=2,
                    )
                    continue
                ordered.append(stem)
                seen.add(stem)
            for stem in sorted(discovered):
                if stem not in seen:
                    warnings.warn(
                        f"{cat.subdir}: {stem!r} on disk but missing from _categories.yml",
                        stacklevel=2,
                    )
                    ordered.append(stem)
        else:
            ordered = sorted(discovered)

        for stem in ordered:
            py = discovered[stem]
            tree = ast.parse(py.read_text(encoding="utf-8"))
            docstring = ast.get_docstring(tree) or ""
            title, description, see_also = _parse_docstring(docstring, py.stem)
            entries.append(
                ExampleEntry(
                    rel_key=f"{cat.subdir}/{py.name}",
                    subdir=cat.subdir,
                    stem=py.stem,
                    slug=_stem_to_slug(py.stem),
                    title=title,
                    description=description,
                    see_also=see_also,
                    source=py,
                )
            )
    return entries


def load_categories(path: Path) -> list[ExampleCategory]:
    """Load ``examples/_categories.yml``, ordered by ``order`` field."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    cats = [
        ExampleCategory(
            subdir=item["subdir"],
            label=item["label"],
            blurb=str(item.get("blurb", "")).rstrip(),
            order=int(item.get("order", 0)),
            example_order=tuple(item.get("examples") or ()),
        )
        for item in raw
    ]
    cats.sort(key=lambda c: c.order)
    return cats


# ---------------------------------------------------------------------------
# Link map (docs-src/_link_map.yml) and include-wrapper auto-detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkMapEntry:
    """Emit *source* at virtual path *dest* with link-resolved content."""

    dest: str
    source: Path

    # Optional literal replacements applied AFTER link resolution. Rare — use
    # only for patterns the resolver can't express (e.g. section anchors that
    # changed on the other side).
    replacements: dict[str, str] = field(default_factory=dict)


def load_link_map(path: Path, repo_root: Path) -> list[LinkMapEntry]:
    """Load ``docs-src/_link_map.yml``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        LinkMapEntry(
            dest=dest,
            source=(repo_root / item["source"]).resolve(),
            replacements=dict(item.get("replacements") or {}),
        )
        for dest, item in raw.items()
    ]


_INCLUDE_RE = re.compile(r'\{%\s*include-markdown\s+"([^"]+)"\s*%\}', re.IGNORECASE)


def scan_include_wrappers(docs_src: Path) -> list[tuple[Path, str]]:
    """Find static ``docs-src/**/*.md`` wrappers that include-markdown an sdd file.

    Returns ``(absolute_source, virtual_dest)`` pairs so the source→dest map
    knows a repo file (e.g. ``sdd/TESTING.md``) is reachable at a docs path
    (e.g. ``design/testing.md``).
    """
    pairs: list[tuple[Path, str]] = []
    for md in docs_src.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        match = _INCLUDE_RE.search(text)
        if not match:
            continue
        include_rel = match.group(1)
        source = (md.parent / include_rel).resolve()
        dest = md.relative_to(docs_src).as_posix()
        pairs.append((source, dest))
    return pairs
