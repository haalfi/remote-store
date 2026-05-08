"""Atomic write + move/copy conformance.

Covers BE-010/011 atomic writes, SAW-* streaming-atomic-write,
WriteResult contract (WR-*), and move/copy semantics including
overwrite, self-op, and post-state.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, NotFound
from remote_store._models import WriteResult
from tests.backends.conformance._helpers import (
    _MOVE_COPY_PARAMS,
    _do_op,
    _fixture_record,
    _require,
    _seed,
)
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(Capability.ATOMIC_WRITE), indirect=True)
class TestBackendWriteAtomic:
    """BE-010 through BE-011: atomic write operations."""

    @pytest.mark.spec("BE-010")
    @pytest.mark.spec("SQL-BLOB-023")
    def test_write_atomic_creates_file(self, backend: Backend) -> None:
        backend.write_atomic("atomic.txt", b"atomic content")
        assert backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("BE-010")
    @pytest.mark.spec("SFTP-015")
    def test_write_atomic_overwrite(self, backend: Backend) -> None:
        backend.write_atomic("atomic2.txt", b"first")
        backend.write_atomic("atomic2.txt", b"second", overwrite=True)
        assert backend.read_bytes("atomic2.txt") == b"second"

    @pytest.mark.spec("BE-010")
    @pytest.mark.spec("SFTP-015")
    def test_write_atomic_already_exists(self, backend: Backend) -> None:
        backend.write_atomic("atomic3.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write_atomic("atomic3.txt", b"second", overwrite=False)


@pytest.mark.parametrize("backend", fixture_params(Capability.ATOMIC_WRITE), indirect=True)
class TestBackendOpenAtomic:
    """SAW-001 through SAW-005: streaming atomic write operations."""

    @pytest.mark.spec("SAW-003")
    @pytest.mark.spec("SQL-BLOB-023")
    def test_open_atomic_creates_file(self, backend: Backend) -> None:
        with backend.open_atomic("oat.txt") as f:
            f.write(b"streaming atomic")
        assert backend.read_bytes("oat.txt") == b"streaming atomic"

    @pytest.mark.spec("SAW-006")
    def test_open_atomic_overwrite(self, backend: Backend) -> None:
        backend.write("oat2.txt", b"first")
        with backend.open_atomic("oat2.txt", overwrite=True) as f:
            f.write(b"second")
        assert backend.read_bytes("oat2.txt") == b"second"

    @pytest.mark.spec("SAW-006")
    def test_open_atomic_already_exists(self, backend: Backend) -> None:
        backend.write("oat3.txt", b"first")
        with pytest.raises(AlreadyExists), backend.open_atomic("oat3.txt", overwrite=False):
            pass

    @pytest.mark.spec("SAW-004")
    @pytest.mark.spec("SQL-BLOB-023")
    def test_open_atomic_exception_cleanup(self, backend: Backend) -> None:
        with pytest.raises(RuntimeError, match="boom"), backend.open_atomic("oat_fail.txt") as f:  # noqa: PT012
            f.write(b"partial")
            raise RuntimeError("boom")
        assert not backend.exists("oat_fail.txt")


_WRITE_OPS = [
    pytest.param("write", Capability.WRITE, id="write"),
    pytest.param("write_atomic", Capability.ATOMIC_WRITE, id="write_atomic"),
]

# name → (reason, strict).  Add an entry when a WRITE_RESULT_NATIVE backend
# temporarily returns last_modified=None from write() (e.g. new declaration lag).
_LAST_MODIFIED_XFAIL: dict[str, tuple[str, bool]] = {}

# name → (reason, strict).  Add an entry when a backend's write path temporarily
# disagrees with get_file_info() on etag, digest, or last_modified.
_RICH_FIELDS_XFAIL: dict[str, tuple[str, bool]] = {}


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestWriteResultConformance:
    """WR-001a / WR-004 / WR-005 / WR-012 / WR-013: WriteResult field contract."""

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

        Payload exceeds the default BufferedWriter block so backends that
        capture size before the writer flushes report a truncated value
        (BUG-168).
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
        """WR-001a rich-field obligation on declaring backends."""
        _require(backend, cap, Capability.WRITE_RESULT_NATIVE)
        if backend.name in _LAST_MODIFIED_XFAIL:
            reason, strict = _LAST_MODIFIED_XFAIL[backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        result = getattr(backend, op)(f"wr/{op}-lm.txt", b"data")
        assert result.last_modified is not None

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_write_result_rich_fields_match_file_info(
        self,
        backend: Backend,
        op: str,
        cap: Capability,
        request: pytest.FixtureRequest,
    ) -> None:
        """WR-001a consistency contract: write() rich fields must match get_file_info()."""
        _require(backend, cap, Capability.METADATA)
        if backend.name in _RICH_FIELDS_XFAIL:
            reason, strict = _RICH_FIELDS_XFAIL[backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        key = f"wr/{op}-rich-fields-match.txt"
        result = getattr(backend, op)(key, b"rich-fields-payload")
        info = backend.get_file_info(key)
        assert result.etag == info.etag
        assert result.digest == info.digest
        if info.modified_at is not None:
            assert result.last_modified == info.modified_at

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
        _require(backend, Capability.METADATA)
        if backend.capabilities.supports(Capability.USER_METADATA):
            pytest.skip("WR-013 negative direction targets non-declaring backends")
        backend.write("wr/meta-no-cap.txt", b"data")
        info = backend.get_file_info("wr/meta-no-cap.txt")
        assert info.metadata is None


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendMoveCopy:
    """BE-018, BE-019: move and copy operations."""

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("SFTP-018")
    @pytest.mark.spec("SQL-BLOB-031")
    def test_move(self, backend: Backend) -> None:
        _require(backend, Capability.MOVE)
        backend.write("mv_src.txt", b"data")
        backend.move("mv_src.txt", "mv_dst.txt")
        assert backend.exists("mv_src.txt") is False
        assert backend.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("BE-019")
    @pytest.mark.spec("SFTP-019")
    @pytest.mark.spec("SQL-BLOB-032")
    def test_copy(self, backend: Backend) -> None:
        _require(backend, Capability.COPY)
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
        _require(backend, cap)
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
        _require(backend, cap)
        _seed(backend, {f"{op}o1.txt": b"a", f"{op}o2.txt": b"b"})
        _do_op(backend, op, f"{op}o1.txt", f"{op}o2.txt", overwrite=True)
        assert backend.read_bytes(f"{op}o2.txt") == b"a"
        if src_exists_after:
            assert backend.read_bytes(f"{op}o1.txt") == b"a"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestMoveCopyOverwrite:
    """Move/Copy overwrite postconditions."""

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_dst_exists_no_overwrite_raises_already_exists(self, backend: Backend, op: str, cap: Capability) -> None:
        """IsFile(dst) && !overwrite && src != dst ==> AlreadyExists(dst)."""
        _require(backend, cap)
        _seed(backend, {f"mcow/{op}_s.txt": b"s", f"mcow/{op}_d.txt": b"d"})
        with pytest.raises(AlreadyExists, match=f"mcow/{op}_d"):
            _do_op(backend, op, f"mcow/{op}_s.txt", f"mcow/{op}_d.txt", overwrite=False)

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_overwrite_replaces_destination(self, backend: Backend, op: str, cap: Capability) -> None:
        """overwrite=True ==> dst gets src content."""
        _require(backend, cap)
        _seed(backend, {f"mcor/{op}_s.txt": b"new", f"mcor/{op}_d.txt": b"old"})
        _do_op(backend, op, f"mcor/{op}_s.txt", f"mcor/{op}_d.txt", overwrite=True)
        assert backend.read_bytes(f"mcor/{op}_d.txt") == b"new"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestMoveCopySelfOperation:
    """Self-move/self-copy: data must not be lost (Dafny: src==dst is a no-op)."""

    @pytest.mark.spec("BE-019")
    def test_self_copy_preserves_data(self, backend: Backend) -> None:
        """copy(src, src, overwrite=True) must not lose data."""
        _require(backend, Capability.COPY)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-copy yet")
        backend.write("selfcp.txt", b"data")
        backend.copy("selfcp.txt", "selfcp.txt", overwrite=True)
        assert backend.read_bytes("selfcp.txt") == b"data"

    @pytest.mark.spec("BE-018")
    def test_self_move_preserves_data(self, backend: Backend) -> None:
        """move(src, src, overwrite=True) must not lose data."""
        _require(backend, Capability.MOVE)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-move yet")
        backend.write("selfmv.txt", b"data")
        backend.move("selfmv.txt", "selfmv.txt", overwrite=True)
        assert backend.read_bytes("selfmv.txt") == b"data"

    @pytest.mark.spec("BE-019")
    def test_self_copy_no_overwrite_preserves_data(self, backend: Backend) -> None:
        """copy(src, src, overwrite=False) is a no-op; must not raise AlreadyExists."""
        _require(backend, Capability.COPY)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-copy yet")
        backend.write("selfcp2.txt", b"data")
        backend.copy("selfcp2.txt", "selfcp2.txt", overwrite=False)
        assert backend.read_bytes("selfcp2.txt") == b"data"

    @pytest.mark.spec("BE-019")
    def test_self_copy_missing_raises_not_found(self, backend: Backend) -> None:
        """copy(src, src) where src does not exist must raise NotFound."""
        _require(backend, Capability.COPY)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-copy yet")
        with pytest.raises(NotFound, match="sc_missing"):
            backend.copy("sc_missing.txt", "sc_missing.txt")

    @pytest.mark.spec("BE-018")
    def test_self_move_no_overwrite_preserves_data(self, backend: Backend) -> None:
        """move(src, src, overwrite=False) is a no-op; must not raise AlreadyExists."""
        _require(backend, Capability.MOVE)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-move yet")
        backend.write("selfmv2.txt", b"data")
        backend.move("selfmv2.txt", "selfmv2.txt", overwrite=False)
        assert backend.read_bytes("selfmv2.txt") == b"data"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.MOVE, Capability.WRITE), indirect=True)
class TestMovePostState:
    """Move post-state: src removed, dst has src content."""

    @pytest.mark.spec("BE-018")
    def test_move_removes_source(self, backend: Backend) -> None:
        """src != dst ==> !PathExists(fs, src)."""
        backend.write("mvps_src.txt", b"data")
        backend.move("mvps_src.txt", "mvps_dst.txt")
        assert not backend.exists("mvps_src.txt")
        assert backend.read_bytes("mvps_dst.txt") == b"data"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.COPY, Capability.WRITE), indirect=True)
class TestCopyPostState:
    """Copy post-state: src unchanged, dst has src content."""

    @pytest.mark.spec("BE-019")
    def test_copy_preserves_source(self, backend: Backend) -> None:
        """IsFile(fs, src): source still exists after copy."""
        backend.write("cpps_src.txt", b"data")
        backend.copy("cpps_src.txt", "cpps_dst.txt")
        assert backend.read_bytes("cpps_src.txt") == b"data"
        assert backend.read_bytes("cpps_dst.txt") == b"data"
