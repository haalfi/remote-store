"""Backend conformance suite — tests BE-xxx specs against any backend."""

from __future__ import annotations

import io
from typing import Any

import pytest

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult


def _require(backend: Backend, *caps: Capability) -> None:
    """Skip the test if the backend lacks any of the given capabilities."""
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")


def _do_op(backend: Backend, op: str, src: str, dst: str, **kw: Any) -> None:
    getattr(backend, op)(src, dst, **kw)


def _seed(backend: Backend, files: dict[str, bytes]) -> None:
    """Write multiple files into the backend."""
    for path, data in files.items():
        backend.write(path, data)


_MOVE_COPY_PARAMS = [
    pytest.param("move", Capability.MOVE, id="move"),
    pytest.param("copy", Capability.COPY, id="copy"),
]


class TestBackendIdentity:
    """BE-001 through BE-003: backend identity and capabilities."""

    @pytest.mark.spec("BE-001")
    def test_backend_is_instance(self, backend: Backend) -> None:
        assert isinstance(backend, Backend)

    @pytest.mark.spec("BE-002")
    def test_name_is_string(self, backend: Backend) -> None:
        assert isinstance(backend.name, str)
        assert len(backend.name) > 0

    @pytest.mark.spec("BE-003")
    def test_capabilities_is_capabilityset(self, backend: Backend) -> None:
        assert isinstance(backend.capabilities, CapabilitySet)

    def test_repr_returns_string(self, backend: Backend) -> None:
        r = repr(backend)
        assert isinstance(r, str)
        assert backend.name in r.lower() or backend.__class__.__name__ in r

    def test_repr_masks_secrets(self, backend: Backend) -> None:
        """AF-008: sensitive values must not appear in repr output."""
        r = repr(backend)
        for secret in ("testing", "testpass", "Eby8vdM02xNOcqFlqUwJPLlmEtl"):
            assert secret not in r, f"Secret {secret!r} leaked in repr: {r}"


