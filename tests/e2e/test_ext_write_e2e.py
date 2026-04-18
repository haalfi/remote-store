"""End-to-end tests for ext.write helpers across real backends.

Verifies that ``write_with_hash`` and ``open_atomic_with_hash`` return a
``WriteResult`` with the correct ``digest`` when the underlying backend is
S3, Azure, SFTP, S3-PyArrow, SQLBlob, or Memory.

Spec: EW-001..EW-004 in ``sdd/specs/046-ext-write.md``.

Requires: ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
Run with: ``pytest -m integration tests/e2e/test_ext_write_e2e.py -s``
"""

from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from remote_store import Capability
from remote_store.ext.write import open_atomic_with_hash, write_with_hash
from tests.e2e.conftest import (
    _azurite_available,
    _minio_available,
    _s3_pyarrow_available,
    _sftp_available,
)

if TYPE_CHECKING:
    from remote_store import Store

# ---------------------------------------------------------------------------
# Fixed payload — small enough to be fast, exercises the full write path.
# ---------------------------------------------------------------------------

_PAYLOAD_SIZE = 4096  # 4 KiB
_PAYLOAD: bytes = random.Random(42).randbytes(_PAYLOAD_SIZE)  # noqa: S311
_EXPECTED_SHA256: str = hashlib.sha256(_PAYLOAD).hexdigest()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@dataclass
class _CleanupEntry:
    kind: str
    extras: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def store_chain():  # -> Iterator[list[tuple[str, Store]]]
    """Yield ``(name, store)`` pairs for all available backends.

    Always includes Memory. Docker backends included when reachable.
    All infrastructure is cleaned up after the test completes.
    """
    from remote_store import Store
    from remote_store.backends._memory import MemoryBackend

    stores: list[tuple[str, Store]] = []
    cleanups: list[_CleanupEntry] = []

    stores.append(("memory", Store(backend=MemoryBackend())))

    if _minio_available():
        import boto3

        from remote_store.backends._s3 import S3Backend
        from tests.e2e.conftest import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-ew-{tag}"
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
        from tests.e2e.conftest import SFTP_HOST, SFTP_PASS, SFTP_PORT, SFTP_USER

        tag = uuid.uuid4().hex[:8]
        base_path = f"/upload/e2e-ew-{tag}"
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
        from tests.e2e.conftest import AZURITE_CONN_STR

        tag = uuid.uuid4().hex[:8]
        container = f"e2e-ew-{tag}"
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
        from tests.e2e.conftest import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-ew-pa-{tag}"
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
        cleanups.append(_CleanupEntry("s3", {"client": client, "bucket": bucket}))

    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend

        stores.append(("sql-blob", Store(backend=SQLBlobBackend(url="sqlite://"))))
    except ImportError:
        pass

    yield stores

    for _name, store in stores:
        store.close()

    for entry in cleanups:
        if entry.kind == "s3":
            from tests.e2e.conftest import _paginated_delete_s3

            _paginated_delete_s3(entry.extras["client"], entry.extras["bucket"])
            entry.extras["client"].delete_bucket(Bucket=entry.extras["bucket"])

        elif entry.kind == "sftp":
            from tests.e2e.conftest import SFTP_HOST, SFTP_PASS, SFTP_PORT, SFTP_USER, _sftp_cleanup

            _sftp_cleanup(SFTP_HOST, SFTP_PORT, SFTP_USER, entry.extras["base_path"], SFTP_PASS)

        elif entry.kind == "azure":
            entry.extras["service"].delete_container(entry.extras["container"])
            entry.extras["service"].close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("EW-001")
@pytest.mark.spec("EW-002")
class TestWriteWithHash:
    """``write_with_hash`` returns correct digest on every real backend."""

    def test_all_backends(self, store_chain: list[tuple[str, Store]]) -> None:
        """Write a known 4 KiB payload and assert digest matches pre-computed SHA-256.

        EW-002: every backend declaring WRITE is exercised — no additional
        capability beyond WRITE is required.
        """
        failures: list[str] = []
        names = [name for name, _ in store_chain]
        print(f"\n  Backends: {', '.join(names)}")  # noqa: T201

        for name, store in store_chain:
            path = f"ext-write-e2e-{uuid.uuid4().hex[:8]}.bin"
            try:
                result = write_with_hash(store, path, _PAYLOAD)
                if result.digest is None:
                    failures.append(f"{name}: digest is None")
                elif result.digest.algorithm != "sha256":
                    failures.append(f"{name}: algorithm={result.digest.algorithm!r}, want 'sha256'")
                elif result.digest.value != _EXPECTED_SHA256:
                    failures.append(
                        f"{name}: digest mismatch — got {result.digest.value[:16]}..., want {_EXPECTED_SHA256[:16]}..."
                    )
                else:
                    print(f"  {name}: OK ({result.digest.value[:16]}...)")  # noqa: T201
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: unexpected exception — {exc!r}")
            finally:
                try:
                    if store.exists(path):
                        store.delete(path)
                except Exception:  # noqa: BLE001
                    pass

        assert not failures, "write_with_hash digest failures:\n" + "\n".join(f"  {f}" for f in failures)


@pytest.mark.integration
@pytest.mark.spec("EW-003")
@pytest.mark.spec("EW-004")
class TestOpenAtomicWithHash:
    """``open_atomic_with_hash`` returns correct digest on every real backend."""

    def test_all_backends(self, store_chain: list[tuple[str, Store]]) -> None:
        """Stream-write a known 4 KiB payload and assert digest matches pre-computed SHA-256.

        EW-003: ATOMIC_WRITE is required (all current e2e backends have it).
        EW-004: ``writer.result`` is None before exit, populated after.
        """
        failures: list[str] = []
        names = [name for name, _ in store_chain]
        print(f"\n  Backends: {', '.join(names)}")  # noqa: T201

        for name, store in store_chain:
            if not store.supports(Capability.ATOMIC_WRITE):
                print(f"  {name}: skipped (no ATOMIC_WRITE)")  # noqa: T201
                continue

            path = f"ext-write-e2e-atomic-{uuid.uuid4().hex[:8]}.bin"
            try:
                with open_atomic_with_hash(store, path) as writer:
                    # EW-004: result must be None before the block exits.
                    if writer.result is not None:
                        failures.append(f"{name}: writer.result is not None before exit")
                    writer.write(_PAYLOAD)

                # EW-004: result must be populated after successful exit.
                if writer.result is None:
                    failures.append(f"{name}: writer.result is None after exit")
                elif writer.result.digest is None:
                    failures.append(f"{name}: writer.result.digest is None")
                elif writer.result.digest.algorithm != "sha256":
                    failures.append(f"{name}: algorithm={writer.result.digest.algorithm!r}, want 'sha256'")
                elif writer.result.digest.value != _EXPECTED_SHA256:
                    failures.append(
                        f"{name}: digest mismatch — got {writer.result.digest.value[:16]}..., "
                        f"want {_EXPECTED_SHA256[:16]}..."
                    )
                else:
                    print(f"  {name}: OK ({writer.result.digest.value[:16]}...)")  # noqa: T201
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: unexpected exception — {exc!r}")
            finally:
                try:
                    if store.exists(path):
                        store.delete(path)
                except Exception:  # noqa: BLE001
                    pass

        assert not failures, "open_atomic_with_hash digest failures:\n" + "\n".join(f"  {f}" for f in failures)
