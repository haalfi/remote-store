"""Tests for the PyArrow FileSystem adapter — sdd/specs/014-pyarrow-filesystem-adapter.md."""

from __future__ import annotations

import io
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

pa = pytest.importorskip("pyarrow")
pafs = pytest.importorskip("pyarrow.fs")
pq = pytest.importorskip("pyarrow.parquet")

from remote_store._backend import Backend  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._store import Store  # noqa: E402
from remote_store.backends._local import LocalBackend  # noqa: E402
from remote_store.backends._memory import MemoryBackend  # noqa: E402
from remote_store.ext.arrow import StoreFileSystemHandler, _map_errors, _StoreSink, pyarrow_fs  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Iterator[Store]:
    backend = MemoryBackend()
    s = Store(backend=backend)
    yield s
    s.close()


@pytest.fixture
def local_store() -> Iterator[Store]:
    """LocalBackend store — needed for integration tests requiring seekable streams."""
    with tempfile.TemporaryDirectory() as tmp:
        backend = LocalBackend(root=tmp)
        yield Store(backend=backend)


@pytest.fixture
def handler(store: Store) -> StoreFileSystemHandler:
    return StoreFileSystemHandler(store)


@pytest.fixture
def fs(store: Store) -> Any:
    return pyarrow_fs(store)


# ---------------------------------------------------------------------------
# PA-001/002/003: Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    @pytest.mark.spec("PA-001")
    def test_handler_holds_store_reference(self, store: Store) -> None:
        h = StoreFileSystemHandler(store)
        assert h._store is store

    @pytest.mark.spec("PA-001")
    @pytest.mark.parametrize(
        ("kwargs", "mat_expected", "spill_expected"),
        [
            pytest.param({}, 64 * 1024 * 1024, 64 * 1024 * 1024, id="defaults"),
            pytest.param(
                {"materialization_threshold": 100, "write_spill_threshold": 200},
                100,
                200,
                id="custom",
            ),
        ],
    )
    def test_thresholds(self, store: Store, kwargs: dict[str, int], mat_expected: int, spill_expected: int) -> None:
        h = StoreFileSystemHandler(store, **kwargs)
        assert h._materialization_threshold == mat_expected
        assert h._write_spill_threshold == spill_expected

    @pytest.mark.spec("PA-002")
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({}, id="no_thresholds"),
            pytest.param({"materialization_threshold": 42, "write_spill_threshold": 99}, id="with_thresholds"),
        ],
    )
    def test_pyarrow_fs_factory(self, store: Store, kwargs: dict[str, int]) -> None:
        result = pyarrow_fs(store, **kwargs)
        assert isinstance(result, pafs.PyFileSystem)

    @pytest.mark.spec("PA-003")
    def test_type_name(self, handler: StoreFileSystemHandler) -> None:
        assert handler.get_type_name() == "remote-store"


# ---------------------------------------------------------------------------
# PA-004/005/006: Path normalization
# ---------------------------------------------------------------------------


class TestPathNormalization:
    @pytest.mark.spec("PA-006")
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("/foo/bar", "foo/bar", id="strip_leading_slash"),
            pytest.param("foo/bar/", "foo/bar", id="strip_trailing_slash"),
            pytest.param("foo//bar///baz", "foo/bar/baz", id="collapse_separators"),
            pytest.param("", "", id="root_empty"),
            pytest.param("/", "", id="root_slash"),
            pytest.param("foo\\bar\\baz", "foo/bar/baz", id="backslash"),
            pytest.param("/foo//bar\\baz/", "foo/bar/baz", id="combined"),
            pytest.param("dir/./file.txt", "dir/file.txt", id="single_dot"),
            pytest.param("dir/../file.txt", "file.txt", id="double_dot"),
            pytest.param("../file.txt", "file.txt", id="double_dot_at_root"),
            pytest.param("a/b/../c/./d/../e", "a/c/e", id="complex_dots"),
        ],
    )
    def test_normalize_path(self, raw: str, expected: str) -> None:
        assert StoreFileSystemHandler.normalize_path(raw) == expected


