"""Atomic write + move/copy conformance.

Covers BE-010/011 atomic writes, SAW-* streaming-atomic-write,
WriteResult contract (WR-*), and move/copy semantics including
overwrite, self-op, and post-state.
"""

from __future__ import annotations

import dataclasses
import io
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, InvalidPath, NotFound, RemoteStoreError
from remote_store._models import WriteResult
from tests._helpers import FailingContentReader
from tests.backends.conformance._helpers import (
    _MOVE_COPY_PARAMS,
    _do_op,
    _fixture_record,
    _require,
    _seed,
    _skip_flat_namespace,
    _skip_unless_large_write_distinct,
)
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(Capability.ATOMIC_WRITE), indirect=True)
class TestBackendWriteAtomic:
    """BE-010 through BE-011: atomic write operations."""

    @pytest.mark.spec("BE-010")
    @pytest.mark.spec("SQL-BLOB-023")
    @pytest.mark.spec("MEM-013")
    def test_write_atomic_creates_file(self, backend: Backend) -> None:
        backend.write_atomic("atomic.txt", b"atomic content")
        assert backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("AW-005")
    def test_write_atomic_creates_intermediate_dirs(self, backend: Backend) -> None:
        """AW-005: write_atomic creates intermediate directories, same as write (BE-009)."""
        backend.write_atomic("aw/deep/dir/file.txt", b"deep atomic")
        assert backend.read_bytes("aw/deep/dir/file.txt") == b"deep atomic"

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

    @pytest.mark.spec("AW-001")
    @pytest.mark.spec("AW-004")
    @pytest.mark.spec("S3-010")
    @pytest.mark.spec("S3PA-013")
    def test_write_atomic_content_failure_leaves_no_partial(self, backend: Backend) -> None:
        """AW-001 / AW-004: a mid-stream *content* failure must commit nothing.

        When the content source raises partway through ``write_atomic``, the
        target must stay absent (AW-001, "no partial content is ever visible")
        and no orphan artefact may survive under the fixture root (AW-004, "no
        orphaned temporary files are left behind"). This is the strongest
        cross-backend exercise of AW-004's cleanup clause: local/SFTP temp-file
        removal, the s3fs ``discard()`` abort, and the PyArrow buffer-before-open.

        Regression for BUG-214: the two S3 backends committed a truncated
        object on this path (the s3fs backend because its file handle's
        ``close()`` ran on the exception path; the PyArrow backend because its
        output stream commits on close and cannot be aborted). The fixes abort
        the in-flight s3fs upload and buffer the PyArrow ``write_atomic`` before
        any upload. Rides every ``ATOMIC_WRITE`` fixture, including the live S3
        fixtures at ``--stage=3`` (the real-AWS confirmation per TESTING.md).

        Plain ``write`` is intentionally excluded: it is non-atomic (AW-007) and
        may leave a partial object on failure, like the local backend.
        """
        key = "aw/atomic-content-failure.bin"
        # 256 KiB delivered before the hard failure: enough to push past the
        # default write block on buffer-then-upload backends while keeping the
        # live-account data transfer negligible.
        content = FailingContentReader.buffered(256 * 1024)
        # The reader raises ConnectionResetError; backends either map it to a
        # RemoteStoreError or let it (a ConnectionError) propagate. Asserting
        # that union -- rather than bare Exception -- means an early/wrong-type
        # failure (TypeError, AssertionError) before the content is touched
        # can't silently satisfy the atomicity assertions below.
        with pytest.raises((RemoteStoreError, ConnectionError)):
            backend.write_atomic(key, content, overwrite=True)
        assert not backend.exists(key)
        remaining = [str(fi.path) for fi in backend.list_files("", recursive=True)]
        assert remaining == [], f"orphan artefact after write_atomic content failure: {remaining}"


