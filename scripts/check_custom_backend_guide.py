"""Drift gate for the Build Your Own Backend guide (BK-320).

The guide at ``docs-src/guides/custom-backend-guide.md`` mirrors four
authorities that evolve independently of it, and each has drifted before:

1. **Snippet regions** — every ``--8<--`` include must resolve to a real
   file (and, when a ``:region`` is named, a real ``[start:region]`` /
   ``[end:region]`` pair), or the docs build silently renders an empty
   code block. A floor assertion catches the catastrophic case where the
   guide lost its includes entirely.
2. **The driver protocols** — the guide's quick-reference tables must
   mirror ``remote_store.drivers``: "Required driver members" lists exactly
   the methods ``Driver`` declares, each row's parameters matching the
   protocol signature; "Declared attributes" lists exactly ``Driver``'s
   annotated attributes plus the optional ones its docstring names
   (``_OPTIONAL_ATTRIBUTES``); "Optional protocols" lists exactly the sync
   ``Supports*`` protocols, each row's member matching that protocol's
   method signature. This is the prose twin of the executable guard in
   ``tests/test_snippets.py``, which pins the tutorial driver itself to the
   same signatures. The tables drifted from the ``Backend`` ABC twice when
   that was the documented route, which is why they are gated at all. Step
   2's capability table lists exactly the capabilities the kernel's
   construction check refuses without a backer, each naming what backs it and
   the setting a backer needs (``rename_replaces = True``, ``put_is_atomic =
   True``), measured by asking that check (``_construction_terms``). A row repeated
   in any table fails, since a lookup would keep only one of the two.
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

Known scope limits, on purpose: only the sync protocols are gated (the
async twins are generated from the same source, and the guide names their
differences in prose); the attributes table is membership-checked only,
since an attribute has no parameters; the optional attributes are a
hand-kept set, checked only for still being named in ``Driver``'s
docstring; the protocols table does not gate an optional protocol's extra
attribute (``rename_replaces``), whose required value the capability table
gates; and parameter comparison is by NAME only (kinds and defaults
are covered by the executable guard).

Wired into ``hatch run lint`` and ``hatch run docs-gate``.

Usage:
    python scripts/check_custom_backend_guide.py [guide-path]
    Defaults to docs-src/guides/custom-backend-guide.md.

Drift-gate::

    kind:       pair
    compares: docs-src/guides/custom-backend-guide.md ↔ the remote_store.drivers protocols, the
        kernel's construction check (_check_construction's refusals), the conformance suite
        files and the fixture loader's closed vocabularies
    domain:     explanation ↔ realization
"""

from __future__ import annotations

import inspect
import re
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GUIDE = _ROOT / "docs-src" / "guides" / "custom-backend-guide.md"

SNIPPET_REF = re.compile(r'--8<--\s+"([^":]+?)(?::([A-Za-z0-9_-]+))?"')
CONFORMANCE_FILE = re.compile(r"tests/backends/conformance/([A-Za-z0-9_]+\.py)")
CELL_CODE = re.compile(r"^\s*\[?`([^`]+)`")
TABLE_CELL_SPLIT = re.compile(r"(?<!\\)\|")
TOML_FENCE = re.compile(r"```toml\n(.*?)```", re.DOTALL)

_REQUIRED_HEADING = "### Required driver members"
_ATTRIBUTES_HEADING = "### Declared attributes"
_PROTOCOLS_HEADING = "### Optional protocols"

# Attributes the kernel reads with a default, so they carry no annotation on
# ``Driver`` and cannot be derived from it. Each must still be named in the
# ``Driver`` docstring, which is where the protocol documents them.
_OPTIONAL_ATTRIBUTES = frozenset({"stream_catch", "size_probe"})


