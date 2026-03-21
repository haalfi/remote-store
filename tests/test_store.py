"""Tests for Store — derived from sdd/specs/001-store-api.md (STORE sections)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def store() -> Iterator[Store]:
    yield Store(backend=MemoryBackend(), root_path="data")


class TestStoreBasics:
    """STORE-001 through STORE-005: Construction, validation, scoping, delegation, capabilities."""

    @pytest.mark.spec("STORE-001")
    def test_construction(self) -> None:
        store = Store(backend=MemoryBackend(), root_path="myroot")
        assert store is not None

    @pytest.mark.spec("STORE-002")
    def test_invalid_path_rejected(self, store: Store) -> None:
        with pytest.raises(InvalidPath):
            store.read("../escape")

    @pytest.mark.spec("STORE-002")
    def test_empty_path_resolves_to_root(self, store: Store) -> None:
        store.write("file.txt", b"data")
        assert store.is_folder("")
        assert list(store.list_files("")) == list(store.list_files("", recursive=False))

    @pytest.mark.spec("STORE-003")
    def test_root_path_prepended(self, store: Store) -> None:
        store.write("hello.txt", b"hi")
        assert store.exists("hello.txt")
        assert store.read_bytes("hello.txt") == b"hi"

    @pytest.mark.spec("STORE-005")
    def test_supports(self, store: Store) -> None:
        assert store.supports(Capability.READ) is True
        assert store.supports(Capability.WRITE) is True

    @pytest.mark.spec("STORE-004")
    def test_write_and_read(self, store: Store) -> None:
        store.write("test.txt", b"content")
        assert store.read_bytes("test.txt") == b"content"

    @pytest.mark.spec("STORE-004")
    def test_read_stream(self, store: Store) -> None:
        store.write("stream.txt", b"stream data")
        assert store.read("stream.txt").read() == b"stream data"


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

    @pytest.mark.spec("SAW-002")
    def test_open_atomic(self, store: Store) -> None:
        with store.open_atomic("oa.txt") as f:
            f.write(b"streaming")
        assert store.read_bytes("oa.txt") == b"streaming"

    @pytest.mark.spec("SAW-006")
    def test_open_atomic_overwrite(self, store: Store) -> None:
        store.write("oa_ow.txt", b"old")
        with store.open_atomic("oa_ow.txt", overwrite=True) as f:
            f.write(b"new")
        assert store.read_bytes("oa_ow.txt") == b"new"

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
        assert len(list(store.list_files("lfr", recursive=True))) == 2

    @pytest.mark.spec("STORE-008")
    def test_list_folders(self, store: Store) -> None:
        store.write("lfd/sub1/a.txt", b"a")
        store.write("lfd/sub2/b.txt", b"b")
        folders = list(store.list_folders("lfd"))
        assert all(isinstance(f, FolderEntry) for f in folders)
        assert {f.name for f in folders} == {"sub1", "sub2"}
        assert {str(f.path) for f in folders} == {"lfd/sub1", "lfd/sub2"}

    @pytest.mark.spec("STORE-008")
    def test_list_folders_child_store_rebases_path(self, store: Store) -> None:
        store.write("cr/sub/a.txt", b"a")
        child = store.child("cr")
        folders = list(child.list_folders(""))
        assert len(folders) == 1
        assert folders[0].name == "sub"
        assert str(folders[0].path) == "sub"

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


_MOVE_COPY_OPS = [pytest.param("move", id="move"), pytest.param("copy", id="copy")]


class TestStoreSamePathOps:
    """STORE-008a: move/copy same-path edge cases."""

    @pytest.mark.spec("STORE-008a")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    def test_same_path_is_noop(self, store: Store, op: str) -> None:
        store.write("same.txt", b"original")
        getattr(store, op)("same.txt", "same.txt")
        assert store.read_bytes("same.txt") == b"original"

    @pytest.mark.spec("STORE-008a")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    def test_same_path_nonexistent_raises(self, store: Store, op: str) -> None:
        with pytest.raises(NotFound):
            getattr(store, op)("ghost.txt", "ghost.txt")

    @pytest.mark.spec("STORE-008a")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    def test_same_path_folder_raises(self, store: Store, op: str) -> None:
        store.write("dir/file.txt", b"x")
        with pytest.raises(NotFound):
            getattr(store, op)("dir", "dir")


class TestStoreIterChildren:
    """ITER-001: iter_children() API."""

    @pytest.mark.spec("ITER-001")
    def test_iter_children(self, store: Store) -> None:
        store.write("ic/a.txt", b"a")
        store.write("ic/b.txt", b"b")
        store.write("ic/sub/c.txt", b"c")
        children = list(store.iter_children("ic"))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}
        assert {str(f.path) for f in folders} == {"ic/sub"}

    @pytest.mark.spec("ITER-001")
    def test_iter_children_child_store_rebases_path(self, store: Store) -> None:
        store.write("icc/sub/a.txt", b"a")
        child = store.child("icc")
        children = list(child.iter_children(""))
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert len(folders) == 1
        assert folders[0].name == "sub"
        assert str(folders[0].path) == "sub"

    @pytest.mark.spec("ITER-001")
    def test_iter_children_empty_dir(self, store: Store) -> None:
        assert list(store.iter_children("nonexistent")) == []

    @pytest.mark.spec("ITER-001")
    def test_iter_children_root(self, store: Store) -> None:
        store.write("root.txt", b"r")
        store.write("sub/nested.txt", b"n")
        children = list(store.iter_children(""))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"root.txt"}
        assert "sub" in {f.name for f in folders}

    @pytest.mark.spec("ITER-001")
    def test_iter_children_file_paths_are_store_relative(self, store: Store) -> None:
        store.write("ic2/f.txt", b"x")
        children = list(store.iter_children("ic2"))
        files = [c for c in children if isinstance(c, FileInfo)]
        assert len(files) == 1
        assert str(files[0].path) == "ic2/f.txt"
        assert store.read_bytes(str(files[0].path)) == b"x"


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
            assert len(store.read_bytes(str(f.path))) == 3

    @pytest.mark.spec("NPR-014")
    def test_list_files_no_root_prefix(self, store: Store) -> None:
        """FileInfo.path must NOT include the store's root_path."""
        store.write("file.txt", b"x")
        paths = {str(f.path) for f in store.list_files("")}
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
        assert store.read_bytes(str(fi.path)) == b"hello"

    @pytest.mark.spec("NPR-014")
    def test_get_folder_info_returns_store_relative(self, store: Store) -> None:
        store.write("fold/a.txt", b"a")
        assert str(store.get_folder_info("fold").path) == "fold"