# ---------------------------------------------------------------------------
# PA-007: get_file_info
# ---------------------------------------------------------------------------


class TestGetFileInfo:
    @pytest.mark.spec("PA-007")
    @pytest.mark.parametrize(
        ("setup_files", "query", "expected_type", "expected_size"),
        [
            pytest.param({"test.txt": b"hello"}, "test.txt", pafs.FileType.File, 5, id="file_type"),
            pytest.param({"dir/file.txt": b"data"}, "dir", pafs.FileType.Directory, None, id="folder_type"),
            pytest.param({}, "nonexistent", pafs.FileType.NotFound, None, id="not_found"),
            pytest.param({}, "", pafs.FileType.Directory, None, id="root_is_directory"),
        ],
    )
    def test_single_path(
        self,
        fs: Any,
        store: Store,
        setup_files: dict[str, bytes],
        query: str,
        expected_type: Any,
        expected_size: int | None,
    ) -> None:
        for path, content in setup_files.items():
            store.write(path, content)
        infos = fs.get_file_info([query])
        assert len(infos) == 1
        assert infos[0].type == expected_type
        if expected_size is not None:
            assert infos[0].size == expected_size

    @pytest.mark.spec("PA-004")
    def test_leading_slash_stripped(self, fs: Any, store: Store) -> None:
        store.write("data.txt", b"x")
        infos = fs.get_file_info(["/data.txt"])
        assert len(infos) == 1
        assert infos[0].type == pafs.FileType.File

    @pytest.mark.spec("PA-007")
    def test_multiple_paths(self, fs: Any, store: Store) -> None:
        store.write("a.txt", b"a")
        store.write("b.txt", b"b")
        infos = fs.get_file_info(["a.txt", "missing", "b.txt"])
        assert infos[0].type == pafs.FileType.File
        assert infos[1].type == pafs.FileType.NotFound
        assert infos[2].type == pafs.FileType.File

    @pytest.mark.spec("PA-007")
    def test_get_file_info_error_during_check(self, store: Store) -> None:
        """If get_file_info raises NotFound (race condition), fall back to is_folder."""
        store.write("volatile.txt", b"data")
        handler = StoreFileSystemHandler(store)
        original_get_file_info = store.get_file_info
        store.get_file_info = lambda path: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound(f"Gone: {path}", path=path)
        )
        try:
            infos = handler.get_file_info(["volatile.txt"])
            assert len(infos) == 1
            assert infos[0].type == pafs.FileType.NotFound
        finally:
            store.get_file_info = original_get_file_info  # type: ignore[assignment]

    @pytest.mark.spec("PA-007")
    def test_get_file_info_is_folder_raises(self, store: Store) -> None:
        """If both get_file_info and is_folder raise, return NotFound."""
        handler = StoreFileSystemHandler(store)
        original_get_file_info = store.get_file_info
        original_is_folder = store.is_folder
        store.get_file_info = lambda path: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound(f"Gone: {path}", path=path)
        )
        store.is_folder = lambda path: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound(f"Gone: {path}", path=path)
        )
        try:
            infos = handler.get_file_info(["ghost"])
            assert len(infos) == 1
            assert infos[0].type == pafs.FileType.NotFound
        finally:
            store.get_file_info = original_get_file_info  # type: ignore[assignment]
            store.is_folder = original_is_folder  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PA-008: get_file_info_selector
# ---------------------------------------------------------------------------


