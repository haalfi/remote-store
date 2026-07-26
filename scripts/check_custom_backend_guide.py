"""Drift gate for the Build Your Own Backend guide (BK-320).

The guide at ``docs-src/guides/custom-backend-guide.md`` mirrors four
authorities that evolve independently of it, and each has drifted before:

1. **Snippet regions** — every ``--8<--`` include must resolve to a real
   file (and, when a ``:region`` is named, a real ``[start:region]`` /
   ``[end:region]`` pair), or the docs build silently renders an empty
   code block. A floor assertion catches the catastrophic case where the
   guide lost its includes entirely.
2. **The Backend ABC** — the guide's "Abstract methods (must implement)"
   table must list exactly ``Backend.__abstractmethods__`` (plus the
   ``CAPABILITIES`` class attribute), and the "Optional overrides" table
   must list the public non-abstract ``Backend`` methods, with each row's
   parameter list matching the ABC signature. This is the prose twin of
   the executable guard in ``tests/test_snippets.py`` (BUG-235:
   ``max_depth`` was added to ``list_files`` and the guide never
   followed; BK-320 found ``resolve()`` missing the same way).
3. **The conformance suite** — every ``tests/backends/conformance/*.py``
   file the guide names must exist on disk.
4. **The fixture registry** — the registration section's fenced TOML
   examples must parse and use only values the fixture loader accepts
   (``tests/backends/fixtures/_loader.py``'s ``VALID_*`` enums), so the
   inline examples cannot drift from the loader's closed vocabularies.

Division of labor: this gate proves *structural sync* — names, members,
files, enum values. It does not execute or import region bodies; runtime
truth (a region calling a nonexistent API) is covered by
``tests/test_snippets.py`` and ``hatch run examples``, which execute the
snippet regions.

Known scope limits, on purpose: the ABC tables cover plain methods only —
properties, classmethods, and class attributes (e.g. ``close_is_terminal``)
are invisible to ``inspect.isfunction`` and are not gated here; the
``CAPABILITIES`` row is membership-checked but has no parameters to
compare; and parameters are compared by NAME only (kinds and defaults are
covered by the executable guard).

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

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

_ROOT = Path(__file__).resolve().parent.parent
_GUIDE = _ROOT / "docs-src" / "guides" / "custom-backend-guide.md"

SNIPPET_REF = re.compile(r'--8<--\s+"([^":]+?)(?::([A-Za-z0-9_-]+))?"')
CONFORMANCE_FILE = re.compile(r"tests/backends/conformance/([A-Za-z0-9_]+\.py)")
TABLE_FIRST_CELL_CODE = re.compile(r"^\|\s*\[?`([^`]+)`")
TOML_FENCE = re.compile(r"```toml\n(.*?)```", re.DOTALL)

# The one non-abstract member the table documents alongside the ABC surface:
# the class-level capability declaration (spec 003, BE-003).
_EXTRA_TABLE_MEMBERS = {"CAPABILITIES"}

# Escape hatch for the optional-overrides membership check: whether the
# tutorial's table must name every public non-abstract method is a
# judgment call (CONTRIBUTING's backend-order gate deliberately proves
# order, not membership). Add a method here to exempt it from the
# missing-row check instead of routing around the gate.
_OPTIONAL_TABLE_EXEMPT: set[str] = set()


def check_snippet_regions(guide_text: str, root: Path) -> list[str]:
    """Every ``--8<--`` include must resolve to a real file and region."""
    violations: list[str] = []
    refs = SNIPPET_REF.findall(guide_text)
    if not refs:
        return ["guide contains no --8<-- snippet includes at all — includes lost or parser broken"]
    for file_ref, region in refs:
        snippet_path = root / file_ref
        if not snippet_path.is_file():
            violations.append(f"snippet file not found: {file_ref}" + (f" (region {region})" if region else ""))
            continue
        if not region:
            continue  # whole-file include: file existence is the whole contract
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
    as stale by the membership check. Parameters are compared by NAME
    only (see the module docstring's scope limits).
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
    abstract table, modulo the ``_OPTIONAL_TABLE_EXEMPT`` escape hatch.
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
    for missing in sorted(expected - listed - _OPTIONAL_TABLE_EXEMPT):
        violations.append(f"optional-overrides table: missing row for '{missing}'")
    for stale in sorted(listed - expected):
        violations.append(f"optional-overrides table: row '{stale}' is not a public non-abstract Backend method")
    violations.extend(_check_member_params(table, expected, "optional-overrides table"))
    return violations


def check_conformance_files(guide_text: str, root: Path) -> list[str]:
    """Every conformance test file the guide names must exist.

    Direction note: this checks named-files-exist, not files-are-named —
    whether the guide's topic table should enumerate every lane is a
    content judgment, not a sync fact.
    """
    filenames = sorted(set(CONFORMANCE_FILE.findall(guide_text)))
    if not filenames:
        return ["guide names no tests/backends/conformance/ files at all — references lost or parser broken"]
    return [
        f"guide names nonexistent conformance file: {filename}"
        for filename in filenames
        if not (root / "tests" / "backends" / "conformance" / filename).is_file()
    ]


def check_registration_toml(guide_text: str, root: Path) -> list[str]:
    """The registration section's fenced TOML must satisfy the fixture loader's enums.

    Parses every ```toml fence in the guide and validates the fields the
    loader treats as closed vocabularies, so the inline examples cannot
    drift from ``tests/backends/fixtures/_loader.py``.
    """
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tests.backends.fixtures._loader import (
        VALID_CONCURRENCY,
        VALID_CONTAINERS,
        VALID_KINDS,
        VALID_STAGES,
        VALID_TRANSPORTS,
    )

    violations: list[str] = []
    fences = TOML_FENCE.findall(guide_text)
    for fence in fences:
        # Strip the "# path/to/file" comment header before parsing.
        try:
            data = tomllib.loads(fence)
        except tomllib.TOMLDecodeError as exc:
            violations.append(f"registration TOML fence does not parse: {exc}")
            continue
        for family, entry in data.get("backend", {}).items():
            where = f"toml example [backend.{family}]"
            if entry.get("transport") not in VALID_TRANSPORTS:
                violations.append(f"{where}: transport {entry.get('transport')!r} not in {sorted(VALID_TRANSPORTS)}")
            if entry.get("concurrency") not in VALID_CONCURRENCY:
                violations.append(
                    f"{where}: concurrency {entry.get('concurrency')!r} not in {sorted(VALID_CONCURRENCY)}"
                )
        for fixture, entry in data.get("fixture", {}).items():
            where = f"toml example [fixture.{fixture}]"
            if entry.get("stage") not in VALID_STAGES:
                violations.append(f"{where}: stage {entry.get('stage')!r} not in {sorted(VALID_STAGES)}")
            if entry.get("kind") not in VALID_KINDS:
                violations.append(f"{where}: kind {entry.get('kind')!r} not in {sorted(VALID_KINDS)}")
            if entry.get("container") not in VALID_CONTAINERS:
                violations.append(f"{where}: container {entry.get('container')!r} not in {sorted(VALID_CONTAINERS)}")
    return violations


def main(argv: list[str] | None = None) -> int:
    """Run all five checks; return 0 if clean, 1 on violations."""
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
        *check_registration_toml(guide_text, _ROOT),
    ]
    if violations:
        for v in violations:
            sys.stderr.write(f"error: {guide.name}: {v}\n")
        sys.stderr.write(
            "\nThe Build Your Own Backend guide drifted from the code it documents.\n"
            "Update docs-src/guides/custom-backend-guide.md (and its snippet file\n"
            "examples/snippets/custom_backend_guide.py) to match the Backend ABC,\n"
            "the conformance suite, and the fixture loader.\n"
        )
        return 1
    print(f"check_custom_backend_guide: {guide.name} is in sync with the Backend ABC and conformance suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
