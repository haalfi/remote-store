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

This file pins both halves of SFTP-030: what ``io_timeout`` covers, and what it
does not. The second half is not an afterthought — SFTP-030 states one exception
and one silent case, and a clause asserting a paramiko behaviour is the kind of
claim this work has got wrong by reading rather than running, so each is
*characterised by a test* rather than asserted.

**Five faults it covers**, because they fail by different mechanisms and none
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
- **Releasing a handle into a channel its own failure condemned**, which the
  bound would otherwise be paid for twice — once by the failed operation and
  once, silently, by the close.
- **Sizing an open handle for a `SEEK_END` seek**, which paramiko's
  ``_get_size`` swallows under a bare ``except`` — so before SIO-011 the seek
  answered ``0`` rather than failing, armed nothing, and left the close to pay a
  second bound. Bounded, but wrong. The wrapper now issues that probe itself.

**One fault it does not cover**, pinned so that a test failure means the gap has
closed and the SFTP-030 exception can go with it:

- **A peer that never answers the `sftp` subsystem request**, which paramiko
  waits for on an untimed event that no channel timeout reaches. The file's only
  genuinely *unbounded* case, and now its only stated exception.

**And one it covers silently**, which is neither of the two categories above:
releasing a handle that never failed, where paramiko catches the stalled
``CMD_CLOSE`` itself. Bounded at one ``io_timeout``, but nothing is raised and
the dead client stays cached — which is what keeps SFTP-030's Postconditions
qualified to a stall *that fails*. "Stated exception" and "unbounded wait" are
therefore not the same set, and neither is "covered" and "reported"; two
artifacts in this repo have collapsed the first pair at least once each.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import shutil
import socket
import tempfile
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store._errors import BackendUnavailable, NotFound, RemoteStoreError  # noqa: E402

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

    SFTP-030 states one exception and this is it — the file's only genuinely
    *unbounded* wait. Keeping the categories apart matters, and the module
    docstring is where they are kept: "stated exception" is not the same set as
    "unbounded wait", nor as "silent". A ``SEEK_END`` seek was the second stated
    exception until SIO-011 made it raise
    (``test_seek_to_end_on_a_stalled_channel_costs_one_bound``, below), which is
    exactly the kind of paramiko-behaviour claim this item has got wrong three
    times by reading rather than running. So this one is pinned: with
    ``io_timeout`` set, a peer that opens the channel and never answers the
    request is *still* blocked well past the bound.

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

    What *this* case does not reach is ``SFTPFile.write``. ``write()`` issues an
    existence ``stat`` first on ``overwrite=False``, and on ``overwrite=True``
    the file open is still a round-trip, so an upload stalled **before the call**
    fails before any payload byte is sent — measured: ``SFTPFile.write`` entered
    0 times either way.

    That is a fact about *when* the peer went silent, not about ``write()``. A
    stall that begins mid-body does reach ``SFTPFile.write`` through plain
    ``write``, which the mid-stream test below covers. Stated carefully because
    this docstring has twice been wrong in the other direction: an early revision
    claimed a ``Channel.sendall`` window-exhaustion route and the
    ``SFTPFile.write`` non-pipelining explanation, neither reached by the run
    that asserted them; its replacement then generalised "entered 0 times" from
    this pre-armed case to every route through ``write()``.
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
@pytest.mark.parametrize("op", ["write", "write_atomic"])
def test_write_stalling_mid_stream_costs_one_bound(stall_relay: _StallRelay, op: str) -> None:
    """A stream that stalls part-way through a write pays the bound once.

    The other upload test stalls *before* the call, so it fails on the first
    round-trip and never reaches ``SFTPFile.write``. This one reaches it: the
    content object stalls the relay from inside its own ``read()``, after the
    first chunk has already been written, so the peer goes quiet with the handle
    open and bytes already sent. Deterministic — the timing is controlled by the
    caller's own stream rather than by racing a thread against the transfer.

    What it pins is the close, not the write. Both operations hold the handle in
    a ``with`` block, so the failure runs ``SFTPFile.close()`` on the way out —
    a flush plus a synchronous ``CMD_CLOSE`` whose reply never comes, with
    paramiko swallowing the timeout. Unguarded that is a second, invisible bound.

    ``write_atomic`` is parametrised in rather than trusted to the shared helper.
    It was the last ``_handle`` call site with no test that would notice the
    guard being removed: its own tests exit the handle cleanly and fail at the
    promote, so they never run the close on a stalled channel. That is the gap
    shape which let ``copy`` ship unguarded a round earlier — a site covered by
    being listed rather than by being run.
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
        getattr(backend, op)(name, _StallsAfterFirstChunk())
    elapsed = time.monotonic() - stalled_at[0]

    assert elapsed < io_timeout * 1.75, (
        f"stalled mid-stream {op} took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
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

    This is the write-side counterpart of the streamed-read test, and what makes
    it distinct is the *guard*, not the moment. It is the only test here that
    exercises ``open_atomic``'s **inline** dead-connection guard: that handle is
    yielded to the caller and its clean-exit close has to sit inside ``_errors``,
    so it cannot route through ``_handle`` like the other five sites do.

    An earlier version of this docstring claimed it was the only case in the file
    reaching ``SFTPFile.write`` with the stall armed, and that "every route
    through ``write()`` fails on an earlier round-trip". That was measured
    against a stall armed *before* the call, and was already false when written:
    ``test_write_stalling_mid_stream_costs_one_bound`` reaches it through plain
    ``write`` and ``write_atomic``, by stalling from inside the content stream.

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


@pytest.mark.spec("SFTP-030")
@pytest.mark.spec("SIO-010")
def test_releasing_a_stalled_stream_costs_one_bound(stall_relay: _StallRelay) -> None:
    """Discarding a stream that failed on a stalled channel pays the bound once.

    The sibling above exits its ``with`` block on the same fault and does not
    time the exit, so the second bound was invisible to it. This one puts the
    clock around both halves: the reads that fail, and the close that follows.

    ``read`` hands back ``BufferedReader(_ErrorMappingStream(handle))``, and the
    wrapper — not this backend — owns that close, which is why the ``_handle``
    guard covering every other paramiko handle does not reach it. Without the
    guard in the wrapper, ``SFTPFile.close()`` issues its synchronous
    ``CMD_CLOSE`` into the channel the read failure just condemned and waits for
    a reply that never comes, so the caller waits ``io_timeout`` twice and sees
    nothing explaining the second wait: paramiko swallows the timeout raised
    inside its own close, and the wrapper suppresses what is left.

    The band matches ``test_stall_costs_one_bound_not_several`` rather than the
    3x used where only a hang is being excluded: at 3x this admits the exact
    doubling it exists to catch.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"release_{uuid.uuid4().hex[:8]}.bin"
    backend.write(name, bytes(range(256)) * 4096)  # 1 MiB

    stream = backend.read(name)
    try:
        assert stream.read(64 * 1024), "expected the stream to deliver bytes before the stall"
        stall_relay.stall_download()

        start = time.monotonic()
        with pytest.raises(BackendUnavailable):
            _drain(stream)
    finally:
        # What a ``with`` block does on the way out, and the half being measured.
        stream.close()
    elapsed = time.monotonic() - start

    assert elapsed < io_timeout * 1.75, (
        f"failed read plus release took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "the stream close is re-entering the stalled channel"
    )