@pytest.mark.parametrize("backend", fixture_params(Capability.ATOMIC_WRITE), indirect=True)
class TestBackendOpenAtomic:
    """SAW-001 through SAW-005: streaming atomic write operations."""

    @pytest.mark.spec("SAW-003")
    @pytest.mark.spec("SQL-BLOB-023")
    @pytest.mark.spec("SAW-010")
    @pytest.mark.spec("SAW-012")
    def test_open_atomic_creates_file(self, backend: Backend) -> None:
        # SAW-010: for the S3 / S3-PyArrow fixtures this drives the
        # SpooledTemporaryFile-buffer-then-PUT streaming-atomic mechanism end to
        # end (write into the buffer, single PUT on context exit). The buffer
        # internals are not separately asserted (the audit-015 addendum's
        # "exercised, not mechanism-asserted" note); the success path is.
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
    @pytest.mark.spec("SAW-005")
    @pytest.mark.spec("SAW-009")
    @pytest.mark.spec("SQL-BLOB-023")
    def test_open_atomic_exception_cleanup(self, backend: Backend) -> None:
        with pytest.raises(RuntimeError, match="boom"), backend.open_atomic("oat_fail.txt") as f:  # noqa: PT012
            f.write(b"partial")
            raise RuntimeError("boom")
        assert not backend.exists("oat_fail.txt")
        # ID-188 / SAW-005: assert no orphan temp artefact survives anywhere
        # under the fixture root. The fixture is function-scoped and writes
        # nothing before the failed open_atomic, so any residual file is a
        # leaked temp from a backend's per-strategy cleanup path (see
        # spec 022 § Per-backend strategies).
        #
        # Asymmetric coverage on the caller-exception path — the assertion
        # only *bites* on strategies that materialise a temp artefact in
        # the remote namespace *before* yielding to the caller: Local
        # (`tempfile.mkstemp` runs before yield, SAW-008) and SFTP
        # (`.~tmp.{uuid}` opened before yield, SAW-009). The buffer-then-PUT
        # strategies — S3 / S3-pyarrow / Azure non-HNS (SAW-010 / SAW-011),
        # MemoryBackend / SQLBlob (SAW-012), and Azure HNS (SAW-011): the
        # HNS upload + DFS rename happen *after* the yield, so a caller
        # exception during the yield never creates a remote blob — discard a
        # `SpooledTemporaryFile` / `BytesIO` without issuing a remote write,
        # so the assertion holds vacuously rather than exercising cleanup.
        # The gate still catches the load-bearing regressions on the two
        # eager-temp strategies (Local SAW-008, SFTP SAW-009) and consumes
        # nothing extra on the vacuous fixtures. HNS upload-failure cleanup
        # (SAW-011 inner branch at `_azure.py` `except Exception` ->
        # `delete_file()`) is exercised by the real file-ancestor test
        # `test_errors.py::TestWriteErrorFidelity::
        # test_open_atomic_under_file_ancestor_raises_invalid_path` (BK-244),
        # whose orphan-temp scan asserts the same no-leak invariant on the
        # HNS upload-under-file-ancestor path.
        remaining = [str(fi.path) for fi in backend.list_files("", recursive=True)]
        assert remaining == [], f"orphan temp files after open_atomic failure: {remaining}"


_WRITE_OPS = [
    pytest.param("write", Capability.WRITE, id="write"),
    pytest.param("write_atomic", Capability.ATOMIC_WRITE, id="write_atomic"),
]

# WriteResult field → capability that must be declared for the field to carry a
# non-None value (BK-239). ``None`` marks the unconditionally-populated fields
# (``path``/``size`` per WR-001a, ``source`` per WR-004). The rich fields are
# gated by WRITE_RESULT_NATIVE (WR-005) and ``metadata`` by USER_METADATA
# (WR-012). ``test_field_capability_map_covers_every_write_result_field`` pins
# this dict to ``dataclasses.fields(WriteResult)``, so a new field cannot land
# without being classified here — that completeness check is what lets future
# field/capability pairs inherit the symmetry guard automatically.
_FIELD_CAPABILITY: dict[str, Capability | None] = {
    "path": None,
    "size": None,
    "source": None,
    "digest": Capability.WRITE_RESULT_NATIVE,
    "etag": Capability.WRITE_RESULT_NATIVE,
    "version_id": Capability.WRITE_RESULT_NATIVE,
    "last_modified": Capability.WRITE_RESULT_NATIVE,
    "metadata": Capability.USER_METADATA,
}

