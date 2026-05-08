"""Conformance-only registry-driven parametrize (spec 048 / TEST-005).

This conftest is scoped to ``tests/backends/conformance/``. It hosts the
``backend`` and ``async_backend`` indirect fixtures and the
``pytest_generate_tests`` hook that auto-parametrises any conformance
test taking those arguments over ``fixture_params``.

The hook lives here, not in ``tests/backends/conftest.py``, because
per-backend tests under ``tests/backends/<backend>/`` use a ``backend``
parameter typed to their own concrete backend class for their own local
fixtures. A repository-wide auto-walk would multiply each per-backend
test by every registered backend.

Tests can still opt in to capability filtering at the class level::

    @pytest.mark.parametrize(
        "backend",
        fixture_params(Capability.WRITE),
        indirect=True,
    )

The hook detects an explicit ``parametrize`` and skips its own walk in
that case, so explicit markers and the auto-walk cohabit cleanly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures import BackendFixture, fixture_params

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from remote_store._backend import Backend


def _is_already_parametrized(metafunc: pytest.Metafunc, argname: str) -> bool:
    """Return True if ``argname`` is already parametrized via a marker."""
    for marker in metafunc.definition.iter_markers("parametrize"):
        if not marker.args:
            continue
        argnames = marker.args[0]
        names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
        if argname in names:
            return True
    return False


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrise conformance tests requesting ``backend`` / ``async_backend``."""
    if "backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "backend"):
        metafunc.parametrize("backend", fixture_params(is_async=False), indirect=True)
    if "async_backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "async_backend"):
        metafunc.parametrize("async_backend", fixture_params(is_async=True), indirect=True)


@pytest.fixture
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Indirect fixture: build a Backend from a ``BackendFixture`` record."""
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    try:
        yield instance  # type: ignore[misc]
    finally:
        if fixture.cleanup is not None:
            fixture.cleanup(instance)


@pytest.fixture
async def async_backend(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    """Indirect async fixture: build an AsyncBackend from a ``BackendFixture`` record.

    Sync ``cleanup`` and async ``aclose`` are both honoured. Async fixtures
    that own a real network pool (live cloud backends) set ``aclose`` so
    the connection pool is awaited before the next test starts. Sync
    teardown (e.g. tempdir removal) goes through ``cleanup`` as for sync
    fixtures. ``asyncio_mode = "auto"`` in ``pyproject.toml`` makes the
    ``async def`` fixture a first-class pytest-asyncio fixture without
    additional decorators.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    try:
        yield instance
    finally:
        if fixture.aclose is not None:
            await fixture.aclose(instance)
        if fixture.cleanup is not None:
            fixture.cleanup(instance)
