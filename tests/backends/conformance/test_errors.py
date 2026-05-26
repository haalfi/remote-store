"""Error fidelity conformance: read/write/delete/move/copy paths.

Each class targets a specific Dafny postcondition section. Class-level
filters apply the minimum capability; ``_skip_flat_namespace()`` keeps
identity-based skipping for backends with no real directory entries.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from tests.backends.conformance._helpers import (
    _MOVE_COPY_PARAMS,
    _do_op,
    _fixture_record,
    _require,
    _seed,
    _skip_flat_namespace,
)
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


pytestmark = pytest.mark.extended_conformance


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestReadErrorFidelity:
    """BackendContract.Read postconditions: dir->InvalidPath, missing->NotFound."""

    @pytest.mark.spec("BE-006")
    def test_read_on_directory_raises_error(self, backend: Backend) -> None:
        """Read(dir) ==> InvalidPath.  Flat-NS backends have no real dirs."""
        _skip_flat_namespace(backend)
        backend.write("rdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="rdir"):
            backend.read("rdir")

    @pytest.mark.spec("BE-007")
    def test_read_bytes_on_directory_raises_error(self, backend: Backend) -> None:
        """read_bytes(dir): same contract as read()."""
        _skip_flat_namespace(backend)
        backend.write("rbdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="rbdir"):
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

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-007")
    @pytest.mark.parametrize("method", ["read", "read_bytes"])
    def test_read_under_file_ancestor_raises_not_found(self, backend: Backend, method: str) -> None:
        """ID-209 round-2: a path under a file-ancestor is not in ``fs`` per
        the Dafny model, so BE-006 / BE-007's ``!PathExists ==> NotFound``
        applies — not the writer-side ``InvalidPath`` clause from BE-008.
        Pre-PR LocalBackend leaked ``NotADirectoryError`` and SFTPBackend
        (after round 1) returned ``InvalidPath``; both now return
        ``NotFound`` matching MemoryBackend.
        """
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-210)",
        )
        backend.write("rufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="rufa.txt"):
            getattr(backend, method)("rufa.txt/child.txt")


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestWriteErrorFidelity:
    """BackendContract.Write postconditions: precondition ordering."""

    @pytest.mark.spec("BE-008")
    def test_write_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> InvalidPath (NOT AlreadyExists)."""
        _skip_flat_namespace(backend)
        backend.write("wdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="wdir"):
            backend.write("wdir", b"data")

    @pytest.mark.spec("BE-008")
    def test_write_on_directory_overwrite_still_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> InvalidPath even with overwrite=True."""
        _skip_flat_namespace(backend)
        backend.write("wdir2/file.txt", b"x")
        with pytest.raises(InvalidPath, match="wdir2"):
            backend.write("wdir2", b"data", overwrite=True)

    @pytest.mark.parametrize(
        ("method", "cap"),
        [
            pytest.param("write", Capability.WRITE, id="write", marks=pytest.mark.spec("BE-008")),
            pytest.param(
                "write_atomic",
                Capability.ATOMIC_WRITE,
                id="write_atomic",
                marks=pytest.mark.spec("BE-008"),
            ),
        ],
    )
    def test_write_under_file_ancestor_raises_invalid_path(
        self, backend: Backend, method: str, cap: Capability
    ) -> None:
        """ID-209: !AllAncestorsTraversable(old(fs), path) ==> InvalidPath.

        Mirrors the new Dafny Write postcondition that closes ID-184's
        trait-totality gap.  Parametrised over ``write`` and ``write_atomic``
        — BE-010 routes ``write_atomic`` through the same BE-008 precondition
        chain, so the file-ancestor InvalidPath promise applies to both.
        Hierarchical backends (Local, SFTP, Memory) natively reject the
        second write because EnsureParents / mkdir / sftp.mkdir cannot
        descend through a regular-file path component.  Flat-namespace
        backends (S3, Azure non-HNS, SQLBlob, HTTP) skip via
        ``_skip_flat_namespace`` — they cannot distinguish the case in
        O(1) without an extra HEAD round trip and are tracked under
        ID-210 (the HEAD-pre-check follow-up).
        """
        _require(backend, cap)
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot reject write-under-file in O(1) (ID-210)",
        )
        seed = f"wufa_{method}.txt"
        nested = f"{seed}/child.txt"
        backend.write(seed, b"file-blocking")
        with pytest.raises(InvalidPath, match=seed):
            getattr(backend, method)(nested, b"under-file")
        # Original file unaffected.
        assert backend.read_bytes(seed) == b"file-blocking"

    @pytest.mark.spec("BE-008")
    @pytest.mark.spec("SAW-001")
    def test_open_atomic_under_file_ancestor_raises_invalid_path(self, backend: Backend) -> None:
        """ID-209: ``open_atomic`` shares BE-008's precondition chain (BE-010 / SAW-001)."""
        _require(backend, Capability.ATOMIC_WRITE)
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot reject write-under-file in O(1) (ID-210)",
        )
        backend.write("wufa_oa.txt", b"file-blocking")
        with pytest.raises(InvalidPath, match="wufa_oa.txt"), backend.open_atomic("wufa_oa.txt/child.txt") as f:
            f.write(b"under-file")
        assert backend.read_bytes("wufa_oa.txt") == b"file-blocking"