def _assert_root_folder_info(fi: FolderInfo, *, count: int, size: int) -> None:
    """Shared assertions for root FolderInfo: type, counts, path identity."""
    assert isinstance(fi, FolderInfo)
    assert fi.file_count == count
    assert fi.total_size == size
    assert str(fi.path) == "."
    assert fi.path == RemotePath.ROOT
    assert fi.path is RemotePath.ROOT


class TestGetFolderInfoRoot:
    """BUG-001: get_folder_info('') must work for root folder."""

    def test_store_get_folder_info_empty_root(self) -> None:
        """Store with root_path='' should return root FolderInfo."""
        s = Store(backend=MemoryBackend(), root_path="")
        s.write("a.txt", b"aaa")
        _assert_root_folder_info(s.get_folder_info(""), count=1, size=3)

    def test_store_get_folder_info_with_root(self, store: Store) -> None:
        """Store with root_path='data' — get_folder_info('') returns root."""
        store.write("r.txt", b"rr")
        _assert_root_folder_info(store.get_folder_info(""), count=1, size=2)

    def test_backend_get_folder_info_empty_string(self) -> None:
        """Backend.get_folder_info('') should not raise InvalidPath."""
        backend = MemoryBackend()
        backend.write("x.txt", b"x")
        fi = backend.get_folder_info("")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 1
        assert str(fi.path) == "."
        assert fi.path is RemotePath.ROOT

    def test_root_path_round_trip_get_folder_info(self, store: Store) -> None:
        """str(get_folder_info('').path) round-trips as input to get_folder_info."""
        store.write("rt.txt", b"abc")
        fi = store.get_folder_info("")
        fi2 = store.get_folder_info(str(fi.path))
        assert fi2.file_count == fi.file_count
        assert fi2.path is RemotePath.ROOT

    def test_root_path_round_trip_list_files(self, store: Store) -> None:
        """str(get_folder_info('').path) round-trips as input to list_files."""
        store.write("rt.txt", b"abc")
        key = str(store.get_folder_info("").path)
        assert "rt.txt" in [str(f.path) for f in store.list_files(key)]

    def test_local_backend_get_folder_info_empty_string(self, tmp_path: Path) -> None:
        """LocalBackend.get_folder_info('') should not raise InvalidPath."""
        (tmp_path / "f.txt").write_bytes(b"hello")
        fi = LocalBackend(root=str(tmp_path)).get_folder_info("")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 1
        assert fi.total_size == 5
        assert str(fi.path) == "."
        assert fi.path is RemotePath.ROOT


