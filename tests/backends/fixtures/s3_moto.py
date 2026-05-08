"""``s3_moto`` fixture: S3Backend against an in-process moto server.

Stage 1, real-local. moto runs entirely in-process via
``ThreadedMotoServer``; no Docker required. Each factory call creates
a fresh bucket with a random suffix so concurrent fixtures do not
collide.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("s3_moto")


def _factory() -> Backend:
    if INFRA.moto_url is None:
        pytest.skip("moto/s3fs not installed")
    import boto3

    from remote_store.backends._s3 import S3Backend

    bucket = f"conformance-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=INFRA.moto_url,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    return S3Backend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name="us-east-1",
        endpoint_url=INFRA.moto_url,
    )


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._s3 import S3Backend
    except ImportError:
        return frozenset()
    return frozenset(S3Backend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
