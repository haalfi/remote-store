"""The sync kernel's content guard: the caller's stream as a driver receives it.

``guard_content`` hands a driver a proxy over the caller's stream so that what
the stream raises is marked as the caller's and passes the choke point verbatim
(ASYNC-091). A driver may hand that proxy on to a client library, so the proxy
must allow what the caller's stream allows, and offer nothing it does not.
"""

from __future__ import annotations

import io

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
@pytest.mark.parametrize("name", ["read", "read1", "readinto", "readline", "readlines", "__next__"])
def test_every_read_the_guarded_stream_forwards_marks_the_callers_error(name: str) -> None:
    # Whichever read a driver uses, a failure of the caller's stream is the caller's.
    class _Failing(io.BytesIO):
        def _fail(self, *args: object) -> bytes:
            raise _CallerStreamError("disk full")

        read = read1 = readinto = readline = readlines = __next__ = _fail  # type: ignore[assignment]

    guarded = sync_io.guard_content(_Failing(b"x"))
    call = (lambda: next(iter(guarded))) if name == "__next__" else getattr(guarded, name)
    args = (bytearray(4),) if name == "readinto" else ()
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
def test_an_attribute_the_stream_lacks_is_not_marked_as_the_callers() -> None:
    guarded = sync_io.guard_content(_ReadOnlySource(b"ab"))  # type: ignore[arg-type]
    with pytest.raises(AttributeError) as caught:
        guarded.readinto  # noqa: B018
    assert not sync_io.from_content(caught.value)
