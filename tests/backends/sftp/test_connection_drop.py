"""SFTPBackend dropped-connection error mapping — SIO-012, SFTP-024, BE-021.

**A drop is not a stall, and the difference decides which exception shape a
caller meets.** ``test_io_timeout.py`` drives a silent peer: every socket stays
open, no byte ever arrives, and the failure is the ``socket.timeout`` that
``io_timeout`` bounds — an ``OSError``, which ``_ErrorMappingStream`` has always
caught. Here the sockets are closed. The client's next receive returns EOF,
paramiko's ``SFTP._read_all`` raises ``EOFError``, and
``SFTPClient._read_response`` converts it to
``SSHException("Server connection dropped: ...")`` before anything of ours sees
it. No bound is involved and nothing waits.

That conversion is the whole of BK-358. ``SSHException`` subclasses neither
``OSError`` nor ``EOFError``, so before SIO-012 it walked straight out of the
wrapper: a caller holding a stream from ``read()`` caught a raw paramiko
exception where BE-021 forbids one and SFTP-024 says none escapes, the cached
client was never invalidated, and the same drop on ``read_bytes`` — which fails
inside ``_errors()`` — was mapped correctly all along. One connection, one
fault, two answers depending on which method the caller used.

**Why a real socket rather than an injected exception.** The gap survived
because the test covering this ground
(``test_read_stream_eoferror_maps_and_reconnects`` in ``test_config.py``) injects
``EOFError`` from a fake handle and so bypasses ``_read_response``, the line that
does the converting. An injected shape cannot reach a defect whose cause is
*which shape paramiko produces*, so every test here drives a relay that really
closes the connection.

**Why the relay goes silent before it closes**, which is the one thing about it
that is not obvious: see ``_DropRelay``. A bare close reaches this defect two
times in fifteen.
"""

from __future__ import annotations

import contextlib
import io
import socket
import threading
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


def _make_backend(port: int) -> Any:
    """An SFTP backend pointed at *port*, with a short bound as a safety net.

    ``io_timeout`` is **not** under test here — a drop raises at once and waits
    on nothing, which is the property separating this file from
    ``test_io_timeout.py``. It is pinned short anyway so a mis-staged drop (one
    the relay failed to deliver) fails the suite in seconds rather than hanging
    it for the shipped 120 s default.
    """
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(
        host="127.0.0.1",
        port=port,
        username="testuser",
        password="testpass",
        base_path="/",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
        io_timeout=5.0,
    )
    _BACKENDS.append(backend)
    return backend


