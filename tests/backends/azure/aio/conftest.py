"""Async HNS cassette wiring (BK-303) — overrides the sync azure-subtree conftest.

Mirrors ``tests/backends/azure/conftest.py`` for the async HNS deviation suite
(``tests/backends/azure/aio/test_live_hns.py``). Redefines ``_hns_record`` over
the async records (``azure_live_hns_async`` / ``azure_replay_hns_async``),
``_hns_dir`` (async per-session ``live-hns-async/<uuid8>`` prefix), the async
``async_live_hns_backend``, and ``live_hns_env``. The generic cassette routing
fixtures and hooks are inherited from the parent ``azure/conftest.py``.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from tests.backends.azure.conftest import hns_record_params
from tests.backends.fixtures._cassettes_azure import (
    FAKE_CONN_STR,
    FAKE_FILESYSTEM,
    LIVE_HNS_ROOT_FS,
    REPLAY_HNS_DIRPATH_ASYNC,
)
from tests.backends.fixtures._live_env import (
    require_azure_live_connection_string,
    require_azure_live_hns_container,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from tests.backends.fixtures.registry import BackendFixture


@pytest.fixture(params=hns_record_params(is_async=True))
def _hns_record(request: pytest.FixtureRequest) -> BackendFixture:
    """The async HNS record (``azure_live_hns_async`` or ``azure_replay_hns_async``)."""
    return request.param


@pytest.fixture
def _hns_dir(_hns_record: BackendFixture) -> Iterator[tuple[str, str, str]]:
    """Yield ``(conn, fs_name, dirpath)`` for the async HNS directory under test.

    The directory is provisioned via the *sync* ``DataLakeServiceClient`` so no
    event loop is needed at setup (mirrors the original ``_live_hns_setup``);
    the async backend under test exercises the async SDK during the test body.
    """
    if _hns_record.kind == "replay":
        yield (FAKE_CONN_STR, FAKE_FILESYSTEM, REPLAY_HNS_DIRPATH_ASYNC)
        return

    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    fs_name = require_azure_live_hns_container()
    prefix = f"live-hns-async/{uuid.uuid4().hex[:8]}"
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
async def async_live_hns_backend(
    _hns_record: BackendFixture, _hns_dir: tuple[str, str, str]
) -> AsyncIterator[tuple[Any, str]]:
    """Yield ``(AsyncAzureBackend, dirpath)`` for the async HNS directory under test."""
    backend = _hns_record.factory()
    try:
        yield backend, _hns_dir[2]
    finally:
        if _hns_record.aclose is not None:
            await _hns_record.aclose(backend)
        if _hns_record.cleanup is not None:
            _hns_record.cleanup(backend)


@pytest.fixture
def live_hns_env(_hns_dir: tuple[str, str, str]) -> tuple[str, str]:
    """Yield ``(connection_string, filesystem)`` for the async HNS account under test."""
    return _hns_dir[0], _hns_dir[1]


@pytest.fixture
async def async_live_hns_root_backend(_hns_record: BackendFixture) -> AsyncIterator[Any]:
    """Async twin of ``live_hns_root_backend`` — a dedicated *empty* HNS filesystem.

    ``get_folder_info("")`` enumerates the whole container root, so the root test
    targets ``LIVE_HNS_ROOT_FS`` (dedicated, persistent, empty) instead of the
    shared container, keeping the recorded root listing a deterministic
    ``{"paths":[]}``. The empty filesystem is provisioned via the *sync*
    ``DataLakeServiceClient`` (no event loop at setup, mirroring ``_hns_dir``);
    the async backend exercises the async SDK during the test body and injects
    ``AsyncioRequestsTransport`` while recording (vcrpy's aiohttp stub drops
    streaming bodies). Replay reuses the standard ``FAKE_FILESYSTEM`` backend.
    """
    if _hns_record.kind == "replay":
        backend = _hns_record.factory()
        try:
            yield backend
        finally:
            if _hns_record.aclose is not None:
                await _hns_record.aclose(backend)
            if _hns_record.cleanup is not None:
                _hns_record.cleanup(backend)
        return

    from azure.core.exceptions import ResourceExistsError  # noqa: PLC0415
    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    client_options: dict[str, object] = {}
    if os.environ.get("_RS_CASSETTE_RECORDING") == "1":
        with contextlib.suppress(ImportError):
            from azure.core.pipeline.transport import AsyncioRequestsTransport  # noqa: PLC0415

            client_options = {"transport": AsyncioRequestsTransport()}

    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        with contextlib.suppress(ResourceExistsError):
            service.create_file_system(LIVE_HNS_ROOT_FS)
        backend = AsyncAzureBackend(
            container=LIVE_HNS_ROOT_FS,
            hns=True,
            connection_string=conn,
            client_options=client_options or None,
        )
        try:
            yield backend
        finally:
            await backend.aclose()
    finally:
        service.close()
