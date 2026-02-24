"""Benchmark fixtures — connect to Docker-hosted backend services.

Requires ``docker compose up -d`` to be running (see docker-compose.yml).
Backends that are unreachable are automatically skipped.
"""

from __future__ import annotations

import os
import socket
import tempfile
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


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


def pytest_terminal_summary(terminalreporter: Any, config: Any) -> None:
    """Print a throughput summary table after the benchmark run."""
    # Collect results from the benchmark plugin if available
    benchmarks = getattr(config, "_benchmarks", None)
    if not benchmarks:
        # Try the plugin directly
        plugin = config.pluginmanager.getplugin("benchmark")
        if plugin and hasattr(plugin, "benchmarks"):
            benchmarks = plugin.benchmarks
    if not benchmarks:
        return

    rows: list[tuple[str, str, str, str, str]] = []
    for bench in benchmarks:
        extra = getattr(bench, "extra_info", {}) if hasattr(bench, "extra_info") else bench.get("extra_info", {})
        payload = extra.get("payload_bytes")
        if not payload:
            continue
        stats = getattr(bench, "stats", None)
        if not stats:
            continue
        mean = getattr(stats, "mean", 0)
        stddev = getattr(stats, "stddev", 0)
        if mean <= 0:
            continue
        tp = payload / mean / 1_048_576
        name = getattr(bench, "fullname", "") or getattr(bench, "name", "?")
        peak_mem = extra.get("peak_memory_MB")
        mem_str = f"{peak_mem:.2f}" if peak_mem is not None else "-"
        rows.append((name, f"{payload:,}", f"{tp:.2f}", f"{stddev * 1000:.3f}", mem_str))

    if not rows:
        return

    terminalreporter.section("Throughput Summary")
    hdr = f"{'Test':<60} {'Bytes':>12} {'MB/s':>10} {'StdDev ms':>12} {'Peak MB':>10}"
    terminalreporter.line(hdr)
    terminalreporter.line("-" * len(hdr))
    for name, sz, tp, sd, mem in rows:
        # Truncate long names
        short = name if len(name) <= 58 else "..." + name[-55:]
        terminalreporter.line(f"{short:<60} {sz:>12} {tp:>10} {sd:>12} {mem:>10}")


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


MINIO_HOST = os.environ.get("BENCH_MINIO_HOST", "127.0.0.1")
MINIO_PORT = int(os.environ.get("BENCH_MINIO_PORT", "9000"))
MINIO_ENDPOINT = f"http://{MINIO_HOST}:{MINIO_PORT}"
MINIO_ACCESS_KEY = os.environ.get("BENCH_MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("BENCH_MINIO_SECRET_KEY", "minioadmin")

AZURITE_HOST = os.environ.get("BENCH_AZURITE_HOST", "127.0.0.1")
AZURITE_PORT = int(os.environ.get("BENCH_AZURITE_PORT", "10000"))
AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw==;"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
)

SFTP_HOST = os.environ.get("BENCH_SFTP_HOST", "127.0.0.1")
SFTP_PORT = int(os.environ.get("BENCH_SFTP_PORT", "2222"))
SFTP_USER = os.environ.get("BENCH_SFTP_USER", "benchuser")
SFTP_PASS = os.environ.get("BENCH_SFTP_PASS", "benchpass")


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
# pytest.param entries with skip markers
# ---------------------------------------------------------------------------

_local_param = pytest.param("local", id="local")

_s3_param = pytest.param(
    "s3",
    id="s3-minio",
    marks=pytest.mark.skipif(not _minio_available(), reason="MinIO not reachable or s3fs not installed"),
)

_s3_pyarrow_param = pytest.param(
    "s3-pyarrow",
    id="s3-pyarrow-minio",
    marks=pytest.mark.skipif(not _s3_pyarrow_available(), reason="MinIO not reachable or pyarrow/s3fs not installed"),
)

