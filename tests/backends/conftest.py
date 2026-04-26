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


# ---------------------------------------------------------------------------
# Force pytest-httpserver to bind on 127.0.0.1 instead of "localhost".
# On Windows, "localhost" resolves to both IPv4 and IPv6; urllib tries
# IPv6 first and waits ~2 s for the connection to time out before falling
# back to IPv4.  Using 127.0.0.1 directly avoids the dual-stack penalty.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple[str, int]:
    return ("127.0.0.1", 0)


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


def _sqlblob_available() -> bool:
    try:
        import sqlalchemy  # noqa: F401

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


@pytest.fixture(scope="session")
def http_server() -> Iterator[object | None]:
    """Start a long-lived HTTP server for conformance tests.

    Session-scoped to avoid the ~0.5 s start/stop overhead per test.
    Individual tests clear handlers via the function-scoped backend fixture.
    """
    if not _http_server_available():
        yield None
        return

    from pytest_httpserver import HTTPServer

    server = HTTPServer(host="127.0.0.1")
    server.start()
    yield server
    server.clear()
    if server.is_running():
        server.stop()


_local_param = pytest.param("local", marks=pytest.mark.os_sensitive)
_memory_param = pytest.param("memory")
_dafny_oracle_param = pytest.param("dafny-oracle")

_sqlblob_param = pytest.param(
    "sql-blob",
    marks=pytest.mark.skipif(not _sqlblob_available(), reason="sqlalchemy not installed"),
)


@pytest.fixture(
    params=[
        _local_param,
        _memory_param,
        _http_param,
        _s3_param,
        _s3_pyarrow_param,
        _sftp_param,
        _azure_param,
        _sqlblob_param,
        _dafny_oracle_param,
    ]
)
def backend(
    request: pytest.FixtureRequest,
    moto_server: str | None,
    sftp_server: tuple[int, str] | None,
    azurite_server: str | None,
    http_server: object | None,
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

        assert isinstance(http_server, HTTPServer)
        # Clear handlers from previous test, set 404 default
        http_server.clear()
        http_server.respond_nohandler = lambda request, extra_message="": WerkzeugResponse(  # type: ignore[assignment]
            b"Not Found", status=404
        )
        b = ReadOnlyHttpBackend(base_url=http_server.url_for("/conformance/"), http_client="urllib")
        yield b
        b.close()
    elif request.param == "dafny-oracle":
        from tests.backends.dafny_oracle import DafnyOracleBackend

        yield DafnyOracleBackend()
    elif request.param == "sql-blob":
        from remote_store.backends._sqlalchemy import SQLBlobBackend

        b = SQLBlobBackend(url="sqlite:///:memory:")
        yield b
        b.close()
    elif request.param == "azure":
        from remote_store.backends._azure import AzureBackend

        assert azurite_server is not None
        container = f"conformance-{uuid.uuid4().hex[:8]}"
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(azurite_server)
        try:
            service.create_container(container)
        except Exception:  # noqa: BLE001
            service.close()
            raise
        b = AzureBackend(container=container, connection_string=azurite_server)
        yield b
        b.close()
        service.delete_container(container)
        service.close()
    else:
        pytest.skip(f"Unknown backend: {request.param}")
