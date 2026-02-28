"""Tests for the PyArrow FileSystem adapter — sdd/specs/014-pyarrow-filesystem-adapter.md."""

from __future__ import annotations

import io
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

pa = pytest.importorskip("pyarrow")
pafs = pytest.importorskip("pyarrow.fs")
pq = pytest.importorskip("pyarrow.parquet")

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
    def test_default_thresholds(self, store: Store) -> None:
        h = StoreFileSystemHandler(store)
        assert h._materialization_threshold == 64 * 1024 * 1024
        assert h._write_spill_threshold == 64 * 1024 * 1024

    @pytest.mark.spec("PA-001")
    def test_custom_thresholds(self, store: Store) -> None:
        h = StoreFileSystemHandler(store, materialization_threshold=100, write_spill_threshold=200)
        assert h._materialization_threshold == 100
        assert h._write_spill_threshold == 200

    @pytest.mark.spec("PA-002")
    def test_pyarrow_fs_factory(self, store: Store) -> None:
        fs = pyarrow_fs(store)
        assert isinstance(fs, pafs.PyFileSystem)

    @pytest.mark.spec("PA-002")
    def test_pyarrow_fs_factory_passes_thresholds(self, store: Store) -> None:
        fs = pyarrow_fs(store, materialization_threshold=42, write_spill_threshold=99)
        assert isinstance(fs, pafs.PyFileSystem)

    @pytest.mark.spec("PA-003")
    def test_type_name(self, handler: StoreFileSystemHandler) -> None:
        assert handler.get_type_name() == "remote-store"


# ---------------------------------------------------------------------------
# PA-004/005/006: Path normalization
# ---------------------------------------------------------------------------


class TestPathNormalization:
    @pytest.mark.spec("PA-006")
    def test_strip_leading_slash(self) -> None:
        assert StoreFileSystemHandler.normalize_path("/foo/bar") == "foo/bar"

    @pytest.mark.spec("PA-006")
    def test_strip_trailing_slash(self) -> None:
        assert StoreFileSystemHandler.normalize_path("foo/bar/") == "foo/bar"

    @pytest.mark.spec("PA-006")
    def test_collapse_separators(self) -> None:
        assert StoreFileSystemHandler.normalize_path("foo//bar///baz") == "foo/bar/baz"

    @pytest.mark.spec("PA-005")
    def test_root_returns_empty(self) -> None:
        assert StoreFileSystemHandler.normalize_path("") == ""
        assert StoreFileSystemHandler.normalize_path("/") == ""

    @pytest.mark.spec("PA-004")
    def test_backslash_normalized(self) -> None:
        assert StoreFileSystemHandler.normalize_path("foo\\bar\\baz") == "foo/bar/baz"

    @pytest.mark.spec("PA-006")
    def test_combined_normalization(self) -> None:
        assert StoreFileSystemHandler.normalize_path("/foo//bar\\baz/") == "foo/bar/baz"


# ---------------------------------------------------------------------------
# PA-007: get_file_info
# ---------------------------------------------------------------------------


class TestGetFileInfo:
    @pytest.mark.spec("PA-007")
    def test_file_type(self, fs: Any, store: Store) -> None:
        store.write("test.txt", b"hello")
        infos = fs.get_file_info(["test.txt"])
        assert len(infos) == 1
        assert infos[0].type == pafs.FileType.File
        assert infos[0].size == 5

    @pytest.mark.spec("PA-007")
    def test_folder_type(self, fs: Any, store: Store) -> None:
        store.write("dir/file.txt", b"data")
        infos = fs.get_file_info(["dir"])
        assert len(infos) == 1
        assert infos[0].type == pafs.FileType.Directory

    @pytest.mark.spec("PA-007")
    def test_not_found(self, fs: Any) -> None:
        infos = fs.get_file_info(["nonexistent"])
        assert len(infos) == 1
        assert infos[0].type == pafs.FileType.NotFound

    @pytest.mark.spec("PA-007")
    def test_root_is_directory(self, fs: Any) -> None:
        infos = fs.get_file_info([""])
        assert len(infos) == 1
        assert infos[0].type == pafs.FileType.Directory

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
        # Non-recursive should not include deeply nested files
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
        # Synthetic dir entry
        assert "dir/sub" in paths
        assert types["dir/sub"] == pafs.FileType.Directory

    @pytest.mark.spec("PA-008")
    def test_allow_not_found_true(self, fs: Any) -> None:
        selector = pafs.FileSelector("nonexistent", allow_not_found=True)
        infos = fs.get_file_info(selector)
        assert infos == []

    @pytest.mark.spec("PA-008")
    def test_allow_not_found_false(self, fs: Any) -> None:
        selector = pafs.FileSelector("nonexistent", allow_not_found=False)
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


