"""Backend test fixtures -- parameterized for conformance testing."""

from __future__ import annotations

import socket
import tempfile
import uuid
from typing import TYPE_CHECKING

import pytest

from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


def _s3_available() -> bool:
    try:
        import moto  # noqa: F401
        import s3fs  # noqa: F401

        return True
    except ImportError:
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def moto_server() -> Iterator[str | None]:
    """Start a moto HTTP server for the test session.

    Uses server mode instead of mock_aws() to avoid Python 3.13
    PEP 667 f_locals incompatibility with s3fs/aiobotocore.
    """
    if not _s3_available():
        yield None
        return
    from moto.moto_server.threaded_moto_server import ThreadedMotoServer

    port = _free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    yield f"http://127.0.0.1:{port}"
    server.stop()


_s3_param = pytest.param(
    "s3",
    marks=pytest.mark.skipif(not _s3_available(), reason="moto/s3fs not installed"),
)


@pytest.fixture(params=["local", _s3_param])
def backend(request: pytest.FixtureRequest, moto_server: str | None) -> Iterator[Backend]:
    """Parameterized backend fixture. Add new backends here."""
    if request.param == "local":
        with tempfile.TemporaryDirectory() as tmp:
            yield LocalBackend(root=tmp)
    elif request.param == "s3":
        import boto3

        from remote_store.backends._s3 import S3Backend

        assert moto_server is not None
        bucket = f"conformance-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        b = S3Backend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=moto_server,
        )
        yield b
        b.close()
    else:
        pytest.skip(f"Unknown backend: {request.param}")
