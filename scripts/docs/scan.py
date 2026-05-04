"""Discovery helpers: turn on-disk sources into typed records.

Record types:

:class:`SddKind`
    One row in :data:`SDD_KINDS`. Declarative config for each sdd subdir
    (adrs, specs, rfcs, audits, research): where to look, how to title,
    whether entries are numbered, optional status column.

:class:`SddEntry`
    One spec/ADR/RFC/audit/research document discovered under
    ``sdd/<kind.source_dir>/``.

:class:`DualEntry`
    One dual file: absolute repo source path and its virtual docs dest.
    Produced by :func:`scan_dual_files`.

:class:`ExampleEntry`
    One example script discovered under ``examples/<category>/``. Title,
    description, and optional ``see_also`` come from the module docstring.

:class:`ExampleCategory`
    One row of ``examples/_categories.yml``.

"""

from __future__ import annotations

import ast
import fnmatch
import re
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator
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


def _load_sdd_kinds(rules_path: Path | None = None) -> tuple[SddKind, ...]:
    """Load SDD kind definitions from ``docs-src/_path_rules.yml``.

    Spec: DOCFRAME-008.

    Args:
        rules_path: Path to the YAML file. Defaults to the canonical repo
            location ``docs-src/_path_rules.yml`` relative to this module.
    """
    from pathlib import Path as _Path

    if rules_path is None:
        rules_path = _Path(__file__).resolve().parent.parent.parent / "docs-src" / "_path_rules.yml"
    try:
        text = rules_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Required config not found: {rules_path}\n"
            "docs-src/_path_rules.yml must be present in a full repo checkout."
        ) from None
    data = yaml.safe_load(text) or {}
    items = data.get("sdd_kinds")
    if items is None:
        raise KeyError(f"_path_rules.yml at {rules_path} is missing the required 'sdd_kinds' key")
    if not items:
        raise ValueError(
            f"_path_rules.yml at {rules_path} has an empty 'sdd_kinds' list; at least one SDD kind must be declared"
        )
    return tuple(
        SddKind(
            slug=item["slug"],
            source_dir=item["source_dir"],
            nav_label=item["nav_label"],
            glob=item.get("glob", "*.md"),
            skip_stems=frozenset(item.get("skip_stems", ())),
            title_prefixes=tuple(item.get("title_prefixes", ())),
            status=item.get("status"),
            numbered=item.get("numbered", True),
        )
        for item in items
    )


SDD_KINDS: tuple[SddKind, ...] = _load_sdd_kinds()


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
    if not directory.is_dir():
        return []
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
# DOCFRAME-002: Classification marker parser
# ---------------------------------------------------------------------------

# Permissive: captures any non-whitespace class token so unrecognised classes
# are detected and rejected below rather than silently falling through to the
# directory-default table.
_MARKER_RE = re.compile(r"<!--\s*doc:\s+(\S+)(?:\s+dest=(\S+))?\s*-->")
_VALID_CLASSES = frozenset({"dual", "repo-only", "docs-only"})


