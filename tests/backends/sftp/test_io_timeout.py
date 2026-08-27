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

- **A silent peer** (server→client), driven through a TCP relay that stops
  delivering on command once the handshake is done. The bytes really stop
  arriving on an open channel; this is the fault, not a simulation of it. Both
  moments are covered: a stall armed before the call, which lands on the open,
  and one armed after bytes are already consumed, which lands mid-transfer.
- **A stalled upload** (client→server), where the request never reaches the
  server so no reply is ever generated — a different fault from a dropped
  reply, though both surface as a receive timeout.
- **A peer that never completes the SFTP version exchange**, which happens
  *inside* the client construction that opens the channel. That window sits
  before any caller-visible operation and is re-entered on every reconnect, so
  a bound armed after it would leave the headline guarantee unarmed exactly
  when a half-alive peer needs it.
"""

from __future__ import annotations

import contextlib
import errno
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

    - ``stall_download()`` silences server→client. The server still receives and
      still replies; the replies are discarded. The client waits on a channel
      that will never produce another byte: a silent peer, not a closed one, so
      the failure is a read timeout rather than EOF.
    - ``stall_upload()`` silences client→server. The server never sees the
      request at all, so no reply is ever generated.

    Both end in a receive timeout on the channel, which is measured rather than
    assumed: paramiko's ``SFTPFile.write`` is not pipelined by default, so it
    waits for each chunk's response before sending the next and the receive
    bound fires before the SSH out-window can drain. An earlier version of this
    docstring claimed the upload case reached ``Channel.sendall`` via window
    exhaustion; it does not.
    """

    def __init__(self, target_port: int) -> None:
        self._target_port = target_port
        self._stall_down = threading.Event()
        self._stall_up = threading.Event()
        # Single-element holder so the pump thread sees updates; None = no budget.
        self._down_budget: list[int | None] = [None]
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

    def stall_download_after(self, nbytes: int) -> None:
        """Deliver roughly *nbytes* more server→client bytes, then go silent.

        The trigger is a byte count rather than a timer, so "stall mid-transfer"
        is deterministic: it lands after the transfer is genuinely under way and
        does not race a loaded runner. It is approximate by one relay chunk —
        the budget is checked before forwarding, so the chunk that crosses zero
        is still delivered.
        """
        self._down_budget[0] = nbytes

    def resume(self) -> None:
        """Deliver again, so a reconnect through this relay can succeed."""
        self._stall_down.clear()
        self._stall_up.clear()
        self._down_budget[0] = None

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
            for src, dst, gate, budget in (
                (client, upstream, self._stall_up, [None]),
                (upstream, client, self._stall_down, self._down_budget),
            ):
                thread = threading.Thread(target=self._pump, args=(src, dst, gate, budget), daemon=True)
                thread.start()
                self._threads.append(thread)

    def _pump(
        self,
        src: socket.socket,
        dst: socket.socket,
        gate: threading.Event,
        budget: list[int | None],
    ) -> None:
        while not self._stop.is_set():
            try:
                chunk = src.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            remaining = budget[0]
            if remaining is not None:
                if remaining <= 0:
                    gate.set()
                else:
                    budget[0] = remaining - len(chunk)
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

    Auth succeeds and the session channel opens. What happens to the ``sftp``
    subsystem request depends on *mode*, and the two are worth separating
    because ``io_timeout`` bounds one and not the other:

    - ``"accept"`` (default) — the request is accepted, but no subsystem handler
      is registered, so the server never sends its SFTP ``VERSION``. The
      client's version exchange, inside ``SFTPClient.__init__``, waits on a
      reply that never comes. That is a ``recv``, so ``Channel.timeout``
      bounds it.
    - ``"never_answer"`` — the handler blocks, so paramiko's server side never
      sends ``CHANNEL_SUCCESS`` or ``CHANNEL_FAILURE`` at all. The client waits
      in ``Channel._wait_for_event``, a bare ``threading.Event.wait()`` that
      never reads ``Channel.timeout``, so nothing bounds it.

    This is the fault the relay cannot stage: it happens while the client is
    being constructed, before any caller-visible operation, so there is no
    moment in the test to flip a switch. Both postures are real — a subsystem
    that dies on spawn looks like the first, a wedged SSH daemon like the
    second — not contrivances to reach the code path.
    """

    def __init__(self, mode: str = "accept") -> None:
        import paramiko

        self._mode = mode
        self._never_answer = threading.Event()  # never set: the handler parks here
        # Set when the subsystem handler is entered, so a test can tell "blocked
        # at the request" from "blocked somewhere earlier in the handshake".
        self.reached_subsystem_request = threading.Event()
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
        mode = self._mode
        parked = self._never_answer
        reached = self.reached_subsystem_request

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
                reached.set()
                if mode == "never_answer":
                    # Block instead of returning: paramiko's server side sends
                    # CHANNEL_SUCCESS / CHANNEL_FAILURE from this call's return
                    # value, so parking here means no reply is ever sent.
                    parked.wait()
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
def unanswering_server() -> Iterator[_MuteSubsystemServer]:
    server = _MuteSubsystemServer(mode="never_answer")
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
def test_subsystem_request_is_not_bounded(unanswering_server: _MuteSubsystemServer) -> None:
    """Characterises a stated exception: the ``subsystem`` request is unbounded.

    SFTP-030 records this as one of two waits ``io_timeout`` does not cover, and
    a spec clause asserting a paramiko behaviour is exactly the kind of claim
    this item has got wrong three times by reading rather than running. So it is
    pinned here: with ``io_timeout`` set, a peer that opens the channel and never
    answers the request is *still* blocked well past the bound.

    The mechanism, for the reader who finds this test failing: ``invoke_subsystem``
    waits in ``Channel._wait_for_event``, a bare ``threading.Event.wait()`` that
    never reads ``Channel.timeout``. Only a ``recv`` consults it.

    **A failure here is good news, not a regression.** It means the wait became
    bounded — paramiko grew a timeout, or we inlined the request to add one — and
    the SFTP-030 exception should be deleted along with this test. That is why it
    asserts on being blocked rather than on a duration: it is a tripwire on a
    documented gap, not a guarantee anyone wants to keep.
    """
    backend = _make_backend(unanswering_server.port, io_timeout=1.0)
    done = threading.Event()

    def _probe() -> None:
        with contextlib.suppress(Exception):
            backend.check_health()
        done.set()

    threading.Thread(target=_probe, daemon=True).start()

    # Pin *where* it is blocked. Without this, a handshake that never got as far
    # as the request would satisfy the assertion below and prove nothing.
    assert unanswering_server.reached_subsystem_request.wait(timeout=10.0), (
        "the client never reached the subsystem request; this test is not exercising what it claims"
    )
    assert not done.wait(timeout=6.0), (
        "the subsystem request completed or failed within 6s at a 1s io_timeout — "
        "if it is now bounded, delete this test and SFTP-030's stated exception"
    )


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
def test_stalled_open_raises_backend_unavailable(stall_relay: _StallRelay) -> None:
    """A peer that goes silent fails the next operation within the bound.

    The stall is armed before the call, so what is bounded here is the first
    round-trip the operation makes — the ``CMD_OPEN`` for the handle, not a
    later transfer. Mid-transfer is a different moment and is covered by
    ``test_streaming_read_raises_rather_than_truncating``, which consumes bytes
    before stalling; naming the distinction matters because an earlier version
    of this test claimed to cover mid-transfer and did not.

    Without ``io_timeout`` this blocks indefinitely; the elapsed assertion is
    what distinguishes "raised" from "eventually gave up".
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"stalled_{uuid.uuid4().hex[:8]}.bin"
    payload = b"x" * (256 * 1024)
    backend.write(name, payload)

    stall_relay.stall_download()

    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.read_bytes(name)
    elapsed = time.monotonic() - start

    # Tied to the bound, not merely to the runner's patience: a band wide
    # enough to admit any bound would make the assertion vacuous, since the
    # pytest.raises above already catches an outright hang.
    assert elapsed < io_timeout * 3, f"read took {elapsed:.1f}s; expected ~{io_timeout}s"


