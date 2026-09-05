"""The Azure transport arm's message, asserted against real sockets (ERR-009, AZ-025).

The classifier's blank-message fallback is unit-tested in ``test_config.py``.
These are its *controls*: every Azure connection failure a caller can actually
provoke arrives with the driver's own explanation, so the fallback must not fire
on any of them. Without these, a fallback that overwrote real detail — the
failure mode SFTP's ``_unavailable`` docstring warns about — would pass the unit
tests unchanged.

Each case drives ``AsyncAzureBackend.check_health()``, which maps through
``_errors()`` → ``_classify`` → ``classify_azure_error``, against a loopback
socket. No Azurite, no network, no credentials: the account key below is
Azurite's published emulator key, present only so the SharedKey signer accepts
the request before it fails on the wire.

Assertions are on *non-emptiness* rather than on exact text on purpose. The
message is the driver's, and the driver's wording is not this library's to
promise: a closed loopback port was measured on Windows answering
``"Connection timeout to host …"`` — a *timeout*, because nothing refused the
connect — and the wording another platform's stack produces for the same
situation is deliberately left unpinned rather than guessed at here. What this
file pins is the property the spec states. That is also why the marker below
matters: an assertion written to survive an unknown platform is only worth
something once that platform runs it.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# These assertions are written to hold on every platform, so they are worth
# nothing unless every platform runs them. CI's default test job is Linux-only;
# the Windows and macOS legs select by this marker, not by directory. Without it
# the module docstring's own claim — that a driver's wording for an unreachable
# port differs by OS and only non-emptiness is portable — would never be
# exercised anywhere it could fail.
pytestmark = pytest.mark.os_sensitive

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from remote_store._errors import BackendUnavailable  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402
from tests.backends.fixtures._cassettes_azure import AZURITE_EMULATOR_KEY  # noqa: E402

# One second is long enough for a loopback round trip that is never coming and
# short enough that three cases stay under five seconds. ``retry_total=0`` keeps
# a failure from being paid for repeatedly.
_TIMEOUT_SECONDS = 1


def _backend(port: int) -> AsyncAzureBackend:
    """Build a backend pointed at a loopback port, with a bounded transport."""
    return AsyncAzureBackend(
        container="c",
        account_name="devstoreaccount1",
        account_url=f"http://127.0.0.1:{port}/devstoreaccount1",
        credential=AZURITE_EMULATOR_KEY,
        hns=False,
        client_options={
            "connection_timeout": _TIMEOUT_SECONDS,
            "read_timeout": _TIMEOUT_SECONDS,
            "retry_total": 0,
        },
    )


class _LoopbackServer:
    """A loopback listener that accepts connections and then misbehaves.

    ``on_accept`` decides how: closing the connection immediately (a server
    disconnect) or holding it open and sending nothing (a stall). Held
    connections are closed on teardown so ``filterwarnings = error`` does not
    turn a leaked socket into a failure elsewhere in the session.
    """

    def __init__(self, *, close_immediately: bool) -> None:
        self._close_immediately = close_immediately
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self.port: int = self._listener.getsockname()[1]
        self._accepted: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def accepted(self) -> list[socket.socket]:
        """Connections currently held open, so a caller can assert on them."""
        return list(self._accepted)

    @property
    def listener_fileno(self) -> int:
        """The listener's descriptor, or ``-1`` once it is closed."""
        return self._listener.fileno()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:  # listener closed by close()
                return
            if self._close_immediately:
                conn.close()
            else:
                self._accepted.append(conn)

    def close(self) -> None:
        self._listener.close()
        self._thread.join(timeout=5)
        for conn in self._accepted:
            conn.close()
        self._accepted.clear()


@pytest.fixture
def unreachable_port() -> int:
    """A loopback port with nothing listening on it."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port: int = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture
def disconnecting_server() -> Iterator[_LoopbackServer]:
    """A server that accepts and immediately closes."""
    server = _LoopbackServer(close_immediately=True)
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def stalling_server() -> Iterator[_LoopbackServer]:
    """A server that accepts and then sends nothing."""
    server = _LoopbackServer(close_immediately=False)
    try:
        yield server
    finally:
        server.close()


async def _health_failure(port: int) -> BackendUnavailable:
    """Drive ``check_health()`` at ``port`` and return the mapped failure."""
    backend = _backend(port)
    try:
        with pytest.raises(BackendUnavailable) as exc_info:
            await backend.check_health()
    finally:
        await backend.aclose()
    return exc_info.value


_EMPTY_MESSAGE_PREFIX = " | "
"""What ``str()`` on a ``RemoteStoreError`` opens with when its message is empty."""

_FALLBACK_MARKER = "with no detail"
"""The tail of ``_azure_common._unavailable``'s synthesised message."""


