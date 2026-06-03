#!/usr/bin/env python3
"""Cross-source capability-parity check: Python ↔ Dafny (BK-245).

The ``Capability`` enum lives in two places that must agree name-for-name:

  P — ``Capability`` in ``src/remote_store/_capabilities.py`` (the runtime
      source of truth), keyed on each member's string ``.value``.
  D — the ``Capability`` datatype in ``sdd/formal/BackendContract.dfy``,
      surfaced through the ``CapabilityName(c)`` helper that maps every
      variant to the same string ``.value`` the Python enum uses.

``check_formal_trace.py`` (ID-206) makes the spec ↔ Dafny ↔ test wiring
mechanical, but it matches ``@spec`` tags, not capability-enum membership:
a future drift between ``Capability.<NAME>`` and the Dafny ``Capability`` /
``CapabilityName`` cases would slip through silently. PR #689 (ID-188)
added ``CapLazyRead`` for parity with ``Capability.LAZY_READ`` on the
strength of a comment alone. This gate turns that comment into an assertion:

    {c.value for c in Capability} == {CapabilityName(c) for c in Capability}

Scope. The parity is per *name* (the ``.value`` string). Ordering and
grouping of the Dafny datatype are deliberately out of scope — only the
set of capability names must match. The Dafny datatype ↔ ``CapabilityName``
internal agreement is already guaranteed by Dafny's exhaustive-match
verification, so this gate parses ``CapabilityName`` for the names and does
not re-derive them from the datatype.

Both sides are parsed from source (AST for Python, regex for the Dafny
``case`` arms) rather than imported — symmetric with ``check_formal_trace``
and free of any package-import or Dafny-toolchain dependency, so it runs in
``hatch run lint`` and CI like the other ``check_*.py`` gates.

CI enforcement. Exit code 0 = parity; 1 = mismatch (or a parse that found
no capabilities on either side — a sign the source shape moved).
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