class TestGetFileInfoSelector:
    @pytest.mark.spec("PA-008")
    def test_non_recursive(self, fs: Any, store: Store) -> None:
        store.write("dir/a.txt", b"a")
        store.write("dir/b.txt", b"b")
        store.write("dir/sub/c.txt", b"c")
        selector = pafs.FileSelector("dir", recursive=False)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        types = {i.path: i.type for i in infos}
        assert "dir/a.txt" in paths
        assert "dir/b.txt" in paths
        assert "dir/sub" in paths
        assert types["dir/sub"] == pafs.FileType.Directory
        assert "dir/sub/c.txt" not in paths

    @pytest.mark.spec("PA-008")
    def test_recursive(self, fs: Any, store: Store) -> None:
        store.write("dir/a.txt", b"a")
        store.write("dir/sub/b.txt", b"b")
        selector = pafs.FileSelector("dir", recursive=True)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        types = {i.path: i.type for i in infos}
        assert "dir/a.txt" in paths
        assert "dir/sub/b.txt" in paths
        assert "dir/sub" in paths
        assert types["dir/sub"] == pafs.FileType.Directory

    @pytest.mark.spec("PA-008")
    @pytest.mark.parametrize(
        ("allow_not_found", "expect_empty"),
        [
            pytest.param(True, True, id="allow_not_found_true"),
            pytest.param(False, False, id="allow_not_found_false"),
        ],
    )
    def test_allow_not_found(self, fs: Any, allow_not_found: bool, expect_empty: bool) -> None:
        selector = pafs.FileSelector("nonexistent", allow_not_found=allow_not_found)
        if expect_empty:
            assert fs.get_file_info(selector) == []
        else:
            with pytest.raises(FileNotFoundError):
                fs.get_file_info(selector)

    @pytest.mark.spec("PA-008")
    def test_store_relative_paths(self, fs: Any, store: Store) -> None:
        store.write("data/file.txt", b"x")
        selector = pafs.FileSelector("data", recursive=True)
        infos = fs.get_file_info(selector)
        file_infos = [i for i in infos if i.type == pafs.FileType.File]
        assert len(file_infos) == 1
        assert file_infos[0].path == "data/file.txt"

    @pytest.mark.spec("PA-008")
    def test_root_selector(self, fs: Any, store: Store) -> None:
        store.write("top.txt", b"t")
        store.write("sub/deep.txt", b"d")
        selector = pafs.FileSelector("", recursive=True)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        assert "top.txt" in paths
        assert "sub/deep.txt" in paths

    @pytest.mark.spec("PA-008")
    def test_no_ancestors_above_base_dir(self, store: Store) -> None:
        store.write("a/b/c/d/file.txt", b"data")
        fs = pyarrow_fs(store)
        selector = pafs.FileSelector("a/b", recursive=True)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        assert "a/b/c" in paths
        assert "a/b/c/d" in paths
        assert "a" not in paths

    @pytest.mark.spec("PA-008")
    def test_root_base_dir_no_regression(self, store: Store) -> None:
        """Empty base_dir should still produce synthetic dirs."""
        store.write("x/y/z.txt", b"data")
        fs = pyarrow_fs(store)
        selector = pafs.FileSelector("", recursive=True)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        assert "x" in paths
        assert "x/y" in paths

    @pytest.mark.spec("PA-008")
    def test_selector_backend_raises_not_found(self, store: Store) -> None:
        """Backends that raise NotFound on list_files trigger the except branch."""
        handler = StoreFileSystemHandler(store)
        original_list_files = store.list_files
        store.list_files = lambda path, *, recursive=False: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound(f"Not found: {path}", path=path)
        )
        try:
            selector = pafs.FileSelector("gone", allow_not_found=True)
            assert handler.get_file_info_selector(selector) == []

            selector = pafs.FileSelector("gone", allow_not_found=False)
            with pytest.raises(FileNotFoundError):
                handler.get_file_info_selector(selector)
        finally:
            store.list_files = original_list_files  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PA-009/010: Read operations
# ---------------------------------------------------------------------------


class TestOpenInputStream:
    @pytest.mark.spec("PA-009")
    def test_read_stream_content(self, fs: Any, store: Store) -> None:
        store.write("hello.txt", b"Hello, world!")
        with fs.open_input_stream("hello.txt") as f:
            data = f.read()
        assert data == b"Hello, world!"

    @pytest.mark.spec("PA-009")
    def test_missing_file_raises(self, fs: Any) -> None:
        with pytest.raises(FileNotFoundError):
            fs.open_input_stream("nonexistent.txt")


