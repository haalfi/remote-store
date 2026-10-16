"""The sync contract kernel: the generated shared core plus the sync-only members.

``DriverBackend`` is ``Backend`` over a sync ``Driver``. Everything both
runtimes share is ``_sync.kernel._KernelCore``, generated from the async
source. This module adds what only the sync surface has: a
``BinaryIO`` ``read``, ``read_seekable`` and ``open_atomic``.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
from typing import TYPE_CHECKING, BinaryIO, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability
from remote_store._errors import RemoteStoreError
from remote_store._kernel._model import Op
from remote_store._kernel._sync.kernel import _KernelCore
from remote_store._stream import _ErrorMappingStream, _safe_wrap

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from types import TracebackType

    from remote_store._kernel._sync.driver import SupportsRangeRead, WriteHandle

_SPOOL_MAX = 8 * 1024 * 1024


class DriverBackend(_KernelCore, Backend):
    """``Backend`` implemented once, over a sync driver.

    Construct it with a built driver, usually from the ``__init__`` of a
    subclass that builds its own.

    Args:
        driver: The built driver.

    Raises:
        ValueError: If the driver's declarations are not backed by its
            protocols, it is flat and has folder objects, it has explicit
            parents and no ``ensure_parents``, it has folder objects and no
            ``remove_folder``, the class's own ``close_is_terminal``
            differs from the driver's, or a primitive is missing or, other
            than ``probe``, is the protocol's own body.
    """

    def read(self, path: str) -> BinaryIO:
        """Open the file at *path*; its stream maps errors through the choke point."""
        key, stream = self._open(path, Op.READ)
        driver = self._driver

        def mapper(exc: Exception, _path: str) -> RemoteStoreError:
            return self._mapped(exc, Op.READ, key)

        wrapped = _safe_wrap(
            stream,
            lambda raw: _ErrorMappingStream(
                raw,
                mapper,
                key,
                is_fatal=driver.connection_dead,  # SIO-010: no second wait on a condemned connection
                size_probe=getattr(driver, "size_probe", None),
                also_catch=tuple(getattr(driver, "stream_catch", ())),
            ),
        )
        return cast("BinaryIO", wrapped)

    def read_seekable(self, path: str) -> BinaryIO:
        """Ranged reads where the driver has them; else the spool over ``read``."""
        if self._range is None:
            return Backend.read_seekable(self, path)
        self._guard()
        key = self._file_key(path)
        entry = self._file_entry(Op.READ_SEEKABLE, key)
        return cast("BinaryIO", _RangeReader(self, self._range, key, entry.size))

    def open_atomic(self, path: str, *, overwrite: bool = False) -> AbstractContextManager[BinaryIO]:
        """A temporary promoted to *path* on exit: on the wire, or spooled then written atomically."""
        # The declared capability decides, ahead of the closed guard and the key
        # rule (BE-030); construction guarantees a route behind it.
        self._require(Capability.ATOMIC_WRITE, path, "cannot write atomically")
        self._guard()
        key = self._write_key(path)
        if self._open_write is not None:
            return _HandleWriter(self, key, overwrite)
        return _SpoolThenWrite(self, key, overwrite)


class _RangeReader(io.RawIOBase):
    """A seekable stream over ``get_range``; every read passes the choke point."""

    def __init__(self, core: DriverBackend, ranged: SupportsRangeRead, key: str, size: int) -> None:
        super().__init__()
        self._core, self._ranged, self._key, self._size = core, ranged, key, size
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        target = base + offset
        if target < 0:
            raise ValueError(f"negative seek position {target}")
        self._pos = target
        return target

    def _fetch(self, want: int) -> bytes:
        with self._core._choke(Op.READ_SEEKABLE, self._key):
            data = self._ranged.get_range(self._key, self._pos, want)
        self._pos += len(data)
        return data

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        want = min(len(buffer), max(self._size - self._pos, 0))
        if not want:
            return 0
        data = self._fetch(want)
        buffer[: len(data)] = data
        return len(data)

    def readall(self) -> bytes:
        """The rest of the file: one ranged request, repeated only after a short answer.

        ``get_range`` may return fewer bytes than asked, so the rest is asked
        for again until it has all arrived or an answer comes back empty.
        """
        chunks: list[bytes] = []
        while (want := self._size - self._pos) > 0:
            data = self._fetch(want)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)


class _HandleStream(io.RawIOBase):
    """The writable face of a driver's wire temporary: forward-only, so it tells but never seeks."""

    def __init__(self, core: DriverBackend, handle: WriteHandle, key: str) -> None:
        super().__init__()
        self._core, self._handle, self._key = core, handle, key
        self._pos = 0

    def writable(self) -> bool:
        return True

    def tell(self) -> int:
        """Bytes written so far; the stream is not seekable."""
        self._checkClosed()
        return self._pos

    def write(self, data: bytes | bytearray | memoryview) -> int:  # type: ignore[override]
        self._checkClosed()
        # memoryview refuses what is not a buffer (an int, a list, a str) with TypeError,
        # where bytes() would turn an int into that many NUL bytes. A buffer that is not
        # C-contiguous is refused as Python's own binary files refuse it, so this route
        # and the spool route answer alike.
        view = memoryview(data)
        if not view.c_contiguous:
            raise BufferError("memoryview: underlying buffer is not C-contiguous")
        chunk = view.tobytes()
        with self._core._choke(Op.OPEN_ATOMIC, self._key):
            self._handle.write(chunk)
        self._pos += len(chunk)
        return len(chunk)