@pytest.mark.spec("SFTP-030")
def test_releasing_a_stalled_handle_after_no_failure_is_silent(
    stall_relay: _StallRelay, caplog: pytest.LogCaptureFixture
) -> None:
    """Characterises what keeps SFTP-030's Postconditions qualified to a stall *that fails*.

    Every mechanism SFTP-030 promises — the classification guards, the handle
    guard, the wrapper's futile-close guard, the client invalidation — is
    triggered by an exception. This is the case that raises none: a handle
    released on a stalled channel with no prior failure. paramiko's
    ``SFTPFile._close`` catches ``(IOError, socket.error)`` itself, and a stalled
    ``CMD_CLOSE`` arrives as ``socket.timeout``, so the wait is paid and
    discarded inside paramiko before anything of ours sees it.

    Note the guard above cannot apply here and is not being tested: it skips a
    close **its own stream's failure** condemned, and this stream never failed.
    The two are siblings only in cost.

    All three halves are asserted because the qualifier needs all three — the
    wait is bounded, nothing is raised, and the cached client survives, which is
    what makes the *following* operation pay the bound again. Only
    ``remote_store``'s own records are checked: paramiko emits two DEBUG lines of
    its own (``[chan 0] close(...)`` and ``[chan 0] Request: close``), which are
    transport chatter rather than a report of the stall.

    **A failure here is good news**, on the same terms as the subsystem test: it
    means the close has become reportable, and SFTP-030's qualifier — plus the
    silent-stall paragraph that carries this figure — should be revisited with
    it. It replaces the ``SEEK_END`` seek as the clause's demonstrating case;
    that one now raises (SIO-011), which is why it can no longer serve.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"silentclose_{uuid.uuid4().hex[:8]}.bin"
    backend.write(name, bytes(range(256)) * 4096)  # 1 MiB

    stream = backend.read(name)
    assert stream.read(64 * 1024), "expected the stream to deliver bytes before the stall"
    stall_relay.stall_download()

    with caplog.at_level(logging.DEBUG, logger="remote_store"):
        # Cleared here, not at entry: ``caplog.records`` spans the whole test,
        # and the backend logs an AUTO_ADD warning when it connects. What is
        # being asserted is what the *close* emits.
        caplog.clear()
        start = time.monotonic()
        stream.close()  # raises nothing, which is the point
        elapsed = time.monotonic() - start

    # Filtered by logger name, not by ``at_level``. That argument raises the
    # level on the ``remote_store`` logger; it does not stop caplog's root
    # handler capturing anything else that passes, so under ``--log-level=DEBUG``
    # paramiko's own two close lines land in ``caplog.records`` too. Asserting on
    # the unfiltered list failed on transport chatter while blaming SFTP-030.
    ours = [r for r in caplog.records if r.name.startswith("remote_store")]
    assert not ours, (
        f"the silent close emitted {[r.getMessage() for r in ours]}; "
        "if it now reports the stall, SFTP-030's silent-stall paragraph is stale"
    )
    assert backend._sftp_client is not None, (
        "no failure reached _map_exception, so the dead client must still be cached — "
        "if this is now None the close has become reportable and SFTP-030's "
        "Postconditions can drop their qualifier"
    )
    # Two-sided: the lower bound is what says the close really did re-enter the
    # stalled channel rather than returning early, and the upper is what says it
    # cost one bound rather than several. No pytest-timeout is configured, so an
    # unbounded regression hangs the suite rather than failing here.
    assert io_timeout * 0.5 < elapsed < io_timeout * 1.75, (
        f"the silent close took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "expected ~1x — one CMD_CLOSE into a stalled channel, swallowed by paramiko"
    )


@pytest.mark.spec("SFTP-030")
def test_get_file_info_surfaces_a_stall(stall_relay: _StallRelay) -> None:
    """Sizing a file by path surfaces a stall, and costs one bound doing it.

    ``get_file_info`` reaches the wire through a ``stat`` — the same *kind* of
    call the ``SEEK_END`` probe makes, though ``SFTPClient.stat`` against a path
    rather than the ``SFTPFile.stat`` the probe issues against an open handle.
    So what this pins is that ``SFTPClient.stat`` has no swallowing sibling of
    paramiko's ``_get_size``, and nothing about the probe: that is
    ``test_seek_to_end_on_a_stalled_channel_costs_one_bound``'s job. Both are
    paramiko-behaviour claims of exactly the kind this file exists to run rather
    than read, which is why they get a test each rather than one standing in for
    the other.

    Both halves of the promise are asserted, because a user acting on it needs
    both: the stall *surfaces*, and the dead client is dropped so the next
    operation reconnects rather than paying the bound again. The sibling test
    below asserts the same two of the seek, which is what SIO-011 brought it to;
    before that it did neither.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"sized_{uuid.uuid4().hex[:8]}.bin"
    payload = bytes(range(256)) * 4096  # 1 MiB
    backend.write(name, payload)
    assert backend.get_file_info(name).size == len(payload), "healthy sizing must be correct first"

    stall_relay.stall_download()
    start = time.monotonic()
    with pytest.raises(BackendUnavailable):
        backend.get_file_info(name)
    elapsed = time.monotonic() - start

    assert elapsed < io_timeout * 1.75, (
        f"get_file_info took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "sizing a file by path should cost one bound, not several"
    )
    assert backend._sftp_client is None, "get_file_info must drop the dead client so the next operation reconnects"


