"""Fixture registry per spec 048 / TEST-004.

The registry is a flat list of ``BackendFixture`` records. Each record
names a fixture, ties it to a backend family, and declares the stage
tier, kind, capabilities, and async/sync mode the fixture operates in.

Conformance tests parametrise via ``fixtures``, which filters the
registry by stage (TEST-006), async mode, and capability set
(TEST-005). Backend-specific tests typically filter by a single
``backend == "<x>"`` predicate; do that with a list comprehension
over ``all_fixtures``. There is no per-backend helper because that
would invite re-implementing the filter in every site.

Per-backend factory modules append ``BackendFixture`` entries to
``_FIXTURES`` at import time. The conftest at ``tests.backends``
imports each module so that import-side effects run before any test
collection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import pytest

from remote_store._backend import Backend
from remote_store.aio import AsyncBackend
from tests.backends.fixtures._state import current_stage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from remote_store._capabilities import Capability


AnyBackend = Backend | AsyncBackend
"""Type alias spanning sync ``Backend`` and ``AsyncBackend``.

The ``is_async`` flag on ``BackendFixture`` disambiguates the union
for parametrize callers; per-test indirect fixtures cast to the
concrete type they need.
"""


@dataclass(frozen=True)
class BackendFixture:
    """Single entry in the fixture registry.

    Per TEST-004 the shape is fixed: name, backend family, no-arg
    factory, stage, kind, capability set, async flag, optional
    cleanup. Records are frozen so a misbehaving test cannot mutate
    a registry entry shared across the session.
    """

    name: str
    backend: str
    factory: Callable[[], AnyBackend]
    stage: int
    kind: Literal["pure", "mocked", "real-local", "real-live", "replay"]
    capabilities: frozenset[Capability]
    is_async: bool
    cleanup: Callable[[AnyBackend], None] | None = None
    aclose: Callable[[AnyBackend], Awaitable[None]] | None = None
    """Awaitable teardown for async fixtures that own a real network pool.

    Set on async live fixtures so the conformance ``async_backend``
    indirect fixture can ``await`` it after a test. Sync fixtures and
    async fixtures whose teardown is purely synchronous (e.g.
    ``memory_async``) leave it as ``None``. Sync ``cleanup`` and async
    ``aclose`` are independent: a fixture may set both when it has both
    sync resources to release and an async pool to close.
    """
    marks: tuple[pytest.MarkDecorator, ...] = field(default_factory=tuple)
    """Pytest marks applied to this fixture's parametrize entry.

    Carries CI-runtime selectors that should ride along with the fixture
    name. For example, ``pytest.mark.os_sensitive`` on the ``local``
    fixture so that LocalBackend conformance is included in the
    macOS/Windows CI matrix that selects ``-m "os_sensitive"``.
    """


_FIXTURES: list[BackendFixture] = []


def register(fixture: BackendFixture) -> None:
    """Append ``fixture`` to the registry. Called from per-backend modules.

    Duplicate names raise ``ValueError`` to surface accidental
    double-registration of the same fixture.
    """
    for existing in _FIXTURES:
        if existing.name == fixture.name:
            raise ValueError(f"duplicate fixture name: {fixture.name!r}")
    _FIXTURES.append(fixture)


def all_fixtures() -> list[BackendFixture]:
    """Return every registered fixture, unfiltered.

    Useful for tests that walk the full registry (e.g. layout
    invariant checks). Most call sites want ``fixtures`` instead.
    """
    return list(_FIXTURES)


def fixtures(*caps: Capability, is_async: bool = False) -> list[BackendFixture]:
    """Return registry entries matching ``caps`` for the active stage.

    Filters applied (in order):

    1. ``stage <= current_stage()`` for TEST-006 stage selection. Each
       stage includes all lower stages.
    2. ``is_async == is_async``: sync and async parametrize callers
       see disjoint subsets.
    3. ``caps <= fixture.capabilities`` for TEST-005 capability
       id-filtering. A fixture lacking any requested capability is
       absent from the returned list (no ``SKIPPED`` entry is emitted
       at runtime because the test was never parametrised over it).

    Pass no ``caps`` to get every fixture in the requested mode and
    stage band.
    """
    stage_cap = current_stage()
    cap_set = frozenset(caps)
    return [
        f for f in _FIXTURES if f.stage <= stage_cap and f.is_async is is_async and cap_set.issubset(f.capabilities)
    ]


def fixture_params(*caps: Capability, is_async: bool = False) -> list[Any]:
    """Wrap ``fixtures`` results as ``pytest.param`` entries.

    Each entry carries the fixture's ``name`` as the parametrize id and
    its ``marks`` (e.g. ``os_sensitive`` on local). Pass directly to
    ``@pytest.mark.parametrize("backend", fixture_params(Cap.X),
    indirect=True)``.
    """
    return [pytest.param(f, id=f.name, marks=list(f.marks)) for f in fixtures(*caps, is_async=is_async)]


__all__ = [
    "AnyBackend",
    "BackendFixture",
    "all_fixtures",
    "fixture_params",
    "fixtures",
    "register",
]