class _DropRelay:
    """TCP relay to *target_port* that drops the connection while a reply is outstanding.

    The sibling instrument to ``_StallRelay`` in ``test_io_timeout.py``, and
    deliberately not a mode of it: that relay keeps its sockets open and stops
    *forwarding*, so the far side goes quiet; this one tears the sockets down, so
    the far side reads EOF. Both are "the server stopped answering" to a caller
    and neither is reachable from the other.

    **``arm()`` silences server→client first and closes on the reply the client
    will never see. That ordering is the instrument, not an implementation
    detail.** Closing the sockets outright races paramiko's transport-reader
    thread: whichever notices the dead socket first decides the shape the caller
    meets. If the transport wins, it tears itself down and the next SFTP read
    raises ``OSError('Socket is closed')`` — an ``OSError``, which the wrapper
    has always caught, so the drop maps and this file's whole subject is missed.
    Measured over 15 runs of a bare close: **13 mapped that way, 2 reached
    ``SSHException``**. Silencing first puts the client inside a blocking
    ``recv`` at the moment the socket dies, so the EOF path is the one that
    fires: 15 of 15, on the streamed read, the ``SEEK_END`` probe and the eager
    read alike. Both figures are 15 runs of the drop staged each way against
    this module's own relay on paramiko 5.0.0 / CPython 3.11, classifying the
    exception that escaped; to re-derive the first, make ``arm()`` call
    ``_tear_down()`` directly — that *is* the bare close — and loop a test.
    (Not by tearing down inside ``_pump`` unconditionally: that fires on the
    first byte either way, so the handshake never completes and nothing is
    measured.)

    **``arm()`` is one-shot.** The teardown re-opens the gate, so the listener
    keeps serving and the next connection is pumped normally — which is what lets
    a test assert the backend reconnects (SFTP-010 tier 2) rather than only that
    it dropped its client, and what lets one relay stage two drops in sequence.
    """

    def __init__(self, target_port: int) -> None:
        self._target_port = target_port
        self._armed = threading.Event()
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._lock = threading.Lock()
        self._live: list[socket.socket] = []

    @property
    def port(self) -> int:
        return int(self._listener.getsockname()[1])

    def start(self) -> None:
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def arm(self) -> None:
        """Drop the connection at the next server→client reply, discarding it."""
        self._armed.set()

    def _tear_down(self) -> None:
        self._armed.clear()
        with self._lock:
            live, self._live = self._live, []
        for sock in live:
            # ``shutdown`` before ``close`` because a bare close does not
            # reliably wake a thread already blocked in ``recv`` on the same
            # socket — the pump would sit there until something else noticed.
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                sock.close()

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
            with self._lock:
                self._live.extend((client, upstream))
            for src, dst, downstream in ((client, upstream, False), (upstream, client, True)):
                threading.Thread(target=self._pump, args=(src, dst, downstream), daemon=True).start()

    def _pump(self, src: socket.socket, dst: socket.socket, downstream: bool) -> None:
        while not self._stop.is_set():
            try:
                chunk = src.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            if downstream and self._armed.is_set():
                # The server answered and the client will never see it, so the
                # client is blocked in ``recv`` right now. Close, and that
                # blocked call wakes on EOF rather than on a torn-down transport.
                self._tear_down()
                return
            try:
                dst.sendall(chunk)
            except OSError:
                return

    def stop(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        self._tear_down()


@pytest.fixture
def drop_relay(sftp_server: tuple[int, str] | None) -> Iterator[_DropRelay]:
    if sftp_server is None:
        pytest.skip("paramiko not installed")
    relay = _DropRelay(sftp_server[0])
    relay.start()
    yield relay
    relay.stop()


def _written(backend: Any, prefix: str) -> tuple[str, bytes]:
    """Write 1 MiB of non-uniform content and return its name and payload.

    Non-uniform so a prefix assertion means something: against ``b"x" * n`` any
    reordering or duplication of chunks would still satisfy ``startswith``.
    """
    name = f"{prefix}_{uuid.uuid4().hex[:8]}.bin"
    payload = bytes(range(256)) * 4096
    backend.write(name, payload)
    return name, payload


def _drain(stream: Any) -> None:
    """Read *stream* to exhaustion, discarding what it yields."""
    while stream.read(64 * 1024):
        pass


@pytest.mark.spec("SIO-012")
@pytest.mark.spec("SFTP-024")
def test_a_mid_read_drop_on_a_stream_raises_backend_unavailable(drop_relay: _DropRelay) -> None:
    """The headline of BK-358: a dropped connection must not reach the caller as paramiko.

    ``read()`` hands back ``BufferedReader(_ErrorMappingStream(handle))``, and
    the backend's ``_errors()`` context manager has long since exited by the time
    the caller reads. The wrapper is therefore the only thing between
    ``SSHException`` and the caller, which is what makes the caught set — not the
    mapper, which already handled this shape — the thing under test.
    """
    backend = _make_backend(drop_relay.port)
    name, _ = _written(backend, "drop")

    with backend.read(name) as stream:
        assert stream.read(64 * 1024), "expected the stream to deliver bytes before the drop"
        drop_relay.arm()

        with pytest.raises(BackendUnavailable):
            _drain(stream)


@pytest.mark.spec("SIO-012")
@pytest.mark.spec("SFTP-010")
def test_a_mid_read_drop_invalidates_the_client_and_the_next_read_reconnects(
    drop_relay: _DropRelay,
) -> None:
    """The recovery half, which the unmapped escape also cost.

    ``_map_exception`` clears the cached client on every ``BackendUnavailable``
    it concludes (SFTP-010 tier 2), so a shape that never reaches it leaves the
    dead client in place for the next operation to re-enter. Asserted through a
    successful second read rather than on ``_sftp_client`` alone: the attribute
    going ``None`` is the mechanism, reconnecting is the guarantee, and a fix
    that cleared the attribute without restoring service would satisfy only the
    first. The relay's one-shot arming is what makes the second half reachable.
    """
    backend = _make_backend(drop_relay.port)
    name, payload = _written(backend, "reconnect")

    stream = backend.read(name)
    try:
        assert stream.read(64 * 1024), "expected the stream to deliver bytes before the drop"
        # internal: no public observable — the reconnect below is the guarantee
        # and says the client was replaced by the time the next operation ran.
        # Only these two say it happened on the operation that surfaced the drop
        # rather than lazily afterwards, which is what SFTP-010 tier 2 is about
        # and what the escape actually cost.
        assert backend._sftp_client is not None, "precondition: a live client is cached"
        drop_relay.arm()
        with pytest.raises(BackendUnavailable):
            _drain(stream)
    finally:
        stream.close()

    assert backend._sftp_client is None, "the drop must invalidate the cached client"
    assert backend.read_bytes(name) == payload, "the next operation must reconnect and succeed"


@pytest.mark.spec("SFTP-030")
def test_a_dropped_stream_raises_rather_than_truncating(drop_relay: _DropRelay) -> None:
    """SFTP-030's no-short-read claim, asserted against a drop and not only a stall.

    ``test_streaming_read_raises_rather_than_truncating`` pins the same clause
    against a **stall** — a silent peer, which raises ``socket.timeout``. BK-358
    recorded the drop as an open question, because a send-side ``EOFError`` is
    swallowed by ``BufferedFile.read`` into a short read before the wrapper sees
    it and it was not known whether the receive side did the same. It does not:
    the drop raises with a valid prefix delivered, so a truncated transfer is
    never mistaken for a complete one on either fault.

    The prefix assertion is what makes this more than a duplicate of the first
    test. Raising is half the claim; a stream that raised *and* handed back
    reordered or duplicated bytes would satisfy the other test alone.
    """
    backend = _make_backend(drop_relay.port)
    name, payload = _written(backend, "prefix")

    with backend.read(name) as stream:
        first = stream.read(64 * 1024)
        assert first, "expected the stream to deliver bytes before the drop"
        drop_relay.arm()

        with pytest.raises(BackendUnavailable):
            _drain(stream)

    assert len(first) < len(payload), "the drop must land mid-transfer, not after the last byte"
    assert payload.startswith(first), "what arrived before the drop must be a valid prefix"


@pytest.mark.spec("SIO-012")
@pytest.mark.spec("BE-021")
def test_the_stream_and_read_bytes_answer_a_drop_the_same_way(drop_relay: _DropRelay) -> None:
    """The asymmetry BK-358 is about, asserted as the thing that must not return.

    ``read_bytes`` fails inside ``_errors()`` and has always mapped; the stream
    fails after it has exited and did not. Driving both against the same fault,
    on the same relay and the same backend, is what makes this a comparison
    rather than two assertions that happen to agree — a later narrowing of the
    caught set breaks this while leaving every ``read_bytes`` test green.

    **The two drops land at different moments, and deliberately.** The stream's
    lands mid-payload. The eager one lands on ``read_bytes``' first round trip,
    because arming mid-payload there kills paramiko's prefetch threads, and their
    ``EOFError`` tracebacks reach pytest as unhandled thread exceptions that
    ``filterwarnings = error`` turns into failures — noise from paramiko's
    threading model, not from anything this item touches. What is compared is the
    answer to a dropped connection, which is what BE-021 speaks about; the
    round trip it lands on is not part of the claim.
    """
    backend = _make_backend(drop_relay.port)
    name, _ = _written(backend, "symmetry")

    stream = backend.read(name)
    try:
        assert stream.read(64 * 1024), "expected the stream to deliver bytes before the drop"
        drop_relay.arm()
        with pytest.raises(BackendUnavailable) as streamed:
            _drain(stream)
    finally:
        stream.close()

    backend.check_health()  # reconnect through the relay, which is one-shot
    drop_relay.arm()
    with pytest.raises(BackendUnavailable) as eager:
        backend.read_bytes(name)

    for exc in (streamed.value, eager.value):
        assert str(exc), "SFTP-023: a dropped connection names the failure rather than raising blank"
        assert exc.backend == "sftp"
        assert exc.path == name


@pytest.mark.spec("SIO-011")
@pytest.mark.spec("SIO-012")
def test_a_seek_to_end_meeting_a_drop_maps(drop_relay: _DropRelay) -> None:
    """The probe path is bounded by the same set as every other path — this widening included.

    SIO-011 moved the ``SEEK_END`` size request into the wrapper so its failure
    has a mapping path to travel, and bounded it by the same tuple as the reads.
    That made the probe leak an ``SSHException`` exactly as a read did, which is
    what the pin in ``test_stream.py`` recorded. The bound is unchanged and the
    set is wider, so the probe maps for the same reason the reads do rather than
    by a rule of its own.
    """
    backend = _make_backend(drop_relay.port)
    name, _ = _written(backend, "seekend")

    with backend.read(name) as stream:
        assert stream.read(4096), "expected the stream to deliver bytes before the drop"
        drop_relay.arm()

        with pytest.raises(BackendUnavailable):
            stream.seek(0, io.SEEK_END)
