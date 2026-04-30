"""S3 control-path e2e against ThreadedMotoServer -- covers BK-166, S3-026, S3PA-026.

End-to-end coverage for BUG-178/BUG-185: drives the full backend lifecycle
through the real ``s3fs`` + ``aiobotocore`` stack with ``moto`` standing in
for the S3 endpoint. Nothing in this module patches the production code
path, so a regression in the ``config_kwargs`` routing surfaces as a real
``TypeError: got multiple values for keyword argument 'config'`` on first
I/O.

The unit-level ``TestAiobotocoreCreateClientBoundary`` in
``tests/backends/test_s3_options.py`` patches
``aiobotocore.session.AioSession.create_client`` and asserts on the
captured kwargs; that pins the kwarg shape. This file pins the wire-level
behavior end-to-end.

Why ``moto[server]`` (not ``moto.mock_aws``): ``mock_aws`` patches the
synchronous ``botocore`` stack only. ``aiobotocore`` issues real HTTP
requests, so we need a real moto HTTP server -- pinned in
``pyproject.toml`` as ``moto[server,s3]``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("s3fs")
pytest.importorskip("aiobotocore")
pytest.importorskip("moto")
pytest.importorskip("botocore")

if TYPE_CHECKING:
    from collections.abc import Iterator


# Mirror the user's MinIO scenario: path-style addressing, proxies cleared
# (so localhost moto isn't sent through any HTTP_PROXY env), tight timeouts.
_FULL_CLIENT_OPTIONS: dict[str, Any] = {
    "config_kwargs": {
        "s3": {"addressing_style": "path"},
        "proxies": {"http": None, "https": None},
        "connect_timeout": 5.0,
        "read_timeout": 5.0,
    },
}


@pytest.fixture(scope="module")
def moto_server() -> Iterator[str]:
    """Start a ThreadedMotoServer on a free port; yield its endpoint URL."""
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def moto_bucket(moto_server: str) -> Iterator[tuple[str, str]]:
    """Create a fresh bucket on the moto server; yield ``(endpoint, bucket)``."""
    import boto3

    bucket = f"bk166-{uuid.uuid4().hex[:8]}"
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
            for obj in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)


def _load(dotted: str) -> type:
    import importlib

    module_path, cls_name = dotted.split(":")
    return getattr(importlib.import_module(module_path), cls_name)


@pytest.mark.parametrize(
    "backend_cls",
    [
        pytest.param(
            "remote_store.backends._s3:S3Backend",
            id="s3",
            marks=pytest.mark.spec("S3-026"),
        ),
        pytest.param(
            "remote_store.backends._s3_pyarrow:S3PyArrowBackend",
            id="s3-pyarrow",
            marks=pytest.mark.spec("S3PA-026"),
        ),
    ],
)
class TestS3ControlPathE2E:
    """BK-166: drive a full backend lifecycle through real s3fs + aiobotocore."""

    def test_full_lifecycle_with_tuned_client_options(self, backend_cls: str, moto_bucket: tuple[str, str]) -> None:
        """write -> list_files -> read -> delete with non-trivial client_options.

        Mirrors the user's MinIO scenario from BUG-185. A pre-fix regression
        raises ``TypeError: got multiple values for keyword argument 'config'``
        from ``aiobotocore.create_client`` on the first I/O call.
        """
        endpoint, bucket = moto_bucket
        cls = _load(backend_cls)
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
        )
        try:
            payload = b"BK-166 e2e payload"
            result = backend.write("docs/hello.txt", payload, overwrite=True)
            assert result.size == len(payload)

            listed = [str(info.path) for info in backend.list_files("docs", recursive=True)]
            assert "docs/hello.txt" in listed

            with backend.read("docs/hello.txt") as stream:
                assert stream.read() == payload

            backend.delete("docs/hello.txt")
            assert not backend.exists("docs/hello.txt")
        finally:
            backend.close()

    def test_lifecycle_with_retry_policy(self, backend_cls: str, moto_bucket: tuple[str, str]) -> None:
        """Same lifecycle with ``RetryPolicy`` alongside the tuned client_options.

        ``RetryPolicy`` replaces the ``config_kwargs['retries']`` entry
        wholesale (S3-026); the round-trip must still complete cleanly.
        """
        from remote_store._config import RetryPolicy

        endpoint, bucket = moto_bucket
        cls = _load(backend_cls)
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
            retry=RetryPolicy(max_attempts=2),
        )
        try:
            payload = b"BK-166 retry payload"
            backend.write("retry/sample.bin", payload, overwrite=True)
            with backend.read("retry/sample.bin") as stream:
                assert stream.read() == payload
            backend.delete("retry/sample.bin")
        finally:
            backend.close()

    def test_prebuilt_config_in_client_kwargs_rejected(self, backend_cls: str, moto_bucket: tuple[str, str]) -> None:
        """S3-026: pre-built ``Config`` in ``client_kwargs`` is rejected end-to-end.

        Pins the s3fs ≥ 2024.x compatibility scope from BK-166: a future
        regression that re-introduces a ``client_kwargs['config']`` pop in
        our builder must fail at filesystem construction, before any I/O
        reaches the wire. Triggered via ``backend._s3fs`` (not a public I/O
        method) because the public methods wrap the builder's ``ValueError``
        in ``RemoteStoreError`` via ``_s3fs_errors``; the rejection itself
        is what we're verifying, not the error-mapping wrapper.
        """
        import botocore.config

        endpoint, bucket = moto_bucket
        cls = _load(backend_cls)
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            client_options={
                "client_kwargs": {"config": botocore.config.Config(connect_timeout=20)},
            },
        )
        try:
            with pytest.raises(ValueError, match="config_kwargs"):
                _ = backend._s3fs
        finally:
            backend.close()
