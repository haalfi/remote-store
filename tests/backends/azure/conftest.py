"""Cassette record/replay wiring for the Azure HNS deviation suite (BK-303).

``tests/backends/azure/test_live_hns.py`` exercises HNS-only behaviour the
conformance suite cannot express (real ``hdi_isfolder`` directory-marker
probes, the ``exists`` DataLake fallback, ``get_folder_info("")`` root carve-out,
``AzureUtils.detect_hns``). Before BK-303 it ran only live; now it has a
record-once / replay-creds-free tier mirroring the conformance
``azure_live`` → ``azure_replay`` pair.

This conftest:

* reuses the generic cassette wiring from
  ``tests/backends/fixtures/_cassette_pytest.py`` — the same routing, scrub
  config, plugin guard, missing-cassette skip, and manifest dump the
  conformance conftest uses — so HNS cassettes land in ``cassettes/azure/`` and
  the recorder's Step-4 audit sees their scrub fires;
* parametrises the HNS suite over the ``azure_live_hns`` / ``azure_replay_hns``
  registry records (``conformance_excluded`` keeps them out of the conformance
  surface) via the ``_hns_record`` fixture, so a single set of test bodies runs
  both live (record) and replay;
* adapts each record into the ``(backend, dirpath)`` / ``(conn, fs)`` shapes the
  existing test bodies consume via ``live_hns_backend`` / ``live_hns_env``.

The async sibling (``aio/conftest.py``) overrides ``_hns_record`` /
``_hns_dir`` / ``live_hns_env`` for the async records and adds
``async_live_hns_backend``; it inherits the routing fixtures and hooks from
here.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from tests.backends.fixtures._cassette_pytest import (
    apply_missing_cassette_skips,
    cassette_plugin_guard,
    default_cassette_name,  # noqa: F401 — imported so pytest resolves it as a fixture
    dump_scrub_manifest,
    vcr_cassette_dir,  # noqa: F401 — imported so pytest resolves it as a fixture
    vcr_config,  # noqa: F401 — imported so pytest resolves it as a fixture
)
from tests.backends.fixtures._cassettes_azure import (
    FAKE_CONN_STR,
    FAKE_FILESYSTEM,
    LIVE_HNS_ROOT_FS,
    REPLAY_HNS_DIRPATH_SYNC,
)
from tests.backends.fixtures._live_env import (
    require_azure_live_connection_string,
    require_azure_live_hns_container,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.backends.fixtures.registry import BackendFixture

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cassette wiring hooks (delegated to the shared module)
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast if pytest-recording is not installed (TEST-007)."""
    cassette_plugin_guard(config)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip HNS replay tests whose cassette is absent (TEST-007)."""
    apply_missing_cassette_skips(config, items)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Dump the per-rule scrub-fire manifest for the recorder's Step-4 audit."""
    dump_scrub_manifest()


# ---------------------------------------------------------------------------
# HNS record selection + directory provisioning
# ---------------------------------------------------------------------------


def hns_record_params(*, is_async: bool) -> list[Any]:
    """Return ``pytest.param`` entries for the HNS live/replay records.

    The parametrize id is the fixture name (``azure_live_hns`` /
    ``azure_replay_hns``) so the root conftest's dynamic ``vcr`` mark, the
    profile's ``fixture_aliases``, the recorder ``-k`` filter, and the
    missing-cassette skip all key on it. Each record's own marks ride along —
    ``pytest.mark.live`` on the live record, ``pytest.mark.vcr(record_mode="none")``
    on the replay record.
    """
    from tests.backends.fixtures import _load_all, all_fixtures  # noqa: PLC0415

    _load_all()  # idempotent; guards against conftest import-order surprises
    by_name = {f.name: f for f in all_fixtures()}
    names = ["azure_live_hns_async", "azure_replay_hns_async"] if is_async else ["azure_live_hns", "azure_replay_hns"]
    return [pytest.param(by_name[n], marks=list(by_name[n].marks), id=n) for n in names]


@pytest.fixture(params=hns_record_params(is_async=False))
def _hns_record(request: pytest.FixtureRequest) -> BackendFixture:
    """The sync HNS record (``azure_live_hns`` or ``azure_replay_hns``) under test."""
    return request.param