@pytest.mark.spec("SFTP-030")
@pytest.mark.spec("SIO-010")
@pytest.mark.spec("SIO-011")
def test_seek_to_end_on_a_stalled_channel_costs_one_bound(stall_relay: _StallRelay) -> None:
    """A ``SEEK_END`` seek fails, once, and condemns the channel on the way out.

    ``SFTPFile.seek(offset, SEEK_END)`` calls paramiko's ``_get_size()``, whose
    whole body is ``try: return self.stat().st_size`` under a bare ``except:
    return 0``. Delegating to it meant the stalled ``stat`` was swallowed: the
    seek blocked for the bound, *answered* ``0`` on a file of any size, and
    raised nothing — so no exception reached ``_fail``, the guard stayed
    unarmed, and the close paid the bound a second time.

    SIO-011 has the wrapper issue the size probe itself, so all three follow
    from one round-trip: the failure surfaces as ``BackendUnavailable``, the
    futile-close guard arms, and ``_map_exception`` clears the cached client.
    All three are asserted, because an implementation could deliver any one
    without the others and each is a separate promise to a caller.

    This replaces a test that characterised the swallow rather than asserting
    against it, on the terms that test set for its own deletion.
    """
    io_timeout = 2.0
    backend = _make_backend(stall_relay.port, io_timeout=io_timeout)
    name = f"seekend_{uuid.uuid4().hex[:8]}.bin"
    payload = bytes(range(256)) * 4096  # 1 MiB
    backend.write(name, payload)

    stream = backend.read(name)
    try:
        assert stream.read(64 * 1024), "expected the stream to deliver bytes before the stall"
        stall_relay.stall_download()

        start = time.monotonic()
        # The wrong-answer half: this used to return 0 and raise nothing.
        with pytest.raises(BackendUnavailable):
            stream.seek(0, 2)
    finally:
        # What a ``with`` block does on the way out, and the half that used to
        # pay the second bound.
        stream.close()
    elapsed = time.monotonic() - start

    # The half that outlives the call. A swallowed failure left the dead client
    # cached, so the next operation re-entered the same channel and waited again;
    # a mapped one clears it, which is what makes SFTP-030's Postconditions hold
    # for the seek without a qualifier.
    assert backend._sftp_client is None, (
        "the stalled seek must clear the cached client so the next operation reconnects"
    )
    # Upper bound only, and two-sided would be wrong here: the cost is now one
    # bound, and there is no floor to assert below it — a seek that failed
    # *faster* than the bound would be a different fault, not this one. No
    # pytest-timeout is configured, so a regression to an unbounded wait hangs
    # the suite rather than failing here; the 1.75x ceiling is what catches the
    # doubling, which is the regression this guards.
    assert elapsed < io_timeout * 1.75, (
        f"seek-to-end plus release took {elapsed:.1f}s ({elapsed / io_timeout:.1f}x the bound); "
        "expected ~1x — one bound inside the probe and a close the guard skips. "
        "At ~2x the probe's failure is not arming the guard and the close is "
        "re-entering the stalled channel"
    )


