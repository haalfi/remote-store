"""Live ADLS Gen2 (HNS) integration tests for ``AsyncAzureBackend``.

Covers async HNS semantics that the conformance suite against
``azure_live_async`` cannot reach AND that differ from the sync sibling
in ``tests/backends/azure/test_live_hns.py``. Async-only KEEPs:

* **WriteResult post-rename etag normalisation cross-check** on the async
  SDK paths. Async ``write_atomic`` reads etag via ``get_file_properties``
  on its own ``DataLakeFileClient`` and ``get_blob_properties`` on its
  own ``BlobClient``; the sync sibling exercises the parallel sync SDK
  pair. Normalisation drift between the two reads is per-backend and only
  surfaces against a real account. Both tests skip on the BUG-173 /
  BUG-196 transient post-rename-read fallback (``etag=None``) so the
  "fully native" contract is audibly bypassed rather than silently
  passed (``TestAsyncLiveHnsWriteResult``).

* **DFS append protocol on async-iterator payloads (BUG-194).** The async
  HNS path drives ``create_file`` → per-chunk ``append_data(offset)`` →
  ``flush_data(total)`` for ``AsyncIterator[bytes]`` payloads. The bug
  only manifested live; sync has no ``AsyncIterator`` writer entry point
  (``TestAsyncLiveHnsWriteAtomicAsyncIterator``).

* **Directory-blob ``hdi_isfolder`` probes** on the async code paths —
  ``write`` / ``write_atomic`` raise ``InvalidPath`` on an HNS directory
  (``TestAsyncLiveHnsDirectoryGuard``); ``get_file_info`` raises
  ``InvalidPath`` (``TestAsyncLiveHnsGetFileInfoOnDirectory``);
  ``is_folder`` / ``is_file`` honour the marker
  (``TestAsyncLiveHnsIsFolderIsFile``, BUG-203); ``read_bytes`` / ``delete``
  raise ``InvalidPath`` without mutating account state
  (``TestAsyncLiveHnsFileApiOnDirectory``, BUG-197 data-loss guard).

* **``get_folder_info("")`` HNS root carve-out** on the async branch
  (``TestAsyncLiveHnsGetFolderInfoRoot``, BUG-213, AZ-024).

* **HNS ``exists`` fallback** on the async branch
  (``TestAsyncLiveHnsExists``).

User-metadata survives ADLS Gen2 ``rename_file`` is a service-side
property that does not differ async vs sync, so one sibling carries it:
the sync conformance ``test_atomic.py::TestWriteResultConformance::test_metadata_round_trips_via_get_file_info``
runs against the real ADLS Gen2 account via the sync ``azure_live``
fixture (the same backing storage as ``azure_live_async``). The
async-iterator-payload metadata assertion lives in
``TestAsyncLiveHnsWriteAtomicAsyncIterator`` because that branch is
async-only and exercises a different SDK call shape.

This file is intentionally **not** co-located with the Azurite-backed async
live tests in ``tests/backends/azure/aio/test_live.py``. That file carries
a module-level ``skipif(not _azurite_reachable())`` guard; real ADLS Gen2
tests must not be blocked by Azurite availability.

Spec: TEST-003 (per-backend deviation tier); BE-021, ASYNC-005, ASYNC-010,
ASYNC-013, ASYNC-015, ASYNC-016, ASYNC-017, AZ-014, AZ-024, AZ-034,
SIO-003, WR-001a, WR-004, WR-012, WR-013.

Gating
------

Two skip-gates (both required to run):

1. ``pytest.mark.live`` at module level. Default ``addopts`` is ``-m 'not live'``,
   so plain ``hatch run test`` skips the file entirely.
2. ``RS_TEST_LIVE_HNS=1`` env var — same gate as
   ``tests/backends/azure/test_live_hns.py``.

Fixture-time precondition (fails loudly, does not skip):

3. ``AZURE_STORAGE_CONNECTION_STRING`` and ``RS_TEST_LIVE_HNS_CONTAINER`` must
   point at a *real* ADLS Gen2 account. ``_require_live_hns_env()`` calls
   ``pytest.fail`` (not ``pytest.skip``) for missing or Azurite-pointing strings —
   a silent skip here would mean "I thought I tested it" but didn't.

Cost discipline
---------------

All tests share one HNS directory provisioned per module via the
``_live_hns_setup`` sync fixture. Each test writes a uuid-suffixed file under the
shared prefix so repeated runs cannot collide. Teardown deletes the entire prefix
on a best-effort basis.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.storage.filedatalake import DataLakeServiceClient  # noqa: E402

from remote_store._errors import InvalidPath  # noqa: E402
from remote_store._path import RemotePath  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402
from tests.backends.fixtures._live_env import (  # noqa: E402
    require_azure_live_connection_string,
    require_azure_live_hns_container,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

_LOG = logging.getLogger(__name__)

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
    """Return ``(connection_string, filesystem)`` or fail loud.

    Both values are validated by the shared ``_live_env`` helpers:
    ``require_azure_live_connection_string`` (presence + Azurite-signature
    rejection) and ``require_azure_live_hns_container``
    (``RS_TEST_LIVE_HNS_CONTAINER`` presence).
    """
    return require_azure_live_connection_string(), require_azure_live_hns_container()


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


@pytest.fixture(scope="module")
def live_hns_env(_live_hns_setup: tuple[str, str, str, str]) -> tuple[str, str]:
    """Module-scoped accessor for the validated ``(connection_string, filesystem)``.

    Sibling of the sync ``live_hns_env`` in
    ``tests/backends/azure/test_live_hns.py``. Centralises env-var lookup
    so individual tests do not re-read ``os.environ``
    directly — direct access bypasses ``_require_live_hns_env``'s fail-loud
    handling and would raise ``KeyError`` on misconfiguration.
    """
    conn, fs_name, _, _ = _live_hns_setup
    return conn, fs_name


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
    backend = AsyncAzureBackend(container=fs_name, hns=True, connection_string=conn)
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
        # WR-001a / AZ-034: on the success path, etag from post-rename
        # get_file_properties must be non-empty, quote-stripped, and lowercased.
        # On a transient post-rename read failure the BUG-196 fallback returns
        # etag=None (rename already committed; WR-001a lists etag as Optional).
        if result.etag is not None:
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
        else:
            # Fallback path — rename committed, post-rename read failed
            # transiently. WR-001a allows etag=None; retrying would raise
            # AlreadyExists. The fallback contract is verified explicitly
            # by mock tests test_write_atomic_hns_get_file_properties_*
            # in tests/backends/azure/aio/test_config.py. Skip rather than
            # silently pass so a fallback run is audible — the method name
            # asserts "fully native" and the rest of that contract is not
            # exercised on this path.
            pytest.skip("transient post-rename read failure; fully-native contract not exercised on fallback path")


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
    ``tests/backends/azure/test_live_hns.py``. Both async methods carry the
    same ``hdi_isfolder`` probe; only a real account confirms the marker is
    set by the
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
        operation: Callable[[AsyncAzureBackend, str], Awaitable[None]],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await operation(backend, dirpath)


# ---------------------------------------------------------------------------
# ASYNC-016 — get_file_info on an HNS directory blob (async path)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsGetFileInfoOnDirectory:
    """Async ``get_file_info`` on an HNS directory blob must raise ``InvalidPath``.

    Async companion to ``TestAzureLiveHnsGetFileInfoOnDirectory``. Only a real
    account confirms the ``hdi_isfolder`` marker is set by the DataLake service.

    Spec: ASYNC-016 (get_file_info), BE-021 (directory-path guard).
    """

    @pytest.mark.spec("ASYNC-016", "BE-021")
    async def test_get_file_info_on_hns_directory_raises_invalid_path(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.get_file_info(dirpath)


class TestAsyncLiveHnsIsFolderIsFile:
    """Async ``is_folder`` / ``is_file`` semantics on a real HNS directory + file.

    Async companion to ``TestAzureLiveHnsIsFolderIsFile``. BUG-203 fixed both
    sync and async ``is_folder`` to inspect ``hdi_isfolder`` metadata instead
    of trusting that ``get_directory_properties()`` succeeded; this class
    proves the marker is actually present on a directory created via
    ``DataLakeServiceClient.create_directory()`` and absent on a regular file
    written via ``write_atomic``.

    Spec: ASYNC-005 (is_folder / is_file).
    """

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder_true_on_hns_directory(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        assert await backend.is_folder(dirpath) is True

    @pytest.mark.spec("ASYNC-005")
    async def test_is_file_false_on_hns_directory(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        assert await backend.is_file(dirpath) is False


# ---------------------------------------------------------------------------
# ASYNC-010 / SIO-003 — write_atomic with AsyncIterator on a real HNS account
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsWriteAtomicAsyncIterator:
    """``write_atomic`` with ``AsyncIterator[bytes]`` payload must succeed on a real HNS account.

    BUG-194 was a streaming bug that only manifested live: ``upload_data`` invoked
    with an async generator caused the SDK's ``get_length()`` to return ``None``,
    which dropped the required ``?position=`` query parameter from ``flush_data``
    and Azure returned ``MissingRequiredQueryParameter``. Azurite tolerated the
    missing parameter so no Azurite-backed test caught it. The shipped fix drives
    the DFS append protocol directly: ``create_file``, then per-chunk
    ``append_data(offset=cumulative)``, then ``flush_data(total)``.

    A mock-level regression guard exists in
    ``tests/aio/test_async_azure.py::test_write_atomic_hns_streams_async_chunks``;
    this live test closes the loop end-to-end against real ADLS Gen2 — the only
    place the original bug surfaced.

    Spec: ASYNC-010 (write_atomic), SIO-003 (streaming contract), WR-001a, WR-012.
    """

    @pytest.mark.spec("ASYNC-010", "SIO-003", "WR-001a")
    async def test_write_atomic_async_iterator_drives_dfs_protocol(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/aiter-{uuid.uuid4().hex[:8]}.txt"
        # Three uneven chunks ensure cumulative-offset arithmetic is exercised
        # (a buggy fix that ignored chunk_len would still pass with one chunk).
        chunks = [b"chunk-one-", b"chunk-two-and-some-extra-", b"final-chunk"]
        expected = b"".join(chunks)

        async def aiter_payload() -> AsyncIterator[bytes]:
            for chunk in chunks:
                yield chunk

        result = await backend.write_atomic(path, aiter_payload())

        # WR-001a: size is the cumulative byte count from the per-chunk loop.
        assert result.size == len(expected)
        assert result.source == "native"
        # The full payload reaches the final blob after rename — confirms
        # create_file → append_data per chunk → flush_data → rename_file all ran.
        assert await backend.read_bytes(path) == expected

    @pytest.mark.spec("ASYNC-010", "WR-012", "WR-013")
    async def test_write_atomic_async_iterator_with_metadata(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """Metadata on the AsyncIterator branch flows through ``create_file(metadata=)``.

        Companion to the unit test
        ``test_write_atomic_hns_async_iterator_metadata_reaches_create_file`` —
        confirms the ``create_file`` metadata kwarg actually persists on the temp
        file and survives ``rename_file`` end-to-end.
        """
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/aiter-meta-{uuid.uuid4().hex[:8]}.txt"
        metadata = {"branch": "async_iterator", "owner": "team-a"}

        async def aiter_payload() -> AsyncIterator[bytes]:
            yield b"hello "
            yield b"world"

        result = await backend.write_atomic(path, aiter_payload(), metadata=metadata)

        # WR-012: WriteResult.metadata echoes the caller's mapping.
        assert result.metadata == metadata
        # WR-013: metadata applied via create_file must survive rename_file.
        fi = await backend.get_file_info(path)
        assert fi.metadata is not None
        assert fi.metadata.get("branch") == "async_iterator"
        assert fi.metadata.get("owner") == "team-a"


# ---------------------------------------------------------------------------
# ASYNC-015 — exists() on a real HNS directory (DataLake probe fallback)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsExists:
    """Async ``exists`` on a real HNS directory — DataLake probe-fallback chain.

    Conformance covers async ``exists`` on regular present / missing files.
    The HNS branch additionally falls back from the blob client to a DataLake
    directory probe; that fallback only fires on a real ADLS Gen2 directory
    blob created via ``DataLakeServiceClient``.

    Spec: ASYNC-015 (exists).
    """

    @pytest.mark.spec("ASYNC-015")
    async def test_exists_returns_true_for_hns_directory(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        assert await backend.exists(dirpath) is True


# ---------------------------------------------------------------------------
# BE-021 — file-API operations on an HNS directory must raise InvalidPath (async)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsFileApiOnDirectory:
    """Async ``read_bytes`` and ``delete`` on HNS directory blobs must raise ``InvalidPath``.

    Async companion to ``TestAzureLiveHnsFileApiOnDirectory``. BE-021 mandates
    that file-API operations on a directory path raise ``InvalidPath``.
    BUG-197 fixed both sync and async paths. These tests are the live
    regression guards for the spec contract.

    Spec: BE-021, ASYNC-013 (read), BE-014 (delete).
    """

    @pytest.mark.spec("BE-021", "ASYNC-013")
    async def test_read_bytes_on_hns_directory_raises_invalid_path(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """BUG-197 fix: read_bytes on an HNS directory must raise ``InvalidPath``."""
        backend, dirpath = async_live_hns_backend
        with pytest.raises(InvalidPath, match="is a directory"):
            await backend.read_bytes(dirpath)

    @pytest.mark.spec("BE-021", "BE-014")
    async def test_delete_on_hns_directory_raises_invalid_path(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
        live_hns_env: tuple[str, str],
    ) -> None:
        """BUG-197 fix: delete on an HNS directory must raise ``InvalidPath``.

        Uses an isolated per-test directory (not the module-shared one) so that
        when the fix is working the directory is NOT deleted and subsequent tests
        are unaffected. A failing test (InvalidPath not raised, directory deleted)
        would still be isolated because the scratch directory is fresh each run.
        """
        backend, dirpath = async_live_hns_backend
        conn, fs_name = live_hns_env
        prefix = dirpath.rsplit("/", 1)[0]
        scratch_dir = f"{prefix}/scratch-dir-{uuid.uuid4().hex[:8]}"
        service = DataLakeServiceClient.from_connection_string(conn)
        try:
            fs_client = service.get_file_system_client(fs_name)
            fs_client.get_directory_client(scratch_dir).create_directory()

            assert await backend.exists(scratch_dir) is True
            with pytest.raises(InvalidPath, match="is a directory"):
                await backend.delete(scratch_dir)
            # Directory must still exist — InvalidPath must have fired before
            # any SDK mutation (BUG-197 data-loss guard).
            assert await backend.exists(scratch_dir) is True
        finally:
            # Best-effort cleanup: delete the scratch directory via the DataLake
            # client (bypasses the file-API guard that prevents backend.delete).
            with contextlib.suppress(Exception):
                fs_client.get_directory_client(scratch_dir).delete_directory()
            service.close()


# ---------------------------------------------------------------------------
# ASYNC-017 — get_folder_info("") on a real HNS account (root-path coverage)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsGetFolderInfoRoot:
    """Async ``get_folder_info("")`` on a real HNS account exercises the root-path call shape.

    Async companion to ``TestAzureLiveHnsGetFolderInfoRoot``. BUG-213 contract
    (post-fix): the async HNS branch skips the per-path
    ``get_directory_client(ap)`` probe when ``ap == ""`` — real ADLS Gen2
    rejects ``get_directory_client("")`` with "Please specify a file system
    name and file path", and the root is always a folder so no marker probe
    is needed. The branch relies on
    ``_fs.get_paths(path="/", recursive=True)`` (the deliberate ``or "/"``
    fallback) to enumerate the root.

    The assertions focus on the API contract (returns a valid ``FolderInfo``
    with non-negative aggregates), not exact counts — the container is shared
    across tests so the count is unpredictable.

    Spec: ASYNC-017 (async get_folder_info postcondition); AZ-024 (HNS root-path carve-out).
    Cassette: new Stage 3 cassette required — record with
    ``RS_TEST_LIVE_HNS=1 hatch run record-azure``.
    """

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_root_returns_valid_folder_info(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """Root async get_folder_info must succeed and return a FolderInfo for path=''.

        Contract under test: ``get_folder_info("")`` against an HNS account
        completes without an SDK exception.  The root-path code path skips
        the per-path ``get_directory_client`` probe (real ADLS Gen2 rejects
        the empty path) and relies on the deliberate ``or "/"`` fallback in
        ``_fs.get_paths`` to enumerate the root.  The live counts vary with
        sibling-test residue and are not contract.
        """
        from remote_store._models import FolderInfo  # noqa: PLC0415 -- intentional late import

        backend, _dirpath = async_live_hns_backend
        info = await backend.get_folder_info("")
        assert isinstance(info, FolderInfo)
        # FolderInfo.path is a RemotePath; the root normalises to RemotePath.ROOT
        # (str form "."), and RemotePath.__eq__ returns NotImplemented for str
        # operands — comparing against "" would always be False.
        assert info.path == RemotePath.ROOT