def check_snippet_regions(guide_text: str, root: Path) -> list[str]:
    """Every ``--8<--`` include must resolve to a real file and region."""
    violations: list[str] = []
    refs = SNIPPET_REF.findall(guide_text)
    if not refs:
        return ["guide contains no --8<-- snippet includes at all — includes lost or parser broken"]
    # Parity floor: every --8<-- occurrence must be a well-formed ref the
    # parser saw, or a malformed ref (bad region charset, missing quotes)
    # silently drops out of validation.
    raw_markers = len(re.findall(r"--8<--", guide_text))
    if raw_markers != len(refs):
        violations.append(
            f"{raw_markers} '--8<--' markers but only {len(refs)} parse as includes — malformed snippet ref?"
        )
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


def _table_rows(guide_text: str, heading: str) -> list[list[str]]:
    """The code spans opening each cell of the table rows under *heading*.

    A row whose first cell opens with no code span (the header, the
    separator) is skipped; a later cell with none yields ``""``. The scan
    ends at the next Markdown heading of ANY level (``#``, ``##``,
    ``####``, ...) so a future subheading inside the section cannot
    silently absorb an unrelated table into the member set. Cells split on
    unescaped pipes, so ``bytes \\| BinaryIO`` stays one cell.
    """
    rows: list[list[str]] = []
    in_section = False
    for line in guide_text.splitlines():
        if line.startswith(heading):
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = TABLE_CELL_SPLIT.split(line.strip().strip("|"))
        codes = [m.group(1) if (m := CELL_CODE.match(cell)) else "" for cell in cells]
        if codes and codes[0]:
            rows.append(codes)
    return rows


def _own_methods(protocol: type) -> dict[str, list[str]]:
    """``{method: parameter names without self}`` for the methods *protocol* itself declares."""
    return {
        name: [p for p in inspect.signature(member).parameters if p != "self"]
        for name, member in vars(protocol).items()
        if inspect.isfunction(member) and not name.startswith("_")
    }


def _membership(listed: set[str], expected: set[str], label: str, what: str) -> list[str]:
    violations = [f"{label}: missing row for '{missing}'" for missing in sorted(expected - listed)]
    violations += [f"{label}: row '{stale}' is not {what}" for stale in sorted(listed - expected)]
    return violations


def _param_drift(label: str, name: str, params: list[str] | None, signature: list[str]) -> list[str]:
    if params != signature:
        return [f"{label}: '{name}' params {params} != protocol signature {signature}"]
    return []


def check_required_table(guide_text: str) -> list[str]:
    """The table must list exactly the methods ``Driver`` declares, with their parameters."""
    from remote_store.drivers import Driver

    rows = _table_rows(guide_text, _REQUIRED_HEADING)
    if not rows:
        return [f"required-members table not found (heading '{_REQUIRED_HEADING}' missing?)"]

    label = "required-members table"
    parsed = [_parse_member_cell(row[0]) for row in rows]
    table = dict(parsed)
    duplicates = _duplicates(label, [name for name, _ in parsed])
    methods = _own_methods(Driver)
    violations = duplicates + _membership(set(table), set(methods), label, "a method Driver declares")
    for name in sorted(set(table) & set(methods)):
        violations += _param_drift(label, name, table[name], methods[name])
    return violations


def check_attributes_table(guide_text: str) -> list[str]:
    """The table must list ``Driver``'s annotated attributes and the optional ones its docstring names."""
    from remote_store.drivers import Driver

    rows = _table_rows(guide_text, _ATTRIBUTES_HEADING)
    if not rows:
        return [f"attributes table not found (heading '{_ATTRIBUTES_HEADING}' missing?)"]

    label = "attributes table"
    doc = Driver.__doc__ or ""
    violations = [
        f"{label}: optional attribute '{name}' is no longer named in the Driver docstring; "
        "drop it from _OPTIONAL_ATTRIBUTES"
        for name in sorted(_OPTIONAL_ATTRIBUTES)
        if f"``{name}``" not in doc
    ]
    expected = set(Driver.__annotations__) | _OPTIONAL_ATTRIBUTES
    violations += _duplicates(label, [row[0].strip() for row in rows])
    violations += _membership({row[0].strip() for row in rows}, expected, label, "a Driver attribute")
    return violations


