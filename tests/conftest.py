"""Shared test fixtures and marker registration."""

from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, settings

from infra._settings import (
    AZURITE_HOST,
    AZURITE_PORT,
    MINIO_ENDPOINT,
    MINIO_HOST,
    MINIO_PORT,
    SFTP_PORT,
)
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from tests.backends.fixtures._loader import VALID_STAGES
from tests.backends.fixtures._state import set_current_stage

if TYPE_CHECKING:
    from collections.abc import Iterator


def _maybe_load_dotenv_for_live(config: pytest.Config) -> None:
    """Load the project ``.env`` when a ``live`` marker selection is in play.

    Live-marked tests carry module-level ``skipif`` gates (e.g.
    ``RS_TEST_LIVE_HNS != "1"``) that fire at collection time, before any
    fixture body runs. If the gating env var sits in ``.env`` and is not
    exported by the shell, a fixture-local ``load_dotenv`` arrives too
    late and the test silently skips — the doc contract "drop the gate
    var into ``.env`` once" would not hold. Loading ``.env`` from
    ``pytest_configure`` (before collection) closes that gap.

    The load is conditional on the mark expression so a regular
    ``hatch run test`` (default ``addopts`` ``-m 'not live'``) does not
    pull credentials into its environment. ``override=False`` keeps any
    value already set in the shell or by CI authoritative.
    """
    # Pass an explicit default so that programmatic invocations or
    # plugin-phase ordering where ``-m`` has not yet been registered
    # don't raise ``ValueError`` from ``getoption``. In a normal
    # ``hatch run pytest`` flow this never fires.
    markexpr = (config.getoption("-m", default="") or "").strip()
    # Tokenize on whitespace and parens, then look for ``live`` used as
    # an inclusion (i.e. not preceded by ``not``). Catches ``live``,
    # ``live or extended_conformance``, ``foo and live``; rejects
    # ``not live`` (the default).
    tokens = markexpr.replace("(", " ").replace(")", " ").split()
    is_live_inclusion = any(t == "live" and (i == 0 or tokens[i - 1] != "not") for i, t in enumerate(tokens))
    if is_live_inclusion:
        from dotenv import load_dotenv  # noqa: PLC0415 -- intentional lazy import

        load_dotenv(override=False)


# ---------------------------------------------------------------------------
# Shared availability / reachability helpers
# Used by the session fixtures in this file (moto_server, azurite_server,
# sftp_server). tests/backends/conftest.py retains its own copies of
# _s3_available, _azure_available, _azurite_reachable, _minio_reachable,
# and _sftp_available to stay self-contained — a subdirectory conftest
# importing from a parent conftest is an upward import that creates the
# same cross-boundary problem in reverse.
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


# Container reachability is a function of one fact per ``[fixture.<x>].container``
# value: which TCP port the container exposes on 127.0.0.1. Centralising
# the port mapping here means a new container value in ``fixtures.toml``
# only needs one entry added below; the per-helper boilerplate (one
# function each for minio/azurite/sftp) is gone.
_CONTAINER_PORTS: dict[str, int] = {
    "minio": MINIO_PORT,
    "azurite": AZURITE_PORT,
    "sftp": SFTP_PORT,
}


def _container_reachable(name: str) -> bool:
    """Return True when the container with the given ``container`` value
    is listening on its known port at 127.0.0.1.

    ``name`` is one of the values from ``VALID_CONTAINERS`` in the
    fixture loader (excluding ``"none"``). Unknown names raise
    ``KeyError`` so a typo at the call site fails loud.
    """
    port = _CONTAINER_PORTS[name]
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
    except OSError:
        return False
    s.close()
    return True


def _azurite_reachable() -> bool:
    return _container_reachable("azurite")


def _minio_reachable() -> bool:
    return _container_reachable("minio")


def _sftp_docker_reachable() -> bool:
    return _container_reachable("sftp")


_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
    f"QueueEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT + 1}/devstoreaccount1;"
    f"TableEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT + 2}/devstoreaccount1;"
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
    """Provide MinIO endpoint URL if reachable on the configured host port."""
    if _minio_reachable():
        yield MINIO_ENDPOINT
    else:
        yield None


