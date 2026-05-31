"""``s3_pyarrow_live`` fixture: S3PyArrowBackend against a real AWS S3 account.

Stage 3, real-live. The S3-PyArrow sibling of ``s3_live``: same gating and
per-call ``rs-conformance-<uuid>`` bucket provisioning, but the backend under
test routes its data path through PyArrow's C++ S3 client (which always uses
multipart upload) instead of s3fs. Added with BUG-214 so the PyArrow
``write_atomic`` buffer-before-upload path is confirmed against real AWS, not
just moto/MinIO -- the emulators cannot exercise the real CompleteMultipartUpload
behaviour the abort path guards against.

Gating
------

Two layers, both required (identical to ``s3_live``):

1. ``--stage=3`` (or ``RS_TEST_STAGE=3``).
2. ``RS_TEST_LIVE_S3=1`` env var (shared with ``s3_live``; kept out of ``.env``
   so a default ``hatch run test`` never touches a real account). When unset,
   the factory skips per TEST-006.

Once both are set, ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` /
``AWS_DEFAULT_REGION`` become fail-loud preconditions via
``_live_env.require_s3_live_credentials``.

Credentials and region
-----------------------

The bucket is provisioned with an explicit boto3 client (same as ``s3_live``).
``S3PyArrowBackend`` is then constructed with ``region_name`` passed through
(PyArrow's S3FileSystem benefits from an explicit region rather than relying on
auto-detection) but without ``key`` / ``secret``, so both the PyArrow data path
and the s3fs control path defer to the default AWS credential chain.

Required IAM permissions
------------------------

Identical to ``s3_live`` -- see that module's "Required IAM permissions" section
(``s3:CreateBucket`` / ``DeleteBucket`` / ``ListBucket`` /
``ListBucketMultipartUploads`` / ``AbortMultipartUpload`` / object CRUD on
``rs-conformance-*``). PyArrow's always-multipart writes make
``AbortMultipartUpload`` and ``ListBucketMultipartUploads`` load-bearing here.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._live_env import require_s3_live_credentials
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("s3_pyarrow_live")

_LOG = logging.getLogger(__name__)

# id(backend) -> (bucket name, boto3 client) so cleanup can tear down
# what factory created without threading state through the Backend instance.
_BUCKETS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    if os.environ.get("RS_TEST_LIVE_S3") != "1":
        pytest.skip("s3_pyarrow_live opt-in via RS_TEST_LIVE_S3=1")
    try:
        import boto3
    except ImportError:
        pytest.skip("boto3 not installed")

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    creds = require_s3_live_credentials()
    region = creds["AWS_DEFAULT_REGION"]
    bucket = f"rs-conformance-{uuid.uuid4().hex[:12]}"
    client = boto3.client(
        "s3",
        aws_access_key_id=creds["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["AWS_SECRET_ACCESS_KEY"],
        region_name=region,
    )
    try:
        create_kwargs: dict = {"Bucket": bucket}
        if region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**create_kwargs)
    except Exception:
        client.close()
        raise
    try:
        # region_name passed through (PyArrow prefers an explicit region);
        # credentials defer to the default chain for both the PyArrow data
        # path and the s3fs control path.
        backend = S3PyArrowBackend(bucket=bucket, region_name=region)
        _BUCKETS[id(backend)] = (bucket, client)
    except Exception:
        try:
            client.delete_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001 -- best-effort on init failure
            _LOG.warning("failed to delete bucket %s after S3PyArrowBackend init failure", bucket, exc_info=True)
        client.close()
        raise
    return backend


def _cleanup(backend: Backend) -> None:
    # Guard backend.close() so a transient close failure cannot strand a
    # real S3 bucket. The deletion path below is the load-bearing step.
    try:
        backend.close()
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("backend.close() failed during cleanup", exc_info=True)
    entry = _BUCKETS.pop(id(backend), None)
    if entry is None:
        return
    bucket, client = entry
    try:
        # Abort any multipart uploads first: a write_atomic abort test may have
        # left none, but a mid-flight failure on the always-multipart PyArrow
        # path could strand one, and delete_bucket fails while an MPU is open.
        for up in client.list_multipart_uploads(Bucket=bucket).get("Uploads", []):  # type: ignore[attr-defined]
            client.abort_multipart_upload(Bucket=bucket, Key=up["Key"], UploadId=up["UploadId"])  # type: ignore[attr-defined]
        paginator = client.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            while objects:
                chunk, objects = objects[:1000], objects[1000:]
                client.delete_objects(  # type: ignore[attr-defined]
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in chunk]},
                )
        client.delete_bucket(Bucket=bucket)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("failed to delete live S3 bucket %s", bucket, exc_info=True)
    finally:
        client.close()  # type: ignore[attr-defined]


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend
    except ImportError:
        return frozenset()
    return frozenset(S3PyArrowBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        marks=(pytest.mark.live,),
        **_meta.to_kwargs(),
    )
)
