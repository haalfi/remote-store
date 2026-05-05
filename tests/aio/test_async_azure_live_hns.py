"""Live ADLS Gen2 (HNS) integration tests for ``AsyncAzureBackend``.

Covers HNS semantics that mock-only suites and Azurite-backed tests cannot reproduce.
The async ``write_atomic`` HNS path (temp upload + ``rename_file``) populates
``WriteResult`` fields from a post-rename ``get_file_properties()`` call — not from
the upload response. Only a real ADLS Gen2 account can confirm that:

- The post-rename read succeeds and returns a valid ETag.
- The ETag is normalised (quote-stripped, lowercased) consistently with what
  ``get_file_info()`` independently returns via a separate SDK path.
- User-defined metadata survives the ``rename_file`` operation.
- ``write_atomic`` raises ``InvalidPath`` when the target is a real HNS directory
  blob created by the DataLake service — not one fabricated in a mock.

This file is intentionally **not** co-located with the Azurite-backed async live
tests in :mod:`tests.aio.test_async_azure_live`. That file carries a module-level
``skipif(not _azurite_reachable())`` guard; real ADLS Gen2 tests must not be blocked
by Azurite availability.

Spec: AZ-014 (``write_atomic`` atomic rename), BE-021 (directory-path guard),
WR-001a (WriteResult native fields), WR-004 (source matches capability),
WR-012 (metadata echo), WR-013 (metadata round-trip), AZ-034 (ETag normalisation).

Gating
------

Three layers, all required:

1. ``pytest.mark.live`` at module level. Default ``addopts`` is ``-m 'not live'``,
   so plain ``hatch run test`` skips the file entirely.
2. ``RS_TEST_LIVE_HNS=1`` env var — same gate as
   :mod:`tests.backends.test_azure_live_hns`.
3. ``AZURE_STORAGE_CONNECTION_STRING`` and ``RS_TEST_LIVE_HNS_CONTAINER`` pointing
   at a *real* ADLS Gen2 account. Azurite-pointing strings are rejected with
   ``pytest.fail`` rather than a silent skip.

Cost discipline
---------------

All tests share one HNS directory provisioned per module via the
``_live_hns_setup`` sync fixture. Each test writes a uuid-suffixed file under the
shared prefix so repeated runs cannot collide. Teardown deletes the entire prefix
on a best-effort basis.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.storage.filedatalake import DataLakeServiceClient  # noqa: E402

from remote_store._errors import InvalidPath  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

_LOG = logging.getLogger(__name__)

_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RS_TEST_LIVE_HNS") != "1",
        reason="live HNS suite is opt-in via RS_TEST_LIVE_HNS=1",
    ),
]

# 1 KiB keeps live-cost footprint small; payload content is irrelevant to the
# contracts under test (path shape and metadata semantics).
_PAYLOAD = b"x" * 1024


def _require_live_hns_env() -> tuple[str, str]:
    """Return (connection_string, filesystem) or fail loud.

    Mirrors the same helper in :mod:`tests.backends.test_azure_live_hns`.
    Kept local rather than shared to avoid a cross-package test import; the
    logic is a one-off env-var validation, not infrastructure worth sharing.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 -- intentional lazy import

    load_dotenv(override=False)
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    fs = os.environ.get("RS_TEST_LIVE_HNS_CONTAINER")
    if not conn:
        pytest.fail("RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING is empty")
    if not fs:
        pytest.fail("RS_TEST_LIVE_HNS=1 set but RS_TEST_LIVE_HNS_CONTAINER is empty")
    if any(frag in conn for frag in _AZURITE_FRAGMENTS):
        pytest.fail(
            "RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING points at Azurite; "
            "the live HNS suite needs a real ADLS Gen2 account"
        )
    return conn, fs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _live_hns_setup() -> Iterator[tuple[str, str, str, str]]:
    """Module-scoped sync fixture: provision one HNS directory for the whole session.

    Yields ``(conn, fs_name, dirpath, prefix)`` where ``dirpath`` is the path
    of an HNS directory blob created via ``DataLakeServiceClient``. All four
    values are strings so the async ``async_live_hns_backend`` fixture can
    consume them without needing an event loop at setup time.

    Teardown deletes the entire prefix on a best-effort basis; a teardown race
    must not turn a green test red.
    """
    conn, fs_name = _require_live_hns_env()
    prefix = f"live-hns-async/{uuid.uuid4().hex[:8]}"
    dirpath = f"{prefix}/dirblob"

    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        fs_client = service.get_file_system_client(fs_name)
        fs_client.get_directory_client(dirpath).create_directory()
        try:
            yield conn, fs_name, dirpath, prefix
        finally:
            try:
                fs_client.get_directory_client(prefix).delete_directory()
            except Exception:  # noqa: BLE001 -- teardown is best-effort
                _LOG.warning("failed to delete live async HNS prefix %s", prefix, exc_info=True)
    finally:
        service.close()


@pytest.fixture
async def async_live_hns_backend(
    _live_hns_setup: tuple[str, str, str, str],
) -> AsyncIterator[tuple[AsyncAzureBackend, str]]:
    """Per-test ``AsyncAzureBackend`` against the real ADLS Gen2 account.

    The backend object is cheap to create; making it function-scoped ensures
    each test gets a clean connection-pool state without paying for repeated
    directory provisioning (which is module-scoped in ``_live_hns_setup``).

    Yields ``(backend, dirpath)`` matching the module-level HNS directory.
    """
    conn, fs_name, dirpath, _ = _live_hns_setup
    backend = AsyncAzureBackend(container=fs_name, connection_string=conn)
    try:
        yield backend, dirpath
    finally:
        await backend.aclose()


