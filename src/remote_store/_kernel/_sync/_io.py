"""Where the sync runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_async/_io.py`` is its counterpart, with the
same names. The generated modules beside this one import these. Neither
imports the driver module, which imports them.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, BinaryIO, Protocol, cast

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
    return bool(getattr(exc, _FROM_CONTENT, False))


def _mark(exc: BaseException) -> None:
    # An exception class that refuses new attributes stays unmarked, and is mapped.
    with contextlib.suppress(AttributeError):
        setattr(exc, _FROM_CONTENT, True)


#: The stream's reads, each forwarded with its failures marked.
_READS = frozenset({"read", "read1", "readinto", "readline", "readlines"})


class _MarkedReader:
    """The caller's stream, with whatever its reads raise marked as the caller's.

    Every attribute is the stream's own, so one the stream lacks is absent here
    too; a read among them is forwarded with its failures marked. It is a proxy,
    not an ``io.IOBase``: iteration and ``with`` are present when the stream's
    type supports them (``_proxy_type``), since Python looks those up on the type.
    """

    __slots__ = ("_stream",)

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._stream, name)
        if name not in _READS:
            return attr

        def marked(*args: object, **kwargs: object) -> object:
            try:
                return attr(*args, **kwargs)
            except Exception as exc:
                _mark(exc)
                raise

        return marked


class _MarkedIteration:
    __slots__ = ()
    _stream: BinaryIO

    def __iter__(self) -> Iterator[bytes]:
        lines = iter(self._stream)
        while True:
            try:
                line = next(lines)
            except StopIteration:
                return
            except Exception as exc:
                _mark(exc)
                raise
            yield line


class _ForwardedContext:
    __slots__ = ()
    _stream: BinaryIO

    def __enter__(self) -> _ForwardedContext:
        self._stream.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> object:
        return self._stream.__exit__(*exc_info)  # type: ignore[arg-type]


_PROXY_TYPES: dict[tuple[bool, bool], type[_MarkedReader]] = {}


def _proxy_type(stream: object) -> type[_MarkedReader]:
    kind = type(stream)
    shape = (hasattr(kind, "__iter__"), hasattr(kind, "__enter__") and hasattr(kind, "__exit__"))
    proxy = _PROXY_TYPES.get(shape)
    if proxy is None:
        bases = (_MarkedIteration,) * shape[0] + (_ForwardedContext,) * shape[1] + (_MarkedReader,)
        proxy = type("_MarkedReader", bases, {"__slots__": ()}) if len(bases) > 1 else _MarkedReader
        _PROXY_TYPES[shape] = proxy
    return proxy


def guard_content(content: Content) -> Content:
    """*content* with whatever the caller's stream raises marked as the caller's.

    The choke point passes a marked error through verbatim: a failing source
    the caller handed in is not a wire error to classify.
    """
    if isinstance(content, bytes | bytearray | memoryview):
        return content
    return cast("BinaryIO", _proxy_type(content)(content))


def feed(handle: _Writable, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes | bytearray | memoryview):
        handle.write(bytes(content))
        return
    while chunk := content.read(_CHUNK):
        handle.write(chunk)