# ---------------------------------------------------------------------------
# PA-009: open_input_stream
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


# ---------------------------------------------------------------------------
# PA-010: open_input_file
# ---------------------------------------------------------------------------


class TestOpenInputFile:
    @pytest.mark.spec("PA-010")
    def test_small_file_buffer_reader(self, store: Store) -> None:
        """Small files (below threshold) use BufferReader (Tier 2)."""
        store.write("small.txt", b"small data")
        fs = pyarrow_fs(store, materialization_threshold=1024)
        with fs.open_input_file("small.txt") as f:
            assert f.read() == b"small data"

    @pytest.mark.spec("PA-010")
    def test_threshold_zero_always_streams(self, local_store: Store) -> None:
        """threshold=0 disables Tier 2 — falls to Tier 3 for seekable streams."""
        local_store.write("data.txt", b"stream me")
        fs = pyarrow_fs(local_store, materialization_threshold=0)
        with fs.open_input_file("data.txt") as f:
            assert f.read() == b"stream me"

    @pytest.mark.spec("PA-010")
    def test_threshold_maxsize_always_materializes(self, store: Store) -> None:
        """sys.maxsize threshold always materializes (Tier 2)."""
        import sys

        store.write("big.txt", b"x" * 100)
        fs = pyarrow_fs(store, materialization_threshold=sys.maxsize)
        with fs.open_input_file("big.txt") as f:
            assert len(f.read()) == 100

    @pytest.mark.spec("PA-010")
    def test_large_seekable_file_streams(self, local_store: Store) -> None:
        """Large files with seekable streams use Tier 3 (PythonFile)."""
        content = b"x" * 100
        local_store.write("large.txt", content)
        # Set threshold below file size to force Tier 3
        fs = pyarrow_fs(local_store, materialization_threshold=10)
        with fs.open_input_file("large.txt") as f:
            assert f.read() == content

    @pytest.mark.spec("PA-010")
    def test_missing_file_raises(self, fs: Any) -> None:
        with pytest.raises(FileNotFoundError):
            fs.open_input_file("nonexistent.txt")


# ---------------------------------------------------------------------------
# PA-011/012: Write operations
# ---------------------------------------------------------------------------


class TestOpenOutputStream:
    @pytest.mark.spec("PA-011")
    def test_write_round_trip(self, fs: Any, store: Store) -> None:
        with fs.open_output_stream("output.txt") as f:
            f.write(b"written via pyarrow")
        assert store.read_bytes("output.txt") == b"written via pyarrow"

    @pytest.mark.spec("PA-011")
    def test_metadata_ignored(self, fs: Any, store: Store) -> None:
        with fs.open_output_stream("meta.txt") as f:
            f.write(b"data")
        assert store.read_bytes("meta.txt") == b"data"

    @pytest.mark.spec("PA-011")
    def test_empty_file(self, fs: Any, store: Store) -> None:
        with fs.open_output_stream("empty.txt"):
            pass
        assert store.read_bytes("empty.txt") == b""

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
    def test_tell(self, store: Store) -> None:
        sink = _StoreSink(store, "tell.txt", spill_threshold=1024)
        assert sink.tell() == 0
        sink.write(b"12345")
        assert sink.tell() == 5
        sink.close()

    @pytest.mark.spec("PA-016")
    def test_writable_readable(self, store: Store) -> None:
        sink = _StoreSink(store, "wr.txt", spill_threshold=1024)
        assert sink.writable() is True
        assert sink.readable() is False
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
    def test_spill_to_disk(self, store: Store) -> None:
        """Write exceeding spill_threshold should still work (spills to tempfile)."""
        sink = _StoreSink(store, "spill.txt", spill_threshold=10)
        data = b"x" * 100
        sink.write(data)
        sink.close()
        assert store.read_bytes("spill.txt") == data

    @pytest.mark.spec("PA-016")
    def test_empty_write(self, store: Store) -> None:
        sink = _StoreSink(store, "empty.txt", spill_threshold=1024)
        sink.close()
        assert store.read_bytes("empty.txt") == b""

    @pytest.mark.spec("PA-016")
    def test_close_failure_maps_error_and_cleans_up(self, store: Store) -> None:
        """If store.write() raises during close(), the error is mapped and the sink is cleaned up."""
        sink = _StoreSink(store, "fail.txt", spill_threshold=1024)
        sink.write(b"data")

        # Monkey-patch store.write to raise NotFound (simulating backend error)
        original_write = store.write
        store.write = lambda *a, **kw: (_ for _ in ()).throw(  # type: ignore[assignment]
            NotFound("backend error", path="fail.txt")
        )
        try:
            with pytest.raises(FileNotFoundError):
                sink.close()
            # Sink should be properly closed even after error
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
        # No error, but directory may not actually exist until a file is written

    @pytest.mark.spec("PA-015")
    def test_delete_dir(self, fs: Any, store: Store) -> None:
        store.write("folder/a.txt", b"a")
        store.write("folder/sub/b.txt", b"b")
        fs.delete_dir("folder")
        assert not store.exists("folder/a.txt")
        assert not store.exists("folder/sub/b.txt")

    @pytest.mark.spec("PA-015")
    def test_delete_dir_root_raises(self, fs: Any) -> None:
        with pytest.raises(NotImplementedError):
            fs.delete_dir("")

    @pytest.mark.spec("PA-015")
    def test_delete_root_dir_contents_raises(self, handler: StoreFileSystemHandler) -> None:
        with pytest.raises(NotImplementedError):
            handler.delete_root_dir_contents()

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents(self, store: Store) -> None:
        store.write("cleanup/a.txt", b"a")
        store.write("cleanup/sub/b.txt", b"b")
        handler = StoreFileSystemHandler(store)
        handler.delete_dir_contents("cleanup")
        assert not store.exists("cleanup/a.txt")
        assert not store.exists("cleanup/sub/b.txt")

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents_root_raises(self, handler: StoreFileSystemHandler) -> None:
        """delete_dir_contents('') must refuse to wipe the entire store."""
        with pytest.raises(NotImplementedError):
            handler.delete_dir_contents("")

    @pytest.mark.spec("PA-015")
    def test_delete_dir_contents_root_leading_slash_raises(self, handler: StoreFileSystemHandler) -> None:
        """delete_dir_contents('/') normalizes to '' and refuses."""
        with pytest.raises(NotImplementedError):
            handler.delete_dir_contents("/")

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


