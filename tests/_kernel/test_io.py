"""The sync kernel's content guard: the caller's stream as a driver receives it.

``guard_content`` hands a driver a proxy over the caller's stream so that what
the stream raises is marked as the caller's and passes the choke point verbatim
(ASYNC-091), and what its reads answer reaches the driver in its shape: a
read or a line as ``bytes`` (a buffer converted), ``readlines`` as a list of
them, ``readinto`` as a count. Anything else, ``None`` included, is the
caller's error. A driver
may hand that proxy on to a client library, so the proxy keeps the caller's
stream's reads, its iteration (as an iterator when the stream is one), its
``with`` and every ordinary attribute, and offers nothing
the stream does not. Other special methods are not forwarded: Python looks
them up on the type, so a forwarded one would answer ``hasattr`` for an
operation that then fails.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pytest

from remote_store._kernel._sync import _io as sync_io
from tests._kernel._fake import NonBlockingRaw


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


def _released() -> memoryview:
    view = memoryview(bytearray(b"q"))
    view.release()
    return view


# The whole space of what a forwarded read can answer, crossed with every read
# the proxy forwards, against one oracle. Each read answers in one of three
# shapes: bytes (or a line of them), a list of lines, or a count of bytes read
# into the caller's buffer.
_SHAPE = {
    "read": "bytes", "read1": "bytes", "readall": "bytes", "readline": "bytes", "peek": "bytes",
    "__next__": "bytes", "__iter__": "bytes",
    "readlines": "lines",
    "readinto": "count", "readinto1": "count",
}  # fmt: skip
_ANSWERS: dict[str, Any] = {
    "bytes": lambda: b"ab",
    "bytearray": lambda: bytearray(b"ab"),
    "memoryview": lambda: memoryview(b"aXb")[::2],
    "str": lambda: "ab",
    "int": lambda: 2,
    "none": lambda: None,  # a non-blocking raw stream's "no data yet"
    "released": _released,
}


def _answering(shape: str, answer: object, name: str) -> object:
    """A stream whose every read answers *answer*, wrapped in a list where *shape* is lines.

    For ``__iter__`` the stream is iterable but not its own iterator, so the
    proxy iterates it through ``_MarkedIteration`` rather than ``__next__``.
    """
    if name == "__iter__":

        class _Lines:
            def read(self, *args: object) -> object:
                return answer

            def __iter__(self) -> Any:
                yield answer

        return _Lines()

    class _Answers(io.BytesIO):
        answered = False

        def _answer(self, *args: object) -> object:
            # Answers once, then the end: an unsized read loops sized reads until b"".
            first, self.answered = not self.answered, True
            if not first:
                return [] if shape == "lines" else (0 if shape == "count" else b"")
            return [answer] if shape == "lines" else answer

        read = read1 = readall = readline = peek = __next__ = readlines = readinto = readinto1 = _answer  # type: ignore[assignment]

    return _Answers(b"x")


def _read_by(guarded: object, name: str) -> object:
    if name == "__next__":
        return next(guarded)  # type: ignore[call-overload]
    if name == "__iter__":
        return next(iter(guarded))  # type: ignore[call-overload]
    if name in ("readinto", "readinto1"):
        return getattr(guarded, name)(bytearray(4))
    answer = getattr(guarded, name)()
    return answer[0] if name == "readlines" else answer


def _expected(shape: str, kind: str) -> tuple[str, Any]:
    """What the driver must see: ``("value", v)``, or ``("raises", type)`` marked as the caller's."""
    if shape == "count":
        return ("value", 2) if kind == "int" else ("raises", TypeError)
    if kind in ("bytes", "bytearray", "memoryview"):
        return ("value", b"ab")
    return ("raises", ValueError if kind == "released" else TypeError)


@pytest.mark.spec("BE-030", "BE-008", "ASYNC-091")
@pytest.mark.parametrize("kind", sorted(_ANSWERS))
def test_a_readlines_answer_that_is_not_a_list_is_the_callers_type_error(kind: str) -> None:
    # The lines shape above answers a list; here readlines answers the bare kind.
    class _Bare(io.BytesIO):
        def readlines(self, *args: object) -> Any:  # type: ignore[override]
            return _ANSWERS[kind]()

    with pytest.raises(TypeError, match="readlines returned .*, not a list") as caught:
        sync_io.guard_content(_Bare(b"x")).readlines()  # type: ignore[union-attr]
    assert sync_io.from_content(caught.value)


def test_every_forwarded_read_has_a_shape() -> None:
    # Drift guard: a read added to the proxy without a shape here goes unenumerated.
    assert set(sync_io._READS) | {"__next__", "__iter__"} == set(_SHAPE)


