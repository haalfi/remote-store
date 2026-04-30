"""S3 control-path lifecycle against ThreadedMotoServer -- covers BK-166, S3-026, S3PA-026.

Wire-level coverage for BUG-178/BUG-185: drives the full backend lifecycle
through the real ``s3fs`` + ``aiobotocore`` stack with ``moto`` standing in
for the S3 endpoint. Nothing in this module patches the production code
path, so a regression in the ``config_kwargs`` routing surfaces as a real
``TypeError: got multiple values for keyword argument 'config'`` on first
I/O.

The unit-level ``TestAiobotocoreCreateClientBoundary`` in
``tests/backends/test_s3_options.py`` patches
``aiobotocore.session.AioSession.create_client`` and asserts on the
captured kwargs; that pins the kwarg shape. This file pins the wire-level
behavior. The companion rejection assertion lives in
``TestConfigKwargsRetryCollision::test_client_kwargs_config_is_rejected``
(unit-level) and is intentionally not duplicated here -- it short-circuits
inside ``_build_s3fs_kwargs`` before any HTTP and gains nothing from a
moto fixture.

S3-PyArrow scope (S3PA-026): ``_FULL_CLIENT_OPTIONS['config_kwargs']`` is
consumed by the s3fs builder only; ``S3PyArrowBackend`` reads
``endpoint_url`` / ``key`` / ``secret`` / ``region_name`` directly when
constructing its PyArrow ``S3FileSystem`` and does not pass
``client_options`` to the data path. So in the ``s3-pyarrow`` parametrize
case, only the s3fs control-path operations (``list_files``, ``exists``,
``delete``) exercise the tuned ``config_kwargs``; ``write`` / ``read``
flow through PyArrow with default settings. That matches S3PA-026's
delta against S3-026 (s3fs control path only).

Why ``moto[server]`` (not ``moto.mock_aws``): ``mock_aws`` patches the
synchronous ``botocore`` stack only. ``aiobotocore`` issues real HTTP
requests, so we need a real moto HTTP server -- pinned in
``pyproject.toml`` as ``moto[server,s3]``.

Why under ``tests/backends/`` (not ``tests/e2e/``): ``tests/e2e/`` is
excluded from ``hatch run test`` / ``hatch run all`` via
``addopts="--ignore=tests/e2e"`` because those tests need Docker. Moto
runs in-process and is fast (~1.5s for the whole module), so this file
must run in the default suite to actually catch regressions; that was
exactly the gap BUG-178 and BUG-185 fell through.
"""

from __future__ import annotations

import socket
import time
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


def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> None:
    # ThreadedMotoServer.start() returns before the HTTP listener is ready;
    # the first boto3 call against the yielded URL can race the bind on slow
    # CI runners. Cheap insurance: poll until accept() succeeds or timeout.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"moto server at {host}:{port} did not become ready in {timeout}s")


@pytest.fixture(scope="module")
def moto_server() -> Iterator[str]:
    """Start a ThreadedMotoServer on a free port; yield its endpoint URL."""
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    _wait_for_port(host, port)
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture(scope="module")
def moto_bucket(moto_server: str) -> Iterator[tuple[str, str]]:
    """Create one bucket on the moto server for the whole module.

    Module-scoped because tests use UUID-suffixed object keys, write with
    ``overwrite=True``, and clean up their own writes -- a fresh bucket per
    parametrize case adds setup with no isolation benefit.
    """
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
class TestS3ControlPathMoto:
    """BK-166: drive a full backend lifecycle through real s3fs + aiobotocore."""

    def test_full_lifecycle_with_tuned_client_options(self, backend_cls: str, moto_bucket: tuple[str, str]) -> None:
        """write -> list_files -> read -> delete with non-trivial client_options.

        Mirrors the user's MinIO scenario from BUG-185. A pre-fix regression
        raises ``TypeError: got multiple values for keyword argument 'config'``
        from ``aiobotocore.create_client`` on the first I/O call.
        """
        endpoint, bucket = moto_bucket
        cls = _load(backend_cls)
        # Unique key per parametrize id so cases sharing the module-scoped bucket
        # cannot clobber each other if one fails before its own delete.
        key = f"docs/hello-{cls.__name__}.txt"
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
        )
        try:
            payload = b"BK-166 wire-level payload"
            result = backend.write(key, payload, overwrite=True)
            assert result.size == len(payload)

            listed = [str(info.path) for info in backend.list_files("docs", recursive=True)]
            assert key in listed

            with backend.read(key) as stream:
                assert stream.read() == payload

            backend.delete(key)
            assert not backend.exists(key)
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
        key = f"retry/sample-{cls.__name__}.bin"
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
            backend.write(key, payload, overwrite=True)
            with backend.read(key) as stream:
                assert stream.read() == payload
            backend.delete(key)
        finally:
            backend.close()
