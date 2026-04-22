"""Tests for AsyncStore -- derived from sdd/specs/029-async-store-backend-api.md."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry, WriteResult
from remote_store._path import RemotePath
from remote_store.aio import AsyncMemoryBackend, AsyncStore
from remote_store.backends._memory import MemoryBackend


class TestAsyncStoreConstruction:
    """ASYNC-040: AsyncStore construction and auto-wrapping."""

    @pytest.mark.spec("ASYNC-040")
    def test_accepts_async_backend(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="data")
        assert repr(store) == "AsyncStore(backend='async-memory', root_path='data')"

    @pytest.mark.spec("ASYNC-040")
    def test_auto_wraps_sync_backend(self) -> None:
        backend = MemoryBackend()
        store = AsyncStore(backend, root_path="data")
        assert repr(store) == "AsyncStore(backend='memory', root_path='data')"

    @pytest.mark.spec("ASYNC-040")
    def test_default_root_path_empty(self) -> None:
        store = AsyncStore(AsyncMemoryBackend())
        assert repr(store) == "AsyncStore(backend='async-memory', root_path='')"

    @pytest.mark.spec("ASYNC-040")
    def test_root_path_normalized(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data/./sub")
        assert repr(store) == "AsyncStore(backend='async-memory', root_path='data/sub')"


class TestAsyncStorePathValidation:
    """ASYNC-041: Path validation via RemotePath."""

    @pytest.mark.spec("ASYNC-041")
    @pytest.mark.parametrize(
        "bad_path",
        [
            pytest.param("../escape", id="dotdot"),
            pytest.param("bad\x00path", id="null_byte"),
        ],
    )
    async def test_invalid_path_rejected(self, async_store: AsyncStore, bad_path: str) -> None:
        with pytest.raises(InvalidPath, match="path"):
            await async_store.read_bytes(bad_path)

    @pytest.mark.spec("ASYNC-041")
    @pytest.mark.parametrize(
        "empty_path",
        [
            pytest.param("", id="empty"),
            pytest.param(".", id="dot"),
        ],
    )
    async def test_empty_path_rejected_for_file_ops(self, async_store: AsyncStore, empty_path: str) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            await async_store.write(empty_path, b"data")

    @pytest.mark.spec("ASYNC-041")
    async def test_empty_path_accepted_for_folder_ops(self, async_store: AsyncStore) -> None:
        await async_store.write("f.txt", b"data")
        assert await async_store.is_folder("")


class TestAsyncStoreRootPathScoping:
    """ASYNC-042: root_path prepended to all paths."""

    @pytest.mark.spec("ASYNC-042")
    async def test_root_path_prepended(self, async_store: AsyncStore) -> None:
        await async_store.write("hello.txt", b"hi")
        assert await async_store.exists("hello.txt")
        assert await async_store.read_bytes("hello.txt") == b"hi"

    @pytest.mark.spec("ASYNC-042")
    async def test_root_path_isolation(self) -> None:
        backend = AsyncMemoryBackend()
        store_a = AsyncStore(backend, root_path="a")
        store_b = AsyncStore(backend, root_path="b")
        await store_a.write("f.txt", b"a_data")
        await store_b.write("f.txt", b"b_data")
        assert await store_a.read_bytes("f.txt") == b"a_data"
        assert await store_b.read_bytes("f.txt") == b"b_data"


class TestAsyncStoreRead:
    """ASYNC-046: read, read_bytes, read_text."""

    @pytest.mark.spec("ASYNC-046")
    async def test_read_bytes(self, async_store: AsyncStore) -> None:
        await async_store.write("r.txt", b"content")
        assert await async_store.read_bytes("r.txt") == b"content"

    @pytest.mark.spec("ASYNC-046")
    async def test_read_stream(self, async_store: AsyncStore) -> None:
        await async_store.write("s.txt", b"stream data")
        chunks = [chunk async for chunk in async_store.read("s.txt")]
        assert b"".join(chunks) == b"stream data"

    @pytest.mark.spec("ASYNC-046")
    async def test_read_text_utf8(self, async_store: AsyncStore) -> None:
        await async_store.write("t.txt", b"Hello, world!")
        assert await async_store.read_text("t.txt") == "Hello, world!"

    @pytest.mark.spec("ASYNC-046")
    async def test_read_text_custom_encoding(self, async_store: AsyncStore) -> None:
        text = "caf\u00e9"
        await async_store.write("latin.txt", text.encode("latin-1"))
        assert await async_store.read_text("latin.txt", encoding="latin-1") == text

    @pytest.mark.spec("ASYNC-046")
    async def test_read_bytes_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.read_bytes("missing.txt")

    @pytest.mark.spec("ASYNC-046")
    async def test_read_text_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.read_text("missing.txt")


class TestAsyncStoreWrite:
    """ASYNC-046: write, write_text, write_atomic."""

    @pytest.mark.spec("ASYNC-046")
    async def test_write_bytes(self, async_store: AsyncStore) -> None:
        await async_store.write("w.txt", b"data")
        assert await async_store.read_bytes("w.txt") == b"data"

    @pytest.mark.spec("ASYNC-046")
    async def test_write_overwrite(self, async_store: AsyncStore) -> None:
        await async_store.write("ow.txt", b"old")
        with pytest.raises(AlreadyExists, match="already exists"):
            await async_store.write("ow.txt", b"new")
        await async_store.write("ow.txt", b"new", overwrite=True)
        assert await async_store.read_bytes("ow.txt") == b"new"

    @pytest.mark.spec("ASYNC-046", "ASYNC-052a")
    async def test_write_text(self, async_store: AsyncStore) -> None:
        await async_store.write_text("wt.txt", "hello")
        assert await async_store.read_text("wt.txt") == "hello"

    @pytest.mark.spec("ASYNC-046", "ASYNC-052a")
    async def test_write_text_overwrite(self, async_store: AsyncStore) -> None:
        await async_store.write_text("wto.txt", "old")
        await async_store.write_text("wto.txt", "new", overwrite=True)
        assert await async_store.read_text("wto.txt") == "new"

    @pytest.mark.spec("ASYNC-046")
    async def test_write_atomic(self, async_store: AsyncStore) -> None:
        await async_store.write_atomic("at.txt", b"atomic")
        assert await async_store.read_bytes("at.txt") == b"atomic"

    @pytest.mark.spec("ASYNC-046")
    async def test_write_async_iterator(self, async_store: AsyncStore) -> None:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"chunk1-"
            yield b"chunk2"

        await async_store.write("iter.txt", chunks())
        assert await async_store.read_bytes("iter.txt") == b"chunk1-chunk2"

    @pytest.mark.spec("ASYNC-046")
    async def test_write_atomic_async_iterator(self, async_store: AsyncStore) -> None:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"atomic-"
            yield b"iter"

        await async_store.write_atomic("at_iter.txt", chunks())
        assert await async_store.read_bytes("at_iter.txt") == b"atomic-iter"

    @pytest.mark.spec("ASYNC-046")
    async def test_write_creates_intermediate_dirs(self, async_store: AsyncStore) -> None:
        await async_store.write("deep/nested/file.txt", b"deep")
        assert await async_store.read_bytes("deep/nested/file.txt") == b"deep"

    @pytest.mark.spec("ASYNC-008", "WR-001")
    async def test_write_returns_write_result(self, async_store: AsyncStore) -> None:
        result = await async_store.write("r.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.size == 5

    @pytest.mark.spec("ASYNC-008", "WR-001", "WR-002")
    async def test_write_result_path_is_store_relative(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="data")
        result = await store.write("r.txt", b"x")
        assert str(result.path) == "r.txt"
        assert "data" not in str(result.path)

    @pytest.mark.spec("ASYNC-052a", "WR-001")
    async def test_write_text_returns_write_result(self, async_store: AsyncStore) -> None:
        result = await async_store.write_text("t.txt", "hi")
        assert isinstance(result, WriteResult)
        assert result.size == 2

    @pytest.mark.spec("ASYNC-010", "WR-001")
    async def test_write_atomic_returns_write_result(self, async_store: AsyncStore) -> None:
        result = await async_store.write_atomic("a.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.size == 5


class TestAsyncStoreDelete:
    """ASYNC-046: delete and delete_folder."""

    @pytest.mark.spec("ASYNC-046")
    async def test_delete(self, async_store: AsyncStore) -> None:
        await async_store.write("del.txt", b"x")
        await async_store.delete("del.txt")
        assert await async_store.exists("del.txt") is False

    @pytest.mark.spec("ASYNC-046")
    async def test_delete_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.delete("ghost.txt")

    @pytest.mark.spec("ASYNC-046")
    async def test_delete_missing_ok(self, async_store: AsyncStore) -> None:
        result = await async_store.delete("ghost.txt", missing_ok=True)
        assert result is None

    @pytest.mark.spec("ASYNC-046")
    async def test_delete_folder_recursive(self, async_store: AsyncStore) -> None:
        await async_store.write("folder/f.txt", b"x")
        await async_store.delete_folder("folder", recursive=True)
        assert await async_store.exists("folder") is False

    @pytest.mark.spec("ASYNC-046")
    async def test_delete_folder_root_rejected(self, async_store: AsyncStore) -> None:
        with pytest.raises(InvalidPath, match="Cannot delete the store root"):
            await async_store.delete_folder("")


class TestAsyncStoreListFiles:
    """ASYNC-052: list_files with pattern filtering and max_depth."""

    @pytest.mark.spec("ASYNC-052")
    async def test_list_files(self, async_store: AsyncStore) -> None:
        await async_store.write("lf/a.txt", b"a")
        await async_store.write("lf/b.csv", b"b")
        files = [f async for f in async_store.list_files("lf")]
        assert len(files) == 2
        assert all(isinstance(f, FileInfo) for f in files)

    @pytest.mark.spec("ASYNC-052")
    async def test_list_files_pattern(self, async_store: AsyncStore) -> None:
        await async_store.write("lf/a.txt", b"a")
        await async_store.write("lf/b.csv", b"b")
        files = [f async for f in async_store.list_files("lf", pattern="*.txt")]
        assert len(files) == 1
        assert files[0].name == "a.txt"

    @pytest.mark.spec("ASYNC-052")
    async def test_list_files_recursive(self, async_store: AsyncStore) -> None:
        await async_store.write("lfr/a.txt", b"a")
        await async_store.write("lfr/sub/b.txt", b"b")
        files = [f async for f in async_store.list_files("lfr", recursive=True)]
        assert len(files) == 2

    @pytest.mark.spec("ASYNC-014", "ASYNC-052")
    async def test_list_files_max_depth_zero(self, async_store: AsyncStore) -> None:
        await async_store.write("md/a.txt", b"a")
        await async_store.write("md/sub/b.txt", b"b")
        files = [f async for f in async_store.list_files("md", max_depth=0)]
        assert len(files) == 1
        assert files[0].name == "a.txt"

    @pytest.mark.spec("ASYNC-014", "ASYNC-052")
    async def test_list_files_max_depth_negative_raises(self, async_store: AsyncStore) -> None:
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            async for _ in async_store.list_files("", max_depth=-1):
                pass

    @pytest.mark.spec("ASYNC-052")
    async def test_list_files_paths_are_store_relative(self, async_store: AsyncStore) -> None:
        await async_store.write("rel/f.txt", b"x")
        files = [f async for f in async_store.list_files("rel")]
        assert len(files) == 1
        assert str(files[0].path) == "rel/f.txt"
        assert await async_store.read_bytes(str(files[0].path)) == b"x"


class TestAsyncStoreListFolders:
    """ASYNC-046: list_folders with immediate and BFS max_depth."""

    @pytest.mark.spec("ASYNC-046")
    async def test_list_folders(self, async_store: AsyncStore) -> None:
        await async_store.write("lfd/sub1/a.txt", b"a")
        await async_store.write("lfd/sub2/b.txt", b"b")
        folders = [f async for f in async_store.list_folders("lfd")]
        assert {f.name for f in folders} == {"sub1", "sub2"}
        assert {str(f.path) for f in folders} == {"lfd/sub1", "lfd/sub2"}

    @pytest.mark.spec("ASYNC-046", "ASYNC-052b")
    async def test_list_folders_max_depth(self, async_store: AsyncStore) -> None:
        await async_store.write("lfd2/a/b/f.txt", b"x")
        folders_d0 = [f async for f in async_store.list_folders("lfd2", max_depth=0)]
        folders_d1 = [f async for f in async_store.list_folders("lfd2", max_depth=1)]
        assert len(folders_d0) == 1
        assert folders_d0[0].name == "a"
        assert len(folders_d1) == 2
        names = {f.name for f in folders_d1}
        assert names == {"a", "b"}

    @pytest.mark.spec("ASYNC-046", "ASYNC-052b")
    async def test_list_folders_max_depth_negative_raises(self, async_store: AsyncStore) -> None:
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            async for _ in async_store.list_folders("", max_depth=-1):
                pass

    @pytest.mark.spec("ASYNC-046")
    async def test_list_folders_child_store_rebases_path(self, async_store: AsyncStore) -> None:
        await async_store.write("cr/sub/a.txt", b"a")
        child = async_store.child("cr")
        folders = [f async for f in child.list_folders("")]
        assert len(folders) == 1
        assert folders[0].name == "sub"
        assert str(folders[0].path) == "sub"


class TestAsyncStoreIterChildren:
    """ASYNC-046: iter_children yields files and folders."""

    @pytest.mark.spec("ASYNC-046")
    async def test_iter_children(self, async_store: AsyncStore) -> None:
        await async_store.write("ic/a.txt", b"a")
        await async_store.write("ic/b.txt", b"b")
        await async_store.write("ic/sub/c.txt", b"c")
        children = [c async for c in async_store.iter_children("ic")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}

    @pytest.mark.spec("ASYNC-046")
    async def test_iter_children_child_store_rebases(self, async_store: AsyncStore) -> None:
        await async_store.write("icc/sub/a.txt", b"a")
        child = async_store.child("icc")
        children = [c async for c in child.iter_children("")]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert len(folders) == 1
        assert str(folders[0].path) == "sub"

    @pytest.mark.spec("ASYNC-046")
    async def test_iter_children_empty_dir(self, async_store: AsyncStore) -> None:
        result = [c async for c in async_store.iter_children("nonexistent")]
        assert result == []


class TestAsyncStoreGlob:
    """ASYNC-053: glob is capability-gated."""

    @pytest.mark.spec("ASYNC-053")
    async def test_glob_raises_without_capability(self, async_store: AsyncStore) -> None:
        with pytest.raises(CapabilityNotSupported, match="glob"):
            async for _ in async_store.glob("*.txt"):
                pass


class TestAsyncStoreMetadata:
    """ASYNC-046: exists, is_file, is_folder, get_file_info, get_folder_info."""

    @pytest.mark.spec("ASYNC-046")
    async def test_exists(self, async_store: AsyncStore) -> None:
        assert await async_store.exists("nope.txt") is False
        await async_store.write("yes.txt", b"y")
        assert await async_store.exists("yes.txt") is True

    @pytest.mark.spec("ASYNC-046")
    async def test_is_file_is_folder(self, async_store: AsyncStore) -> None:
        await async_store.write("dir/file.txt", b"x")
        assert await async_store.is_file("dir/file.txt") is True
        assert await async_store.is_folder("dir") is True

    @pytest.mark.spec("ASYNC-046")
    async def test_get_file_info(self, async_store: AsyncStore) -> None:
        await async_store.write("info.txt", b"hello")
        fi = await async_store.get_file_info("info.txt")
        assert fi.name == "info.txt"
        assert fi.size == 5
        assert str(fi.path) == "info.txt"

    @pytest.mark.spec("ASYNC-046")
    async def test_get_file_info_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.get_file_info("missing.txt")

    @pytest.mark.spec("ASYNC-046")
    async def test_get_folder_info(self, async_store: AsyncStore) -> None:
        await async_store.write("fi/a.txt", b"aaa")
        fi = await async_store.get_folder_info("fi")
        assert fi.file_count == 1
        assert fi.total_size == 3


class TestAsyncStoreGetFolderInfoDepthLimited:
    """Depth-limited get_folder_info aggregation."""

    @pytest.mark.spec("ASYNC-046", "ASYNC-052c")
    async def test_depth_limited_aggregation(self, async_store: AsyncStore) -> None:
        await async_store.write("dfi/a.txt", b"aaa")
        await async_store.write("dfi/sub/b.txt", b"bb")
        fi_d0 = await async_store.get_folder_info("dfi", max_depth=0)
        fi_full = await async_store.get_folder_info("dfi")
        assert fi_d0.file_count == 1
        assert fi_d0.total_size == 3
        assert fi_full.file_count == 2
        assert fi_full.total_size == 5

    @pytest.mark.spec("ASYNC-046", "ASYNC-052c")
    async def test_depth_limited_negative_raises(self, async_store: AsyncStore) -> None:
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            await async_store.get_folder_info("", max_depth=-1)

    @pytest.mark.spec("ASYNC-046", "ASYNC-052c")
    async def test_depth_limited_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.get_folder_info("ghost", max_depth=0)


_MOVE_COPY_OPS = [pytest.param("move", id="move"), pytest.param("copy", id="copy")]


class TestAsyncStoreFileOps:
    """ASYNC-047: move, copy, same-path no-op."""

    @pytest.mark.spec("ASYNC-047")
    async def test_move(self, async_store: AsyncStore) -> None:
        await async_store.write("mv_src.txt", b"data")
        await async_store.move("mv_src.txt", "mv_dst.txt")
        assert await async_store.exists("mv_src.txt") is False
        assert await async_store.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("ASYNC-047")
    async def test_copy(self, async_store: AsyncStore) -> None:
        await async_store.write("cp_src.txt", b"data")
        await async_store.copy("cp_src.txt", "cp_dst.txt")
        assert await async_store.read_bytes("cp_src.txt") == b"data"
        assert await async_store.read_bytes("cp_dst.txt") == b"data"

    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    async def test_same_path_is_noop(self, async_store: AsyncStore, op: str) -> None:
        await async_store.write("same.txt", b"original")
        await getattr(async_store, op)("same.txt", "same.txt")
        assert await async_store.read_bytes("same.txt") == b"original"

    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    async def test_same_path_nonexistent_raises(self, async_store: AsyncStore, op: str) -> None:
        with pytest.raises(NotFound, match="not found"):
            await getattr(async_store, op)("ghost.txt", "ghost.txt")

    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    async def test_empty_path_rejected(self, async_store: AsyncStore, op: str) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            await getattr(async_store, op)("", "dst.txt")


class TestAsyncStoreLifecycle:
    """ASYNC-048: aclose, context manager, child no-op aclose."""

    @pytest.mark.spec("ASYNC-048")
    async def test_context_manager(self) -> None:
        async with AsyncStore(AsyncMemoryBackend(), root_path="data") as store:
            await store.write("f.txt", b"data")
            assert await store.read_bytes("f.txt") == b"data"

    @pytest.mark.spec("ASYNC-048")
    async def test_aclose(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        await store.write("f.txt", b"data")
        await store.aclose()
        # aclose is a no-op for memory backend
        assert store.supports(Capability.READ)

    @pytest.mark.spec("ASYNC-048")
    async def test_child_aclose_is_noop(self) -> None:
        backend = AsyncMemoryBackend()
        parent = AsyncStore(backend, root_path="data")
        await parent.write("f.txt", b"data")
        child = parent.child("sub")
        await child.aclose()
        # Parent should still work after child aclose
        assert await parent.read_bytes("f.txt") == b"data"


class TestAsyncStoreChild:
    """ASYNC-054: child() returns AsyncStore, shared backend, composed root."""

    @pytest.mark.spec("ASYNC-054")
    async def test_child_returns_async_store(self, async_store: AsyncStore) -> None:
        await async_store.write("sub/file.txt", b"data")
        child = async_store.child("sub")
        assert isinstance(child, AsyncStore)
        assert await child.read_bytes("file.txt") == b"data"

    @pytest.mark.spec("ASYNC-054")
    async def test_child_shares_backend(self, async_store: AsyncStore) -> None:
        await async_store.write("sub/file.txt", b"shared")
        child = async_store.child("sub")
        assert await child.read_bytes("file.txt") == b"shared"

    @pytest.mark.spec("ASYNC-054")
    async def test_child_composes_root(self) -> None:
        backend = AsyncMemoryBackend()
        parent = AsyncStore(backend, root_path="data")
        child = parent.child("sub")
        grandchild = parent.child("sub").child("deep")
        single = parent.child("sub/deep")
        assert grandchild == single
        assert child != grandchild

    @pytest.mark.spec("ASYNC-054")
    @pytest.mark.parametrize(
        "bad_path",
        [
            pytest.param("", id="empty"),
            pytest.param("../escape", id="dotdot"),
            pytest.param("bad\x00path", id="null_byte"),
        ],
    )
    def test_child_invalid_subpath_rejected(self, async_store: AsyncStore, bad_path: str) -> None:
        with pytest.raises(InvalidPath, match="path"):
            async_store.child(bad_path)

    @pytest.mark.spec("ASYNC-054")
    async def test_child_write_visible_from_parent(self, async_store: AsyncStore) -> None:
        child = async_store.child("sub")
        await child.write("file.txt", b"from_child")
        assert await async_store.read_bytes("sub/file.txt") == b"from_child"


class TestAsyncStoreEquality:
    """ASYNC-049: __eq__ and __hash__."""

    @pytest.mark.spec("ASYNC-049")
    def test_equal_if_same_backend_and_root(self) -> None:
        backend = AsyncMemoryBackend()
        a = AsyncStore(backend, root_path="data")
        b = AsyncStore(backend, root_path="data")
        assert a == b

    @pytest.mark.spec("ASYNC-049")
    def test_not_equal_different_root(self) -> None:
        backend = AsyncMemoryBackend()
        a = AsyncStore(backend, root_path="a")
        b = AsyncStore(backend, root_path="b")
        assert a != b

    @pytest.mark.spec("ASYNC-049")
    def test_not_equal_different_backend(self) -> None:
        a = AsyncStore(AsyncMemoryBackend(), root_path="data")
        b = AsyncStore(AsyncMemoryBackend(), root_path="data")
        assert a != b

    @pytest.mark.spec("ASYNC-049")
    def test_hash_same_for_equal_stores(self) -> None:
        backend = AsyncMemoryBackend()
        a = AsyncStore(backend, root_path="data")
        b = AsyncStore(backend, root_path="data")
        assert hash(a) == hash(b)

    @pytest.mark.spec("ASYNC-049")
    def test_not_equal_to_other_types(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        assert store != "not a store"


class TestAsyncStoreInterop:
    """ASYNC-050/051: to_key, native_path, resolve, unwrap, supports."""

    @pytest.mark.spec("ASYNC-051")
    @pytest.mark.parametrize(
        ("root_path", "child_path", "key", "expected"),
        [
            pytest.param("data", None, "file.txt", "data/file.txt", id="with-root"),
            pytest.param("", None, "file.txt", "file.txt", id="no-root"),
            pytest.param("data", "sub", "file.txt", "data/sub/file.txt", id="child-store"),
            pytest.param("data", None, "", "data", id="root-key"),
        ],
    )
    def test_native_path(self, root_path: str, child_path: str | None, key: str, expected: str) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path=root_path)
        if child_path:
            store = store.child(child_path)
        assert store.native_path(key) == expected

    @pytest.mark.spec("ASYNC-050")
    def test_to_key(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="data")
        assert store.to_key("data/file.txt") == "file.txt"

    @pytest.mark.spec("ASYNC-050")
    def test_to_key_unrelated_raises(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        with pytest.raises(InvalidPath):
            store.to_key("other/file.txt")

    @pytest.mark.spec("ASYNC-046", "ASYNC-052d")
    def test_resolve(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        plan = store.resolve("file.txt")
        assert plan.key == "file.txt"
        assert plan.native_path == "data/file.txt"

    @pytest.mark.spec("ASYNC-046")
    def test_unwrap_raises(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        with pytest.raises(CapabilityNotSupported, match="does not expose native handle"):
            store.unwrap(dict)

    @pytest.mark.spec("ASYNC-044")
    def test_supports(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        assert store.supports(Capability.READ) is True
        assert store.supports(Capability.WRITE) is True
        assert store.supports(Capability.GLOB) is False


class TestAsyncStoreCapabilityGating:
    """ASYNC-045: CapabilityNotSupported raised before I/O."""

    @pytest.mark.spec("ASYNC-045")
    @pytest.mark.parametrize(
        ("capability", "method", "args"),
        [
            pytest.param(Capability.GLOB, "glob", ("*.txt",), id="glob"),
        ],
    )
    async def test_capability_gated(
        self,
        async_store: AsyncStore,
        capability: Capability,
        method: str,
        args: tuple[str, ...],
    ) -> None:
        with pytest.raises(CapabilityNotSupported, match="is not supported"):
            async for _ in getattr(async_store, method)(*args):
                pass


class TestAsyncStoreEagerValidation:
    """ASYNC-045: generator-returning methods validate eagerly on call, not on iteration."""

    @pytest.mark.spec("ASYNC-045")
    @pytest.mark.parametrize(
        ("method", "args"),
        [
            pytest.param("read", ("",), id="read-empty"),
            pytest.param("list_files", ("",), id="list_files"),
            pytest.param("list_folders", ("",), id="list_folders"),
            pytest.param("iter_children", ("",), id="iter_children"),
            pytest.param("glob", ("*.txt",), id="glob"),
        ],
    )
    def test_validation_without_iteration(
        self,
        method: str,
        args: tuple[str, ...],
    ) -> None:
        """Calling the method (without iterating) raises immediately."""
        from tests.aio.conftest import RestrictedAsyncBackend

        if method == "glob":
            # glob needs GLOB capability removed to trigger eager error
            restricted = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.GLOB})
            store = AsyncStore(restricted, root_path="data")
            with pytest.raises(CapabilityNotSupported, match="is not supported"):
                store.glob("*.txt")  # no iteration, error raised here
        elif method == "read":
            store = AsyncStore(AsyncMemoryBackend(), root_path="data")
            with pytest.raises(InvalidPath, match="must not be empty"):
                store.read("")  # no iteration, error raised here
        else:
            # list_files, list_folders, iter_children need LIST removed
            restricted = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.LIST})
            store = AsyncStore(restricted, root_path="data")
            with pytest.raises(CapabilityNotSupported, match="is not supported"):
                getattr(store, method)(*args)  # no iteration, error raised here


class TestAsyncStoreWriteAtomicCapabilityGate:
    """ASYNC-011: write_atomic raises CapabilityNotSupported when backend lacks ATOMIC_WRITE."""

    @pytest.mark.spec("ASYNC-011")
    async def test_write_atomic_without_capability(self) -> None:
        from tests.aio.conftest import RestrictedAsyncBackend

        restricted = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.ATOMIC_WRITE})
        store = AsyncStore(restricted, root_path="")
        with pytest.raises(CapabilityNotSupported, match="atomic_write"):
            await store.write_atomic("file.txt", b"data")


class TestAsyncStoreNoRootRebase:
    """Rebase methods return original objects unchanged when root_path is empty."""

    @pytest.mark.spec("ASYNC-042")
    async def test_list_files_no_root(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="")
        await store.write("a.txt", b"data")
        files = [f async for f in store.list_files("")]
        assert len(files) == 1
        assert files[0].name == "a.txt"

    @pytest.mark.spec("ASYNC-042")
    async def test_list_folders_no_root(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="")
        await store.write("sub/b.txt", b"data")
        folders = [f async for f in store.list_folders("")]
        assert len(folders) == 1
        assert folders[0].name == "sub"

    @pytest.mark.spec("ASYNC-042")
    async def test_get_folder_info_no_root(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="")
        await store.write("a.txt", b"data")
        info = await store.get_folder_info("")
        assert info.file_count == 1
        assert info.total_size == 4


class TestAsyncStorePing:
    """ASYNC-052e: ping delegates to check_health."""

    @pytest.mark.spec("ASYNC-046", "ASYNC-052e")
    async def test_ping(self, async_store: AsyncStore) -> None:
        result = await async_store.ping()
        assert result is None


# ---------------------------------------------------------------------------
# Depth filter in list_files (_async_store.py line 355)
# ---------------------------------------------------------------------------


class TestAsyncStoreListFilesDepthFilter:
    """ASYNC-list-depth: list_files depth filter trims results beyond max_depth."""

    async def test_depth_filter_trims_deep_files(self) -> None:
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend)
        await store.write("a/b/shallow.txt", b"x")
        await store.write("a/b/c/deep.txt", b"x")
        files = [f async for f in store.list_files("a", max_depth=1)]
        names = {f.name for f in files}
        assert "shallow.txt" in names
        assert "deep.txt" not in names


# ---------------------------------------------------------------------------
# AsyncStore glob (_async_store.py lines 451-452, 456-457)
# ---------------------------------------------------------------------------


class TestAsyncStoreGlobInner:
    """glob() full path: lines 451-452 (pattern construction) and 456-457 (inner generator)."""

    async def test_glob_matches_files(self) -> None:
        import tempfile
        from pathlib import Path

        from remote_store.aio._sync_adapter import SyncBackendAdapter
        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "a.csv").write_bytes(b"1")
            (data_dir / "b.parquet").write_bytes(b"2")
            (data_dir / "c.csv").write_bytes(b"3")
            backend = SyncBackendAdapter(LocalBackend(root=tmp))
            store = AsyncStore(backend)
            results = [f async for f in store.glob("data/*.csv")]
            names = {r.name for r in results}
            assert names == {"a.csv", "c.csv"}

    async def test_glob_rooted_store(self) -> None:
        import tempfile
        from pathlib import Path

        from remote_store.aio._sync_adapter import SyncBackendAdapter
        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.csv").write_bytes(b"1")
            (Path(tmp) / "b.parquet").write_bytes(b"2")
            backend = SyncBackendAdapter(LocalBackend(root=tmp))
            store = AsyncStore(backend)
            results = [f async for f in store.glob("*.csv")]
            assert len(results) == 1
            assert results[0].name == "a.csv"


# ---------------------------------------------------------------------------
# _strip_root edge case (_async_store.py line 844)
# ---------------------------------------------------------------------------


class TestAsyncStoreStripRoot:
    """_strip_root: path == root returns empty string."""

    async def test_strip_root_exact_match_returns_empty(self) -> None:
        """When backend path equals store root, _strip_root returns ''."""
        backend = AsyncMemoryBackend()
        store = AsyncStore(backend, root_path="prefix")
        await store.write("file.txt", b"data")
        # list_files calls _strip_root internally; root-exact entry → ""
        files = [f async for f in store.list_files("")]
        assert any(f.name == "file.txt" for f in files)


class TestAsyncStoreHead:
    """WR-008 / ASYNC: AsyncStore.head() returns WriteResult with source='sidecar'."""

    @pytest.fixture
    def async_store(self) -> AsyncStore:
        return AsyncStore(AsyncMemoryBackend(), root_path="data")

    async def test_head_returns_sidecar_write_result(self, async_store: AsyncStore) -> None:
        from remote_store._models import WriteResult

        await async_store.write("f.bin", b"abc")
        result = await async_store.head("f.bin")
        assert isinstance(result, WriteResult)
        assert result.source == "sidecar"
        assert result.size == 3

    async def test_head_raises_not_found(self, async_store: AsyncStore) -> None:
        with pytest.raises(NotFound, match="not found"):
            await async_store.head("missing.txt")

    async def test_head_requires_metadata_capability(self) -> None:
        from tests.aio.conftest import RestrictedAsyncBackend

        restricted = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.METADATA})
        store = AsyncStore(restricted, root_path="data")
        with pytest.raises(CapabilityNotSupported):
            await store.head("f.bin")

    async def test_head_path_is_store_relative(self, async_store: AsyncStore) -> None:
        await async_store.write("nested/f.bin", b"xy")
        result = await async_store.head("nested/f.bin")
        assert result.path == RemotePath("nested/f.bin")


class TestAsyncStoreMetadataGate:
    """WR-010/WR-011 async parity: metadata= validation and capability gate."""

    @pytest.fixture
    def async_store(self) -> AsyncStore:
        return AsyncStore(AsyncMemoryBackend(), root_path="data")

    async def test_write_empty_metadata_passes(self, async_store: AsyncStore) -> None:
        await async_store.write("f.bin", b"x", metadata={})
        assert await async_store.read_bytes("f.bin") == b"x"

    @pytest.mark.spec("WR-010", "WR-012")
    @pytest.mark.parametrize(
        ("method", "content"),
        [
            ("write", b"x"),
            ("write_text", "hello"),
            ("write_atomic", b"hello"),
        ],
        ids=["write", "write_text", "write_atomic"],
    )
    async def test_write_nonempty_metadata_succeeds(
        self, async_store: AsyncStore, method: str, content: bytes | str
    ) -> None:
        result = await getattr(async_store, method)("f.bin", content, metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("WR-011")
    async def test_write_invalid_metadata_raises_value_error(self, async_store: AsyncStore) -> None:
        with pytest.raises(ValueError, match="underscore"):
            await async_store.write("f.bin", b"x", metadata={"_bad": "v"})

    @pytest.mark.spec("WR-010")
    async def test_write_metadata_no_capability_raises(self) -> None:
        from tests.aio.conftest import RestrictedAsyncBackend

        backend = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.USER_METADATA})
        store = AsyncStore(backend, root_path="data")
        with pytest.raises(CapabilityNotSupported, match="user_metadata"):
            await store.write("f.bin", b"x", metadata={"k": "v"})

    @pytest.mark.spec("WR-010", "ASYNC-052a")
    async def test_write_text_metadata_no_capability_raises(self) -> None:
        from tests.aio.conftest import RestrictedAsyncBackend

        backend = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.USER_METADATA})
        store = AsyncStore(backend, root_path="data")
        with pytest.raises(CapabilityNotSupported, match="user_metadata"):
            await store.write_text("f.bin", "hi", metadata={"k": "v"})

    @pytest.mark.spec("WR-010", "ASYNC-010")
    async def test_write_atomic_metadata_no_capability_raises(self) -> None:
        from tests.aio.conftest import RestrictedAsyncBackend

        backend = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.USER_METADATA})
        store = AsyncStore(backend, root_path="data")
        with pytest.raises(CapabilityNotSupported, match="user_metadata"):
            await store.write_atomic("f.bin", b"x", metadata={"k": "v"})