@pytest.mark.spec("SFTP-030")
@pytest.mark.parametrize("op", ["read", "read_bytes", "delete"])
def test_stall_costs_one_bound_not_several(stall_relay: _StallRelay, op: str) -> None:
    """A stalled operation pays the bound once, not once per classification probe.

    These three classify a failure by re-probing the server (``_raise_if_dir``,
    ``_has_file_ancestor``). Each probe re-enters the same stalled channel while
    the cached client is still set, so without a guard the caller waits a
    multiple of the bound rather than the bound.

    The band is deliberately tighter than the other elapsed assertions here: at
    3x it would admit the doubling it exists to catch. ``read`` measured 2.0x
    before the guard and 1.0x after (a 2 s bound, so 4.0 s → 2.0 s), so 1.75x
    fails the regression while leaving ~1.5 s of slack on a loaded runner.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"onebound_{uuid.uuid4().hex[:8]}.bin"
    backend.write(name, b"x" * 4096)

    stall_relay.stall_download()
    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        getattr(backend, op)(name)
    elapsed = time.monotonic() - start
    assert elapsed < io_timeout * 1.75, (
        f"{op} took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "a classification probe is re-entering the stalled channel"
    )


@pytest.mark.spec("SFTP-030")
@pytest.mark.parametrize(
    ("walk_error", "expect_drop"),
    [(TimeoutError("timed out"), True), (OSError("Failure"), False)],
    ids=["channel-dies-during-walk", "opaque-walk-error"],
)
def test_ancestor_walk_meeting_a_dead_channel_reports_the_drop(
    sftp_server: tuple[int, str] | None,
    monkeypatch: pytest.MonkeyPatch,
    walk_error: Exception,
    expect_drop: bool,
) -> None:
    """A channel that dies *during* the file-ancestor walk still reconnects.

    The stall tests all reach ``_has_file_ancestor`` with a caller error that is
    already dead, which the call-site guard short-circuits — so the re-raise
    inside the walk itself is never exercised by them. The state that reaches it
    is split: the caller's failure is an errno-less ``SSH_FX_FAILURE`` (opaque,
    not dead, so classification proceeds) and the channel dies afterwards, on a
    probe. A relay cannot produce that split on demand, so the two halves are
    injected onto the live client instead.

    What is asserted is the consequence, not the ``raise``. Swallowing the dead
    stat returns ``False``, the caller's opaque error surfaces, and
    ``_map_exception`` maps it to a plain ``RemoteStoreError`` — which does not
    clear the cached client, so the next operation reuses a channel that is
    gone. The ``opaque-walk-error`` case is the control: same shape, a walk
    failure that is *not* a drop, and there the original error must still stand
    and the client must survive.
    """
    if sftp_server is None:
        pytest.skip("paramiko not installed")

    import paramiko

    from remote_store._errors import RemoteStoreError

    backend = _make_backend(sftp_server[0], io_timeout=2.0)
    leaf = f"ancestor_{uuid.uuid4().hex[:8]}.bin"
    name = f"deep_{uuid.uuid4().hex[:8]}/sub/{leaf}"
    client = backend.unwrap(paramiko.SFTPClient)

    def _fail_open(*_args: Any, **_kwargs: Any) -> Any:
        # paramiko's shape for SSH_FX_FAILURE: an OSError carrying no errno.
        raise OSError("Failure")

    def _stat(remote: str, *_args: Any, **_kwargs: Any) -> Any:
        if remote.endswith(leaf):
            # The is-dir classification stat: target is gone, not a directory,
            # so the caller's original failure stands and the walk is reached.
            raise FileNotFoundError(errno.ENOENT, "No such file")
        raise walk_error

    monkeypatch.setattr(client, "file", _fail_open)
    monkeypatch.setattr(client, "stat", _stat)

    with pytest.raises(RemoteStoreError) as caught:
        backend.read_bytes(name)

    assert isinstance(caught.value, BackendUnavailable) is expect_drop
    reconnected = backend.unwrap(paramiko.SFTPClient) is not client
    assert reconnected is expect_drop, (
        "a drop must invalidate the cached client so the next operation reconnects; a non-drop must leave it in place"
    )


@pytest.mark.spec("SFTP-030")
def test_stalled_upload_request_raises_backend_unavailable(stall_relay: _StallRelay) -> None:
    """A client→server stall is bounded: the request never reaches the server.

    Distinct from the download stalls in mechanism, if not in where it lands.
    There the server replies and the relay discards the reply; here the request
    never arrives, so no reply is ever generated. Both end in a receive timeout.

    What this does *not* reach is ``SFTPFile.write``. ``write()`` issues an
    existence ``stat`` first on ``overwrite=False``, and on ``overwrite=True``
    the file open is still a round-trip, so a stalled upload always fails before
    any payload byte is sent — measured: ``SFTPFile.write`` entered 0 times
    either way. The write half proper is covered by the next test, which opens
    the handle before stalling. An earlier revision of this test claimed both a
    ``Channel.sendall`` window-exhaustion route and the ``SFTPFile.write``
    non-pipelining explanation; neither was reached by the run that asserted it.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    backend.check_health()  # connect while the relay is still delivering

    stall_relay.stall_upload()
    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.write(f"upload_{uuid.uuid4().hex[:8]}.bin", b"w" * 4096)
    elapsed = time.monotonic() - start
    assert elapsed < io_timeout * 3, f"write took {elapsed:.1f}s; expected ~{io_timeout}s"


