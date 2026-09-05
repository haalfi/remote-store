"""Error-mapping stream wrapper for lazy reads."""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from remote_store._errors import RemoteStoreError


def _safe_wrap(raw: Any, *wrappers: Callable[..., Any]) -> Any:
    """Apply *wrappers* in order, closing *raw* if any wrapper fails.

    Each wrapper receives the result of the previous one.  If a wrapper
    raises, every successfully-created layer (plus *raw*) is closed so
    that the underlying resource does not leak.

    >>> wrapped = _safe_wrap(raw_handle, error_mapper, buffered_reader)
    """
    layers: list[Any] = [raw]
    try:
        for wrapper in wrappers:
            layers.append(wrapper(layers[-1]))
        return layers[-1]
    except BaseException:
        # Close in reverse (outer-first) order.  Outer wrappers delegate
        # close() to inner layers, so inner layers may be closed twice;
        # this is safe because close() is idempotent on IO base classes.
        for layer in reversed(layers):
            with contextlib.suppress(Exception):
                layer.close()
        raise


class _ErrorMappingStream(io.RawIOBase):
    """Wraps a BinaryIO stream and maps I/O exceptions through a classifier.

    When the caller reads from a stream returned by ``Backend.read()``, the
    backend's ``_errors()`` context manager has already exited, so a native
    ``OSError`` -- or an ``EOFError``, which is *not* an ``OSError`` -- would
    otherwise leak unmapped.  This wrapper intercepts I/O methods and passes
    both through the backend's error classifier so callers see
    ``RemoteStoreError`` subtypes.

    **The caught tuple is the real bound here, and it is narrower than the
    backends this serves.**  Only ``(OSError, EOFError)`` are intercepted, so
    anything outside that pair propagates unmapped.  On paramiko's SFTP read
    path neither arm catches a dropped connection: the read side converts its
    ``EOFError`` to ``SSHException``, and a send-side ``EOFError`` is swallowed
    by ``BufferedFile.read`` into a short read before it reaches this wrapper
    (both measured).  A stalled channel *is* caught, as ``socket.timeout`` is
    an ``OSError``.  Which producer does reach the ``EOFError`` arm is
    undetermined -- do not read it as covering a specific paramiko path, and do
    not narrow the tuple on the strength of that.

    Programming errors (``TypeError``, ``ValueError``, ``AttributeError``, etc.)
    are **not** caught -- they propagate normally.  That includes anything
    *is_fatal* raises: a classifier is pure inspection, so one that raises is a
    bug in the backend, and suppressing it would replace the real failure with
    silence.

    **Releasing a stream whose failure condemned the connection.**
    ``close`` closes *inner* under ``contextlib.suppress``, and on a connection
    the failure already killed that close is not free: paramiko's
    ``SFTPFile.close()`` issues a synchronous ``CMD_CLOSE`` and waits for a reply
    that never comes, so the caller pays ``io_timeout`` a second time with
    nothing to explain the wait.  A backend that can recognise such a failure
    passes *is_fatal*; once it returns ``True`` for a mapped exception, the inner
    close is skipped.  The handle is then released by the peer's own teardown, or
    at collection **of this wrapper** -- ``close`` does not drop ``_inner``, so
    the handle stays reachable through it for as long as the closed stream
    object itself is held.  For paramiko, that collection runs
    ``SFTPFile.__del__`` -> ``_close(async_=True)``, which sends ``CMD_CLOSE``
    without waiting.  A caller that retains closed streams therefore retains
    the dead connection with them; the backend has already dropped its own
    reference by then, so this wrapper is what keeps the transport alive.

    The verdict is taken when the failure is mapped rather than at close time, so
    the stream records a ``bool`` instead of holding the exception: keeping the
    exception would keep its traceback, and the frames it references, alive for
    as long as the stream is.

    **Sizing a stream for a ``SEEK_END`` seek.**  Some inner streams answer
    ``seek(offset, SEEK_END)`` by asking the remote for a size, and can swallow
    that request's failure: paramiko's ``SFTPFile.seek`` delegates to
    ``_get_size()``, whose whole body is ``try: return self.stat().st_size``
    under a bare ``except: return 0``.  A stalled channel therefore made the
    seek *answer* ``0`` on a file of any size while raising nothing, so nothing
    reached ``_fail``, the guard above stayed unarmed, and the close paid the
    bound a second time.  A backend whose handle behaves that way passes
    *size_probe*; the wrapper then resolves the size itself and delegates an
    absolute seek, so the failure travels the ordinary mapping path.

    That probe is bounded by the same caught tuple as every other path, which
    is deliberate: a ``paramiko.SFTPError`` raised by the probe escapes unmapped
    exactly as one raised by a read does.  Widening the tuple for the probe
    alone would make one path better than the rest with no reason saying why --
    what that tuple should catch is a separate question from this one.

    Args:
        inner: The underlying stream to wrap.
        mapper: ``(Exception, str) -> RemoteStoreError`` callable.
        path: The logical path, forwarded to *mapper* for diagnostics.
        is_fatal: Optional ``(Exception) -> bool`` predicate deciding whether a
            failure leaves the underlying connection unusable.  Omitted by
            backends whose streams fail for reasons a close survives, and for
            them the close stays unconditional.  It **must be pure inspection
            of the exception** -- no I/O, no round-trip: it is called on the
            failure path of a connection that may already be dead, so a probe
            inside it would pay the very wait this guard exists to remove.
        size_probe: Optional ``(inner) -> int`` callable returning the size of
            *inner*, used to resolve ``SEEK_END``.  Unlike *is_fatal* this one
            **is** a round-trip, and it is called on the success path before any
            failure is known.  Supply it only for an inner stream that resolves
            ``SEEK_END`` by a request it can then discard -- paramiko's
            ``SFTPFile`` is the one measured to do so.  Every other stream this
            wrapper serves reaches ``SEEK_END`` by some route with no such
            request in it, so all of them omit the probe and their seek
            delegates exactly as before; no stream pays a probe on another's
            behalf.  The routes themselves are enumerated once, in the spec --
            not here, because paraphrasing that list is what made it wrong in
            three successive reviews.
    """

    def __init__(
        self,
        inner: Any,
        mapper: Callable[[Exception, str], RemoteStoreError],
        path: str,
        *,
        is_fatal: Callable[[Exception], bool] | None = None,
        size_probe: Callable[[Any], int] | None = None,
    ) -> None:
        self._inner = inner
        self._mapper = mapper
        self._path = path
        self._is_fatal = is_fatal
        self._size_probe = size_probe
        self._connection_lost = False

    def _fail(self, exc: Exception) -> RemoteStoreError:
        """Map *exc*, recording whether it leaves the connection unusable.

        Every mapping path goes through here, so ``seek`` and ``tell`` arm the
        guard exactly as a read does.
        """
        if self._is_fatal is not None and self._is_fatal(exc):
            self._connection_lost = True
        return self._mapper(exc, self._path)

    # region: RawIOBase required
    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        try:
            return cast(int, self._inner.readinto(b))  # noqa: TC006
        except (OSError, EOFError) as exc:
            raise self._fail(exc) from exc

    # endregion

    # region: optional but expected
    def read(self, size: int = -1) -> bytes | None:
        try:
            data = self._inner.read(size)
            return cast(bytes | None, data)  # noqa: TC006
        except (OSError, EOFError) as exc:
            raise self._fail(exc) from exc

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        try:
            data = self._inner.readline(size)
            return cast(bytes, data)  # noqa: TC006
        except (OSError, EOFError) as exc:
            raise self._fail(exc) from exc

    def seek(self, offset: int, whence: int = 0) -> int:
        try:
            if whence == io.SEEK_END and self._size_probe is not None:
                # SIO-010/SIO-011: resolve the end ourselves so a failed size
                # request reaches ``_fail`` instead of being swallowed by the
                # inner stream. The delegated seek is absolute, which is local
                # on a paramiko handle -- delegating SEEK_END would round-trip
                # a second time.
                result = self._inner.seek(self._size_probe(self._inner) + offset, io.SEEK_SET)
            else:
                result = self._inner.seek(offset, whence)
            # paramiko SFTPFile.seek() returns None
            if result is None:
                return self._inner.tell() or 0
            return int(result)
        except (OSError, EOFError) as exc:
            raise self._fail(exc) from exc

    def seekable(self) -> bool:
        return bool(getattr(self._inner, "seekable", lambda: False)())

    def tell(self) -> int:
        try:
            result = self._inner.tell()
            # paramiko SFTPFile.tell() should return int, but guard anyway
            return int(result) if result is not None else 0
        except (OSError, EOFError) as exc:
            raise self._fail(exc) from exc

    def close(self) -> None:
        if not self.closed:
            # SIO-010: skip a close that would re-enter a connection this
            # stream's own failure condemned -- see the class docstring.
            if not self._connection_lost:
                with contextlib.suppress(Exception):
                    self._inner.close()
            super().close()

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        try:
            line = self.readline()
            if not line:
                raise StopIteration
            return line
        except StopIteration:
            raise
        except (OSError, EOFError) as exc:  # defensive: readline() already maps these  # pragma: no cover
            raise self._fail(exc) from exc

    # endregion
