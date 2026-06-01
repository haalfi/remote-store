"""boto3-direct S3 lane (ID-202 PoC): error mapping + BUG-214 atomicity.

These tests pin the two contracts the ID-202 backlog calls out for the
``S3Boto3Backend``:

* **ID-200 error mapping.** ``_classify_error`` reads
  ``ClientError.response['Error']['Code']`` directly. moto enforces neither
  IAM nor credential validity, so a real 403 is unreachable in-process
  (``sdd/research/research-s3-error-mapping-fidelity.md`` rows (b)/(c));
  the 403 / credential rows are therefore pinned at the *mapping boundary*
  by feeding realistic ``ClientError``s through ``_classify_error``, exactly
  as the ID-200 audit did for the s3fs lane. The 404 row is reproducible on
  moto and is asserted over the (mocked) wire.
* **BUG-214 atomicity.** Unlike the s3fs lane, a mid-stream content failure
  must leave **no** object: ``put_object`` never sends a truncated body and
  ``upload_fileobj`` aborts the multipart upload on exception. The s3fs lane
  needed an explicit ``discard()`` fix (see ``test_moto.py``); the boto3 lane
  gets the guarantee by construction, and this test proves it.

Deliberately boto3-only: no ``s3fs`` / ``aiobotocore`` import-skip, because
retiring that stack is the whole point of the lane.

The live 403-mapping test and the >5 GB multipart smoke are opt-in
(``RS_TEST_LIVE_S3=1``; the 5 GB case additionally needs ``RS_TEST_S3_5GB=1``)
and never run in ``hatch run all``.
"""

from __future__ import annotations

import io
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests._helpers import FailingContentReader

pytest.importorskip("boto3")
pytest.importorskip("botocore")
pytest.importorskip("moto")

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store.backends._s3_boto3 import S3Boto3Backend

_MB = 1024 * 1024


class _ZeroStream(io.RawIOBase):
    """Read-only stream that yields ``size`` NUL bytes without allocating them."""

    def __init__(self, size: int) -> None:
        super().__init__()
        self._remaining = size

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        if self._remaining <= 0:
            return 0
        n = min(len(b), self._remaining)
        b[:n] = b"\x00" * n
        self._remaining -= n
        return n


@pytest.fixture(scope="module")
def moto_bucket(moto_server: str | None) -> Iterator[tuple[str, str]]:
    """Create one bucket on the shared moto server for the whole module."""
    if moto_server is None:
        pytest.skip("moto / boto3 not available")
    import boto3

    bucket = f"id202-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    try:
        yield moto_server, bucket
    finally:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        client.delete_bucket(Bucket=bucket)
        client.close()


def _make_backend(endpoint: str, bucket: str) -> S3Boto3Backend:
    from remote_store.backends._s3_boto3 import S3Boto3Backend

    return S3Boto3Backend(
        bucket=bucket,
        endpoint_url=endpoint,
        key="testing",
        secret="testing",
        region_name="us-east-1",
    )


class _RaisingClient:
    """Stub boto3 client whose every call raises a fabricated exception.

    Injected into ``backend._client_instance`` (the same fixture-injection the
    s3fs lane uses for ``_fs_instance``) so the error-mapping rows moto cannot
    reproduce (403 / credential / 5xx) are driven through the **public**
    ``read_bytes`` / ``get_file_info`` surface rather than calling the private
    ``_classify_error`` directly -- TESTING.md Rule 8 (tests survive renames).
    """

    def __init__(self, exc: Exception, *, head_response: dict | None = None) -> None:
        self._exc = exc
        self._head_response = head_response

    def get_object(self, **_kwargs: object) -> object:
        raise self._exc

    def head_object(self, **_kwargs: object) -> object:
        if self._head_response is not None:
            return self._head_response
        raise self._exc


def _backend_raising(exc: Exception) -> S3Boto3Backend:
    backend = _make_backend("http://localhost:1", "b")
    backend._client_instance = _RaisingClient(exc)
    return backend


