"""S3 backend tests -- covers S3-xxx spec items.

Requires: moto[server,s3], s3fs, boto3 (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("moto", reason="moto not installed")
pytest.importorskip("s3fs", reason="s3fs not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import BackendUnavailable, PermissionDenied  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from remote_store._backend import Backend

REGION = "us-east-1"


@pytest.fixture
def s3_backend(moto_server: str) -> Iterator[Backend]:
    """Create an S3Backend against moto's mock S3 service."""
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name=REGION,
    )
    client.create_bucket(Bucket=bucket)

    from remote_store.backends._s3 import S3Backend

    backend = S3Backend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name=REGION,
        endpoint_url=moto_server,
    )
    yield backend
    backend.close()


# region: Construction (S3-002, S3-003)
class TestS3Construction:
    """S3-002, S3-003: backend-identity strings that do not parametrize.
    Construction validation, lazy connection, endpoint-URL normalization,
    credentials-optional, and client_options are covered in
    tests/backends/test_s3_shared.py alongside the S3-PyArrow equivalents."""

    @pytest.mark.spec("S3-002")
    def test_name_is_s3(self, s3_backend: Backend) -> None:
        assert s3_backend.name == "s3"

    @pytest.mark.spec("S3-003")
    def test_declares_all_capabilities(self, s3_backend: Backend) -> None:
        caps = s3_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.ATOMIC_MOVE:
                assert not caps.supports(cap), "S3 must not declare ATOMIC_MOVE (copy-then-delete)"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"