@pytest.fixture(scope="session")
def sftp_docker_server() -> Iterator[int | None]:
    """Provide the Dockerised SFTP server port if reachable on the configured host port.

    The container is the ``atmoz/sftp:alpine`` service published on
    ``SFTP_HOST_PORT`` (from ``infra/.env``) by
    ``infra/docker-compose.yml`` and the CI ``test`` job. When
    unreachable, fixtures depending on this yield ``None`` and skip via
    factory-level ``pytest.skip(...)`` per spec 048 / TEST-006.
    """
    if _sftp_docker_reachable():
        yield SFTP_PORT
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

    from tests.backends.sftp._helpers import start_sftp_server, stop_sftp_server

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


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--stage=N`` and ``--record`` CLI options (spec 048).

    ``--stage=N`` selects which fixture tier participates in the session.
    Each stage includes all lower stages, so ``--stage=2`` runs Stage 1
    plus Stage 2. Default is auto-detected: Stage 2 when a Docker daemon
    is reachable, Stage 1 otherwise. Stage 3 (live cloud) is never
    implicit; it requires per-backend env vars on top of the explicit
    flag.

    The ``RS_TEST_STAGE`` env var (1, 2, or 3) overrides auto-detection
    without requiring the explicit flag. Useful on developer machines
    where Docker is installed but the daemon is paused or slow: the
    ``docker info`` probe takes up to 5 s before falling back to Stage 1
    on every invocation; the env var short-circuits the probe.

    ``--record`` maps to ``--record-mode=rewrite`` for pytest-recording /
    vcrpy: it deletes any existing cassette for each vcr-marked test and
    records fresh traffic. Use with ``--stage=3`` to refresh cassettes
    from live backends. On Windows, also pass
    ``--allowed-hosts=127.0.0.1,::1,localhost`` when ``--block-network``
    is active to avoid blocking the ProactorEventLoop self-pipe.
    """
    parser.addoption(
        "--stage",
        action="store",
        type=int,
        choices=sorted(VALID_STAGES),
        default=None,
        help="Test stage: 1 (repo-only), 2 (Docker), 3 (live cloud). "
        "Default: auto-detect (2 if Docker reachable, else 1). "
        "Override via RS_TEST_STAGE env var to skip the docker info probe.",
    )
    parser.addoption(
        "--record",
        action="store_true",
        default=False,
        help="Record cassettes from live backends (maps to --record-mode=rewrite). "
        "Use with --stage=3 and the relevant RS_TEST_LIVE_* env vars.",
    )


def _docker_daemon_reachable() -> bool:
    """Return True when ``docker info`` succeeds within a 5-second budget.

    Used by stage auto-detection. We probe the daemon directly rather
    than relying on a specific service port (Azurite, MinIO, ...) because
    those can be stopped while the daemon is still up; a developer with
    Docker available should default to Stage 2 even before starting any
    container.
    """
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            ["docker", "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def pytest_configure(config: object) -> None:
    """Register custom markers and set the active stage."""
    if os.environ.get("RS_REQUIRE_MINIO") == "1" and not _minio_reachable():
        pytest.exit(
            f"RS_REQUIRE_MINIO=1 but MinIO is not reachable at {MINIO_HOST}:{MINIO_PORT}",
            returncode=1,
        )
    if isinstance(config, pytest.Config):
        _maybe_load_dotenv_for_live(config)
        if config.getoption("--record", default=False):
            import importlib.util  # noqa: PLC0415

            if importlib.util.find_spec("pytest_recording") is None:
                pytest.exit(
                    "--record requires pytest-recording; run: uv pip install --python .venv pytest-recording",
                    returncode=1,
                )
            # Map --record to --record-mode=rewrite for pytest-recording.
            # The record_mode session fixture reads config.option.record_mode.
            config.option.record_mode = "rewrite"
            # Signal to async live fixtures to use AsyncioRequestsTransport so
            # vcrpy captures streaming response bodies (aiohttp drops them).
            os.environ["_RS_CASSETTE_RECORDING"] = "1"
        stage = config.getoption("--stage")
        if stage is None:
            env_override = os.environ.get("RS_TEST_STAGE")
            if env_override is not None:
                try:
                    stage = int(env_override)
                except ValueError:
                    pytest.exit(
                        f"RS_TEST_STAGE must be one of {sorted(VALID_STAGES)} (got {env_override!r})",
                        returncode=1,
                    )
                if stage not in VALID_STAGES:
                    pytest.exit(
                        f"RS_TEST_STAGE must be one of {sorted(VALID_STAGES)} (got {stage})",
                        returncode=1,
                    )
            else:
                stage = 2 if _docker_daemon_reachable() else 1
        set_current_stage(stage)
        config.addinivalue_line("markers", "spec(id): links test to a spec section ID")
        config.addinivalue_line("markers", "integration: requires external services")
        config.addinivalue_line("markers", "requires_docker: test needs Docker services (e.g. Azurite)")
        config.addinivalue_line(
            "markers",
            "os_sensitive: exercises OS-specific behaviour (paths, atomic writes, local filesystem); "
            "run on macOS and Windows CI",
        )
        config.addinivalue_line("markers", "pbt: property-based test using Hypothesis")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Add ``pytest.mark.vcr`` to azure_live items when ``--record`` is active.

    The static ``marks`` tuple on the ``azure_live`` / ``azure_live_async``
    ``BackendFixture`` carries only ``pytest.mark.live``. Adding ``vcr``
    statically would engage vcrpy in ``record_mode='none'`` for plain
    ``-m live --stage=3`` sessions (without ``--record``), blocking real HTTP
    with vcrpy's request interceptor. This hook attaches the mark dynamically
    so the cassette layer only activates during explicit recording sessions.
    """
    if not config.getoption("--record", default=False):
        return
    for item in items:
        if "azure_live" in item.name:
            item.add_marker(pytest.mark.vcr)


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