class TestOpenInputFile:
    @pytest.mark.spec("PA-010")
    @pytest.mark.parametrize(
        ("use_local", "content", "threshold", "description"),
        [
            pytest.param(False, b"small data", 1024, "small_file_buffer_reader", id="small_file"),
            pytest.param(True, b"stream me", 0, "threshold_zero_streams", id="threshold_zero"),
            pytest.param(False, b"x" * 100, None, "maxsize_materializes", id="maxsize"),
            pytest.param(True, b"x" * 100, 10, "large_seekable_streams", id="large_seekable"),
        ],
    )
    def test_read_round_trip(
        self,
        store: Store,
        local_store: Store,
        use_local: bool,
        content: bytes,
        threshold: int | None,
        description: str,
    ) -> None:
        import sys

        target = local_store if use_local else store
        target.write("data.txt", content)
        mat_threshold = sys.maxsize if threshold is None else threshold
        result_fs = pyarrow_fs(target, materialization_threshold=mat_threshold)
        with result_fs.open_input_file("data.txt") as f:
            assert f.read() == content

    @pytest.mark.spec("PA-010")
    def test_missing_file_raises(self, fs: Any) -> None:
        with pytest.raises(FileNotFoundError):
            fs.open_input_file("nonexistent.txt")

    @pytest.mark.spec("PA-010")
    def test_large_file_uses_read_seekable(self, store: Store) -> None:
        """Large files above threshold use read_seekable() for Tier 3 PythonFile."""
        content = b"x" * 100
        store.write("big.txt", content)
        result_fs = pyarrow_fs(store, materialization_threshold=10)
        with result_fs.open_input_file("big.txt") as f:
            assert f.read() == content


# ---------------------------------------------------------------------------
# PA-010: Tier 1 native fast path
# ---------------------------------------------------------------------------


class _FakePyArrowBackend(Backend):
    """Minimal backend stub that exposes a native PyArrow FS via unwrap().

    Used to test Tier 1 E2E probing without requiring Docker/S3.
    Delegates actual I/O to a LocalBackend underneath.
    """

    def __init__(self, local_backend: Any) -> None:
        self._inner = local_backend
        self._pa_fs = pafs.LocalFileSystem()

    @property
    def name(self) -> str:
        return "fake-pyarrow"

    @property
    def capabilities(self) -> Any:
        return self._inner.capabilities

    def unwrap(self, type_hint: type) -> Any:
        if type_hint is pafs.FileSystem:
            return self._pa_fs
        raise CapabilityNotSupported(f"Cannot unwrap {type_hint}", capability="unwrap", backend="fake-pyarrow")

    def native_path(self, path: str) -> str:
        root = str(self._inner._root)
        return f"{root}/{path}" if path else root

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)

    def is_file(self, path: str) -> bool:
        return self._inner.is_file(path)

    def is_folder(self, path: str) -> bool:
        return self._inner.is_folder(path)

    def read(self, path: str) -> Any:
        return self._inner.read(path)

    def read_bytes(self, path: str) -> bytes:
        return self._inner.read_bytes(path)

    def write(self, path: str, content: Any, *, overwrite: bool = False) -> None:
        self._inner.write(path, content, overwrite=overwrite)

    def write_atomic(self, path: str, content: Any, *, overwrite: bool = False) -> None:
        self._inner.write_atomic(path, content, overwrite=overwrite)

    def open_atomic(self, path: str, *, overwrite: bool = False) -> Any:
        return self._inner.open_atomic(path, overwrite=overwrite)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._inner.delete(path, missing_ok=missing_ok)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._inner.delete_folder(path, recursive=recursive, missing_ok=missing_ok)

    def list_files(self, path: str, *, recursive: bool = False) -> Any:
        return self._inner.list_files(path, recursive=recursive)

    def list_folders(self, path: str) -> Any:
        return self._inner.list_folders(path)

    def get_file_info(self, path: str) -> Any:
        return self._inner.get_file_info(path)

    def get_folder_info(self, path: str) -> Any:
        return self._inner.get_folder_info(path)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.move(src, dst, overwrite=overwrite)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.copy(src, dst, overwrite=overwrite)


