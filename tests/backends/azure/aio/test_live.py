"""Live Azurite integration tests for ``AsyncAzureBackend`` (ID-157).

The companion file ``tests/aio/test_async_azure.py`` is mock-only: it covers
method signatures and error-mapping branches but cannot exercise the real
async Azure Blob SDK. This module fills that gap by running against a live
Azurite container so it catches real wire semantics the mocks miss:

- Multi-chunk streaming downloads via the real ``download_blob`` chunker.
- ETag and ``last_modified`` propagation from the SDK upload response into
  ``WriteResult`` (whose values are stripped, lower-cased, and timezone-aware).
- USER_METADATA round-trips through the real Blob metadata header path.
- 404 / 409 / 412 wire responses mapped through ``classify_azure_error``.

**Standalone fixture** (per-test container) rather than a fixture shared
with the sync Azure tests under ``tests/backends/azure/``: the
async API uses ``aclose()`` (coroutine) and async generators, so the
fixture lifecycle and most test bodies cannot converge structurally.
Container setup/teardown reuses the **sync** ``BlobServiceClient`` (via
``azurite_server`` from ``tests/conftest.py``) which avoids spinning up an
async event loop just to provision a container.

Azurite does not emulate Hierarchical Namespace. HNS-specific live tests
(write_atomic temp+rename, metadata survival, directory guard) live in
``tests/backends/azure/aio/test_live_hns.py`` and are gated on
``RS_TEST_LIVE_HNS=1``.
"""

from __future__ import annotations

import base64
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.core.exceptions import HttpResponseError  # noqa: E402
from azure.storage.blob import BlobServiceClient  # noqa: E402
from azure.storage.blob.aio import BlobClient as AsyncBlobClient  # noqa: E402

from remote_store._errors import AlreadyExists, NotFound, PermissionDenied, RemoteStoreError  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402
from remote_store.backends._azure_common import classify_azure_error  # noqa: E402
from tests.conftest import _azurite_reachable  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


