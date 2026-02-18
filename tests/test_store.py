"""Tests for Store — derived from sdd/specs/001-store-api.md (STORE sections). Integration tests via local backend."""

from __future__ import annotations

import tempfile

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath
from remote_store._store import Store
from remote_store.backends._local import LocalBackend


@pytest.fixture
def store() -> Store:
    with tempfile.TemporaryDirectory() as tmp:
        backend = LocalBackend(root=tmp)
        yield Store(backend=backend, root_path="data")  # type: ignore[misc]


class TestStoreConstruction:
    """STORE-001: Construction."""

    @pytest.mark.spec("STORE-001")
    def test_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="myroot")
            assert store is not None


class TestStorePathValidation:
    """STORE-002: Path validation."""

    @pytest.mark.spec("STORE-002")
    def test_invalid_path_rejected(self, store: Store) -> None:
        with pytest.raises(InvalidPath):
            store.read("../escape")

    @pytest.mark.spec("STORE-002")
    def test_empty_path_resolves_to_root(self, store: Store) -> None:
        store.write("file.txt", b"data")
        assert store.is_folder("")
        assert list(store.list_files("")) == list(store.list_files("", recursive=False))


class TestStoreRootPathScoping:
    """STORE-003: Root path scoping."""

    @pytest.mark.spec("STORE-003")
    def test_root_path_prepended(self, store: Store) -> None:
        store.write("hello.txt", b"hi")
        assert store.exists("hello.txt")
        assert store.read_bytes("hello.txt") == b"hi"


class TestStoreDelegation:
    """STORE-004: Delegation to backend."""

    @pytest.mark.spec("STORE-004")
    def test_write_and_read(self, store: Store) -> None:
        store.write("test.txt", b"content")
        assert store.read_bytes("test.txt") == b"content"

    @pytest.mark.spec("STORE-004")
    def test_read_stream(self, store: Store) -> None:
        store.write("stream.txt", b"stream data")
        stream = store.read("stream.txt")
        assert stream.read() == b"stream data"


class TestStoreCapabilities:
    """STORE-005: Capability check."""

    @pytest.mark.spec("STORE-005")
    def test_supports(self, store: Store) -> None:
        assert store.supports(Capability.READ) is True
        assert store.supports(Capability.WRITE) is True


class TestStoreFullAPI:
    """STORE-008: Full API surface."""

    @pytest.mark.spec("STORE-008")
    def test_exists(self, store: Store) -> None:
        assert store.exists("nope.txt") is False
        store.write("yes.txt", b"y")
        assert store.exists("yes.txt") is True

    @pytest.mark.spec("STORE-008")
    def test_is_file_is_folder(self, store: Store) -> None:
        store.write("dir/file.txt", b"x")
        assert store.is_file("dir/file.txt") is True
        assert store.is_folder("dir") is True

    @pytest.mark.spec("STORE-008")
    def test_write_overwrite(self, store: Store) -> None:
        store.write("ow.txt", b"a")
        with pytest.raises(AlreadyExists):
            store.write("ow.txt", b"b")
        store.write("ow.txt", b"b", overwrite=True)
        assert store.read_bytes("ow.txt") == b"b"

    @pytest.mark.spec("STORE-008")
    def test_write_atomic(self, store: Store) -> None:
        store.write_atomic("at.txt", b"atomic")
        assert store.read_bytes("at.txt") == b"atomic"

    @pytest.mark.spec("STORE-008")
    def test_delete(self, store: Store) -> None:
        store.write("del.txt", b"x")
        store.delete("del.txt")
        assert store.exists("del.txt") is False

    @pytest.mark.spec("STORE-008")
    def test_delete_missing_ok(self, store: Store) -> None:
        store.delete("nonexistent.txt", missing_ok=True)

    @pytest.mark.spec("STORE-008")
    def test_delete_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            store.delete("nonexistent.txt")

    @pytest.mark.spec("STORE-008")
    def test_delete_folder(self, store: Store) -> None:
        store.write("folder/file.txt", b"x")
        store.delete_folder("folder", recursive=True)
        assert store.exists("folder") is False

    @pytest.mark.spec("STORE-008")
    def test_list_files(self, store: Store) -> None:
        store.write("lf/a.txt", b"a")
        store.write("lf/b.txt", b"b")
        files = list(store.list_files("lf"))
        assert len(files) == 2
        assert all(isinstance(f, FileInfo) for f in files)

    @pytest.mark.spec("STORE-008")
    def test_list_files_recursive(self, store: Store) -> None:
        store.write("lfr/a.txt", b"a")
        store.write("lfr/sub/b.txt", b"b")
        files = list(store.list_files("lfr", recursive=True))
        assert len(files) == 2

    @pytest.mark.spec("STORE-008")
    def test_list_folders(self, store: Store) -> None:
        store.write("lfd/sub1/a.txt", b"a")
        store.write("lfd/sub2/b.txt", b"b")
        folders = set(store.list_folders("lfd"))
        assert folders == {"sub1", "sub2"}

    @pytest.mark.spec("STORE-008")
    def test_get_file_info(self, store: Store) -> None:
        store.write("info.txt", b"hello")
        fi = store.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.size == 5

    @pytest.mark.spec("STORE-008")
    def test_get_folder_info(self, store: Store) -> None:
        store.write("fi/a.txt", b"aaa")
        fi = store.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 1

    @pytest.mark.spec("STORE-008")
    def test_move(self, store: Store) -> None:
        store.write("mv_src.txt", b"data")
        store.move("mv_src.txt", "mv_dst.txt")
        assert store.exists("mv_src.txt") is False
        assert store.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("STORE-008")
    def test_copy(self, store: Store) -> None:
        store.write("cp_src.txt", b"data")
        store.copy("cp_src.txt", "cp_dst.txt")
        assert store.read_bytes("cp_src.txt") == b"data"
        assert store.read_bytes("cp_dst.txt") == b"data"