_sftp_param = pytest.param(
    "sftp",
    id="sftp-docker",
    marks=pytest.mark.skipif(
        not _sftp_docker_available(), reason="SFTP container not reachable or paramiko not installed"
    ),
)

_azure_param = pytest.param(
    "azure",
    id="azure-azurite",
    marks=pytest.mark.skipif(not _azurite_available(), reason="Azurite not reachable or azure SDK not installed"),
)


# ---------------------------------------------------------------------------
# Backend fixture
# ---------------------------------------------------------------------------


@pytest.fixture(params=[_local_param, _s3_param, _s3_pyarrow_param, _sftp_param, _azure_param])
def bench_backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Yield a fresh backend instance for each parameterized backend type."""
    tag = uuid.uuid4().hex[:8]

    if request.param == "local":
        with tempfile.TemporaryDirectory() as tmp:
            yield LocalBackend(root=tmp)

    elif request.param == "s3":
        import boto3

        from remote_store.backends._s3 import S3Backend

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
        # Cleanup: delete all objects then the bucket
        resp = client.list_objects_v2(Bucket=bucket)
        for obj in resp.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)

    elif request.param == "s3-pyarrow":
        import boto3

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

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
        resp = client.list_objects_v2(Bucket=bucket)
        for obj in resp.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)

    elif request.param == "sftp":
        import paramiko

        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

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
        # Cleanup: remove benchmark directory from SFTP server
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        _sftp_rmtree(sftp, base_path)
        sftp.close()
        transport.close()

    elif request.param == "azure":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        container = f"bench-az-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        b = AzureBackend(container=container, connection_string=AZURITE_CONN_STR)
        yield b
        b.close()
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
    """Build parametrized (backend_type, target_kind) entries for bench_target."""
    params: list[Any] = []

    # Local
    params.append(pytest.param(("local", "remote_store"), id="local-remote_store"))
    params.append(pytest.param(("local", "pathlib_raw"), id="local-pathlib_raw"))
    params.append(pytest.param(("local", "fsspec_local"), id="local-fsspec_local"))

    # S3 (MinIO)
    s3_skip = pytest.mark.skipif(not _minio_available(), reason="MinIO not reachable or s3fs not installed")
    params.append(pytest.param(("s3", "remote_store"), id="s3-minio-remote_store", marks=s3_skip))
    params.append(pytest.param(("s3", "boto3_raw"), id="s3-minio-boto3_raw", marks=s3_skip))
    params.append(pytest.param(("s3", "s3fs"), id="s3-minio-s3fs", marks=s3_skip))

    # S3-PyArrow (MinIO)
    pa_skip = pytest.mark.skipif(
        not _s3_pyarrow_available(), reason="MinIO not reachable or pyarrow/s3fs not installed"
    )
    params.append(pytest.param(("s3-pyarrow", "remote_store"), id="s3-pyarrow-minio-remote_store", marks=pa_skip))

    # SFTP
    sftp_skip = pytest.mark.skipif(
        not _sftp_docker_available(), reason="SFTP container not reachable or paramiko not installed"
    )
    params.append(pytest.param(("sftp", "remote_store"), id="sftp-docker-remote_store", marks=sftp_skip))
    params.append(pytest.param(("sftp", "paramiko_raw"), id="sftp-docker-paramiko_raw", marks=sftp_skip))
    sshfs_skip = [
        sftp_skip,
        pytest.mark.skipif(not _sshfs_available(), reason="sshfs not installed"),
    ]
    params.append(pytest.param(("sftp", "sshfs"), id="sftp-docker-sshfs", marks=sshfs_skip))

    # Azure (Azurite)
    az_skip = pytest.mark.skipif(not _azurite_available(), reason="Azurite not reachable or azure SDK not installed")
    params.append(pytest.param(("azure", "remote_store"), id="azure-azurite-remote_store", marks=az_skip))
    params.append(pytest.param(("azure", "azure_blob_raw"), id="azure-azurite-azure_blob_raw", marks=az_skip))
    adlfs_skip = [
        az_skip,
        pytest.mark.skipif(not _adlfs_available(), reason="adlfs not installed"),
    ]
    params.append(pytest.param(("azure", "adlfs"), id="azure-azurite-adlfs", marks=adlfs_skip))

    return params


@pytest.fixture(params=_build_target_params())
def bench_target(request: pytest.FixtureRequest) -> Iterator[Any]:
    """Yield a BenchTarget for comparative benchmarks.

    Each parametrization is a ``(backend_type, target_kind)`` pair.
    Test IDs look like ``test_write[s3-minio-remote_store]``.
    """
    from benchmarks.targets._remote_store import RemoteStoreTarget

    backend_type, target_kind = request.param
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

                    b = S3Backend(
                        bucket=bucket,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                        region_name="us-east-1",
                        endpoint_url=MINIO_ENDPOINT,
                    )
                else:
                    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

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

                yield S3fsTarget(
                    bucket=bucket,
                    endpoint_url=MINIO_ENDPOINT,
                    key=MINIO_ACCESS_KEY,
                    secret=MINIO_SECRET_KEY,
                )
        finally:
            # Cleanup bucket
            resp = client.list_objects_v2(Bucket=bucket)
            for obj in resp.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
            client.delete_bucket(Bucket=bucket)

    elif backend_type == "sftp":
        base_path = f"/upload/bench_tgt_{tag}"
        if target_kind == "remote_store":
            from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

            b = SFTPBackend(
                host=SFTP_HOST,
                port=SFTP_PORT,
                username=SFTP_USER,
                password=SFTP_PASS,
                base_path=base_path,
                host_key_policy=HostKeyPolicy.AUTO_ADD,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            t = RemoteStoreTarget(b)
            yield t
            t.close()
        elif target_kind == "paramiko_raw":
            from benchmarks.targets._raw_sdk import ParamikoRawTarget

            t = ParamikoRawTarget(
                host=SFTP_HOST,
                port=SFTP_PORT,
                username=SFTP_USER,
                password=SFTP_PASS,
                base_path=base_path,
            )
            yield t
            t.close()
        elif target_kind == "sshfs":
            from benchmarks.targets._fsspec import SshfsTarget

            yield SshfsTarget(
                host=SFTP_HOST,
                port=SFTP_PORT,
                username=SFTP_USER,
                password=SFTP_PASS,
                base_path=base_path,
            )
        # Cleanup SFTP directory
        import paramiko

        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        _sftp_rmtree(sftp, base_path)
        sftp.close()
        transport.close()

    elif backend_type == "azure":
        from azure.storage.blob import BlobServiceClient

        container = f"bench-tgt-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        try:
            if target_kind == "remote_store":
                from remote_store.backends._azure import AzureBackend

                b = AzureBackend(container=container, connection_string=AZURITE_CONN_STR)
                t = RemoteStoreTarget(b)
                yield t
                t.close()
            elif target_kind == "azure_blob_raw":
                from benchmarks.targets._raw_sdk import AzureBlobRawTarget

                t = AzureBlobRawTarget(container=container, connection_string=AZURITE_CONN_STR)
                yield t
                t.close()
            elif target_kind == "adlfs":
                from benchmarks.targets._fsspec import AdlfsTarget

                yield AdlfsTarget(container=container, connection_string=AZURITE_CONN_STR)
        finally:
            service.delete_container(container)
            service.close()


# ---------------------------------------------------------------------------
# Payload fixtures (various file sizes)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        pytest.param(1_024, id="1KB"),
        pytest.param(65_536, id="64KB"),
        pytest.param(1_048_576, id="1MB"),
    ]
)
def payload(request: pytest.FixtureRequest) -> bytes:
    """Return a bytes payload of the requested size."""
    return b"X" * request.param
