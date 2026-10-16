"""The sync kernel's content guard: the caller's stream as a driver receives it.

``guard_content`` hands a driver a proxy over the caller's stream so that what
the stream raises is marked as the caller's and passes the choke point verbatim
(ASYNC-091). A driver may hand that proxy on to a client library, so the proxy
keeps the caller's stream's reads, its iteration (as an iterator when the
stream is one), its ``with`` and every ordinary attribute, and offers nothing
the stream does not. Other special methods are not forwarded: Python looks
them up on the type, so a forwarded one would answer ``hasattr`` for an
operation that then fails.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from remote_store._kernel._sync import _io as sync_io


class _CallerStreamError(Exception):
    """An error the caller's own content raises, not the wire's."""


class _ReadOnlySource:
    """A source with ``read`` and nothing else, as a caller may hand in."""

    def __init__(self, data: bytes) -> None:
        self._data = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._data.read(n)


@pytest.mark.spec("ASYNC-091")
def test_the_guarded_stream_iterates_and_closes_as_the_callers_stream_does() -> None:
    # A driver may hand content to a client that iterates it or enters it as a
    # context manager; the guard must not refuse what the caller's stream allows.
    source = io.BytesIO(b"l1\nl2\n")
    guarded = sync_io.guard_content(source)
    assert list(guarded) == [b"l1\n", b"l2\n"]
    with guarded as entered:
        assert entered is guarded
    assert source.closed


@pytest.mark.spec("ASYNC-091")
@pytest.mark.parametrize("name", ["read1", "readinto", "readline", "readlines", "__iter__", "__enter__"])
def test_the_guarded_stream_offers_only_what_the_callers_stream_offers(name: str) -> None:
    # A method the caller's stream lacks is absent, so a driver probing for it
    # (``hasattr``) takes its fallback rather than a marked AttributeError.
    guarded = sync_io.guard_content(_ReadOnlySource(b"ab"))  # type: ignore[arg-type]
    assert not hasattr(guarded, name)
    assert guarded.read() == b"ab"


@pytest.mark.spec("ASYNC-091")
@pytest.mark.parametrize(
    "name", ["read", "read1", "readinto", "readinto1", "readline", "readlines", "readall", "peek", "__next__"]
)
def test_every_read_the_guarded_stream_forwards_marks_the_callers_error(name: str) -> None:
    # Whichever read a driver uses, a failure of the caller's stream is the caller's.
    class _Failing(io.BytesIO):
        def _fail(self, *args: object) -> bytes:
            raise _CallerStreamError("disk full")

        read = read1 = readinto = readinto1 = readline = readlines = readall = peek = __next__ = _fail  # type: ignore[assignment]

    guarded = sync_io.guard_content(_Failing(b"x"))
    call = (lambda: next(iter(guarded))) if name == "__next__" else getattr(guarded, name)
    args = (bytearray(4),) if name in ("readinto", "readinto1") else ()
    with pytest.raises(_CallerStreamError) as caught:
        call(*args)
    assert sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
def test_every_other_attribute_is_the_streams_own() -> None:
    # A driver that rewinds or sizes its content (an upload_fileobj-style SDK)
    # reaches the stream's own seek, tell and name through the guard.
    source = io.BytesIO(b"abcdef")
    source.name = "caller.bin"  # type: ignore[attr-defined]
    guarded = sync_io.guard_content(source)
    assert guarded.read(2) == b"ab"
    assert guarded.tell() == 2
    assert guarded.seek(0) == 0
    assert guarded.read() == b"abcdef"
    assert guarded.name == "caller.bin"
    assert guarded.getvalue() == b"abcdef"  # type: ignore[attr-defined]


@pytest.mark.spec("ASYNC-091")
def test_the_guard_over_an_iterator_is_an_iterator() -> None:
    # Every io stream is its own iterator, so next() works on it directly.
    guarded = sync_io.guard_content(io.BytesIO(b"l1\nl2\n"))
    assert iter(guarded) is guarded
    assert next(guarded) == b"l1\n"
    assert next(guarded) == b"l2\n"
    with pytest.raises(StopIteration):
        next(guarded)


@pytest.mark.spec("ASYNC-091")
def test_a_failing_next_on_the_guarded_iterator_is_marked() -> None:
    class _Lines(io.BytesIO):
        def __next__(self) -> bytes:
            raise _CallerStreamError("disk full")

    guarded = sync_io.guard_content(_Lines(b"x"))
    with pytest.raises(_CallerStreamError) as caught:
        next(guarded)
    assert sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
@pytest.mark.parametrize("name", ["__len__", "__getitem__", "__contains__"])
def test_the_guarded_stream_offers_no_special_method_it_cannot_serve(name: str) -> None:
    # Python looks special methods up on the type, so one reached through
    # __getattr__ would answer hasattr() while the operation itself fails; a
    # client probing hasattr(o, "__len__") (requests' super_len) would then break.
    class _Rich(io.BytesIO):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> int:
            return 0

        def __contains__(self, item: object) -> bool:
            return False

    guarded = sync_io.guard_content(_Rich(b"x"))
    assert not hasattr(guarded, name)


def _answering(chunk: object) -> io.BytesIO:
    """A stream whose every bytes-answering read, iteration included, answers *chunk*."""

    class _Answers(io.BytesIO):
        def _answer(self, *args: object) -> object:
            return chunk

        read = read1 = readall = readline = peek = __next__ = _answer  # type: ignore[assignment]

        def readlines(self, *args: object) -> list[object]:  # type: ignore[override]
            return [chunk]

    return _Answers(b"x")


def _read_by(guarded: object, name: str) -> object:
    if name == "__next__":
        return next(guarded)  # type: ignore[call-overload]
    if name == "__iter__":
        return next(iter(guarded))  # type: ignore[call-overload]
    if name == "readlines":
        return guarded.readlines()[0]  # type: ignore[attr-defined]
    return getattr(guarded, name)()


_BYTE_READS = ["read", "read1", "readall", "readline", "readlines", "peek", "__next__", "__iter__"]


@pytest.mark.spec("BE-008", "MEM-020")
@pytest.mark.parametrize("name", _BYTE_READS)
@pytest.mark.parametrize("chunk", [bytearray(b"ab"), memoryview(b"aXb")[::2]], ids=["bytearray", "memoryview"])
def test_a_buffer_a_read_answers_reaches_the_driver_as_bytes(name: str, chunk: object) -> None:
    answer = _read_by(sync_io.guard_content(_answering(chunk)), name)
    assert type(answer) is bytes
    assert answer == b"ab"


@pytest.mark.spec("BE-008", "MEM-020", "ASYNC-091")
@pytest.mark.parametrize("name", _BYTE_READS)
@pytest.mark.parametrize("chunk", ["ab", 3], ids=["str", "int"])
def test_a_read_answering_non_bytes_is_the_callers_type_error(name: str, chunk: object) -> None:
    with pytest.raises(TypeError, match="not bytes") as caught:
        _read_by(sync_io.guard_content(_answering(chunk)), name)
    assert sync_io.from_content(caught.value)


def _released() -> memoryview:
    view = memoryview(bytearray(b"q"))
    view.release()
    return view


@pytest.mark.spec("BE-008", "ASYNC-091")
@pytest.mark.parametrize("name", _BYTE_READS)
def test_a_buffer_that_cannot_be_read_is_the_callers_error(name: str) -> None:
    # Converting a released memoryview raises; it is the caller's buffer failing.
    with pytest.raises(ValueError, match="released") as caught:
        _read_by(sync_io.guard_content(_answering(_released())), name)
    assert sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
def test_a_failing_iter_on_the_guarded_stream_is_marked() -> None:
    class _NoIter(_ReadOnlySource):  # iterable, not its own iterator
        def __iter__(self) -> Any:
            raise _CallerStreamError("no lines")

    guarded = sync_io.guard_content(_NoIter(b"x"))  # type: ignore[arg-type]
    with pytest.raises(_CallerStreamError) as caught:
        next(iter(guarded))  # type: ignore[call-overload]
    assert sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
@pytest.mark.parametrize("phase", ["__enter__", "__exit__"])
def test_a_failing_with_on_the_guarded_stream_is_marked(phase: str) -> None:
    class _Ctx(io.BytesIO):
        def __enter__(self) -> Any:
            if phase == "__enter__":
                raise _CallerStreamError("enter")
            return self

        def __exit__(self, *exc_info: object) -> Any:
            raise _CallerStreamError("exit")

    guarded = sync_io.guard_content(_Ctx(b"x"))
    with pytest.raises(_CallerStreamError) as caught, guarded:  # type: ignore[union-attr]
        pass
    assert sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
def test_an_exit_re_raising_the_drivers_error_leaves_it_the_drivers() -> None:
    # The exception __exit__ was handed came from the driver's own with-body; a
    # stream that re-raises it must not turn a wire error into the caller's.
    class _ReRaising(io.BytesIO):
        def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> Any:
            if exc is not None:
                raise exc
            return False

    wire = OSError("wire broke")
    with pytest.raises(OSError, match="wire broke") as caught, sync_io.guard_content(_ReRaising(b"x")):  # type: ignore[union-attr]
        raise wire
    assert caught.value is wire
    assert not sync_io.from_content(caught.value)


@pytest.mark.spec("ASYNC-091")
def test_an_attribute_the_stream_lacks_is_not_marked_as_the_callers() -> None:
    guarded = sync_io.guard_content(_ReadOnlySource(b"ab"))  # type: ignore[arg-type]
    with pytest.raises(AttributeError) as caught:
        guarded.readinto  # noqa: B018
    assert not sync_io.from_content(caught.value)
