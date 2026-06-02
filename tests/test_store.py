"""Tests for Store — derived from sdd/specs/001-store-api.md (STORE sections)."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def store() -> Store:
    return Store(backend=MemoryBackend(), root_path="data")


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

    @pytest.mark.spec("STORE-005")
    def test_supports_atomic_move_true_for_memory(self) -> None:
        """Store.supports delegates to backend; MemoryBackend declares ATOMIC_MOVE."""
        store = Store(backend=MemoryBackend(), root_path="root")
        assert store.supports(Capability.ATOMIC_MOVE) is True

    @pytest.mark.spec("STORE-005")
    def test_supports_atomic_move_false_when_backend_lacks_it(self) -> None:
        """Store.supports returns False when the backend's CapabilitySet excludes ATOMIC_MOVE."""
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import CapabilitySet

        mock_backend = MagicMock(spec=Backend)
        mock_backend.capabilities = CapabilitySet(set(Capability) - {Capability.ATOMIC_MOVE})
        store = Store(backend=mock_backend, root_path="root")
        assert store.supports(Capability.ATOMIC_MOVE) is False

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
        result = store.delete("nonexistent.txt", missing_ok=True)
        assert result is None

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

    @pytest.mark.spec("STORE-008a", "BE-018", "BE-019", "BE-021")
    @pytest.mark.parametrize("op", _MOVE_COPY_OPS)
    def test_same_path_folder_raises_invalid_path(self, store: Store, op: str) -> None:
        """BK-227: self-op on a directory source raises InvalidPath, not NotFound."""
        store.write("dir/file.txt", b"x")
        with pytest.raises(InvalidPath, match=r"directory: dir"):
            getattr(store, op)("dir", "dir")


# BK-254: documented Store raises that were verified only against the raw
# Backend (tests/backends/conformance/test_errors.py), never through a Store.
# Store is a thin delegator, so these pin the contract at the consumer surface;
# the same-path move/copy edge cases live in TestStoreSamePathOps above, the
# empty/"." path shape in tests/test_coverage_gaps.py::test_empty_path_rejected,
# and read_text/read_seekable NotFound in TestStoreReadText / test_seekable.py.
# Each case carries the backend-contract clause it surfaces (BE-* from
# sdd/formal/BackendContract.dfy) alongside STORE-008 (the Store API surface),
# mirroring TestStoreSamePathOps' dual STORE-008a/BE-* tagging.


def _seed(store: Store, *paths: str) -> None:
    for path in paths:
        store.write(path, b"x")