class TestStoreToKey:
    """NPR-010 through NPR-013: Store.to_key."""

    @pytest.fixture
    def local_store(self, tmp_path: Path) -> tuple[Store, str]:
        real_tmp = str(tmp_path.resolve())
        return Store(backend=LocalBackend(root=str(tmp_path)), root_path="data"), real_tmp

    @pytest.mark.spec("NPR-010")
    def test_to_key_strips_root(self, local_store: tuple[Store, str]) -> None:
        s, real_tmp = local_store
        assert s.to_key(f"{real_tmp}/data/reports/q1.csv") == "reports/q1.csv"

    @pytest.mark.spec("NPR-012")
    def test_to_key_no_root_path(self, tmp_path: Path) -> None:
        real_tmp = str(tmp_path.resolve())
        s = Store(backend=LocalBackend(root=str(tmp_path)), root_path="")
        assert s.to_key(f"{real_tmp}/reports/q1.csv") == "reports/q1.csv"

    @pytest.mark.spec("NPR-013")
    def test_to_key_unrelated_path_raises(self, local_store: tuple[Store, str]) -> None:
        s, real_tmp = local_store
        with pytest.raises(InvalidPath):
            s.to_key(f"{real_tmp}/other/file.txt")


class TestStoreUnwrap:
    """STORE-013: Store.unwrap() delegation."""

    @pytest.mark.spec("STORE-013")
    @pytest.mark.parametrize(
        "use_child",
        [
            pytest.param(False, id="direct"),
            pytest.param(True, id="child"),
        ],
    )
    def test_unwrap_delegates_to_backend(self, use_child: bool) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        target = store.child("sub") if use_child else store
        with pytest.raises(CapabilityNotSupported):
            target.unwrap(dict)


class TestStoreNativePath:
    """STORE-015: Store.native_path() composition."""

    @pytest.mark.spec("STORE-015")
    @pytest.mark.parametrize(
        "root_path, child, key, expected",
        [
            pytest.param("data", None, "file.txt", "data/file.txt", id="with-root"),
            pytest.param("", None, "file.txt", "file.txt", id="no-root"),
            pytest.param("data", "sub", "file.txt", "data/sub/file.txt", id="child-store"),
            pytest.param("data", None, "", "data", id="root-key"),
        ],
    )
    def test_native_path(self, root_path: str, child: str | None, key: str, expected: str) -> None:
        backend = MemoryBackend()
        store = Store(backend=backend, root_path=root_path) if root_path else Store(backend=backend)
        if child:
            store = store.child(child)
        assert store.native_path(key) == expected