# name → (reason, strict).  Add an entry when a WRITE_RESULT_NATIVE backend
# temporarily returns last_modified=None from write() (e.g. new declaration lag).
_LAST_MODIFIED_XFAIL: dict[str, tuple[str, bool]] = {}

# name → (reason, strict).  Add an entry when a backend's write path temporarily
# disagrees with get_file_info() on etag, digest, or last_modified.
_RICH_FIELDS_XFAIL: dict[str, tuple[str, bool]] = {}

# A single payload size that trips every distinct large-write path —
# Graph's 4 MiB ``createUploadSession`` boundary (GR-018), S3's 5 MiB multipart
# part floor, and Azure's 1 MiB single-put default. Imported by the async
# conformance suite so sync and async exercise the same threshold.
_LARGE_WRITE_SIZE = 8 * 1024 * 1024

# name → (reason, strict).  Like _RICH_FIELDS_XFAIL but for the large/streamed
# write path only — a backend may agree with get_file_info() on a small single
# write yet diverge once the multipart / staged / upload-session path runs.
# strict=False where the divergence is confirmed on the emulator but unverified
# against the real cloud (Azurite ≠ real ADLS Gen2).
_LARGE_RICH_FIELDS_XFAIL: dict[str, tuple[str, bool]] = {
    "azure": (
        "BUG-216: Azure large/block-staged write fills WriteResult.digest from the commit "
        "response, but the staged blob stores no Content-MD5, so get_file_info().digest is "
        "None — they diverge (observed on Azurite; real ADLS Gen2 unverified)",
        False,
    ),
}

# (op, cap) for the copy/move user-metadata round-trip (BK-195 / BK-233).
# Per-param @spec marks differ by op: copy carries BE-019, move BE-018;
# both carry WR-013, the user-metadata round-trip invariant.
_MOVE_COPY_META_PARAMS = [
    pytest.param(
        "copy",
        Capability.COPY,
        id="copy",
        marks=[pytest.mark.spec("WR-013"), pytest.mark.spec("BE-019")],
    ),
    pytest.param(
        "move",
        Capability.MOVE,
        id="move",
        marks=[pytest.mark.spec("WR-013"), pytest.mark.spec("BE-018")],
    ),
]