@pytest.mark.spec("BE-030", "BE-008", "MEM-020", "ASYNC-091")
@pytest.mark.parametrize("kind", sorted(_ANSWERS))
@pytest.mark.parametrize("name", sorted(_SHAPE))
def test_what_every_read_answers_reaches_the_driver_as_its_shape_or_the_callers_error(name: str, kind: str) -> None:
    # None from any read is refused, never taken for the end: a driver's read
    # loop would otherwise store a truncated file.
    shape = _SHAPE[name]
    outcome, expected = _expected(shape, kind)
    guarded = sync_io.guard_content(_answering(shape, _ANSWERS[kind](), name))  # type: ignore[arg-type]
    if outcome == "value":
        answer = _read_by(guarded, name)
        assert type(answer) is type(expected)
        assert answer == expected
    else:
        with pytest.raises(expected) as caught:
            _read_by(guarded, name)
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


_UNSIZED: dict[str, Any] = {
    "read()": lambda s: s.read(),
    "read(-1)": lambda s: s.read(-1),
    "read(None)": lambda s: s.read(None),
    "read(size=-1)": lambda s: s.read(size=-1),
    "readall()": lambda s: s.readall(),
}


@pytest.mark.spec("BE-030", "ASYNC-091")
@pytest.mark.parametrize("how", sorted(_UNSIZED))
def test_an_unsized_read_never_stops_at_a_none_the_stream_hides(how: str) -> None:
    # The stream's own unsized read is readall, which stops at the None and
    # answers b"ab": the proxy reads in sized chunks so it sees the None itself.
    if how in ("read()", "read(-1)", "readall()"):  # the spellings a raw read accepts
        assert _UNSIZED[how](NonBlockingRaw()) == b"ab"
    with pytest.raises(TypeError, match="NoneType, not bytes") as caught:
        _UNSIZED[how](sync_io.guard_content(NonBlockingRaw()))  # type: ignore[arg-type]
    assert sync_io.from_content(caught.value)


class _Counted(io.BytesIO):
    """A stream that records the size of every read."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.sizes: list[object] = []

    def read(self, size: int | None = -1) -> bytes:
        self.sizes.append(size)
        return super().read(size)


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("how", sorted(set(_UNSIZED) - {"readall()"}))
def test_an_unsized_read_answers_every_byte_in_sized_chunks(how: str) -> None:
    data = bytes(range(256)) * (3 * sync_io._CHUNK // 256) + b"tail"
    source = _Counted(data)
    answer = _UNSIZED[how](sync_io.guard_content(source))
    assert type(answer) is bytes
    assert answer == data
    assert source.sizes == [sync_io._CHUNK] * 5  # four reads of data, one of the end


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("size", [0, 3])
def test_a_sized_read_is_forwarded_as_it_is(size: int) -> None:
    source = _Counted(b"abcdef")
    assert sync_io.guard_content(source).read(size) == b"abcdef"[:size]  # type: ignore[union-attr]
    assert source.sizes == [size]


class _NamedSize(io.BytesIO):
    """A stream whose ``read`` names its size ``n``, not ``size``."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.sizes: list[object] = []

    def read(self, n: int | None = -1) -> bytes:  # type: ignore[override]
        self.sizes.append(n)
        return super().read(n)


@pytest.mark.spec("BE-030")
def test_a_size_under_the_streams_own_keyword_is_forwarded_as_it_is() -> None:
    # Only a size the proxy can read as unsized is read in full; any other keyword is the stream's.
    source = _NamedSize(b"abcdef")
    assert sync_io.guard_content(source).read(n=3) == b"abc"  # type: ignore[union-attr,call-arg]
    assert source.sizes == [3]


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize(
    "call",
    [lambda s: s.read(-1, size=2), lambda s: s.read(None, foo=1)],
    ids=["read(-1, size=2)", "read(None, foo=1)"],
)
def test_a_size_with_keywords_beside_it_is_the_streams_to_answer(call: Any) -> None:
    # The stream refuses the call itself; the proxy does not read it as unsized.
    with pytest.raises(TypeError, match="argument") as native:
        call(io.BytesIO(b"abc"))
    with pytest.raises(TypeError, match=re.escape(str(native.value))):
        call(sync_io.guard_content(io.BytesIO(b"abc")))


@pytest.mark.spec("BE-030")
def test_an_unsized_read_is_not_a_join_of_its_chunks() -> None:
    # Joining the chunks held the content twice. tracemalloc counts a buffer's
    # resize once, so this pins the join away, not the process peak, which a
    # growing buffer can still raise.
    import tracemalloc

    data = b"x" * (16 * sync_io._CHUNK)
    guarded = sync_io.guard_content(io.BytesIO(data))
    tracemalloc.start()
    try:
        answer = guarded.read()  # type: ignore[union-attr]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert answer == data
    assert peak < 1.5 * len(data)


@pytest.mark.spec("ASYNC-091")
def test_an_attribute_the_stream_lacks_is_not_marked_as_the_callers() -> None:
    guarded = sync_io.guard_content(_ReadOnlySource(b"ab"))  # type: ignore[arg-type]
    with pytest.raises(AttributeError) as caught:
        guarded.readinto  # noqa: B018
    assert not sync_io.from_content(caught.value)
