"""Benchmark fixtures -- connect to Docker-hosted or cloud backend services.

Requires ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
to be running (Docker mode), or appropriate env vars set (cloud mode).

Use ``--infra cloud`` to run against real cloud services instead of Docker.
"""

from __future__ import annotations

import _thread
import os
import socket
import sys
import tempfile
import threading
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--infra",
        default="docker",
        choices=["docker", "cloud"],
        help="Infrastructure mode: 'docker' (default) uses local containers, 'cloud' uses real services.",
    )
    parser.addoption(
        "--backend",
        default=None,
        help="Comma-separated backend filter (e.g., --backend s3,sftp).",
    )
    parser.addoption(
        "--bench-timeout",
        default=None,
        type=int,
        help="Per-test timeout in seconds (default: 120 cloud, 60 docker).",
    )
    parser.addoption(
        "--latency",
        default=0,
        type=int,
        help="Simulated network latency in ms for azure-latency backend (via Toxiproxy).",
    )


# ---------------------------------------------------------------------------
# Detect --infra mode at collection time for skip-mark evaluation
# ---------------------------------------------------------------------------


def _is_cloud_mode() -> bool:
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--infra=cloud":
            return True
        if arg == "--infra" and i + 1 < len(argv) and argv[i + 1] == "cloud":
            return True
    return False


_CLOUD_MODE = _is_cloud_mode()


# ---------------------------------------------------------------------------
# Backend filter (deselect, not skip -- avoids fixture setup)
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    backend_filter = config.getoption("--backend")
    if not backend_filter:
        return
    allowed = {b.strip() for b in backend_filter.split(",")}
    selected, deselected = [], []
    for item in items:
        params = getattr(item, "callspec", None)
        if params is None:
            selected.append(item)
            continue
        p = params.params
        if "bench_backend" in p:
            (selected if p["bench_backend"] in allowed else deselected).append(item)
        elif "bench_target" in p:
            (selected if p["bench_target"][0] in allowed else deselected).append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


# ---------------------------------------------------------------------------
# Per-test timeout watchdog (Windows-compatible, no signal.alarm)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _bench_timeout(request: pytest.FixtureRequest) -> Any:
    timeout = request.config.getoption("--bench-timeout")
    if timeout is None:
        timeout = 120 if request.config.getoption("--infra") == "cloud" else 60
    timer = threading.Timer(float(timeout), _thread.interrupt_main)
    timer.daemon = True
    timer.start()
    try:
        yield
    except KeyboardInterrupt:
        pytest.fail(f"Benchmark timed out after {timeout}s")
    finally:
        timer.cancel()


# ---------------------------------------------------------------------------
# Post-run throughput computation (uses final stats from JSON output)
# ---------------------------------------------------------------------------


def pytest_benchmark_update_json(config: Any, benchmarks: Any, output_json: Any) -> None:
    """Inject ``throughput_MBps`` into saved JSON from ``payload_bytes`` + mean."""
    for bench in output_json.get("benchmarks", []):
        extra = bench.get("extra_info", {})
        payload = extra.get("payload_bytes")
        mean = bench.get("stats", {}).get("mean")
        if payload and mean and mean > 0:
            extra["throughput_MBps"] = round(payload / mean / 1_048_576, 2)


# ---------------------------------------------------------------------------
# Reachability helpers
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


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _paginated_delete_s3(client: Any, bucket: str, prefix: str = "") -> None:
    """Delete all objects in *bucket* (optionally under *prefix*) using pagination."""
    paginator = client.get_paginator("list_objects_v2")
    kwargs: dict[str, str] = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    for page in paginator.paginate(**kwargs):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])


# ---------------------------------------------------------------------------
# Docker defaults
# ---------------------------------------------------------------------------