@pytest.mark.parametrize("backend", fixture_params(Capability.DELETE, Capability.WRITE), indirect=True)
class TestDeleteErrorFidelity:
    """BackendContract.Delete postconditions: dir->InvalidPath."""

    @pytest.mark.spec("BE-012")
    def test_delete_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> InvalidPath (no native exception leak)."""
        _skip_flat_namespace(backend)
        backend.write("ddir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir"):
            backend.delete("ddir")

    @pytest.mark.spec("BE-012")
    def test_delete_on_directory_missing_ok_still_raises(self, backend: Backend) -> None:
        """IsDir(path) with missing_ok: type mismatch is not 'missing', still InvalidPath."""
        _skip_flat_namespace(backend)
        backend.write("ddir2/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir2"):
            backend.delete("ddir2", missing_ok=True)
        assert backend.exists("ddir2/file.txt"), "Child file was silently deleted"

    @pytest.mark.spec("BE-012")
    def test_delete_under_file_ancestor_raises_not_found(self, backend: Backend) -> None:
        """ID-209 round-2: file-ancestor path is not in ``fs``, so BE-012's
        ``!PathExists ==> NotFound`` applies — not the type-mismatch
        ``InvalidPath`` clause.  Symmetric with ``read`` / ``read_bytes``.
        """
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-210)",
        )
        backend.write("dufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="dufa.txt"):
            backend.delete("dufa.txt/child.txt")
        # missing_ok=True: file-ancestor is "missing", not "wrong type" — so the
        # call must succeed quietly (no exception), matching the Dafny
        # ``!PathExists ∧ missing_ok ==> Ok`` clause.
        backend.delete("dufa.txt/child.txt", missing_ok=True)
        # Blocker unaffected by either call.
        assert backend.read_bytes("dufa.txt") == b"file-blocking"


@pytest.mark.parametrize("backend", fixture_params(Capability.DELETE), indirect=True)
class TestDeleteFolderErrorFidelity:
    """BackendContract.DeleteFolder postconditions."""

    @pytest.mark.spec("BE-013")
    def test_delete_folder_on_file_raises_error(self, backend: Backend) -> None:
        """IsFile(path) ==> InvalidPath (Dafny: InvalidPath)."""
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend, "flat-namespace backends cannot distinguish file vs folder")
        backend.write("dffile.txt", b"x")
        with pytest.raises(InvalidPath, match="dffile"):
            backend.delete_folder("dffile.txt")

    @pytest.mark.spec("BE-013")
    def test_delete_folder_on_file_no_native_leak(self, backend: Backend) -> None:
        """Flat-namespace backends: delete_folder(file) must not leak native exceptions."""
        _require(backend, Capability.WRITE)
        if not _fixture_record(backend).flat_namespace:
            pytest.skip("hierarchical backend; covered by test_delete_folder_on_file_raises_error")
        backend.write("dffile_flat.txt", b"x")
        with contextlib.suppress(RemoteStoreError):
            backend.delete_folder("dffile_flat.txt")
        # File may or may not still exist; the test passed if no non-RemoteStoreError leaked.
        assert True  # explicit: survived without native exception leak

    @pytest.mark.spec("BE-013")
    @pytest.mark.spec("SFTP-016")
    def test_delete_folder_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists && !missing_ok ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_df"):
            backend.delete_folder("ec_missing_df", missing_ok=False)

    @pytest.mark.spec("BE-013")
    def test_delete_folder_missing_ok_passes(self, backend: Backend) -> None:
        """!PathExists && missing_ok ==> Ok (no error raised)."""
        backend.delete_folder("ec_missing_df_ok", missing_ok=True)
        assert not backend.exists("ec_missing_df_ok")

    @pytest.mark.spec("BE-013")
    @pytest.mark.spec("SFTP-017")
    def test_delete_folder_non_recursive_non_empty_raises(self, backend: Backend) -> None:
        """IsDir && !recursive && HasChildren ==> DirectoryNotEmpty."""
        _require(backend, Capability.WRITE)
        _skip_flat_namespace(backend)
        _seed(backend, {"dne/a.txt": b"a"})
        with pytest.raises(DirectoryNotEmpty, match="dne"):
            backend.delete_folder("dne", recursive=False)

    @pytest.mark.spec("BE-013")
    def test_delete_folder_recursive_removes_all(self, backend: Backend) -> None:
        """IsDir && recursive ==> Ok, all children removed."""
        _require(backend, Capability.WRITE)
        _seed(backend, {"dfr/a.txt": b"a", "dfr/sub/b.txt": b"b"})
        backend.delete_folder("dfr", recursive=True)
        assert not backend.exists("dfr/a.txt")
        assert not backend.exists("dfr/sub/b.txt")
        assert not backend.exists("dfr")

    @pytest.mark.spec("BE-013")
    def test_delete_folder_recursive_no_child_survives(self, backend: Backend) -> None:
        """ID-184 (T-side): the Dafny ``forall p | IsChildOf(p, path) ::
        !PathExists(fs, p)`` quantifier — no file under the deleted prefix
        survives the recursive delete. Sibling of
        ``test_delete_folder_recursive_removes_all`` whose named-path checks
        only spot-check the seed; this ``list_files`` scan extends the
        coverage to anything else the backend might have left behind under
        ``dfrls/``. The distinct prefix (vs ``dfr/`` in the sibling test)
        keeps the new test free of cassette cross-talk so its unrecorded
        ``azure_replay`` cassette self-skips cleanly.
        """
        _require(backend, Capability.WRITE, Capability.LIST)
        _seed(backend, {"dfrls/a.txt": b"a", "dfrls/sub/b.txt": b"b"})
        backend.delete_folder("dfrls", recursive=True)
        assert list(backend.list_files("dfrls", recursive=True)) == []


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestGetFileInfoErrorFidelity:
    """BackendContract.GetFileInfo postconditions."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info_on_directory_raises_error(self, backend: Backend) -> None:
        """IsDir(path) ==> InvalidPath (Dafny: InvalidPath)."""
        _skip_flat_namespace(backend)
        backend.write("gfid/file.txt", b"x")
        with pytest.raises(InvalidPath, match="gfid"):
            backend.get_file_info("gfid")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_gfi"):
            backend.get_file_info("ec_missing_gfi")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_under_file_ancestor_raises_not_found(self, backend: Backend) -> None:
        """ID-209 round-2: file-ancestor path → NotFound (read-side semantics)."""
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-210)",
        )
        backend.write("gfufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="gfufa.txt"):
            backend.get_file_info("gfufa.txt/child.txt")


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestGetFolderInfoErrorFidelity:
    """BackendContract.GetFolderInfo postconditions."""

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_on_file_raises_error(self, backend: Backend) -> None:
        """IsFile(path) ==> InvalidPath (Dafny: InvalidPath)."""
        _skip_flat_namespace(backend)
        backend.write("gfof.txt", b"x")
        with pytest.raises(InvalidPath, match="gfof"):
            backend.get_folder_info("gfof.txt")

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_missing_raises_not_found(self, backend: Backend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_gfo"):
            backend.get_folder_info("ec_missing_gfo")


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestMoveCopyErrorFidelity:
    """Move/Copy error postconditions from BackendContract.dfy."""

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_source_is_directory_raises_error(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsDir(src) ==> InvalidPath (Dafny: InvalidPath)."""
        _require(backend, cap)
        _skip_flat_namespace(backend)
        backend.write(f"mcds/{op}/file.txt", b"x")
        with pytest.raises(InvalidPath, match=f"mcds/{op}(?!_dst)"):
            _do_op(backend, op, f"mcds/{op}", f"mcds/{op}_dst.txt")

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_destination_is_directory_raises_error(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsFile(src) && IsDir(dst) ==> InvalidPath (Dafny: InvalidPath)."""
        _require(backend, cap)
        _skip_flat_namespace(backend)
        backend.write(f"mcdd/{op}_src.txt", b"src")
        backend.write(f"mcdd/{op}_dstdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match=f"mcdd/{op}_dstdir"):
            _do_op(backend, op, f"mcdd/{op}_src.txt", f"mcdd/{op}_dstdir")

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_source_missing_raises_not_found(self, backend: Backend, op: str, cap: Capability) -> None:
        """!PathExists(src) ==> NotFound(src)."""
        _require(backend, cap)
        with pytest.raises(NotFound, match="ec_mc_missing_src"):
            _do_op(backend, op, "ec_mc_missing_src.txt", "ec_mc_dst.txt")

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_destination_under_file_ancestor_raises_invalid_path(
        self, backend: Backend, op: str, cap: Capability
    ) -> None:
        """ID-209: ``!AllAncestorsTraversable(old(fs), dst)`` ==> ``InvalidPath(dst)``.

        Mirror of the BE-008 file-ancestor clause on the dst side of
        move/copy.  Same flat-namespace skip rationale as the write test:
        ID-210 tracks the optional HEAD pre-check follow-up for flat-NS
        backends.
        """
        _require(backend, cap)
        _skip_flat_namespace(
            backend,
            "flat-namespace backends cannot reject move/copy-under-file in O(1) (ID-210)",
        )
        backend.write(f"mcua/{op}_blocker.txt", b"file-blocking")
        backend.write(f"mcua/{op}_src.txt", b"srcdata")
        with pytest.raises(InvalidPath, match=f"mcua/{op}_blocker.txt"):
            _do_op(backend, op, f"mcua/{op}_src.txt", f"mcua/{op}_blocker.txt/dst.txt")
        # Blocker and source both unaffected.
        assert backend.read_bytes(f"mcua/{op}_blocker.txt") == b"file-blocking"
        assert backend.read_bytes(f"mcua/{op}_src.txt") == b"srcdata"
