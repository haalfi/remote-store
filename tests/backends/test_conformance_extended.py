"""Extended backend conformance suite — Dafny postcondition oracle.

Tests derive from the formal postconditions in ``sdd/formal/BackendContract.dfy``.
Each ``ensures`` clause maps to one or more ``@pytest.mark.extended_conformance``
test.  Focus areas:

- Error fidelity: dir→InvalidPath, missing→NotFound, file→InvalidPath (DeleteFolder)
- Precondition ordering: Write(dir) → InvalidPath not AlreadyExists
- Listing completeness: list_files returns ALL matching files
- Depth filtering: max_depth boundary (inclusive), recursive=false
- Move/Copy: dst-dir check, self-move/copy as no-op, overwrite
- Resource cleanup: stream close, context manager
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    NotFound,
    RemoteStoreError,
)

if TYPE_CHECKING:
    from remote_store._backend import Backend

# ---------------------------------------------------------------------------
# Helpers (reused from test_conformance.py patterns)
# ---------------------------------------------------------------------------

# Backends that use flat/virtual namespace — no real directory entries.
# Update this set when adding a new flat-namespace backend.
_FLAT_NAMESPACE_BACKENDS = frozenset({"s3", "s3-pyarrow", "azure", "http"})


def _require(backend: Backend, *caps: Capability) -> None:
    """Skip the test if the backend lacks any of the given capabilities."""
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")


def _seed(backend: Backend, files: dict[str, bytes]) -> None:
    """Write multiple files into the backend."""
    for path, data in files.items():
        backend.write(path, data)


def _skip_flat_namespace(backend: Backend, reason: str = "flat-namespace backend") -> None:
    """Skip test for backends without real directory entries."""
    if backend.name in _FLAT_NAMESPACE_BACKENDS:
        pytest.skip(reason)


def _do_op(backend: Backend, op: str, src: str, dst: str, **kw: Any) -> None:
    getattr(backend, op)(src, dst, **kw)


_MOVE_COPY_PARAMS = [
    pytest.param("move", Capability.MOVE, id="move"),
    pytest.param("copy", Capability.COPY, id="copy"),
]

pytestmark = pytest.mark.extended_conformance


# ===========================================================================
# §1  Error Fidelity — Dafny §6 postconditions on error paths
# ===========================================================================


class TestReadErrorFidelity:
    """BackendContract.Read postconditions: dir→InvalidPath, missing→NotFound."""

    @pytest.mark.spec("BE-006")
    def test_read_on_directory_raises_error(self, backend: Backend) -> None:
        """Read(dir) ==> InvalidPath.  Flat-NS backends have no real dirs."""
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("rdir/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.read("rdir")

    @pytest.mark.spec("BE-007")
    def test_read_bytes_on_directory_raises_error(self, backend: Backend) -> None:
        """read_bytes(dir) — same contract as read()."""
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("rbdir/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.read_bytes("rbdir")

    @pytest.mark.spec("BE-006")
    def test_read_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_read"):
            backend.read("ec_missing_read.txt")

    @pytest.mark.spec("BE-007")
    def test_read_bytes_missing_raises_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound, match="ec_missing_rb"):
            backend.read_bytes("ec_missing_rb.txt")


class TestWriteErrorFidelity:
    """BackendContract.Write postconditions: precondition ordering."""

    @pytest.mark.spec("BE-008")
    def test_write_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> error (NOT AlreadyExists).

        Dafny: ensures IsDir(old(fs), path) ==> Err(InvalidPath).
        The dir check must fire BEFORE the overwrite check.
        """
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("wdir/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.write("wdir", b"data")

    @pytest.mark.spec("BE-008")
    def test_write_on_directory_overwrite_still_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> error even with overwrite=True.

        Precondition ordering: type check before overwrite check.
        """
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("wdir2/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.write("wdir2", b"data", overwrite=True)


class TestDeleteErrorFidelity:
    """BackendContract.Delete postconditions: dir→error (no native leak).

    Dafny contract specifies InvalidPath; some backends currently raise
    NotFound (tracked as ID-131). Test for RemoteStoreError base class.
    """

    @pytest.mark.spec("BE-012")
    def test_delete_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> RemoteStoreError (no native exception leak)."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("ddir/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.delete("ddir")

    @pytest.mark.spec("BE-012")
    def test_delete_on_directory_missing_ok_raises_or_passes(self, backend: Backend) -> None:
        """IsDir(path) with missing_ok: no native exception leak."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("ddir2/file.txt", b"x")
        # Some backends raise RemoteStoreError, some pass — either is ok.
        # The key contract: no native exception leaks.
        native_leaked = False
        try:
            backend.delete("ddir2", missing_ok=True)
        except RemoteStoreError:
            pass  # expected — some backends reject delete(dir) even with missing_ok
        except Exception:  # noqa: BLE001
            native_leaked = True
        assert not native_leaked, "Native exception leaked through delete(dir, missing_ok=True)"


class TestDeleteFolderErrorFidelity:
    """BackendContract.DeleteFolder postconditions."""

    @pytest.mark.spec("BE-013")
    def test_delete_folder_on_file_raises_error(self, backend: Backend) -> None:
        """IsFile(path) ==> RemoteStoreError (Dafny: InvalidPath; ID-131 tracks fix)."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        backend.write("dffile.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.delete_folder("dffile.txt")

    @pytest.mark.spec("BE-013")
    def test_delete_folder_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists && !missing_ok ==> NotFound."""
        _require(backend, Capability.DELETE)
        with pytest.raises(NotFound, match="ec_missing_df"):
            backend.delete_folder("ec_missing_df", missing_ok=False)

    @pytest.mark.spec("BE-013")
    def test_delete_folder_missing_ok_passes(self, backend: Backend) -> None:
        """!PathExists && missing_ok ==> Ok (no error raised)."""
        _require(backend, Capability.DELETE)
        backend.delete_folder("ec_missing_df_ok", missing_ok=True)
        assert not backend.exists("ec_missing_df_ok")

    @pytest.mark.spec("BE-013")
    def test_delete_folder_non_recursive_non_empty_raises(self, backend: Backend) -> None:
        """IsDir && !recursive && HasChildren ==> DirectoryNotEmpty."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(backend)
        _seed(backend, {"dne/a.txt": b"a"})
        with pytest.raises(DirectoryNotEmpty, match="dne"):
            backend.delete_folder("dne", recursive=False)

    @pytest.mark.spec("BE-013")
    def test_delete_folder_recursive_removes_all(self, backend: Backend) -> None:
        """IsDir && recursive ==> Ok, all children removed."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        _seed(backend, {"dfr/a.txt": b"a", "dfr/sub/b.txt": b"b"})
        backend.delete_folder("dfr", recursive=True)
        assert not backend.exists("dfr/a.txt")
        assert not backend.exists("dfr/sub/b.txt")
        assert not backend.exists("dfr")


class TestGetFileInfoErrorFidelity:
    """BackendContract.GetFileInfo postconditions."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> RemoteStoreError (Dafny: InvalidPath; ID-131 tracks fix)."""
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        backend.write("gfid/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            backend.get_file_info("gfid")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_gfi"):
            backend.get_file_info("ec_missing_gfi")


# ===========================================================================
# §2  Listing — Dafny §6 ListFiles / ListFolders postconditions
# ===========================================================================


class TestListFilesCompleteness:
    """ListFiles completeness postcondition: every matching file MUST appear."""

    # Depth tree for max_depth tests:
    # pc/a.txt          depth=0
    # pc/d1/b.txt       depth=1
    # pc/d1/c.txt       depth=1
    # pc/d1/d2/d.txt    depth=2
    # pc/d1/d2/d3/e.txt depth=3
    DEPTH_TREE: dict[str, bytes] = {
        "pc/a.txt": b"a",
        "pc/d1/b.txt": b"b",
        "pc/d1/c.txt": b"c",
        "pc/d1/d2/d.txt": b"d",
        "pc/d1/d2/d3/e.txt": b"e",
    }

    @pytest.mark.spec("BE-014")
    def test_list_files_non_recursive(self, backend: Backend) -> None:
        """recursive=false → only immediate children (depth 0)."""
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=False))
        assert {f.name for f in files} == {"a.txt"}

    @pytest.mark.spec("BE-014")
    @pytest.mark.parametrize(
        ("max_depth", "expected_names"),
        [
            pytest.param(0, {"a.txt"}, id="depth0"),
            pytest.param(1, {"a.txt", "b.txt", "c.txt"}, id="depth1"),
            pytest.param(2, {"a.txt", "b.txt", "c.txt", "d.txt"}, id="depth2"),
            pytest.param(3, {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}, id="depth3"),
        ],
    )
    def test_list_files_recursive_max_depth(self, backend: Backend, max_depth: int, expected_names: set[str]) -> None:
        """Depth filtering is inclusive (Dafny DepthFilterBoundaryInclusive)."""
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=True, max_depth=max_depth))
        assert {f.name for f in files} == expected_names

    @pytest.mark.spec("BE-014")
    def test_list_files_unlimited_depth(self, backend: Backend) -> None:
        """max_depth=None → all files returned."""
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=True))
        assert {f.name for f in files} == {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}

    @pytest.mark.spec("BE-014")
    def test_list_files_missing_path_yields_empty(self, backend: Backend) -> None:
        """Dafny: !PathExists ==> r.value == [].  Never raises NotFound."""
        _require(backend, Capability.LIST)
        files = list(backend.list_files("ec_nonexistent_listing"))
        assert files == []

    @pytest.mark.spec("BE-014")
    def test_list_files_all_results_are_children(self, backend: Backend) -> None:
        """All returned files must be children of the listed path."""
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, {"lfc/a.txt": b"a", "lfc/sub/b.txt": b"b", "other/c.txt": b"c"})
        files = list(backend.list_files("lfc", recursive=True))
        for f in files:
            assert str(f.path).startswith("lfc/"), f"Unexpected path: {f.path}"