def check_protocols_table(guide_text: str) -> list[str]:
    """The table must list exactly the sync ``Supports*`` protocols, each with its method's parameters."""
    from remote_store import drivers

    rows = _table_rows(guide_text, _PROTOCOLS_HEADING)
    if not rows:
        return [f"protocols table not found (heading '{_PROTOCOLS_HEADING}' missing?)"]

    label = "protocols table"
    protocols = {name: getattr(drivers, name) for name in drivers.__all__ if name.startswith("Supports")}
    listed = {row[0].strip(): (row[1] if len(row) > 1 else "") for row in rows}
    violations = _duplicates(label, [row[0].strip() for row in rows])
    violations += _membership(set(listed), set(protocols), label, "a Supports* protocol in remote_store.drivers")
    for name in sorted(set(listed) & set(protocols)):
        member, params = _parse_member_cell(listed[name])
        methods = _own_methods(protocols[name])
        if member not in methods:
            violations.append(f"{label}: '{name}' row names '{member}', not one of its methods {sorted(methods)}")
            continue
        violations += _param_drift(label, f"{name}.{member}", params, methods[member])
    return violations


_CAPABILITY_HEADER = "| Capability | Backed by |"
BACKER_NAME = re.compile(r"\b(Supports[A-Za-z]+|put_is_atomic)\b")


def _construction_terms() -> dict[str, dict[str, str | None]]:
    """``{capability: {backer: the qualifier construction needs, or None}}``, measured by asking construction.

    A bare driver declaring one capability and presenting nothing optional is
    built for every capability; each one construction refuses is gated, and is
    backed by every ``Supports*`` protocol (or ``put_is_atomic``) that, added
    alone, makes construction accept it. A backer's qualifier is the setting it
    backs the capability only with: ``put_is_atomic = True`` for the attribute,
    and ``rename_replaces = True`` for a rename that construction refuses when
    it does not replace (a rename is probed both ways).
    """
    from remote_store import drivers
    from remote_store._capabilities import Capability, CapabilitySet
    from remote_store._kernel._sync.kernel import _check_construction

    protocols = {name: getattr(drivers, name) for name in drivers.__all__ if name.startswith("Supports")}

    def accepted(capability: Capability, extra: dict[str, object]) -> bool:
        attrs: dict[str, object] = {
            "name": "probe",
            "namespace": "flat",
            "parents": "none",
            "put_is_atomic": False,
            "capabilities": CapabilitySet({capability}),
            **extra,
        }
        try:
            _check_construction(type("_Probe", (), attrs)())  # type: ignore[arg-type]
        except ValueError:
            return False
        return True

    terms: dict[str, dict[str, str | None]] = {}
    for capability in Capability:
        if accepted(capability, {}):
            continue
        found: dict[str, str | None] = {}
        if accepted(capability, {"put_is_atomic": True}):
            found["put_is_atomic"] = "put_is_atomic = True"
        for name, protocol in protocols.items():
            stubs: dict[str, object] = {member: lambda *_a, **_k: None for member in _own_methods(protocol)}
            if name != "SupportsRename":
                if accepted(capability, stubs):
                    found[name] = None
            elif accepted(capability, {**stubs, "rename_replaces": False}):
                found[name] = None
            elif accepted(capability, {**stubs, "rename_replaces": True}):
                found[name] = "rename_replaces = True"
        terms[capability.name] = found
    return terms


