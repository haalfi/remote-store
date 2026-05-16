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
tests in ``tests.aio.test_async_azure_live``. That file carries a module-level
``skipif(not _azurite_reachable())`` guard; real ADLS Gen2 tests must not be blocked
by Azurite availability.

Spec: AZ-014 (``write_atomic`` atomic rename), BE-021 (directory-path guard),
WR-001a (WriteResult native fields), WR-004 (source matches capability),
WR-012 (metadata echo), WR-013 (metadata round-trip), AZ-034 (ETag normalisation).

Gating
------

Two skip-gates (both required to run):

1. ``pytest.mark.live`` at module level. Default ``addopts`` is ``-m 'not live'``,
   so plain ``hatch run test`` skips the file entirely.
2. ``RS_TEST_LIVE_HNS=1`` env var — same gate as
   ``tests.backends.test_azure_live_hns``.

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

from remote_store._errors import AlreadyExists, InvalidPath, NotFound  # noqa: E402
from remote_store._models import FileInfo  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

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

    Mirrors the same helper in ``tests.backends.test_azure_live_hns``.
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


@pytest.fixture(scope="module")
def live_hns_env(_live_hns_setup: tuple[str, str, str, str]) -> tuple[str, str]:
    """Module-scoped accessor for the validated ``(connection_string, filesystem)``.

    Sibling of the sync ``live_hns_env`` in ``tests.backends.test_azure_live_hns``.
    Centralises env-var lookup so individual tests do not re-read ``os.environ``
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
        # Note: the async path lacks the BUG-173 try/except fallback the sync path
        # carries, so a post-rename read failure propagates as a write error rather
        # than returning etag=None.  This assertion therefore exercises the only path
        # the async backend supports.  Tracked as BUG-196 in sdd/BACKLOG.md.
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

    The async ``write_atomic`` HNS path attaches metadata to the temp file at
    creation — via ``upload_data(metadata=)`` for ``bytes`` payloads, via
    ``create_file(metadata=)`` for ``AsyncIterator`` payloads (BUG-194) — then
    renames. Mocks verify the kwarg reaches the right SDK call; only a real account
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
    ``tests.backends.test_azure_live_hns``. Both async methods carry the same
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
        operation: Callable[[AsyncAzureBackend, str], Awaitable[None]],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await operation(backend, dirpath)


# ---------------------------------------------------------------------------
# BE-010 — content round-trip and overwrite on the async HNS write_atomic path
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsContentRoundTrip:
    """Bytes written via async write_atomic must survive the HNS temp-upload + rename_file commit.

    Async companion to ``TestAzureLiveHnsContentRoundTrip``. After the BUG-194 fix,
    the async HNS path routes ``bytes`` directly to ``upload_data`` (length resolved
    via ``len()``) and routes ``AsyncIterator`` payloads through ``create_file`` +
    per-chunk ``append_data`` + ``flush_data`` — neither path materialises the
    payload to a single buffer (SIO-003, ASYNC-021 preserved). This round-trip
    confirms the bytes payload reaches the final blob after the DFS rename.

    Spec: BE-010 (write_atomic), WR-001a (WriteResult size).
    """

    @pytest.mark.spec("BE-010", "WR-001a")
    async def test_write_atomic_content_survives_hns_rename(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/roundtrip-{uuid.uuid4().hex[:8]}.txt"
        payload = b"roundtrip-" + uuid.uuid4().bytes

        result = await backend.write_atomic(path, payload)

        assert result.size == len(payload)
        assert await backend.read_bytes(path) == payload

    @pytest.mark.spec("BE-010")
    async def test_write_atomic_overwrite_replaces_content(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/overwrite-{uuid.uuid4().hex[:8]}.txt"
        original = b"original-content"
        replacement = b"replaced-content"

        await backend.write_atomic(path, original)
        await backend.write_atomic(path, replacement, overwrite=True)

        assert await backend.read_bytes(path) == replacement

    @pytest.mark.spec("BE-010")
    async def test_write_atomic_overwrite_false_raises_already_exists(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/noover-{uuid.uuid4().hex[:8]}.txt"

        await backend.write_atomic(path, _PAYLOAD)
        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.write_atomic(path, _PAYLOAD, overwrite=False)


# ---------------------------------------------------------------------------
# ASYNC-018 — move uses rename_file on HNS accounts (async path)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsMove:
    """Async ``move`` must use ``rename_file`` on an HNS account for atomic relocation.

    Async companion to ``TestAzureLiveHnsMove``. Only a real account confirms the
    async ``rename_file`` path executes correctly end-to-end.

    Spec: ASYNC-018 (move).
    """

    @pytest.mark.spec("ASYNC-018")
    async def test_move_hns_src_content_reaches_dst(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/move-src-{uid}.txt"
        dst = f"{prefix}/move-dst-{uid}.txt"
        payload = b"move-content-" + uuid.uuid4().bytes

        await backend.write_atomic(src, payload)
        await backend.move(src, dst)

        assert await backend.read_bytes(dst) == payload
        with pytest.raises(NotFound, match="(?i)not found"):
            await backend.read_bytes(src)

    @pytest.mark.spec("ASYNC-018")
    async def test_move_existing_dst_overwrite_false_raises_already_exists(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """Async ``move`` must guard against silent overwrite when ``overwrite=False``."""
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/move-src-exists-{uid}.txt"
        dst = f"{prefix}/move-dst-exists-{uid}.txt"

        await backend.write_atomic(src, b"src")
        await backend.write_atomic(dst, b"dst-original")

        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.move(src, dst)
        # Both blobs must remain unchanged after the failed move.
        assert await backend.read_bytes(dst) == b"dst-original"
        assert await backend.read_bytes(src) == b"src"


# ---------------------------------------------------------------------------
# ASYNC-016 — get_file_info on an HNS directory blob (async path)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsGetFileInfoOnDirectory:
    """Async ``get_file_info`` on an HNS directory blob must raise ``NotFound``.

    Async companion to ``TestAzureLiveHnsGetFileInfoOnDirectory``. Only a real
    account confirms the ``hdi_isfolder`` marker is set by the DataLake service.

    Note: ASYNC-016 specifies ``InvalidPath`` for directory paths, but the current
    implementation raises ``NotFound``. This test documents the actual live behaviour;
    the deviation is tracked as **BUG-195** in ``sdd/BACKLOG.md`` and must be flipped to
    ``InvalidPath`` when that fix lands.

    Spec: ASYNC-016 (get_file_info).
    """

    # BUG-195: marks the spec target, not the current behaviour. ASYNC-016 specifies
    # InvalidPath but the runtime raises NotFound; this test documents the deviation
    # and must be flipped to pytest.raises(InvalidPath) when BUG-195 is fixed.
    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_on_hns_directory_raises_not_found(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        with pytest.raises(NotFound, match="(?i)not found"):
            await backend.get_file_info(dirpath)


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
# BE-013 / BE-014 / BE-018 — NotFound on real HNS account (read / delete / move)
# ---------------------------------------------------------------------------


async def _async_read_bytes_missing(backend: AsyncAzureBackend, prefix: str) -> None:
    await backend.read_bytes(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


async def _async_get_file_info_missing(backend: AsyncAzureBackend, prefix: str) -> None:
    await backend.get_file_info(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


async def _async_delete_missing(backend: AsyncAzureBackend, prefix: str) -> None:
    await backend.delete(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


async def _async_move_missing_src(backend: AsyncAzureBackend, prefix: str) -> None:
    uid = uuid.uuid4().hex[:8]
    await backend.move(f"{prefix}/missing-src-{uid}.txt", f"{prefix}/missing-dst-{uid}.txt")


class TestAsyncLiveHnsNotFound:
    """Operations on missing HNS paths must raise ``NotFound`` on a real account.

    The most common error path in real usage. Mock suites stub
    ``ResourceNotFoundError`` directly; only a real account confirms the SDK
    actually raises it for the shapes the production code probes (blob client
    vs file client paths can differ).

    Spec: ASYNC-016 (read / get_file_info), BE-014 (delete), ASYNC-018 (move).
    """

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(_async_read_bytes_missing, id="read_bytes", marks=pytest.mark.spec("ASYNC-016")),
            pytest.param(_async_get_file_info_missing, id="get_file_info", marks=pytest.mark.spec("ASYNC-016")),
            pytest.param(_async_delete_missing, id="delete", marks=pytest.mark.spec("BE-014")),
            pytest.param(_async_move_missing_src, id="move", marks=pytest.mark.spec("ASYNC-018")),
        ],
    )
    async def test_operation_on_missing_path_raises_not_found(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
        operation: Callable[[AsyncAzureBackend, str], Awaitable[None]],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        with pytest.raises(NotFound, match="(?i)not found"):
            await operation(backend, prefix)

    @pytest.mark.spec("BE-014")
    async def test_delete_missing_with_missing_ok_is_silent(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """``missing_ok=True`` is the contract for idempotent delete; live confirms."""
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        missing = f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt"
        # Returning normally is the assertion: missing_ok=True must not raise.
        result = await backend.delete(missing, missing_ok=True)
        assert result is None


# ---------------------------------------------------------------------------
# ASYNC-015 — exists() on a real HNS account
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsExists:
    """Async ``exists`` must return True for present files and HNS directories, False for missing.

    Async companion to ``TestAzureLiveHnsExists``. The HNS branch falls back from the
    blob client to a DataLake directory probe; only a real account exercises the
    fallback chain on actual HNS resources.

    Spec: ASYNC-015 (exists).
    """

    @pytest.mark.spec("ASYNC-015")
    async def test_exists_returns_true_for_present_file(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/exists-{uuid.uuid4().hex[:8]}.txt"
        await backend.write_atomic(path, _PAYLOAD)
        assert await backend.exists(path) is True

    @pytest.mark.spec("ASYNC-015")
    async def test_exists_returns_false_for_missing_path(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        missing = f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt"
        assert await backend.exists(missing) is False

    @pytest.mark.spec("ASYNC-015")
    async def test_exists_returns_true_for_hns_directory(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        """The DataLake directory-probe fallback fires only on a real HNS account."""
        backend, dirpath = async_live_hns_backend
        assert await backend.exists(dirpath) is True


# ---------------------------------------------------------------------------
# ASYNC-022 — list_files on an HNS prefix (recursive vs non-recursive)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsListFiles:
    """Async ``list_files`` traverses HNS prefixes via ``DataLakeFileSystemClient.get_paths``.

    Async companion to ``TestAzureLiveHnsListFiles``. Non-recursive must yield only
    immediate files; recursive must include nested files.

    Spec: ASYNC-022 (list_files).
    """

    @pytest.mark.spec("ASYNC-022")
    async def test_list_files_non_recursive_yields_immediate_files_only(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/listroot-{uuid.uuid4().hex[:8]}"
        await backend.write_atomic(f"{sub}/a.txt", b"a")
        await backend.write_atomic(f"{sub}/b.txt", b"b")
        await backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files = sorted([str(fi.path) async for fi in backend.list_files(sub)])
        assert files == [f"{sub}/a.txt", f"{sub}/b.txt"]

    @pytest.mark.spec("ASYNC-022")
    async def test_list_files_recursive_yields_nested_files(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/listrec-{uuid.uuid4().hex[:8]}"
        await backend.write_atomic(f"{sub}/a.txt", b"a")
        await backend.write_atomic(f"{sub}/b.txt", b"b")
        await backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files = sorted([str(fi.path) async for fi in backend.list_files(sub, recursive=True)])
        assert files == [f"{sub}/a.txt", f"{sub}/b.txt", f"{sub}/nested/c.txt"]


# ---------------------------------------------------------------------------
# ASYNC-024 — iter_children on an HNS prefix yields both files and folders
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsIterChildren:
    """Async ``iter_children`` yields ``FileInfo`` for files and ``FolderEntry`` for subdirs.

    Async companion to ``TestAzureLiveHnsIterChildren``. The HNS branch uses
    ``get_paths(recursive=False)`` and routes ``is_directory`` entries to
    ``FolderEntry``; only a real account confirms the marker shape.

    Spec: ASYNC-024 (iter_children).
    """

    @pytest.mark.spec("ASYNC-024")
    async def test_iter_children_yields_files_and_folders(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/iterchild-{uuid.uuid4().hex[:8]}"
        await backend.write_atomic(f"{sub}/a.txt", b"a")
        await backend.write_atomic(f"{sub}/b.txt", b"b")
        await backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files: list[str] = []
        folders: list[str] = []
        async for entry in backend.iter_children(sub):
            if isinstance(entry, FileInfo):
                files.append(str(entry.path))
            else:
                folders.append(str(entry.path))

        assert sorted(files) == [f"{sub}/a.txt", f"{sub}/b.txt"]
        assert sorted(folders) == [f"{sub}/nested"]


# ---------------------------------------------------------------------------
# BE-014 — delete happy path on a real HNS account (async)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsDelete:
    """Async ``delete`` must remove the file from the account.

    Async companion to ``TestAzureLiveHnsDelete``. Mocks confirm the SDK call;
    only a real account confirms the file actually vanishes.

    Spec: BE-014 (delete).
    """

    @pytest.mark.spec("BE-014")
    async def test_delete_removes_file_from_account(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/delete-{uuid.uuid4().hex[:8]}.txt"
        await backend.write_atomic(path, _PAYLOAD)
        assert await backend.exists(path) is True

        await backend.delete(path)

        assert await backend.exists(path) is False
        with pytest.raises(NotFound, match="(?i)not found"):
            await backend.read_bytes(path)


# ---------------------------------------------------------------------------
# BE-019 — copy on a real HNS account (async)
# ---------------------------------------------------------------------------


class TestAsyncLiveHnsCopy:
    """Async ``copy`` must create an independent blob; respect overwrite semantics.

    Async companion to ``TestAzureLiveHnsCopy``.

    Spec: BE-019 (copy).
    """

    @pytest.mark.spec("BE-019")
    async def test_copy_creates_independent_blob(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-{uid}.txt"
        dst = f"{prefix}/copy-dst-{uid}.txt"
        payload = b"copy-content-" + uuid.uuid4().bytes

        await backend.write_atomic(src, payload)
        await backend.copy(src, dst)

        assert await backend.read_bytes(src) == payload
        assert await backend.read_bytes(dst) == payload

    @pytest.mark.spec("BE-019")
    async def test_copy_overwrite_false_existing_dst_raises_already_exists(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-exists-{uid}.txt"
        dst = f"{prefix}/copy-dst-exists-{uid}.txt"

        await backend.write_atomic(src, b"src")
        await backend.write_atomic(dst, b"dst-original")

        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.copy(src, dst)
        assert await backend.read_bytes(dst) == b"dst-original"

    @pytest.mark.spec("BE-019")
    async def test_copy_overwrite_true_replaces_dst(
        self,
        async_live_hns_backend: tuple[AsyncAzureBackend, str],
    ) -> None:
        backend, dirpath = async_live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-over-{uid}.txt"
        dst = f"{prefix}/copy-dst-over-{uid}.txt"

        await backend.write_atomic(src, b"new-content")
        await backend.write_atomic(dst, b"old-content")

        await backend.copy(src, dst, overwrite=True)
        assert await backend.read_bytes(dst) == b"new-content"


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
