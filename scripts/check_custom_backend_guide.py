"""Drift gate for the Build Your Own Backend guide (BK-320).

The guide at ``docs-src/guides/custom-backend-guide.md`` mirrors three
authorities that evolve independently of it, and each has drifted before:

1. **Snippet regions** — every ``--8<-- "file:region"`` include must
   resolve to a real ``[start:region]`` / ``[end:region]`` pair, or the
   docs build silently renders an empty code block.
2. **The Backend ABC** — the guide's "Abstract methods (must implement)"
   table must list exactly ``Backend.__abstractmethods__`` (plus the
   ``CAPABILITIES`` class attribute), and the "Optional overrides" table
   must list exactly the public non-abstract ``Backend`` methods, with
   each row's parameter list matching the ABC signature. This is the
   prose twin of the executable guard in ``tests/test_snippets.py``
   (BUG-235: ``max_depth`` was added to ``list_files`` and the guide
   never followed; BK-320 found ``resolve()`` missing from the
   optional-overrides table the same way).
3. **The conformance suite** — every ``tests/backends/conformance/*.py``
   file the guide names must exist on disk.

Wired into ``hatch run lint`` and ``hatch run docs-gate``.

Usage:
    python scripts/check_custom_backend_guide.py [guide-path]
    Defaults to docs-src/guides/custom-backend-guide.md.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GUIDE = _ROOT / "docs-src" / "guides" / "custom-backend-guide.md"

SNIPPET_REF = re.compile(r'--8<--\s+"([^":]+):([A-Za-z0-9_-]+)"')
CONFORMANCE_FILE = re.compile(r"tests/backends/conformance/([A-Za-z0-9_]+\.py)")
TABLE_FIRST_CELL_CODE = re.compile(r"^\|\s*\[?`([^`]+)`")

# The one non-abstract member the table documents alongside the ABC surface:
# the class-level capability declaration (spec 003, BE-003).
_EXTRA_TABLE_MEMBERS = {"CAPABILITIES"}


def check_snippet_regions(guide_text: str, root: Path) -> list[str]:
    """Every ``--8<--`` include must resolve to a real file and region."""
    violations: list[str] = []
    for file_ref, region in SNIPPET_REF.findall(guide_text):
        snippet_path = root / file_ref
        if not snippet_path.is_file():
            violations.append(f"snippet file not found: {file_ref} (region {region})")
            continue
        snippet_text = snippet_path.read_text(encoding="utf-8")
        for marker in (f"[start:{region}]", f"[end:{region}]"):
            if marker not in snippet_text:
                violations.append(f"{file_ref}: missing marker {marker}")
    return violations


def _parse_member_cell(cell: str) -> tuple[str, list[str] | None]:
    """Split a table cell like ``write(path, content, overwrite)`` into name + params.

    Returns ``(name, None)`` for property/attribute rows without parentheses.
    Parameter defaults (``metadata=None``) are stripped to bare names.
    """
    if "(" not in cell:
        return cell.strip(), None
    name, _, params_part = cell.partition("(")
    params = [p.partition("=")[0].strip() for p in params_part.rstrip(")").split(",") if p.strip()]
    return name.strip(), params


def _table_members(guide_text: str, heading: str) -> dict[str, list[str] | None]:
    """Extract ``{member: params-or-None}`` from the table under *heading*.

    The scan ends at the next Markdown heading of ANY level (``#``,
    ``##``, ``####``, ...) so a future subheading inside the section
    cannot silently absorb an unrelated table into the member set.
    """
    members: dict[str, list[str] | None] = {}
    in_section = False
    for line in guide_text.splitlines():
        if line.startswith(heading):
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        if not in_section:
            continue
        match = TABLE_FIRST_CELL_CODE.match(line)
        if match is None:
            continue
        cell = match.group(1)
        if cell.strip() in {"Member", "---"}:
            continue
        name, params = _parse_member_cell(cell)
        members[name] = params
    return members


def _check_member_params(table: dict[str, list[str] | None], expected: set[str], label: str) -> list[str]:
    """Compare each expected table row's parameter list against the ABC signature.

    Rows outside *expected* are skipped here — they are already reported
    as stale by the membership check. Known limitation, accepted for a
    prose table: parameters are compared by NAME only — a kind change
    (positional to keyword-only) or a default change is invisible here.
    The executable guard in ``tests/test_snippets.py`` covers kinds and
    defaults for the tutorial class itself.
    """
    from remote_store import Backend

    violations: list[str] = []
    for name, params in sorted(table.items()):
        if params is None or name not in expected or not hasattr(Backend, name):
            continue
        attr = inspect.getattr_static(Backend, name)
        if isinstance(attr, property):
            continue
        abc_params = [p for p in inspect.signature(getattr(Backend, name)).parameters if p != "self"]
        if params != abc_params:
            violations.append(f"{label}: '{name}' params {params} != ABC signature {abc_params}")
    return violations


def check_abstract_table(guide_text: str) -> list[str]:
    """The table must mirror ``Backend.__abstractmethods__`` name-for-name."""
    from remote_store import Backend

    table = _table_members(guide_text, "### Abstract methods")
    if not table:
        return ["abstract-methods table not found (heading '### Abstract methods' missing?)"]

    violations: list[str] = []
    expected = set(Backend.__abstractmethods__) | _EXTRA_TABLE_MEMBERS
    listed = set(table)
    for missing in sorted(expected - listed):
        violations.append(f"abstract-methods table: missing row for '{missing}'")
    for stale in sorted(listed - expected):
        violations.append(f"abstract-methods table: row '{stale}' is not an abstract member of Backend")
    violations.extend(_check_member_params(table, expected, "abstract-methods table"))
    return violations


def check_optional_overrides_table(guide_text: str) -> list[str]:
    """The table must mirror the public non-abstract ``Backend`` methods.

    This is the table BK-320 had to hand-repair (``resolve()`` was
    missing), so it gets the same membership + parameter gating as the
    abstract table.
    """
    from remote_store import Backend

    table = _table_members(guide_text, "### Optional overrides")
    if not table:
        return ["optional-overrides table not found (heading '### Optional overrides' missing?)"]

    violations: list[str] = []
    abstract = set(Backend.__abstractmethods__)
    expected = {
        name
        for name, member in inspect.getmembers(Backend, predicate=inspect.isfunction)
        if not name.startswith("_") and name not in abstract
    }
    listed = set(table)
    for missing in sorted(expected - listed):
        violations.append(f"optional-overrides table: missing row for '{missing}'")
    for stale in sorted(listed - expected):
        violations.append(f"optional-overrides table: row '{stale}' is not a public non-abstract Backend method")
    violations.extend(_check_member_params(table, expected, "optional-overrides table"))
    return violations


def check_conformance_files(guide_text: str, root: Path) -> list[str]:
    """Every conformance test file the guide names must exist."""
    violations: list[str] = []
    for filename in sorted(set(CONFORMANCE_FILE.findall(guide_text))):
        if not (root / "tests" / "backends" / "conformance" / filename).is_file():
            violations.append(f"guide names nonexistent conformance file: {filename}")
    return violations


def main(argv: list[str] | None = None) -> int:
    """Run all four checks; return 0 if clean, 1 on violations."""
    guide = Path(argv[0]) if argv else _GUIDE
    if not guide.is_file():
        sys.stderr.write(f"error: guide not found: {guide}\n")
        return 1
    guide_text = guide.read_text(encoding="utf-8")

    violations = [
        *check_snippet_regions(guide_text, _ROOT),
        *check_abstract_table(guide_text),
        *check_optional_overrides_table(guide_text),
        *check_conformance_files(guide_text, _ROOT),
    ]
    if violations:
        for v in violations:
            sys.stderr.write(f"error: {guide.name}: {v}\n")
        sys.stderr.write(
            "\nThe Build Your Own Backend guide drifted from the code it documents.\n"
            "Update docs-src/guides/custom-backend-guide.md (and its snippet file\n"
            "examples/snippets/custom_backend_guide.py) to match the Backend ABC\n"
            "and the conformance suite.\n"
        )
        return 1
    print(f"check_custom_backend_guide: {guide.name} is in sync with the Backend ABC and conformance suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