class TestBackendExists:
    """BE-004: exists() behavior."""

    @pytest.mark.spec("BE-004")
    def test_false_for_missing(self, backend: Backend) -> None:
        assert backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("BE-004")
    def test_true_after_write(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("hello.txt", b"hello")
        assert backend.exists("hello.txt") is True


class TestBackendFileFolder:
    """BE-005: is_file() / is_folder() distinction."""

    @pytest.mark.spec("BE-005")
    def test_is_file(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("a.txt", b"data")
        assert backend.is_file("a.txt") is True
        assert backend.is_folder("a.txt") is False

    @pytest.mark.spec("BE-005")
    def test_is_folder(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("dir/a.txt", b"data")
        assert backend.is_folder("dir") is True
        assert backend.is_file("dir") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("is_file", id="is_file"), pytest.param("is_folder", id="is_folder")],
    )
    def test_false_for_missing(self, backend: Backend, method: str) -> None:
        assert getattr(backend, method)("nope") is False


class TestBackendRead:
    """BE-006 through BE-007: read operations."""

    @pytest.mark.spec("BE-006")
    def test_read_returns_binary_stream(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("data.bin", b"\x00\x01\x02")
        with backend.read("data.bin") as stream:
            assert stream.read() == b"\x00\x01\x02"

    @pytest.mark.spec("BE-007")
    def test_read_bytes(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("file.txt", b"content")
        assert backend.read_bytes("file.txt") == b"content"

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-007")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("read", id="read_stream"), pytest.param("read_bytes", id="read_bytes")],
    )
    def test_not_found(self, backend: Backend, method: str) -> None:
        with pytest.raises(NotFound):
            getattr(backend, method)("missing.txt")


class TestBackendWrite:
    """BE-008 through BE-009: write operations."""

    @pytest.mark.spec("BE-008")
    def test_write_creates_file(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("new.txt", b"hello")
        assert backend.read_bytes("new.txt") == b"hello"

    @pytest.mark.spec("BE-008")
    def test_write_raises_already_exists(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("exists.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write("exists.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-008")
    def test_write_overwrite(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("over.txt", b"first")
        backend.write("over.txt", b"second", overwrite=True)
        assert backend.read_bytes("over.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_from_binaryio(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("stream.txt", io.BytesIO(b"streamed"))
        assert backend.read_bytes("stream.txt") == b"streamed"

    @pytest.mark.spec("BE-009")
    def test_write_creates_intermediate_dirs(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("a/b/c/deep.txt", b"deep")
        assert backend.read_bytes("a/b/c/deep.txt") == b"deep"


class TestBackendWriteAtomic:
    """BE-010 through BE-011: atomic write operations."""

    @pytest.mark.spec("BE-010")
    def test_write_atomic_creates_file(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        backend.write_atomic("atomic.txt", b"atomic content")
        assert backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("BE-010")
    def test_write_atomic_overwrite(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        backend.write_atomic("atomic2.txt", b"first")
        backend.write_atomic("atomic2.txt", b"second", overwrite=True)
        assert backend.read_bytes("atomic2.txt") == b"second"

    @pytest.mark.spec("BE-010")
    def test_write_atomic_already_exists(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        backend.write_atomic("atomic3.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write_atomic("atomic3.txt", b"second", overwrite=False)


class TestBackendOpenAtomic:
    """SAW-001 through SAW-005: streaming atomic write operations."""

    @pytest.mark.spec("SAW-003")
    def test_open_atomic_creates_file(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        with backend.open_atomic("oat.txt") as f:
            f.write(b"streaming atomic")
        assert backend.read_bytes("oat.txt") == b"streaming atomic"

    @pytest.mark.spec("SAW-006")
    def test_open_atomic_overwrite(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        backend.write("oat2.txt", b"first")
        with backend.open_atomic("oat2.txt", overwrite=True) as f:
            f.write(b"second")
        assert backend.read_bytes("oat2.txt") == b"second"

    @pytest.mark.spec("SAW-006")
    def test_open_atomic_already_exists(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        backend.write("oat3.txt", b"first")
        with pytest.raises(AlreadyExists), backend.open_atomic("oat3.txt", overwrite=False):
            pass

    @pytest.mark.spec("SAW-004")
    def test_open_atomic_exception_cleanup(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        with pytest.raises(RuntimeError, match="boom"), backend.open_atomic("oat_fail.txt") as f:  # noqa: PT012
            f.write(b"partial")
            raise RuntimeError("boom")
        assert not backend.exists("oat_fail.txt")


_WRITE_OPS = [
    pytest.param("write", Capability.WRITE, id="write"),
    pytest.param("write_atomic", Capability.ATOMIC_WRITE, id="write_atomic"),
]

# reason → (message, strict).  strict=False for dafny-oracle: the Dafny spec
# treats last_modified as opaque and hardcodes None by design — it is not a
# Python defect.  Flipping requires a BackendContract.dfy / MemoryBackend.dfy
# edit plus a dafny_translate.sh regen (tracked as ID-152 in BACKLOG.md).
_LAST_MODIFIED_XFAIL: dict[str, tuple[str, bool]] = {
    # strict=False: spec-opacity, not a Python defect.  Remove it together with
    # the BackendContract.dfy change tracked in ID-152 (BACKLOG.md).
    "dafny-oracle": (
        "spec opacity: Dafny MemoryBackend.Write returns Option_None() for last_modified by design; "
        "flip requires BackendContract.dfy edit + oracle regen (ID-152)",
        False,
    ),
}


class TestWriteResultConformance:
    """WR-001a / WR-004 / WR-005 / WR-012 / WR-013: WriteResult field contract.

    Traces the ``Write`` postconditions in
    ``sdd/formal/BackendContract.dfy`` § Backend.Write for the Python
    backend layer.  Rich-field checks are gated on
    ``Capability.WRITE_RESULT_NATIVE``; metadata checks are gated on
    ``Capability.USER_METADATA``.
    """

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_result_is_write_result_with_path_and_size(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap)
        payload = b"wr001a-payload"
        result = getattr(backend, op)(f"wr/{op}-path-size.txt", payload)
        assert isinstance(result, WriteResult)
        assert str(result.path) == f"wr/{op}-path-size.txt"
        assert result.size == len(payload)

    @pytest.mark.spec("WR-001a")
    def test_size_matches_written_bytes_for_streaming_input(self, backend: Backend) -> None:
        """WR-001a size clause for BinaryIO input on write_atomic.

        Payload is larger than the default ``BufferedWriter`` block so that
        any backend capturing ``size`` before the writer flushes would
        report a truncated value. This surfaced BUG-168 on
        ``LocalBackend.write_atomic`` under Python 3.14, where the
        pre-flush ``os.path.getsize`` call observed ``0`` — fixed by
        moving the size capture after the ``with`` block closes.
        """
        _require(backend, Capability.ATOMIC_WRITE)
        payload = b"x" * (100 * 1024)
        result = backend.write_atomic("wr/streaming-size.bin", io.BytesIO(payload))
        assert result.size == len(payload)

    @pytest.mark.spec("WR-004")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_source_matches_write_result_native(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap)
        result = getattr(backend, op)(f"wr/{op}-source.txt", b"data")
        expected = "native" if backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE) else "basic"
        assert result.source == expected

    @pytest.mark.spec("WR-005")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_basic_source_leaves_rich_fields_none(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap)
        if backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE):
            pytest.skip("WR-005 governs basic-source results")
        result = getattr(backend, op)(f"wr/{op}-basic.txt", b"data")
        assert result.source == "basic"
        assert result.digest is None
        assert result.etag is None
        assert result.version_id is None
        assert result.last_modified is None

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_native_populates_last_modified(
        self,
        backend: Backend,
        op: str,
        cap: Capability,
        request: pytest.FixtureRequest,
    ) -> None:
        """WR-001a rich-field obligation on declaring backends.

        The Dafny postcondition pins ``fs[path].info.last_modified ==
        r.value.last_modified`` when ``CapWriteResultNative`` is declared.
        A declaring backend that returns ``last_modified=None`` vacuously
        passes the divergence check but violates the quality obligation
        the capability advertises (spec 045 WR-009, WR-001a).

        Per-backend xfail reasons are in ``_LAST_MODIFIED_XFAIL``.  BUG-170
        (``sql-blob``) is a Python defect with ``strict=True``;
        ``dafny-oracle`` uses ``strict=False`` because the Dafny spec treats
        ``last_modified`` as opaque — that entry is removed as part of ID-152.
        """
        _require(backend, cap, Capability.WRITE_RESULT_NATIVE)
        if backend.name in _LAST_MODIFIED_XFAIL:
            reason, strict = _LAST_MODIFIED_XFAIL[backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        result = getattr(backend, op)(f"wr/{op}-lm.txt", b"data")
        assert result.last_modified is not None

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_native_file_info_matches_write_result(self, backend: Backend, op: str, cap: Capability) -> None:
        """WR-001a divergence check between WriteResult and FileInfo.

        When ``WRITE_RESULT_NATIVE`` is declared, a subsequent
        ``get_file_info()`` must return values consistent with the
        ``WriteResult`` for the fields both paths can populate
        (``etag`` and ``last_modified`` / ``modified_at``).

        ``digest`` is excluded: per WR-007 the default write path returns
        ``WriteResult.digest is None`` on every v1 backend, while some
        ``get_file_info`` implementations may surface a server-computed
        hash (e.g. S3 + ``ChecksumMode="ENABLED"``). Divergence on
        ``digest`` alone does not violate the WR-001a postcondition as
        written in ``BackendContract.dfy`` — that postcondition ties
        rich-field absence to *capability*, not to ``get_file_info``.
        """
        _require(backend, cap, Capability.WRITE_RESULT_NATIVE, Capability.METADATA)
        key = f"wr/{op}-fi-match.txt"
        result = getattr(backend, op)(key, b"data")
        info = backend.get_file_info(key)
        assert info.etag == result.etag
        # BUG-170 (sql-blob) returns last_modified=None from the write path, so
        # the divergence check is vacuous there; test_native_populates_last_modified
        # xfails the underlying defect.
        if result.last_modified is not None:
            assert info.modified_at == result.last_modified

    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_metadata_echoed_when_gate_passes(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap, Capability.USER_METADATA)
        meta = {"author": "alice", "project": "conformance"}
        result = getattr(backend, op)(f"wr/{op}-meta-echo.txt", b"data", metadata=meta)
        assert result.metadata == meta

    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_metadata_is_none_when_not_passed(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap)
        result = getattr(backend, op)(f"wr/{op}-meta-absent.txt", b"data")
        assert result.metadata is None

    @pytest.mark.spec("WR-013")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_metadata_round_trips_via_get_file_info(self, backend: Backend, op: str, cap: Capability) -> None:
        _require(backend, cap, Capability.USER_METADATA, Capability.METADATA)
        meta = {"author": "bob", "version": "v1"}
        key = f"wr/{op}-meta-roundtrip.txt"
        getattr(backend, op)(key, b"data", metadata=meta)
        info = backend.get_file_info(key)
        assert info.metadata == meta

    @pytest.mark.spec("WR-013")
    def test_file_info_metadata_none_when_capability_absent(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE, Capability.METADATA)
        if backend.capabilities.supports(Capability.USER_METADATA):
            pytest.skip("WR-013 negative direction targets non-declaring backends")
        backend.write("wr/meta-no-cap.txt", b"data")
        info = backend.get_file_info("wr/meta-no-cap.txt")
        assert info.metadata is None


class TestBackendDelete:
    """BE-012 through BE-013: delete operations."""

    @pytest.mark.spec("BE-012")
    def test_delete_removes_file(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE, Capability.WRITE)
        backend.write("del.txt", b"bye")
        backend.delete("del.txt")
        assert backend.exists("del.txt") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_empty(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE, Capability.WRITE)
        if backend.name in ("s3", "s3-pyarrow", "azure", "sql-blob"):
            pytest.skip("Virtual folders vanish when last object is deleted (S3-009/AZ-006/SQL-BLOB-flat)")
        backend.write("dir/file.txt", b"x")
        backend.delete("dir/file.txt")
        backend.delete_folder("dir")
        assert backend.exists("dir") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_recursive(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE, Capability.WRITE)
        _seed(backend, {"dir2/a.txt": b"a", "dir2/sub/b.txt": b"b"})
        backend.delete_folder("dir2", recursive=True)
        assert backend.exists("dir2") is False

    @pytest.mark.spec("BE-012")
    @pytest.mark.spec("BE-013")
    @pytest.mark.parametrize(
        ("method", "target"),
        [
            pytest.param("delete", "missing.txt", id="file"),
            pytest.param("delete_folder", "nodir", id="folder"),
        ],
    )
    @pytest.mark.parametrize(
        ("missing_ok", "expect_error"),
        [
            pytest.param(False, True, id="not_found_raises"),
            pytest.param(True, False, id="missing_ok_passes"),
        ],
    )
    def test_delete_missing(
        self,
        backend: Backend,
        method: str,
        target: str,
        missing_ok: bool,
        expect_error: bool,
    ) -> None:
        _require(backend, Capability.DELETE)
        if expect_error:
            with pytest.raises(NotFound):
                getattr(backend, method)(target, missing_ok=missing_ok)
        else:
            getattr(backend, method)(target, missing_ok=missing_ok)


class TestBackendListing:
    """BE-014 through BE-015: listing operations."""

    @pytest.mark.spec("BE-014")
    @pytest.mark.parametrize(
        ("prefix", "seeds", "recursive", "expected_names"),
        [
            pytest.param(
                "lf",
                {"lf/a.txt": b"a", "lf/b.txt": b"b", "lf/sub/c.txt": b"c"},
                False,
                {"a.txt", "b.txt"},
                id="non_recursive",
            ),
            pytest.param(
                "lfr",
                {"lfr/a.txt": b"a", "lfr/sub/b.txt": b"b"},
                True,
                {"a.txt", "b.txt"},
                id="recursive",
            ),
        ],
    )
    def test_list_files(
        self,
        backend: Backend,
        prefix: str,
        seeds: dict[str, bytes],
        recursive: bool,
        expected_names: set[str],
    ) -> None:
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, seeds)
        files = list(backend.list_files(prefix, recursive=recursive))
        assert {f.name for f in files} == expected_names
        for f in files:
            assert isinstance(f, FileInfo)

    @pytest.mark.spec("BE-015")
    def test_list_folders(self, backend: Backend) -> None:
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, {"lfd/sub1/a.txt": b"a", "lfd/sub2/b.txt": b"b", "lfd/file.txt": b"f"})
        folders = list(backend.list_folders("lfd"))
        assert all(isinstance(f, FolderEntry) for f in folders)
        assert {f.name for f in folders} == {"sub1", "sub2"}
        assert {str(f.path) for f in folders} == {"lfd/sub1", "lfd/sub2"}


class TestBackendIterChildren:
    """ITER-004, ITER-005: iter_children() — combined file+folder listing."""

    @pytest.mark.spec("ITER-004")
    def test_iter_children(self, backend: Backend) -> None:
        _require(backend, Capability.LIST, Capability.WRITE)
        _seed(backend, {"ic/a.txt": b"a", "ic/b.txt": b"b", "ic/sub/c.txt": b"c"})
        children = list(backend.iter_children("ic"))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}
        assert {str(f.path) for f in folders} == {"ic/sub"}

    @pytest.mark.spec("ITER-004")
    def test_iter_children_empty_or_nonexistent(self, backend: Backend) -> None:
        _require(backend, Capability.LIST)
        assert list(backend.iter_children("nonexistent")) == []

    @pytest.mark.spec("ITER-004")
    @pytest.mark.parametrize(
        ("prefix", "file_path", "expect_files", "expect_folders"),
        [
            pytest.param("icf", "icf/x.txt", {"x.txt"}, set(), id="only_files"),
            pytest.param("ico", "ico/sub/y.txt", set(), {"sub"}, id="only_folders"),
        ],
    )
    def test_iter_children_single_type(
        self,
        backend: Backend,
        prefix: str,
        file_path: str,
        expect_files: set[str],
        expect_folders: set[str],
    ) -> None:
        _require(backend, Capability.LIST, Capability.WRITE)
        backend.write(file_path, b"x")
        children = list(backend.iter_children(prefix))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == expect_files
        assert {f.name for f in folders} == expect_folders


class TestBackendMetadata:
    """BE-016 through BE-017: metadata operations."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("info.txt", b"hello world")
        fi = backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11

    @pytest.mark.spec("BE-017")
    @pytest.mark.spec("ID-134")
    def test_get_folder_info(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        _seed(backend, {"fi/a.txt": b"aaa", "fi/b.txt": b"bb"})
        fi = backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("BE-017")
    @pytest.mark.spec("ID-134")
    def test_get_folder_info_excludes_subdirs(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        _seed(backend, {"mix/a.txt": b"aaa", "mix/sub/b.txt": b"bb"})
        fi = backend.get_folder_info("mix")
        # ChildFiles counts all files recursively under path, including sub/b.txt.
        assert fi.file_count == 2
        assert fi.total_size == 5
        # DirEntry nodes (mix/sub/) must not be counted.

    @pytest.mark.spec("BE-016")
    def test_file_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_file_info("missing_target")

    @pytest.mark.spec("BE-017")
    def test_folder_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_folder_info("missing_target")


class TestBackendMoveCopy:
    """BE-018, BE-019: move and copy operations."""

    @pytest.mark.spec("BE-018")
    def test_move(self, backend: Backend) -> None:
        _require(backend, Capability.MOVE, Capability.WRITE)
        backend.write("mv_src.txt", b"data")
        backend.move("mv_src.txt", "mv_dst.txt")
        assert backend.exists("mv_src.txt") is False
        assert backend.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("BE-019")
    def test_copy(self, backend: Backend) -> None:
        _require(backend, Capability.COPY, Capability.WRITE)
        backend.write("cp_src.txt", b"data")
        backend.copy("cp_src.txt", "cp_dst.txt")
        assert backend.read_bytes("cp_src.txt") == b"data"
        assert backend.read_bytes("cp_dst.txt") == b"data"

    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_not_found(self, backend: Backend, op: str, cap: Capability) -> None:
        """BE-018/BE-019: move/copy raise NotFound for missing source."""
        _require(backend, cap)
        with pytest.raises(NotFound):
            _do_op(backend, op, "missing.txt", "dst.txt")

    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_already_exists(self, backend: Backend, op: str, cap: Capability) -> None:
        """BE-018/BE-019: move/copy raise AlreadyExists when overwrite=False."""
        _require(backend, cap, Capability.WRITE)
        _seed(backend, {f"{op}1.txt": b"a", f"{op}2.txt": b"b"})
        with pytest.raises(AlreadyExists):
            _do_op(backend, op, f"{op}1.txt", f"{op}2.txt", overwrite=False)

    @pytest.mark.parametrize(
        ("op", "cap", "src_exists_after"),
        [
            pytest.param("move", Capability.MOVE, False, id="move"),
            pytest.param("copy", Capability.COPY, True, id="copy"),
        ],
    )
    def test_overwrite(
        self,
        backend: Backend,
        op: str,
        cap: Capability,
        src_exists_after: bool,
    ) -> None:
        """BE-018/BE-019: move/copy with overwrite=True replaces destination."""
        _require(backend, cap, Capability.WRITE)
        _seed(backend, {f"{op}o1.txt": b"a", f"{op}o2.txt": b"b"})
        _do_op(backend, op, f"{op}o1.txt", f"{op}o2.txt", overwrite=True)
        assert backend.read_bytes(f"{op}o2.txt") == b"a"
        if src_exists_after:
            assert backend.read_bytes(f"{op}o1.txt") == b"a"


class TestBackendLifecycle:
    """BE-020: close is callable."""

    @pytest.mark.spec("BE-020")
    def test_close_is_callable(self, backend: Backend) -> None:
        result = backend.close()
        assert result is None


class TestBackendToKey:
    """NPR-003 through NPR-008: to_key reverse path resolution."""

    @pytest.mark.spec("NPR-003")
    def test_to_key_exists(self, backend: Backend) -> None:
        assert hasattr(backend, "to_key")
        assert callable(backend.to_key)

    @pytest.mark.spec("NPR-004")
    def test_to_key_is_deterministic(self, backend: Backend) -> None:
        assert backend.to_key("some/path") == backend.to_key("some/path")

    @pytest.mark.spec("NPR-005")
    def test_to_key_passthrough_for_relative(self, backend: Backend) -> None:
        """Relative paths with no matching prefix pass through unchanged."""
        assert isinstance(backend.to_key("some/path"), str)

    @pytest.mark.spec("NPR-003")
    def test_to_key_round_trip_with_listing(self, backend: Backend) -> None:
        """Paths from list_files can be converted back via to_key."""
        _require(backend, Capability.LIST, Capability.WRITE)
        backend.write("tk/a.txt", b"a")
        files = list(backend.list_files("tk"))
        assert len(files) == 1
        assert backend.read_bytes(str(files[0].path)) == b"a"


class TestStreamingConformance:
    """SIO-001, SIO-003, SIO-009: streaming semantics.

    SIO-001 only requires a readable BinaryIO at start-of-stream. Pre-loading
    the full file into memory before returning (e.g. BytesIO) is acceptable for
    backends that do not declare LAZY_READ. The LAZY_READ conformance tests below
    enforce the laziness contract only on backends that declare it.
    """

    @pytest.mark.spec("SIO-001")
    def test_read_returns_readable_stream(self, backend: Backend) -> None:
        """read() must return a readable BinaryIO stream with correct content."""
        _require(backend, Capability.WRITE)
        backend.write("stream_test.bin", b"hello streaming")
        stream = backend.read("stream_test.bin")
        assert stream.readable(), "read() must return a readable stream"
        assert stream.read() == b"hello streaming"
        stream.close()

    @pytest.mark.spec("SIO-009")
    def test_read_is_lazy(self, backend: Backend) -> None:
        """Backends declaring LAZY_READ must not return a BytesIO-backed stream."""
        _require(backend, Capability.WRITE, Capability.LAZY_READ)
        backend.write("lazy_test.bin", b"lazy read test")
        stream = backend.read("lazy_test.bin")
        # Peel every layer of buffering until we reach a stream with no further
        # `.raw` attribute — this guards against multi-level wrappers such as
        # BufferedReader(CustomWrapper(BytesIO(...))).
        inner = stream
        while hasattr(inner, "raw"):
            inner = inner.raw  # type: ignore[union-attr]
        assert not isinstance(inner, io.BytesIO), (
            "Backend declares LAZY_READ but read() returned a BytesIO-backed stream"
        )
        assert stream.read() == b"lazy read test"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_supports_chunked_reads(self, backend: Backend) -> None:
        """Streams must support reading in fixed-size chunks."""
        _require(backend, Capability.WRITE)
        content = b"A" * 1000
        backend.write("chunks.bin", content)
        stream = backend.read("chunks.bin")
        chunks = []
        while True:
            chunk = stream.read(100)
            if not chunk:
                break
            assert len(chunk) <= 100
            chunks.append(chunk)
        assert b"".join(chunks) == content
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_eof_returns_empty_bytes_not_none(self, backend: Backend) -> None:
        """read() at EOF must return b'' (empty bytes), not None."""
        _require(backend, Capability.WRITE)
        backend.write("eof_test.bin", b"x")
        stream = backend.read("eof_test.bin")
        data = stream.read()
        assert data == b"x"
        eof = stream.read()
        assert eof == b"", f"Expected b'' at EOF, got {eof!r}"
        eof2 = stream.read(10)
        assert eof2 == b"", f"Expected b'' at EOF with size hint, got {eof2!r}"
        stream.close()

    @pytest.mark.spec("SIO-009")
    def test_read_is_lazy_readinto(self, backend: Backend) -> None:
        """LAZY_READ streams must support readinto() via the RawIOBase protocol."""
        _require(backend, Capability.WRITE, Capability.LAZY_READ)
        content = b"readinto test data"
        backend.write("readinto_test.bin", content)
        stream = backend.read("readinto_test.bin")
        # Reach the raw layer for readinto() — BufferedReader handles readinto
        # at the buffered level, but we want to exercise the raw stream.
        raw = stream
        while hasattr(raw, "raw"):
            raw = raw.raw  # type: ignore[union-attr]
        buf = bytearray(len(content))
        n = raw.readinto(buf)
        assert isinstance(n, int), f"readinto() must return int, got {type(n).__name__}"
        assert n > 0, "readinto() must return > 0 bytes on a non-empty stream"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_stream_position_starts_at_zero(self, backend: Backend) -> None:
        """Stream must be positioned at the start on return."""
        _require(backend, Capability.WRITE)
        backend.write("pos.bin", b"0123456789")
        stream = backend.read("pos.bin")
        assert stream.read(3) == b"012"
        assert stream.read() == b"3456789"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_stream_supports_context_manager(self, backend: Backend) -> None:
        """read() stream supports context manager protocol for reliable cleanup."""
        _require(backend, Capability.WRITE)
        backend.write("ctx.bin", b"context manager test")
        with backend.read("ctx.bin") as stream:
            content = stream.read()
        assert content == b"context manager test"
        assert stream.closed

    @pytest.mark.spec("SIO-003")
    def test_write_from_binaryio_streams_content(self, backend: Backend) -> None:
        """write() with BinaryIO must not require the caller to materialize bytes."""
        _require(backend, Capability.WRITE)
        content = b"X" * 8192
        backend.write("binio_write.bin", io.BytesIO(content))
        assert backend.read_bytes("binio_write.bin") == content

    @pytest.mark.spec("SIO-003")
    def test_write_binaryio_reads_from_current_position(self, backend: Backend) -> None:
        """write() must read BinaryIO from its current position, not from start."""
        _require(backend, Capability.WRITE)
        buf = io.BytesIO(b"HEADER_PAYLOAD")
        buf.seek(7)  # Skip past "HEADER_"
        backend.write("partial_pos.bin", buf)
        assert backend.read_bytes("partial_pos.bin") == b"PAYLOAD"


class TestBackendGlob:
    """GLOB-018/019/020: glob conformance across backends."""

    @pytest.mark.spec("GLOB-018")
    @pytest.mark.parametrize(
        ("seeds", "pattern", "expected"),
        [
            pytest.param(
                {"g/a.txt": b"a", "g/b.csv": b"b"},
                "g/*.txt",
                ["g/a.txt"],
                id="basic",
            ),
            pytest.param(
                {"gr/a.txt": b"a"},
                "gr/**/*.txt",
                ["gr/a.txt"],
                id="recursive-zero-seg",
            ),
            pytest.param(
                {"gr/sub/b.txt": b"b", "gr/sub/c.csv": b"c"},
                "gr/**/*.txt",
                ["gr/sub/b.txt"],
                id="recursive-one-seg",
            ),
        ],
    )
    def test_glob(
        self,
        backend: Backend,
        request: pytest.FixtureRequest,
        seeds: dict[str, bytes],
        pattern: str,
        expected: list[str],
    ) -> None:
        _require(backend, Capability.GLOB, Capability.WRITE)
        # BUG-175: SQLite GLOB pre-filter rejects the zero-directory match
        # for `**/` (treats `**` as two `*`s separated by a literal `/`).
        # The one-segment variant passes today.
        if backend.name == "sql-blob" and request.node.callspec.id.endswith("recursive-zero-seg"):
            pytest.skip("BUG-175: SQLBlob SQLite GLOB pre-filter drops zero-segment **/ matches")
        _seed(backend, seeds)
        assert sorted(str(f.path) for f in backend.glob(pattern)) == expected


class TestBackendUnwrap:
    """BE-022: unwrap raises by default."""

    @pytest.mark.spec("BE-022")
    def test_unwrap_raises_by_default(self, backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)


class TestBackendNativePath:
    """BE-025: native_path() default is identity."""

    @pytest.mark.spec("BE-025")
    def test_native_path_round_trip(self, backend: Backend) -> None:
        """native_path is the inverse of to_key (NPR-020)."""
        assert backend.to_key(backend.native_path("some/key")) == "some/key"

    @pytest.mark.spec("BE-025")
    def test_native_path_empty_returns_root(self, backend: Backend) -> None:
        """native_path('') returns the backend's root (NPR-021)."""
        assert isinstance(backend.native_path(""), str)


class TestBackendResolveDefault:
    """RES-020: Backend.resolve() default implementation returns a ResolutionPlan."""

    _PATHS = [
        pytest.param("simple.txt", id="simple"),
        pytest.param("dir/sub/file.txt", id="nested"),
        pytest.param("", id="empty"),
    ]

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _PATHS)
    def test_returns_resolution_plan(self, backend: Backend, path: str) -> None:
        from remote_store._resolution import ResolutionPlan

        plan = backend.resolve(path)
        assert isinstance(plan, ResolutionPlan)
        assert plan.key == path

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _PATHS)
    def test_kind_is_non_empty_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.kind == backend.name

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _PATHS)
    def test_backend_is_non_empty_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.backend == backend.name

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _PATHS)
    def test_native_path_is_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.native_path == backend.native_path(path)


class TestAtomicMoveCapability:
    """CAP-001: ATOMIC_MOVE capability declared by backends with atomic move semantics."""

    # Backends exercised by the conformance fixture (conftest.py).
    # sql-query is not parameterised here; it has its own test module.
    _DECLARES = {"local", "memory", "dafny-oracle", "sql-blob"}
    _DOES_NOT_DECLARE = {"s3", "s3-pyarrow", "azure", "sftp", "http"}

    @pytest.mark.spec("CAP-001")
    def test_atomic_move_capability_declaration(self, backend: Backend) -> None:
        name = backend.name
        supports = backend.capabilities.supports(Capability.ATOMIC_MOVE)
        if name in self._DECLARES:
            assert supports, f"{name} should declare ATOMIC_MOVE"
        elif name in self._DOES_NOT_DECLARE:
            assert not supports, f"{name} should not declare ATOMIC_MOVE"
        else:
            pytest.fail(
                f"Backend {name!r} is not listed in _DECLARES or _DOES_NOT_DECLARE. "
                "Update TestAtomicMoveCapability to classify this backend."
            )


class TestBackendResolveUniversalContract:
    """RES-025: Universal contract for Backend.resolve()."""

    _PATHS = [
        pytest.param("simple.txt", id="simple"),
        pytest.param("dir/sub/file.txt", id="nested"),
        pytest.param("", id="empty"),
    ]

    @pytest.mark.spec("RES-025")
    @pytest.mark.parametrize("path", _PATHS)
    def test_native_path_matches_backend(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.native_path == backend.native_path(path)

    @pytest.mark.spec("RES-025")
    @pytest.mark.parametrize("path", _PATHS)
    def test_details_is_mapping(self, backend: Backend, path: str) -> None:
        from collections.abc import Mapping

        plan = backend.resolve(path)
        assert isinstance(plan.details, Mapping)
        assert plan.kind == backend.name