# ---------------------------------------------------------------------------
# WR-001a / WR-004 — WriteResult native fields for the async HNS path
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsWriteResult:
    """WriteResult from async write_atomic on a real HNS account must be fully native-sourced.

    The async HNS ``write_atomic`` path (temp upload + ``rename_file``) populates
    ``etag`` and ``last_modified`` from a post-rename ``get_file_properties()`` call.
    This is a distinct code path from the non-HNS async path (which reads from the
    ``upload_blob`` response dict). Only a real ADLS Gen2 account confirms that the
    post-rename read succeeds, returns a valid ETag, and that the ETag normalises
    consistently with what ``get_file_info()`` returns via its independent SDK call.

    Spec: WR-001a, WR-004, BE-010, AZ-034.
    """

    @pytest.mark.spec("WR-001a", "WR-004", "BE-010", "AZ-034")
    async def test_write_atomic_hns_write_result_fully_native(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """All native WriteResult fields must be populated and consistent for async HNS write_atomic.

        The etag cross-check (``WriteResult.etag`` vs ``FileInfo.etag``) is the
        uniquely live assertion: the backend reads etag via two distinct SDK paths
        (post-rename ``get_file_properties`` vs ``get_blob_properties`` inside
        ``get_file_info``), and normalisation inconsistency only surfaces on a real
        account.
        """
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/wr-native-{uuid.uuid4().hex[:8]}.txt"

        result = await backend.write_atomic(path, _PAYLOAD)

        # WR-004 / WR-001a: async HNS backend declares WRITE_RESULT_NATIVE.
        assert result.source == "native"
        # WR-001a: size must equal the committed byte count.
        assert result.size == len(_PAYLOAD)
        # WR-001a / AZ-034: etag from post-rename get_file_properties must be
        # non-empty, quote-stripped, and lowercased.
        assert result.etag is not None, (
            "async HNS write_atomic must populate WriteResult.etag from post-rename get_file_properties"
        )
        assert result.etag != ""
        assert '"' not in result.etag, f"etag must be quote-stripped; got {result.etag!r}"
        assert result.etag == result.etag.lower(), f"etag must be lowercased; got {result.etag!r}"
        # WR-001a: last_modified from the post-rename read must be timezone-aware.
        assert result.last_modified is not None, "async HNS write_atomic must populate WriteResult.last_modified"
        assert result.last_modified.tzinfo is not None, "last_modified must be timezone-aware"
        # AZ-034 consistency: WriteResult.etag and FileInfo.etag must agree.
        fi = await backend.get_file_info(path)
        assert fi.etag is not None
        assert fi.etag == result.etag, (
            f"WriteResult.etag {result.etag!r} != FileInfo.etag {fi.etag!r}: "
            "normalisation inconsistent between post-rename get_file_properties and get_file_info"
        )


# ---------------------------------------------------------------------------
# WR-012 / WR-013 — metadata echo and round-trip through async HNS rename
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsMetadata:
    """Metadata must be echoed in WriteResult (WR-012) and survive the async HNS rename (WR-013).

    The async ``write_atomic`` HNS path uploads to a temp file with ``metadata=``
    then renames. Mocks verify the kwarg reaches ``upload_data``; only a real account
    confirms ``rename_file`` does not drop the metadata.
    """

    @pytest.mark.spec("WR-012", "WR-013", "BE-010", "AZ-014")
    async def test_write_atomic_hns_metadata_echo_and_round_trip(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/meta-{uuid.uuid4().hex[:8]}.txt"
        metadata = {"env": "prod", "owner": "team-a"}

        result = await backend.write_atomic(path, _PAYLOAD, metadata=metadata)

        # WR-012: WriteResult.metadata must echo the caller's mapping immediately —
        # the backend must not wait for a round-trip to populate this field.
        assert result.metadata == metadata
        # WR-001a baseline: size and source are always populated.
        assert result.size == len(_PAYLOAD)
        assert result.source == "native"

        fi = await backend.get_file_info(path)
        assert fi.metadata is not None, "WR-013: metadata must survive async HNS rename_file"
        # Compare key-by-key: ADLS Gen2 may surface internal markers alongside user
        # metadata, and the backend is allowed to strip them. The contract is that
        # user-supplied keys round-trip with their values intact.
        assert fi.metadata.get("env") == "prod"
        assert fi.metadata.get("owner") == "team-a"


# ---------------------------------------------------------------------------
# BE-021 — directory-path guard on a real HNS account (async API)
# ---------------------------------------------------------------------------


async def _async_write(backend: AsyncAzureBackend, path: str) -> None:
    await backend.write(path, _PAYLOAD)


async def _async_write_atomic(backend: AsyncAzureBackend, path: str) -> None:
    await backend.write_atomic(path, _PAYLOAD)


class TestAsyncLiveHnsDirectoryGuard:
    """``write`` and ``write_atomic`` must raise ``InvalidPath`` on a real HNS directory blob.

    Async companion to ``TestAzureLiveHnsDirectoryGuard`` in
    :mod:`tests.backends.test_azure_live_hns`. Both async methods carry the same
    ``hdi_isfolder`` probe; only a real account confirms the marker is set by the
    DataLake service rather than fabricated in a mock. ``AsyncAzureBackend`` has no
    ``open_atomic``; the two write methods are the full async guard surface.

    Spec: BE-021, BE-008, BE-010.
    """

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(_async_write, id="write", marks=pytest.mark.spec("BE-008")),
            pytest.param(_async_write_atomic, id="write_atomic", marks=pytest.mark.spec("BE-010")),
        ],
    )
    async def test_directory_path_raises_invalid_path(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
        operation,
    ) -> None:
        backend, dirpath = async_live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await operation(backend, dirpath)
