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


_Func = ast.FunctionDef | ast.AsyncFunctionDef
_Decorated = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _references_large_constant(func: _Func) -> bool:
    return any(isinstance(node, ast.Name) and node.id in _LARGE_PAYLOAD_CONSTANTS for node in ast.walk(func))


def _has_large_payload_mark(node: _Decorated) -> bool:
    return any("large_payload" in ast.unparse(dec) for dec in node.decorator_list)


def _find_unmarked(parent: ast.AST, marked_by_class: bool, unmarked: list[str], prefix: str) -> None:
    """Collect ``test_*`` functions that reference the size constants but are not
    marked — counting a ``large_payload`` mark on any enclosing class, mirroring
    how pytest propagates class-level marks to methods (which the runtime
    exclusion honours via ``item.get_closest_marker``). Without this, marking the
    class instead of the method would falsely fail the guard."""
    for child in ast.iter_child_nodes(parent):
        if isinstance(child, ast.ClassDef):
            _find_unmarked(child, marked_by_class or _has_large_payload_mark(child), unmarked, prefix)
        elif (
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name.startswith("test_")
            and _references_large_constant(child)
            and not (marked_by_class or _has_large_payload_mark(child))
        ):
            unmarked.append(f"{prefix}::{child.name}")


def test_large_payload_tests_are_marked() -> None:
    """Each conformance test that uploads a large payload must be marked.

    Walks ``conformance/`` (including ``aio/``); fails loudly listing any test
    function that references the size constants but lacks the mark (at method or
    enclosing-class level)."""
    conformance = Path(__file__).parent
    unmarked: list[str] = []
    for path in conformance.rglob("test_*.py"):
        if path == Path(__file__):
            continue
        tree = ast.parse(path.read_bytes())
        _find_unmarked(tree, marked_by_class=False, unmarked=unmarked, prefix=str(path.relative_to(conformance)))

    assert not unmarked, (
        f"{len(unmarked)} large-payload test(s) missing @pytest.mark.large_payload "
        "(BK-305 live-cloud exclusion will not fire):\n"
        + "\n".join(f"  {n}" for n in sorted(unmarked))
        + "\nAdd the mark, or stop referencing the large-payload size constants."
    )