@pytest.mark.spec("SFTP-030")
def test_write_stalling_mid_stream_costs_one_bound(stall_relay: _StallRelay) -> None:
    """``write()`` from a stream that stalls part-way pays the bound once.

    The other upload test stalls *before* the call, so it fails on the first
    round-trip and never reaches ``SFTPFile.write``. This one reaches it: the
    content object stalls the relay from inside its own ``read()``, after the
    first chunk has already been written, so the peer goes quiet with the handle
    open and bytes already sent. Deterministic — the timing is controlled by the
    caller's own stream rather than by racing a thread against the transfer.

    What it pins is the close, not the write. ``write()`` holds the handle in a
    ``with`` block, so the failure runs ``SFTPFile.close()`` on the way out —
    a flush plus a synchronous ``CMD_CLOSE`` whose reply never comes, with
    paramiko swallowing the timeout. Unguarded that is a second, invisible
    bound. The same shape exists in ``write_atomic``, ``copy`` and ``move``'s
    fallback, which is why the guard lives in one helper rather than at the site
    an earlier round happened to measure.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"midwrite_{uuid.uuid4().hex[:8]}.bin"
    stalled_at: list[float] = []

    class _StallsAfterFirstChunk:
        """A content stream that goes quiet on the wire once writing is underway."""

        def __init__(self) -> None:
            self._chunks = 0

        def read(self, size: int = -1) -> bytes:
            self._chunks += 1
            if self._chunks == 1:
                return b"a" * (256 * 1024)  # written while the link is healthy
            if self._chunks == 2:
                stall_relay.stall_upload()
                stalled_at.append(time.monotonic())
                return b"b" * (256 * 1024)  # this one meets a silent peer
            return b""

    with pytest.raises(BackendUnavailable):
        backend.write(name, _StallsAfterFirstChunk())
    elapsed = time.monotonic() - stalled_at[0]

    assert elapsed < io_timeout * 1.75, (
        f"stalled mid-stream write took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "the handle close is re-entering the stalled channel"
    )


@pytest.mark.spec("SFTP-030")
def test_copy_stalling_mid_stream_costs_one_bound(stall_relay: _StallRelay) -> None:
    """``copy()`` holds *two* handles, so an unguarded exit pays two extra bounds.

    The only operation here with more than one open handle, which is why it is
    worth its own test rather than trusting the shared helper: ``copy`` opens the
    source for reading and the destination for writing inside one ``with``, and a
    stall part-way through the transfer condemns both. Measured at this bound:
    6.9 s (3.4x) unguarded, 2.0 s guarded — and two of those three bounds are
    silent, because paramiko's ``SFTPFile._close`` swallows the ``socket.error``
    its own ``CMD_CLOSE`` raises.

    Reaching that moment needs the peer to fall silent *during* the copy, not
    before it: a stall armed up front fails on the source ``stat``, well ahead of
    either handle. ``stall_download_after`` gives a byte-count trigger, so the
    stall lands mid-transfer deterministically rather than on a timer.

    Review found this site missing from the ``_handle`` sweep while the spec,
    the PR body and a sibling test docstring all named ``copy`` as covered. The
    tests that existed were the ones a prior round had measured at their own
    call site; nothing bound the sites swept only by inheriting the helper.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    src = f"copysrc_{uuid.uuid4().hex[:8]}.bin"
    dst = f"copydst_{uuid.uuid4().hex[:8]}.bin"
    backend.write(src, b"c" * (8 * 1024 * 1024))

    # Enough to clear the two stats and get the transfer genuinely under way.
    stall_relay.stall_download_after(512 * 1024)

    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.copy(src, dst)
    elapsed = time.monotonic() - start

    assert elapsed < io_timeout * 1.75, (
        f"copy took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "one of the two handle closes is re-entering the stalled channel"
    )