@pytest.mark.spec("S3-010")
class TestBug214MidStreamFailure:
    """A mid-stream content failure must not commit a truncated object.

    The s3fs lane committed a truncated-but-complete object because
    ``S3File.__exit__`` flushed on the exception path (BUG-214). The boto3
    lane uses ``put_object`` (single, below the 8 MB transfer threshold) and
    ``upload_fileobj`` (multipart, above it); neither leaves an object when
    the content source raises -- the PUT body is never completed and the
    multipart upload is aborted. Both regimes are asserted to leave neither
    an object nor an orphaned multipart upload (S3-010 / AW-001).
    """

    @pytest.mark.parametrize("op", ["write", "write_atomic"])
    @pytest.mark.parametrize(
        ("fill", "regime"),
        [(4 * _MB, "single-put"), (12 * _MB, "multipart")],
    )
    def test_no_truncated_object_on_mid_stream_failure(
        self,
        moto_bucket: tuple[str, str],
        op: str,
        fill: int,
        regime: str,
    ) -> None:
        import boto3

        from remote_store._errors import RemoteStoreError

        endpoint, bucket = moto_bucket
        key = f"bug214/{op}-{regime}.bin"
        backend = _make_backend(endpoint, bucket)
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        try:
            with pytest.raises(RemoteStoreError):
                getattr(backend, op)(key, FailingContentReader.buffered(fill), overwrite=True)

            # No truncated object was committed ...
            listed = client.list_objects_v2(Bucket=bucket, Prefix=key).get("Contents", [])
            assert [obj["Key"] for obj in listed if obj["Key"] == key] == []
            # ... and no multipart upload was left orphaned.
            uploads = client.list_multipart_uploads(Bucket=bucket).get("Uploads", [])
            assert [up for up in uploads if up["Key"] == key] == []
        finally:
            backend.close()
            client.close()