class TestTier1NativeFastPath:
    """Tier 1: native PyArrow FS fast path via unwrap() + native_path()."""

    @pytest.mark.spec("PA-010")
    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(LocalBackend, id="local"),
            pytest.param(MemoryBackend, id="memory"),
        ],
    )
    def test_tier1_disabled_for_non_native_backends(self, backend_cls: type) -> None:
        if backend_cls is LocalBackend:
            with tempfile.TemporaryDirectory() as tmp:
                s = Store(backend=backend_cls(root=tmp))
                h = StoreFileSystemHandler(s)
        else:
            s = Store(backend=backend_cls())
            h = StoreFileSystemHandler(s)
        assert h._native_fs is None
        assert h._native_path_fn is None

    @pytest.mark.spec("PA-010")
    def test_tier1_e2e_with_native_backend(self, local_store: Store) -> None:
        """E2E: backend exposing unwrap(FileSystem) auto-enables Tier 1."""
        local_store.write("tier1.txt", b"native read")
        fake = _FakePyArrowBackend(local_store._backend)
        patched_store = Store(backend=fake)
        h = StoreFileSystemHandler(patched_store)
        assert h._native_fs is not None
        assert h._native_path_fn is not None
        result_fs = pafs.PyFileSystem(h)
        with result_fs.open_input_file("tier1.txt") as f:
            assert f.read() == b"native read"

    @pytest.mark.spec("PA-010")
    def test_tier1_dispatch_with_mock_native_fs(self, local_store: Store) -> None:
        """Simulate Tier 1 by injecting a native FS that handles reads."""
        local_store.write("tier1.txt", b"native read")
        h = StoreFileSystemHandler(local_store)
        local_pa_fs = pafs.LocalFileSystem()
        h._native_fs = local_pa_fs
        root = local_store._backend._root  # type: ignore[attr-defined]
        h._native_path_fn = lambda key: str(root / key) if key else str(root)
        result_fs = pafs.PyFileSystem(h)
        with result_fs.open_input_file("tier1.txt") as f:
            assert f.read() == b"native read"

    @pytest.mark.spec("PA-010")
    def test_tier1_with_root_path(self, local_store: Store) -> None:
        """Tier 1 path translation includes store root_path via dispatch."""
        local_store.write("sub/file.txt", b"child data")
        child = local_store.child("sub")
        h = StoreFileSystemHandler(child)
        assert h._native_fs is None
        native = child.native_path("file.txt")
        assert native.endswith("sub/file.txt")
        assert child.to_key(native) == "file.txt"
        local_pa_fs = pafs.LocalFileSystem()
        h._native_fs = local_pa_fs
        h._native_path_fn = child.native_path
        result_fs = pafs.PyFileSystem(h)
        with result_fs.open_input_file("file.txt") as f:
            assert f.read() == b"child data"

    @pytest.mark.spec("PA-010")
    def test_tier1_missing_file_raises(self, local_store: Store) -> None:
        h = StoreFileSystemHandler(local_store)
        local_pa_fs = pafs.LocalFileSystem()
        h._native_fs = local_pa_fs
        root = local_store._backend._root  # type: ignore[attr-defined]
        h._native_path_fn = lambda key: str(root / key)
        result_fs = pafs.PyFileSystem(h)
        with pytest.raises(FileNotFoundError):
            result_fs.open_input_file("nonexistent.txt")


# ---------------------------------------------------------------------------
# PA-011/012: Write operations
# ---------------------------------------------------------------------------


class TestOpenOutputStream:
    @pytest.mark.spec("PA-011")
    @pytest.mark.parametrize(
        ("filename", "write_data", "expected"),
        [
            pytest.param("output.txt", b"written via pyarrow", b"written via pyarrow", id="write_round_trip"),
            pytest.param("meta.txt", b"data", b"data", id="metadata_ignored"),
            pytest.param("empty.txt", b"", b"", id="empty_file"),
        ],
    )
    def test_write(self, fs: Any, store: Store, filename: str, write_data: bytes, expected: bytes) -> None:
        with fs.open_output_stream(filename) as f:
            if write_data:
                f.write(write_data)
        assert store.read_bytes(filename) == expected

    @pytest.mark.spec("PA-012")
    def test_append_raises(self, fs: Any) -> None:
        with pytest.raises(NotImplementedError):
            fs.open_append_stream("file.txt")


