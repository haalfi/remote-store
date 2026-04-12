"""Tests for SyncBackendAdapter -- derived from sdd/specs/029-async-store-backend-api.md."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderEntry
from remote_store.aio._sync_adapter import SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend


def _make_populated_adapter() -> tuple[SyncBackendAdapter, MemoryBackend]:
    """Create an adapter with pre-populated data."""
    backend = MemoryBackend()
    backend.write("a.txt", b"alpha")
    backend.write("b.txt", b"bravo")
    backend.write("sub/c.txt", b"charlie")
    return SyncBackendAdapter(backend), backend


class TestSyncAdapterConstruction:
    """ASYNC-030: SyncBackendAdapter wraps a Backend."""

    @pytest.mark.spec("ASYNC-030")
    def test_wraps_sync_backend(self) -> None:
        backend = MemoryBackend()
        adapter = SyncBackendAdapter(backend)
        assert adapter.name == "memory"

    @pytest.mark.spec("ASYNC-030")
    def test_is_async_backend_subclass(self) -> None:
        from remote_store.aio._async_backend import AsyncBackend

        adapter = SyncBackendAdapter(MemoryBackend())
        assert isinstance(adapter, AsyncBackend)
        assert adapter.name == "memory"


class TestSyncAdapterPropertyPassthrough:
    """ASYNC-034: name and capabilities forwarded without threading."""

    @pytest.mark.spec("ASYNC-034")
    def test_name_forwarded(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        assert adapter.name == "memory"

    @pytest.mark.spec("ASYNC-034")
    def test_capabilities_forwarded(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        assert adapter.capabilities.supports(Capability.READ)
        assert adapter.capabilities.supports(Capability.WRITE)
        assert adapter.capabilities.supports(Capability.LIST)


class TestSyncAdapterIODelegation:
    """ASYNC-031: I/O methods delegate via to_thread."""

    @pytest.mark.spec("ASYNC-031")
    async def test_exists_true(self) -> None:
        adapter, _ = _make_populated_adapter()
        assert await adapter.exists("a.txt") is True

    @pytest.mark.spec("ASYNC-031")
    async def test_exists_false(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        assert await adapter.exists("nope.txt") is False

    @pytest.mark.spec("ASYNC-031")
    async def test_is_file(self) -> None:
        adapter, _ = _make_populated_adapter()
        assert await adapter.is_file("a.txt") is True
        assert await adapter.is_file("sub") is False

    @pytest.mark.spec("ASYNC-031")
    async def test_is_folder(self) -> None:
        adapter, _ = _make_populated_adapter()
        assert await adapter.is_folder("sub") is True
        assert await adapter.is_folder("a.txt") is False

    @pytest.mark.spec("ASYNC-031")
    async def test_read_bytes(self) -> None:
        adapter, _ = _make_populated_adapter()
        assert await adapter.read_bytes("a.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-031")
    async def test_read_bytes_not_found(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(NotFound, match="not found"):
            await adapter.read_bytes("missing.txt")

    @pytest.mark.spec("ASYNC-031")
    async def test_delete(self) -> None:
        adapter, _ = _make_populated_adapter()
        await adapter.delete("a.txt")
        assert await adapter.exists("a.txt") is False

    @pytest.mark.spec("ASYNC-031")
    async def test_move(self) -> None:
        adapter, _ = _make_populated_adapter()
        await adapter.move("a.txt", "moved.txt")
        assert await adapter.exists("a.txt") is False
        assert await adapter.read_bytes("moved.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-031")
    async def test_copy(self) -> None:
        adapter, _ = _make_populated_adapter()
        await adapter.copy("a.txt", "copied.txt")
        assert await adapter.read_bytes("a.txt") == b"alpha"
        assert await adapter.read_bytes("copied.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-031")
    async def test_get_file_info(self) -> None:
        adapter, _ = _make_populated_adapter()
        info = await adapter.get_file_info("a.txt")
        assert info.name == "a.txt"
        assert info.size == 5

    @pytest.mark.spec("ASYNC-031")
    async def test_get_folder_info(self) -> None:
        adapter, _ = _make_populated_adapter()
        info = await adapter.get_folder_info("")
        assert info.file_count == 3
        assert info.total_size == len(b"alpha") + len(b"bravo") + len(b"charlie")

    @pytest.mark.spec("ASYNC-031")
    async def test_delete_folder(self) -> None:
        adapter, _ = _make_populated_adapter()
        await adapter.delete_folder("sub", recursive=True)
        assert await adapter.exists("sub") is False

    @pytest.mark.spec("ASYNC-031", "ASYNC-037")
    async def test_check_health(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        result = await adapter.check_health()
        assert result is None


class TestSyncAdapterStreamingRead:
    """ASYNC-033: Streaming read -- chunk loop and cleanup."""

    @pytest.mark.spec("ASYNC-033")
    async def test_read_yields_content(self) -> None:
        adapter, _ = _make_populated_adapter()
        chunks = [chunk async for chunk in adapter.read("a.txt")]
        assert b"".join(chunks) == b"alpha"

    @pytest.mark.spec("ASYNC-033")
    async def test_read_not_found(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(NotFound, match="not found"):
            async for _ in adapter.read("ghost.txt"):
                pass

    @pytest.mark.spec("ASYNC-033")
    async def test_read_large_content_chunked(self) -> None:
        backend = MemoryBackend()
        # Write content larger than the 65536 chunk size
        large = b"X" * 200_000
        backend.write("big.bin", large)
        adapter = SyncBackendAdapter(backend)
        chunks = [chunk async for chunk in adapter.read("big.bin")]
        assert b"".join(chunks) == large
        assert len(chunks) >= 2


class TestSyncAdapterIteratorMaterialization:
    """ASYNC-032: list_files, list_folders, glob, iter_children collect-then-yield."""

    @pytest.mark.spec("ASYNC-032")
    async def test_list_files(self) -> None:
        adapter, _ = _make_populated_adapter()
        files = [f async for f in adapter.list_files("")]
        assert len(files) == 2
        assert all(isinstance(f, FileInfo) for f in files)

    @pytest.mark.spec("ASYNC-032")
    async def test_list_files_recursive(self) -> None:
        adapter, _ = _make_populated_adapter()
        files = [f async for f in adapter.list_files("", recursive=True)]
        assert len(files) == 3

    @pytest.mark.spec("ASYNC-032")
    async def test_list_folders(self) -> None:
        adapter, _ = _make_populated_adapter()
        folders = [f async for f in adapter.list_folders("")]
        assert len(folders) == 1
        assert all(isinstance(f, FolderEntry) for f in folders)
        assert folders[0].name == "sub"

    @pytest.mark.spec("ASYNC-032")
    async def test_glob_raises(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(CapabilityNotSupported, match="does not support glob"):
            async for _ in adapter.glob("*.txt"):
                pass

    @pytest.mark.spec("ASYNC-032")
    async def test_iter_children(self) -> None:
        adapter, _ = _make_populated_adapter()
        children = [c async for c in adapter.iter_children("")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}


class TestSyncAdapterWriteContent:
    """ASYNC-036: write with bytes and AsyncIterator."""

    @pytest.mark.spec("ASYNC-036")
    async def test_write_bytes(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        await adapter.write("out.txt", b"hello")
        assert await adapter.read_bytes("out.txt") == b"hello"

    @pytest.mark.spec("ASYNC-036")
    async def test_write_async_iterator(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())

        async def gen() -> AsyncIterator[bytes]:
            yield b"hello "
            yield b"world"

        await adapter.write("out.txt", gen())
        assert await adapter.read_bytes("out.txt") == b"hello world"

    @pytest.mark.spec("ASYNC-036")
    async def test_write_overwrite_false_raises(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        await adapter.write("out.txt", b"first")
        with pytest.raises(AlreadyExists, match="already exists"):
            await adapter.write("out.txt", b"second")

    @pytest.mark.spec("ASYNC-036")
    async def test_write_atomic_bytes(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        await adapter.write_atomic("at.txt", b"atomic")
        assert await adapter.read_bytes("at.txt") == b"atomic"

    @pytest.mark.spec("ASYNC-036")
    async def test_write_atomic_async_iterator(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())

        async def gen() -> AsyncIterator[bytes]:
            yield b"ato"
            yield b"mic"

        await adapter.write_atomic("at.txt", gen())
        assert await adapter.read_bytes("at.txt") == b"atomic"


class TestSyncAdapterPathPassthrough:
    """ASYNC-034: Path methods forwarded from sync backend."""

    @pytest.mark.spec("ASYNC-034")
    def test_to_key(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        assert adapter.to_key("some/path") == "some/path"

    @pytest.mark.spec("ASYNC-034")
    def test_native_path(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        assert adapter.native_path("some/path") == "some/path"

    @pytest.mark.spec("ASYNC-034")
    def test_resolve(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        plan = adapter.resolve("data.csv")
        assert plan.key == "data.csv"

    @pytest.mark.spec("ASYNC-034")
    def test_unwrap_raises_for_unsupported(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(CapabilityNotSupported, match="does not expose"):
            adapter.unwrap(MemoryBackend)


class TestSyncAdapterLifecycle:
    """ASYNC-035: aclose delegates to sync close."""

    @pytest.mark.spec("ASYNC-035")
    async def test_aclose(self) -> None:
        backend = MemoryBackend()
        adapter = SyncBackendAdapter(backend)
        await adapter.write("f.txt", b"data")
        await adapter.aclose()
        # After close, the sync backend is closed (no-op for memory)
        assert adapter.name == "memory"


class TestSyncAdapterErrorPropagation:
    """Errors from sync backend propagate correctly through to_thread."""

    @pytest.mark.spec("ASYNC-031")
    async def test_not_found_propagates(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(NotFound, match="not found"):
            await adapter.read_bytes("missing.txt")

    @pytest.mark.spec("ASYNC-031")
    async def test_already_exists_propagates(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        await adapter.write("x.txt", b"data")
        with pytest.raises(AlreadyExists, match="already exists"):
            await adapter.write("x.txt", b"other")

    @pytest.mark.spec("ASYNC-031")
    async def test_delete_not_found_propagates(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        with pytest.raises(NotFound, match="not found"):
            await adapter.delete("ghost.txt")

    @pytest.mark.spec("ASYNC-031")
    async def test_delete_missing_ok_no_error(self) -> None:
        adapter = SyncBackendAdapter(MemoryBackend())
        result = await adapter.delete("ghost.txt", missing_ok=True)
        assert result is None


class TestSyncAdapterGlob:
    """ASYNC-048: glob wraps sync backend glob via asyncio.to_thread."""

    @pytest.mark.spec("ASYNC-048")
    async def test_glob_yields_matching_files(self) -> None:
        import tempfile
        from pathlib import Path

        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "a.csv").write_bytes(b"1")
            (data_dir / "b.parquet").write_bytes(b"2")
            (data_dir / "c.csv").write_bytes(b"3")
            backend = LocalBackend(root=tmp)
            adapter = SyncBackendAdapter(backend)
            results = [info async for info in adapter.glob("data/*.csv")]
            names = {r.name for r in results}
            assert names == {"a.csv", "c.csv"}
