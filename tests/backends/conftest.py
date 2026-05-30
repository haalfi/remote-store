"""Backend test infrastructure (spec 048).

Loads the fixture registry, publishes session infrastructure into
``INFRA``, and hosts the HTTP server fixture used by the registry's
``http`` factory.

Registry-driven parametrize (the auto-walk over ``fixture_params``)
lives in ``tests.backends.conformance.conftest`` rather than here.
Per-backend tests under ``tests/backends/<backend>/`` define their own
local fixtures with a ``backend`` parameter typed to their concrete
class; auto-parametrising those would multiply each test by every
registered backend, which is wrong. Confining the auto-walk to the
conformance subtree keeps both worlds working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures import _load_all
from tests.backends.fixtures._state import INFRA

if TYPE_CHECKING:
    from collections.abc import Iterator


# Trigger registration. Idempotent because the registry rejects duplicate names.
_load_all()


@pytest.fixture(scope="session", autouse=True)
def _populate_infra(
    moto_server: str | None,
    minio_server: str | None,
    sftp_server: tuple[int, str] | None,
    sftp_chroot_server: tuple[int, str] | None,
    sftp_docker_server: int | None,
    azurite_server: str | None,
    http_server: object | None,
) -> Iterator[None]:
    """Copy session infrastructure endpoints into ``INFRA``.

    Per-backend factory modules in ``tests.backends.fixtures`` read
    from ``INFRA`` at call time. This autouse session fixture forces the
    underlying service fixtures to start (or detect-and-skip) before any
    test setup runs, then publishes the live values into ``INFRA`` for
    the registry to consume.
    """
    INFRA.moto_url = moto_server
    INFRA.minio_url = minio_server
    if sftp_server is not None:
        INFRA.sftp_inproc_port, INFRA.sftp_inproc_host_key = sftp_server
    if sftp_chroot_server is not None:
        INFRA.sftp_chroot_port, INFRA.sftp_chroot_host_key = sftp_chroot_server
    INFRA.sftp_docker_port = sftp_docker_server
    INFRA.azurite_conn_str = azurite_server
    INFRA.http_server = http_server
    yield
    INFRA.moto_url = None
    INFRA.minio_url = None
    INFRA.sftp_inproc_port = None
    INFRA.sftp_inproc_host_key = None
    INFRA.sftp_chroot_port = None
    INFRA.sftp_chroot_host_key = None
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
