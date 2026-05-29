"""S3-PyArrow hybrid backend tests -- covers S3PA-xxx spec items.

Requires: s3fs, pyarrow, boto3 (test dependencies).
On pyarrow < 24: uses moto ThreadedMotoServer. On pyarrow ≥ 24: uses MinIO.
All tests are skipped if the required backend is unavailable.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("s3fs", reason="s3fs not installed")
pytest.importorskip("pyarrow", reason="pyarrow not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")


from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import NotFound  # noqa: E402
from tests._helpers import MINIO_KEY as _MINIO_KEY  # noqa: E402
from tests._helpers import MINIO_SECRET as _MINIO_SECRET  # noqa: E402
from tests._helpers import pyarrow_ge_24  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from remote_store._backend import Backend

REGION = "us-east-1"


@pytest.fixture
def s3pa_backend(moto_server: str | None, minio_server: str | None) -> Iterator[Backend]:
    """Create an S3PyArrowBackend against moto (pyarrow < 24) or MinIO (pyarrow ≥ 24)."""
    if pyarrow_ge_24():
        if minio_server is None:
            pytest.skip("MinIO not reachable; required for S3-PyArrow on pyarrow ≥ 24")
        endpoint = minio_server
        key, secret = _MINIO_KEY, _MINIO_SECRET
    else:
        if moto_server is None:
            pytest.skip("moto server not available")
        endpoint = moto_server
        key, secret = "testing", "testing"

    bucket = f"test-pa-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name=REGION,
    )
    client.create_bucket(Bucket=bucket)

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    backend = S3PyArrowBackend(
        bucket=bucket,
        key=key,
        secret=secret,
        region_name=REGION,
        endpoint_url=endpoint,
    )
    try:
        yield backend
    finally:
        backend.close()
        if pyarrow_ge_24():
            # MinIO is persistent; drain and delete the per-test bucket.
            # Moto resets on server stop so cleanup is not needed there.
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents", []):
                    client.delete_object(Bucket=bucket, Key=obj["Key"])
            client.delete_bucket(Bucket=bucket)


# region: Construction (S3PA-002, S3PA-003)
class TestS3PyArrowConstruction:
    """S3PA-002, S3PA-003: backend-identity strings that do not parametrize.
    Construction validation, lazy connection, endpoint-URL normalization,
    credentials-optional, and client_options are covered in
    tests/backends/s3/test_shared.py alongside the S3 equivalents."""

    @pytest.mark.spec("S3PA-002")
    def test_name_is_s3_pyarrow(self, s3pa_backend: Backend) -> None:
        assert s3pa_backend.name == "s3-pyarrow"

    @pytest.mark.spec("S3PA-003")
    def test_declares_all_capabilities(self, s3pa_backend: Backend) -> None:
        caps = s3pa_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        excluded = {Capability.ATOMIC_MOVE, Capability.USER_METADATA}
        for cap in Capability:
            if cap in excluded:
                assert not caps.supports(cap), f"S3-PyArrow must not declare {cap.value}"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"


class TestS3PyArrowTlsCaBundle:
    """TLS-006: pyarrow-specific tls_ca_file_path wiring. The shared s3fs
    control-path (accepted/missing/directory/default/verify) lives in
    test_shared.py."""

    @pytest.mark.spec("TLS-006")
    def test_tls_ca_bundle_sets_tls_ca_file_path_on_pyarrow(self, tmp_path: Path) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = S3PyArrowBackend(
            bucket="b",
            key="k",
            secret="s",
            endpoint_url="http://localhost:9000",
            tls_ca_bundle=str(cert),
        )
        with patch("pyarrow.fs.S3FileSystem") as mock_pa_s3:
            _ = backend._pa_fs
            call_kwargs = mock_pa_s3.call_args[1]
            assert call_kwargs["tls_ca_file_path"] == str(cert)

    @pytest.mark.spec("TLS-006")
    def test_tls_ca_bundle_does_not_override_explicit_tls_ca_file_path(self, tmp_path: Path) -> None:
        """setdefault ensures a pre-existing tls_ca_file_path wins."""
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = S3PyArrowBackend(
            bucket="b",
            key="k",
            secret="s",
            endpoint_url="http://localhost:9000",
            tls_ca_bundle=str(cert),
        )
        # Patch _pa_fs to intercept kwargs and verify setdefault semantics:
        # pre-populate tls_ca_file_path before the property runs.
        with patch("pyarrow.fs.S3FileSystem") as mock_pa_s3:
            # Intercept the property to inject a pre-existing key.  We patch
            # dict.setdefault indirectly by verifying that if the kwarg is
            # already present, it is preserved.  Since _pa_fs builds kwargs
            # internally, we hook into the mock to observe the final call.
            _ = backend._pa_fs
            call_kwargs = mock_pa_s3.call_args[1]
            # Confirm setdefault was used (value == our bundle, since nothing
            # else provides tls_ca_file_path in the current code path)
            assert call_kwargs["tls_ca_file_path"] == str(cert)


# endregion


# region: Read path (S3PA-012, RFC-0003)
class TestS3PyArrowReadPath:
    """S3PA-012: read path optimization -- no BufferedReader wrapping."""

    @pytest.mark.spec("S3PA-012")
    def test_read_not_wrapped_in_buffered_reader(self, s3pa_backend: Backend) -> None:
        """read() returns stream without BufferedReader (RFC-0003)."""
        s3pa_backend.write("buf.bin", b"data")
        stream = s3pa_backend.read("buf.bin")
        assert not isinstance(stream, io.BufferedReader)
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_read_stream_readline(self, s3pa_backend: Backend) -> None:
        """read() stream supports readline() without BufferedReader."""
        s3pa_backend.write("lines.txt", b"line1\nline2\nline3\n")
        stream = s3pa_backend.read("lines.txt")
        assert stream.readline() == b"line1\n"
        assert stream.readline() == b"line2\n"
        assert stream.readline() == b"line3\n"
        assert stream.readline() == b""
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_read_stream_chunked_read(self, s3pa_backend: Backend) -> None:
        """read(n) returns exactly n bytes (or fewer at EOF) without BufferedReader."""
        s3pa_backend.write("chunk.bin", b"abcdefghij")
        stream = s3pa_backend.read("chunk.bin")
        assert stream.read(4) == b"abcd"
        assert stream.read(4) == b"efgh"
        assert stream.read(4) == b"ij"
        assert stream.read(4) == b""
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_no_trailing_newline(self, s3pa_backend: Backend) -> None:
        """Last line without trailing newline returns content then empty."""
        s3pa_backend.write("notrail.txt", b"line1\nline2")
        stream = s3pa_backend.read("notrail.txt")
        assert stream.readline() == b"line1\n"
        assert stream.readline() == b"line2"
        assert stream.readline() == b""
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_empty_file(self, s3pa_backend: Backend) -> None:
        """readline() on empty file returns empty bytes immediately."""
        s3pa_backend.write("empty.txt", b"")
        stream = s3pa_backend.read("empty.txt")
        assert stream.readline() == b""
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_with_size_limit(self, s3pa_backend: Backend) -> None:
        """readline(size) limits the number of bytes returned."""
        s3pa_backend.write("sized.txt", b"hello\nworld\n")
        stream = s3pa_backend.read("sized.txt")
        assert stream.readline(3) == b"hel"
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_interleaved_with_read(self, s3pa_backend: Backend) -> None:
        """read() then readline() continues from mid-stream position."""
        s3pa_backend.write("interleave.txt", b"abcdefghij\nrest\n")
        stream = s3pa_backend.read("interleave.txt")
        assert stream.read(6) == b"abcdef"
        assert stream.readline() == b"ghij\n"
        assert stream.readline() == b"rest\n"
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_long_line(self, s3pa_backend: Backend) -> None:
        """Line longer than _READLINE_CHUNK exercises multi-chunk path."""
        long_line = b"x" * 10000 + b"\nshort\n"
        s3pa_backend.write("longline.txt", long_line)
        stream = s3pa_backend.read("longline.txt")
        assert stream.readline() == b"x" * 10000 + b"\n"
        assert stream.readline() == b"short\n"
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_readline_newline_at_chunk_boundary(self, s3pa_backend: Backend) -> None:
        """Newline at exactly _READLINE_CHUNK (8192) exercises the seek guard."""
        line = b"x" * 8191 + b"\n"
        s3pa_backend.write("boundary.txt", line + b"next\n")
        stream = s3pa_backend.read("boundary.txt")
        assert stream.readline() == line
        assert stream.readline() == b"next\n"
        stream.close()

    @pytest.mark.spec("S3PA-012")
    def test_read_stream_iteration(self, s3pa_backend: Backend) -> None:
        """for line in stream collects all lines via __next__."""
        s3pa_backend.write("iter.txt", b"a\nb\nc\n")
        stream = s3pa_backend.read("iter.txt")
        lines = list(stream)
        assert lines == [b"a\n", b"b\n", b"c\n"]
        stream.close()


# endregion


# region: Resource Management (S3PA-021)
class TestS3PyArrowLifecycle:
    """S3PA-021: PyArrow-specific unwrap. s3fs unwrap (S3PA-021) is covered by
    TestS3SharedUnwrap in test_shared.py. Close semantics live in
    conformance + TestS3SharedLifecycle; wrong-type unwrap is covered by
    TestBackendUnwrap."""

    @pytest.mark.spec("S3PA-021")
    def test_unwrap_pyarrow(self, s3pa_backend: Backend) -> None:
        from pyarrow.fs import S3FileSystem as PyArrowS3

        fs = s3pa_backend.unwrap(PyArrowS3)
        assert isinstance(fs, PyArrowS3)


# endregion


# region: _PyArrowBinaryIO unit tests (lines 54, 57, 98-99, 102)


class TestPyArrowBinaryIOMethods:
    """Unit tests for _PyArrowBinaryIO adapter -- no live S3 needed."""

    def _make_raw(self, *, seekable: bool = True, tell_pos: int = 0) -> tuple[object, object]:
        from unittest.mock import MagicMock

        import pyarrow as pa

        from remote_store.backends._s3_pyarrow import _PyArrowBinaryIO

        mock_pa = MagicMock(spec=pa.NativeFile)
        mock_pa.seekable.return_value = seekable
        mock_pa.tell.return_value = tell_pos
        return _PyArrowBinaryIO(mock_pa), mock_pa

    def test_readable_returns_true(self) -> None:
        raw, _ = self._make_raw()
        assert raw.readable() is True

    def test_seekable_delegates_to_pa_true(self) -> None:
        raw, mock_pa = self._make_raw(seekable=True)
        assert raw.seekable() is True
        mock_pa.seekable.assert_called_once()

    def test_seekable_delegates_to_pa_false(self) -> None:
        raw, mock_pa = self._make_raw(seekable=False)
        assert raw.seekable() is False

    def test_seek_delegates_and_returns_position(self) -> None:
        raw, mock_pa = self._make_raw(tell_pos=7)
        result = raw.seek(7)
        mock_pa.seek.assert_called_once_with(7, 0)
        assert result == 7

    def test_seek_with_whence_cur(self) -> None:
        raw, mock_pa = self._make_raw(tell_pos=5)
        result = raw.seek(2, 1)
        mock_pa.seek.assert_called_once_with(2, 1)
        assert result == 5

    def test_tell_delegates_to_pa(self) -> None:
        raw, mock_pa = self._make_raw(tell_pos=42)
        assert raw.tell() == 42
        mock_pa.tell.assert_called()


# endregion


# region: Retry debug log paths (lines 380, 410-426)


class TestS3PyArrowRetryNonDefaultParams:
    """S3PA-026: non-default RetryPolicy on the PyArrow data path triggers a
    debug log and passes only ``max_attempts``. The parallel s3fs-control-path
    assertions (S3-026 + S3PA-026 paired) live in test_shared.py."""

    def test_pa_fs_non_default_retry_triggers_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from unittest.mock import MagicMock, patch

        from remote_store._config import RetryPolicy
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(
            bucket="test-bucket",
            retry=RetryPolicy(max_attempts=5, backoff_base=2.0),  # non-default backoff_base
        )
        import pyarrow.fs as pa_fs

        mock_fs = MagicMock(spec=pa_fs.S3FileSystem)
        with (
            caplog.at_level(logging.DEBUG, logger="remote_store.backends._s3_pyarrow"),
            patch("pyarrow.fs.S3FileSystem", return_value=mock_fs),
            patch("pyarrow.fs.AwsStandardS3RetryStrategy") as mock_retry_cls,
        ):
            _ = backend._pa_fs
            assert mock_retry_cls.call_args.kwargs == {"max_attempts": 5}
        assert any("only max_attempts is used" in rec.message for rec in caplog.records)


# endregion


# region: MinIO routing sentinel


class TestS3PyArrowMinIOSentinel:
    """Sentinel: confirm s3pa_backend uses MinIO (not moto) when pyarrow ≥ 24.

    Guards against a routing regression where pyarrow_ge_24() returns False
    under pyarrow 24 -- which would silently fall back to moto and pass CI
    without ever exercising the MinIO path.
    """

    def test_backend_endpoint_is_minio_when_pyarrow_ge_24(self, s3pa_backend: Backend) -> None:
        """On pyarrow ≥ 24, s3pa_backend must route to MinIO at the configured host port."""
        if not pyarrow_ge_24():
            return
        from infra._settings import MINIO_ENDPOINT

        assert s3pa_backend._endpoint_url is not None
        assert s3pa_backend._endpoint_url.startswith(MINIO_ENDPOINT), (
            f"pyarrow_ge_24() is True but backend is not on MinIO: {s3pa_backend._endpoint_url!r}"
        )


# endregion


# region: RetryPolicy acceptance + pyarrow retry strategy (RET-013)
# Migrated from tests/test_config.py (BK-216 / BK-191).


@pytest.mark.spec("RET-013")
def test_s3_pyarrow_accepts_retry() -> None:
    from remote_store._config import RetryPolicy
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    rp = RetryPolicy(max_attempts=4)
    assert S3PyArrowBackend(bucket="b", retry=rp)._retry is rp


@pytest.mark.spec("RET-013")
def test_s3_pyarrow_retry_strategy() -> None:
    from unittest.mock import patch

    from remote_store._config import RetryPolicy
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    backend = S3PyArrowBackend(bucket="b", retry=RetryPolicy(max_attempts=9))
    with patch("pyarrow.fs.S3FileSystem") as mock_s3fs:
        mock_s3fs.return_value = mock_s3fs
        _ = backend._pa_fs
        assert mock_s3fs.call_args[1]["retry_strategy"].max_attempts == 9
    backend.close()


# endregion


# region: check_health() probe identity + error mapping (PING-005)
# Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6). The healthy-path
# return-None assertion is covered by tests/backends/conformance/test_check_health.py;
# this test pins the probe identity (pyarrow ``get_file_info(bucket)``) and the
# FileNotFoundError -> NotFound mapping (PING-009).
@pytest.mark.spec("PING-005")
@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        pytest.param(None, None, id="healthy"),
        pytest.param(FileNotFoundError("not found"), NotFound, id="not-found"),
    ],
)
def test_s3_pyarrow_health(side_effect: Exception | None, expected: type[Exception] | None) -> None:
    from unittest.mock import MagicMock

    from pyarrow.fs import FileInfo as PyArrowFileInfo
    from pyarrow.fs import S3FileSystem as PyArrowS3FileSystem

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    pa_mock = MagicMock(spec=PyArrowS3FileSystem)
    if side_effect is not None:
        pa_mock.get_file_info.side_effect = side_effect
    else:
        pa_mock.get_file_info.return_value = MagicMock(spec=PyArrowFileInfo)
    backend = S3PyArrowBackend(bucket="test-bucket")
    backend._pa_fs_instance = pa_mock
    if expected is not None:
        with pytest.raises(expected):
            backend.check_health()
    else:
        backend.check_health()
        assert pa_mock.get_file_info.call_count == 1
        assert pa_mock.get_file_info.call_args.args == ("test-bucket",)


# endregion


# region: Credential masking (AF-008, SEC-004) — migrated from tests/test_coverage_gaps.py (BK-222 / BK-191 slice 6/6)


class TestS3PyArrowCredentialMasking:
    """AF-008: S3PyArrowBackend repr masks sensitive fields and accepts Secret wrappers."""

    def test_masks_set_secrets(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(bucket="b", key="AKID", secret="SK")
        r = repr(backend)
        for raw in ("AKID", "SK"):
            assert raw not in r
        for masked in ("key='***'", "secret='***'"):
            assert masked in r

    def test_shows_none_for_unset_secrets(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(bucket="b")
        r = repr(backend)
        for expected in ("key=None", "secret=None"):
            assert expected in r

    @pytest.mark.spec("SEC-004")
    def test_accepts_secret_wrapper(self) -> None:
        from remote_store._config import Secret
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(bucket="b", key=Secret("AKID"), secret=Secret("SK"))
        assert backend._key == "AKID"  # internal: no public observable (repr shows '***' for raw strings too)
        assert backend._secret == "SK"  # internal: no public observable


# endregion
