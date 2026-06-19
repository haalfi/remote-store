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

HTTP cassette / replay (TEST-007 / spec 049)
--------------------------------------------
The generic, registry-driven cassette wiring — directory routing, live/replay
name aliasing, the scrub-config fixture, the plugin guard, the missing-cassette
skip, and the scrub-fire manifest dump — lives in
``tests/backends/fixtures/_cassette_pytest.py`` so the sibling
``tests/backends/azure/`` deviation subtree can reuse it (BK-303). This conftest
imports the three fixtures and three hook helpers and adds only what is
conformance-specific: the real-ADLS-Gen2 xfail roster.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures import BackendFixture, fixture_params
from tests.backends.fixtures._cassette_pytest import (
    apply_missing_cassette_skips,
    cassette_plugin_guard,
    default_cassette_name,  # noqa: F401 — imported so pytest resolves it as a fixture
    dump_scrub_manifest,
    vcr_cassette_dir,  # noqa: F401 — imported so pytest resolves it as a fixture
    vcr_config,  # noqa: F401 — imported so pytest resolves it as a fixture
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from remote_store._backend import Backend


_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plugin guard + manifest dump (delegated to the shared cassette wiring)
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast if pytest-recording is not installed (TEST-007)."""
    cassette_plugin_guard(config)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Dump the per-rule scrub-fire manifest for the recorder's Step-4 audit.

    No-op unless ``record_cassettes.py`` exported ``_RS_SCRUB_MANIFEST``.
    """
    dump_scrub_manifest()


# ---------------------------------------------------------------------------
# Missing-cassette skip hook (TEST-007) + HNS known-failures xfail
# ---------------------------------------------------------------------------

# Test function names that expose a real-ADLS-Gen2 conformance gap not yet
# fixed in the backend.  Applied as xfail(strict=False) for real-Azure
# fixture IDs so CI does not treat them as unexpected failures; once the
# underlying bug is fixed and cassettes are re-recorded, the xpass signals
# the entry can be removed.  Currently empty: BUG-202 + BUG-203 fixes landed
# in PR #650; cassettes were refreshed (BK-224) so both names xpass and were
# removed from the roster.  Guard: ``test_xfail_guard.py`` asserts every
# entry matches a live test function.
_AZURE_HNS_KNOWN_FAILURE_FN_NAMES: frozenset[str] = frozenset()

# Fixture IDs that represent real ADLS Gen2 (live or replay) — not Azurite.
_AZURE_REAL_FIXTURE_IDS: frozenset[str] = frozenset(
    {
        "azure_live",
        "azure_live_async",
        "azure_replay",
        "azure_replay_async",
    }
)


def _has_real_azure_fixture(node_id: str) -> bool:
    """Return True if the node ID contains a real-Azure fixture ID as a whole token."""
    for fid in _AZURE_REAL_FIXTURE_IDS:
        if f"[{fid}]" in node_id or f"[{fid}-" in node_id or f"-{fid}]" in node_id or f"-{fid}-" in node_id:
            return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply the real-Azure xfail roster, then the missing-cassette skip (TEST-007).

    The xfail marks are applied in **all** modes, including ``--record``.
    During recording, xfail still lets the HTTP call complete (so the cassette
    is written) and then gracefully handles the subsequent assertion failure
    — without this, ``record_cassettes.py`` aborts at step 2 when the known-
    failing tests return non-zero. The missing-cassette skip (delegated to the
    shared helper) is gated on replay mode internally.
    """
    for item in items:
        fn_name = getattr(item, "originalname", item.name.split("[")[0])
        if fn_name in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES and _has_real_azure_fixture(item.nodeid):
            item.add_marker(
                pytest.mark.xfail(
                    strict=False,
                    reason="Known real-ADLS-Gen2 conformance gap (see _AZURE_HNS_KNOWN_FAILURE_FN_NAMES)",
                )
            )

    apply_missing_cassette_skips(config, items)


# ---------------------------------------------------------------------------
# Conformance parametrize hooks
# ---------------------------------------------------------------------------


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
    """Indirect fixture: build a Backend from a ``BackendFixture`` record.

    Attaches the ``BackendFixture`` record onto the produced instance as
    ``_fixture_record`` so conformance helpers (``_skip_flat_namespace``,
    self-op skips) can consult per-fixture flags without re-deriving them
    from ``backend.name``. Reading the record is what closes BK-185 — the
    Azurite emulator and live ADLS Gen2 share ``backend.name == "azure"``
    but disagree on ``flat_namespace``.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    # Constraint: backend classes must not define ``__slots__`` (and must
    # not override ``__setattr__`` to reject unknown attributes). The
    # current backend set is plain dataclasses / classes with no slots,
    # so the assignment is safe; if a future backend adds slots, surface
    # the failure here rather than silently in a downstream
    # ``_fixture_record`` access.
    instance._fixture_record = fixture  # type: ignore[attr-defined]
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

    Both teardown channels are guarded so a transient failure in
    ``aclose`` (e.g. SDK pool-flush error) cannot strand the resource
    that ``cleanup`` is responsible for releasing — mirrors the same
    threat model that motivates the per-fixture ``_cleanup`` guards in
    ``azure_live`` / ``azurite``.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    # Same ``__slots__`` constraint as the sync ``backend`` fixture above.
    instance._fixture_record = fixture  # type: ignore[attr-defined]
    try:
        yield instance
    finally:
        if fixture.aclose is not None:
            try:
                await fixture.aclose(instance)
            except Exception:  # noqa: BLE001 -- teardown is best-effort
                _LOG.warning("fixture.aclose() failed; continuing to cleanup", exc_info=True)
        if fixture.cleanup is not None:
            fixture.cleanup(instance)
