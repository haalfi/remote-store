"""Shared test fixtures and marker registration."""

from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, settings

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Shared availability / reachability helpers
# Used by fixtures in this file (moto_server, azurite_server, sftp_server)
# and imported directly by tests/backends/test_azure.py and
# tests/aio/test_sync_adapter_conformance.py. tests/backends/conftest.py
# retains its own copies of _s3_available, _azure_available,
# _azurite_reachable, _minio_reachable, and _sftp_available to stay
# self-contained — a subdirectory conftest importing from a parent conftest
# is an upward import that creates the same cross-boundary problem in reverse.
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _s3_available() -> bool:
    try:
        import moto  # noqa: F401
        import s3fs  # noqa: F401

        return True
    except ImportError:
        return False


def _azure_available() -> bool:
    try:
        import azure.storage.filedatalake  # noqa: F401

        return True
    except ImportError:
        return False


def _sftp_available() -> bool:
    try:
        import paramiko  # noqa: F401

        return True
    except ImportError:
        return False


def _azurite_reachable() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 10000), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def _minio_reachable() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 9000), timeout=1)
        s.close()
        return True
    except OSError:
        return False


_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)


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
def minio_server() -> Iterator[str | None]:
    """Provide MinIO endpoint URL if reachable on 127.0.0.1:9000."""
    if _minio_reachable():
        yield "http://127.0.0.1:9000"
    else:
        yield None


@pytest.fixture(scope="session")
def azurite_server() -> Iterator[str | None]:
    """Provide Azurite connection string if available."""
    if not _azure_available() or not _azurite_reachable():
        yield None
        return
    yield _AZURITE_CONN_STR


@pytest.fixture(scope="session")
def sftp_server() -> Iterator[tuple[int, str] | None]:
    """Start an in-process SFTP server for the test session."""
    if not _sftp_available():
        yield None
        return

    import shutil
    import tempfile

    from tests.backends.sftp_server import start_sftp_server, stop_sftp_server

    tmpdir = tempfile.mkdtemp(prefix="sftp_test_")
    thread, port, host_key, stop_event, server_socket = start_sftp_server(root=tmpdir, host="127.0.0.1")

    key_type = host_key.get_name()
    key_b64 = host_key.get_base64()
    host_key_entry = f"[127.0.0.1]:{port} {key_type} {key_b64}"

    yield port, host_key_entry

    stop_sftp_server(thread, stop_event, server_socket)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True, scope="session")
def _close_leaked_event_loops() -> Iterator[None]:
    """Close any phantom event loops leaked by pytest-asyncio at session teardown.

    pytest-asyncio 1.3 on Python 3.11 calls ``asyncio.get_event_loop()`` when
    setting up each async test.  Python 3.11 auto-creates a new loop when none
    is set (backward-compat behaviour) and stores it in the thread-local policy.
    pytest-asyncio saves this phantom loop as ``old_loop`` and restores it as
    the policy default after every async test's teardown.  When a subsequent
    sync test calls ``asyncio.run()`` the phantom loop is orphaned: asyncio.run
    replaces the policy default and then sets it to ``None`` without closing the
    old one.  The loop's internal cyclic reference (``_read_from_self`` bound
    method ↔ Handle) keeps it alive as cyclic garbage until the GC runs at
    session teardown, where ``BaseEventLoop.__del__`` emits ``ResourceWarning``.
    pytest turns that into ``PytestUnraisableExceptionWarning``; with
    ``filterwarnings = error`` the session fails even though every test passed.

    Closing all unclosed, non-running event loops here — before pytest's
    ``gc_collect_harder()`` runs — prevents the warning.  Session fixtures
    finalise before ``config._ensure_unconfigure()`` (which hosts
    ``gc_collect_harder()``), so the timing guarantee holds.  The sweep is
    intentionally broad: at session teardown, any unclosed non-running loop is
    garbage regardless of origin.  Regression coverage for this fixture is
    whole-suite: the combination of ``tests/aio/test_sync_adapter.py`` async
    tests followed by ``tests/test_snippets.py::TestAsyncSyncBridgesSnippets``
    (a sync test that calls ``asyncio.run()``) reproduces the leak on Python
    3.11 without this fixture.

    Ref: ID-158.
    """
    import asyncio
    import gc

    yield
    for obj in gc.get_objects():
        try:
            if isinstance(obj, asyncio.AbstractEventLoop) and not obj.is_running() and not obj.is_closed():
                obj.close()
        except Exception:  # noqa: BLE001
            pass


# -- Hypothesis profiles (dev=50, ci=100, nightly=1000) --
# Activate via HYPOTHESIS_PROFILE env var (e.g. HYPOTHESIS_PROFILE=ci).
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("nightly", max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_configure(config: object) -> None:
    """Register custom markers."""
    if os.environ.get("RS_REQUIRE_MINIO") == "1" and not _minio_reachable():
        pytest.exit(
            "RS_REQUIRE_MINIO=1 but MinIO is not reachable at 127.0.0.1:9000",
            returncode=1,
        )
    if isinstance(config, pytest.Config):
        config.addinivalue_line("markers", "spec(id): links test to a spec section ID")
        config.addinivalue_line("markers", "integration: requires external services")
        config.addinivalue_line("markers", "requires_docker: test needs Docker services (e.g. Azurite)")
        config.addinivalue_line(
            "markers",
            "os_sensitive: exercises OS-specific behaviour (paths, atomic writes, local filesystem); "
            "run on macOS and Windows CI",
        )
        config.addinivalue_line("markers", "pbt: property-based test using Hypothesis")


# region: shared fixtures


@pytest.fixture
def mem_backend() -> MemoryBackend:
    """Fresh MemoryBackend instance."""
    return MemoryBackend()


@pytest.fixture
def mem_store() -> Store:
    """Store backed by a fresh MemoryBackend with no root_path."""
    return Store(backend=MemoryBackend())


# endregion


# region: shared test helpers


class RestrictedBackend:
    """Backend wrapper that removes specific capabilities for testing.

    Delegates all methods to the inner MemoryBackend but overrides the
    ``capabilities`` property to return a restricted ``CapabilitySet``.
    """

    def __init__(self, backend: MemoryBackend, exclude: set[Capability]) -> None:
        self._inner = backend
        self._caps = CapabilitySet(set(Capability) - exclude)

    @property
    def capabilities(self) -> CapabilitySet:
        return self._caps

    @property
    def name(self) -> str:
        return self._inner.name

    def __getattr__(self, item: str) -> object:
        return getattr(self._inner, item)


def make_restricted_store(exclude: set[Capability]) -> Store:
    """Create a Store whose backend lacks the given capabilities."""
    backend = MemoryBackend()
    backend.write("test.txt", b"hello")
    backend.write("folder/a.txt", b"data")
    restricted = RestrictedBackend(backend, exclude)
    return Store(backend=restricted, root_path="")  # type: ignore[arg-type]


# endregion