class TestStoreRoundTrip:
    """NPR-001, NPR-014 through NPR-016: round-trip invariant."""

    @pytest.mark.spec("NPR-001")
    def test_list_files_returns_store_relative_paths(self, store: Store) -> None:
        store.write("reports/q1.csv", b"data")
        files = list(store.list_files("reports"))
        assert len(files) == 1
        assert str(files[0].path) == "reports/q1.csv"

    @pytest.mark.spec("NPR-001")
    def test_list_files_round_trip(self, store: Store) -> None:
        """FileInfo.path from listing is directly usable as Store method input."""
        store.write("rt/a.txt", b"aaa")
        store.write("rt/b.txt", b"bbb")
        for f in store.list_files("rt"):
            data = store.read_bytes(str(f.path))
            assert len(data) == 3

    @pytest.mark.spec("NPR-014")
    def test_list_files_no_root_prefix(self, store: Store) -> None:
        """FileInfo.path must NOT include the store's root_path."""
        store.write("file.txt", b"x")
        files = list(store.list_files(""))
        paths = {str(f.path) for f in files}
        # Must be "file.txt", not "data/file.txt"
        assert "file.txt" in paths
        assert not any(p.startswith("data/") for p in paths)

    @pytest.mark.spec("NPR-016")
    def test_round_trip_recursive(self, store: Store) -> None:
        store.write("a/b/c.txt", b"deep")
        for f in store.list_files("", recursive=True):
            assert store.read_bytes(str(f.path)) == b"deep"

    @pytest.mark.spec("NPR-014")
    def test_get_file_info_returns_store_relative(self, store: Store) -> None:
        store.write("info.txt", b"hello")
        fi = store.get_file_info("info.txt")
        assert str(fi.path) == "info.txt"
        # Round-trip: path should work as input
        assert store.read_bytes(str(fi.path)) == b"hello"

    @pytest.mark.spec("NPR-014")
    def test_get_folder_info_returns_store_relative(self, store: Store) -> None:
        store.write("fold/a.txt", b"a")
        fi = store.get_folder_info("fold")
        assert str(fi.path) == "fold"


class TestStoreToKey:
    """NPR-010 through NPR-013: Store.to_key."""

    @pytest.mark.spec("NPR-010")
    def test_to_key_strips_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            native = f"{tmp}/data/reports/q1.csv"
            assert store.to_key(native) == "reports/q1.csv"

    @pytest.mark.spec("NPR-012")
    def test_to_key_no_root_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="")
            native = f"{tmp}/reports/q1.csv"
            assert store.to_key(native) == "reports/q1.csv"

    @pytest.mark.spec("NPR-013")
    def test_to_key_unrelated_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.to_key(f"{tmp}/other/file.txt")
