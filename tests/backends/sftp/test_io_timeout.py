"""SFTPBackend ``io_timeout`` channel-bound tests -- SFTP-030.

What this file pins is the half a caller cannot arm for itself. Reads on an
already-open SFTP channel are governed by ``Channel.timeout``, which paramiko
defaults to ``None`` (``paramiko/channel.py``); the four timeouts passed to
``ssh.connect()`` all bound the *connect* phase, ``channel_timeout`` included --
paramiko documents it as how long to wait for *opening* a channel. So a peer
that completes the handshake and then stops sending mid-transfer blocks
forever, and the ``_is_connection_dead`` / ``_map_exception`` recovery path --
which already matches ``TimeoutError`` and already clears the cached client --
never fires.

``io_timeout`` arms it, in ``_connect``, so every reconnect re-arms it too: a
caller doing ``unwrap(SFTPClient).get_channel().settimeout(n)`` loses the
setting on the first transparent reconnect, which is precisely when a flaky
link needs it.

The stall test drives a real paramiko client against the real in-process SFTP
server through a TCP relay that goes silent server->client on command, after
the handshake has completed. That is the fault being defended against, not a
simulation of it: the bytes really stop arriving on an open channel.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store._errors import BackendUnavailable  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


_BACKENDS: list[Backend] = []


@pytest.fixture(autouse=True)
def _close_tracked_backends() -> Iterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            backend.close()


def _make_backend(port: int, *, io_timeout: float | None = None, base_path: str = "/") -> Any:
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    kwargs: dict[str, Any] = {}
    if io_timeout is not None:
        kwargs["io_timeout"] = io_timeout
    backend = SFTPBackend(
        host="127.0.0.1",
        port=port,
        username="testuser",
        password="testpass",
        base_path=base_path,
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
        **kwargs,
    )
    _BACKENDS.append(backend)
    return backend


def _channel(backend: Any) -> Any:
    """The live SFTP channel, reached through the public escape hatch.

    ``unwrap`` connects on first use, so this doubles as "make the backend
    connect" and keeps the assertions off private attributes.
    """
    import paramiko

    return backend.unwrap(paramiko.SFTPClient).get_channel()


def _channel_timeout(backend: Any) -> float | None:
    return _channel(backend).gettimeout()


class _StallRelay:
    """TCP relay to *target_port* that can be told to stop delivering to the client.

    ``stall()`` makes the server->client pump discard everything it reads
    instead of forwarding it, while leaving both sockets open. The client is
    left waiting on a channel that will never produce another byte -- a silent
    peer, not a closed one, so the failure is a read timeout rather than EOF.
    """

    def __init__(self, target_port: int) -> None:
        self._target_port = target_port
        self._stalled = threading.Event()
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._threads: list[threading.Thread] = []
        self._socks: list[socket.socket] = []

    @property
    def port(self) -> int:
        return int(self._listener.getsockname()[1])

    def start(self) -> None:
        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()
        self._threads.append(thread)

    def stall(self) -> None:
        self._stalled.set()

    def resume(self) -> None:
        """Deliver again, so a reconnect through this relay can succeed."""
        self._stalled.clear()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            try:
                upstream = socket.create_connection(("127.0.0.1", self._target_port))
            except OSError:
                client.close()
                continue
            self._socks.extend((client, upstream))
            for src, dst, drop_when_stalled in (
                (client, upstream, False),
                (upstream, client, True),
            ):
                thread = threading.Thread(target=self._pump, args=(src, dst, drop_when_stalled), daemon=True)
                thread.start()
                self._threads.append(thread)

    def _pump(self, src: socket.socket, dst: socket.socket, drop_when_stalled: bool) -> None:
        while not self._stop.is_set():
            try:
                chunk = src.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            if drop_when_stalled and self._stalled.is_set():
                # Keep draining the server so it never blocks on a full buffer,
                # but deliver nothing: the client's channel simply goes quiet.
                continue
            try:
                dst.sendall(chunk)
            except OSError:
                return

    def stop(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        for sock in self._socks:
            with contextlib.suppress(OSError):
                sock.close()


@pytest.fixture
def stall_relay(sftp_server: tuple[int, str] | None) -> Iterator[_StallRelay]:
    if sftp_server is None:
        pytest.skip("paramiko not installed (in-process SFTP server unavailable)")
    relay = _StallRelay(sftp_server[0])
    relay.start()
    yield relay
    relay.stop()


@pytest.mark.spec("SFTP-005")
@pytest.mark.parametrize("bad", [0, 0.0, -1, -0.5])
def test_non_positive_io_timeout_rejected(bad: float) -> None:
    """Zero would read as non-blocking to paramiko, failing every read at once."""
    from remote_store.backends._sftp import SFTPBackend

    with pytest.raises(ValueError, match="io_timeout"):
        SFTPBackend(host="example.com", io_timeout=bad)


@pytest.mark.spec("SFTP-030")
def test_default_leaves_channel_unbounded(sftp_server: tuple[int, str] | None) -> None:
    """Default is ``None``: no bound is armed, so no existing caller changes behaviour."""
    if sftp_server is None:
        pytest.skip("paramiko not installed")
    backend = _make_backend(sftp_server[0])
    assert _channel_timeout(backend) is None


@pytest.mark.spec("SFTP-030")
def test_io_timeout_armed_on_channel(sftp_server: tuple[int, str] | None) -> None:
    """A configured ``io_timeout`` reaches the live channel, not just the constructor."""
    if sftp_server is None:
        pytest.skip("paramiko not installed")
    backend = _make_backend(sftp_server[0], io_timeout=7.5)
    assert _channel_timeout(backend) == pytest.approx(7.5)


@pytest.mark.spec("SFTP-030")
def test_stall_recovers_and_rearms_the_bound(stall_relay: _StallRelay) -> None:
    """After a real stall, the backend reconnects *and* the new channel is bounded.

    Both halves matter and neither implies the other. Recovery is the existing
    contract: a stall must leave the backend reusable rather than wedged on a
    dead channel. Re-arming is what a caller cannot arrange from outside — the
    reconnect builds a fresh channel that paramiko initialises to ``None``, so
    a ``settimeout()`` applied through ``unwrap`` would evaporate here, exactly
    when a flaky link needs it most.

    The reconnect is driven by an actual stall rather than by clearing the
    cached client by hand, so what is asserted is the path a dropped link takes.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"stalled_{uuid.uuid4().hex[:8]}.bin"
    payload = b"z" * (256 * 1024)
    backend.write(name, payload)
    first = _channel(backend)

    stall_relay.stall()
    with pytest.raises(BackendUnavailable):
        backend.read_bytes(name)

    stall_relay.resume()
    # The next operation must reconnect on its own; no reset call in between.
    assert backend.read_bytes(name) == payload

    second = _channel(backend)
    assert second is not first, "expected a fresh channel after the reconnect"
    assert second.gettimeout() == pytest.approx(io_timeout)


@pytest.mark.spec("SFTP-030")
def test_stalled_peer_raises_backend_unavailable(stall_relay: _StallRelay) -> None:
    """A peer that goes silent mid-transfer fails within the bound instead of hanging.

    Without ``io_timeout`` this read blocks indefinitely; the assertion on
    elapsed time is what distinguishes "raised" from "eventually gave up".
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"stalled_{uuid.uuid4().hex[:8]}.bin"
    payload = b"x" * (256 * 1024)
    backend.write(name, payload)

    # Handshake, auth and channel open have all completed by now; only then
    # does the peer go quiet, so what is bounded here is a read on an
    # already-open channel.
    stall_relay.stall()

    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        # read_bytes, not read: this must pull the payload over the wire, so
        # the failure lands mid-transfer rather than on the open.
        backend.read_bytes(name)
    elapsed = time.monotonic() - start

    # Generous headroom over io_timeout: the point is that it returns at all,
    # bounded by the timeout rather than by the test runner losing patience.
    assert elapsed < io_timeout + 30, f"read took {elapsed:.1f}s; expected ~{io_timeout}s"
