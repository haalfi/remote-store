"""``s3_boto3_moto`` fixture: S3Boto3Backend against an in-process moto server.

Stage 1, real-local (ID-202 PoC). moto runs in-process via
``ThreadedMotoServer``; no Docker required. Each factory call creates a
fresh bucket with a random suffix so concurrent fixtures do not collide.

Mirrors ``s3_moto.py`` but constructs the boto3-direct ``S3Boto3Backend``
instead of the s3fs-backed ``S3Backend``.
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


def _make_factory(reject_write_under_file_ancestor: bool):
    def _factory() -> Backend:
        if INFRA.moto_url is None:
            pytest.skip("moto/boto3 not installed")
        import boto3

        from remote_store.backends._s3_boto3 import S3Boto3Backend

        bucket = f"conformance-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=INFRA.moto_url,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        return S3Boto3Backend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=INFRA.moto_url,
            reject_write_under_file_ancestor=reject_write_under_file_ancestor,
        )

    return _factory


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._s3_boto3 import S3Boto3Backend
    except ImportError:
        return frozenset()
    return frozenset(S3Boto3Backend.CAPABILITIES)


for _name in ("s3_boto3_moto", "s3_boto3_moto_strict"):
    _meta = load_fixture(_name)
    register(
        BackendFixture(
            factory=_make_factory(_meta.rejects_write_under_file_ancestor),
            capabilities=_capabilities(),
            cleanup=_cleanup,
            **_meta.to_kwargs(),
        )
    )
