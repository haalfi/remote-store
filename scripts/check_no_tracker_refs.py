"""Check that internal tracker IDs do not leak into surfaces that reach users.

Two rules from ``sdd/CONTENT-RULES.md`` drive this check:

* **Rule 1 (6-month test).** Every sentence in a published surface must
  still read correctly when the cited tracker has been closed and the
  audience has forgotten what the number meant. Tracker IDs (backlog and
  spec coordinates) fail the test.
* **Rule 5 (source-code facts stay in source).** The mapping from a
  behavioural rule to its spec/backlog coordinates lives inside
  ``sdd/``, not in the docstrings or guides the same rule reaches users
  through.

Scope
=====

In scope (every match is a violation):

* every docstring in ``src/remote_store/**/*.py`` -- mkdocstrings
  renders docstrings of public symbols (those in ``__all__``) onto the
  docs site, and private helpers stay reachable via ``help()`` and
  source browse;
* every ``.md`` under ``docs-src/`` -- the docs-site source tree;
* ``README.md``, ``FEATURES.md``, ``CONTRIBUTING.md`` -- repo-root
  dual-classified pages that ship to both PyPI/GitHub and the docs
  site.

Out of scope (the trackers are how those documents are addressed):

* ``sdd/**`` -- internal SDD artefacts (specs, ADRs, RFCs, BACKLOG,
  traces, research, audits).
* ``CHANGELOG.md`` -- the tracker ID IS the index entry.
* ``DEVELOPMENT_STORY.md`` -- release-history narrative whose purpose
  is to retell work by ID.
* ``CLAUDE.md``, ``AGENTS.md`` -- agent-harness files, not user-facing.
* ``tests/``, ``.claude/``, ``infra/``, ``packaging/`` -- internal.
* ``docs-src/_data/`` -- generated graph artefacts.
* ``#`` comments inside ``.py`` files -- readers of the source are
  contributors, not users.

Generated Markdown
------------------

A handful of generators emit ``.md`` outside ``_data/`` (today:
``scripts/drift_check.py`` --> ``docs-src/reference/tested-versions.md``).
Those files ARE scanned by this gate; the contract is enforced at the
generator template, not by widening the exclusion. Any generator that
emits to ``docs-src/`` outside ``_data/`` MUST keep its template free of
tracker IDs.

Patterns flagged
================

The gate matches a *structural* tracker shape, not an enumerated prefix
list:

* ``PREFIX-NNN`` -- any uppercase prefix joined to digits by a hyphen,
  including compound prefixes like ``SQL-BLOB-020``. Catches every
  current and future backlog tracker (``ID-``, ``BK-``, ``BUG-``,
  ``BL-``, ``AF-``) and every spec section ID under ``sdd/specs/``
  (``BE-``, ``ASYNC-``, ``WR-``, ``S3-``, ``AZ-``, ``MEM-``, ``HTTP-``-
  prefixed spec sections, etc.) without an enumeration that would rot.
* ``RFC-NNN`` / ``ADR-NNN`` -- the leading-zero, zero-padded form is
  treated as internal (e.g. ``RFC-0014``, ``ADR-0025``); IETF-style
  ``RFC-3986`` and external ADR references are exempt.
* ``spec NNN`` -- numeric spec ordinals like ``spec 003``, ``spec 029``.
* ``PR #NNN`` -- bare PR cross-references; lines containing
  ``conda-forge/staged-recipes`` are allowlisted as external GitHub
  links.

External standards and codes are exempt via ``_EXTERNAL_PREFIXES``
(HTTP status codes, CVE advisories, ISO/IEEE/PEP standards, UTF-N
encodings). Add a new prefix there when a legitimate external code
matches the structural shape; ``test_external_prefixes_are_allowed``
locks the contract.

Exit codes
==========

* ``0`` -- clean.
* ``1`` -- one or more violations found (printed to stderr with
  ``file:line``).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #

# Structural tracker pattern: any uppercase prefix joined to a number
# by a hyphen. Matches ``ID-211``, ``BK-243``, ``BE-008``, ``ASYNC-080``,
# ``S3-010``, ``SQL-BLOB-020`` (compound prefix), ``RFC-3986``, etc.
# The ``[A-Z][A-Z0-9-]*`` shape allows letters, digits, and embedded
# hyphens in the prefix; the trailing ``-\d+`` is the numeric suffix.
# We then filter matches through ``_is_internal_tracker`` to drop
# external codes (HTTP-NNN, CVE-NNNN-NNNNN, RFC-NNNN without
# leading-zero pad, etc.).
_TRACKER_RE = re.compile(r"\b([A-Z][A-Z0-9-]*)-(\d+)\b")

# ``spec NNN`` numeric ordinals. ``\d{3,}`` accepts any 3+ digit form so
# this stays correct once the spec collection crosses 100.
_NUMERIC_SPEC_RE = re.compile(r"\bspec \d{3,}\b")

# Bare PR cross-references.
_PR_RE = re.compile(r"\bPR #\d+\b")

# Prefixes that match ``_TRACKER_RE`` but refer to external standards
# or codes, not internal trackers. Keep narrow; extend only when a
# real-world false positive appears in published prose.
_EXTERNAL_PREFIXES: frozenset[str] = frozenset(
    {
        "HTTP",  # HTTP status codes (HTTP-404)
        "CVE",  # security advisories (CVE-YYYY-NNNN, matches the YYYY half)
        "UTF",  # text encodings (UTF-8, UTF-16, UTF-32)
        "ISO",  # ISO standards (ISO-8601, ISO-639)
        "IEEE",  # IEEE standards (IEEE-754, IEEE-802)
        "PEP",  # Python Enhancement Proposals (PEP-484, PEP-585)
        "SHA",  # hash families when written with a dash (SHA-256, SHA-512)
        "MD5",  # ditto, defensive
        "SSH",  # SSH protocol versions (SSH-2.0-OpenSSH_…)
    }
)


def _is_internal_tracker(prefix: str, digits: str) -> bool:
    """Decide whether a ``PREFIX-NNN`` token refers to an internal coordinate.

    External standards and codes (``HTTP-404``, ``CVE-2024-1234``,
    ``UTF-8``, etc.) and IETF-style RFCs are exempt; everything else is
    treated as a backlog or spec coordinate.

    Compound-aware: the structural regex captures the longest valid
    ``[A-Z][A-Z0-9-]*`` prefix, so a compound token like
    ``CVE-2024-12345`` arrives with ``prefix='CVE-2024'``, and a
    compound spec like ``HTTP-CON-001`` arrives with
    ``prefix='HTTP-CON'``. The carve-out rules distinguish:

    * Most external prefixes (``HTTP``, ``UTF``, ``ISO``, ``IEEE``,
      ``PEP``, ``SHA``, ``MD5``, ``SSH``) are external only in their
      bare form (``HTTP-404``); a compound shape (``HTTP-CON-001``) is
      an internal spec section.
    * ``CVE`` is always compound (``CVE-YYYY-NNNN``); the leading-alpha
      check applies.
    * ``RFC`` / ``ADR`` use the leading-zero pad to disambiguate
      internal SDD docs (``RFC-0014``) from external IETF references
      (``RFC-3986``).
    """
    if prefix in _EXTERNAL_PREFIXES:
        return False
    leading = prefix.split("-", 1)[0]
    if leading == "CVE":
        return False
    if leading in {"RFC", "ADR"}:
        return digits.startswith("0")
    return True


# Substring allowlist applied to each line BEFORE patterns run. Any
# match of the substring is masked with whitespace so the regexes
# cannot match against it; line/column positions are preserved.
_LINE_ALLOWLIST: tuple[str, ...] = (
    # External GitHub repo reference (conda-forge submission tracking
    # in the release checklist).
    "conda-forge/staged-recipes PR #",
)

# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parent.parent

_SRC_ROOT = _REPO_ROOT / "src" / "remote_store"
_DOCS_ROOT = _REPO_ROOT / "docs-src"
_ROOT_MD_FILES: tuple[Path, ...] = (
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "FEATURES.md",
    _REPO_ROOT / "CONTRIBUTING.md",
)

# Top-level directories inside docs-src/ to skip (generated artefacts).
# Other generators emit into docs-src/ outside this set (notably
# ``scripts/drift_check.py`` --> ``reference/tested-versions.md``); the
# gate scans their output too, so any tracker IDs leaking through a
# generator template are caught here even though the fix lives in the
# generator. See the module docstring "Generated Markdown" section.
_DOCS_EXCLUDED_TOP_DIRS: frozenset[str] = frozenset({"_data"})

# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    match: str
    snippet: str


# --------------------------------------------------------------------------- #
# Line scanner
# --------------------------------------------------------------------------- #


def _mask_allowlisted(line: str) -> str:
    """Replace each allowlisted substring with whitespace of equal length.

    Whitespace preserves column positions so regex matches still report
    the correct location, but the masked span itself cannot match.
    """
    out = line
    for allow in _LINE_ALLOWLIST:
        if allow in out:
            out = out.replace(allow, " " * len(allow))
    return out


def _scan_lines(lines: Iterable[str], *, path: Path, line_offset: int = 0) -> list[Violation]:
    out: list[Violation] = []
    for idx, line in enumerate(lines):
        masked = _mask_allowlisted(line)
        lineno = line_offset + idx + 1
        # Structural PREFIX-NNN matcher, filtered against external codes.
        for m in _TRACKER_RE.finditer(masked):
            prefix, digits = m.group(1), m.group(2)
            if not _is_internal_tracker(prefix, digits):
                continue
            out.append(Violation(path=path, line=lineno, match=m.group(0), snippet=line.strip()))
        # Numeric spec ordinals.
        for m in _NUMERIC_SPEC_RE.finditer(masked):
            out.append(Violation(path=path, line=lineno, match=m.group(0), snippet=line.strip()))
        # Bare PR references.
        for m in _PR_RE.finditer(masked):
            out.append(Violation(path=path, line=lineno, match=m.group(0), snippet=line.strip()))
    return out


# --------------------------------------------------------------------------- #
# Python scanner
# --------------------------------------------------------------------------- #


def _docstring_anchor(node: ast.AST) -> int:
    """Return the 1-based source line of the docstring's first line.

    AST gives us the line of the string-literal expression; that line
    holds the opening quotes, and the first content line of a
    triple-quoted docstring starts there too (or on the next line for
    the common ``\"\"\"\\n<body>`` shape -- callers must account for the
    one-line offset themselves by using the literal source range, which
    is rarely worth the extra complexity here).
    """
    body = getattr(node, "body", None)
    if not body:
        return int(getattr(node, "lineno", 1))
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return int(first.value.lineno)
    return int(getattr(node, "lineno", 1))


def _scan_python_file(path: Path) -> list[Violation]:
    """Scan every docstring (module, class, function, method) in *path*."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            continue
        # ``_docstring_anchor`` returns the source line of the opening
        # triple-quote. For a docstring shaped ``"""\\n<body>"""`` the
        # first content line is anchor+1; for ``"""<body>"""`` it is
        # anchor itself. Scanning relative to anchor preserves enough
        # precision to point a reader at the right paragraph; the
        # exact column-offset is not worth the complexity.
        anchor = _docstring_anchor(node)
        out.extend(_scan_lines(doc.splitlines(), path=path, line_offset=anchor - 1))
    return out