class TestClientErrorClassification:
    """Error mapping pinned through the PUBLIC ``read_bytes`` surface (ID-200).

    moto enforces neither IAM nor credential validity, so the 403 / credential
    and 5xx rows are unreachable in-process (ID-200 rows (b)/(c)). A
    ``_RaisingClient`` injected for the call makes ``read_bytes`` surface the
    fabricated exception through ``_boto_errors`` -> ``_classify_error``,
    exercising the mapping boundary without calling the private classifier
    (TESTING.md Rule 8). The 404 row is covered over the real moto wire by
    ``TestNotFoundOverTheWire``. Every typed error carries
    ``backend == "s3-boto3"``.
    """

    def _client_error(self, code: str, status: int):
        from botocore.exceptions import ClientError

        return ClientError(
            {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
            "GetObject",
        )

    @pytest.mark.spec("S3-016", "S3-018")
    @pytest.mark.parametrize(
        ("code", "status"),
        [
            ("AccessDenied", 403),
            ("InvalidAccessKeyId", 403),
            ("SignatureDoesNotMatch", 403),
            ("ExpiredToken", 400),  # ID-200 §3(c): HTTP 400 yet a credential failure
        ],
    )
    def test_permission_codes_map_to_permission_denied(self, code: str, status: int) -> None:
        from remote_store._errors import PermissionDenied

        backend = _backend_raising(self._client_error(code, status))
        with pytest.raises(PermissionDenied) as exc_info:
            backend.read_bytes("k")
        assert exc_info.value.backend == "s3-boto3"

    # No @pytest.mark.spec: S3-017 covers *connection* errors only
    # (008-s3-backend.md:151); no spec clause maps HTTP 5xx server responses to
    # BackendUnavailable. The mapping is intentional but unspecced -- a Ship
    # promotion adds the clause (or a dedicated S3B-* ID) before marking.
    @pytest.mark.parametrize(
        ("code", "status"), [("InternalError", 500), ("ServiceUnavailable", 503), ("SlowDown", 503)]
    )
    def test_server_codes_map_to_backend_unavailable(self, code: str, status: int) -> None:
        from remote_store._errors import BackendUnavailable

        backend = _backend_raising(self._client_error(code, status))
        with pytest.raises(BackendUnavailable) as exc_info:
            backend.read_bytes("k")
        assert exc_info.value.backend == "s3-boto3"

    @pytest.mark.spec("S3-017")
    def test_endpoint_connection_error_maps_backend_unavailable(self) -> None:
        from botocore.exceptions import EndpointConnectionError

        from remote_store._errors import BackendUnavailable

        backend = _backend_raising(EndpointConnectionError(endpoint_url="http://x"))
        with pytest.raises(BackendUnavailable) as exc_info:
            backend.read_bytes("k")
        assert exc_info.value.backend == "s3-boto3"

    def test_unknown_client_error_code_maps_to_base_error(self) -> None:
        """An unrecognised ClientError code falls through to the base RemoteStoreError."""
        from remote_store._errors import RemoteStoreError

        backend = _backend_raising(self._client_error("TeapotError", 418))
        with pytest.raises(RemoteStoreError) as exc_info:
            backend.read_bytes("k")
        assert type(exc_info.value) is RemoteStoreError  # base type, not a subtype
        assert exc_info.value.backend == "s3-boto3"

    def test_non_botocore_exception_maps_via_message(self) -> None:
        """A non-botocore exception routes through the shared message classifier."""
        from remote_store._errors import RemoteStoreError

        backend = _backend_raising(RuntimeError("mystery failure"))
        with pytest.raises(RemoteStoreError) as exc_info:
            backend.read_bytes("k")
        assert exc_info.value.backend == "s3-boto3"


class TestNotFoundOverTheWire:
    """A real moto 404 surfaces as ``NotFound`` through the boto3 lane (S3-015)."""

    @pytest.mark.spec("S3-015")
    def test_read_bytes_missing_maps_not_found(self, moto_bucket: tuple[str, str]) -> None:
        from remote_store._errors import NotFound

        endpoint, bucket = moto_bucket
        backend = _make_backend(endpoint, bucket)
        try:
            with pytest.raises(NotFound) as exc_info:
                backend.read_bytes("does/not/exist.txt")
            assert exc_info.value.backend == "s3-boto3"
        finally:
            backend.close()

    @pytest.mark.spec("S3-015")
    def test_get_file_info_missing_maps_not_found(self, moto_bucket: tuple[str, str]) -> None:
        from remote_store._errors import NotFound

        endpoint, bucket = moto_bucket
        backend = _make_backend(endpoint, bucket)
        try:
            with pytest.raises(NotFound) as exc_info:
                backend.get_file_info("does/not/exist.txt")
            assert exc_info.value.backend == "s3-boto3"
        finally:
            backend.close()


class TestS3Boto3Lifecycle:
    """Construction-path coverage + s3fs-lane parity for the retry policy."""

    def test_retry_policy_round_trips(self, moto_bucket: tuple[str, str]) -> None:
        """A RetryPolicy maps to botocore and the backend still round-trips.

        Mirrors the s3fs lane's ``test_lifecycle_with_retry_policy``. The
        non-default ``backoff_base`` exercises the "only max_attempts is
        mappable" debug branch in ``_build_boto_config``.
        """
        from remote_store._config import RetryPolicy
        from remote_store.backends._s3_boto3 import S3Boto3Backend

        endpoint, bucket = moto_bucket
        backend = S3Boto3Backend(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            retry=RetryPolicy(max_attempts=5, backoff_base=2.0),
        )
        try:
            backend.write("retry/probe.txt", b"hello", overwrite=True)
            assert backend.read_bytes("retry/probe.txt") == b"hello"
        finally:
            backend.delete("retry/probe.txt", missing_ok=True)
            backend.close()

    def test_unwrap_returns_boto_client(self) -> None:
        """``unwrap(BaseClient)`` returns the native boto3 S3 client (S3-020 shape)."""
        from botocore.client import BaseClient

        backend = _make_backend("http://localhost:1", "b")
        try:
            assert isinstance(backend.unwrap(BaseClient), BaseClient)
        finally:
            backend.close()

    def test_malformed_checksum_yields_no_digest(self) -> None:
        """A non-decodable checksum field is swallowed; ``digest`` is ``None``."""
        backend = _make_backend("http://localhost:1", "b")
        backend._client_instance = _RaisingClient(
            AssertionError("unused"),
            head_response={"ContentLength": 0, "ChecksumSHA256": "abc"},  # bad base64
        )
        try:
            assert backend.get_file_info("k").digest is None
        finally:
            backend.close()

    # No @pytest.mark.spec: this pins the S3 analogue of SEEK-006 (Azure Range
    # Reader Override) on a lane that SEEK-004 still classifies as a read()
    # passthrough; the boto3-lane axiom (a future S3B-* referencing SEEK-006)
    # does not exist yet. See research-s3-boto3-poc.md § 4a.
    def test_read_seekable_is_unbuffered_and_seeks(self, moto_bucket: tuple[str, str]) -> None:
        """``read_seekable`` returns a seekable, **unbuffered** Range stream.

        PyArrow's random ``read_at`` consumes this path; a ``BufferedReader``
        here would pay a full-buffer GET per seek (Azure / S3PyArrow contract),
        so the override must not be buffered. Also verifies a seek+read.
        """
        endpoint, bucket = moto_bucket
        backend = _make_backend(endpoint, bucket)
        try:
            backend.write("seek/probe.bin", bytes(range(256)) * 8, overwrite=True)
            stream = backend.read_seekable("seek/probe.bin")
            try:
                assert stream.seekable()
                assert not isinstance(stream, io.BufferedReader)
                assert stream.seek(100) == 100
                assert stream.read(4) == bytes([100, 101, 102, 103])
            finally:
                stream.close()
        finally:
            backend.delete("seek/probe.bin", missing_ok=True)
            backend.close()


# ---------------------------------------------------------------------------
# Opt-in live tests (never run in `hatch run all`).
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("RS_TEST_LIVE_S3") != "1",
    reason="live boto3-lane S3 tests are opt-in via RS_TEST_LIVE_S3=1",
)
class TestS3Boto3Live:
    """Live-AWS confirmation for the boto3 lane (ID-202).

    Mirrors BK-248 for the s3fs lane: a backend built with bogus credentials
    yields a real 403 over the wire that ``_classify_error`` maps to
    ``PermissionDenied``. The >5 GB multipart smoke proves the s3fs-fuse
    restart cliff (one of the three pains ID-202 retires) is gone -- it is
    additionally gated behind ``RS_TEST_S3_5GB=1`` because a 5 GB upload is
    slow and costs real transfer.
    """

    @pytest.mark.spec("S3-016", "S3-018")
    def test_invalid_credentials_map_permission_denied(self) -> None:
        from remote_store._errors import PermissionDenied
        from remote_store.backends._s3_boto3 import S3Boto3Backend
        from tests.backends.fixtures._live_env import require_s3_live_credentials

        creds = require_s3_live_credentials()
        backend = S3Boto3Backend(
            bucket="rs-conformance-id202-invalid",
            key="AKIAIOSFODNN7EXAMPLE",
            secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region_name=creds["AWS_DEFAULT_REGION"],
        )
        try:
            with pytest.raises(PermissionDenied) as exc_info:
                backend.read_bytes("id202-probe.txt")
            assert exc_info.value.backend == "s3-boto3"
        finally:
            backend.close()

    @pytest.mark.skipif(
        os.environ.get("RS_TEST_S3_5GB") != "1",
        reason="5 GB multipart smoke is opt-in via RS_TEST_S3_5GB=1 (slow, real transfer)",
    )
    def test_multipart_above_5gb_has_no_cliff(self) -> None:
        """Stream 5 GiB + 1 byte through the boto3 multipart path and read the size back.

        s3fs-fuse #1936 restarts the upload past 5 GB; the boto3
        ``TransferConfig`` path does not. A zero-filled streaming source keeps
        peak memory flat; the object is deleted afterwards.
        """

        import boto3

        from remote_store.backends._s3_boto3 import S3Boto3Backend
        from tests.backends.fixtures._live_env import require_s3_live_credentials

        creds = require_s3_live_credentials()
        size = 5 * 1024 * 1024 * 1024 + 1  # 5 GiB + 1 byte
        bucket = f"rs-conformance-id202-{uuid.uuid4().hex[:8]}"

        client = boto3.client("s3", region_name=creds["AWS_DEFAULT_REGION"])
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": creds["AWS_DEFAULT_REGION"]},
        )
        backend = S3Boto3Backend(bucket=bucket, region_name=creds["AWS_DEFAULT_REGION"])
        key = "id202-5gb.bin"
        try:
            backend.write(key, _ZeroStream(size), overwrite=True)
            assert backend.get_file_info(key).size == size
        finally:
            backend.delete(key, missing_ok=True)
            backend.close()
            client.delete_bucket(Bucket=bucket)
            client.close()
