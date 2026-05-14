"""Guard: every name in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES is a live test.

Catches silent xfail drift: if a test in the frozenset is renamed or removed,
pytest_collection_modifyitems silently stops applying the mark, CI breaks on
the next replay run, and no one notices until then.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.backends.conformance.conftest import _AZURE_HNS_KNOWN_FAILURE_FN_NAMES


def test_hns_xfail_names_are_live() -> None:
    """Each name in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES must match a test function
    in the conformance directory.  Fails loudly on any stale entry."""
    conformance = Path(__file__).parent
    live: set[str] = set()
    for path in conformance.glob("test_*.py"):
        if path == Path(__file__):
            continue
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                live.add(node.name)

    stale = _AZURE_HNS_KNOWN_FAILURE_FN_NAMES - live
    assert not stale, (
        f"{len(stale)} name(s) in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES no longer exist"
        " as conformance test functions:\n"
        + "\n".join(f"  {n}" for n in sorted(stale))
        + "\nUpdate the frozenset in tests/backends/conformance/conftest.py."
    )
