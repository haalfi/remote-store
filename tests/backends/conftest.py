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


def _s3_pyarrow_available() -> bool:
    try:
        import moto  # noqa: F401
        import pyarrow  # noqa: F401
        import s3fs  # noqa: F401

        return True
    except ImportError:
        return False


def _sftp_available() -> bool:
    try:
        import paramiko  # noqa: F401

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


@pytest.fixture(scope="session")
def sftp_server() -> Iterator[tuple[int, str] | None]:
    """Start an in-process SFTP server for the test session."""
    if not _sftp_available():
        yield None
        return

    from tests.backends.sftp_server import start_sftp_server, stop_sftp_server

    tmpdir = tempfile.mkdtemp(prefix="sftp_test_")

    thread, port, host_key, stop_event, server_socket = start_sftp_server(root=tmpdir, host="127.0.0.1")

    # Build a known_hosts entry for the test server
    key_type = host_key.get_name()
    key_b64 = host_key.get_base64()
    host_key_entry = f"[127.0.0.1]:{port} {key_type} {key_b64}"

    yield port, host_key_entry

    stop_sftp_server(thread, stop_event, server_socket)

    # Clean up temp directory
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


_s3_param = pytest.param(
    "s3",
    marks=pytest.mark.skipif(not _s3_available(), reason="moto/s3fs not installed"),
)

_s3_pyarrow_param = pytest.param(
    "s3-pyarrow",
    marks=pytest.mark.skipif(not _s3_pyarrow_available(), reason="pyarrow/s3fs not installed"),
)

_sftp_param = pytest.param(
    "sftp",
    marks=pytest.mark.skipif(not _sftp_available(), reason="paramiko not installed"),
)


@pytest.fixture(params=["local", _s3_param, _s3_pyarrow_param, _sftp_param])
def backend(
    request: pytest.FixtureRequest,
    moto_server: str | None,
    sftp_server: tuple[int, str] | None,
) -> Iterator[Backend]:
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
    elif request.param == "s3-pyarrow":
        import boto3

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        assert moto_server is not None
        bucket = f"conformance-pa-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        b = S3PyArrowBackend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=moto_server,
        )
        yield b
        b.close()
    elif request.param == "sftp":
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        assert sftp_server is not None
        port, host_key_entry = sftp_server
        base_path = f"/test_{uuid.uuid4().hex[:8]}"
        b = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            base_path=base_path,
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
        yield b
        b.close()
    else:
        pytest.skip(f"Unknown backend: {request.param}")
