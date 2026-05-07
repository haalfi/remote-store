"""``s3_pyarrow_moto`` fixture: S3PyArrowBackend backed by in-process moto.

Stage 1, real-local. Path active when ``pyarrow < 24``: those releases
talk to moto's HTTP server through the legacy s3fs path. Newer pyarrow
runs the C++ `arrow::fs::S3FileSystem` and demands a real S3 endpoint
(MinIO Stage 2); see ``s3_pyarrow_minio.py`` for that side.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests._helpers import pyarrow_ge_24
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_BUCKETS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    try:
        import pyarrow  # noqa: F401
        import s3fs  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow/s3fs not installed")
    if pyarrow_ge_24():
        pytest.skip("pyarrow >= 24 requires the s3_pyarrow_minio fixture, not moto")
    if INFRA.moto_url is None:
        pytest.skip("moto_server not available; required for S3-PyArrow on pyarrow < 24")
    import boto3

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    bucket = f"conformance-pa-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=INFRA.moto_url,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    backend = S3PyArrowBackend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name="us-east-1",
        endpoint_url=INFRA.moto_url,
    )
    _BUCKETS[id(backend)] = (bucket, client)
    return backend


def _cleanup(backend: Backend) -> None:
    backend.close()
    _BUCKETS.pop(id(backend), None)


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend
    except ImportError:
        return frozenset()
    return frozenset(S3PyArrowBackend.CAPABILITIES)


register(
    BackendFixture(
        name="s3_pyarrow_moto",
        backend="s3_pyarrow",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
    )
)
