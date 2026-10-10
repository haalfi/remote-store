"""Regression for the session ``moto_server`` fixture's bind (BUG-315).

The fixture used to choose a free port, release it, and let moto bind it later.
On Windows, werkzeug's ``SO_REUSEADDR`` let a second server share a port that
was already in use; and when a bind failed, ``ThreadedMotoServer.start()``
waited forever on a ready event that only a successful bind sets, hanging the
xdist worker. ``_start_moto_server`` in ``tests/conftest.py`` now binds port 0
on loopback in the caller's thread, so the port is chosen by that one bind and a
failed bind raises in the fixture.
"""

from __future__ import annotations

import threading
import urllib.request

import pytest

from tests.conftest import _start_moto_server

pytest.importorskip("moto")

pytestmark = pytest.mark.os_sensitive

# TEST-NET-3 (RFC 5737): no host owns it, so binding it fails on every OS.
_UNASSIGNABLE_HOST = "203.0.113.1"


def test_failed_bind_raises_instead_of_hanging() -> None:
    """A bind the OS refuses surfaces as ``OSError`` within a bound, not a hang."""
    outcome: list[BaseException | None] = []

    def attempt() -> None:
        try:
            _start_moto_server(host=_UNASSIGNABLE_HOST)
        except BaseException as exc:  # noqa: BLE001 -- recorded for the assertion below
            outcome.append(exc)
        else:
            outcome.append(None)

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive(), "start blocked on a failed bind instead of raising"
    assert len(outcome) == 1
    assert isinstance(outcome[0], OSError), f"expected OSError, got {outcome[0]!r}"
    assert _UNASSIGNABLE_HOST in str(outcome[0])
    assert isinstance(outcome[0].__cause__, OSError), "the bind's own error must stay attached"


def test_two_servers_bind_distinct_loopback_ports_and_serve() -> None:
    """Each start binds its own loopback port and answers S3 requests on it.

    Moto keeps its S3 state per process, so two servers started here share
    buckets; the isolation the fixture needs is between xdist worker processes,
    which a distinct port per server gives.
    """
    first, first_thread = _start_moto_server()
    second, second_thread = _start_moto_server()
    try:
        assert first.server_address[0] == "127.0.0.1"
        assert second.server_address[0] == "127.0.0.1"
        assert first.server_port != second.server_port

        bucket = "bug-315-serves"
        put = urllib.request.Request(f"http://127.0.0.1:{first.server_port}/{bucket}", method="PUT")
        with urllib.request.urlopen(put, timeout=10) as response:
            assert response.status == 200
        head = urllib.request.Request(f"http://127.0.0.1:{second.server_port}/{bucket}", method="HEAD")
        with urllib.request.urlopen(head, timeout=10) as response:
            assert response.status == 200
    finally:
        for server, thread in ((first, first_thread), (second, second_thread)):
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