@pytest.fixture
def _hns_dir(_hns_record: BackendFixture) -> Iterator[tuple[str, str, str]]:
    """Yield ``(conn, fs_name, dirpath)`` for the HNS directory under test.

    Replay: returns the fixed ``FAKE_CONN_STR`` / ``FAKE_FILESYSTEM`` /
    ``REPLAY_HNS_DIRPATH_SYNC`` — no HTTP, so the replay backend never recreates
    the directory; the recorded probe responses carry the directory state.

    Live: provisions a fresh ``live-hns/<uuid8>/dirblob`` directory via a
    separate ``DataLakeServiceClient`` and best-effort deletes the prefix on
    teardown. The per-session uuid is scrubbed to ``REPLAY`` by the
    ``azure.uri.hns-prefix`` rule so the cassette path matches the replay
    fixture's fixed dirpath.
    """
    if _hns_record.kind == "replay":
        yield (FAKE_CONN_STR, FAKE_FILESYSTEM, REPLAY_HNS_DIRPATH_SYNC)
        return

    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    fs_name = require_azure_live_hns_container()
    prefix = f"live-hns/{uuid.uuid4().hex[:8]}"
    dirpath = f"{prefix}/dirblob"

    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        fs_client = service.get_file_system_client(fs_name)
        fs_client.get_directory_client(dirpath).create_directory()
        try:
            yield (conn, fs_name, dirpath)
        finally:
            with contextlib.suppress(Exception):
                fs_client.get_directory_client(prefix).delete_directory()
    finally:
        service.close()


@pytest.fixture
def live_hns_backend(_hns_record: BackendFixture, _hns_dir: tuple[str, str, str]) -> Iterator[tuple[Any, str]]:
    """Yield ``(AzureBackend, dirpath)`` for the HNS directory under test."""
    backend = _hns_record.factory()
    try:
        yield backend, _hns_dir[2]
    finally:
        if _hns_record.cleanup is not None:
            _hns_record.cleanup(backend)


@pytest.fixture
def live_hns_env(_hns_dir: tuple[str, str, str]) -> tuple[str, str]:
    """Yield ``(connection_string, filesystem)`` for the HNS account under test."""
    return _hns_dir[0], _hns_dir[1]


@pytest.fixture
def live_hns_root_backend(_hns_record: BackendFixture) -> Iterator[Any]:
    """Yield an ``AzureBackend`` whose container is a dedicated *empty* HNS filesystem.

    ``get_folder_info("")`` enumerates the whole container root recursively, so
    recording it against the shared ``RS_TEST_LIVE_HNS_CONTAINER`` baked that
    container's mutable top-level inventory into the cassette (non-reproducible,
    unbounded residue). The root test instead targets ``LIVE_HNS_ROOT_FS`` — a
    dedicated, persistent, empty filesystem this fixture creates and never writes
    to — so the recorded root listing is a deterministic ``{"paths":[]}``.

    Replay reuses the standard ``FAKE_FILESYSTEM`` backend: the ``azure.uri.root-fs``
    scrub maps the live probe name onto ``FAKE_FILESYSTEM``, so the replay request
    matches the scrubbed cassette. This fixture does NOT depend on ``_hns_dir`` —
    the root probe needs no per-session directory.
    """
    if _hns_record.kind == "replay":
        backend = _hns_record.factory()
        try:
            yield backend
        finally:
            if _hns_record.cleanup is not None:
                _hns_record.cleanup(backend)
        return

    from azure.core.exceptions import ResourceExistsError  # noqa: PLC0415
    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    from remote_store.backends._azure import AzureBackend  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        # Idempotent: the probe filesystem is persistent and only ever read, so
        # an existing one is already empty. Never deleted (Azure filesystem
        # deletion is eventually-consistent and would flake a re-create).
        with contextlib.suppress(ResourceExistsError):
            service.create_file_system(LIVE_HNS_ROOT_FS)
        backend = AzureBackend(container=LIVE_HNS_ROOT_FS, hns=True, connection_string=conn)
        try:
            yield backend
        finally:
            backend.close()
    finally:
        service.close()