class TestErrorMapping:
    @pytest.mark.spec("PA-019")
    def test_not_found_maps_to_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError), _map_errors():
            raise NotFound("gone", path="x")

    @pytest.mark.spec("PA-019")
    def test_invalid_path_maps_to_value_error(self) -> None:
        with pytest.raises(ValueError), _map_errors():
            raise InvalidPath("bad path", path="x")

    @pytest.mark.spec("PA-019")
    def test_permission_denied_maps_to_permission_error(self) -> None:
        with pytest.raises(PermissionError), _map_errors():
            raise PermissionDenied("nope", path="x")

    @pytest.mark.spec("PA-019")
    def test_already_exists_maps_to_file_exists_error(self) -> None:
        with pytest.raises(FileExistsError), _map_errors():
            raise AlreadyExists("exists", path="x")

    @pytest.mark.spec("PA-019")
    def test_capability_not_supported_maps_to_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError), _map_errors():
            raise CapabilityNotSupported("nope", capability="x", backend="test")

    @pytest.mark.spec("PA-019")
    def test_directory_not_empty_maps_to_os_error(self) -> None:
        with pytest.raises(OSError), _map_errors():
            raise DirectoryNotEmpty("not empty", path="x")

    @pytest.mark.spec("PA-019")
    def test_backend_unavailable_maps_to_os_error(self) -> None:
        with pytest.raises(OSError), _map_errors():
            raise BackendUnavailable("unavailable", backend="test")

    @pytest.mark.spec("PA-019")
    def test_base_error_maps_to_os_error(self) -> None:
        with pytest.raises(OSError), _map_errors():
            raise RemoteStoreError("generic")

    @pytest.mark.spec("PA-020")
    def test_no_remote_store_error_leakage(self, fs: Any) -> None:
        """Ensure RemoteStoreError never escapes to the caller."""
        with pytest.raises(FileNotFoundError):
            fs.open_input_stream("definitely/missing.txt")

    @pytest.mark.spec("PA-019")
    def test_exception_chaining(self) -> None:
        original = NotFound("test", path="x")
        with pytest.raises(FileNotFoundError) as exc_info, _map_errors():  # noqa: PT012
            raise original
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# PA-024/025: Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    @pytest.mark.spec("PA-024")
    def test_parquet_round_trip(self, local_store: Store) -> None:
        """Write and read a Parquet file through the PyArrow filesystem."""
        fs = pyarrow_fs(local_store)
        table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        pq.write_table(table, "test.parquet", filesystem=fs)
        result = pq.read_table("test.parquet", filesystem=fs)
        assert result.equals(table)

    @pytest.mark.spec("PA-025")
    def test_pandas_round_trip(self, local_store: Store) -> None:
        """Pandas Parquet round-trip via filesystem= parameter."""
        pd = pytest.importorskip("pandas")
        fs = pyarrow_fs(local_store)
        df = pd.DataFrame({"x": [10, 20], "y": ["foo", "bar"]})
        df.to_parquet("pandas_test.parquet", engine="pyarrow", filesystem=fs)
        result = pd.read_parquet("pandas_test.parquet", engine="pyarrow", filesystem=fs)
        pd.testing.assert_frame_equal(df, result)

    @pytest.mark.spec("PA-025")
    def test_dataset_discovery(self, local_store: Store) -> None:
        """PyArrow dataset() discovers files via get_file_info_selector."""
        ds = pytest.importorskip("pyarrow.dataset")
        fs = pyarrow_fs(local_store)
        table = pa.table({"value": [1, 2, 3]})
        pq.write_table(table, "ds/part1.parquet", filesystem=fs)
        pq.write_table(table, "ds/part2.parquet", filesystem=fs)
        dataset = ds.dataset("ds", filesystem=fs, format="parquet")
        result = dataset.to_table()
        assert result.num_rows == 6

    @pytest.mark.spec("PA-024")
    def test_write_via_pyarrow_read_via_store(self, local_store: Store) -> None:
        """Write through PyArrow, read back through Store API."""
        fs = pyarrow_fs(local_store)
        table = pa.table({"a": [42]})
        pq.write_table(table, "cross.parquet", filesystem=fs)
        raw = local_store.read_bytes("cross.parquet")
        assert len(raw) > 0
        # Verify it's valid Parquet
        result = pq.read_table(io.BytesIO(raw))
        assert result.column("a").to_pylist() == [42]


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestNonSeekableFallback:
    """Cover Tier 2 fallback for non-seekable large streams (lines 266-275)."""

    @pytest.mark.spec("PA-010")
    def test_non_seekable_large_file_materializes(self, store: Store, caplog: pytest.LogCaptureFixture) -> None:
        """Non-seekable stream above threshold falls back to Tier 2 with warning."""
        import logging

        content = b"x" * 100
        store.write("big.txt", content)

        # Monkey-patch store.read to return a non-seekable stream
        original_read = store.read

        def non_seekable_read(path: str) -> io.RawIOBase:
            stream = original_read(path)
            stream.seekable = lambda: False  # type: ignore[attr-defined]
            return stream

        store.read = non_seekable_read  # type: ignore[assignment]
        try:
            fs = pyarrow_fs(store, materialization_threshold=10)
            with (
                caplog.at_level(logging.WARNING, logger="remote_store.ext.arrow"),
                fs.open_input_file("big.txt") as f,
            ):
                assert f.read() == content
            assert "not seekable" in caplog.text
        finally:
            store.read = original_read  # type: ignore[assignment]