@pytest.mark.spec("WR-001a")
def test_field_capability_map_covers_every_write_result_field() -> None:
    """BK-239: the field→capability map must classify every WriteResult field.

    Backend-independent guard. Adding a field to ``WriteResult`` without an
    entry in ``_FIELD_CAPABILITY`` fails here, forcing the author to declare
    the capability that gates it. This is the mechanism by which the generic
    symmetry assertion below inherits new field/capability pairs automatically.
    """
    assert {f.name for f in dataclasses.fields(WriteResult)} == set(_FIELD_CAPABILITY)


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

    @pytest.mark.spec("WR-005")
    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_populated_field_implies_declared_capability(self, backend: Backend, op: str, cap: Capability) -> None:
        """BK-239: generic field↔capability symmetry over every WriteResult field.

        Generalises the two per-pair under-declaration guards on the
        ``WriteResult`` fields themselves
        (``test_basic_source_leaves_rich_fields_none`` for the rich fields,
        ``test_metadata_is_none_when_not_passed`` for ``metadata``, both WR-012
        / WR-005 inspecting ``WriteResult`` directly — not the WR-013
        ``FileInfo`` round-trip guard):
        for every populated field, the capability that gates it
        (``_FIELD_CAPABILITY``) MUST be declared. Runs on all WRITE backends,
        not only the basic-source ones, so a backend that populates a gated
        field without declaring its capability fails regardless of direction.
        """
        _require(backend, cap)
        # Exercise the metadata→USER_METADATA branch non-vacuously where the
        # gate permits; metadata stays None (and the branch is vacuous) on
        # backends that do not declare it.
        meta = {"author": "symmetry"} if backend.capabilities.supports(Capability.USER_METADATA) else None
        result = getattr(backend, op)(f"wr/{op}-symmetry.txt", b"data", metadata=meta)
        for name, required in _FIELD_CAPABILITY.items():
            if required is not None and getattr(result, name) is not None:
                assert backend.capabilities.supports(required), (
                    f"{backend.name} populated WriteResult.{name} without declaring {required.name}"
                )

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
        assert result.size == info.size
        assert result.etag == info.etag
        assert result.digest == info.digest
        if info.modified_at is not None:
            assert result.last_modified == info.modified_at

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    def test_large_streamed_write_result_matches_file_info(
        self,
        backend: Backend,
        op: str,
        cap: Capability,
        request: pytest.FixtureRequest,
    ) -> None:
        """WR-001a: WriteResult↔FileInfo consistency on the large/streamed write path.

        Backends with a size-thresholded upload mechanism (S3 multipart,
        Azure block staging, Graph ``createUploadSession``) take a different
        code path for large payloads than the single-PUT path the sibling
        ``test_write_result_rich_fields_match_file_info`` exercises with a tiny
        ``bytes`` payload. A streamed ``_LARGE_WRITE_SIZE`` payload trips that
        path; the returned ``WriteResult`` must still agree with a subsequent
        ``get_file_info()`` on ``size`` and the rich fields. Gated to fixtures
        whose backend runs that path against a real endpoint (the
        ``large_write_distinct`` opt-in).
        """
        _require(backend, cap, Capability.METADATA)
        _skip_unless_large_write_distinct(backend)
        if backend.name in _LARGE_RICH_FIELDS_XFAIL:
            reason, strict = _LARGE_RICH_FIELDS_XFAIL[backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        key = f"wr/{op}-large-streamed.bin"
        result = getattr(backend, op)(key, io.BytesIO(b"\xab" * _LARGE_WRITE_SIZE))
        info = backend.get_file_info(key)
        assert result.size == info.size == _LARGE_WRITE_SIZE
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

    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_META_PARAMS)
    def test_metadata_round_trips_through_move_copy(self, backend: Backend, op: str, cap: Capability) -> None:
        """WR-013 round-trip applied to the move/copy paths (BK-195 / BK-233).

        BE-018/BE-019 Metadata invariant: a successful move/copy preserves the
        source file's user metadata, so ``get_file_info(dst)`` MUST return the
        same mapping the source carried before the operation.
        """
        _require(backend, cap, Capability.USER_METADATA, Capability.METADATA)
        meta = {"author": "carol", "stage": "bronze"}
        src = f"wr/{op}-meta-src.txt"
        dst = f"wr/{op}-meta-dst.txt"
        backend.write(src, b"data", metadata=meta)
        _do_op(backend, op, src, dst)
        info = backend.get_file_info(dst)
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
    @pytest.mark.spec("S3-013")
    @pytest.mark.spec("S3PA-015")
    def test_move(self, backend: Backend) -> None:
        _require(backend, Capability.MOVE)
        backend.write("mv_src.txt", b"data")
        backend.move("mv_src.txt", "mv_dst.txt")
        assert backend.exists("mv_src.txt") is False
        assert backend.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("BE-019")
    @pytest.mark.spec("SFTP-019")
    @pytest.mark.spec("SQL-BLOB-032")
    @pytest.mark.spec("AZ-018")
    @pytest.mark.spec("S3-014")
    @pytest.mark.spec("S3PA-014")
    @pytest.mark.spec("MEM-016b")
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

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    def test_self_op_preserves_data(self, backend: Backend, op: str, cap: Capability, overwrite: bool) -> None:
        """{move,copy}(src, src, overwrite={True,False}) is a no-op: source content preserved."""
        _require(backend, cap, Capability.WRITE)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-{op} yet")
        path = f"self_{op}_ow{overwrite}.txt"
        backend.write(path, b"data")
        _do_op(backend, op, path, path, overwrite=overwrite)
        assert backend.read_bytes(path) == b"data"

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_self_op_missing_raises_not_found(self, backend: Backend, op: str, cap: Capability) -> None:
        """{move,copy}(src, src) where src does not exist raises NotFound."""
        _require(backend, cap)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-{op} yet")
        path = f"sm_{op}_missing.txt"
        with pytest.raises(NotFound, match=f"sm_{op}_missing"):
            _do_op(backend, op, path, path)

    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    def test_self_op_on_directory_raises_invalid_path(self, backend: Backend, op: str, cap: Capability) -> None:
        """{move,copy}(src, src) where src is a directory raises InvalidPath.

        BE-018/019 src-type precondition; BE-021 error mapping.
        """
        _require(backend, cap)
        if not _fixture_record(backend).self_op_supported:
            pytest.skip(f"Backend {backend.name!r} does not handle self-{op} yet")
        _skip_flat_namespace(backend, "flat-namespace backends cannot distinguish file vs folder")
        backend.write(f"sd_{op}/file.txt", b"x")
        with pytest.raises(InvalidPath, match=f"sd_{op}"):
            _do_op(backend, op, f"sd_{op}", f"sd_{op}")


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