class TestStoreReadText:
    """RTXT-001: read_text() convenience method."""

    @pytest.mark.spec("RTXT-001")
    def test_read_text_utf8_default(self, store: Store) -> None:
        store.write("greet.txt", b"Hello, world!")
        assert store.read_text("greet.txt") == "Hello, world!"

    @pytest.mark.spec("RTXT-001")
    def test_read_text_custom_encoding(self, store: Store) -> None:
        text = "caf\u00e9"
        store.write("latin.txt", text.encode("latin-1"))
        assert store.read_text("latin.txt", encoding="latin-1") == text

    @pytest.mark.spec("RTXT-001")
    @pytest.mark.parametrize(
        "errors, check",
        [
            pytest.param("strict", "raises", id="strict-raises"),
            pytest.param("replace", "contains-replacement", id="replace"),
            pytest.param("ignore", "stripped", id="ignore"),
        ],
    )
    def test_read_text_error_handling(self, store: Store, errors: str, check: str) -> None:
        if check == "raises":
            store.write("bad.bin", b"\xff\xfe")
            with pytest.raises(UnicodeDecodeError):
                store.read_text("bad.bin")
        elif check == "contains-replacement":
            store.write("bad.bin", b"\xff\xfe")
            assert "\ufffd" in store.read_text("bad.bin", errors="replace")
        else:
            store.write("bad.bin", b"hello\xffworld")
            assert store.read_text("bad.bin", errors="ignore") == "helloworld"

    @pytest.mark.spec("RTXT-001")
    def test_read_text_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            store.read_text("missing.txt")

    @pytest.mark.spec("RTXT-001")
    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("", id="empty-path"),
            pytest.param(".", id="dot-path"),
        ],
    )
    def test_read_text_invalid_path(self, store: Store, path: str) -> None:
        with pytest.raises(InvalidPath):
            store.read_text(path)


class TestStoreWriteText:
    """WTXT-001: write_text() convenience method."""

    @pytest.mark.spec("WTXT-001")
    def test_write_text_utf8_default(self, store: Store) -> None:
        store.write_text("greet.txt", "Hello, world!")
        assert store.read_text("greet.txt") == "Hello, world!"

    @pytest.mark.spec("WTXT-001")
    def test_write_text_custom_encoding(self, store: Store) -> None:
        text = "caf\u00e9"
        store.write_text("latin.txt", text, encoding="latin-1")
        assert store.read_bytes("latin.txt") == text.encode("latin-1")

    @pytest.mark.spec("WTXT-001")
    def test_write_text_overwrite(self, store: Store) -> None:
        store.write_text("ow.txt", "old")
        store.write_text("ow.txt", "new", overwrite=True)
        assert store.read_text("ow.txt") == "new"

    @pytest.mark.spec("WTXT-001")
    def test_write_text_already_exists(self, store: Store) -> None:
        store.write_text("ow.txt", "first")
        with pytest.raises(AlreadyExists):
            store.write_text("ow.txt", "second")

    @pytest.mark.spec("WTXT-001")
    def test_write_text_bytes_rejected(self, store: Store) -> None:
        with pytest.raises(AttributeError):
            store.write_text("bad.txt", b"not a string")  # type: ignore[arg-type]

    @pytest.mark.spec("WTXT-001")
    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("", id="empty-path"),
            pytest.param(".", id="dot-path"),
        ],
    )
    def test_write_text_invalid_path(self, store: Store, path: str) -> None:
        with pytest.raises(InvalidPath):
            store.write_text(path, "text")

    @pytest.mark.spec("WTXT-001")
    def test_write_text_roundtrip(self, store: Store) -> None:
        store.write_text("rt.txt", "caf\u00e9", encoding="utf-8")
        assert store.read_bytes("rt.txt") == "caf\u00e9".encode()