class TestGetFileInfoEdgeCases:
    """Cover FileNotFoundError catch in get_file_info (lines 182-183)."""

    @pytest.mark.spec("PA-007")
    def test_get_file_info_error_during_check(self, store: Store) -> None:
        """If get_file_info raises NotFound (race condition), fall back to is_folder."""
        store.write("volatile.txt", b"data")
        handler = StoreFileSystemHandler(store)

        # Monkey-patch get_file_info to raise NotFound (simulating race condition)
        original_get_file_info = store.get_file_info

        def flaky_get_file_info(path: str):  # type: ignore[no-untyped-def]
            raise NotFound(f"Gone: {path}", path=path)

        store.get_file_info = flaky_get_file_info  # type: ignore[assignment]
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

        def raise_get_file_info(path: str):  # type: ignore[no-untyped-def]
            raise NotFound(f"Gone: {path}", path=path)

        def raise_is_folder(path: str) -> bool:
            raise NotFound(f"Gone: {path}", path=path)

        store.get_file_info = raise_get_file_info  # type: ignore[assignment]
        store.is_folder = raise_is_folder  # type: ignore[assignment]
        try:
            infos = handler.get_file_info(["ghost"])
            assert len(infos) == 1
            assert infos[0].type == pafs.FileType.NotFound
        finally:
            store.get_file_info = original_get_file_info  # type: ignore[assignment]
            store.is_folder = original_is_folder  # type: ignore[assignment]


