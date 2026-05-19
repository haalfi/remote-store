"""``s3_pyarrow_minio`` fixture: S3PyArrowBackend against MinIO.

Stage 2, real-local. Active when ``pyarrow >= 24``, where the C++
``arrow::fs::S3FileSystem`` path requires a real S3-compatible endpoint
(moto's HTTP server is no longer sufficient). MinIO runs as the
chainguard MinIO Docker container; the host port comes from
``infra/.env`` (``MINIO_HOST_PORT``).

The companion Stage 1 fixture for older pyarrow versions is
``s3_pyarrow_moto``; the two are mutually exclusive at runtime.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from infra._settings import MINIO_HOST, MINIO_PORT
from tests._helpers import MINIO_KEY, MINIO_SECRET, pyarrow_ge_24
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("s3_pyarrow_minio")

_BUCKETS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    try:
        import pyarrow  # noqa: F401
        import s3fs  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow/s3fs not installed")
    if not pyarrow_ge_24():
        pytest.skip("pyarrow < 24 uses the s3_pyarrow_moto fixture, not MinIO")
    if INFRA.minio_url is None:
        pytest.skip(f"MinIO not reachable on {MINIO_HOST}:{MINIO_PORT}")
    import boto3

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    bucket = f"conformance-pa-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=INFRA.minio_url,
        aws_access_key_id=MINIO_KEY,
        aws_secret_access_key=MINIO_SECRET,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    backend = S3PyArrowBackend(
        bucket=bucket,
        key=MINIO_KEY,
        secret=MINIO_SECRET,
        region_name="us-east-1",
        endpoint_url=INFRA.minio_url,
    )
    _BUCKETS[id(backend)] = (bucket, client)
    return backend


def _cleanup(backend: Backend) -> None:
    backend.close()
    entry = _BUCKETS.pop(id(backend), None)
    if entry is None:
        return
    bucket, client = entry
    paginator = client.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])  # type: ignore[attr-defined]
    client.delete_bucket(Bucket=bucket)  # type: ignore[attr-defined]


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
        marks=(pytest.mark.requires_docker,),
        **_meta.to_kwargs(),
    )
)
