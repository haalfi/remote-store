"""SFTPBackend ``io_timeout`` channel-bound tests — SFTP-030.

What this file pins is the half a caller cannot arm for itself. Reads on an
already-open SFTP channel are governed by ``Channel.timeout``, which paramiko
defaults to ``None`` (``paramiko/channel.py``); the four timeouts passed to
``ssh.connect()`` all bound the *connect* phase, ``channel_timeout`` included —
paramiko documents it as how long to wait for *opening* a channel. So a peer
that completes the handshake and then stops sending mid-transfer blocks
forever, and the ``_is_connection_dead`` / ``_map_exception`` recovery path —
which already matches ``TimeoutError`` and already clears the cached client —
never fires.

``io_timeout`` arms it, in ``_connect``, so every reconnect re-arms it too: a
caller doing ``unwrap(SFTPClient).get_channel().settimeout(n)`` loses the
setting on the first transparent reconnect, which is precisely when a flaky
link needs it.

Three faults are covered, because they fail by different mechanisms and none
implies the others:

- **A silent peer mid-transfer** (server→client), driven through a TCP relay
  that stops delivering on command once the handshake is done. The bytes really
  stop arriving on an open channel; this is the fault, not a simulation of it.
- **A stalled upload** (client→server), which reaches the bound through SSH
  window exhaustion in ``Channel.sendall`` rather than through an empty receive
  pipe, so it is not equivalent to the read case by inspection.
- **A peer that never completes the SFTP version exchange**, which happens
  *inside* the client construction that opens the channel. That window sits
  before any caller-visible operation and is re-entered on every reconnect, so
  a bound armed after it would leave the headline guarantee unarmed exactly
  when a half-alive peer needs it.
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


def _drain(stream: Any) -> None:
    """Read *stream* to exhaustion, discarding what it yields."""
    while stream.read(64 * 1024):
        pass


class _StallRelay:
    """TCP relay to *target_port* that can be told to stop delivering, per direction.

    Both directions stall by the same means — the pump keeps reading its source
    and discards instead of forwarding — while leaving every socket open. What
    differs is the fault that produces, and the two are not interchangeable:

    - ``stall_download()`` silences server→client. The client waits on a channel
      that will never produce another byte: a silent peer, not a closed one, so
      the failure is a read timeout rather than EOF.
    - ``stall_upload()`` silences client→server. The server never sees the data,
      so it never sends the window adjustments that let the client keep writing;
      the client's SSH window drains and ``Channel.sendall`` blocks. That is
      window exhaustion, not an empty receive pipe, which is why the write half
      of the bound needs its own test rather than being taken on symmetry.
    """

    def __init__(self, target_port: int) -> None:
        self._target_port = target_port
        self._stall_down = threading.Event()
        self._stall_up = threading.Event()
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

    def stall_download(self) -> None:
        self._stall_down.set()

    def stall_upload(self) -> None:
        self._stall_up.set()

    def resume(self) -> None:
        """Deliver again, so a reconnect through this relay can succeed."""
        self._stall_down.clear()
        self._stall_up.clear()

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
            for src, dst, gate in (
                (client, upstream, self._stall_up),
                (upstream, client, self._stall_down),
            ):
                thread = threading.Thread(target=self._pump, args=(src, dst, gate), daemon=True)
                thread.start()
                self._threads.append(thread)

    def _pump(self, src: socket.socket, dst: socket.socket, gate: threading.Event) -> None:
        while not self._stop.is_set():
            try:
                chunk = src.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            if gate.is_set():
                # Keep draining the source so it never blocks on a full socket
                # buffer, but deliver nothing: the far side simply goes quiet.
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


class _MuteSubsystemServer:
    """SSH server that accepts everything and then never speaks SFTP.

    Auth succeeds, the session channel opens, and the ``sftp`` subsystem request
    is accepted — but no subsystem handler is registered, so the server never
    sends its SFTP ``VERSION``. The client's version exchange, which runs inside
    ``SFTPClient.__init__``, waits on a reply that never comes.

    This is the fault the relay cannot stage: it happens while the client is
    being constructed, before any caller-visible operation, so there is no
    moment in the test to flip a switch. Accepting-then-going-mute is a real
    server posture (a subsystem that dies on spawn looks exactly like this),
    not a contrivance to reach the code path.
    """

    def __init__(self) -> None:
        import paramiko

        self._paramiko = paramiko
        self._host_key = paramiko.RSAKey.generate(2048)
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._transports: list[Any] = []

    @property
    def port(self) -> int:
        return int(self._listener.getsockname()[1])

    def _interface(self) -> Any:
        paramiko = self._paramiko

        class _Mute(paramiko.ServerInterface):
            def check_auth_password(self, username: str, password: str) -> int:
                return paramiko.AUTH_SUCCESSFUL

            def check_auth_publickey(self, username: str, key: Any) -> int:
                return paramiko.AUTH_SUCCESSFUL

            def get_allowed_auths(self, username: str) -> str:
                return "password,publickey"

            def check_channel_request(self, kind: str, chanid: int) -> int:
                return paramiko.OPEN_SUCCEEDED

            def check_channel_subsystem_request(self, channel: Any, name: str) -> bool:
                # Accept, and register no handler: the channel is open and the
                # server is mute from here on.
                return True

        return _Mute()

    def start(self) -> None:
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        self._listener.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except (TimeoutError, OSError):
                continue
            transport = self._paramiko.Transport(conn)
            transport.add_server_key(self._host_key)
            self._transports.append(transport)
            with contextlib.suppress(Exception):
                transport.start_server(server=self._interface())

    def stop(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        for transport in self._transports:
            with contextlib.suppress(Exception):
                transport.close()


@pytest.fixture
def mute_server() -> Iterator[_MuteSubsystemServer]:
    server = _MuteSubsystemServer()
    server.start()
    yield server
    server.stop()


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

    stall_relay.stall_download()
    with pytest.raises(BackendUnavailable):
        backend.read_bytes(name)

    stall_relay.resume()
    # The next operation must reconnect on its own; no reset call in between.
    assert backend.read_bytes(name) == payload

    second = _channel(backend)
    assert second is not first, "expected a fresh channel after the reconnect"
    assert second.gettimeout() == pytest.approx(io_timeout)


@pytest.mark.spec("SFTP-030")
def test_version_exchange_is_bounded(mute_server: _MuteSubsystemServer) -> None:
    """A peer that opens the channel and never speaks SFTP fails within the bound.

    The SFTP version exchange runs inside ``SFTPClient.__init__`` — after the
    channel is open, so the connect-phase ``channel_timeout`` is already spent,
    and before any caller-visible operation, so nothing later can rescue it.
    A bound armed only once the client exists leaves this window unbounded, and
    because every reconnect re-runs it, a half-alive peer would park the caller
    indefinitely *with* ``io_timeout`` set — the guarantee the option is bought
    for, missing exactly where it was promised.
    """
    io_timeout = 2.0
    backend = _make_backend(mute_server.port, io_timeout=io_timeout)

    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.check_health()
    elapsed = time.monotonic() - start
    assert elapsed < io_timeout * 3, f"connect took {elapsed:.1f}s; expected ~{io_timeout}s"


@pytest.mark.spec("SFTP-030")
def test_version_exchange_unbounded_without_io_timeout(
    mute_server: _MuteSubsystemServer,
) -> None:
    """The default really is unbounded here, so the test above is not vacuous.

    A positive control: without ``io_timeout`` the same mute peer does not fail
    within the window the bounded case returns in. Without this, a connect that
    happened to fail for an unrelated reason would make the bounded assertion
    pass while proving nothing.
    """
    backend = _make_backend(mute_server.port)
    done = threading.Event()

    def _probe() -> None:
        with contextlib.suppress(Exception):
            backend.check_health()
        done.set()

    threading.Thread(target=_probe, daemon=True).start()
    assert not done.wait(timeout=8.0), "expected the unbounded default to still be blocked"


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
    stall_relay.stall_download()

    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        # read_bytes, not read: this must pull the payload over the wire, so
        # the failure lands mid-transfer rather than on the open.
        backend.read_bytes(name)
    elapsed = time.monotonic() - start

    # Tied to the bound, not merely to the runner's patience: a band wide
    # enough to admit any bound would make the assertion vacuous, since the
    # pytest.raises above already catches an outright hang. 3x leaves room for
    # a loaded runner while still failing a bound armed at the wrong value, a
    # TCP-level give-up, or a classification path that re-pays the timeout.
    assert elapsed < io_timeout * 3, f"read took {elapsed:.1f}s; expected ~{io_timeout}s"


@pytest.mark.spec("SFTP-030")
def test_stalled_upload_raises_backend_unavailable(stall_relay: _StallRelay) -> None:
    """The bound covers writes, which reach it by a different mechanism than reads.

    A read stalls on an empty receive pipe; a write stalls because the server
    never acknowledges data, so the SSH window drains and ``Channel.sendall``
    blocks. Paramiko bounds each ``send`` inside ``sendall`` rather than the
    call as a whole, so the two cases are not equivalent by inspection and the
    "covers writes as well as reads" claim needs its own evidence.

    The payload exceeds paramiko's default 2 MiB window so the send is forced
    to block rather than fitting entirely into it.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    backend.check_health()  # connect while the relay is still delivering

    stall_relay.stall_upload()
    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.write(f"upload_{uuid.uuid4().hex[:8]}.bin", b"w" * (8 * 1024 * 1024))
    elapsed = time.monotonic() - start
    assert elapsed < io_timeout * 6, f"write took {elapsed:.1f}s; expected ~{io_timeout}s"


@pytest.mark.spec("SFTP-030")
def test_streaming_read_raises_rather_than_truncating(stall_relay: _StallRelay) -> None:
    """A stall part-way through a stream raises; it never returns a short read.

    This is the case the whole retry-exclusion rationale is argued from — a
    caller that has *already consumed bytes* when the peer goes quiet. It is
    also the one where silence would be worst: a truncated stream that returned
    cleanly would be indistinguishable from a complete one, and the caller would
    persist a partial file believing it whole.

    ``read_bytes`` cannot cover this. It is all-or-nothing, so no caller can
    observe a partial result from it.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"streamed_{uuid.uuid4().hex[:8]}.bin"
    payload = bytes(range(256)) * 4096  # 1 MiB, non-uniform so a prefix is meaningful
    backend.write(name, payload)

    with backend.read(name) as stream:
        first = stream.read(64 * 1024)
        assert first, "expected the stream to deliver bytes before the stall"

        stall_relay.stall_download()
        # Draining to the end must raise rather than return what it has.
        with pytest.raises(BackendUnavailable):
            _drain(stream)

    # What arrived before the stall is a valid prefix, not corrupt or reordered.
    assert payload.startswith(first)
