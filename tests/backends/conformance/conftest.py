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

HTTP cassette / replay (TEST-007)
----------------------------------
This conftest also hosts the pytest-recording wiring that bridges
``azure_live`` (record source) and ``azure_replay`` (replay consumer):

* ``pytest_configure`` — plugin guard: fails fast when pytest-recording is
  not installed so the ``record_mode`` fixture is never missing.
* ``vcr_cassette_dir`` — directs all azure cassettes to the spec-mandated
  path ``tests/backends/cassettes/azure/``.
* ``default_cassette_name`` — normalises ``[azure_live]`` / ``[azure_replay]``
  to ``[azure]`` (and the async variants to ``[azure_async]``) so that the
  cassette recorded from the live fixture is the same file read by the
  replay fixture (plan challenge 1).
* ``vcr_config`` — the scrubbing layer; drops credentials, rewrites the real
  account name and per-call filesystem UUID to fixed placeholders.
* ``pytest_collection_modifyitems`` — missing-cassette → skip hook (TEST-007:
  if the cassette is absent, skip rather than raise).
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import TYPE_CHECKING, Any

import pytest

from tests.backends.fixtures import BackendFixture, fixture_params
from tests.backends.fixtures._cassettes import (
    CASSETTE_DIR_AZURE,
    build_vcr_config,
    live_connection_string,
    parse_account_name,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from remote_store._backend import Backend


_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cassette name normalisation (TEST-007 / plan challenge 1)
# ---------------------------------------------------------------------------

# Maps each parametrize-id suffix that carries cassette traffic to a
# backend-canonical suffix shared by both the live (recording) and replay
# (playback) parametrizations.  The normalisation ensures that
# ``test_foo[azure_live]`` and ``test_foo[azure_replay]`` share one cassette
# file (``test_foo[azure].yaml``) — and similarly for the async variants.
_CASSETTE_ID_ALIASES: dict[str, str] = {
    "azure_live": "azure",
    "azure_live_async": "azure_async",
    "azure_replay": "azure",
    "azure_replay_async": "azure_async",
}

# Forbidden characters replaced by pytest-recording's get_default_cassette_name.
_FORBIDDEN_CASSETTE_CHARS = r"""<>?%*:|"'/\\"""


def _normalise_cassette_name(node_name: str, cls: type | None) -> str:
    """Return a cassette name with backend-fixture suffixes normalised.

    Applies the same class-prefix and forbidden-char replacement logic as
    ``pytest_recording.plugin.get_default_cassette_name`` so the skip hook
    and the ``default_cassette_name`` fixture compute the same path.

    Handles ids where the backend fixture appears at any position within the
    parametrize bracket group — first (``[azure_replay-write-no-overwrite]``),
    last (``[write-azure_replay]``), or sole (``[azure_replay]``).  Each
    fixture name is matched as a whole component bounded by ``[``, ``]``, or
    ``-`` so no partial-name collisions can occur.
    """
    name = node_name
    for fixture_name, canonical in _CASSETTE_ID_ALIASES.items():
        name = name.replace(f"[{fixture_name}]", f"[{canonical}]")
        name = name.replace(f"[{fixture_name}-", f"[{canonical}-")
        name = name.replace(f"-{fixture_name}]", f"-{canonical}]")
        name = name.replace(f"-{fixture_name}-", f"-{canonical}-")
    cassette_name = f"{cls.__name__}.{name}" if cls is not None else name
    for ch in _FORBIDDEN_CASSETTE_CHARS:
        cassette_name = cassette_name.replace(ch, "-")
    return cassette_name


def _cassette_path_for_item(item: pytest.Item) -> None | Any:
    """Return the expected cassette ``Path`` for a vcr-marked conformance test.

    Returns ``None`` when the item's parametrize id is not an azure fixture
    (and therefore has no cassette path to check).
    """
    from pathlib import Path  # noqa: PLC0415 -- local to avoid top-level Path import noise

    name = item.name
    # Check if any alias fixture name appears as a whole component in the id.
    if not any(
        f"[{k}]" in name or f"[{k}-" in name or f"-{k}]" in name or f"-{k}-" in name for k in _CASSETTE_ID_ALIASES
    ):
        return None
    cls = getattr(item, "cls", None)
    cassette_name = _normalise_cassette_name(name, cls)
    return Path(CASSETTE_DIR_AZURE) / f"{cassette_name}.yaml"


# ---------------------------------------------------------------------------
# Plugin guard (TEST-007)
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast if pytest-recording is not installed.

    The ``record_mode`` fixture (session-scoped, provided by pytest-recording)
    is a dependency of both ``vcr_config`` and the ``vcr`` autouse fixture.
    A missing plugin would surface as an opaque ``fixture 'record_mode' not
    found`` deep in a session that otherwise looks healthy.  This guard
    converts that into a clear up-front message.
    """
    if importlib.util.find_spec("pytest_recording") is None:
        pytest.exit(
            "pytest-recording is required for HTTP cassette replay (TEST-007); "
            "run: uv pip install --python .venv pytest-recording",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# Cassette directory and name overrides (TEST-007 / plan challenges 1 & 2)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:  # noqa: ARG001
    """Override: all conformance azure cassettes live in tests/backends/cassettes/azure/.

    Spec TEST-007 mandates ``tests/backends/cassettes/<backend>/`` for all
    HTTP replay cassettes.  The default pytest-recording path
    (``{test_file_dir}/cassettes/{test_module}/``) would scatter cassettes
    across the conformance subtree; centralising them makes the corpus
    reviewable as a single PR diff (TEST-009).

    Module-scoped to match the scope of pytest-recording's built-in
    ``vcr_cassette_dir`` fixture.  Non-azure tests in this module are
    unaffected: the ``vcr`` autouse fixture only activates for tests that
    carry ``pytest.mark.vcr``.
    """
    return str(CASSETTE_DIR_AZURE)


@pytest.fixture
def default_cassette_name(request: pytest.FixtureRequest) -> str:
    """Override: normalise backend-fixture suffixes so live and replay share a cassette.

    ``test_foo[azure_live]`` and ``test_foo[azure_replay]`` must read and write
    the same cassette file.  pytest-recording's default uses the raw node name,
    which would produce two different files.  This fixture applies the
    ``_CASSETTE_ID_ALIASES`` map to collapse them to a shared canonical suffix
    (``[azure]`` / ``[azure_async]``).
    """
    return _normalise_cassette_name(request.node.name, request.cls)


# ---------------------------------------------------------------------------
# Scrubbing layer — vcr_config fixture (TEST-007)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _real_azure_account(record_mode: str) -> str | None:
    """Real storage-account name (record mode) or ``None`` (replay mode).

    Session-scoped because ``record_mode`` is session-scoped and the env var
    does not change within a session.  Only calls ``live_connection_string()``
    when recording is active (any mode other than ``"none"``), so normal
    ``hatch run test`` runs never touch ``.env`` credentials.
    """
    if record_mode == "none":
        return None
    return parse_account_name(live_connection_string())


@pytest.fixture
def vcr_config(_real_azure_account: str | None) -> dict[str, Any]:
    """Scrubbing layer for vcrpy: credentials, account name, filesystem UUID.

    Delegates to ``_cassettes.build_vcr_config`` which is the single source
    of truth for what gets stripped out of every recorded cassette.
    """
    return build_vcr_config(_real_azure_account)


# ---------------------------------------------------------------------------
# Missing-cassette skip hook (TEST-007) + HNS known-failures xfail
# ---------------------------------------------------------------------------

# Test function names known to expose real-ADLS-Gen2 conformance gaps.
# Real ADLS Gen2 accepts or mishandles calls that Azurite correctly rejects
# per spec.  Each name below is grouped by the BUG it tracks:
#   - BUG-198 (folder-API on HNS file path, async): test_delete_folder_on_file_*,
#     test_get_folder_info_on_file_raises_error
#   - BUG-200 (move/copy directory checks on HNS, async):
#     test_source_is_directory_raises_error, test_destination_is_directory_raises_error
#   - BUG-202 (write_atomic streaming MissingRequiredQueryParameter on HNS):
#     test_size_matches_written_bytes_for_streaming_input
#   - BUG-203 (is_file returns True for HNS directory blob): test_is_file
# Applied as xfail(strict=False) for real-Azure fixture IDs so that:
#   - CI does not treat them as unexpected failures (they match live behaviour)
#   - Once the bugs are fixed, they flip to xpass without blocking CI
_AZURE_HNS_KNOWN_FAILURE_FN_NAMES: frozenset[str] = frozenset(
    {
        # BUG-198
        "test_delete_folder_on_file_raises_error",
        "test_delete_folder_on_file_missing_ok_still_raises",
        "test_get_folder_info_on_file_raises_error",
        # BUG-200
        "test_source_is_directory_raises_error",
        "test_destination_is_directory_raises_error",
        # BUG-202
        "test_size_matches_written_bytes_for_streaming_input",
        # BUG-203
        "test_is_file",
    }
)

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
    """Skip vcr-marked conformance tests whose cassette is absent (TEST-007).

    Also marks known HNS-bug test functions as xfail for real-Azure fixture IDs
    so that CI does not treat them as unexpected failures.

    vcrpy's native behaviour in ``record_mode=none`` is to *raise* on an
    unmatched request.  The spec requires a *skip* instead.  This hook checks
    at collection time and adds ``pytest.mark.skip`` for any vcr-marked test
    whose cassette file does not exist yet.

    The xfail marks are applied in **all** modes, including ``--record``.
    During recording, xfail still lets the HTTP call complete (so the cassette
    is written) and then gracefully handles the subsequent assertion failure
    — without this, ``record_cassettes.py`` aborts at step 2 when the known-
    failing tests return non-zero.  Only the missing-cassette skip is gated on
    replay mode.
    """
    record_mode = config.getoption("--record-mode", default=None) or "none"

    # HNS known-failures: applied unconditionally (record + replay).
    for item in items:
        fn_name = getattr(item, "originalname", item.name.split("[")[0])
        if fn_name in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES and _has_real_azure_fixture(item.nodeid):
            item.add_marker(
                pytest.mark.xfail(
                    strict=False,
                    reason="Known real-ADLS-Gen2 conformance gap (see BUG-198/200/202/203 in BACKLOG.md)",
                )
            )

    # Missing-cassette skip: only relevant during replay (cassette is being
    # written during recording, so its absence is expected).
    if record_mode != "none":
        return
    for item in items:
        if item.get_closest_marker("vcr") is None:
            continue
        cassette = _cassette_path_for_item(item)
        if cassette is None or cassette.exists():
            continue
        rel = os.path.relpath(cassette, config.rootpath)
        item.add_marker(
            pytest.mark.skip(reason=f"replay cassette missing ({rel}); record with pytest --stage=3 --record")
        )


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