class _HandleWriter:
    """``open_atomic`` over ``open_write``: commit on success, abort on any error."""

    __slots__ = ("_core", "_handle", "_key", "_overwrite")

    def __init__(self, core: DriverBackend, key: str, overwrite: bool) -> None:
        self._core, self._key, self._overwrite = core, key, overwrite
        self._handle: WriteHandle | None = None

    def __enter__(self) -> BinaryIO:
        core = self._core
        assert core._open_write is not None
        core._prepare_write(Op.OPEN_ATOMIC, self._key)
        try:
            with core._choke(Op.OPEN_ATOMIC, self._key):
                self._handle = core._open_write.open_write(self._key, overwrite=self._overwrite, metadata=None)
        except RemoteStoreError as err:
            core._write_refused(err, Op.OPEN_ATOMIC, self._key, self._overwrite)
            raise
        return cast("BinaryIO", _HandleStream(core, self._handle, self._key))

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        handle, self._handle = self._handle, None
        assert handle is not None
        if exc is not None:
            with contextlib.suppress(Exception):
                handle.abort()
            return
        try:
            with self._core._choke(Op.OPEN_ATOMIC, self._key):
                handle.commit()
        except BaseException as err:
            with contextlib.suppress(Exception):
                handle.abort()
            if isinstance(err, RemoteStoreError):
                self._core._write_refused(err, Op.OPEN_ATOMIC, self._key, self._overwrite)
            raise


class _SpoolThenWrite:
    """``open_atomic`` without a wire temporary: spool locally, then ``write_atomic``.

    The async-to-sync adapter's synthesis (``_SpoolAndFlush``), over the kernel's own
    ``write_atomic``: a caller error leaves *key* untouched.
    """

    __slots__ = ("_core", "_key", "_overwrite", "_spool")

    def __init__(self, core: DriverBackend, key: str, overwrite: bool) -> None:
        self._core, self._key, self._overwrite = core, key, overwrite
        self._spool: BinaryIO | None = None

    def __enter__(self) -> BinaryIO:
        self._spool = cast("BinaryIO", tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX))  # noqa: SIM115
        return self._spool

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        spool, self._spool = self._spool, None
        assert spool is not None
        try:
            if exc is None:
                spool.seek(0)
                # The spool is the kernel's own, not the caller's content, so it is
                # not marked: its failure is a native error the choke point maps.
                self._core._write_atomic(self._key, spool, overwrite=self._overwrite, metadata=None, caller=False)
        finally:
            with contextlib.suppress(Exception):
                spool.close()
