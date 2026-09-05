"""Tests for _ErrorMappingStream and _safe_wrap."""

from __future__ import annotations

import io
from typing import cast

import pytest

from remote_store._errors import NotFound, RemoteStoreError
from remote_store._stream import _ErrorMappingStream, _safe_wrap


def _test_mapper(exc: Exception, path: str) -> RemoteStoreError:
    """Simple mapper that converts any exception to NotFound."""
    return NotFound(f"mapped: {exc}", path=path, backend="test")


# ---------------------------------------------------------------------------
# Helper streams
# ---------------------------------------------------------------------------


class _ParamikoLikeStream(io.RawIOBase):
    """A stream that returns None from seek() like paramiko SFTPFile."""

    def __init__(self, data: bytes) -> None:
        super().__init__()
        self._buf = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def seek(self, offset: int, whence: int = 0) -> int:
        self._buf.seek(offset, whence)
        return None  # type: ignore[return-value]  # paramiko behavior

    def tell(self) -> int:
        return self._buf.tell()


class _FailingStream(io.RawIOBase):
    """A stream that raises an OSError on every operation."""

    def __init__(self, exc_type: type = OSError) -> None:
        super().__init__()
        self._exc_type = exc_type

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise self._exc_type("disk failure" if self._exc_type is OSError else "bad argument")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise self._exc_type("disk failure" if self._exc_type is OSError else "bad argument")

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise OSError("disk failure")

    def seek(self, offset: int, whence: int = 0) -> int:
        raise OSError("disk failure")

    def tell(self) -> int:
        raise OSError("disk failure")


class _EOFStream(io.RawIOBase):
    """Raises ``EOFError`` on every read op — a dead-connection signal the wrapper must map.

    ``EOFError`` is not an ``OSError``, so it needs its own arm in the caught
    tuple. Deliberately *not* attributed to a paramiko call site: on the SFTP
    read path a drop surfaces as ``SSHException`` (``_read_response`` catches
    the ``EOFError`` and converts it) and a send-side ``EOFError`` is swallowed
    into a short read by ``BufferedFile``. This stands in for the shape.
    """

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise EOFError("server closed connection")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise EOFError("server closed connection")

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise EOFError("server closed connection")

    def seek(self, offset: int, whence: int = 0) -> int:
        raise EOFError("server closed connection")

    def tell(self) -> int:
        raise EOFError("server closed connection")


class _FailingCloseStream(io.RawIOBase):
    """A stream that raises on close."""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        return 0

    def close(self) -> None:
        if not self.closed:
            super().close()
            raise OSError("close failed")


class _ChannelDeath(OSError):
    """The failure shape ``_fatal`` below treats as condemning the connection.

    A distinct type rather than a message match, so a test that means "not
    fatal" can raise a plain ``OSError`` and be sure the predicate says so.
    """


def _fatal(exc: Exception) -> bool:
    """Stand-in for ``SFTPBackend._is_connection_dead`` — shape, not message."""
    return isinstance(exc, _ChannelDeath)