@pytest.mark.spec("SIO-011")
def test_seek_to_end_on_a_healthy_channel_answers_the_true_size(
    sftp_server: tuple[int, str] | None,
) -> None:
    """The case that always worked keeps working, negative offsets included.

    The probe replaces paramiko's ``_get_size`` on every ``SEEK_END`` seek, not
    only a stalled one, so the healthy path is the larger blast radius of the
    two and the one no stall test touches. ``seek(-n, SEEK_END)`` is the shape
    that matters: ``SFTPFile.seekable()`` returns ``True`` unconditionally, so
    ``read_seekable()`` hands this stream straight to an analytical reader, and
    a Parquet footer read is a negative offset from the end.
    """
    if sftp_server is None:
        pytest.skip("paramiko not installed")
    backend = _make_backend(sftp_server[0])
    name = f"healthy_seekend_{uuid.uuid4().hex[:8]}.bin"
    payload = bytes(range(256)) * 4096  # 1 MiB
    backend.write(name, payload)

    with backend.read(name) as stream:
        assert stream.seek(0, 2) == len(payload), "seek-to-end must report the real size"
        assert stream.read() == b"", "the true end has no bytes after it"

        assert stream.seek(-8, 2) == len(payload) - 8
        assert stream.read(8) == payload[-8:], "a footer read must land on the last 8 bytes"

        # SEEK_SET after SEEK_END: the probe must not have disturbed the
        # handle's own position bookkeeping.
        assert stream.seek(0) == 0
        assert stream.read(4) == payload[:4]