_DELEGATED_RAISE_CASES = [
    # 1. move/copy cross-path NotFound (missing src) and AlreadyExists
    #    (existing dst, overwrite=False) — distinct src != dst.
    pytest.param(
        (),
        lambda s: s.move("dr_src.txt", "dr_dst.txt"),
        NotFound,
        "dr_src.txt",
        marks=pytest.mark.spec("BE-018"),
        id="move-missing-src-NotFound",
    ),
    pytest.param(
        (),
        lambda s: s.copy("dr_src.txt", "dr_dst.txt"),
        NotFound,
        "dr_src.txt",
        marks=pytest.mark.spec("BE-019"),
        id="copy-missing-src-NotFound",
    ),
    pytest.param(
        ("dr_src.txt", "dr_dst.txt"),
        lambda s: s.move("dr_src.txt", "dr_dst.txt"),
        AlreadyExists,
        "dr_dst.txt",
        marks=pytest.mark.spec("BE-018"),
        id="move-dst-exists-AlreadyExists",
    ),
    pytest.param(
        ("dr_src.txt", "dr_dst.txt"),
        lambda s: s.copy("dr_src.txt", "dr_dst.txt"),
        AlreadyExists,
        "dr_dst.txt",
        marks=pytest.mark.spec("BE-019"),
        id="copy-dst-exists-AlreadyExists",
    ),
    # 2. delete_folder: DirectoryNotEmpty (non-recursive on non-empty),
    #    NotFound, and file-target InvalidPath.
    pytest.param(
        ("dne/a.txt", "dne/b.txt"),
        lambda s: s.delete_folder("dne", recursive=False),
        DirectoryNotEmpty,
        "dne",
        marks=pytest.mark.spec("BE-013"),
        id="delete_folder-non_empty-DirectoryNotEmpty",
    ),
    pytest.param(
        (),
        lambda s: s.delete_folder("dfmissing"),
        NotFound,
        "dfmissing",
        marks=pytest.mark.spec("BE-013"),
        id="delete_folder-missing-NotFound",
    ),
    pytest.param(
        ("dffile.txt",),
        lambda s: s.delete_folder("dffile.txt"),
        InvalidPath,
        "dffile",
        marks=pytest.mark.spec("BE-013"),
        id="delete_folder-file_target-InvalidPath",
    ),
    # 3. read / read_bytes NotFound (only read_text / read_seekable have it today).
    pytest.param(
        (),
        lambda s: s.read("rmissing.txt"),
        NotFound,
        "rmissing",
        marks=pytest.mark.spec("BE-006"),
        id="read-missing-NotFound",
    ),
    pytest.param(
        (),
        lambda s: s.read_bytes("rbmissing.txt"),
        NotFound,
        "rbmissing",
        marks=pytest.mark.spec("BE-007"),
        id="read_bytes-missing-NotFound",
    ),
    # 4. get_file_info NotFound; get_folder_info NotFound on the max_depth=None
    #    branch (delegates straight to backend.get_folder_info, distinct from
    #    the depth branch covered in tests/test_depth_listing.py).
    pytest.param(
        (),
        lambda s: s.get_file_info("gfimissing.txt"),
        NotFound,
        "gfimissing",
        marks=pytest.mark.spec("BE-016"),
        id="get_file_info-missing-NotFound",
    ),
    pytest.param(
        (),
        lambda s: s.get_folder_info("gfomissing"),
        NotFound,
        "gfomissing",
        marks=pytest.mark.spec("BE-017"),
        id="get_folder_info-missing-NotFound-default-branch",
    ),
    # 5. InvalidPath-on-directory ("path names a directory") for the
    #    file-targeted ops read / read_bytes / delete / get_file_info — only the
    #    empty / "." path shape is asserted at Store today.
    pytest.param(
        ("adir/file.txt",),
        lambda s: s.read("adir"),
        InvalidPath,
        "adir",
        marks=pytest.mark.spec("BE-006"),
        id="read-directory-InvalidPath",
    ),
    pytest.param(
        ("adir/file.txt",),
        lambda s: s.read_bytes("adir"),
        InvalidPath,
        "adir",
        marks=pytest.mark.spec("BE-007"),
        id="read_bytes-directory-InvalidPath",
    ),
    pytest.param(
        ("adir/file.txt",),
        lambda s: s.delete("adir"),
        InvalidPath,
        "adir",
        marks=pytest.mark.spec("BE-012"),
        id="delete-directory-InvalidPath",
    ),
    pytest.param(
        ("adir/file.txt",),
        lambda s: s.get_file_info("adir"),
        InvalidPath,
        "adir",
        marks=pytest.mark.spec("BE-016"),
        id="get_file_info-directory-InvalidPath",
    ),
]