class _CloseTrackingStream(io.RawIOBase):
    """Reads fail with *exc* (or return *data* when it is ``None``); closes are counted.

    Counted rather than flagged: the skip has to hold when close is reached
    twice — a ``with`` block plus an explicit ``close()``, or a
    ``BufferedReader`` layer closing its raw — and a boolean cannot tell a
    second inner close from the first.
    """

    def __init__(self, exc: Exception | None = None, data: bytes = b"payload") -> None:
        super().__init__()
        self._exc = exc
        self._buf = io.BytesIO(data)
        self.close_calls = 0

    def readable(self) -> bool:
        return True

    def _check(self) -> None:
        if self._exc is not None:
            raise self._exc

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        self._check()
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        self._check()
        return self._buf.read(size)

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        self._check()
        return self._buf.readline(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        self._check()
        return self._buf.seek(offset, whence)

    def tell(self) -> int:
        self._check()
        return self._buf.tell()

    def close(self) -> None:
        self.close_calls += 1
        super().close()


class _ParamikoSeekEndStream(io.RawIOBase):
    """Models paramiko's ``SFTPFile``: ``SEEK_END`` sizes over the wire, and swallows.

    ``SFTPFile.seek`` resolves ``SEEK_END`` through ``_get_size()``, whose whole
    body is ``try: return self.stat().st_size`` under a bare ``except: return
    0`` (paramiko 5.0.0, read with ``inspect.getsource``).  So a size round-trip
    that fails leaves the seek *answering* at ``offset`` rather than raising --
    the shape SIO-011 removes.  ``stat_size`` stands for that round-trip:
    ``seek`` swallows it exactly as paramiko does, and the wrapper's
    ``size_probe`` calls it directly so the failure has somewhere to go.

    ``seek`` returns ``None``, as paramiko's does, so these tests exercise the
    wrapper's existing None-fallback rather than a tidier stand-in.
    """

    def __init__(self, data: bytes = b"payload", *, stat_exc: Exception | None = None) -> None:
        super().__init__()
        self._data = data
        self._buf = io.BytesIO(data)
        self._stat_exc = stat_exc
        self.stat_calls = 0
        self.seek_calls: list[tuple[int, int]] = []
        self.close_calls = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        # ``SFTPFile.seekable()`` returns ``True`` unconditionally, which is why
        # ``read_seekable()`` hands this stream straight on rather than spooling
        # it -- and why a ``BufferedReader`` will accept the seek below.
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def stat_size(self) -> int:
        self.stat_calls += 1
        if self._stat_exc is not None:
            raise self._stat_exc
        return len(self._data)

    def seek(self, offset: int, whence: int = 0) -> int:
        self.seek_calls.append((offset, whence))
        if whence == io.SEEK_END:
            try:
                size = self.stat_size()
            except Exception:  # noqa: BLE001 -- paramiko's own `except: return 0`
                size = 0
            self._buf.seek(size + offset, io.SEEK_SET)
        else:
            self._buf.seek(offset, whence)
        return None  # type: ignore[return-value]  # paramiko behavior

    def tell(self) -> int:
        return self._buf.tell()

    def close(self) -> None:
        self.close_calls += 1
        super().close()


def _stat_size_probe(inner: object) -> int:
    """Stand-in for ``_sftp_handle_size`` — shape, not paramiko."""
    return cast("int", cast("_ParamikoSeekEndStream", inner).stat_size())


# ---------------------------------------------------------------------------
# Passthrough tests
# ---------------------------------------------------------------------------


class TestErrorMappingStreamPassthrough:
    """Stream operations pass through to the inner stream when no error occurs."""

    @pytest.mark.parametrize(
        ("data", "action", "expected"),
        [
            pytest.param(b"hello world", lambda s: s.read(), b"hello world", id="read-all"),
            pytest.param(b"hello world", lambda s: s.read(5), b"hello", id="read-sized"),
            pytest.param(b"line1\nline2\n", lambda s: s.readline(), b"line1\n", id="readline"),
        ],
    )
    def test_read_operations(self, data: bytes, action, expected: bytes) -> None:
        stream = _ErrorMappingStream(io.BytesIO(data), _test_mapper, "f.txt")
        assert action(stream) == expected

    def test_seek_tell_passthrough(self) -> None:
        inner = io.BytesIO(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(5)
        assert stream.tell() == 5
        stream.seek(0)
        assert stream.tell() == 0

    @pytest.mark.parametrize(
        ("attr", "expected"),
        [
            pytest.param("seekable", True, id="seekable"),
            pytest.param("readable", True, id="readable"),
        ],
    )
    def test_stream_capabilities(self, attr: str, expected: bool) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        assert getattr(stream, attr)() is expected

    def test_iteration(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"a\nb\nc\n"), _test_mapper, "f.txt")
        assert list(stream) == [b"a\n", b"b\n", b"c\n"]

    def test_close_passthrough(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        stream.close()
        assert stream.closed

    def test_readinto_passthrough(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        buf = bytearray(5)
        n = stream.readinto(buf)
        assert n == 5
        assert buf == b"hello"


# ---------------------------------------------------------------------------
# Seek/tell None-fallback (paramiko-style)
# ---------------------------------------------------------------------------


class TestSeekTellNoneFallback:
    """seek()/tell() None-fallback for paramiko-style streams."""

    @pytest.mark.parametrize(
        ("offset", "setup_action", "expected_pos"),
        [
            pytest.param(0, lambda s: s.read(5), 0, id="seek-to-zero-after-read"),
            pytest.param(3, lambda _: None, 3, id="seek-to-nonzero"),
        ],
    )
    def test_seek_returns_position_when_inner_returns_none(
        self,
        offset,
        setup_action,
        expected_pos,
    ) -> None:
        inner = _ParamikoLikeStream(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        setup_action(stream)
        pos = stream.seek(offset)
        assert pos == expected_pos

    def test_tell_returns_int_when_inner_returns_none(self) -> None:
        """tell() guards against None even though paramiko returns int."""
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(3)
        inner.tell = lambda: None  # type: ignore[assignment]
        assert stream.tell() == 0


# ---------------------------------------------------------------------------
# Error remapping and edge cases
# ---------------------------------------------------------------------------


class TestErrorMappingStreamErrors:
    """OSError remapping, programming error propagation, close swallowing."""

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
            pytest.param(lambda s: next(iter(s)), id="iteration"),
        ],
    )
    def test_operation_remaps_oserror(self, action) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            action(stream)

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
            pytest.param(lambda s: next(iter(s)), id="iteration"),
        ],
    )
    def test_operation_remaps_eoferror(self, action) -> None:
        """audit-020 M1: ``EOFError`` must map like ``OSError``.

        ``EOFError`` is not an ``OSError``. The wrapper caught only ``OSError``,
        so an ``EOFError`` escaped raw to the ``read()`` consumer, unmapped — and
        for the SFTP backend that also meant the dead client was never
        invalidated. The arm is pinned by shape rather than by a paramiko call
        site: see ``_EOFStream`` above for why no SFTP read path produces one.
        """
        stream = _ErrorMappingStream(_EOFStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            action(stream)

    def test_exception_chain_preserved(self) -> None:
        """Mapped exception preserves original via __cause__ (from exc)."""
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound) as exc_info:
            stream.read()
        assert isinstance(exc_info.value.__cause__, OSError)

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
        ],
    )
    def test_type_error_propagates(self, action) -> None:
        stream = _ErrorMappingStream(_FailingStream(TypeError), _test_mapper, "f.txt")
        with pytest.raises(TypeError, match="bad argument"):
            action(stream)

    def test_close_swallows_errors(self) -> None:
        stream = _ErrorMappingStream(_FailingCloseStream(), _test_mapper, "f.txt")
        stream.close()  # should not raise
        assert stream.closed


