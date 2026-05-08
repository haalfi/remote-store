"""``http`` fixture: ReadOnlyHttpBackend over a session pytest-httpserver.

Stage 1, real-local. The HTTP server itself is a session fixture in
``tests.backends.conftest``; ``INFRA.http_server`` carries the live
instance. Each factory call clears handlers and installs a 404
default so individual tests start with a clean slate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("http")


def _factory() -> Backend:
    if INFRA.http_server is None:
        pytest.skip("pytest-httpserver/werkzeug not installed")
    from pytest_httpserver import HTTPServer
    from werkzeug.wrappers import Response as WerkzeugResponse

    from remote_store.backends._http import ReadOnlyHttpBackend

    server = INFRA.http_server
    if not isinstance(server, HTTPServer):
        pytest.skip("http_server fixture is not an HTTPServer instance")
    server.clear()
    server.respond_nohandler = lambda request, extra_message="": WerkzeugResponse(  # type: ignore[assignment]
        b"Not Found", status=404
    )
    return ReadOnlyHttpBackend(base_url=server.url_for("/conformance/"), http_client="urllib")


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._http import ReadOnlyHttpBackend
    except ImportError:
        return frozenset()
    return frozenset(ReadOnlyHttpBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
