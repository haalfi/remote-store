"""End-to-end test fixtures -- connect to Docker-hosted backend services.

Requires ``docker compose -f infra/docker-compose.yml up -d``. Tests are
skipped when the required service is not reachable. Host ports, hosts,
and credentials come from ``infra/.env`` (single source of truth).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from infra._settings import (
    AZURITE_CONN_STR,
    AZURITE_HOST,
    AZURITE_PORT,
    LEGACY_SFTP_HOST,
    LEGACY_SFTP_PORT,
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_HOST,
    MINIO_PORT,
    MINIO_SECRET_KEY,
    SFTP_HOST,
    SFTP_PASS,
    SFTP_PORT,
    SFTP_USER,
)
from remote_store import Store
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator


# Docker defaults (host ports, credentials) come from ``infra/.env`` via
# ``infra._settings``. ``infra._settings`` honours per-name os.environ
# overrides, so ``E2E_MINIO_PORT=...`` style spot-overrides keep working
# via the same name (without the ``E2E_`` prefix the old defaults used).


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
# Live Microsoft Graph gate (device-code / consumer OneDrive)
# ---------------------------------------------------------------------------

# Consumer/personal accounts consent to the delegated Files.ReadWrite scope, not
# the work/school .All variants (mirrors the graph_live conformance fixture).
_GRAPH_LIVE_SCOPES = ["Files.ReadWrite", "User.Read"]


def _graph_live_available() -> bool:
    """Return True when the live Graph two-layer gate is satisfied.

    Graph has no emulator — the gate is the ``RS_TEST_LIVE_GRAPH=1`` opt-in
    plus the ``graph`` extra (httpx / msal). Credential presence is validated
    fail-loud only when the hop is actually built (``build_graph_live_store``),
    matching the ``graph_live`` conformance fixture; an unset opt-in skips the
    Graph hop cleanly.
    """
    if os.environ.get("RS_TEST_LIVE_GRAPH") != "1":
        return False
    try:
        import httpx  # noqa: F401
        import msal  # noqa: F401
    except ImportError:
        return False
    return True


def build_graph_live_store(root_path: str) -> Any:
    """Build an ``AsyncStore`` on the real Graph drive, rooted at *root_path*.

    Reuses the two-layer live-credential gate (``require_graph_live_credentials``)
    so missing vars fail loud rather than skip. Caller owns ``aclose()`` and
    scratch-folder cleanup.
    """
    from remote_store.aio import AsyncStore, GraphAuth, GraphBackend
    from tests.backends.fixtures._live_env import require_graph_live_credentials

    creds = require_graph_live_credentials()
    auth = GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"], scopes=_GRAPH_LIVE_SCOPES)
    backend = GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth)
    return AsyncStore(backend=backend, root_path=root_path)


def build_graph_live_sync_store(root_path: str) -> Store:
    """Build a sync ``Store`` on the real Graph drive, bridged via the adapter.

    Graph is async-only; ``AsyncBackendSyncAdapter`` wraps ``GraphBackend`` so the
    live Graph hop can join the *sync* e2e lake / transfer / chain tests — the
    same bridging the ``azure-bridged`` hop uses in the async streaming test.
    Roots via ``Store.root_path`` (not ``GraphBackend.base_path``) so an unrooted
    sibling can delete the scratch folder, mirroring ``build_graph_live_store``.
    Caller owns ``close()`` and scratch-folder cleanup.
    """
    from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
    from remote_store.aio import GraphAuth, GraphBackend
    from tests.backends.fixtures._live_env import require_graph_live_credentials

    creds = require_graph_live_credentials()
    auth = GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"], scopes=_GRAPH_LIVE_SCOPES)
    backend = AsyncBackendSyncAdapter(GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth))
    return Store(backend=backend, root_path=root_path)


def _graph_scratch_cleanup(scratch: str) -> None:
    """Best-effort delete of a Graph scratch folder via an unrooted bridged sibling.

    The rooted store cannot address its own root's parent, so teardown uses an
    unrooted sibling (mirrors ``graph_live._aclose``). A teardown race must never
    turn a green test red.
    """
    try:
        cleaner = build_graph_live_sync_store("")
        try:
            cleaner.delete_folder(scratch, recursive=True, missing_ok=True)
        finally:
            cleaner.close()
    except Exception:  # noqa: BLE001 -- teardown best-effort
        pass


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
        "Legacy SFTP container not reachable (start: docker compose -f infra/docker-compose.yml up -d legacy-sftp)"
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


@pytest.fixture
def graph_lake() -> Iterator[Store]:
    """Live Graph lake store, bridged to sync via ``AsyncBackendSyncAdapter``.

    Graph has no emulator, so this fixture is live-only: it skips unless the
    ``RS_TEST_LIVE_GRAPH`` two-layer gate is satisfied. Each test gets a fresh
    scratch folder on the drive, removed on teardown.
    """
    if not _graph_live_available():
        pytest.skip("Graph live gate unmet (RS_TEST_LIVE_GRAPH=1 + graph extra + creds)")
    scratch = f"e2e-lake-{uuid.uuid4().hex[:8]}"
    store = build_graph_live_sync_store(scratch)
    try:
        yield store
    finally:
        store.close()
        _graph_scratch_cleanup(scratch)


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

    Standard set: Memory, S3/MinIO, SFTP, Azure/Azurite, S3-PyArrow, SQLBlob,
    plus a live-gated ``graph-bridged`` hop (``AsyncBackendSyncAdapter`` over the
    real Graph drive) when the ``RS_TEST_LIVE_GRAPH`` gate is satisfied. Memory
    and SQLBlob are always present; Docker backends are included only when their
    service is reachable; Graph only on a live run.

    Tests that need ``azure-bridged`` define a local ``store_chain`` fixture
    that calls ``_build_store_chain()``, extends the list, and then calls
    ``_teardown_store_chain()``; the local fixture shadows this one — so it does
    not inherit the Graph hop, which is intentional: the async streaming test
    already covers Graph, so the sync streaming chain stays Graph-free.
    """
    stores, cleanups = _build_store_chain()
    graph_scratch: str | None = None
    graph_appended = False
    try:
        # Build the live Graph hop *inside* the try: a build failure (live-lane
        # auth/network hiccup) must still reach the finally so
        # _teardown_store_chain() releases the Docker resources
        # _build_store_chain() already opened — otherwise they leak.
        if _graph_live_available():
            graph_scratch = f"e2e-chain-{uuid.uuid4().hex[:8]}"
            stores.append(("graph-bridged", build_graph_live_sync_store(graph_scratch)))
            graph_appended = True
        yield stores
    finally:
        # Nested finally so a failure closing the Graph hop can never skip the
        # Docker teardown.
        try:
            if graph_appended:
                _name, graph_store = stores.pop()
                graph_store.close()
                _graph_scratch_cleanup(graph_scratch)
        finally:
            _teardown_store_chain(stores, cleanups)