# ---------------------------------------------------------------------------
# Backend-supplied exception shapes (SIO-012, BK-358)
# ---------------------------------------------------------------------------


class _TransportError(Exception):
    """Stands for ``paramiko.SSHException``: neither ``OSError`` nor ``EOFError``.

    A local type rather than the real paramiko one. This module tests the shared
    wrapper, which does not know paramiko exists and is imported by backends that
    do not install it; reaching for the real class here would make a core unit
    test depend on an optional extra to assert something that is not about
    paramiko at all. The real shapes are driven end to end against a dropped
    socket in ``tests/backends/sftp/test_connection_drop.py``.
    """


class _OtherTransportError(Exception):
    """A second outside-the-base shape, used to prove a supplied set is not a blanket."""


class _TransportErrorStream(io.RawIOBase):
    """Raises *exc* on every mapping path.

    ``_FailingStream`` hardcodes ``OSError`` on ``readline``/``seek``/``tell``,
    so it cannot say whether the six ``except`` clauses agree with each other.
    SIO-012's postcondition is that they do, which needs one shape raised from
    all of them.
    """

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise self._exc

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise self._exc

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise self._exc

    def seek(self, offset: int, whence: int = 0) -> int:
        raise self._exc

    def tell(self) -> int:
        raise self._exc


_EVERY_MAPPING_PATH = [
    pytest.param(lambda s: s.read(), id="read"),
    pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
    pytest.param(lambda s: s.readline(), id="readline"),
    pytest.param(lambda s: s.seek(0), id="seek"),
    pytest.param(lambda s: s.tell(), id="tell"),
    pytest.param(lambda s: next(iter(s)), id="iteration"),
]
"""The six paths that map. Shared so a path added to the wrapper is added once here."""


