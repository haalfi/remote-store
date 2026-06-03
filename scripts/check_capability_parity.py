#!/usr/bin/env python3
"""Cross-source capability-parity check: Python ↔ Dafny (BK-245).

The set of capability names must be identical on both sides of the model:

  P — the ``Capability`` enum in ``src/remote_store/_capabilities.py``,
      keyed on each member's string ``.value``.
  D — the ``CapabilityName`` helper in ``sdd/formal/BackendContract.dfy``,
      which maps every ``Capability`` datatype variant to that same string.

This gate asserts they match name-for-name::

    {c.value for c in Capability} == {CapabilityName(c) for c in Capability}

so a capability added on one side but not the other fails the lint gate
rather than drifting silently. Parity is per name only: the Dafny datatype's
ordering and grouping are out of scope, and its datatype ↔ ``CapabilityName``
agreement is enforced separately by Dafny's exhaustive-match verification.

Both sides are parsed from source — AST for the Python enum, a brace-scoped
regex for the ``CapabilityName`` arms — so the gate needs no package import
and no Dafny toolchain, and runs in ``hatch run lint`` like the other
``check_*.py`` gates. Exit code 0 = parity; 1 = a mismatch, or a parse that
found no capabilities on either side (a sign the source shape moved).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The ``CapabilityName`` function header, used to slice its ``{ … }`` body out
# of the contract before scanning for arms. Scoping to the body keeps a future
# second ``match c`` helper over ``Capability`` (e.g. a description function)
# from leaking its arms into the parsed set — over-collection the empty-parse
# guard would not catch.
_CAPABILITY_NAME_FN_RE = re.compile(r"function\s+CapabilityName\b")

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
# Source D — Dafny CapabilityName arms
# ---------------------------------------------------------------------------


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


def extract_dafny_capabilities(contract_dfy: Path) -> set[str]:
    """Return the string of every ``CapabilityName`` arm in the Dafny contract.

    Only arms inside the ``CapabilityName`` function body count: a second
    ``match c`` helper over ``Capability`` elsewhere in the contract must not
    leak its ``case`` arms into the parsed capability set.
    """
    body = _capability_name_body(contract_dfy.read_text(encoding="utf-8"))
    return {string for _variant, string in _DAFNY_CASE_RE.findall(body)}


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
    dafny = extract_dafny_capabilities(contract_dfy)

    # A zero-count parse means the source shape moved out from under the
    # regex/AST — fail loudly rather than report a vacuous "parity".
    if not python:
        print(f"FAIL: no Capability members parsed from {capabilities_py}")
        return 1
    if not dafny:
        print(f"FAIL: no CapabilityName arms parsed from {contract_dfy}")
        return 1

    python_only, dafny_only = compute_mismatch(python, dafny)

    print("capability parity: Python Capability.value <-> Dafny CapabilityName (BK-245)")
    print(f"  Python capabilities : {len(python)}")
    print(f"  Dafny  capabilities : {len(dafny)}")
    print()

    if python_only or dafny_only:
        print("FAIL: capability sets differ between Python and Dafny:")
        if python_only:
            print(f"  in Python only (add to BackendContract.dfy): {sorted(python_only)}")
        if dafny_only:
            print(f"  in Dafny only (add to _capabilities.py)   : {sorted(dafny_only)}")
        print("\nKeep Capability.<name>.value and the Dafny Capability /")
        print("CapabilityName cases at per-name parity (BK-245).")
        return 1

    print(f"OK: {len(python)} capabilities match name-for-name across Python and Dafny.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
