"""Tests for AsyncMemoryBackend -- derived from sdd/specs/029-async-store-backend-api.md."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry, WriteResult
from remote_store.aio.backends._memory import AsyncMemoryBackend


class TestAsyncMemoryBasics:
    """Name and capabilities of the async memory backend."""

    @pytest.mark.spec("ASYNC-002")
    def test_name(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.name == "async-memory"

    @pytest.mark.spec("ASYNC-003")
    def test_capabilities_include_core(self) -> None:
        backend = AsyncMemoryBackend()
        for cap in (Capability.READ, Capability.WRITE, Capability.DELETE, Capability.LIST):
            assert backend.capabilities.supports(cap)

    @pytest.mark.spec("WR-010", "ASYNC-008")
    def test_capabilities_include_write_result_native_and_user_metadata(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE)
        assert backend.capabilities.supports(Capability.USER_METADATA)

    @pytest.mark.spec("ASYNC-003")
    def test_glob_not_supported(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.capabilities.supports(Capability.GLOB) is False

    @pytest.mark.spec("ASYNC-003")
    def test_repr(self) -> None:
        backend = AsyncMemoryBackend()
        assert "AsyncMemoryBackend" in repr(backend)


class TestAsyncMemoryReadWrite:
    """ASYNC-006/007/008: Read and write operations."""

    @pytest.mark.spec("ASYNC-008")
    async def test_write_and_read_bytes(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"hello")
        assert await backend.read_bytes("f.txt") == b"hello"

    @pytest.mark.spec("ASYNC-008")
    async def test_write_async_iterator(self) -> None:
        backend = AsyncMemoryBackend()

        async def gen() -> AsyncIterator[bytes]:
            yield b"hello "
            yield b"world"

        await backend.write("f.txt", gen())
        assert await backend.read_bytes("f.txt") == b"hello world"

    @pytest.mark.spec("ASYNC-006")
    async def test_read_streaming(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"content")
        chunks = [chunk async for chunk in backend.read("f.txt")]
        assert b"".join(chunks) == b"content"
        assert len(chunks) >= 1

    @pytest.mark.spec("ASYNC-007")
    async def test_read_bytes_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.read_bytes("missing.txt")

    @pytest.mark.spec("ASYNC-006")
    async def test_read_stream_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            async for _ in backend.read("missing.txt"):
                pass

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite_false_raises(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"first")
        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.write("f.txt", b"second")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite_true(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"old")
        await backend.write("f.txt", b"new", overwrite=True)
        assert await backend.read_bytes("f.txt") == b"new"

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write_atomic("f.txt", b"atomic")
        assert await backend.read_bytes("f.txt") == b"atomic"

    @pytest.mark.spec("ASYNC-009")
    async def test_write_creates_intermediate_dirs(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a/b/c.txt", b"deep")
        assert await backend.read_bytes("a/b/c.txt") == b"deep"
        assert await backend.is_folder("a")
        assert await backend.is_folder("a/b")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_empty_path_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.write("", b"data")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_returns_write_result(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.size == 5
        assert result.source == "native"
        assert str(result.path) == "f.txt"

    @pytest.mark.spec("ASYNC-008")
    async def test_write_result_path_is_backend_relative(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write("dir/f.txt", b"x")
        assert str(result.path) == "dir/f.txt"

    @pytest.mark.spec("ASYNC-008")
    async def test_write_result_last_modified_populated(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write("f.txt", b"x")
        assert result.last_modified is not None

    @pytest.mark.spec("ASYNC-008")
    async def test_write_metadata_returned(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write("f.txt", b"x", metadata={"k": "v"})
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-008")
    async def test_write_metadata_none_when_not_passed(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write("f.txt", b"x")
        assert result.metadata is None

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_returns_write_result(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write_atomic("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.size == 5

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_metadata_returned(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.write_atomic("f.txt", b"x", metadata={"a": "b"})
        assert result.metadata == {"a": "b"}


class TestAsyncMemoryDelete:
    """ASYNC-012/013: Delete operations."""

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_file(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"data")
        await backend.delete("f.txt")
        assert await backend.exists("f.txt") is False

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.delete("ghost.txt")

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_missing_ok(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.delete("ghost.txt", missing_ok=True)
        assert result is None

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_on_directory_raises_invalid_path(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("ddir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir"):
            await backend.delete("ddir")

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_on_directory_missing_ok_still_raises(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("ddir2/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir2"):
            await backend.delete("ddir2", missing_ok=True)
        assert await backend.exists("ddir2/file.txt"), "child silently deleted"

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_recursive(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/a.txt", b"a")
        await backend.write("dir/sub/b.txt", b"b")
        await backend.delete_folder("dir", recursive=True)
        assert await backend.exists("dir") is False

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_non_recursive_empty(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/f.txt", b"x")
        await backend.delete("dir/f.txt")
        await backend.delete_folder("dir")
        assert await backend.exists("dir") is False

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_non_recursive_not_empty(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/f.txt", b"x")
        with pytest.raises(DirectoryNotEmpty, match="not empty"):
            await backend.delete_folder("dir")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.delete_folder("ghost")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_missing_ok(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.delete_folder("ghost", missing_ok=True)
        assert result is None

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_empty_path_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.delete_folder("")

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_empty_path_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.delete("")


class TestAsyncMemoryListing:
    """ASYNC-014/015/029: list_files, list_folders, iter_children."""

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_non_recursive(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"a")
        await backend.write("sub/b.txt", b"b")
        files = [f async for f in backend.list_files("")]
        assert len(files) == 1
        assert files[0].name == "a.txt"

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_recursive(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"a")
        await backend.write("sub/b.txt", b"b")
        files = [f async for f in backend.list_files("", recursive=True)]
        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_subfolder(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("sub/a.txt", b"a")
        await backend.write("sub/b.txt", b"b")
        files = [f async for f in backend.list_files("sub")]
        assert len(files) == 2

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("sub1/a.txt", b"a")
        await backend.write("sub2/b.txt", b"b")
        folders = [f async for f in backend.list_folders("")]
        assert {f.name for f in folders} == {"sub1", "sub2"}
        assert all(isinstance(f, FolderEntry) for f in folders)

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"a")
        await backend.write("sub/b.txt", b"b")
        children = [c async for c in backend.iter_children("")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt"}
        assert {f.name for f in folders} == {"sub"}

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_empty_result(self) -> None:
        backend = AsyncMemoryBackend()
        files = [f async for f in backend.list_files("nonexistent")]
        assert files == []


class TestAsyncMemoryMetadata:
    """ASYNC-004/005/016/017: exists, is_file, is_folder, get_file_info, get_folder_info."""

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_file(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"data")
        assert await backend.exists("f.txt") is True
        assert await backend.exists("nope.txt") is False

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_folder(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/f.txt", b"data")
        assert await backend.exists("dir") is True

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_root(self) -> None:
        backend = AsyncMemoryBackend()
        assert await backend.exists("") is True

    @pytest.mark.spec("ASYNC-005")
    async def test_is_file(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"data")
        assert await backend.is_file("f.txt") is True
        assert await backend.is_file("") is False

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/f.txt", b"data")
        assert await backend.is_folder("dir") is True
        assert await backend.is_folder("f.txt") is False
        assert await backend.is_folder("") is True

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"hello")
        info = await backend.get_file_info("f.txt")
        assert info.name == "f.txt"
        assert info.size == 5
        assert info.modified_at is not None

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.get_file_info("missing.txt")

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/a.txt", b"aaa")
        await backend.write("dir/b.txt", b"bb")
        info = await backend.get_folder_info("dir")
        assert info.file_count == 2
        assert info.total_size == 5
        assert info.modified_at is not None

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_root(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"aaa")
        info = await backend.get_folder_info("")
        assert info.file_count == 1
        assert info.total_size == 3

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.get_folder_info("ghost")


class TestAsyncMemoryFileOps:
    """ASYNC-018/019: move and copy."""

    @pytest.mark.spec("ASYNC-018")
    async def test_move(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        await backend.move("src.txt", "dst.txt")
        assert await backend.exists("src.txt") is False
        assert await backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.spec("ASYNC-018")
    async def test_move_overwrite(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"new")
        await backend.write("dst.txt", b"old")
        await backend.move("src.txt", "dst.txt", overwrite=True)
        assert await backend.read_bytes("dst.txt") == b"new"
        assert await backend.exists("src.txt") is False

    @pytest.mark.spec("ASYNC-018")
    async def test_move_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.move("ghost.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_already_exists(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"a")
        await backend.write("dst.txt", b"b")
        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.move("src.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_same_path_noop(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"data")
        await backend.move("f.txt", "f.txt")
        assert await backend.read_bytes("f.txt") == b"data"

    @pytest.mark.spec("ASYNC-019")
    async def test_copy(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        await backend.copy("src.txt", "dst.txt")
        assert await backend.read_bytes("src.txt") == b"data"
        assert await backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_overwrite(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"new")
        await backend.write("dst.txt", b"old")
        await backend.copy("src.txt", "dst.txt", overwrite=True)
        assert await backend.read_bytes("dst.txt") == b"new"

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_not_found(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.copy("ghost.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_already_exists(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"a")
        await backend.write("dst.txt", b"b")
        with pytest.raises(AlreadyExists, match="already exists"):
            await backend.copy("src.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_empty_src_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.move("", "dst.txt")

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_empty_src_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.copy("", "dst.txt")


class TestAsyncMemoryErrors:
    """Error behavior for invalid inputs."""

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        "bad_path",
        [
            pytest.param("../escape", id="dotdot"),
            pytest.param("bad\x00path", id="null_byte"),
            pytest.param("/absolute", id="absolute"),
        ],
    )
    async def test_invalid_path_rejected(self, bad_path: str) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(InvalidPath):
            await backend.write(bad_path, b"data")

    @pytest.mark.spec("ASYNC-024")
    async def test_write_to_dir_path_raises(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("dir/f.txt", b"data")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.write("dir", b"data")


class TestAsyncMemoryConcurrency:
    """ASYNC-055: Concurrent coroutines on the same event loop."""

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_writes(self) -> None:
        backend = AsyncMemoryBackend()

        async def write_file(name: str, data: bytes) -> None:
            await backend.write(name, data)

        await asyncio.gather(
            write_file("a.txt", b"aaa"),
            write_file("b.txt", b"bbb"),
            write_file("c.txt", b"ccc"),
        )
        assert await backend.read_bytes("a.txt") == b"aaa"
        assert await backend.read_bytes("b.txt") == b"bbb"
        assert await backend.read_bytes("c.txt") == b"ccc"

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_read_write(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"initial")

        async def reader() -> bytes:
            return await backend.read_bytes("f.txt")

        async def writer() -> None:
            await backend.write("f.txt", b"updated", overwrite=True)

        # Run reader and writer concurrently -- both should complete without error
        results = await asyncio.gather(reader(), writer(), return_exceptions=True)
        # No exceptions should have been raised
        assert not any(isinstance(r, Exception) for r in results)
        # Final value should be "updated"
        assert await backend.read_bytes("f.txt") == b"updated"

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_reads(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"shared")

        async def reader() -> bytes:
            return await backend.read_bytes("f.txt")

        results = await asyncio.gather(reader(), reader(), reader())
        assert all(r == b"shared" for r in results)


class TestAsyncMemoryLifecycle:
    """ASYNC-022/023: aclose no-op and context manager."""

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_noop(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"data")
        await backend.aclose()
        # Still functional after aclose
        assert await backend.read_bytes("f.txt") == b"data"

    @pytest.mark.spec("ASYNC-023")
    async def test_context_manager(self) -> None:
        async with AsyncMemoryBackend() as backend:
            await backend.write("f.txt", b"data")
            assert await backend.read_bytes("f.txt") == b"data"


class TestAsyncMemoryMetadataRoundTrip:
    """BK-176 / ASYNC-016: metadata round-trips through all FileInfo-producing sites."""

    @pytest.mark.spec("ASYNC-016")
    @pytest.mark.parametrize("path", ["f.txt", "sub/f.txt"], ids=["root", "nested"])
    async def test_get_file_info_preserves_metadata(self, path: str) -> None:
        backend = AsyncMemoryBackend()
        await backend.write(path, b"x", metadata={"k": "v"})
        info = await backend.get_file_info(path)
        assert info.metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-016")
    async def test_list_files_non_recursive_preserves_metadata(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"x", metadata={"k": "v"})
        entries = [e async for e in backend.list_files("")]
        assert len(entries) == 1
        assert entries[0].metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-016")
    async def test_list_files_recursive_preserves_metadata(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("sub/f.txt", b"x", metadata={"k": "v"})
        entries = [e async for e in backend.list_files("", recursive=True)]
        assert len(entries) == 1
        assert entries[0].metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-016")
    async def test_iter_children_preserves_metadata(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"x", metadata={"k": "v"})
        entries = [e async for e in backend.iter_children("")]
        file_entries = [e for e in entries if isinstance(e, FileInfo)]
        assert len(file_entries) == 1
        assert file_entries[0].metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-016")
    async def test_metadata_none_when_not_written(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("f.txt", b"x")
        info = await backend.get_file_info("f.txt")
        assert info.metadata is None


class TestAsyncMemoryDeleteFolderEdgeCases:
    """Cover delete_folder parent-not-found branches (lines 256-258)."""

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_parent_not_found_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.delete_folder("no_parent/child")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_parent_not_found_missing_ok(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.delete_folder("no_parent/child", missing_ok=True)
        assert result is None


class TestAsyncMemoryListFoldersEdgeCases:
    """Cover list_folders early return for nonexistent path (line 334)."""

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders_nonexistent_returns_empty(self) -> None:
        backend = AsyncMemoryBackend()
        folders = [f async for f in backend.list_folders("nonexistent")]
        assert folders == []


class TestAsyncMemoryGetFileInfoEdgeCases:
    """Cover get_file_info empty path (line 391)."""

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_empty_path_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.get_file_info("")


class TestAsyncMemoryMoveEdgeCases:
    """Cover move edge cases: empty dst, same-path directory, missing parent, dst-is-dir (lines 460, 468, 475, 487)."""

    @pytest.mark.spec("ASYNC-018")
    async def test_move_empty_dst_raises(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.move("src.txt", "")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_same_path_not_a_file_raises_not_found(self) -> None:
        # src == dst but the path is not a file (line 468)
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.move("nonexistent", "nonexistent")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_missing_parent_raises_not_found(self) -> None:
        # src_parent does not exist (line 475)
        backend = AsyncMemoryBackend()
        with pytest.raises(NotFound, match="not found"):
            await backend.move("no_parent/file.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_dst_is_directory_raises_invalid_path(self) -> None:
        # dst exists as a directory (line 487)
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        await backend.write("existing_dir/f.txt", b"x")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.move("src.txt", "existing_dir")


class TestAsyncMemoryCopyEdgeCases:
    """Cover copy edge cases: empty dst, dst-is-dir (lines 521, 535)."""

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_empty_dst_raises(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        with pytest.raises(InvalidPath, match="must not be empty"):
            await backend.copy("src.txt", "")

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_dst_is_directory_raises_invalid_path(self) -> None:
        # dst exists as a directory (line 535)
        backend = AsyncMemoryBackend()
        await backend.write("src.txt", b"data")
        await backend.write("existing_dir/f.txt", b"x")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.copy("src.txt", "existing_dir")


class TestAsyncMemoryTraverseEdgeCases:
    """Cover _traverse non-dir intermediate node (line 570) and _ensure_parents file conflict (line 587)."""

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_through_file_returns_empty(self) -> None:
        # _traverse returns None when a file is encountered mid-path (line 570)
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"data")
        files = [f async for f in backend.list_files("a.txt/deep")]
        assert files == []

    @pytest.mark.spec("ASYNC-008")
    async def test_write_through_existing_file_raises_invalid_path(self) -> None:
        # _ensure_parents raises when a path segment is already a file (line 587)
        backend = AsyncMemoryBackend()
        await backend.write("a/file.txt", b"data")
        with pytest.raises(InvalidPath, match="exists as a file"):
            await backend.write("a/file.txt/nested.txt", b"data")


class TestAsyncMemoryListFilesDepthFilter:
    """Cover list_files max_depth directory pruning (line 694)."""

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_max_depth_prunes_deep_directories(self) -> None:
        # At depth >= max_depth a subdirectory is skipped (line 694 hit)
        backend = AsyncMemoryBackend()
        await backend.write("a/b/shallow.txt", b"x")
        await backend.write("a/b/c/deep.txt", b"x")
        files = [f async for f in backend.list_files("", recursive=True, max_depth=2)]
        names = {f.name for f in files}
        assert "shallow.txt" in names
        assert "deep.txt" not in names