pytestmark = [
    pytest.mark.requires_docker,
    pytest.mark.skipif(
        not _azurite_reachable(),
        reason="Azurite not reachable at 127.0.0.1:10000",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _provision_async_backend(
    azurite_server: str,
    *,
    client_options: dict[str, Any] | None = None,
) -> AsyncIterator[AsyncAzureBackend]:
    """Provision a fresh Azurite container + ``AsyncAzureBackend``.

    Centralises the per-test cleanup so the fixture and bespoke tests that
    need custom ``client_options`` (e.g. the streaming chunk-size test) do
    not duplicate the nested-finally teardown. If any cleanup step fails,
    the rest still run.
    """
    container = f"test-az-aio-{uuid.uuid4().hex[:8]}"
    # Sync client for setup/teardown — avoids spinning up an event loop
    # just to create a container.
    service = BlobServiceClient.from_connection_string(azurite_server)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise
    backend = AsyncAzureBackend(
        container=container,
        connection_string=azurite_server,
        client_options=client_options,
    )
    try:
        yield backend
    finally:
        try:
            await backend.aclose()
        finally:
            try:
                service.delete_container(container)
            finally:
                service.close()


@pytest.fixture
async def async_azure_backend(azurite_server: str | None) -> AsyncIterator[AsyncAzureBackend]:
    """Per-test ``AsyncAzureBackend`` against a fresh Azurite container.

    The module-level ``skipif(not _azurite_reachable())`` and
    ``pytest.importorskip`` together guarantee that ``azurite_server`` is
    a non-None connection string whenever this fixture runs.
    """
    assert azurite_server is not None  # noqa: S101 — type-narrowing under the module-level skip
    async with _provision_async_backend(azurite_server) as backend:
        yield backend


# ---------------------------------------------------------------------------
# Read / write round-trip
# ---------------------------------------------------------------------------


class TestAsyncAzureLiveRoundTrip:
    """Real SDK round-trips through the public async API.

    Spec: AZ-021 (``read_bytes()``), AZ-022 (``write()``), AZ-014 (atomic
    write), AZ-023 (``get_file_info()``), AZ-034 (ETag and Content-MD5),
    WR-001a (WriteResult fields).
    """

    @pytest.mark.spec("AZ-022")
    @pytest.mark.spec("AZ-021")
    async def test_write_then_read_bytes(self, async_azure_backend: AsyncAzureBackend) -> None:
        result = await async_azure_backend.write("rt.txt", b"hello async")
        assert result.size == len(b"hello async")
        assert await async_azure_backend.read_bytes("rt.txt") == b"hello async"

    @pytest.mark.spec("AZ-014")
    async def test_write_atomic_then_read_bytes(self, async_azure_backend: AsyncAzureBackend) -> None:
        # Non-HNS: write_atomic delegates to write (PUT is atomic).
        result = await async_azure_backend.write_atomic("atomic.txt", b"atomic-payload")
        assert result.size == len(b"atomic-payload")
        assert await async_azure_backend.read_bytes("atomic.txt") == b"atomic-payload"

    @pytest.mark.spec("AZ-022")
    @pytest.mark.spec("WR-001a")
    async def test_write_etag_non_empty_and_normalised(self, async_azure_backend: AsyncAzureBackend) -> None:
        """ETag from real SDK upload response is stripped and lower-cased."""
        result = await async_azure_backend.write("et.txt", b"data")
        assert isinstance(result.etag, str)
        assert result.etag != ""
        assert '"' not in result.etag
        assert result.etag == result.etag.lower()

    @pytest.mark.spec("AZ-022")
    @pytest.mark.spec("WR-001a")
    async def test_write_last_modified_populated(self, async_azure_backend: AsyncAzureBackend) -> None:
        result = await async_azure_backend.write("lm.txt", b"data")
        assert result.last_modified is not None
        assert result.last_modified.tzinfo is not None

    @pytest.mark.spec("AZ-023")
    @pytest.mark.spec("AZ-034")
    async def test_get_file_info_etag_matches_write(self, async_azure_backend: AsyncAzureBackend) -> None:
        """``WriteResult.etag`` and ``FileInfo.etag`` agree for the same file."""
        wr = await async_azure_backend.write("etmatch.txt", b"data")
        fi = await async_azure_backend.get_file_info("etmatch.txt")
        assert fi.etag is not None
        assert fi.etag == wr.etag


# ---------------------------------------------------------------------------
# Streaming read (multi-chunk download)
# ---------------------------------------------------------------------------


class TestAsyncAzureLiveStreaming:
    """Real ``download_blob().chunks()`` should yield multiple chunks for large blobs.

    Spec: AZ-020 (``read()``), SIO-001 (Streaming Reads).
    """

    @pytest.mark.spec("AZ-020")
    @pytest.mark.spec("SIO-001")
    async def test_read_streams_multiple_chunks(self, azurite_server: str | None) -> None:
        """``download_blob().chunks()`` yields > 1 chunk when the payload exceeds the chunk size.

        The Blob SDK only chunks downloads when payload >
        ``max_single_get_size`` (default 32 MiB). To keep the test fast we
        use a dedicated backend that sets ``max_single_get_size`` /
        ``max_chunk_get_size`` to 256 KiB via ``client_options`` and write
        ~1 MiB. This verifies the async chunk iterator path that the
        mock-only suite cannot reach: the production wiring of
        ``client_options`` reaches the BlobServiceClient kwargs, the
        downloader actually chunks, and the async generator forwards
        every chunk.
        """
        assert azurite_server is not None  # noqa: S101 — type-narrowing under the module-level skip
        chunk_size = 256 * 1024
        async with _provision_async_backend(
            azurite_server,
            client_options={"max_single_get_size": chunk_size, "max_chunk_get_size": chunk_size},
        ) as backend:
            payload = b"x" * (chunk_size * 4 + 1024)  # 4 chunks + tail
            await backend.write("stream.bin", payload)

            chunks: list[bytes] = []
            async for chunk in backend.read("stream.bin"):
                chunks.append(chunk)

            assert b"".join(chunks) == payload
            assert len(chunks) > 1, f"Expected multi-chunk download; got {len(chunks)} chunks"
            # The largest chunk must not exceed the configured download chunk
            # size. This is the assertion that actually defends the chunking
            # claim: if ``client_options`` ever stops reaching the downloader,
            # the SDK falls back to its 32 MiB default and a single-chunk
            # download covers the whole payload.
            assert max(len(c) for c in chunks) <= chunk_size, (
                f"Largest chunk {max(len(c) for c in chunks)} exceeds configured {chunk_size}"
            )

    @pytest.mark.spec("AZ-021")
    async def test_read_bytes_full_payload(self, async_azure_backend: AsyncAzureBackend) -> None:
        """``read_bytes`` returns the full payload regardless of chunking."""
        payload = b"y" * (2 * 1024 * 1024)  # 2 MiB
        await async_azure_backend.write("full.bin", payload)
        got = await async_azure_backend.read_bytes("full.bin")
        assert got == payload


# ---------------------------------------------------------------------------
# Metadata round-trip (USER_METADATA)
# ---------------------------------------------------------------------------


class TestAsyncAzureLiveMetadata:
    """USER_METADATA must survive a real upload + ``get_file_info`` round trip."""

    @pytest.mark.spec("WR-013")
    async def test_write_metadata_round_trips_via_get_file_info(
        self,
        async_azure_backend: AsyncAzureBackend,
    ) -> None:
        await async_azure_backend.write(
            "meta.txt",
            b"data",
            metadata={"env": "prod", "owner": "team-a"},
        )
        fi = await async_azure_backend.get_file_info("meta.txt")
        assert fi.metadata is not None
        assert fi.metadata.get("env") == "prod"
        assert fi.metadata.get("owner") == "team-a"

    @pytest.mark.spec("WR-013")
    async def test_write_atomic_metadata_round_trips(self, async_azure_backend: AsyncAzureBackend) -> None:
        # Non-HNS: write_atomic delegates to write; still verify metadata flow end to end.
        await async_azure_backend.write_atomic(
            "atomic_meta.txt",
            b"data",
            metadata={"env": "stage"},
        )
        fi = await async_azure_backend.get_file_info("atomic_meta.txt")
        assert fi.metadata is not None
        assert fi.metadata.get("env") == "stage"

    @pytest.mark.spec("WR-012")
    @pytest.mark.spec("WR-013")
    async def test_write_no_metadata_yields_empty_or_none_user_metadata(
        self,
        async_azure_backend: AsyncAzureBackend,
    ) -> None:
        """No ``metadata=`` means ``WriteResult.metadata is None`` (WR-012) and
        ``FileInfo.metadata`` round-trips empty/None (WR-013)."""
        wr = await async_azure_backend.write("no_meta.txt", b"data")
        # WR-012: WriteResult.metadata is None when caller passed no metadata.
        assert wr.metadata is None
        fi = await async_azure_backend.get_file_info("no_meta.txt")
        # WR-013: round-trip yields no user metadata. Backend strips internal
        # ``hdi_isfolder`` and returns ``None`` if nothing else remains.
        assert not fi.metadata


# ---------------------------------------------------------------------------
# Error mapping against real Azure responses
# ---------------------------------------------------------------------------


class TestAsyncAzureLiveErrorMapping:
    """Real 404 / 409 / 412 responses should map to remote_store error types.

    Spec: ASYNC-024 (async backend error mapping). 404 ↦ NotFound (ERR-002),
    409 ↦ AlreadyExists (ERR-003), 412 ↦ ``RemoteStoreError`` (no specific
    subtype declared today; see ``classify_azure_error``).
    """

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-002")
    async def test_read_bytes_missing_raises_not_found(self, async_azure_backend: AsyncAzureBackend) -> None:
        with pytest.raises(NotFound, match="ghost"):
            await async_azure_backend.read_bytes(f"ghost-{uuid.uuid4().hex}.txt")

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-002")
    async def test_read_iter_missing_raises_not_found(self, async_azure_backend: AsyncAzureBackend) -> None:
        """``read()`` async generator on a missing key raises ``NotFound``.

        ``read()`` uses a bare try/except wrapping ``classify_azure_error``
        directly (see ``backends/_azure.py:read``) — wire-distinct from the
        ``_errors()`` async context manager covered by ``read_bytes`` /
        ``get_file_info`` / ``delete``. Without this test, a regression in
        the streaming-iterator's classifier branch would slip past the
        mock suite (which can't reach the real SDK 404 path).
        """
        with pytest.raises(NotFound, match="ghost"):
            async for _ in async_azure_backend.read(f"ghost-{uuid.uuid4().hex}.txt"):
                pass

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-002")
    async def test_get_file_info_missing_raises_not_found(self, async_azure_backend: AsyncAzureBackend) -> None:
        with pytest.raises(NotFound, match="ghost"):
            await async_azure_backend.get_file_info(f"ghost-{uuid.uuid4().hex}.txt")

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-002")
    async def test_delete_missing_raises_not_found(self, async_azure_backend: AsyncAzureBackend) -> None:
        with pytest.raises(NotFound, match="ghost"):
            await async_azure_backend.delete(f"ghost-{uuid.uuid4().hex}.txt")

    @pytest.mark.spec("ASYNC-024")
    async def test_delete_missing_ok_swallows_not_found(self, async_azure_backend: AsyncAzureBackend) -> None:
        path = f"ghost-{uuid.uuid4().hex}.txt"
        await async_azure_backend.delete(path, missing_ok=True)
        assert await async_azure_backend.exists(path) is False

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-003")
    async def test_write_overwrite_false_raises_already_exists(
        self,
        async_azure_backend: AsyncAzureBackend,
    ) -> None:
        await async_azure_backend.write("dup.txt", b"first")
        with pytest.raises(AlreadyExists, match="dup"):
            await async_azure_backend.write("dup.txt", b"second")

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ERR-003")
    async def test_write_atomic_overwrite_false_raises_already_exists(
        self,
        async_azure_backend: AsyncAzureBackend,
    ) -> None:
        await async_azure_backend.write_atomic("dup_atomic.txt", b"first")
        with pytest.raises(AlreadyExists, match="dup_atomic"):
            await async_azure_backend.write_atomic("dup_atomic.txt", b"second")

    async def test_if_match_precondition_failure_maps_to_remote_store_error(
        self,
        async_azure_backend: AsyncAzureBackend,
        azurite_server: str | None,
    ) -> None:
        """A real wire 412 (If-Match precondition failure) is classified by ``classify_azure_error``.

        Wire-level coverage of the pure ``classify_azure_error`` function on
        a 412 produced by the real Azure SDK over the network — the path
        mocks cannot reproduce because they fabricate ``status_code`` rather
        than letting the SDK set it from the response. Because the public
        ``AsyncAzureBackend`` API does not expose ``if_match``, the test
        drives the precondition through an independent async ``BlobClient``
        constructed from the same connection string. **This is not coverage
        of ASYNC-024**: the backend's ``_errors()`` context manager is not
        entered here. ASYNC-024 is exercised by the sibling 404/409 tests
        in this class. The raw, unstripped ETag from the seed write's
        ``get_blob_properties()`` is used to avoid a subtle real-Azure
        brittleness — ``FileInfo.etag`` is lower-cased by
        ``props_to_fileinfo`` so re-quoting it can fail to match the
        original wire form on case-sensitive servers.
        """
        assert azurite_server is not None  # noqa: S101 — type-narrowing under the module-level skip

        # Use the public ResolutionPlan to discover the container name
        # rather than reaching for a private attribute.
        container = async_azure_backend.resolve("preset.txt").details["container"]
        bc = AsyncBlobClient.from_connection_string(azurite_server, container_name=container, blob_name="preset.txt")
        try:
            # Seed a blob via the public async API, then capture the raw
            # (unstripped, original-case) ETag from get_blob_properties so
            # the If-Match value matches the wire form exactly.
            await async_azure_backend.write("preset.txt", b"v1", overwrite=True)
            v1_props = await bc.get_blob_properties()
            stale_etag = v1_props.etag
            assert isinstance(stale_etag, str), f"Expected str ETag from SDK, got {type(stale_etag).__name__}"
            assert stale_etag.startswith('"'), f"Expected raw quoted ETag from SDK, got {stale_etag!r}"
            assert stale_etag.endswith('"'), f"Expected raw quoted ETag from SDK, got {stale_etag!r}"
            # Overwrite to invalidate v1's ETag.
            await async_azure_backend.write("preset.txt", b"v2", overwrite=True)
            # ResourceModifiedError ⊂ HttpResponseError; the precision check
            # is the status_code assertion below, so the base class suffices.
            with pytest.raises(HttpResponseError) as exc_info:
                await bc.upload_blob(b"v3", overwrite=True, if_match=stale_etag)
        finally:
            await bc.close()
        # The pure classifier the backend would use on this wire response
        # must produce a RemoteStoreError with backend identity preserved.
        mapped = classify_azure_error(exc_info.value, "preset.txt", async_azure_backend.name)
        assert isinstance(mapped, RemoteStoreError)
        assert mapped.backend == "async-azure"
        assert getattr(exc_info.value, "status_code", None) == 412

    @pytest.mark.spec("ASYNC-024")
    async def test_bad_signature_maps_to_permission_denied(
        self,
        async_azure_backend: AsyncAzureBackend,
        azurite_server: str | None,
    ) -> None:
        """A real wire 403 (bad shared-key signature) maps to ``PermissionDenied`` (BUG-222).

        Azurite surfaces a wrong account key as a **bare**
        ``HttpResponseError(status=403)`` (``AuthenticationFailed``), not a
        ``ClientAuthenticationError`` — which is real Azure's shape, covered
        by the Stage-3 sibling in ``test_live_auth.py``. This exercises the
        ``status_code == 403`` branch of ``classify_azure_error`` against a
        genuine wire response the mock suite fabricates rather than produces.
        A bad key is reached by swapping the ``AccountKey`` segment of the
        Azurite connection string for a well-formed-but-wrong value.
        """
        assert azurite_server is not None  # noqa: S101 — type-narrowing under the module-level skip
        container = async_azure_backend.resolve("probe.txt").details["container"]
        bad_conn = ";".join(
            "AccountKey=" + base64.b64encode(b"wrong-key-padding-wrong-key-padding-xxxx").decode()
            if seg.startswith("AccountKey=")
            else seg
            for seg in azurite_server.split(";")
        )
        bc = AsyncBlobClient.from_connection_string(bad_conn, container_name=container, blob_name="probe.txt")
        try:
            with pytest.raises(HttpResponseError) as exc_info:
                await bc.download_blob()
        finally:
            await bc.close()
        assert getattr(exc_info.value, "status_code", None) == 403
        mapped = classify_azure_error(exc_info.value, "probe.txt", "async-azure")
        assert isinstance(mapped, PermissionDenied)
        assert mapped.backend == "async-azure"