@pytest.mark.spec("SIO-011")
def test_seek_to_end_raises_when_the_server_refuses_to_size_the_handle() -> None:
    """A server that refuses ``CMD_FSTAT`` gets an error, where it used to get ``0``.

    This is the only case where SIO-011 changes behaviour on a connection that
    is not stalled, which is why it is asserted apart from the stall. FSTAT is
    optional in the SFTP protocol: a minimal or embedded server may serve
    streamed reads while answering ``SSH_FX_OP_UNSUPPORTED`` to a stat on the
    open handle. paramiko's ``_get_size`` swallowed that refusal under its bare
    ``except`` and returned ``0``, so the seek answered ``0`` on a readable file
    — the same wrong answer as the stalled case, reached with nothing stalled.

    Both directions are asserted against the same server, because "now raises"
    means little beside an unstated alternative: the raw paramiko handle, which
    is what the wrapper used to delegate to, still swallows the refusal here and
    answers ``0`` on a 16-byte file. That is the pre-clause behaviour reproduced
    rather than described, and if paramiko ever drops the bare ``except`` this
    half fails and takes the contrast with it.

    **Such a server is not otherwise healthy, and the surrounding assertions say
    where the line falls.** Path-based ``stat`` is left working, so
    ``get_file_info`` sizes the file and ``exists`` answers; the streamed
    ``read`` and a ``SEEK_SET`` seek work, because neither needs the handle's
    size. ``read_bytes`` does *not* — paramiko's prefetch stats the handle — and
    it raised on this server before this change as much as after, which is worth
    pinning here so the failure is not misread as one SIO-011 introduced.
    """
    from tests.backends.sftp._helpers import (
        NoFstatStubSFTPServer,
        start_sftp_server,
        stop_sftp_server,
    )

    tmpdir = tempfile.mkdtemp(prefix="sftp_nofstat_")
    thread, port, _host_key, stop_event, sock = start_sftp_server(
        root=tmpdir, host="127.0.0.1", server_class=NoFstatStubSFTPServer
    )
    try:
        backend = _make_backend(port)
        name = f"nofstat_{uuid.uuid4().hex[:8]}.bin"
        payload = b"0123456789abcdef"
        backend.write(name, payload)

        # Where the line falls: everything that does not need the handle's size.
        assert backend.get_file_info(name).size == len(payload)
        assert backend.exists(name) is True

        with backend.read(name) as stream:
            assert stream.read(4) == payload[:4], "a streamed read needs no handle stat"

            with pytest.raises(RemoteStoreError) as caught:
                stream.seek(0, 2)
            assert not isinstance(caught.value, NotFound), (
                "a refused FSTAT is not a missing file; it must not be mapped to NotFound"
            )

            assert stream.seek(2) == 2, "a SEEK_SET seek is local and must still work"
            assert stream.read(3) == payload[2:5]

        # Pre-existing, and pinned so it is not read as this clause's doing:
        # paramiko's prefetch stats the handle, so the buffered read already
        # failed on such a server before SIO-011 existed.
        with pytest.raises(RemoteStoreError):
            backend.read_bytes(name)

        # The pre-clause behaviour, on the same server: the raw handle the
        # wrapper used to delegate to swallows the refusal and answers 0.
        raw = backend._sftp.file(backend._sftp_path(name), "r")
        try:
            raw.seek(0, 2)
            assert raw.tell() == 0, (
                "expected paramiko's _get_size to swallow the refusal and answer 0; "
                "if this is now the real size or an error, the bare except is gone "
                "and this test's contrast has lost its subject"
            )
        finally:
            with contextlib.suppress(Exception):
                raw.close()
    finally:
        stop_sftp_server(thread, stop_event, sock)
        shutil.rmtree(tmpdir, ignore_errors=True)