class TestBackendSuppliedShapes:
    """The caught set is per-construction-site: base plus whatever the backend adds.

    The base is ``(OSError, EOFError)`` and was the *whole* bound until BK-358,
    which is why a dropped SFTP connection reached callers as a raw
    ``paramiko.SSHException`` — that shape subclasses neither arm, and
    ``SFTPClient._read_response`` produces it in place of the ``EOFError`` the
    base would have caught.

    **Both halves are pinned deliberately.** The widening is the fix; the
    *default staying exactly as it was* is what keeps the fix from reaching the
    five other construction sites the wrapper serves — S3 (fsspec, boto3,
    PyArrow), Azure (twice) and HTTP — none of which was measured to need it.
    """

    @pytest.mark.spec("SIO-012")
    @pytest.mark.parametrize("action", _EVERY_MAPPING_PATH)
    def test_a_supplied_shape_maps_on_every_path(self, action) -> None:
        """A supplied shape travels every mapping path, not only the reads.

        Parametrised across all six because the clauses are separate ``except``
        statements: a widening applied to ``read`` and ``readinto`` alone would
        satisfy the SFTP drop tests, which never seek or tell on a dead channel,
        while leaving ``seek``, ``tell`` and the probe still leaking.
        """
        stream = _ErrorMappingStream(
            _TransportErrorStream(_TransportError("connection dropped")),
            _test_mapper,
            "f.txt",
            also_catch=(_TransportError,),
        )
        with pytest.raises(NotFound, match="mapped"):
            action(stream)

    @pytest.mark.spec("SIO-012")
    @pytest.mark.parametrize("action", _EVERY_MAPPING_PATH)
    def test_without_a_supplied_set_the_same_shape_propagates(self, action) -> None:
        """The default is unchanged, which is what protects every other backend.

        The sibling above and this test differ in one argument. A regression that
        widened the base tuple instead of the per-site set would pass that one and
        fail this one, which is the only place that distinction is visible.
        """
        stream = _ErrorMappingStream(
            _TransportErrorStream(_TransportError("connection dropped")),
            _test_mapper,
            "f.txt",
        )
        with pytest.raises(_TransportError, match="connection dropped"):
            action(stream)

    @pytest.mark.spec("SIO-012")
    def test_a_supplied_set_is_not_a_blanket(self) -> None:
        """Supplying one shape must not start mapping every shape.

        The tempting fix for BK-358 was ``except Exception``, and the reason it
        was refused is that the wrapper deliberately lets programming errors
        through. This is the assertion that would catch that fix arriving by the
        back door — through a set built from ``Exception`` rather than from the
        types the backend named.
        """
        stream = _ErrorMappingStream(
            _TransportErrorStream(_OtherTransportError("something else")),
            _test_mapper,
            "f.txt",
            also_catch=(_TransportError,),
        )
        with pytest.raises(_OtherTransportError, match="something else"):
            stream.read()

    @pytest.mark.spec("SIO-012")
    def test_a_supplied_shape_still_propagates_a_programming_error(self) -> None:
        """Widening the set does not widen it to the errors that mean a bug.

        Sibling of ``test_type_error_propagates``, run against a stream that
        *does* supply a set — the clause it exercises is a different one, since a
        widened site was where a blanket catch would land first.
        """
        stream = _ErrorMappingStream(
            _TransportErrorStream(TypeError("bad argument")),
            _test_mapper,
            "f.txt",
            also_catch=(_TransportError,),
        )
        with pytest.raises(TypeError, match="bad argument"):
            stream.read()

    @pytest.mark.spec("SIO-012")
    def test_a_supplied_shape_preserves_the_exception_chain(self) -> None:
        """``raise ... from exc``, so the transport's own error survives for a reader.

        The mapped message is generic by construction; the ``__cause__`` is where
        "which paramiko failure was this" lives, and a caller debugging a drop has
        nothing else to read.
        """
        stream = _ErrorMappingStream(
            _TransportErrorStream(_TransportError("connection dropped")),
            _test_mapper,
            "f.txt",
            also_catch=(_TransportError,),
        )
        with pytest.raises(NotFound) as exc_info:
            stream.read()
        assert isinstance(exc_info.value.__cause__, _TransportError)

    @pytest.mark.spec("SIO-012")
    @pytest.mark.spec("SIO-010")
    def test_a_supplied_shape_reaches_the_futile_close_guard(self) -> None:
        """A supplied shape arms SIO-010's guard exactly as a base-tuple one does.

        The two clauses meet here: SIO-010 arms on what ``_fail`` sees, and
        SIO-012 decides what reaches ``_fail``. Before the widening the guard was
        inert on the shape a dropped connection actually takes, because nothing
        was mapped for it to be armed by.

        The predicate is local rather than the module's ``_fatal``, which matches
        ``_ChannelDeath`` — an ``OSError``, so the base set would have caught it
        and the supplied set would have decided nothing.
        """
        inner = _CloseTrackingStream(_TransportError("connection dropped"))
        stream = _ErrorMappingStream(
            inner,
            _test_mapper,
            "f.txt",
            is_fatal=lambda exc: isinstance(exc, _TransportError),
            also_catch=(_TransportError,),
        )

        with pytest.raises(NotFound, match="mapped"):
            stream.read()
        stream.close()

        assert inner.close_calls == 0, "a mapped fatal failure must skip the inner close"
        assert stream.closed