def check_capability_table(guide_text: str) -> list[str]:
    """Step 2's table must list exactly the capabilities construction gates, each with what backs it."""
    lines = guide_text.splitlines()
    try:
        start = lines.index(_CAPABILITY_HEADER)
    except ValueError:
        return [f"capability table not found (header '{_CAPABILITY_HEADER}' missing?)"]

    label = "capability table"
    rows: dict[str, set[str]] = {}
    texts: dict[str, str] = {}
    violations: list[str] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        first, _, rest = line.strip("|").partition("|")
        capability = first.strip().strip("`")
        if capability in rows:
            violations.append(f"{label}: duplicate row for '{capability}'")
        rows[capability] = set(BACKER_NAME.findall(rest))
        texts[capability] = rest
    terms = _construction_terms()
    violations += _membership(set(rows), set(terms), label, "a capability construction gates")
    for capability in sorted(set(rows) & set(terms)):
        expected = set(terms[capability])
        if rows[capability] != expected:
            violations.append(
                f"{label}: '{capability}' names {sorted(rows[capability])}, but construction accepts {sorted(expected)}"
            )
        # A backer that backs the capability only with a setting must say so.
        violations += [
            f"{label}: '{capability}' row omits '{qualifier}', which construction needs for {backer}"
            for backer, qualifier in sorted(terms[capability].items())
            if qualifier is not None and qualifier not in texts[capability]
        ]
    return violations


def _duplicates(label: str, names: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for name in names:
        if name in seen:
            out.append(f"{label}: duplicate row for '{name}'")
        seen.add(name)
    return out


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
    """The registration section's fenced TOML must satisfy the fixture loader.

    Parses every ```toml fence in the guide, merges the entries, and runs
    them through the loader's own ``_parse_backend`` / ``_parse_fixture``
    (not a re-implementation), so the inline examples stay in sync with
    every validation the loader enforces — enums, required keys, types,
    and family references — by construction.
    """
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tests.backends.fixtures._loader import _parse_backend, _parse_fixture

    violations: list[str] = []
    fences = TOML_FENCE.findall(guide_text)
    if not fences:
        return ["guide contains no ```toml fences — registration examples lost or parser broken"]

    backends_raw: dict = {}
    fixtures_raw: dict = {}
    for fence in fences:
        try:
            data = tomllib.loads(fence)
        except tomllib.TOMLDecodeError as exc:
            violations.append(f"registration TOML fence does not parse: {exc}")
            continue
        backends_raw.update(data.get("backend", {}))
        fixtures_raw.update(data.get("fixture", {}))

    backends = {}
    for family, entry in backends_raw.items():
        try:
            backends[family] = _parse_backend(family, entry)
        except ValueError as exc:
            violations.append(f"toml example: {exc}")
    for fixture, entry in fixtures_raw.items():
        try:
            _parse_fixture(fixture, entry, backends)
        except ValueError as exc:
            violations.append(f"toml example: {exc}")
    return violations


def main(argv: list[str] | None = None) -> int:
    """Run every check; return 0 if clean, 1 on violations."""
    guide = Path(argv[0]) if argv else _GUIDE
    if not guide.is_file():
        sys.stderr.write(f"error: guide not found: {guide}\n")
        return 1
    guide_text = guide.read_text(encoding="utf-8")

    violations = [
        *check_snippet_regions(guide_text, _ROOT),
        *check_required_table(guide_text),
        *check_attributes_table(guide_text),
        *check_protocols_table(guide_text),
        *check_capability_table(guide_text),
        *check_conformance_files(guide_text, _ROOT),
        *check_registration_toml(guide_text, _ROOT),
    ]
    if violations:
        for v in violations:
            sys.stderr.write(f"error: {guide.name}: {v}\n")
        sys.stderr.write(
            "\nThe Build Your Own Backend guide drifted from the code it documents.\n"
            "Update docs-src/guides/custom-backend-guide.md (and its snippet file\n"
            "examples/snippets/custom_backend_guide.py) to match the driver protocols\n"
            "in remote_store.drivers, the conformance suite, and the fixture loader.\n"
        )
        return 1
    print(f"check_custom_backend_guide: {guide.name} is in sync with the driver protocols and conformance suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