class TestS3TlsCaBundle:
    """TLS-004: AWS_CA_BUNDLE environment-variable fallback (S3-specific).
    The rest of the tls_ca_bundle contract (accepted/missing/directory/default,
    s3fs verify wiring) is covered in test_s3_shared.py."""

    @pytest.mark.spec("TLS-004")
    def test_tls_ca_bundle_env_var_missing_file_raises(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        with (
            patch.dict("os.environ", {"AWS_CA_BUNDLE": "/no/such/env.pem"}, clear=False),
            pytest.raises(ValueError, match="does not exist or is not a file"),
        ):
            S3Backend(bucket="b", key="k", secret="s")


# endregion


# region: Error Mapping (S3-016, S3-017)
class TestS3ErrorMapping:
    """S3-016, S3-017: PermissionDenied and BackendUnavailable mapping.
    S3-015 (NotFound.backend) and S3-018 (RemoteStoreError.backend) are
    covered by TestS3SharedErrorMapping in test_s3_shared.py."""

    @pytest.mark.spec("S3-016")
    @pytest.mark.parametrize(
        "message",
        [
            pytest.param("An error occurred (403) AccessDenied", id="http_403"),
            pytest.param("access denied for this resource", id="access_denied_msg"),
        ],
    )
    def test_permission_denied_mapping(self, s3_backend: Backend, message: str) -> None:
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        with (
            patch.object(s3_backend._s3fs, "cat_file", side_effect=Exception(message)),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            s3_backend.read_bytes("secret.txt")
        assert exc_info.value.backend == "s3"
        assert exc_info.value.path == "secret.txt"

    @pytest.mark.spec("S3-017")
    @pytest.mark.parametrize(
        "message",
        [
            pytest.param("Could not connect to the endpoint URL", id="endpoint"),
            pytest.param("connect timeout reached", id="timeout"),
            pytest.param("dns resolution failed", id="dns"),
            pytest.param("name or service not known", id="name_or_service"),
        ],
    )
    def test_backend_unavailable_mapping(self, s3_backend: Backend, message: str) -> None:
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        with (
            patch.object(s3_backend._s3fs, "cat_file", side_effect=Exception(message)),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            s3_backend.read_bytes("file.txt")
        assert exc_info.value.backend == "s3"


# endregion


# region: ETag and Digest (S3-023, S3-024)
class TestS3ETagAndDigest:
    """S3-023, S3-024: ETag and ContentDigest in FileInfo.
    test_get_file_info_has_etag (S3-023) and test_get_file_info_has_digest_sha256
    (S3-024) are covered by TestS3SharedETagAndDigest in test_s3_shared.py."""

    @pytest.mark.spec("S3-023")
    def test_list_files_has_etag(self, s3_backend: Backend) -> None:
        s3_backend.write("etag_list.txt", b"hello")
        files = list(s3_backend.list_files(""))
        matches = [f for f in files if f.name == "etag_list.txt"]
        assert len(matches) == 1
        assert matches[0].etag is not None
        assert '"' not in matches[0].etag
        assert matches[0].etag == matches[0].etag.lower()

    @pytest.mark.spec("S3-023")
    def test_digest_type_for_standard_upload(self, s3_backend: Backend) -> None:
        """S3 automatically computes CRC32 for standard uploads."""
        from remote_store._models import ContentDigest

        s3_backend.write("no_explicit_checksum.txt", b"hello")
        fi = s3_backend.get_file_info("no_explicit_checksum.txt")
        assert fi.digest is not None
        assert isinstance(fi.digest, ContentDigest)
        assert fi.digest.algorithm == "crc32"

    @pytest.mark.spec("S3-024")
    def test_write_result_digest_for_standard_upload(self, s3_backend: Backend) -> None:
        """S3 auto-CRC32 is surfaced in WriteResult.digest (BUG-177 regression guard).

        write() issues head_object(ChecksumMode="ENABLED") after the upload,
        so WriteResult.digest is populated from the same source as
        get_file_info().  This liveness assertion ensures a bilateral
        regression (stripping ChecksumMode from both paths) would be caught.
        """
        from remote_store._models import ContentDigest

        result = s3_backend.write("write_result_digest.txt", b"hello")
        assert result.digest is not None
        assert isinstance(result.digest, ContentDigest)
        assert result.digest.algorithm == "crc32"

    @pytest.mark.spec("S3-023")
    @pytest.mark.parametrize(
        ("info_dict", "expected_etag"),
        [
            pytest.param(
                {"etag": '"abc123"', "size": 10},
                "abc123",
                id="lowercase_key_fallback",
            ),
            pytest.param(
                {"ETag": '"d41d8cd98f00b204e9800998ecf8427e-2"', "size": 100},
                "d41d8cd98f00b204e9800998ecf8427e-2",
                id="multipart_suffix_preserved",
            ),
            pytest.param(
                {"size": 5},
                None,
                id="etag_none_when_absent",
            ),
        ],
    )
    def test_info_to_fileinfo_etag(self, info_dict: dict, expected_etag: str | None) -> None:
        """_info_to_fileinfo handles various ETag key forms correctly."""
        from datetime import datetime, timezone

        from remote_store.backends._s3 import S3Backend

        backend = object.__new__(S3Backend)
        info_dict.setdefault("LastModified", datetime(2024, 1, 1, tzinfo=timezone.utc))
        info_dict.setdefault("name", "bucket/file.txt")
        fi = backend._info_to_fileinfo(info_dict, "file.txt")
        assert fi.etag == expected_etag

    @pytest.mark.spec("S3-024")
    def test_digest_from_head_response_no_algorithm(self) -> None:
        """Returns None when no known checksum keys are present."""
        from remote_store.backends._s3 import S3Backend

        backend = object.__new__(S3Backend)
        raw = {"ContentLength": 5, "ETag": '"abc"'}
        assert backend._digest_from_head_response(raw) is None

    @pytest.mark.spec("S3-024")
    def test_list_files_digest_always_none(self, s3_backend: Backend, moto_server: str) -> None:
        """Listing paths never populate digest."""
        import base64
        import hashlib

        import boto3

        from remote_store.backends._s3 import S3Backend

        content = b"listed"
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()
        backend = s3_backend
        assert isinstance(backend, S3Backend)
        raw_client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name=REGION,
        )
        raw_client.put_object(
            Bucket=backend._bucket,
            Key="listed_sha256.txt",
            Body=content,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=b64,
        )

        files = list(backend.list_files(""))
        matches = [f for f in files if f.name == "listed_sha256.txt"]
        assert len(matches) == 1
        assert matches[0].digest is None

    @pytest.mark.spec("S3-024")
    def test_digest_from_head_response_sha256(self) -> None:
        """_digest_from_head_response returns ContentDigest for SHA256."""
        import base64
        import hashlib

        from remote_store._models import ContentDigest
        from remote_store.backends._s3 import S3Backend

        content = b"test"
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()
        backend = object.__new__(S3Backend)
        raw = {"ContentLength": 4, "ChecksumSHA256": b64}
        result = backend._digest_from_head_response(raw)
        assert isinstance(result, ContentDigest)
        assert result.algorithm == "sha256"
        assert result.value == hashlib.sha256(content).hexdigest()


# endregion


# ---------------------------------------------------------------------------
# WriteResult (WR-012)
# ---------------------------------------------------------------------------


class TestS3WriteResult:
    """S3Backend.write/write_atomic WriteResult behaviour not covered by conformance."""

    @pytest.mark.spec("WR-012")
    def test_write_metadata_passed_to_sdk(self, s3_backend: Backend) -> None:
        """Metadata kwarg reaches the S3 object (verified via HeadObject)."""
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        s3_backend.write("meta.txt", b"x", metadata={"env": "test"})
        info = s3_backend.get_file_info("meta.txt")
        assert info.metadata == {"env": "test"}


# ---------------------------------------------------------------------------
# RetryPolicy acceptance + botocore config wiring (RET-011)
# Migrated from tests/test_config.py (BK-216 / BK-191).
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-011")
def test_s3_accepts_retry() -> None:
    from remote_store._config import RetryPolicy
    from remote_store.backends._s3 import S3Backend

    rp = RetryPolicy(max_attempts=10)
    assert S3Backend(bucket="b", retry=rp)._retry is rp


@pytest.mark.spec("RET-011")
def test_s3_retry_botocore_config() -> None:
    from remote_store._config import RetryPolicy
    from remote_store.backends._s3 import S3Backend

    backend = S3Backend(bucket="b", retry=RetryPolicy(max_attempts=7))
    # S3-026 / BUG-185: the merged Config flows to s3fs as config_kwargs (a dict),
    # never as client_kwargs["config"] (which would collide with the
    # config=AioConfig(...) s3fs passes to aiobotocore.create_client()).
    config_kwargs = backend._fs.config_kwargs
    assert "config" not in backend._fs.client_kwargs
    assert config_kwargs["retries"]["max_attempts"] == 7
    assert config_kwargs["retries"]["mode"] == "standard"
    backend.close()


# region: Credential masking (AF-008, SEC-004) — migrated from tests/test_coverage_gaps.py (BK-222 / BK-191 slice 6/6)


class TestS3CredentialMasking:
    """AF-008: S3Backend repr masks sensitive fields and accepts Secret wrappers."""

    def test_masks_set_secrets(self) -> None:
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="b", key="AKID", secret="SK", endpoint_url="http://x")
        r = repr(backend)
        for raw in ("AKID", "SK"):
            assert raw not in r
        for masked in ("key='***'", "secret='***'"):
            assert masked in r
        for visible in ("bucket='b'", "endpoint_url='http://x'"):
            assert visible in r

    def test_shows_none_for_unset_secrets(self) -> None:
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="b")
        r = repr(backend)
        for expected in ("key=None", "secret=None"):
            assert expected in r

    @pytest.mark.spec("SEC-004")
    def test_accepts_secret_wrapper(self) -> None:
        from remote_store._config import Secret
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="b", key=Secret("AKID"), secret=Secret("SK"))
        assert backend._key == "AKID"
        assert backend._secret == "SK"


# endregion