# ID-191: BE-018 observable contract — model-level encoding paired with
# sdd/formal/ResourceSafety.dfy § 2.3 (MoveContract / ObservableForAtomicMove).
# Lives in test_atomic.py with the rest of the BE-018 conformance, but is
# *not* parametrised over fixture_params: it constructs its own in-process
# backend and wraps it in a crash-injecting shim. The wrapper raises at a
# configurable point in a copy-then-delete protocol, modelling the failure
# windows the Dafny § 2.3 contract reasons about. No oracle certifies this
# test (crash injection has no compiled-MemoryBackend equivalent), and no
# parametrised backend fixture exercises it — the @pytest.mark.spec("BE-018")
# marker is for traceability into the spec coverage matrix only (per
# sdd/BACKLOG.md ID-191).
#
# Test discipline: a deterministic wrapper makes the OR assertion derivable
# from the wrapper's own code, which is a tautology rather than a property
# observation.  To give the test genuine discriminating power, the matrix
# carries two BE-018-respecting shapes (after_copy, after_delete) AND one
# BE-018-violating shape (delete_first).  The conformance test asserts the
# OR holds on the first two; a sibling test asserts the OR *fails* on the
# violating shape, proving that the disjunction is non-vacuous as an
# observation: a wrapper that violated the contract WOULD be caught here.

# BE-018-respecting wrapper shapes — exercised by the positive test.
_CRASH_POINTS_OK = [
    pytest.param("after_copy", id="after_copy"),
    pytest.param("after_delete", id="after_delete"),
]


class _CopyDeleteCrash:
    """Move-only wrapper that injects a crash at a configurable point.

    Not a full ``Backend`` substitute: only ``move`` is implemented. Tests
    use the inner backend directly for seeding and post-state assertions.

    ``crash_point`` values:

    - ``after_copy``: ``inner.copy(src, dst); raise`` — crash strictly
      between copy success and delete start. Source is untouched, dst was
      materialised by the copy. Discharges the left disjunct of BE-018's
      OR (``src_present``). Satisfies BE-018.
    - ``after_delete``: ``inner.copy(src, dst); inner.delete(src); raise``
      — crash after delete succeeded but before the wrapper returns
      success. Source is gone, dst is intact. Discharges the right
      disjunct (``dst_present``). Satisfies BE-018.
    - ``delete_first``: ``inner.delete(src); raise`` — delete the source
      WITHOUT first copying it. Source is gone, dst was never written.
      VIOLATES BE-018: both gone. Used by the negative test below to
      prove the OR assertion is non-vacuous.
    """

    def __init__(self, inner: Backend, crash_point: str) -> None:
        self._inner = inner
        self._crash_point = crash_point

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        if self._crash_point == "delete_first":
            # BE-018-violating shape: delete src without copying.  No
            # `overwrite` use — the inner.delete is unconditional.
            del overwrite
            self._inner.delete(src)
            raise RuntimeError(f"simulated crash at {self._crash_point}")
        self._inner.copy(src, dst, overwrite=overwrite)
        if self._crash_point == "after_delete":
            self._inner.delete(src)
        raise RuntimeError(f"simulated crash at {self._crash_point}")


