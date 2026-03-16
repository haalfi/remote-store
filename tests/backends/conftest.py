"""Backend test fixtures -- parameterized for conformance testing."""

from __future__ import annotations

import socket
import tempfile
import uuid
from typing import TYPE_CHECKING

import pytest

from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


def _http_server_available() -> bool:
    try:
        import pytest_httpserver  # noqa: F401
        import werkzeug  # noqa: F401

        return True
    except ImportError:
        return False


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


def _azure_available() -> bool:
    try:
        import azure.storage.filedatalake  # noqa: F401

        return True
    except ImportError:
        return False


def _azurite_reachable() -> bool:
    """Check if Azurite is reachable (started externally via Docker)."""
    try:
        s = socket.create_connection(("127.0.0.1", 10000), timeout=1)
        s.close()
        return True
    except OSError:
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

_azure_param = pytest.param(
    "azure",
    marks=[
        pytest.mark.requires_docker,
        pytest.mark.skipif(
            not _azure_available() or not _azurite_reachable(),
            reason="azure SDK not installed or Azurite not reachable",
        ),
    ],
)


_http_param = pytest.param(
    "http",
    marks=pytest.mark.skipif(not _http_server_available(), reason="pytest-httpserver not installed"),
)

_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)


@pytest.fixture(scope="session")
def azurite_server() -> Iterator[str | None]:
    """Provide Azurite connection string if available."""
    if not _azure_available() or not _azurite_reachable():
        yield None
        return
    yield _AZURITE_CONN_STR


_local_param = pytest.param("local", marks=pytest.mark.os_sensitive)
_memory_param = pytest.param("memory", marks=pytest.mark.os_sensitive)


@pytest.fixture(
    params=[
        _local_param,
        _memory_param,
        _http_param,
        _s3_param,
        _s3_pyarrow_param,
        _sftp_param,
        _azure_param,
    ]
)
def backend(
    request: pytest.FixtureRequest,
    moto_server: str | None,
    sftp_server: tuple[int, str] | None,
    azurite_server: str | None,
) -> Iterator[Backend]:
    """Parameterized backend fixture. Add new backends here."""
    if request.param == "local":
        with tempfile.TemporaryDirectory() as tmp:
            yield LocalBackend(root=tmp)
    elif request.param == "memory":
        yield MemoryBackend()
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
    elif request.param == "http":
        from pytest_httpserver import HTTPServer
        from werkzeug.wrappers import Response as WerkzeugResponse

        from remote_store.backends._http import ReadOnlyHttpBackend

        server = HTTPServer(host="127.0.0.1")
        # Return 404 for unregistered paths (default is 500)
        server.respond_nohandler = lambda request, extra_message="": WerkzeugResponse(  # type: ignore[assignment]
            b"Not Found", status=404
        )
        server.start()
        b = ReadOnlyHttpBackend(base_url=server.url_for("/conformance/"), http_client="urllib")
        yield b
        b.close()
        server.clear()
        if server.is_running():
            server.stop()
    elif request.param == "azure":
        from remote_store.backends._azure import AzureBackend

        assert azurite_server is not None
        container = f"conformance-{uuid.uuid4().hex[:8]}"
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(azurite_server)
        try:
            service.create_container(container)
        except Exception:
            service.close()
            raise
        b = AzureBackend(container=container, connection_string=azurite_server)
        yield b
        b.close()
        service.delete_container(container)
        service.close()
    else:
        pytest.skip(f"Unknown backend: {request.param}")
