"""Integration tests for AsyncBackendSyncAdapter against Azurite.

Requires:  docker compose -f infra/docker-compose.yml up -d
Run with:  pytest -m integration tests/aio/test_async_to_sync_adapter_integration.py -s

These tests exercise the full sync Backend API contract through the adapter
backed by a live AsyncAzureBackend.  Every test is traced to its spec ID via
@pytest.mark.spec; invariants are ASYNC-080..093 in
sdd/specs/029-async-store-backend-api.md § AsyncBackendSyncAdapter.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import AZURITE_CONN_STR, _azurite_available

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store import Store

pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")

pytestmark = pytest.mark.skipif(
    not _azurite_available(),
    reason="Azurite not reachable or azure SDK not installed",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def azurite_adapter_store() -> Iterator[Store]:
    """Store backed by AsyncAzureBackend wrapped in AsyncBackendSyncAdapter.

    Creates a fresh Azurite container, yields a Store, cleans up after all
    tests in the module complete.
    """
    from azure.storage.blob import BlobServiceClient

    from remote_store import Store
    from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
    from remote_store.aio.backends._azure import AsyncAzureBackend

    tag = uuid.uuid4().hex[:8]
    container = f"adapter-integ-{tag}"

    service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
    service.create_container(container)

    async_backend = AsyncAzureBackend(container=container, connection_string=AZURITE_CONN_STR)
    adapter = AsyncBackendSyncAdapter(async_backend)
    store = Store(backend=adapter)

    yield store

    store.close()
    service.delete_container(container)
    service.close()


# ---------------------------------------------------------------------------
# Lifecycle (ASYNC-088, ASYNC-092)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterLifecycleAzurite:
    """close() drains cleanly; sync context-manager protocol works."""

    @pytest.mark.spec("ASYNC-092")
    def test_context_manager_enter_returns_self(self) -> None:
        """__enter__ returns the adapter; __exit__ calls close()."""
        from azure.storage.blob import BlobServiceClient

        from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
        from remote_store.aio.backends._azure import AsyncAzureBackend

        tag = uuid.uuid4().hex[:8]
        container = f"adapter-cm-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        try:
            async_backend = AsyncAzureBackend(container=container, connection_string=AZURITE_CONN_STR)
            with AsyncBackendSyncAdapter(async_backend) as adapter:
                assert adapter is not None
                assert adapter.name == "async-azure"
            # After __exit__, adapter should be closed.
            with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
                adapter.exists("anything.txt")
        finally:
            service.delete_container(container)
            service.close()

    @pytest.mark.spec("ASYNC-088")
    def test_close_is_idempotent(self, azurite_adapter_store: Store) -> None:
        """close() on the underlying adapter must not raise on repeat calls.

        We call store.close() once, then adapter.close() again directly.
        The second call must be a no-op.  The adapter must be in closed state
        after both calls (behavioral check via ASYNC-083).
        """
        from azure.storage.blob import BlobServiceClient

        from remote_store import Store
        from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
        from remote_store.aio.backends._azure import AsyncAzureBackend

        tag = uuid.uuid4().hex[:8]
        container = f"adapter-idem-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        try:
            async_backend = AsyncAzureBackend(container=container, connection_string=AZURITE_CONN_STR)
            adapter = AsyncBackendSyncAdapter(async_backend)
            store = Store(backend=adapter)
            store.close()  # first close
            adapter.close()  # second close -- must not raise
            # Behavioral check: adapter is closed and stays closed (ASYNC-083).
            with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
                adapter.exists("probe.txt")
        finally:
            service.delete_container(container)
            service.close()


# ---------------------------------------------------------------------------
# Capabilities (ASYNC-084)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterCapabilitiesAzurite:
    """ASYNC-084: SEEKABLE_READ masked; LAZY_READ and ATOMIC_WRITE preserved."""

    @pytest.mark.spec("ASYNC-084")
    @pytest.mark.parametrize(
        ("capability_name", "expected"),
        [
            ("SEEKABLE_READ", False),  # masked by adapter (async stream is forward-only)
            ("LAZY_READ", True),  # preserved (single-chunk in-flight, ASYNC-080)
            ("ATOMIC_WRITE", True),  # preserved verbatim from AsyncAzureBackend
        ],
    )
    def test_capability_translation(self, azurite_adapter_store: Store, capability_name: str, expected: bool) -> None:
        from remote_store._capabilities import Capability

        assert azurite_adapter_store.supports(Capability[capability_name]) is expected


# ---------------------------------------------------------------------------
# Core I/O round-trip (ASYNC-080, ASYNC-081, ASYNC-087)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterCoreIOAzurite:
    """write + read round-trips, streaming behaviour, error mapping."""

    @pytest.mark.spec("ASYNC-087")
    def test_write_read_bytes_roundtrip(self, azurite_adapter_store: Store) -> None:
        path = f"roundtrip-{uuid.uuid4().hex[:6]}.bin"
        payload = b"hello azurite adapter"
        azurite_adapter_store.write(path, payload)
        assert azurite_adapter_store.read_bytes(path) == payload

    @pytest.mark.spec("ASYNC-081")
    def test_read_returns_forward_only_binary_io(self, azurite_adapter_store: Store) -> None:
        """read() must return a BinaryIO whose seekable() is False (ASYNC-081)."""
        path = f"seekable-{uuid.uuid4().hex[:6]}.bin"
        azurite_adapter_store.write(path, b"data")
        stream = azurite_adapter_store.read(path)
        try:
            assert stream.readable() is True
            assert stream.seekable() is False
        finally:
            stream.close()

    @pytest.mark.spec("ASYNC-080")
    def test_read_streams_in_multiple_chunks(self, azurite_adapter_store: Store) -> None:
        """A file larger than one chunk must be read in > 1 iteration (ASYNC-080).

        Uses 600 KiB so that the 65536-byte chunk size yields >= 9 iterations.
        """
        path = f"streaming-{uuid.uuid4().hex[:6]}.bin"
        payload = b"x" * (600 * 1024)  # 600 KiB
        azurite_adapter_store.write(path, payload)

        stream = azurite_adapter_store.read(path)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            stream.close()

        assert len(chunks) > 1, f"Expected multiple chunks; got {len(chunks)}"
        assert b"".join(chunks) == payload

    @pytest.mark.spec("ASYNC-087")
    def test_exists_true_and_false(self, azurite_adapter_store: Store) -> None:
        path = f"exists-{uuid.uuid4().hex[:6]}.txt"
        assert azurite_adapter_store.exists(path) is False
        azurite_adapter_store.write(path, b"x")
        assert azurite_adapter_store.exists(path) is True

    @pytest.mark.spec("ASYNC-087")
    def test_delete(self, azurite_adapter_store: Store) -> None:
        path = f"delete-{uuid.uuid4().hex[:6]}.txt"
        azurite_adapter_store.write(path, b"bye")
        azurite_adapter_store.delete(path)
        assert azurite_adapter_store.exists(path) is False

    @pytest.mark.spec("ASYNC-087")
    def test_move(self, azurite_adapter_store: Store) -> None:
        src = f"move-src-{uuid.uuid4().hex[:6]}.txt"
        dst = f"move-dst-{uuid.uuid4().hex[:6]}.txt"
        azurite_adapter_store.write(src, b"moved-content")
        azurite_adapter_store.move(src, dst)
        assert azurite_adapter_store.exists(src) is False
        assert azurite_adapter_store.read_bytes(dst) == b"moved-content"

    @pytest.mark.spec("ASYNC-087")
    def test_copy(self, azurite_adapter_store: Store) -> None:
        src = f"copy-src-{uuid.uuid4().hex[:6]}.txt"
        dst = f"copy-dst-{uuid.uuid4().hex[:6]}.txt"
        azurite_adapter_store.write(src, b"copy-content")
        azurite_adapter_store.copy(src, dst)
        assert azurite_adapter_store.read_bytes(src) == b"copy-content"
        assert azurite_adapter_store.read_bytes(dst) == b"copy-content"


# ---------------------------------------------------------------------------
# Atomic write (ASYNC-085)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterAtomicWriteAzurite:
    """ASYNC-085: open_atomic commits on clean exit."""

    @pytest.mark.spec("ASYNC-085")
    def test_open_atomic_commits(self, azurite_adapter_store: Store) -> None:
        path = f"atomic-{uuid.uuid4().hex[:6]}.bin"
        payload = b"atomic payload"
        with azurite_adapter_store.open_atomic(path) as fh:
            fh.write(payload)
        assert azurite_adapter_store.read_bytes(path) == payload

    @pytest.mark.spec("ASYNC-085")
    def test_open_atomic_aborts_on_exception(self, azurite_adapter_store: Store) -> None:
        path = f"atomic-abort-{uuid.uuid4().hex[:6]}.bin"

        def _do_abort() -> None:
            with azurite_adapter_store.open_atomic(path) as fh:
                fh.write(b"partial")
                raise ValueError("intentional")

        with pytest.raises(ValueError, match="intentional"):
            _do_abort()
        assert azurite_adapter_store.exists(path) is False


# ---------------------------------------------------------------------------
# Listing (ASYNC-032, ASYNC-087)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterListingAzurite:
    """list_files, list_folders, iter_children produce correct results."""

    @pytest.fixture
    def populated_prefix(self, azurite_adapter_store: Store) -> str:
        """Write a small tree into the shared store; return the unique prefix."""
        prefix = f"list-{uuid.uuid4().hex[:6]}"
        azurite_adapter_store.write(f"{prefix}/a.txt", b"alpha")
        azurite_adapter_store.write(f"{prefix}/b.txt", b"bravo")
        azurite_adapter_store.write(f"{prefix}/sub/c.txt", b"charlie")
        return prefix

    @pytest.mark.spec("ASYNC-032")
    def test_list_files_recursive(self, azurite_adapter_store: Store, populated_prefix: str) -> None:
        files = list(azurite_adapter_store.list_files(populated_prefix, recursive=True))
        names = {f.name for f in files}
        assert "a.txt" in names
        assert "b.txt" in names
        assert "c.txt" in names

    @pytest.mark.spec("ASYNC-032")
    def test_list_folders(self, azurite_adapter_store: Store, populated_prefix: str) -> None:
        folders = list(azurite_adapter_store.list_folders(populated_prefix))
        names = {f.name for f in folders}
        assert "sub" in names


# ---------------------------------------------------------------------------
# Error mapping (ASYNC-087)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterErrorMappingAzurite:
    """Remote-store error types propagate verbatim through the adapter."""

    @pytest.mark.spec("ASYNC-087")
    def test_not_found_on_missing_path(self, azurite_adapter_store: Store) -> None:
        from remote_store._errors import NotFound

        missing = f"ghost-{uuid.uuid4().hex}.txt"
        with pytest.raises(NotFound, match="ghost-"):
            azurite_adapter_store.read_bytes(missing)

    @pytest.mark.spec("ASYNC-087")
    def test_already_exists_without_overwrite(self, azurite_adapter_store: Store) -> None:
        from remote_store._errors import AlreadyExists

        path = f"dup-{uuid.uuid4().hex[:6]}.txt"
        azurite_adapter_store.write(path, b"first")
        with pytest.raises(AlreadyExists, match="dup-"):
            azurite_adapter_store.write(path, b"second")


# ---------------------------------------------------------------------------
# Health check (ASYNC-093)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterHealthCheckAzurite:
    """ASYNC-093: check_health() returns without error against live Azurite."""

    @pytest.mark.spec("ASYNC-093")
    def test_check_health_succeeds(self, azurite_adapter_store: Store) -> None:
        """check_health() must not raise; store must remain operational afterwards.

        Invoked via Store.ping() which calls self._backend.check_health().
        """
        azurite_adapter_store.ping()
        # Verify the store is still operational: a nonexistent path returns False.
        assert azurite_adapter_store.exists(f"post-health-{uuid.uuid4().hex[:6]}.txt") is False


# ---------------------------------------------------------------------------
# Closed-adapter reuse (ASYNC-083)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterClosedReuseAzurite:
    """ASYNC-083: any method call after close() raises RuntimeError."""

    @pytest.mark.spec("ASYNC-083")
    def test_raises_on_use_after_close(self) -> None:
        from azure.storage.blob import BlobServiceClient

        from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
        from remote_store.aio.backends._azure import AsyncAzureBackend

        tag = uuid.uuid4().hex[:8]
        container = f"adapter-closed-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        try:
            async_backend = AsyncAzureBackend(container=container, connection_string=AZURITE_CONN_STR)
            adapter = AsyncBackendSyncAdapter(async_backend)
            adapter.close()
            with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
                adapter.exists("anything.txt")
        finally:
            service.delete_container(container)
            service.close()