# ---------------------------------------------------------------------------
# PA-016: _StoreSink
# ---------------------------------------------------------------------------


class TestStoreSink:
    @pytest.mark.spec("PA-016")
    def test_write_and_close(self, store: Store) -> None:
        sink = _StoreSink(store, "sink.txt", spill_threshold=1024)
        sink.write(b"hello ")
        sink.write(b"world")
        sink.close()
        assert store.read_bytes("sink.txt") == b"hello world"

    @pytest.mark.spec("PA-016")
    def test_tell_and_properties(self, store: Store) -> None:
        sink = _StoreSink(store, "tell.txt", spill_threshold=1024)
        assert sink.tell() == 0
        assert sink.writable() is True
        assert sink.readable() is False
        sink.write(b"12345")
        assert sink.tell() == 5
        sink.close()

    @pytest.mark.spec("PA-016")
    def test_double_close(self, store: Store) -> None:
        sink = _StoreSink(store, "dc.txt", spill_threshold=1024)
        sink.write(b"data")
        sink.close()
        sink.close()  # second close is a no-op
        assert store.read_bytes("dc.txt") == b"data"

    @pytest.mark.spec("PA-016")
    def test_write_after_close(self, store: Store) -> None:
        sink = _StoreSink(store, "wac.txt", spill_threshold=1024)
        sink.close()
        with pytest.raises(ValueError, match="closed"):
            sink.write(b"nope")

    @pytest.mark.spec("PA-016")
    @pytest.mark.parametrize(
        ("data", "spill_threshold", "filename"),
        [
            pytest.param(b"x" * 100, 10, "spill.txt", id="spill_to_disk"),
            pytest.param(b"", 1024, "empty.txt", id="empty_write"),
        ],
    )
    def test_write_variants(self, store: Store, data: bytes, spill_threshold: int, filename: str) -> None:
        sink = _StoreSink(store, filename, spill_threshold=spill_threshold)
        if data:
            sink.write(data)
        sink.close()
        assert store.read_bytes(filename) == data

    @pytest.mark.spec("PA-016")
    def test_close_failure_maps_error_and_cleans_up(self, store: Store) -> None:
        """If store.write() raises during close(), the error is mapped and the sink is cleaned up."""
        sink = _StoreSink(store, "fail.txt", spill_threshold=1024)
        sink.write(b"data")
        original_write = store.write
        store.write = lambda *a, **kw: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound("backend error", path="fail.txt")
        )
        try:
            with pytest.raises(FileNotFoundError):
                sink.close()
            assert sink.closed
        finally:
            store.write = original_write  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PA-013/014/015/017/018: Mutation operations
# ---------------------------------------------------------------------------