class TestStoreDelegatedRaises:
    """STORE-008: documented Store raises proven at the consumer surface (BK-254).

    Store delegates each of these to the backend; the conformance suite already
    pins the backend-contract postconditions (BE-*) on the raw Backend. These
    cases prove the same raises survive the Store delegation path (path
    validation, root prefixing, capability gating) for a real MemoryBackend.
    """

    @pytest.mark.spec("STORE-008")
    @pytest.mark.parametrize(("seed", "call", "exc", "match"), _DELEGATED_RAISE_CASES)
    def test_delegated_raise(
        self,
        store: Store,
        seed: tuple[str, ...],
        call: Callable[[Store], object],
        exc: type[Exception],
        match: str,
    ) -> None:
        _seed(store, *seed)
        with pytest.raises(exc, match=match):
            call(store)


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
        fi = s.get_folder_info("")
        _assert_root_folder_info(fi, count=1, size=3)
        assert fi.file_count == 1

    def test_store_get_folder_info_with_root(self, store: Store) -> None:
        """Store with root_path='data' — get_folder_info('') returns root."""
        store.write("r.txt", b"rr")
        fi = store.get_folder_info("")
        _assert_root_folder_info(fi, count=1, size=2)
        assert fi.file_count == 1

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
    @pytest.mark.spec("NPR-002")
    @pytest.mark.spec("NPR-011")
    @pytest.mark.spec("STORE-011")
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
    @pytest.mark.spec("NPR-022")
    @pytest.mark.parametrize(
        ("root_path", "child", "key", "expected"),
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
    @pytest.mark.spec("SIO-007")
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
        ("errors", "check"),
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
    @pytest.mark.spec("WTXT-006")
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


class TestListFilesDepthFilter:
    """STORE-depth-filter: list_files depth filter trims results beyond max_depth."""

    @pytest.mark.spec("STORE-012")
    def test_depth_filter_trims_files_beyond_max_depth(self, store: Store) -> None:
        """list_files with max_depth skips files at depth > max_depth."""
        store.write("a/b/shallow.txt", b"x")
        store.write("a/b/c/deep.txt", b"x")
        files = list(store.list_files("a", max_depth=1))
        names = {f.name for f in files}
        assert "shallow.txt" in names
        assert "deep.txt" not in names

    @pytest.mark.spec("WTXT-001")
    def test_write_text_roundtrip(self, store: Store) -> None:
        store.write_text("rt.txt", "caf\u00e9", encoding="utf-8")
        assert store.read_bytes("rt.txt") == "caf\u00e9".encode()


class TestWriteReturnsResult:
    """WR-001: write*() return WriteResult, not None."""

    @pytest.fixture
    def store(self) -> Store:
        return Store(backend=MemoryBackend(), root_path="data")

    @pytest.mark.spec("WR-001")
    @pytest.mark.parametrize(
        ("method", "args", "expected_size"),
        [
            ("write", ("f.bin", b"hello"), 5),
            ("write_text", ("f.txt", "hi"), 2),
            ("write_atomic", ("f.bin", b"atomic"), 6),
        ],
    )
    def test_write_methods_return_write_result(
        self,
        store: Store,
        method: str,
        args: tuple[object, ...],
        expected_size: int,
    ) -> None:
        from remote_store._models import WriteResult

        result = getattr(store, method)(*args)
        assert isinstance(result, WriteResult)
        assert result.size == expected_size


class TestStoreHead:
    """WR-008: Store.head() returns WriteResult with source='sidecar'."""

    @pytest.fixture
    def store(self) -> Store:
        return Store(backend=MemoryBackend(), root_path="data")

    @pytest.mark.spec("WR-008")
    @pytest.mark.spec("WR-006")
    def test_head_returns_sidecar_write_result(self, store: Store) -> None:
        from remote_store._models import WriteResult

        store.write("f.bin", b"abc")
        result = store.head("f.bin")
        assert isinstance(result, WriteResult)
        assert result.source == "sidecar"
        assert result.size == 3

    @pytest.mark.spec("WR-008")
    def test_head_raises_not_found(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound, match="missing"):
            store.head("missing.txt")

    @pytest.mark.spec("WR-008")
    def test_head_requires_metadata_capability(self) -> None:
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import CapabilitySet
        from remote_store._errors import CapabilityNotSupported

        mock_backend = MagicMock(spec=Backend)
        mock_backend.capabilities = CapabilitySet(set(Capability) - {Capability.METADATA})
        mock_backend.name = "mock"
        s = Store(backend=mock_backend)
        with pytest.raises(CapabilityNotSupported):
            s.head("f.bin")

    @pytest.mark.spec("WR-008")
    def test_head_path_is_store_relative(self, store: Store) -> None:
        from remote_store._path import RemotePath

        store.write("nested/f.bin", b"xy")
        result = store.head("nested/f.bin")
        assert result.path == RemotePath("nested/f.bin")

    @pytest.mark.spec("WR-008")
    def test_head_maps_all_fields(self) -> None:
        """digest, etag, last_modified, metadata all forwarded from FileInfo."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import CapabilitySet
        from remote_store._models import ContentDigest, FileInfo
        from remote_store._path import RemotePath

        digest = ContentDigest(algorithm="sha256", value="abc123")
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        info = FileInfo(
            path=RemotePath("data/f.bin"),
            name="f.bin",
            size=7,
            modified_at=ts,
            digest=digest,
            etag="etag-xyz",
            metadata={"k": "v"},
        )
        mock_backend = MagicMock(spec=Backend)
        mock_backend.name = "mock"
        mock_backend.capabilities = CapabilitySet(set(Capability))
        mock_backend.get_file_info.return_value = info
        s = Store(backend=mock_backend)
        result = s.head("f.bin")
        assert result.digest == digest
        assert result.etag == "etag-xyz"
        assert result.last_modified == ts
        assert result.metadata == {"k": "v"}


class TestMetadataGate:
    """WR-010, WR-011: metadata= validation and USER_METADATA capability gate."""

    @pytest.fixture
    def store(self) -> Store:
        return Store(backend=MemoryBackend(), root_path="data")

    @pytest.mark.spec("WR-011")
    def test_empty_metadata_passes_validation(self, store: Store) -> None:
        result = store.write("f.bin", b"x", metadata={})
        from remote_store._models import WriteResult

        assert isinstance(result, WriteResult)
        assert result.size == 1

    @pytest.mark.spec("WR-011")
    def test_metadata_nonempty_key_passes(self, store: Store) -> None:
        result = store.write("f.bin", b"x", metadata={"key": "value"})
        from remote_store._models import WriteResult

        assert isinstance(result, WriteResult)
        assert result.size == 1

    @pytest.mark.spec("WR-011")
    def test_metadata_empty_key_raises_value_error(self, store: Store) -> None:
        with pytest.raises(ValueError, match="empty"):
            store.write("f.bin", b"x", metadata={"": "value"})

    @pytest.mark.spec("WR-011")
    def test_metadata_leading_underscore_key_raises_value_error(self, store: Store) -> None:
        with pytest.raises(ValueError, match="underscore"):
            store.write("f.bin", b"x", metadata={"_secret": "value"})

    @pytest.mark.spec("WR-011")
    def test_metadata_non_ascii_key_raises_value_error(self, store: Store) -> None:
        with pytest.raises(ValueError, match="ASCII"):
            store.write("f.bin", b"x", metadata={"\u00e9cl\u00e9": "value"})

    @pytest.mark.spec("WR-011")
    def test_metadata_size_exceeds_2048_raises_value_error(self, store: Store) -> None:
        big = {"k": "v" * 2049}
        with pytest.raises(ValueError, match="2048"):
            store.write("f.bin", b"x", metadata=big)

    @pytest.mark.spec("WR-011")
    def test_metadata_size_at_boundary_passes(self, store: Store) -> None:
        """Payload of exactly 2048 bytes must not raise."""
        exact = {"k": "v" * (2048 - 1)}
        result = store.write("f.bin", b"x", metadata=exact)
        assert result.size == 1

    @pytest.mark.spec("WR-011")
    def test_metadata_non_str_key_raises_value_error(self, store: Store) -> None:
        with pytest.raises(ValueError, match="str"):
            store.write("f.bin", b"x", metadata={1: "value"})  # type: ignore[arg-type]

    @pytest.mark.spec("WR-011")
    def test_metadata_non_str_value_raises_value_error(self, store: Store) -> None:
        with pytest.raises(ValueError, match="str"):
            store.write("f.bin", b"x", metadata={"key": 42})  # type: ignore[dict-item]

    @pytest.mark.spec("WR-011")
    def test_metadata_validation_applies_to_write_atomic(self, store: Store) -> None:
        with pytest.raises(ValueError, match="underscore"):
            store.write_atomic("f.bin", b"x", metadata={"_bad": "v"})

    @pytest.mark.spec("WR-011")
    def test_metadata_validation_before_capability_check(self) -> None:
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import CapabilitySet

        mock_backend = MagicMock(spec=Backend)
        mock_backend.capabilities = CapabilitySet(
            set(Capability) - {Capability.USER_METADATA, Capability.GLOB, Capability.LAZY_READ}
        )
        mock_backend.name = "mock"
        s = Store(backend=mock_backend)
        with pytest.raises(ValueError, match="underscore"):
            s.write("f.bin", b"x", metadata={"_bad": "v"})

    @pytest.mark.spec("WR-010")
    def test_nonempty_metadata_without_capability_raises(self) -> None:
        from unittest.mock import patch

        from remote_store._capabilities import CapabilitySet
        from remote_store._errors import CapabilityNotSupported

        backend = MemoryBackend()
        caps = CapabilitySet(set(Capability) - {Capability.USER_METADATA, Capability.GLOB, Capability.LAZY_READ})
        with patch.object(type(backend), "capabilities", new_callable=lambda: property(lambda _: caps)):
            s = Store(backend=backend, root_path="data")
            with pytest.raises(CapabilityNotSupported):
                s.write("f.bin", b"x", metadata={"key": "val"})

    @pytest.mark.spec("WR-010")
    def test_empty_metadata_without_capability_allowed(self) -> None:
        from unittest.mock import patch

        from remote_store._capabilities import CapabilitySet

        backend = MemoryBackend()
        caps = CapabilitySet(set(Capability) - {Capability.USER_METADATA, Capability.GLOB, Capability.LAZY_READ})
        with patch.object(type(backend), "capabilities", new_callable=lambda: property(lambda _: caps)):
            s = Store(backend=backend, root_path="data")
            result = s.write("f.bin", b"x", metadata={})
            from remote_store._models import WriteResult

            assert isinstance(result, WriteResult)
            assert result.size == 1


class TestStoreEquality:
    """STORE-010: two Stores are equal iff they share the same backend instance and root."""

    @pytest.mark.spec("STORE-010")
    def test_equal_same_backend_and_root(self) -> None:
        backend = MemoryBackend()
        assert Store(backend=backend, root_path="data") == Store(backend=backend, root_path="data")

    @pytest.mark.spec("STORE-010")
    def test_not_equal_different_root(self) -> None:
        backend = MemoryBackend()
        assert Store(backend=backend, root_path="data") != Store(backend=backend, root_path="other")

    @pytest.mark.spec("STORE-010")
    def test_not_equal_different_backend_instance(self) -> None:
        # Same root, but distinct backend instances — not equal (identity, not value).
        assert Store(backend=MemoryBackend(), root_path="data") != Store(backend=MemoryBackend(), root_path="data")

    @pytest.mark.spec("STORE-010")
    def test_equal_stores_hash_equal(self) -> None:
        backend = MemoryBackend()
        a = Store(backend=backend, root_path="data")
        b = Store(backend=backend, root_path="data")
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


class TestStoreThreadSafety:
    """STORE-007: a single Store is safe to share across threads.

    Exercises the share-across-threads clause via concurrent reads on one shared
    Store (MemoryBackend serializes under a single lock, MEM-025). The companion
    *immutability* clause of STORE-007 is by-convention — Store exposes no public
    mutators and is not a frozen dataclass — so it has no raise to assert here.
    """

    @pytest.mark.spec("STORE-007")
    def test_shared_store_concurrent_reads(self) -> None:
        import threading

        store = Store(backend=MemoryBackend(), root_path="data")
        for i in range(20):
            store.write(f"f{i}.txt", f"data-{i}".encode())

        results: dict[int, bytes] = {}
        errors: list[Exception] = []

        def reader(idx: int) -> None:
            try:
                results[idx] = store.read_bytes(f"f{idx}.txt")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert all(results[i] == f"data-{i}".encode() for i in range(20))


class TestStoreCapabilityGates:
    """BE-011, ITER-002: capability-gated methods raise before delegating.

    Enforcement lives in ``Store._gate()`` (Backend does not gate directly, see
    _backend.py); the backend contract is therefore exercised through ``Store``.
    """

    @staticmethod
    @contextlib.contextmanager
    def _store_without(capability: Capability) -> Iterator[Store]:
        from unittest.mock import patch

        from remote_store._capabilities import CapabilitySet

        backend = MemoryBackend()
        caps = CapabilitySet(set(backend.capabilities) - {capability})
        with patch.object(type(backend), "capabilities", new_callable=lambda: property(lambda _: caps)):
            yield Store(backend=backend, root_path="data")

    @pytest.mark.spec("BE-011")
    @pytest.mark.spec("AW-002")
    @pytest.mark.spec("AW-007")
    def test_write_atomic_requires_atomic_write(self) -> None:
        # AW-002 (capability gate, checked before I/O) and AW-007 (never falls
        # back to a non-atomic write) are the same observable behaviour: the
        # call raises rather than silently degrading.
        with self._store_without(Capability.ATOMIC_WRITE) as store, pytest.raises(CapabilityNotSupported):
            store.write_atomic("f.txt", b"x")

    @pytest.mark.spec("ITER-002")
    def test_iter_children_requires_list(self) -> None:
        with self._store_without(Capability.LIST) as store, pytest.raises(CapabilityNotSupported):
            list(store.iter_children(""))