MINIO_HOST = os.environ.get("BENCH_MINIO_HOST", "127.0.0.1")
MINIO_PORT = int(os.environ.get("BENCH_MINIO_PORT", "9000"))
MINIO_ENDPOINT = f"http://{MINIO_HOST}:{MINIO_PORT}"
MINIO_ACCESS_KEY = os.environ.get("BENCH_MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("BENCH_MINIO_SECRET_KEY", "minioadmin")

AZURE_MAX_CONCURRENCY = int(os.environ.get("BENCH_AZURE_MAX_CONCURRENCY", "1"))

# Azurite and Toxiproxy connection strings / config from shared module.
from benchmarks._toxiproxy import (  # noqa: E402
    AZURITE_CONN_STR,
    AZURITE_HOST,
    AZURITE_PORT,
    TOXIPROXY_API_PORT,
    TOXIPROXY_AZURITE_CONN_STR,
    TOXIPROXY_HOST,
)

SFTP_HOST = os.environ.get("BENCH_SFTP_HOST", "127.0.0.1")
SFTP_PORT = int(os.environ.get("BENCH_SFTP_PORT", "2222"))
SFTP_USER = os.environ.get("BENCH_SFTP_USER", "benchuser")
SFTP_PASS = os.environ.get("BENCH_SFTP_PASS", "benchpass")


# ---------------------------------------------------------------------------
# Cloud config (used when --infra cloud)
# ---------------------------------------------------------------------------

CLOUD_S3_BUCKET = os.environ.get("BENCH_S3_BUCKET", "")
CLOUD_S3_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
CLOUD_S3_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
CLOUD_S3_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

CLOUD_AZURE_CONN_STR = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
CLOUD_AZURE_CONTAINER = os.environ.get("BENCH_AZURE_CONTAINER", "")

CLOUD_SFTP_HOST = os.environ.get("BENCH_SFTP_HOST", "")
CLOUD_SFTP_PORT = int(os.environ.get("BENCH_SFTP_PORT", "22"))
CLOUD_SFTP_USER = os.environ.get("BENCH_SFTP_USER", "")
CLOUD_SFTP_PASS = os.environ.get("BENCH_SFTP_PASS", "")
CLOUD_SFTP_KEY_FILE = os.environ.get("BENCH_SFTP_KEY_FILE", "")


def _minio_available() -> bool:
    try:
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


def _toxiproxy_available() -> bool:
    try:
        import azure.storage.blob  # noqa: F401
    except ImportError:
        return False
    return _port_open(TOXIPROXY_HOST, TOXIPROXY_API_PORT)


def _sftp_docker_available() -> bool:
    try:
        import paramiko  # noqa: F401
    except ImportError:
        return False
    return _port_open(SFTP_HOST, SFTP_PORT)


def _s3_pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        import s3fs  # noqa: F401
    except ImportError:
        return False
    return _port_open(MINIO_HOST, MINIO_PORT)


# ---------------------------------------------------------------------------
# pytest.param entries with cloud-aware skip markers
# ---------------------------------------------------------------------------

if _CLOUD_MODE:
    _s3_skip = pytest.mark.skipif(not CLOUD_S3_BUCKET, reason="BENCH_S3_BUCKET not set for cloud mode")
    _pa_skip = pytest.mark.skipif(not CLOUD_S3_BUCKET, reason="BENCH_S3_BUCKET not set for cloud mode")
    _sftp_skip = pytest.mark.skipif(not CLOUD_SFTP_HOST, reason="BENCH_SFTP_HOST not set for cloud mode")
    _azure_skip = pytest.mark.skipif(
        not CLOUD_AZURE_CONN_STR or not CLOUD_AZURE_CONTAINER,
        reason="AZURE_STORAGE_CONNECTION_STRING / BENCH_AZURE_CONTAINER not set for cloud mode",
    )
else:
    _s3_skip = pytest.mark.skipif(not _minio_available(), reason="MinIO not reachable or s3fs not installed")
    _pa_skip = pytest.mark.skipif(
        not _s3_pyarrow_available(), reason="MinIO not reachable or pyarrow/s3fs not installed"
    )
    _sftp_skip = pytest.mark.skipif(
        not _sftp_docker_available(), reason="SFTP container not reachable or paramiko not installed"
    )
    _azure_skip = pytest.mark.skipif(
        not _azurite_available(), reason="Azurite not reachable or azure SDK not installed"
    )

_toxiproxy_skip = pytest.mark.skipif(
    not _toxiproxy_available(), reason="Toxiproxy not reachable or azure SDK not installed"
)

_local_param = pytest.param("local", id="local")
_s3_param = pytest.param("s3", id="s3-minio", marks=_s3_skip)
_s3_pyarrow_param = pytest.param("s3-pyarrow", id="s3-pyarrow-minio", marks=_pa_skip)
_sftp_param = pytest.param("sftp", id="sftp-docker", marks=_sftp_skip)
_azure_param = pytest.param("azure", id="azure-azurite", marks=_azure_skip)
_azure_latency_param = pytest.param("azure-latency", id="azure-latency", marks=_toxiproxy_skip)


# ---------------------------------------------------------------------------
# Toxiproxy latency management
# ---------------------------------------------------------------------------


from benchmarks._toxiproxy import clear_latency as _toxiproxy_clear_latency  # noqa: E402
from benchmarks._toxiproxy import set_latency as _toxiproxy_set_latency  # noqa: E402

# ---------------------------------------------------------------------------
# SFTP cleanup helper (with try/finally safety)
# ---------------------------------------------------------------------------


def _sftp_cleanup(
    host: str,
    port: int,
    username: str,
    base_path: str,
    password: str | None = None,
    key_file: str | None = None,
) -> None:
    """Clean up an SFTP directory tree, closing transport even on failure."""
    import paramiko

    transport = paramiko.Transport((host, port))
    try:
        if key_file:
            pkey = paramiko.RSAKey.from_private_key_file(key_file)
            transport.connect(username=username, pkey=pkey)
        elif password:
            transport.connect(username=username, password=password)
        else:
            transport.connect(username=username)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        try:
            _sftp_rmtree(sftp, base_path)
        finally:
            sftp.close()
    finally:
        transport.close()


# ---------------------------------------------------------------------------
# Backend fixture
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        _local_param,
        _s3_param,
        _s3_pyarrow_param,
        _sftp_param,
        _azure_param,
        _azure_latency_param,
    ]
)
def bench_backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Yield a fresh backend instance for each parameterized backend type.

    When ``--infra cloud`` is passed, uses real cloud credentials from env vars
    instead of Docker containers.
    """
    cloud = request.config.getoption("--infra") == "cloud"
    tag = uuid.uuid4().hex[:8]

    if request.param == "local":
        with tempfile.TemporaryDirectory() as tmp:
            yield LocalBackend(root=tmp)

    elif request.param == "s3":
        import boto3

        from remote_store.backends._s3 import S3Backend

        if cloud:
            if not CLOUD_S3_BUCKET:
                pytest.skip("BENCH_S3_BUCKET not set for cloud mode")
            bucket = CLOUD_S3_BUCKET
            client = boto3.client("s3", region_name=CLOUD_S3_REGION)
            b = S3Backend(bucket=bucket, region_name=CLOUD_S3_REGION)
            yield b
            b.close()
            # Cleanup: delete all objects (bucket should be dedicated to benchmarks)
            _paginated_delete_s3(client, bucket)
        else:
            bucket = f"bench-s3-{tag}"
            client = boto3.client(
                "s3",
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            client.create_bucket(Bucket=bucket)
            b = S3Backend(
                bucket=bucket,
                key=MINIO_ACCESS_KEY,
                secret=MINIO_SECRET_KEY,
                region_name="us-east-1",
                endpoint_url=MINIO_ENDPOINT,
            )
            yield b
            b.close()
            _paginated_delete_s3(client, bucket)
            client.delete_bucket(Bucket=bucket)

    elif request.param == "s3-pyarrow":
        import boto3

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        if cloud:
            if not CLOUD_S3_BUCKET:
                pytest.skip("BENCH_S3_BUCKET not set for cloud mode")
            bucket = CLOUD_S3_BUCKET
            client = boto3.client("s3", region_name=CLOUD_S3_REGION)
            b = S3PyArrowBackend(bucket=bucket, region_name=CLOUD_S3_REGION)
            yield b
            b.close()
            _paginated_delete_s3(client, bucket)
        else:
            bucket = f"bench-pa-{tag}"
            client = boto3.client(
                "s3",
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            client.create_bucket(Bucket=bucket)
            b = S3PyArrowBackend(
                bucket=bucket,
                key=MINIO_ACCESS_KEY,
                secret=MINIO_SECRET_KEY,
                region_name="us-east-1",
                endpoint_url=MINIO_ENDPOINT,
            )
            yield b
            b.close()
            _paginated_delete_s3(client, bucket)
            client.delete_bucket(Bucket=bucket)

    elif request.param == "sftp":
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        if cloud:
            if not CLOUD_SFTP_HOST:
                pytest.skip("BENCH_SFTP_HOST not set for cloud mode")
            base_path = f"/upload/bench_{tag}"
            connect_kwargs: dict[str, Any] = {}
            if CLOUD_SFTP_KEY_FILE:
                connect_kwargs["key_filename"] = CLOUD_SFTP_KEY_FILE
            elif CLOUD_SFTP_PASS:
                connect_kwargs["password"] = CLOUD_SFTP_PASS
            b = SFTPBackend(
                host=CLOUD_SFTP_HOST,
                port=CLOUD_SFTP_PORT,
                username=CLOUD_SFTP_USER,
                base_path=base_path,
                host_key_policy=HostKeyPolicy.AUTO_ADD,
                connect_kwargs=connect_kwargs,
            )
            yield b
            b.close()
            _sftp_cleanup(
                CLOUD_SFTP_HOST,
                CLOUD_SFTP_PORT,
                CLOUD_SFTP_USER,
                base_path,
                password=CLOUD_SFTP_PASS or None,
                key_file=CLOUD_SFTP_KEY_FILE or None,
            )
        else:
            base_path = f"/upload/bench_{tag}"
            b = SFTPBackend(
                host=SFTP_HOST,
                port=SFTP_PORT,
                username=SFTP_USER,
                password=SFTP_PASS,
                base_path=base_path,
                host_key_policy=HostKeyPolicy.AUTO_ADD,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            yield b
            b.close()
            _sftp_cleanup(SFTP_HOST, SFTP_PORT, SFTP_USER, base_path, password=SFTP_PASS)

    elif request.param == "azure":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        if cloud:
            if not CLOUD_AZURE_CONN_STR or not CLOUD_AZURE_CONTAINER:
                pytest.skip("AZURE_STORAGE_CONNECTION_STRING / BENCH_AZURE_CONTAINER not set")
            container = CLOUD_AZURE_CONTAINER
            b = AzureBackend(
                container=container, connection_string=CLOUD_AZURE_CONN_STR, max_concurrency=AZURE_MAX_CONCURRENCY
            )
            yield b
            b.close()
            # Cleanup: delete all blobs (container should be dedicated to benchmarks)
            service = BlobServiceClient.from_connection_string(CLOUD_AZURE_CONN_STR)
            cc = service.get_container_client(container)
            for blob in cc.list_blobs():
                cc.delete_blob(blob.name)
            service.close()
        else:
            container = f"bench-az-{tag}"
            service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
            service.create_container(container)
            b = AzureBackend(
                container=container, connection_string=AZURITE_CONN_STR, max_concurrency=AZURE_MAX_CONCURRENCY
            )
            yield b
            b.close()
            service.delete_container(container)
            service.close()

    elif request.param == "azure-latency":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        latency_ms = request.config.getoption("--latency")
        container = f"bench-azl-{tag}"
        # Create container via direct Azurite connection (bypasses toxiproxy).
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        # Set up latency toxic.
        _toxiproxy_set_latency(latency_ms)
        # Backend connects through toxiproxy.
        b = AzureBackend(
            container=container,
            connection_string=TOXIPROXY_AZURITE_CONN_STR,
            max_concurrency=AZURE_MAX_CONCURRENCY,
        )
        yield b
        b.close()
        _toxiproxy_clear_latency()
        service.delete_container(container)
        service.close()

    else:
        pytest.skip(f"Unknown backend: {request.param}")


# ---------------------------------------------------------------------------
# Comparative benchmark target fixture
# ---------------------------------------------------------------------------


def _adlfs_available() -> bool:
    try:
        import adlfs  # noqa: F401
    except ImportError:
        return False
    return True


def _sshfs_available() -> bool:
    try:
        import sshfs  # noqa: F401
    except ImportError:
        return False
    return True


def _build_target_params() -> list[Any]:
    """Build parametrized (backend_type, target_kind) entries for bench_target.

    Skip marks are cloud-aware: in Docker mode they check port reachability,
    in cloud mode they check for the required env vars.
    """
    params: list[Any] = []

    # Local
    params.append(pytest.param(("local", "remote_store"), id="local-remote_store"))
    params.append(pytest.param(("local", "pathlib_raw"), id="local-pathlib_raw"))
    params.append(pytest.param(("local", "fsspec_local"), id="local-fsspec_local"))

    # S3 (MinIO / cloud)
    params.append(pytest.param(("s3", "remote_store"), id="s3-remote_store", marks=_s3_skip))
    params.append(pytest.param(("s3", "boto3_raw"), id="s3-boto3_raw", marks=_s3_skip))
    params.append(pytest.param(("s3", "s3fs"), id="s3-s3fs", marks=_s3_skip))

    # S3-PyArrow (MinIO / cloud)
    params.append(pytest.param(("s3-pyarrow", "remote_store"), id="s3-pyarrow-remote_store", marks=_pa_skip))

    # SFTP
    params.append(pytest.param(("sftp", "remote_store"), id="sftp-remote_store", marks=_sftp_skip))
    params.append(pytest.param(("sftp", "paramiko_raw"), id="sftp-paramiko_raw", marks=_sftp_skip))
    sshfs_skip = [
        _sftp_skip,
        pytest.mark.skipif(not _sshfs_available(), reason="sshfs not installed"),
    ]
    params.append(pytest.param(("sftp", "sshfs"), id="sftp-sshfs", marks=sshfs_skip))

    # Azure (Azurite / cloud)
    params.append(pytest.param(("azure", "remote_store"), id="azure-remote_store", marks=_azure_skip))
    params.append(pytest.param(("azure", "azure_blob_raw"), id="azure-azure_blob_raw", marks=_azure_skip))
    adlfs_skip = [
        _azure_skip,
        pytest.mark.skipif(not _adlfs_available(), reason="adlfs not installed"),
    ]
    params.append(pytest.param(("azure", "adlfs"), id="azure-adlfs", marks=adlfs_skip))

    # Azure with simulated latency (Toxiproxy)
    params.append(
        pytest.param(("azure-latency", "remote_store"), id="azure-latency-remote_store", marks=_toxiproxy_skip)
    )

    return params


@pytest.fixture(params=_build_target_params())
def bench_target(request: pytest.FixtureRequest) -> Iterator[Any]:
    """Yield a BenchTarget for comparative benchmarks.

    Each parametrization is a ``(backend_type, target_kind)`` pair.
    Test IDs look like ``test_write[s3-remote_store]``.

    Supports both Docker and cloud (``--infra cloud``) modes.
    """
    from benchmarks.targets._remote_store import RemoteStoreTarget

    backend_type, target_kind = request.param
    cloud = request.config.getoption("--infra") == "cloud"
    tag = uuid.uuid4().hex[:8]

    if backend_type == "local":
        with tempfile.TemporaryDirectory() as tmp:
            if target_kind == "remote_store":
                yield RemoteStoreTarget(LocalBackend(root=tmp))
            elif target_kind == "pathlib_raw":
                from benchmarks.targets._raw_sdk import PathLibRawTarget

                yield PathLibRawTarget(root=tmp)
            elif target_kind == "fsspec_local":
                from benchmarks.targets._fsspec import LocalFsspecTarget

                yield LocalFsspecTarget(root=tmp)

    elif backend_type in ("s3", "s3-pyarrow"):
        import boto3

        if cloud:
            bucket = CLOUD_S3_BUCKET
            client = boto3.client("s3", region_name=CLOUD_S3_REGION)
        else:
            bucket = f"bench-tgt-{tag}"
            client = boto3.client(
                "s3",
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            client.create_bucket(Bucket=bucket)
        try:
            if target_kind == "remote_store":
                if backend_type == "s3":
                    from remote_store.backends._s3 import S3Backend

                    if cloud:
                        b = S3Backend(bucket=bucket, region_name=CLOUD_S3_REGION)
                    else:
                        b = S3Backend(
                            bucket=bucket,
                            key=MINIO_ACCESS_KEY,
                            secret=MINIO_SECRET_KEY,
                            region_name="us-east-1",
                            endpoint_url=MINIO_ENDPOINT,
                        )
                else:
                    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

                    if cloud:
                        b = S3PyArrowBackend(bucket=bucket, region_name=CLOUD_S3_REGION)
                    else:
                        b = S3PyArrowBackend(
                            bucket=bucket,
                            key=MINIO_ACCESS_KEY,
                            secret=MINIO_SECRET_KEY,
                            region_name="us-east-1",
                            endpoint_url=MINIO_ENDPOINT,
                        )
                t = RemoteStoreTarget(b)
                yield t
                t.close()
            elif target_kind == "boto3_raw":
                from benchmarks.targets._raw_sdk import Boto3RawTarget

                yield Boto3RawTarget(bucket=bucket, client=client)
            elif target_kind == "s3fs":
                from benchmarks.targets._fsspec import S3fsTarget

                if cloud:
                    t = S3fsTarget(bucket=bucket)  # type: ignore[assignment]
                else:
                    t = S3fsTarget(  # type: ignore[assignment]
                        bucket=bucket,
                        endpoint_url=MINIO_ENDPOINT,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                    )
                yield t
                t.close()
        finally:
            _paginated_delete_s3(client, bucket)
            if not cloud:
                client.delete_bucket(Bucket=bucket)

    elif backend_type == "sftp":
        if cloud:
            host, port, user = CLOUD_SFTP_HOST, CLOUD_SFTP_PORT, CLOUD_SFTP_USER
            password = CLOUD_SFTP_PASS or None
            key_file = CLOUD_SFTP_KEY_FILE or None
        else:
            host, port, user = SFTP_HOST, SFTP_PORT, SFTP_USER
            password = SFTP_PASS
            key_file = None

        base_path = f"/upload/bench_tgt_{tag}"
        try:
            if target_kind == "remote_store":
                from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

                connect_kwargs: dict[str, Any] = {}
                if key_file:
                    connect_kwargs["key_filename"] = key_file
                if not cloud:
                    connect_kwargs.update(allow_agent=False, look_for_keys=False)
                bk = SFTPBackend(
                    host=host,
                    port=port,
                    username=user,
                    password=password,
                    base_path=base_path,
                    host_key_policy=HostKeyPolicy.AUTO_ADD,
                    connect_kwargs=connect_kwargs,
                )
                t = RemoteStoreTarget(bk)
                yield t
                t.close()
            elif target_kind == "paramiko_raw":
                from benchmarks.targets._raw_sdk import ParamikoRawTarget

                if not password:
                    pytest.skip("ParamikoRawTarget requires password auth")
                t = ParamikoRawTarget(
                    host=host,
                    port=port,
                    username=user,
                    password=password,
                    base_path=base_path,
                )
                yield t
                t.close()
            elif target_kind == "sshfs":
                from benchmarks.targets._fsspec import SshfsTarget

                if not password:
                    pytest.skip("SshfsTarget requires password auth")
                t = SshfsTarget(
                    host=host,
                    port=port,
                    username=user,
                    password=password,
                    base_path=base_path,
                )
                yield t
                t.close()
        finally:
            _sftp_cleanup(host, port, user, base_path, password=password, key_file=key_file)

    elif backend_type == "azure":
        from azure.storage.blob import BlobServiceClient

        if cloud:
            container = CLOUD_AZURE_CONTAINER
            conn_str = CLOUD_AZURE_CONN_STR
        else:
            container = f"bench-tgt-{tag}"
            conn_str = AZURITE_CONN_STR

        service = BlobServiceClient.from_connection_string(conn_str)
        if not cloud:
            service.create_container(container)
        try:
            if target_kind == "remote_store":
                from remote_store.backends._azure import AzureBackend

                bk = AzureBackend(
                    container=container, connection_string=conn_str, max_concurrency=AZURE_MAX_CONCURRENCY
                )
                t = RemoteStoreTarget(bk)
                yield t
                t.close()
            elif target_kind == "azure_blob_raw":
                from benchmarks.targets._raw_sdk import AzureBlobRawTarget

                t = AzureBlobRawTarget(container=container, connection_string=conn_str)
                yield t
                t.close()
            elif target_kind == "adlfs":
                from benchmarks.targets._fsspec import AdlfsTarget

                t = AdlfsTarget(container=container, connection_string=conn_str)
                yield t
                t.close()
        finally:
            if cloud:
                # Delete all blobs but keep the container
                cc = service.get_container_client(container)
                for blob in cc.list_blobs():
                    cc.delete_blob(blob.name)
            else:
                service.delete_container(container)
            service.close()

    elif backend_type == "azure-latency":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        latency_ms = request.config.getoption("--latency")
        container = f"bench-tgt-azl-{tag}"
        # Create container via direct Azurite (bypasses toxiproxy).
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        _toxiproxy_set_latency(latency_ms)
        try:
            if target_kind == "remote_store":
                bk = AzureBackend(
                    container=container,
                    connection_string=TOXIPROXY_AZURITE_CONN_STR,
                    max_concurrency=AZURE_MAX_CONCURRENCY,
                )
                t = RemoteStoreTarget(bk)
                yield t
                t.close()
        finally:
            _toxiproxy_clear_latency()
            service.delete_container(container)
            service.close()


# ---------------------------------------------------------------------------
# Payload fixtures (various file sizes)
# ---------------------------------------------------------------------------


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(1_024, id="1KB"),
        pytest.param(65_536, id="64KB"),
        pytest.param(1_048_576, id="1MB"),
        pytest.param(10_485_760, id="10MB", marks=pytest.mark.standard),
        pytest.param(104_857_600, id="100MB", marks=pytest.mark.full),
    ],
)
def payload(request: pytest.FixtureRequest) -> bytes:
    """Return a bytes payload of the requested size.

    Session-scoped to avoid re-allocating large payloads (up to 100 MB)
    for every test function.
    """
    return b"X" * request.param


# ---------------------------------------------------------------------------
# Configurable large-file size
# ---------------------------------------------------------------------------

BENCH_LARGE_FILE_MB = int(os.environ.get("BENCH_LARGE_FILE_MB", "10"))