# --------------------------------------------------------------------------- #
# Markdown scanner
# --------------------------------------------------------------------------- #


def _scan_markdown_file(path: Path) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return _scan_lines(text.splitlines(), path=path)


# --------------------------------------------------------------------------- #
# File enumeration
# --------------------------------------------------------------------------- #


def _iter_python_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return iter(())
    return iter(sorted(root.rglob("*.py")))


def _iter_markdown_files(root_files: Iterable[Path], docs_root: Path) -> Iterator[Path]:
    out: list[Path] = [p for p in root_files if p.is_file()]
    if docs_root.is_dir():
        for md in sorted(docs_root.rglob("*.md")):
            rel = md.relative_to(docs_root)
            if rel.parts and rel.parts[0] in _DOCS_EXCLUDED_TOP_DIRS:
                continue
            out.append(md)
    return iter(sorted(out))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def _format_violation(v: Violation, *, repo_root: Path) -> str:
    try:
        rel = v.path.relative_to(repo_root)
    except ValueError:
        rel = v.path
    return f"{rel}:{v.line}: {v.match}  --  {v.snippet}"


_REMEDIATION = (
    "See sdd/CONTENT-RULES.md Rules 1 and 5. Move the coordinate into the "
    "corresponding sdd/specs/ or sdd/BACKLOG-DONE.md entry, and describe "
    "the behaviour in prose at the published surface."
)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def collect_violations(
    *,
    src_root: Path = _SRC_ROOT,
    docs_root: Path = _DOCS_ROOT,
    root_md_files: Iterable[Path] = _ROOT_MD_FILES,
) -> list[Violation]:
    """Run all scanners; return a sorted list of violations."""
    out: list[Violation] = []
    for py in _iter_python_files(src_root):
        out.extend(_scan_python_file(py))
    for md in _iter_markdown_files(root_md_files, docs_root):
        out.extend(_scan_markdown_file(md))
    out.sort(key=lambda v: (str(v.path), v.line, v.match))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--src-root",
        type=Path,
        default=_SRC_ROOT,
        help="Python source root (default: src/remote_store).",
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        default=_DOCS_ROOT,
        help="Markdown docs root (default: docs-src).",
    )
    args = parser.parse_args(argv)

    violations = collect_violations(
        src_root=args.src_root,
        docs_root=args.docs_root,
    )
    if not violations:
        print("check_no_tracker_refs: no tracker IDs found in published surfaces.")
        return 0

    for v in violations:
        print(_format_violation(v, repo_root=_REPO_ROOT), file=sys.stderr)
    print(
        f"\ncheck_no_tracker_refs: {len(violations)} tracker reference(s) in published surfaces.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
