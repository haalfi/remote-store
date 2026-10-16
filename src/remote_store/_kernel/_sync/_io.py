"""Where the sync runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_async/_io.py`` is its counterpart, with the
same names. The generated modules beside this one import these. Neither
imports the driver module, which imports them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

#: What ``get`` returns: the sync driver hands back a binary stream.
ReadStream = BinaryIO
#: What ``put`` and ``write_atomic`` accept.
Content = BinaryIO | bytes

_CHUNK = 256 * 1024


class _Writable(Protocol):
    """The part of a driver's write handle ``feed`` uses."""

    def write(self, data: bytes) -> None: ...


def read_all(stream: ReadStream) -> bytes:
    """Drain *stream* into one ``bytes`` and close it."""
    try:
        return stream.read()
    finally:
        close_stream(stream)


def close_stream(stream: object) -> None:
    """Close a stream the kernel opened, if it can be closed."""
    close = getattr(stream, "close", None)
    if close is not None:
        close()


_FROM_CONTENT = "_remote_store_from_content"


def from_content(exc: BaseException) -> bool:
    """Whether *exc* was raised by the caller's own content, not by the wire."""
    return bool(exc.__dict__.get(_FROM_CONTENT, False))


def _mark(exc: BaseException) -> None:
    # Into the instance dict, which every exception has: a class whose own
    # __setattr__ refuses new attributes is marked too.
    exc.__dict__[_FROM_CONTENT] = True


#: The stream's reads, each forwarded with its failures marked.
_READS = frozenset({"read", "read1", "readall", "readinto", "readinto1", "readline", "readlines", "peek"})
#: The reads that answer bytes, whose answer must be binary.
_BYTE_READS = frozenset({"read", "read1", "readall", "readline", "peek"})


def _binary(chunk: object, source: object) -> object:
    """*chunk* as ``bytes`` when it is a buffer; a caller-marked ``TypeError`` when it is not binary.

    ``None``, a non-blocking raw stream's "no data yet", is refused too: a
    driver's read loop would take it for the end and store a truncated file.
    """
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, bytearray | memoryview):
        try:
            return bytes(chunk)
        except Exception as err:  # a buffer that cannot be read, such as a released memoryview
            _mark(err)
            raise
    exc = TypeError(f"content stream {type(source).__name__} returned {type(chunk).__name__}, not bytes")
    _mark(exc)
    raise exc


def _count(answer: object, source: object) -> object:
    """*answer* when ``readinto`` answered a count; a caller-marked ``TypeError`` otherwise.

    ``None``, a non-blocking raw stream's "no data yet", is refused like a
    ``None`` read: a driver's loop would take it for the end.
    """
    if isinstance(answer, int):
        return answer
    exc = TypeError(f"content stream {type(source).__name__} readinto returned {type(answer).__name__}, not a count")
    _mark(exc)
    raise exc


def _lines(answer: object, source: object) -> list[object]:
    """*answer* when ``readlines`` answered a list; a caller-marked ``TypeError`` otherwise."""
    if isinstance(answer, list):
        return answer
    exc = TypeError(f"content stream {type(source).__name__} readlines returned {type(answer).__name__}, not a list")
    _mark(exc)
    raise exc


def take_content(content: object) -> Content:
    """*content* as the kernel passes it on, converted or refused after the metadata gate and before any I/O.

    A ``bytearray`` or ``memoryview`` becomes a copy as ``bytes`` here, so a
    buffer that cannot be read fails at the same rank as content that is
    neither a buffer nor a readable stream, which is a ``TypeError``.
    """
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray | memoryview):
        return bytes(content)
    if callable(getattr(content, "read", None)):
        return cast("BinaryIO", content)
    msg = f"content must be bytes or a readable binary stream, not {type(content).__name__}"
    raise TypeError(msg)