class TestMutationOps:
    @pytest.mark.spec("PA-013")
    def test_delete_file(self, fs: Any, store: Store) -> None:
        store.write("del.txt", b"delete me")
        fs.delete_file("del.txt")
        assert not store.exists("del.txt")

    @pytest.mark.spec("PA-013")
    def test_delete_file_missing_raises(self, fs: Any) -> None:
        with pytest.raises(FileNotFoundError):
            fs.delete_file("nonexistent.txt")

    @pytest.mark.spec("PA-014")
    def test_create_dir_noop(self, fs: Any, store: Store) -> None:
        fs.create_dir("newdir")
        fs.create_dir("newdir/sub", recursive=True)

    @pytest.mark.spec("PA-015")
    def test_delete_dir(self, fs: Any, store: Store) -> None:
        store.write("folder/a.txt", b"a")
        store.write("folder/sub/b.txt", b"b")
        fs.delete_dir("folder")
        assert not store.exists("folder/a.txt")
        assert not store.exists("folder/sub/b.txt")

    @pytest.mark.spec("PA-015")
    @pytest.mark.parametrize(
        ("method", "args"),
        [
            pytest.param("delete_dir", ("",), id="delete_dir_root"),
            pytest.param("delete_root_dir_contents", (), id="delete_root_dir_contents"),
            pytest.param("delete_dir_contents", ("",), id="delete_dir_contents_root"),
            pytest.param("delete_dir_contents", ("/",), id="delete_dir_contents_root_slash"),
        ],
    )
    def test_root_operations_raise(self, handler: StoreFileSystemHandler, method: str, args: tuple[str, ...]) -> None:
        with pytest.raises(NotImplementedError):
            getattr(handler, method)(*args)

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents(self, store: Store) -> None:
        store.write("cleanup/a.txt", b"a")
        store.write("cleanup/sub/b.txt", b"b")
        handler = StoreFileSystemHandler(store)
        handler.delete_dir_contents("cleanup")
        assert not store.exists("cleanup/a.txt")
        assert not store.exists("cleanup/sub/b.txt")

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents_missing_dir_ok(self, handler: StoreFileSystemHandler) -> None:
        handler.delete_dir_contents("nonexistent", missing_dir_ok=True)

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents_missing_raises(self, handler: StoreFileSystemHandler) -> None:
        with pytest.raises(FileNotFoundError):
            handler.delete_dir_contents("nonexistent", missing_dir_ok=False)

    @pytest.mark.spec("PA-017")
    def test_move(self, fs: Any, store: Store) -> None:
        store.write("src.txt", b"move me")
        fs.move("src.txt", "dst.txt")
        assert not store.exists("src.txt")
        assert store.read_bytes("dst.txt") == b"move me"

    @pytest.mark.spec("PA-018")
    def test_copy(self, fs: Any, store: Store) -> None:
        store.write("orig.txt", b"copy me")
        fs.copy_file("orig.txt", "copy.txt")
        assert store.read_bytes("orig.txt") == b"copy me"
        assert store.read_bytes("copy.txt") == b"copy me"


# ---------------------------------------------------------------------------
# PA-019/020: Error mapping
# ---------------------------------------------------------------------------


_ERROR_MAPPING_CASES = [
    pytest.param(NotFound("gone", path="x"), FileNotFoundError, id="not_found"),
    pytest.param(InvalidPath("bad path", path="x"), ValueError, id="invalid_path"),
    pytest.param(PermissionDenied("nope", path="x"), PermissionError, id="permission_denied"),
    pytest.param(AlreadyExists("exists", path="x"), FileExistsError, id="already_exists"),
    pytest.param(
        CapabilityNotSupported("nope", capability="x", backend="test"),
        NotImplementedError,
        id="capability_not_supported",
    ),
    pytest.param(DirectoryNotEmpty("not empty", path="x"), OSError, id="directory_not_empty"),
    pytest.param(BackendUnavailable("unavailable", backend="test"), OSError, id="backend_unavailable"),
    pytest.param(RemoteStoreError("generic"), OSError, id="base_error"),
]