@pytest.mark.spec("SFTP-030")
def test_stall_during_streamed_write_costs_one_bound(stall_relay: _StallRelay) -> None:
    """A stall part-way through a streamed write is bounded, once.

    This is the write-side counterpart of the streamed-read test, and the only
    case in this file that actually enters ``SFTPFile.write`` with the stall
    armed (verified by spying on it: entered twice, the seed write and the one
    that fails). Reaching it needs the handle opened *before* the stall, which
    ``open_atomic`` gives us; every route through ``write()`` fails on an
    earlier round-trip instead.

    The single-bound half is what makes it worth its runtime. ``open_atomic``
    closes the handle best-effort on an abnormal exit, and paramiko's
    ``SFTPFile.close()`` issues ``CMD_CLOSE`` and waits — so on a dead channel
    the caller paid the bound twice, the second time invisibly, because the
    close is wrapped in ``contextlib.suppress``. Measured at this bound: 4.04 s
    before the guard, 2.04 s after. The 1.75x band fails the regression.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"streamwrite_{uuid.uuid4().hex[:8]}.bin"

    stalled_at: list[float] = []

    def _write_until_stalled() -> None:
        with backend.open_atomic(name) as handle:
            handle.write(b"seed")  # a real write, before anything is stalled
            stall_relay.stall_upload()
            stalled_at.append(time.monotonic())
            handle.write(b"w" * (8 * 1024 * 1024))

    with pytest.raises(BackendUnavailable):
        _write_until_stalled()
    elapsed = time.monotonic() - stalled_at[0]

    assert elapsed < io_timeout * 1.75, (
        f"streamed write took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "the handle close is re-entering the stalled channel"
    )


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