@pytest.mark.spec("AZ-025")
@pytest.mark.spec("ASYNC-079")
async def test_an_unreachable_port_keeps_the_drivers_own_words(unreachable_port: int) -> None:
    """Nothing listening: aiohttp explains the connect failure, and that survives."""
    mapped = await _health_failure(unreachable_port)

    assert not str(mapped).startswith(_EMPTY_MESSAGE_PREFIX), "unreachable port: empty message"
    assert _FALLBACK_MARKER not in str(mapped), "unreachable port: fallback overwrote the driver"
    assert mapped.backend == "async-azure"


@pytest.mark.spec("AZ-025")
@pytest.mark.spec("ASYNC-079")
async def test_a_server_that_disconnects_keeps_the_drivers_own_words(
    disconnecting_server: _LoopbackServer,
) -> None:
    """Accept-then-close: aiohttp reports a server disconnect, and that survives."""
    mapped = await _health_failure(disconnecting_server.port)

    assert not str(mapped).startswith(_EMPTY_MESSAGE_PREFIX), "server disconnect: empty message"
    assert _FALLBACK_MARKER not in str(mapped), "server disconnect: fallback overwrote the driver"
    assert mapped.backend == "async-azure"


@pytest.mark.spec("AZ-025")
@pytest.mark.spec("ASYNC-079")
async def test_a_stalled_response_keeps_the_drivers_own_words(stalling_server: _LoopbackServer) -> None:
    """Accept-and-say-nothing: the closest reachable shape to the defect, and not blank.

    ``aiohttp``'s ``ServerTimeoutError`` subclasses ``asyncio.TimeoutError``, so
    azure-core wraps it as ``ServiceResponseTimeoutError`` — the same class the
    unit test in ``test_config.py`` drives blank. The difference is the
    argument: this one carries text, so the fallback must stand aside.

    That is also why the unit test constructs its input instead of driving it.
    A blank message needs a *bare* ``asyncio.TimeoutError``; azure-core builds
    its own ``aiohttp.ClientTimeout(sock_connect=..., sock_read=...)`` per
    request, and aiohttp answers those with text. If a future aiohttp or
    azure-core starts delivering the bare shape through this path, this test
    fails and the reproduction becomes drivable end to end.
    """
    mapped = await _health_failure(stalling_server.port)

    assert not str(mapped).startswith(_EMPTY_MESSAGE_PREFIX), "stalled response: empty message"
    assert _FALLBACK_MARKER not in str(mapped), "stalled response: fallback overwrote the driver"
    assert mapped.backend == "async-azure"


def test_the_loopback_helper_closes_every_socket_it_opened() -> None:
    """The fixture's own contract: teardown leaves no socket open.

    A listener or an accepted connection that outlived its fixture would leak
    into the rest of the session, and ``filterwarnings = error`` would attribute
    the resulting ``ResourceWarning`` to whichever test the collector happened to
    be in — a failure that reads as unrelated to this file.

    Asserted on the descriptors rather than by rebinding the port. A rebind proves
    nothing: ``SO_REUSEADDR`` lets Windows bind a port that is still in use, so
    the rebind succeeds whether or not ``close()`` did anything, and comparing
    ``getsockname()`` to the port just requested cannot fail at all.
    """
    server = _LoopbackServer(close_immediately=False)
    probe = socket.socket()
    probe.settimeout(5)
    probe.connect(("127.0.0.1", server.port))

    # Wait for the accept thread to record the connection, so the assertion
    # covers a non-empty set rather than passing on a race.
    deadline = time.monotonic() + 5
    while not server.accepted and time.monotonic() < deadline:
        time.sleep(0.01)
    accepted = list(server.accepted)
    assert accepted, "the server never accepted the probe connection"

    probe.close()
    server.close()

    assert server.listener_fileno == -1, "the listener socket outlived close()"
    assert [c.fileno() for c in accepted] == [-1] * len(accepted), "an accepted connection outlived close()"