# ---------------------------------------------------------------------------
# Futile-close guard (SIO-010, BK-355)
# ---------------------------------------------------------------------------


class TestFutileCloseGuard:
    """A close that would re-enter a connection the failure condemned is skipped.

    The cost this exists to remove is a *second* blocking round-trip: paramiko's
    ``SFTPFile.close()`` issues a synchronous ``CMD_CLOSE`` and waits, so
    releasing a stream that already failed on a stalled channel pays the bound
    again — silently, since the close sits under ``contextlib.suppress``. What
    is asserted here is the skip itself; that it costs one bound rather than two
    is measured against a real stalled channel in
    ``tests/backends/sftp/test_io_timeout.py``.
    """

    @pytest.mark.spec("SIO-010")
    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
        ],
    )
    def test_a_fatal_failure_skips_the_inner_close(self, action) -> None:
        """Every mapping path arms the guard, not just the two a read goes through.

        Parametrised because the guard is per-path: an implementation recording
        the verdict in ``read``/``readinto`` only would leave the others unarmed,
        and this is the level at which that is a wrapper property.

        **What this does not claim.** These are wrapper-level cases against an
        inner stream that raises on demand; they do not say a real backend
        handle raises from all five. Against paramiko it does not: ``tell`` and a
        ``SEEK_SET`` / ``SEEK_CUR`` seek read ``_realpos`` locally and never
        round-trip, so a stalled channel neither blocks nor fails them. A
        ``SEEK_END`` seek does round-trip, and reaches ``_fail`` only because
        the wrapper resolves the size through its own probe rather than through
        paramiko's swallowing ``_get_size`` -- SIO-011, covered by
        ``TestSeekEndSizeProbe`` below and measured against a stalled channel by
        ``test_seek_to_end_on_a_stalled_channel_costs_one_bound``. The guard is
        written per-path because the *wrapper* serves several backends whose
        inner streams differ, not because every path is reachable on any one of
        them.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        with pytest.raises(NotFound):
            action(stream)
        stream.close()

        assert inner.close_calls == 0, "the close re-entered a connection already condemned"
        assert stream.closed, "the wrapper must still report itself closed"

    @pytest.mark.spec("SIO-010")
    def test_a_non_fatal_failure_still_closes(self) -> None:
        """The guard is narrow: only what the predicate condemns skips the close.

        A stream can fail for reasons a close survives, and on those the close is
        what releases the handle — so skipping on *any* mapped failure would
        trade a bounded wait for a leak.
        """
        inner = _CloseTrackingStream(OSError("transient read error"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        with pytest.raises(NotFound):
            stream.read()
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_without_a_predicate_a_failure_never_skips_the_close(self) -> None:
        """The default is the old behaviour, unconditionally.

        S3, S3-boto3, S3-PyArrow, Azure and HTTP all construct the wrapper
        without a predicate. This pins that their close is byte-for-byte what it
        was: the guard must be opt-in, not a default the shared wrapper applies
        on their behalf.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")

        with pytest.raises(NotFound):
            stream.read()
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_a_stream_that_never_failed_closes_normally(self) -> None:
        """Holding a predicate is not itself a reason to skip."""
        inner = _CloseTrackingStream(data=b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        assert stream.read() == b"hello"
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_a_raising_predicate_propagates(self) -> None:
        """A classifier that raises is a programming error, not a mapped failure.

        The wrapper's contract is that programming errors propagate, and a
        predicate is pure inspection — so a raising one is a bug in the backend.
        Suppressing it would substitute silence for the real failure and leave
        the guard's verdict unset with nothing to say so.
        """
        inner = _CloseTrackingStream(OSError("read failed"))

        def _broken(exc: Exception) -> bool:
            raise AttributeError("predicate is broken")

        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_broken)

        with pytest.raises(AttributeError, match="predicate is broken"):
            stream.read()

        # The other half of the docstring, and the half a mutation reaches: a
        # predicate that raised returned no verdict, so the guard must stay
        # unarmed and the close must still release the handle. An
        # implementation that re-raised but set the flag would leak here while
        # the assertion above still passed.
        stream.close()
        assert inner.close_calls == 1, "a predicate that raised must not arm the guard"

    @pytest.mark.spec("SIO-010")
    def test_the_guard_survives_the_buffered_layer(self) -> None:
        """SFTP hands back ``BufferedReader(_ErrorMappingStream(...))``.

        The caller therefore never closes the wrapper directly — the buffer
        does, on its raw. A guard that only held when closed directly would be
        armed on the one construction no SFTP caller has.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        raw = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)
        buffered = io.BufferedReader(cast("io.RawIOBase", raw))

        with pytest.raises(NotFound):
            buffered.read()
        buffered.close()

        assert inner.close_calls == 0
        assert raw.closed


# ---------------------------------------------------------------------------
# SEEK_END size probe (SIO-011, BK-357)
# ---------------------------------------------------------------------------


class TestSeekEndSizeProbe:
    """``SEEK_END`` resolves through the wrapper's own probe, not the inner stream's.

    The defect this closes has two halves and the second is the worse one.  An
    inner stream that sizes itself over the wire and swallows the failure leaves
    the wrapper with nothing to map: the futile-close guard stays unarmed, *and*
    the seek answers ``0`` on a file of any size, which a caller cannot tell
    from an empty file.  Both halves are asserted here at wrapper level; that a
    stalled channel then costs one bound rather than two is measured against a
    real stalled channel in ``tests/backends/sftp/test_io_timeout.py``.
    """

    @pytest.mark.spec("SIO-011")
    def test_a_failing_probe_raises_where_the_inner_seek_would_have_answered(self) -> None:
        """The wrong-answer half: the same stream answers ``0`` without the hook."""
        inner = _ParamikoSeekEndStream(b"0123456789", stat_exc=_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)

        with pytest.raises(NotFound, match="mapped"):
            stream.seek(0, io.SEEK_END)

        assert inner.seek_calls == [], "the inner seek must not run once the probe has failed"

    @pytest.mark.spec("SIO-011")
    def test_a_failing_probe_arms_the_futile_close_guard(self) -> None:
        """The doubled-wait half: the probe's failure reaches ``_fail`` like a read's.

        Asserted separately from the raise above because they are different
        properties — an implementation that mapped the failure but recorded no
        verdict would satisfy the first and leave the close paying the bound
        again, which is the cost SIO-010 exists to remove.
        """
        inner = _ParamikoSeekEndStream(b"0123456789", stat_exc=_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)

        with pytest.raises(NotFound):
            stream.seek(0, io.SEEK_END)
        stream.close()

        assert inner.close_calls == 0, "the close re-entered a connection already condemned"
        assert stream.closed, "the wrapper must still report itself closed"

    @pytest.mark.spec("SIO-011")
    def test_without_a_probe_the_inner_swallow_still_answers(self) -> None:
        """The hook is opt-in, and this is the behaviour every other stream keeps.

        The six non-SFTP construction sites supply no probe, and none of them
        resolves ``SEEK_END`` by a request it could then discard -- SIO-011
        enumerates the routes they take instead. Deliberately not restated here:
        that enumeration has been wrong in three successive review rounds, once
        in each artifact that copied it, so this docstring links rather than
        paraphrases (CONTENT-RULES rule 4).

        What matters at this level is only that the wrapper does not start
        probing on their behalf, which is what this pins, on the same shape
        ``test_without_a_predicate_a_failure_never_skips_the_close`` pins for the
        close.
        """
        inner = _ParamikoSeekEndStream(b"0123456789", stat_exc=_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        assert stream.seek(0, io.SEEK_END) == 0, "without the hook the inner swallow is unchanged"
        assert inner.seek_calls == [(0, io.SEEK_END)], "the whence must reach the inner stream intact"
        stream.close()
        assert inner.close_calls == 1, "nothing was mapped, so nothing may skip the close"

    @pytest.mark.spec("SIO-011")
    @pytest.mark.parametrize(
        ("offset", "expected"),
        [
            pytest.param(0, 10, id="end"),
            pytest.param(-4, 6, id="negative-offset"),
            pytest.param(-10, 0, id="whole-file"),
        ],
    )
    def test_a_healthy_probe_positions_relative_to_the_probed_size(self, offset: int, expected: int) -> None:
        """The case that always worked must keep working, negative offsets included.

        Parametrised over a negative offset as well as ``0`` because the offset
        arithmetic is the wrapper's own: ``seek(0, SEEK_END)`` alone would pass
        against an implementation that dropped the caller's offset entirely.
        """
        inner = _ParamikoSeekEndStream(b"0123456789")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)

        assert stream.seek(offset, io.SEEK_END) == expected
        assert inner.seek_calls == [(expected, io.SEEK_SET)], (
            "the wrapper must resolve the target itself and delegate an absolute seek, "
            "which is local on a paramiko handle -- delegating SEEK_END would round-trip twice"
        )
        assert inner.stat_calls == 1, "one probe per seek, not one per layer"

    @pytest.mark.spec("SIO-011")
    @pytest.mark.parametrize(
        "whence",
        [pytest.param(io.SEEK_SET, id="seek-set"), pytest.param(io.SEEK_CUR, id="seek-cur")],
    )
    def test_a_local_seek_never_probes(self, whence: int) -> None:
        """``SEEK_SET`` / ``SEEK_CUR`` are local on a paramiko handle; probing them would add a round-trip."""
        inner = _ParamikoSeekEndStream(b"0123456789")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)

        stream.seek(3, whence)

        assert inner.stat_calls == 0
        assert inner.seek_calls == [(3, whence)]

    @pytest.mark.spec("SIO-011")
    def test_the_probe_survives_the_buffered_layer(self) -> None:
        """SFTP hands back ``BufferedReader(_ErrorMappingStream(...))``.

        No SFTP caller holds the wrapper directly, so a probe wired only for the
        bare construction would be armed on the one shape nobody has.  The
        sibling of ``test_the_guard_survives_the_buffered_layer``.
        """
        inner = _ParamikoSeekEndStream(b"0123456789", stat_exc=_ChannelDeath("channel stalled"))
        raw = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)
        buffered = io.BufferedReader(cast("io.RawIOBase", raw))

        with pytest.raises(NotFound):
            buffered.seek(0, io.SEEK_END)
        buffered.close()

        assert inner.close_calls == 0
        assert raw.closed

    @pytest.mark.spec("SIO-011")
    @pytest.mark.spec("SIO-012")
    def test_a_probe_failure_is_bounded_by_the_same_set_as_every_other_path(self) -> None:
        """The probe follows the site's caught set — it neither leads nor lags it.

        This pinned the opposite outcome until BK-358. SIO-011 bounded the probe
        by the base ``(OSError, EOFError)`` on purpose, so a ``paramiko.SFTPError``
        escaped the probe unmapped exactly as one escaped a read; widening for the
        probe alone would have made one path better than the rest with no clause
        saying why. SIO-012 answered the question a site at a time instead, and
        the probe moved with it — which is the property worth pinning, because
        it is the one a later edit could break in either direction.

        Both directions are asserted for that reason: supplied maps, unsupplied
        propagates, one stream shape and one argument between them.
        """
        supplied = _ParamikoSeekEndStream(b"0123456789", stat_exc=_TransportError("garbage packet"))
        stream = _ErrorMappingStream(
            supplied,
            _test_mapper,
            "f.txt",
            is_fatal=lambda exc: isinstance(exc, _TransportError),
            size_probe=_stat_size_probe,
            also_catch=(_TransportError,),
        )
        with pytest.raises(NotFound, match="mapped"):
            stream.seek(0, io.SEEK_END)
        stream.close()
        assert supplied.close_calls == 0, "the mapped failure was fatal, so the close must be skipped"

        unsupplied = _ParamikoSeekEndStream(b"0123456789", stat_exc=_TransportError("garbage packet"))
        bare = _ErrorMappingStream(unsupplied, _test_mapper, "f.txt", is_fatal=_fatal, size_probe=_stat_size_probe)
        with pytest.raises(_TransportError, match="garbage packet"):
            bare.seek(0, io.SEEK_END)
        bare.close()
        assert unsupplied.close_calls == 1, "nothing was mapped, so the guard must stay unarmed"


# ---------------------------------------------------------------------------
# _safe_wrap tests (BUG-159)
# ---------------------------------------------------------------------------


class _TrackingStream(io.RawIOBase):
    """Stream that tracks whether close() was called.

    Extends RawIOBase (not BytesIO) so it can be wrapped in
    ``io.BufferedReader`` on Python 3.14+ which enforces the
    RawIOBase requirement.
    """

    def __init__(self, data: bytes = b"hello") -> None:
        super().__init__()
        self._buf = io.BytesIO(data)
        self.was_closed = False

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def close(self) -> None:
        self.was_closed = True
        super().close()


class TestSafeWrap:
    """Tests for the _safe_wrap helper."""

    @pytest.mark.spec("BUG-159")
    def test_successful_wrap(self) -> None:
        raw = _TrackingStream()
        result = _safe_wrap(raw, lambda s: io.BufferedReader(s))
        assert isinstance(result, io.BufferedReader)
        assert not raw.was_closed

    @pytest.mark.spec("BUG-159")
    def test_wrapper_failure_closes_raw(self) -> None:
        """If a wrapper raises, the raw handle is closed (BUG-159 fix)."""
        raw = _TrackingStream()

        def failing_wrapper(s: object) -> io.BytesIO:
            raise RuntimeError("wrapping failed")

        with pytest.raises(RuntimeError, match="wrapping failed"):
            _safe_wrap(raw, failing_wrapper)

        assert raw.was_closed, "Raw stream must be closed when wrapper fails"

    @pytest.mark.spec("BUG-159")
    def test_multi_layer_wrap(self) -> None:
        raw = _TrackingStream()
        result = _safe_wrap(
            raw,
            lambda s: _ErrorMappingStream(s, _test_mapper, "f.txt"),
            lambda s: io.BufferedReader(s),
        )
        assert isinstance(result, io.BufferedReader)
        assert not raw.was_closed

    @pytest.mark.spec("BUG-159")
    def test_second_wrapper_failure_closes_all(self) -> None:
        """If the second wrapper fails, both the first wrapper and raw are closed."""
        raw = _TrackingStream()
        first_layer_closed = []

        class _TrackingWrapper(io.RawIOBase):
            def __init__(self, inner: object) -> None:
                self._inner = inner

            def close(self) -> None:
                first_layer_closed.append(True)
                super().close()

            def readable(self) -> bool:
                return True

            def readinto(self, b: bytearray | memoryview) -> int:
                return 0

        def second_fails(s: object) -> io.BytesIO:
            raise ValueError("second layer failed")

        with pytest.raises(ValueError, match="second layer failed"):
            _safe_wrap(raw, _TrackingWrapper, second_fails)

        assert raw.was_closed
        assert first_layer_closed, "First wrapper layer must also be closed"
