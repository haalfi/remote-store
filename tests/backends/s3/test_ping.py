"""S3Backend check_health() probe-identity and error-mapping tests -- PING-004.

The healthy-path assertion (``check_health() is None``) is the universal
ABC contract covered by tests/backends/conformance/test_check_health.py.
This file pins what is S3-specific:

- The probe is ``head_bucket(Bucket=...)`` -- not ``list_objects``, not
  ``get_bucket_location``. Asserting the SDK method by name documents the
  intentional choice of the cheapest read-only operation.
- botocore failure modes map to the standard taxonomy: ``FileNotFoundError``
  -> ``NotFound``; 403 messages -> ``PermissionDenied``; endpoint-URL
  failures -> ``BackendUnavailable``.

Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("s3fs", reason="s3fs not installed")

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied  # noqa: E402


def _s3_backend(bucket: str, side_effect: Any = None) -> Any:
    from s3fs import S3FileSystem

    from remote_store.backends._s3 import S3Backend

    s3_mock = MagicMock(spec=S3FileSystem)
    if side_effect is None:
        s3_mock.s3.head_bucket.return_value = {}
    else:
        s3_mock.s3.head_bucket.side_effect = side_effect
    backend = S3Backend(bucket=bucket)
    backend._fs_instance = s3_mock
    return backend, s3_mock


class TestS3CheckHealth:
    @pytest.mark.spec("PING-004")
    def test_s3_probe_is_head_bucket(self) -> None:
        backend, s3_mock = _s3_backend("test-bucket")
        backend.check_health()
        assert s3_mock.s3.head_bucket.call_count == 1
        assert s3_mock.s3.head_bucket.call_args.kwargs == {"Bucket": "test-bucket"}

    @pytest.mark.spec("PING-004")
    @pytest.mark.parametrize(
        ("side_effect", "expected"),
        [
            pytest.param(FileNotFoundError("nosuchbucket"), NotFound, id="not-found"),
            pytest.param(Exception("403 AccessDenied"), PermissionDenied, id="permission-denied"),
            pytest.param(Exception("Could not connect to the endpoint URL"), BackendUnavailable, id="unavailable"),
        ],
    )
    def test_s3_errors(self, side_effect: Exception, expected: type[Exception]) -> None:
        backend, _ = _s3_backend("bad-bucket", side_effect=side_effect)
        with pytest.raises(expected):
            backend.check_health()
