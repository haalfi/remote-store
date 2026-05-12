"""End-to-end test fixtures -- connect to Docker-hosted backend services.

Requires ``docker compose -f benchmarks/infra/docker-compose.yml up -d``.
Tests are skipped when the required service is not reachable.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from remote_store import Store
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator


# ---------------------------------------------------------------------------
# Docker defaults (same as benchmarks/conftest.py)
# ---------------------------------------------------------------------------

MINIO_HOST = os.environ.get("E2E_MINIO_HOST", "127.0.0.1")
MINIO_PORT = int(os.environ.get("E2E_MINIO_PORT", "9000"))
MINIO_ENDPOINT = f"http://{MINIO_HOST}:{MINIO_PORT}"
MINIO_ACCESS_KEY = os.environ.get("E2E_MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("E2E_MINIO_SECRET_KEY", "minioadmin")

AZURITE_HOST = os.environ.get("E2E_AZURITE_HOST", "127.0.0.1")
AZURITE_PORT = int(os.environ.get("E2E_AZURITE_PORT", "10000"))
AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw==;"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
)

SFTP_HOST = os.environ.get("E2E_SFTP_HOST", "127.0.0.1")
SFTP_PORT = int(os.environ.get("E2E_SFTP_PORT", "2222"))
SFTP_USER = os.environ.get("E2E_SFTP_USER", "benchuser")
SFTP_PASS = os.environ.get("E2E_SFTP_PASS", "benchpass")

LEGACY_SFTP_HOST = os.environ.get("E2E_LEGACY_SFTP_HOST", "127.0.0.1")
LEGACY_SFTP_PORT = int(os.environ.get("E2E_LEGACY_SFTP_PORT", "2223"))
LEGACY_SFTP_USER = os.environ.get("E2E_LEGACY_SFTP_USER", "legacyuser")
LEGACY_SFTP_PASS = os.environ.get("E2E_LEGACY_SFTP_PASS", "legacypass")


# ---------------------------------------------------------------------------
# Reachability helpers
# ---------------------------------------------------------------------------


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _minio_available() -> bool:
    try:
        import s3fs  # noqa: F401
    except ImportError:
        return False
    return _port_open(MINIO_HOST, MINIO_PORT)


def _s3_pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        import s3fs  # noqa: F401
    except ImportError:
        return False
    return _port_open(MINIO_HOST, MINIO_PORT)


def _azurite_available() -> bool:
    try:
        import azure.storage.filedatalake  # noqa: F401
    except ImportError:
        return False
    return _port_open(AZURITE_HOST, AZURITE_PORT)


def _sftp_available() -> bool:
    try:
        import paramiko  # noqa: F401
    except ImportError:
        return False
    return _port_open(SFTP_HOST, SFTP_PORT)


def _legacy_sftp_available() -> bool:
    try:
        import paramiko  # noqa: F401
    except ImportError:
        return False
    return _port_open(LEGACY_SFTP_HOST, LEGACY_SFTP_PORT)


# ---------------------------------------------------------------------------
# SFTP cleanup helpers
# ---------------------------------------------------------------------------


def _sftp_rmtree(sftp: Any, path: str) -> None:
    """Recursively remove a directory tree via paramiko SFTP."""
    import stat

    try:
        entries = sftp.listdir_attr(path)
    except FileNotFoundError:
        return
    for entry in entries:
        child = f"{path}/{entry.filename}"
        if stat.S_ISDIR(entry.st_mode):  # type: ignore[arg-type]
            _sftp_rmtree(sftp, child)
        else:
            sftp.remove(child)
    sftp.rmdir(path)


def _sftp_cleanup(host: str, port: int, username: str, base_path: str, password: str) -> None:
    """Remove the SFTP test directory using a fresh transport."""
    import paramiko

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        try:
            _sftp_rmtree(sftp, base_path)
        finally:
            sftp.close()
    finally:
        transport.close()


# ---------------------------------------------------------------------------
# S3 cleanup helper
# ---------------------------------------------------------------------------


def _paginated_delete_s3(client: Any, bucket: str) -> None:
    """Delete all objects in *bucket* using pagination."""
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])


# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

minio_skip = pytest.mark.skipif(not _minio_available(), reason="MinIO not reachable or s3fs not installed")
s3_pyarrow_skip = pytest.mark.skipif(
    not _s3_pyarrow_available(), reason="MinIO not reachable or pyarrow/s3fs not installed"
)
azurite_skip = pytest.mark.skipif(not _azurite_available(), reason="Azurite not reachable or azure SDK not installed")
sftp_skip = pytest.mark.skipif(not _sftp_available(), reason="SFTP container not reachable or paramiko not installed")
legacy_sftp_skip = pytest.mark.skipif(
    not _legacy_sftp_available(),
    reason=(
        "Legacy SFTP container not reachable "
        "(start: docker compose -f benchmarks/infra/docker-compose.yml up -d legacy-sftp)"
    ),
)


# ---------------------------------------------------------------------------
# Store fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_lake() -> Iterator[Store]:
    """In-memory lake store (baseline, always available)."""
    backend = MemoryBackend()
    store = Store(backend=backend)
    yield store
    store.close()


@pytest.fixture
def s3_lake() -> Iterator[Store]:
    """S3 lake store backed by MinIO Docker."""
    pytest.importorskip("s3fs")
    if not _minio_available():
        pytest.skip("MinIO not reachable")

    import boto3

    from remote_store.backends._s3 import S3Backend

    tag = uuid.uuid4().hex[:8]
    bucket = f"e2e-lake-{tag}"

    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)

    backend = S3Backend(
        bucket=bucket,
        key=MINIO_ACCESS_KEY,
        secret=MINIO_SECRET_KEY,
        region_name="us-east-1",
        endpoint_url=MINIO_ENDPOINT,
    )
    store = Store(backend=backend)
    yield store
    store.close()
    _paginated_delete_s3(client, bucket)
    client.delete_bucket(Bucket=bucket)


@pytest.fixture
def s3_pyarrow_lake() -> Iterator[Store]:
    """S3-PyArrow lake store backed by MinIO Docker."""
    pytest.importorskip("pyarrow")
    pytest.importorskip("s3fs")
    if not _minio_available():
        pytest.skip("MinIO not reachable")

    import boto3

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    tag = uuid.uuid4().hex[:8]
    bucket = f"e2e-lake-pa-{tag}"

    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)

    backend = S3PyArrowBackend(
        bucket=bucket,
        key=MINIO_ACCESS_KEY,
        secret=MINIO_SECRET_KEY,
        region_name="us-east-1",
        endpoint_url=MINIO_ENDPOINT,
    )
    store = Store(backend=backend)
    yield store
    store.close()
    _paginated_delete_s3(client, bucket)
    client.delete_bucket(Bucket=bucket)


@pytest.fixture
def azurite_lake() -> Iterator[Store]:
    """Azure lake store backed by Azurite Docker."""
    pytest.importorskip("azure.storage.filedatalake")
    if not _azurite_available():
        pytest.skip("Azurite not reachable")

    from azure.storage.blob import BlobServiceClient

    from remote_store.backends._azure import AzureBackend

    tag = uuid.uuid4().hex[:8]
    container = f"e2e-lake-{tag}"

    service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
    service.create_container(container)

    backend = AzureBackend(container=container, connection_string=AZURITE_CONN_STR)
    store = Store(backend=backend)
    yield store
    store.close()
    service.delete_container(container)
    service.close()


@pytest.fixture
def sftp_lake() -> Iterator[Store]:
    """SFTP lake store backed by atmoz/sftp Docker."""
    pytest.importorskip("paramiko")
    if not _sftp_available():
        pytest.skip("SFTP not reachable")

    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    tag = uuid.uuid4().hex[:8]
    base_path = f"/upload/e2e-lake-{tag}"

    # Create the base_path directory before the backend connects.
    # _ensure_parent_dirs skips when parent == base_path, so root-level
    # writes would fail without this.
    import paramiko

    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    assert sftp is not None
    try:
        sftp.mkdir(base_path)
    finally:
        sftp.close()
        transport.close()

    backend = SFTPBackend(
        host=SFTP_HOST,
        port=SFTP_PORT,
        username=SFTP_USER,
        password=SFTP_PASS,
        base_path=base_path,
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    store = Store(backend=backend)
    yield store
    store.close()
    _sftp_cleanup(SFTP_HOST, SFTP_PORT, SFTP_USER, base_path, SFTP_PASS)


@pytest.fixture
def sql_lake() -> Iterator[Store]:
    """SQLite-backed blob store (always available, no Docker needed)."""
    pytest.importorskip("sqlalchemy")

    from remote_store.backends._sqlalchemy import SQLBlobBackend

    backend = SQLBlobBackend(url="sqlite://")
    store = Store(backend=backend)
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Shared multi-backend store chain
# ---------------------------------------------------------------------------


@dataclass
class _CleanupEntry:
    """Resources to clean up after a multi-backend test completes."""

    kind: str  # "s3", "sftp", "azure"
    extras: dict[str, Any] = field(default_factory=dict)


def _build_store_chain() -> tuple[list[tuple[str, Store]], list[_CleanupEntry]]:
    """Return ``(stores, cleanups)`` for all available backends.

    Always includes Memory first and SQLBlob last *within this function's
    return value* (when installed).  Callers that extend the list after
    the fact (e.g. appending ``azure-bridged``) will see it after SQLBlob.
    Docker backends (S3/MinIO, SFTP, Azure, S3-PyArrow) are included only
    when reachable.  Does *not* include ``azure-bridged``; tests that need it
    should extend the returned list before yielding.
    """
    stores: list[tuple[str, Store]] = []
    cleanups: list[_CleanupEntry] = []

    stores.append(("memory", Store(backend=MemoryBackend())))

    if _minio_available():
        import boto3

        from remote_store.backends._s3 import S3Backend

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-{tag}"
        client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        stores.append(
            (
                "s3",
                Store(
                    backend=S3Backend(
                        bucket=bucket,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                        region_name="us-east-1",
                        endpoint_url=MINIO_ENDPOINT,
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("s3", {"client": client, "bucket": bucket}))

    if _sftp_available():
        import paramiko

        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        tag = uuid.uuid4().hex[:8]
        base_path = f"/upload/e2e-{tag}"
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        try:
            sftp.mkdir(base_path)
        finally:
            sftp.close()
            transport.close()
        stores.append(
            (
                "sftp",
                Store(
                    backend=SFTPBackend(
                        host=SFTP_HOST,
                        port=SFTP_PORT,
                        username=SFTP_USER,
                        password=SFTP_PASS,
                        base_path=base_path,
                        host_key_policy=HostKeyPolicy.AUTO_ADD,
                        connect_kwargs={"allow_agent": False, "look_for_keys": False},
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("sftp", {"base_path": base_path}))

    if _azurite_available():
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        tag = uuid.uuid4().hex[:8]
        container = f"e2e-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        stores.append(
            (
                "azure",
                Store(backend=AzureBackend(container=container, connection_string=AZURITE_CONN_STR)),
            )
        )
        cleanups.append(_CleanupEntry("azure", {"service": service, "container": container}))

    if _s3_pyarrow_available():
        import boto3

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-pa-{tag}"
        client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        stores.append(
            (
                "s3-pyarrow",
                Store(
                    backend=S3PyArrowBackend(
                        bucket=bucket,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                        region_name="us-east-1",
                        endpoint_url=MINIO_ENDPOINT,
                    )
                ),
            )
        )
        # kind="s3" reuses the same boto3 teardown path as the plain S3 backend.
        cleanups.append(_CleanupEntry("s3", {"client": client, "bucket": bucket}))

    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend

        stores.append(("sql-blob", Store(backend=SQLBlobBackend(url="sqlite://"))))
    except ImportError:
        pass

    return stores, cleanups


def _teardown_store_chain(stores: list[tuple[str, Store]], cleanups: list[_CleanupEntry]) -> None:
    """Close all stores and clean up remote infrastructure."""
    for _name, store in stores:
        store.close()
    for entry in cleanups:
        if entry.kind == "s3":
            _paginated_delete_s3(entry.extras["client"], entry.extras["bucket"])
            entry.extras["client"].delete_bucket(Bucket=entry.extras["bucket"])
        elif entry.kind == "sftp":
            _sftp_cleanup(SFTP_HOST, SFTP_PORT, SFTP_USER, entry.extras["base_path"], SFTP_PASS)
        elif entry.kind == "azure":
            entry.extras["service"].delete_container(entry.extras["container"])
            entry.extras["service"].close()


@pytest.fixture
def store_chain() -> Iterator[list[tuple[str, Store]]]:
    """Yield all available backend stores for multi-backend e2e tests.

    Standard set: Memory, S3/MinIO, SFTP, Azure/Azurite, S3-PyArrow, SQLBlob.
    Memory and SQLBlob are always present; Docker backends are included only
    when their service is reachable.

    Tests that need ``azure-bridged`` define a local ``store_chain`` fixture
    that calls ``_build_store_chain()``, extends the list, and then calls
    ``_teardown_store_chain()``; the local fixture shadows this one.
    """
    stores, cleanups = _build_store_chain()
    yield stores
    _teardown_store_chain(stores, cleanups)