class TestSelectorBackendRaises:
    """Cover get_file_info_selector FileNotFoundError catch (lines 226-229)."""

    @pytest.mark.spec("PA-008")
    def test_selector_backend_raises_not_found(self, store: Store) -> None:
        """Backends that raise NotFound on list_files trigger the except branch."""
        handler = StoreFileSystemHandler(store)

        original_list_files = store.list_files

        def raising_list_files(path: str, *, recursive: bool = False):  # type: ignore[no-untyped-def]
            raise NotFound(f"Not found: {path}", path=path)

        store.list_files = raising_list_files  # type: ignore[assignment]
        try:
            # allow_not_found=True should return empty
            selector = pafs.FileSelector("gone", allow_not_found=True)
            infos = handler.get_file_info_selector(selector)
            assert infos == []

            # allow_not_found=False should raise
            selector = pafs.FileSelector("gone", allow_not_found=False)
            with pytest.raises(FileNotFoundError):
                handler.get_file_info_selector(selector)
        finally:
            store.list_files = original_list_files  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Deep review: DuckDB/Polars/fsspec compatibility
# ---------------------------------------------------------------------------


class TestSyntheticDirMultiLevelBase:
    """Ensure recursive selector with multi-level base_dir doesn't emit ancestors."""

    @pytest.mark.spec("PA-008")
    def test_no_ancestors_above_base_dir(self, store: Store) -> None:
        store.write("a/b/c/d/file.txt", b"data")
        fs = pyarrow_fs(store)
        selector = pafs.FileSelector("a/b", recursive=True)
        infos = fs.get_file_info(selector)
        paths = {i.path for i in infos}
        # "a/b/c" and "a/b/c/d" are valid synthetic dirs (descendants of base)
        assert "a/b/c" in paths
        assert "a/b/c/d" in paths
        # "a" is ABOVE base_dir — must NOT appear
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


class TestHandlerEquality:
    """StoreFileSystemHandler __eq__/__ne__ for filesystem identity."""

    def test_same_store_equal(self, store: Store) -> None:
        h1 = StoreFileSystemHandler(store)
        h2 = StoreFileSystemHandler(store)
        assert h1 == h2

    def test_same_store_ne_returns_false(self, store: Store) -> None:
        h1 = StoreFileSystemHandler(store)
        h2 = StoreFileSystemHandler(store)
        assert (h1 != h2) is False

    def test_different_store_not_equal(self) -> None:
        s1 = Store(backend=MemoryBackend())
        s2 = Store(backend=MemoryBackend())
        h1 = StoreFileSystemHandler(s1)
        h2 = StoreFileSystemHandler(s2)
        assert h1 != h2

    def test_different_store_eq_returns_false(self) -> None:
        s1 = Store(backend=MemoryBackend())
        s2 = Store(backend=MemoryBackend())
        h1 = StoreFileSystemHandler(s1)
        h2 = StoreFileSystemHandler(s2)
        assert (h1 == h2) is False

    def test_eq_other_type_returns_not_implemented(self, store: Store) -> None:
        h = StoreFileSystemHandler(store)
        assert h.__eq__("not a handler") is NotImplemented
        assert h.__eq__(42) is NotImplemented

    def test_ne_other_type_returns_not_implemented(self, store: Store) -> None:
        h = StoreFileSystemHandler(store)
        assert h.__ne__("not a handler") is NotImplemented
        assert h.__ne__(42) is NotImplemented


class TestNormalizeDotDotDot:
    """normalize_path resolves . and .. components."""

    @pytest.mark.spec("PA-006")
    def test_single_dot_removed(self) -> None:
        assert StoreFileSystemHandler.normalize_path("dir/./file.txt") == "dir/file.txt"

    @pytest.mark.spec("PA-006")
    def test_double_dot_resolved(self) -> None:
        assert StoreFileSystemHandler.normalize_path("dir/../file.txt") == "file.txt"

    @pytest.mark.spec("PA-006")
    def test_double_dot_at_root_ignored(self) -> None:
        assert StoreFileSystemHandler.normalize_path("../file.txt") == "file.txt"

    @pytest.mark.spec("PA-006")
    def test_complex_dot_resolution(self) -> None:
        assert StoreFileSystemHandler.normalize_path("a/b/../c/./d/../e") == "a/c/e"


class TestAllExports:
    """PA-022: __all__ re-exports verification."""

    @pytest.mark.spec("PA-022")
    def test_arrow_module_exports(self) -> None:
        from remote_store.ext import arrow

        assert "StoreFileSystemHandler" in arrow.__all__
        assert "pyarrow_fs" in arrow.__all__

    @pytest.mark.spec("PA-022")
    def test_top_level_reexports(self) -> None:
        import remote_store

        assert hasattr(remote_store, "StoreFileSystemHandler")
        assert hasattr(remote_store, "pyarrow_fs")