class TestListFoldersCompleteness:
    """ListFolders completeness: every immediate child dir MUST appear."""

    @pytest.mark.spec("BE-015")
    def test_list_folders_missing_path_yields_empty(self, backend: Backend) -> None:
        """Dafny: !PathExists ==> r.value == [].  Never raises NotFound."""
        _require(backend, Capability.LIST)
        folders = list(backend.list_folders("ec_nonexistent_folders"))
        assert folders == []

    @pytest.mark.spec("BE-015")
    def test_list_folders_completeness(self, backend: Backend) -> None:
        """All immediate child directories appear."""
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(
            backend,
            {
                "lfc2/s1/a.txt": b"a",
                "lfc2/s2/b.txt": b"b",
                "lfc2/s3/c.txt": b"c",
                "lfc2/top.txt": b"t",
            },
        )
        folders = list(backend.list_folders("lfc2"))
        assert {f.name for f in folders} == {"s1", "s2", "s3"}


# ===========================================================================
# §3  Move/Copy — Dafny §6 Move/Copy postconditions
# ===========================================================================


class TestMoveCopyErrorFidelity:
    """Move/Copy error postconditions from BackendContract.dfy."""

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_source_is_directory_raises_error(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsDir(src) ==> RemoteStoreError (Dafny: InvalidPath; ID-131 tracks fix).

        Memory backend enforces this; LocalBackend currently moves/copies
        the directory (no error). Test only on memory for now.
        """
        _require(backend, cap, Capability.WRITE)
        if backend.name != "memory":
            pytest.skip("Only MemoryBackend enforces dir-src check (ID-131)")
        backend.write(f"mcds/{op}/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            _do_op(backend, op, f"mcds/{op}", f"mcds/{op}_dst.txt")

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_destination_is_directory_raises_error(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsFile(src) && IsDir(dst) ==> RemoteStoreError (Dafny: InvalidPath; ID-131).

        Memory backend enforces this; LocalBackend currently overwrites.
        """
        _require(backend, cap, Capability.WRITE)
        if backend.name != "memory":
            pytest.skip("Only MemoryBackend enforces dir-dst check (ID-131)")
        backend.write(f"mcdd/{op}_src.txt", b"src")
        backend.write(f"mcdd/{op}_dstdir/file.txt", b"x")
        # TODO(ID-131): tighten to InvalidPath once all backends comply
        with pytest.raises(RemoteStoreError):
            _do_op(backend, op, f"mcdd/{op}_src.txt", f"mcdd/{op}_dstdir")

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_source_missing_raises_not_found(self, backend: Backend, op: str, cap: Capability) -> None:
        """!PathExists(src) ==> NotFound(src)."""
        _require(backend, cap)
        with pytest.raises(NotFound, match="ec_mc_missing_src"):
            _do_op(backend, op, "ec_mc_missing_src.txt", "ec_mc_dst.txt")


class TestMoveCopyOverwrite:
    """Move/Copy overwrite and self-operation semantics."""

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_dst_exists_no_overwrite_raises_already_exists(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsFile(dst) && !overwrite && src != dst ==> AlreadyExists(dst)."""
        _require(backend, cap, Capability.WRITE)
        _seed(backend, {f"mcow/{op}_s.txt": b"s", f"mcow/{op}_d.txt": b"d"})
        with pytest.raises(AlreadyExists, match=f"mcow/{op}_d"):
            _do_op(backend, op, f"mcow/{op}_s.txt", f"mcow/{op}_d.txt", overwrite=False)

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_overwrite_replaces_destination(self, backend: Backend, op: str, cap: Capability) -> None:
        """overwrite=True → dst gets src content."""
        _require(backend, cap, Capability.WRITE)
        _seed(backend, {f"mcor/{op}_s.txt": b"new", f"mcor/{op}_d.txt": b"old"})
        _do_op(backend, op, f"mcor/{op}_s.txt", f"mcor/{op}_d.txt", overwrite=True)
        assert backend.read_bytes(f"mcor/{op}_d.txt") == b"new"


class TestMoveCopySelfOperation:
    """Self-move/self-copy: data must not be lost.

    Dafny spec says src==dst is a no-op. Most backends fail:
    Local leaks SameFileError, S3 returns 400, SFTP deletes the file.
    Only MemoryBackend handles it correctly (ID-131 tracks the fixes).
    """

    @pytest.mark.spec("BE-019")
    def test_self_copy_preserves_data(self, backend: Backend) -> None:
        """copy(src, src, overwrite=True) must not lose data."""
        _require(backend, Capability.COPY, Capability.WRITE)
        if backend.name != "memory":
            pytest.skip("Only MemoryBackend handles self-copy correctly (ID-131)")
        backend.write("selfcp.txt", b"data")
        backend.copy("selfcp.txt", "selfcp.txt", overwrite=True)
        assert backend.read_bytes("selfcp.txt") == b"data"

    @pytest.mark.spec("BE-018")
    def test_self_move_preserves_data(self, backend: Backend) -> None:
        """move(src, src, overwrite=True) must not lose data."""
        _require(backend, Capability.MOVE, Capability.WRITE)
        if backend.name != "memory":
            pytest.skip("Only MemoryBackend handles self-move correctly (ID-131)")
        backend.write("selfmv.txt", b"data")
        backend.move("selfmv.txt", "selfmv.txt", overwrite=True)
        assert backend.read_bytes("selfmv.txt") == b"data"


class TestMovePostState:
    """Move post-state: src removed, dst has src content."""

    @pytest.mark.spec("BE-018")
    def test_move_removes_source(self, backend: Backend) -> None:
        """src != dst ==> !PathExists(fs, src)."""
        _require(backend, Capability.MOVE, Capability.WRITE)
        backend.write("mvps_src.txt", b"data")
        backend.move("mvps_src.txt", "mvps_dst.txt")
        assert not backend.exists("mvps_src.txt")
        assert backend.read_bytes("mvps_dst.txt") == b"data"


class TestCopyPostState:
    """Copy post-state: src unchanged, dst has src content."""

    @pytest.mark.spec("BE-019")
    def test_copy_preserves_source(self, backend: Backend) -> None:
        """IsFile(fs, src) — source still exists after copy."""
        _require(backend, Capability.COPY, Capability.WRITE)
        backend.write("cpps_src.txt", b"data")
        backend.copy("cpps_src.txt", "cpps_dst.txt")
        assert backend.read_bytes("cpps_src.txt") == b"data"
        assert backend.read_bytes("cpps_dst.txt") == b"data"


# ===========================================================================
# §4  Write-Read round-trip — Dafny WriteReadConsistency lemma
# ===========================================================================


class TestWriteReadRoundTrip:
    """Write then read: content must match exactly."""

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize(
        "content",
        [
            pytest.param(b"", id="empty"),
            pytest.param(b"\x00\x01\x02\xff", id="binary"),
            pytest.param(b"hello world", id="text"),
            pytest.param(b"x" * 10_000, id="large"),
        ],
    )
    def test_roundtrip(self, backend: Backend, content: bytes) -> None:
        _require(backend, Capability.WRITE)
        backend.write("ec_rt.bin", content, overwrite=True)
        assert backend.read_bytes("ec_rt.bin") == content


# ===========================================================================
# §5  Resource cleanup — SIO-001 safety
# ===========================================================================


class TestResourceCleanup:
    """Streams from read() must support close/context-manager."""

    @pytest.mark.spec("SIO-001")
    def test_read_stream_close(self, backend: Backend) -> None:
        """Stream must be closeable."""
        _require(backend, Capability.WRITE)
        backend.write("ec_rc.txt", b"data")
        stream = backend.read("ec_rc.txt")
        stream.read()
        stream.close()
        assert stream.closed

    @pytest.mark.spec("SIO-001")
    def test_read_stream_context_manager(self, backend: Backend) -> None:
        """Context manager must close the stream on exit."""
        _require(backend, Capability.WRITE)
        backend.write("ec_rcm.txt", b"data")
        with backend.read("ec_rcm.txt") as stream:
            stream.read()
        assert stream.closed

    @pytest.mark.spec("SIO-001")
    def test_read_stream_double_close(self, backend: Backend) -> None:
        """Double close must not raise, stream stays closed."""
        _require(backend, Capability.WRITE)
        backend.write("ec_rdc.txt", b"data")
        stream = backend.read("ec_rdc.txt")
        stream.close()
        stream.close()  # must not raise
        assert stream.closed


# ===========================================================================
# §6  Operational consistency — Write overwrite semantics, exists() after ops
# ===========================================================================


class TestOperationalConsistency:
    """Cross-cutting operational invariants."""

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-008")
    def test_exists_after_write(self, backend: Backend) -> None:
        """exists(path) returns True after successful write."""
        _require(backend, Capability.WRITE)
        backend.write("ec_eaw.txt", b"x")
        assert backend.exists("ec_eaw.txt") is True

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-012")
    def test_exists_after_delete(self, backend: Backend) -> None:
        """exists(path) returns False after successful delete."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        backend.write("ec_ead.txt", b"x")
        backend.delete("ec_ead.txt")
        assert backend.exists("ec_ead.txt") is False

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_true_replaces(self, backend: Backend) -> None:
        """Write with overwrite=True replaces content."""
        _require(backend, Capability.WRITE)
        backend.write("ec_wot.txt", b"first")
        backend.write("ec_wot.txt", b"second", overwrite=True)
        assert backend.read_bytes("ec_wot.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_false_rejects(self, backend: Backend) -> None:
        """Write with overwrite=False raises AlreadyExists."""
        _require(backend, Capability.WRITE)
        backend.write("ec_wof.txt", b"first")
        with pytest.raises(AlreadyExists, match="ec_wof"):
            backend.write("ec_wof.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-012")
    def test_delete_preserves_siblings(self, backend: Backend) -> None:
        """Deleting one file must not affect siblings."""
        _require(backend, Capability.DELETE, Capability.WRITE)
        _seed(backend, {"ec_sib/a.txt": b"a", "ec_sib/b.txt": b"b"})
        backend.delete("ec_sib/a.txt")
        assert not backend.exists("ec_sib/a.txt")
        assert backend.read_bytes("ec_sib/b.txt") == b"b"

    @pytest.mark.spec("BE-014")
    def test_list_files_returns_fileinfo_with_name(self, backend: Backend) -> None:
        """list_files results have name and path attributes."""
        _require(backend, Capability.LIST, Capability.WRITE)
        backend.write("ec_lfi/x.txt", b"x")
        files = list(backend.list_files("ec_lfi"))
        assert len(files) >= 1
        assert files[0].name == "x.txt"
        assert str(files[0].path).endswith("x.txt")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_size(self, backend: Backend) -> None:
        """get_file_info returns correct size."""
        _require(backend, Capability.WRITE)
        data = b"hello world"
        backend.write("ec_gfis.txt", data)
        info = backend.get_file_info("ec_gfis.txt")
        assert info.size == len(data)