class TestMoveCrashInjection:
    """BE-018 § Atomicity: copy-then-delete crash leaves data recoverable.

    Encodes the non-loss invariant — source intact OR destination intact,
    never both gone — at the move *protocol* layer, paired with the Dafny
    § 2.3 MoveContract that excludes ObservedCopyDone by construction.

    Two positive shapes exercise the OR from both directions; one negative
    shape (BE-018-violating) demonstrates the assertion is non-vacuous.
    """

    @pytest.mark.spec("BE-018")
    @pytest.mark.parametrize("crash_point", _CRASH_POINTS_OK)
    def test_partial_move_preserves_at_least_one_copy(self, crash_point: str) -> None:
        """Positive: BE-018-respecting wrapper shapes satisfy the OR."""
        from remote_store.backends._memory import MemoryBackend

        inner = MemoryBackend()
        wrapper = _CopyDeleteCrash(inner, crash_point)
        inner.write("crash_src.txt", b"payload")

        with pytest.raises(RuntimeError, match="simulated crash"):
            wrapper.move("crash_src.txt", "crash_dst.txt")

        src_present = inner.exists("crash_src.txt")
        dst_present = inner.exists("crash_dst.txt")
        # BE-018 contract: never both gone. The Dafny § 2.3 MoveContract
        # excludes ObservedCopyDone (src gone, dst not yet written) for
        # atomic backends; this OR is its conformance shadow. Non-trivially
        # discharged in both directions across the _CRASH_POINTS_OK matrix:
        # `after_copy` carries the left disjunct, `after_delete` the right.
        assert src_present or dst_present, "BE-018: source intact OR destination intact (never both gone)"
        # Whichever side(s) survive, the surviving content must be intact —
        # BE-018 forbids silent corruption alongside the non-loss invariant.
        if src_present:
            assert inner.read_bytes("crash_src.txt") == b"payload"
        if dst_present:
            assert inner.read_bytes("crash_dst.txt") == b"payload"

    @pytest.mark.spec("BE-018")
    def test_or_assertion_catches_be018_violation(self) -> None:
        """Negative: a BE-018-violating wrapper makes the OR fail.

        Proves the OR is non-vacuous: a copy-then-delete protocol that
        crashes leaving both gone (the `delete_first` shape) trips the
        same assertion the positive test discharges. Without this case
        the assertion is structurally tautological for the in-process
        wrapper — the wrapper's own code determines the post-state, so
        verifying the post-state would amount to verifying the wrapper.
        Running the assertion against a known-bad wrapper and observing
        it fail is what distinguishes the test from such a tautology.
        """
        from remote_store.backends._memory import MemoryBackend

        inner = MemoryBackend()
        wrapper = _CopyDeleteCrash(inner, "delete_first")
        inner.write("crash_src.txt", b"payload")

        with pytest.raises(RuntimeError, match="simulated crash"):
            wrapper.move("crash_src.txt", "crash_dst.txt")

        src_present = inner.exists("crash_src.txt")
        dst_present = inner.exists("crash_dst.txt")
        # The BE-018-violating shape: both gone.  The OR assertion that
        # the positive test discharges would fail here — assert that it
        # would, directly.
        assert not src_present
        assert not dst_present
        # If a future change accidentally made src_present or dst_present
        # True for delete_first, this AssertionError would bite, alerting
        # to a wrapper-shape drift that silently weakens the negative test.
        with pytest.raises(
            AssertionError,
            match="BE-018: source intact OR destination intact",
        ):
            assert src_present or dst_present, "BE-018: source intact OR destination intact (never both gone)"
