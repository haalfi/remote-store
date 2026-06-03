#!/usr/bin/env python3
"""Cross-source capability-parity check: Python ↔ Dafny (BK-245).

A capability name lives in three places that must agree. This gate parses
all three from source and asserts they line up:

  P  — the ``Capability`` enum in ``src/remote_store/_capabilities.py``,
       keyed on each member's string ``.value``.
  Dv — the ``Capability`` datatype variants in ``sdd/formal/BackendContract.dfy``
       (``CapRead``, ``CapWrite``, …).
  Da — the ``CapabilityName`` helper in the same file, whose ``case`` arms map
       each variant to a string.

Two independent assertions:

  1. Dafny-internal: ``{datatype variants} == {CapabilityName arm variants}``.
     A variant with no arm (or an arm for a non-variant) fails here. Dafny's
     exhaustive-match verification also catches this, but that runs in a
     separate, path-gated CI job; checking it in the lint gate makes the
     parity self-contained rather than dependent on the Dafny job running.
  2. Cross-language: ``{c.value for c in Capability} == {CapabilityName arm
     strings}``. A capability added on one language's side but not the other
     fails here.

Parity is per name; the Dafny datatype's ordering and grouping are out of
scope. Both sides are parsed from source (AST for the Python enum, scoped
regex for the datatype and the ``CapabilityName`` arms), so the gate needs no
package import and no Dafny toolchain. It runs in the ``hatch run lint`` and
``verify-formal`` CI jobs so it fires whenever either source changes.

Exit code 0 = parity; 1 = a mismatch, or a parse that found no capabilities
in one of the three sources (a sign the source shape moved).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The ``Capability`` datatype header, used to slice its variant list out of the
# contract. The list runs until the next top-level declaration (``type
# CapabilitySet = …``); only ``| Cap…`` constructor lines contribute variants,
# which keeps the ``Error`` datatype's ``| CapabilityNotSupported`` and the
# ``type CapabilitySet`` alias from being mistaken for variants.
_CAPABILITY_DATATYPE_RE = re.compile(r"datatype\s+Capability\s*=")

# The ``CapabilityName`` function header, used to slice its ``{ … }`` body out
# of the contract before scanning for arms. Scoping to the body keeps a future
# second ``match c`` helper over ``Capability`` (e.g. a description function)
# from leaking its arms into the parsed set — over-collection the empty-parse
# guard would not catch.
_CAPABILITY_NAME_FN_RE = re.compile(r"function\s+CapabilityName\b")

# A Dafny ``Capability`` constructor token (``CapRead``, ``CapLazyRead``).
_CAP_VARIANT_RE = re.compile(r"\bCap\w+\b")

# A Dafny ``CapabilityName`` arm: ``case CapLazyRead => "lazy_read"``.
_DAFNY_CASE_RE = re.compile(r'case\s+(Cap\w+)\s*=>\s*"([^"]+)"')


# ---------------------------------------------------------------------------
# Source P — Python Capability enum
# ---------------------------------------------------------------------------


def extract_python_capabilities(capabilities_py: Path) -> set[str]:
    """Return the ``.value`` string of every member of the ``Capability`` enum.

    AST-parses the ``Capability`` class for ``NAME = "value"`` assignments;
    methods, the docstring, and any non-string member are ignored. Importing
    the module would work too, but parsing keeps the gate symmetric with the
    Dafny side and free of the package's import graph.
    """
    tree = ast.parse(capabilities_py.read_text(encoding="utf-8"), filename=str(capabilities_py))
    values: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "Capability"):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not (isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)):
                continue
            if any(isinstance(t, ast.Name) for t in stmt.targets):
                values.add(stmt.value.value)
    return values


# ---------------------------------------------------------------------------
# Source D — Dafny Capability datatype + CapabilityName arms
# ---------------------------------------------------------------------------


def _capability_datatype_variants(text: str) -> set[str]:
    """Return the constructor names of the ``Capability`` datatype.

    Reads ``| Cap…`` constructor lines following ``datatype Capability =``,
    stopping at the first content line that is neither a comment nor a
    constructor (the next top-level declaration). Empty set if the datatype is
    absent, which ``main`` rejects as an empty parse.
    """
    header = _CAPABILITY_DATATYPE_RE.search(text)
    if header is None:
        return set()
    variants: set[str] = set()
    for line in text[header.end() :].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("|"):
            variants.update(_CAP_VARIANT_RE.findall(line))
            continue
        # First non-comment, non-constructor line ends the datatype.
        break
    return variants


def _capability_name_body(text: str) -> str:
    """Return the brace-delimited body of the ``CapabilityName`` function.

    Empty string if the function is absent or its braces are unbalanced —
    either case surfaces as an empty parse, which ``main`` rejects.
    """
    header = _CAPABILITY_NAME_FN_RE.search(text)
    if header is None:
        return ""
    start = text.find("{", header.end())
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    return ""


def extract_dafny_capability_arms(contract_dfy: Path) -> dict[str, str]:
    """Map each ``CapabilityName`` arm's variant to its string.

    Only arms inside the ``CapabilityName`` function body count: a second
    ``match c`` helper over ``Capability`` elsewhere in the contract must not
    leak its ``case`` arms into the parsed set.
    """
    body = _capability_name_body(contract_dfy.read_text(encoding="utf-8"))
    return {variant: string for variant, string in _DAFNY_CASE_RE.findall(body)}


def extract_dafny_capabilities(contract_dfy: Path) -> set[str]:
    """Return the string of every ``CapabilityName`` arm in the Dafny contract."""
    return set(extract_dafny_capability_arms(contract_dfy).values())


def extract_dafny_capability_variants(contract_dfy: Path) -> set[str]:
    """Return the constructor names of the Dafny ``Capability`` datatype."""
    return _capability_datatype_variants(contract_dfy.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Comparison + reporting
# ---------------------------------------------------------------------------


def compute_mismatch(python: set[str], dafny: set[str]) -> tuple[set[str], set[str]]:
    """Return ``(python_only, dafny_only)`` capability names."""
    return python - dafny, dafny - python


def main(
    capabilities_py: Path | None = None,
    contract_dfy: Path | None = None,
) -> int:
    capabilities_py = capabilities_py or ROOT / "src" / "remote_store" / "_capabilities.py"
    contract_dfy = contract_dfy or ROOT / "sdd" / "formal" / "BackendContract.dfy"

    python = extract_python_capabilities(capabilities_py)
    arms = extract_dafny_capability_arms(contract_dfy)
    datatype_variants = extract_dafny_capability_variants(contract_dfy)
    arm_variants = set(arms)
    dafny_names = set(arms.values())

    # A zero-count parse means the source shape moved out from under the
    # regex/AST — fail loudly rather than report a vacuous "parity".
    if not python:
        print(f"FAIL: no Capability members parsed from {capabilities_py}")
        return 1
    if not arms:
        print(f"FAIL: no CapabilityName arms parsed from {contract_dfy}")
        return 1
    if not datatype_variants:
        print(f"FAIL: no Capability datatype variants parsed from {contract_dfy}")
        return 1

    print("capability parity: Python Capability.value <-> Dafny CapabilityName (BK-245)")
    print(f"  Python capabilities      : {len(python)}")
    print(f"  Dafny datatype variants  : {len(datatype_variants)}")
    print(f"  Dafny CapabilityName arms: {len(arms)}")
    print()

    failed = False

    # Check 1 — Dafny-internal: every datatype variant has a CapabilityName arm.
    variant_no_arm = datatype_variants - arm_variants
    arm_no_variant = arm_variants - datatype_variants
    if variant_no_arm or arm_no_variant:
        failed = True
        print("FAIL: Dafny Capability datatype and CapabilityName disagree:")
        if variant_no_arm:
            print(f"  datatype variant with no CapabilityName arm: {sorted(variant_no_arm)}")
        if arm_no_variant:
            print(f"  CapabilityName arm with no datatype variant: {sorted(arm_no_variant)}")
        print()

    # Check 2 — cross-language: Python .value set vs CapabilityName arm strings.
    python_only, dafny_only = compute_mismatch(python, dafny_names)
    if python_only or dafny_only:
        failed = True
        print("FAIL: capability names differ between Python and Dafny:")
        if python_only:
            print(f"  in Python only (add to BackendContract.dfy): {sorted(python_only)}")
        if dafny_only:
            print(f"  in Dafny only (add to _capabilities.py)   : {sorted(dafny_only)}")
        print()

    if failed:
        print("Keep Capability.<name>.value, the Dafny Capability datatype, and")
        print("the CapabilityName cases at per-name parity (BK-245).")
        return 1

    print(f"OK: {len(python)} capabilities match name-for-name across Python and Dafny.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
