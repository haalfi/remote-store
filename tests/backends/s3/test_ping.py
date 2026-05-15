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
- ``TestS3CheckHealthMoto`` runs the probe for real against an in-process
  moto server: a live bucket yields ``None``, a missing bucket raises
  ``NotFound``. The ``MagicMock``-based tests above patch the s3fs client
  and so never exercised the ``aiobotocore`` code path -- which is exactly
  where BUG-208 lived (an un-awaited ``head_bucket`` coroutine that made
  ``check_health()`` a silent no-op).

Mock spec for ``call_s3`` (Python 3.12+ ``__wrapped__`` drift): on
Python 3.12+ ``unittest.mock._mock_add_spec`` calls ``inspect.unwrap()``
on each attribute of the spec object before checking
``iscoroutinefunction``. s3fs's ``call_s3 = sync_wrapper(_call_s3)``
carries ``__wrapped__`` pointing at the async ``_call_s3``, so
``MagicMock(spec=S3FileSystem).call_s3`` is auto-promoted to
``AsyncMock`` even though the real ``call_s3`` is sync. The local
``_sync_call_s3_spec`` function is used as the child
``MagicMock(spec=...)`` so the mock stays sync on every Python version
(Python 3.11 was unaffected; 3.13 surfaced the drift).

Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("s3fs", reason="s3fs not installed")

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied  # noqa: E402


def _sync_call_s3_spec(method: str, *args: Any, **kwargs: Any) -> Any:
    """Sync signature spec for s3fs's ``call_s3`` -- see module docstring."""


def _s3_backend(bucket: str, side_effect: Any = None) -> Any:
    from s3fs import S3FileSystem

    from remote_store.backends._s3 import S3Backend

    s3_mock = MagicMock(spec=S3FileSystem)
    s3_mock.call_s3 = MagicMock(spec=_sync_call_s3_spec)
    if side_effect is None:
        s3_mock.call_s3.return_value = {}
    else:
        s3_mock.call_s3.side_effect = side_effect
    backend = S3Backend(bucket=bucket)
    backend._fs_instance = s3_mock
    return backend, s3_mock


class TestS3CheckHealth:
    @pytest.mark.spec("PING-004")
    def test_s3_probe_is_head_bucket(self) -> None:
        backend, s3_mock = _s3_backend("test-bucket")
        backend.check_health()
        assert s3_mock.call_s3.call_count == 1
        assert s3_mock.call_s3.call_args.args == ("head_bucket",)
        assert s3_mock.call_s3.call_args.kwargs == {"Bucket": "test-bucket"}

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


class TestS3CheckHealthMoto:
    """BUG-208: check_health() must issue the real head_bucket request.

    Drives S3Backend against an in-process moto server with no patching of
    the production code path. A pre-fix regression -- passing an un-awaited
    aiobotocore coroutine to nowhere -- makes the healthy-bucket case leak a
    RuntimeWarning (escalated to an error by filterwarnings) and the
    missing-bucket case silently return None instead of raising.
    """

    @staticmethod
    def _backend(endpoint: str, bucket: str) -> Any:
        from remote_store.backends._s3 import S3Backend

        return S3Backend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=endpoint,
        )

    @pytest.mark.spec("PING-004")
    def test_check_health_passes_for_existing_bucket(self, moto_server: str | None) -> None:
        if moto_server is None:
            pytest.skip("moto / s3fs not available")
        import boto3

        bucket = f"ping-ok-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        backend = self._backend(moto_server, bucket)
        try:
            assert backend.check_health() is None
        finally:
            backend.close()
            client.delete_bucket(Bucket=bucket)

    @pytest.mark.spec("PING-004")
    def test_check_health_raises_not_found_for_missing_bucket(self, moto_server: str | None) -> None:
        if moto_server is None:
            pytest.skip("moto / s3fs not available")
        backend = self._backend(moto_server, f"ping-missing-{uuid.uuid4().hex[:8]}")
        try:
            with pytest.raises(NotFound, match="Not found"):
                backend.check_health()
        finally:
            backend.close()
