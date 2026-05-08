"""Mutation-scope manifest invariants.

Pin the contract that ``scripts/mutate_scopes.py`` and the fixture
registry stay in sync: every async fixture in the registry must be
matched by at least one ``conformance-async-extended-*`` scope's ``-k``
filter. Without this guard, adding a new async fixture (e.g. async S3,
async Azure) would silently get zero coverage from the per-topic
mutation scopes.

The manifest is loaded via ``importlib.util.spec_from_file_location``
rather than ``sys.path`` manipulation; ``check_test_placement.py``
flags the latter pattern outside ``tests/scripts/``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.backends.fixtures import _load_all, all_fixtures

_load_all()

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutate_scopes.py"


def _load_manifest():
    spec = importlib.util.spec_from_file_location("mutate_scopes", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass forward-reference resolution works.
    sys.modules.setdefault("mutate_scopes", module)
    spec.loader.exec_module(module)
    return module


def _kfilter_matches(name: str, kfilter: str) -> bool:
    """Cheap pytest ``-k`` substring check for the syntax mutate scopes use.

    Splits on the boolean ``or`` keyword (the only operator currently used
    in ``scripts/mutate_scopes.py``) and substring-matches each term. The
    assertion below will fail loudly the moment a scope adopts unsupported
    syntax, which is the right tripwire.
    """
    return any(term.strip() and term.strip() in name for term in kfilter.split(" or "))


@pytest.mark.spec("TEST-004")
def test_every_async_fixture_matches_an_async_extended_scope() -> None:
    scopes = _load_manifest().SCOPES

    async_extended_scopes = [
        (name, scope) for name, scope in scopes.items() if any("test_async_extended.py" in t for t in scope.tests)
    ]
    assert async_extended_scopes, (
        "no scope in scripts/mutate_scopes.py runs test_async_extended.py; async fixtures cannot be mutation-tested"
    )

    uncovered: list[str] = []
    for f in all_fixtures():
        if not f.is_async:
            continue
        if not any(
            scope.filter is None or _kfilter_matches(f.name, scope.filter) for _, scope in async_extended_scopes
        ):
            uncovered.append(f.name)

    assert not uncovered, (
        "async fixtures missing from any conformance-async-extended-* scope: "
        f"{uncovered}. Add a scope in scripts/mutate_scopes.py whose `-k` "
        "filter substring-matches the fixture name."
    )