class TestErrorMapping:
    @pytest.mark.spec("PA-019")
    @pytest.mark.parametrize(("exc", "expected_type"), _ERROR_MAPPING_CASES)
    def test_error_mapping(self, exc: Exception, expected_type: type) -> None:
        with pytest.raises(expected_type), _map_errors():
            raise exc

    @pytest.mark.spec("PA-020")
    def test_no_remote_store_error_leakage(self, fs: Any) -> None:
        with pytest.raises(FileNotFoundError):
            fs.open_input_stream("definitely/missing.txt")

    @pytest.mark.spec("PA-019")
    def test_exception_chaining(self) -> None:
        original = NotFound("test", path="x")
        with pytest.raises(FileNotFoundError) as exc_info, _map_errors():  # noqa: PT012
            raise original
        assert exc_info.value.__cause__ is original

    @pytest.mark.spec("PA-021")
    def test_handler_after_store_close(self) -> None:
        store = Store(backend=MemoryBackend())
        store.write("f.txt", b"data")
        result_fs = pyarrow_fs(store)
        original_read = store.read
        store.read = lambda path: (_ for _ in ()).throw(  # type: ignore[assignment]
            BackendUnavailable("Store is closed", backend="memory")
        )
        try:
            with pytest.raises(OSError):
                result_fs.open_input_stream("f.txt")
        finally:
            store.read = original_read  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PA-024/025: Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    @pytest.mark.spec("PA-024")
    def test_parquet_round_trip(self, local_store: Store) -> None:
        result_fs = pyarrow_fs(local_store)
        table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        pq.write_table(table, "test.parquet", filesystem=result_fs)
        result = pq.read_table("test.parquet", filesystem=result_fs)
        assert result.equals(table)

    @pytest.mark.spec("PA-025")
    def test_pandas_round_trip(self, local_store: Store) -> None:
        pd = pytest.importorskip("pandas")
        result_fs = pyarrow_fs(local_store)
        df = pd.DataFrame({"x": [10, 20], "y": ["foo", "bar"]})
        df.to_parquet("pandas_test.parquet", engine="pyarrow", filesystem=result_fs)
        result = pd.read_parquet("pandas_test.parquet", engine="pyarrow", filesystem=result_fs)
        pd.testing.assert_frame_equal(df, result)

    @pytest.mark.spec("PA-025")
    def test_dataset_discovery(self, local_store: Store) -> None:
        ds = pytest.importorskip("pyarrow.dataset")
        result_fs = pyarrow_fs(local_store)
        table = pa.table({"value": [1, 2, 3]})
        pq.write_table(table, "ds/part1.parquet", filesystem=result_fs)
        pq.write_table(table, "ds/part2.parquet", filesystem=result_fs)
        dataset = ds.dataset("ds", filesystem=result_fs, format="parquet")
        result = dataset.to_table()
        assert result.num_rows == 6

    @pytest.mark.spec("PA-024")
    def test_write_via_pyarrow_read_via_store(self, local_store: Store) -> None:
        result_fs = pyarrow_fs(local_store)
        table = pa.table({"a": [42]})
        pq.write_table(table, "cross.parquet", filesystem=result_fs)
        raw = local_store.read_bytes("cross.parquet")
        assert len(raw) > 0
        result = pq.read_table(io.BytesIO(raw))
        assert result.column("a").to_pylist() == [42]


# ---------------------------------------------------------------------------
# Handler equality & exports
# ---------------------------------------------------------------------------


class TestHandlerEquality:
    @pytest.mark.parametrize(
        ("same_store", "expect_eq"),
        [
            pytest.param(True, True, id="same_store"),
            pytest.param(False, False, id="different_store"),
        ],
    )
    def test_equality(self, same_store: bool, expect_eq: bool) -> None:
        s1 = Store(backend=MemoryBackend())
        s2 = s1 if same_store else Store(backend=MemoryBackend())
        h1 = StoreFileSystemHandler(s1)
        h2 = StoreFileSystemHandler(s2)
        assert h1.__eq__(h2) is expect_eq
        assert h1.__ne__(h2) is (not expect_eq)

    @pytest.mark.parametrize("dunder", ["__eq__", "__ne__"], ids=["eq", "ne"])
    def test_other_type_returns_not_implemented(self, store: Store, dunder: str) -> None:
        h = StoreFileSystemHandler(store)
        method = getattr(h, dunder)
        assert method("not a handler") is NotImplemented
        assert method(42) is NotImplemented


class TestAllExports:
    @pytest.mark.spec("PA-022")
    def test_arrow_module_exports(self) -> None:
        from remote_store.ext import arrow

        assert "StoreFileSystemHandler" in arrow.__all__
        assert "pyarrow_fs" in arrow.__all__

    @pytest.mark.spec("PA-022")
    def test_no_top_level_reexports(self) -> None:
        import remote_store

        assert not hasattr(remote_store, "StoreFileSystemHandler")
        assert not hasattr(remote_store, "pyarrow_fs")