def _parse_marker(text: str) -> tuple[str, str | None] | None:
    """Parse the doc classification marker from the first 5 non-blank lines.

    Returns ``(class, dest)`` where *dest* is ``None`` for non-dual classes.
    Returns ``None`` when no marker is present.
    Raises ``ValueError`` on malformed markers (unrecognised class, missing/extra
    ``dest=``, multiple markers — including same-line duplicates).
    """
    non_blank = 0
    found: list[re.Match[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        non_blank += 1
        found.extend(_MARKER_RE.finditer(line))
        if non_blank >= 5:
            break

    if len(found) > 1:
        raise ValueError("Multiple doc markers found in file")
    if not found:
        return None

    m = found[0]
    klass = m.group(1)
    dest = m.group(2)

    if klass not in _VALID_CLASSES:
        raise ValueError(f"Unrecognised marker class {klass!r}")
    if klass == "dual" and dest is None:
        raise ValueError("dual marker requires dest=")
    if klass != "dual" and dest is not None:
        raise ValueError(f"{klass} marker must not have dest=")

    return klass, dest


def _classify_file(path: Path, repo_root: Path) -> tuple[str, str | None]:
    """Classify *path* via its inline marker or the directory-default table.

    Returns ``(class, dest)`` where *dest* is ``None`` for non-dual classes.
    Raises ``ValueError`` (G-01) when the file is unclassified.
    """
    path = path.resolve()
    repo_root = repo_root.resolve()

    result = _parse_marker(path.read_text(encoding="utf-8"))
    if result is not None:
        return result

    # Directory defaults (AUTHORING.md § Directory defaults)
    for kind in SDD_KINDS:
        kind_dir = (repo_root / kind.source_dir).resolve()
        if path.parent == kind_dir and fnmatch.fnmatch(path.name, kind.glob) and path.stem not in kind.skip_stems:
            return "dual", f"explanation/design/{kind.slug}/{path.stem}.md"

    templates_dir = (repo_root / "sdd/templates").resolve()
    if path.is_relative_to(templates_dir):
        return "repo-only", None

    docs_src = (repo_root / "docs-src").resolve()
    if path.is_relative_to(docs_src):
        return "docs-only", None

    rel = path.relative_to(repo_root)
    raise ValueError(f"{rel} carries no marker and matches no directory default (G-01)")


# ---------------------------------------------------------------------------
# DOCFRAME-001 + DOCFRAME-003: DualEntry and scan_dual_files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DualEntry:
    """One dual file: absolute source path and its virtual docs destination."""

    source: Path  # absolute repo path
    dest: str  # virtual dest, e.g. "explanation/design/authoring.md"


def _scan_kind_for_dual(kind: SddKind, kind_dir: Path) -> list[DualEntry]:
    """Return dual entries for one SDD subdir."""
    if not kind_dir.is_dir():
        return []
    entries: list[DualEntry] = []
    for p in sorted(kind_dir.glob(kind.glob)):
        if p.stem in kind.skip_stems:
            # skip_stems blocks directory-default dual classification only.
            # An explicit dual marker still yields an entry.
            try:
                result = _parse_marker(p.read_text(encoding="utf-8"))
            except ValueError as exc:
                warnings.warn(f"Malformed doc marker in {p.name}: {exc}; skipping", stacklevel=2)
                continue
            if result is not None and result[0] == "dual":
                entries.append(DualEntry(source=p.resolve(), dest=result[1]))
            continue
        try:
            result = _parse_marker(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            warnings.warn(f"Malformed doc marker in {p.name}: {exc}; skipping", stacklevel=2)
            continue
        if result is None:
            entries.append(DualEntry(source=p.resolve(), dest=f"explanation/design/{kind.slug}/{p.stem}.md"))
        elif result[0] == "dual":
            entries.append(DualEntry(source=p.resolve(), dest=result[1]))
        # repo-only or docs-only override: not a dual file
    return entries


# Used as fallback skip-list when git is unavailable (test fixtures, etc.).
_VCS_DIRS = frozenset({".git", ".hg", ".svn"})


def _git_repo_markdown(repo_root: Path) -> list[Path]:
    """Return sorted list of git-visible .md files under *repo_root*.

    Delegates to ``git ls-files`` so the full gitignore grammar — wildcards,
    negation patterns, nested ``.gitignore`` files — is handled by git itself.
    Falls back to ``rglob`` skipping only :data:`_VCS_DIRS` when the tree is
    not a git repository (test fixtures, CI sandboxes without git, etc.).
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode == 0:
        return sorted((repo_root / p).resolve() for p in result.stdout.splitlines())
    # Fallback: rglob, skipping VCS internals only.
    return sorted(
        md.resolve()
        for md in repo_root.rglob("*.md")
        if not any(part in _VCS_DIRS for part in md.relative_to(repo_root).parts)
    )


def scan_dual_files(repo_root: Path) -> Iterator[DualEntry]:
    """Discover all dual files in *repo_root*.

    Yields :class:`DualEntry` for every file whose effective classification is
    ``dual``: SDD-subdir files (directory-default dual per :data:`SDD_KINDS`)
    and files elsewhere that carry an explicit ``<!-- doc: dual dest=... -->``
    marker.

    **Caveat:** malformed markers (those that cause :func:`_parse_marker` to
    raise ``ValueError``) emit a :mod:`warnings` warning and are skipped.
    The gate (DOCFRAME-004) is the authority for detecting and reporting G-01
    violations; callers that need a complete and verified source→dest map must
    run the gate first.

    Spec: DOCFRAME-001, DOCFRAME-003.
    """
    repo_root = repo_root.resolve()
    sdd_dirs: set[Path] = {(repo_root / kind.source_dir).resolve() for kind in SDD_KINDS}

    # SDD subdirs: sequential scan (~5 dirs, tens of files each).
    for kind in SDD_KINDS:
        yield from _scan_kind_for_dual(kind, repo_root / kind.source_dir)

    # Files elsewhere: yield those with explicit dual markers.
    # git ls-files handles the full gitignore grammar; falls back to rglob in
    # non-git trees (see _git_repo_markdown).
    docs_src = (repo_root / "docs-src").resolve()
    for abs_md in _git_repo_markdown(repo_root):
        if any(abs_md.is_relative_to(d) for d in sdd_dirs):
            continue
        if abs_md.is_relative_to(docs_src):
            continue
        try:
            result = _parse_marker(abs_md.read_text(encoding="utf-8"))
        except ValueError as exc:
            warnings.warn(
                f"Malformed doc marker in {abs_md.relative_to(repo_root)}: {exc}; skipping",
                stacklevel=2,
            )
            continue
        if result is not None and result[0] == "dual":
            yield DualEntry(source=abs_md, dest=result[1])


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
