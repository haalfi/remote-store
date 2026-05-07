"""Backend test fixtures, registry-driven (spec 048 / TEST-004 / TEST-006).

The legacy parametrized ``backend`` fixture is replaced by a registry-
driven indirect fixture. ``pytest_generate_tests`` walks the registry
once per test that requests ``backend`` and parametrises over the active
stage's fixtures. Tests that need capability filtering should mark
themselves with::

    @pytest.mark.parametrize(
        "backend",
        fixture_params(Capability.WRITE),
        indirect=True,
    )

The hook below skips auto-parametrising whenever the test already
declares its own parametrize, so explicit markers and the auto-walk
cohabit cleanly.

The ``http_server`` and ``httpserver_listen_address`` session fixtures
remain here because the HTTP fixture's factory in
:mod:`tests.backends.fixtures.http` reads the live server from
``INFRA.http_server``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures import BackendFixture, _load_all, fixture_params
from tests.backends.fixtures._state import INFRA

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# Trigger registration. Idempotent because the registry rejects duplicate names.
_load_all()


@pytest.fixture(scope="session", autouse=True)
def _populate_infra(
    moto_server: str | None,
    minio_server: str | None,
    sftp_server: tuple[int, str] | None,
    sftp_docker_server: int | None,
    azurite_server: str | None,
    http_server: object | None,
) -> Iterator[None]:
    """Copy session infrastructure endpoints into ``INFRA``.

    Per-backend factory modules in :mod:`tests.backends.fixtures` read
    from ``INFRA`` at call time. This autouse session fixture forces the
    underlying service fixtures to start (or detect-and-skip) before any
    test setup runs, then publishes the live values into ``INFRA`` for
    the registry to consume.
    """
    INFRA.moto_url = moto_server
    INFRA.minio_url = minio_server
    if sftp_server is not None:
        INFRA.sftp_inproc_port, INFRA.sftp_inproc_host_key = sftp_server
    INFRA.sftp_docker_port = sftp_docker_server
    INFRA.azurite_conn_str = azurite_server
    INFRA.http_server = http_server
    yield
    INFRA.moto_url = None
    INFRA.minio_url = None
    INFRA.sftp_inproc_port = None
    INFRA.sftp_inproc_host_key = None
    INFRA.sftp_docker_port = None
    INFRA.azurite_conn_str = None
    INFRA.http_server = None


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


# ---------------------------------------------------------------------------
# Backend indirect fixture + auto-parametrize
# ---------------------------------------------------------------------------


def _is_already_parametrized(metafunc: pytest.Metafunc, argname: str) -> bool:
    """Return True if ``argname`` is already parametrized via a marker."""
    for marker in metafunc.definition.iter_markers("parametrize"):
        if not marker.args:
            continue
        argnames = marker.args[0]
        names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
        if argname in names:
            return True
    return False


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrise tests requesting ``backend`` / ``async_backend`` over the registry.

    Tests that already carry an explicit
    ``@pytest.mark.parametrize("backend", ...)`` (or async equivalent)
    are left alone -- the registry-walk fallback is for legacy tests
    that have not yet migrated to capability-filtered parametrize
    (TEST-005).
    """
    if "backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "backend"):
        metafunc.parametrize("backend", fixture_params(is_async=False), indirect=True)
    if "async_backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "async_backend"):
        metafunc.parametrize("async_backend", fixture_params(is_async=True), indirect=True)


@pytest.fixture
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Indirect fixture: build a Backend from a :class:`BackendFixture` record.

    Receives the registry record via ``request.param``, calls
    ``factory()`` to produce a fresh instance, yields it to the test,
    then runs ``cleanup`` on teardown.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    try:
        yield instance  # type: ignore[misc]
    finally:
        if fixture.cleanup is not None:
            fixture.cleanup(instance)


@pytest.fixture
def async_backend(request: pytest.FixtureRequest) -> Iterator[object]:
    """Indirect async fixture: build an AsyncBackend from a :class:`BackendFixture` record.

    Mirrors :func:`backend` for ``is_async=True`` registry entries.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    try:
        yield instance
    finally:
        if fixture.cleanup is not None:
            fixture.cleanup(instance)