class _MarkedReader:
    """The caller's stream, with whatever its reads raise marked as the caller's.

    What a read answers is checked too: a buffer becomes ``bytes``, an answer
    that is not binary (``None`` included) is a caller-marked ``TypeError``,
    and so is a ``readinto`` answer that is not a count or a ``readlines``
    answer that is not a list. Every ordinary attribute is the stream's own, so one the
    stream lacks is absent here too; a read among them is forwarded with its
    failures marked. An unsized ``read`` and an argument-free ``readall`` are
    read here in sized chunks instead: a raw stream's own ``readall`` stops at a ``None`` this
    proxy would never see, so a driver reading in full would store a
    truncated file. Line reads loop inside the stream and are not covered. It
    is a proxy, not an ``io.IOBase``: Python looks special methods up on the
    type, so none is forwarded (``hasattr`` would answer for an operation that
    fails), and iteration (as an iterator when the stream is one) and ``with``
    are present only when the stream's type supports them (``_proxy_type``).
    """

    __slots__ = ("_stream",)

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def __getattr__(self, name: str) -> object:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        attr = getattr(self._stream, name)
        if name not in _READS:
            return attr

        def marked(*args: object, **kwargs: object) -> object:
            if (name == "readall" and not args and not kwargs) or (name == "read" and _unsized(args, kwargs)):
                return self._read_whole(by_keyword="size" in kwargs)
            try:
                answer = attr(*args, **kwargs)
            except Exception as exc:
                _mark(exc)
                raise
            if name in _BYTE_READS:
                return _binary(answer, self._stream)
            if name == "readlines":
                return [_binary(line, self._stream) for line in _lines(answer, self._stream)]
            return _count(answer, self._stream)  # readinto, readinto1

        return marked

    def _read_whole(self, *, by_keyword: bool) -> bytes:
        """The rest of the stream, by checked sized reads until one answers empty.

        Each read spells its size as the caller did, so a stream that refuses
        ``size=`` refuses it here too. The chunks are joined, so the content is
        held twice at the end, where a file's own ``read()`` holds it once:
        growing one buffer instead held it a little less and took several
        times as long.
        """
        chunks: list[bytes] = []
        while True:
            try:
                # typing's BinaryIO.read names no size parameter; io's streams take it positionally.
                answer = cast("Any", self._stream).read(size=_CHUNK) if by_keyword else self._stream.read(_CHUNK)
            except Exception as exc:
                _mark(exc)
                raise
            chunk = cast("bytes", _binary(answer, self._stream))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def _unsized(args: tuple[object, ...], kwargs: dict[str, object]) -> bool:
    """Whether a ``read`` call asks for everything: no size, ``None`` or a negative one.

    Any other call, a keyword other than ``size`` or a keyword beside a
    positional size, is the stream's own to answer, so it is forwarded.
    """
    if args and not kwargs and len(args) == 1:
        size = args[0]
    elif not args and set(kwargs) == {"size"}:
        size = kwargs["size"]
    else:
        return not args and not kwargs
    return size is None or (isinstance(size, int) and size < 0)


class _MarkedIteration:
    __slots__ = ()
    _stream: BinaryIO

    def __iter__(self) -> Iterator[bytes]:
        try:
            lines = iter(self._stream)
        except Exception as exc:
            _mark(exc)
            raise
        while True:
            try:
                line = next(lines)
            except StopIteration:
                return
            except Exception as exc:
                _mark(exc)
                raise
            yield cast("bytes", _binary(line, self._stream))


class _MarkedIterator:
    """For a stream that is its own iterator (every ``io`` stream): so is the proxy."""

    __slots__ = ()
    _stream: BinaryIO

    def __iter__(self) -> _MarkedIterator:
        return self

    def __next__(self) -> bytes:
        try:
            line = next(self._stream)
        except StopIteration:
            raise
        except Exception as exc:
            _mark(exc)
            raise
        return cast("bytes", _binary(line, self._stream))


class _ForwardedContext:
    __slots__ = ()
    _stream: BinaryIO

    def __enter__(self) -> _ForwardedContext:
        try:
            self._stream.__enter__()
        except Exception as exc:
            _mark(exc)
            raise
        return self

    def __exit__(self, *exc_info: object) -> object:
        try:
            return self._stream.__exit__(*exc_info)  # type: ignore[arg-type]
        except Exception as exc:
            # The exception the with-body raised, re-raised, is the driver's own.
            if exc is not exc_info[1]:
                _mark(exc)
            raise


_PROXY_TYPES: dict[tuple[type | None, bool], type[_MarkedReader]] = {}


def _proxy_type(stream: object) -> type[_MarkedReader]:
    kind = type(stream)
    iteration: type | None = None
    if hasattr(kind, "__iter__"):
        iteration = _MarkedIterator if hasattr(kind, "__next__") else _MarkedIteration
    shape = (iteration, hasattr(kind, "__enter__") and hasattr(kind, "__exit__"))
    proxy = _PROXY_TYPES.get(shape)
    if proxy is None:
        bases = ((iteration,) if iteration else ()) + (_ForwardedContext,) * shape[1] + (_MarkedReader,)
        proxy = type("_MarkedReader", bases, {"__slots__": ()}) if len(bases) > 1 else _MarkedReader
        _PROXY_TYPES[shape] = proxy
    return proxy


def guard_content(content: Content) -> Content:
    """*content* with the caller's stream marked: what its reads raise is the caller's.

    The choke point passes a marked error through verbatim: a failing source
    the caller handed in is not a wire error to classify. What the stream's
    reads answer is converted and checked as ``_MarkedReader`` describes. A
    buffer, or anything without ``read``, is returned as it is:
    ``take_content`` converts or refuses it, at its own rank.
    """
    if isinstance(content, bytes | bytearray | memoryview) or not callable(getattr(content, "read", None)):
        return content
    return cast("BinaryIO", _proxy_type(content)(content))


def feed(handle: _Writable, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes):
        handle.write(content)
        return
    while chunk := content.read(_CHUNK):
        handle.write(chunk)
