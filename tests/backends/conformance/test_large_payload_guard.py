"""Guard: every large-payload conformance test carries ``@pytest.mark.large_payload``.

The BK-305 live-cloud exclusion (see ``pytest_collection_modifyitems`` in
``conftest.py``) only fires on items that carry the ``large_payload`` mark. If a
new 8 MiB-per-call test is added without the mark, ``record-azure`` /
``record-graph`` silently records ~100x-norm cassettes against a pay-per-use
account again, and an ad-hoc ``--stage=3 -m live`` run hits the account with the
large payload. This guard ties the mark to the payload-size constants: any
conformance test whose body references ``_LARGE_WRITE_SIZE`` or ``_LARGE_SIZE``
must be marked, so the protection cannot silently rot when tests are added.
"""

from __future__ import annotations

import ast
from pathlib import Path

# The payload-size constants the live-cloud exclusion exists to keep off the wire.
_LARGE_PAYLOAD_CONSTANTS = frozenset({"_LARGE_WRITE_SIZE", "_LARGE_SIZE"})


def _references_large_constant(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(node, ast.Name) and node.id in _LARGE_PAYLOAD_CONSTANTS for node in ast.walk(func))


def _has_large_payload_mark(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any("large_payload" in ast.unparse(dec) for dec in func.decorator_list)


def test_large_payload_tests_are_marked() -> None:
    """Each conformance test that uploads a large payload must be marked.

    Walks ``conformance/`` (including ``aio/``); fails loudly listing any test
    function that references the size constants but lacks the mark."""
    conformance = Path(__file__).parent
    unmarked: list[str] = []
    for path in conformance.rglob("test_*.py"):
        if path == Path(__file__):
            continue
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if _references_large_constant(node) and not _has_large_payload_mark(node):
                unmarked.append(f"{path.relative_to(conformance)}::{node.name}")

    assert not unmarked, (
        f"{len(unmarked)} large-payload test(s) missing @pytest.mark.large_payload "
        "(BK-305 live-cloud exclusion will not fire):\n"
        + "\n".join(f"  {n}" for n in sorted(unmarked))
        + "\nAdd the mark, or stop referencing the large-payload size constants."
    )
