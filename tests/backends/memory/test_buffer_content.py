"""Content types on both Memory classes: the kernel hands the driver ``bytes``.

A ``bytearray`` or ``memoryview`` passed to ``write`` or ``write_atomic`` is
stored as the bytes it holds, on the sync and async class and through
``Store``. Content that is no bytes source at all is a ``TypeError`` before
anything is stored. Before the kernel did both, the drivers read such content
as a stream and the probe answered from the target (BUG-328).
"""

from __future__ import annotations

import asyncio
import inspect
import io
from typing import TYPE_CHECKING, Any

import pytest

from remote_store import Store
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

RUNTIMES = ("sync", "async")

_BUFFERS = [
    pytest.param(bytearray(b"abc"), b"abc", id="bytearray"),
    pytest.param(memoryview(b"abc"), b"abc", id="memoryview"),
    pytest.param(memoryview(b"aXbXc")[::2], b"abc", id="memoryview-strided"),
    pytest.param(bytearray(), b"", id="bytearray-empty"),
]


def _make(runtime: str) -> Any:
    return MemoryBackend() if runtime == "sync" else AsyncMemoryBackend()


def _run(result: Any) -> Any:
    return asyncio.run(result) if inspect.iscoroutine(result) else result


@pytest.mark.spec("MEM-020", "BE-008")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("method", ["write", "write_atomic"])
@pytest.mark.parametrize(("content", "stored"), _BUFFERS)
def test_a_buffer_is_stored_as_its_bytes(runtime: str, method: str, content: Any, stored: bytes) -> None:
    backend = _make(runtime)
    result = _run(getattr(backend, method)("d/f", content))
    assert result.size == len(stored)
    assert _run(backend.read_bytes("d/f")) == stored
    assert _run(backend.get_file_info("d/f")).size == len(stored)


@pytest.mark.spec("MEM-020", "BE-008")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("method", ["write", "write_atomic"])
def test_a_buffer_overwrites_an_existing_file(runtime: str, method: str) -> None:
    backend = _make(runtime)
    _run(backend.write("f", b"old"))
    _run(getattr(backend, method)("f", bytearray(b"new!"), overwrite=True))
    assert _run(backend.read_bytes("f")) == b"new!"


@pytest.mark.spec("MEM-020", "BE-008")
@pytest.mark.parametrize("method", ["write", "write_atomic"])
@pytest.mark.parametrize(("content", "stored"), _BUFFERS)
def test_a_buffer_is_stored_through_a_store(method: str, content: Any, stored: bytes) -> None:
    store = Store(MemoryBackend())
    getattr(store, method)("d/f", content)
    assert store.read_bytes("d/f") == stored


class _StrStream(io.RawIOBase):
    """A stream whose reads return ``str``: not binary, though it has ``read``."""

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> str:  # type: ignore[override]
        return "x"


class _NoneMidStream(io.RawIOBase):
    """A non-blocking raw stream: ``None`` (no data yet) between two chunks."""

    def __init__(self) -> None:
        self._answers = [b"ab", None, b"c", b""]

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> Any:  # type: ignore[override]
        return self._answers.pop(0)


async def _chunks(*parts: Any) -> AsyncIterator[Any]:
    for part in parts:
        yield part


def _not_content(runtime: str) -> list[Any]:
    common = [["x"], 3, "text"]
    sync_only = [io.StringIO("x"), _StrStream(), _NoneMidStream()]  # None: never a truncated file
    return common + (sync_only if runtime == "sync" else [_chunks("x"), _chunks(b"ab", None)])


@pytest.mark.spec("MEM-020", "BE-008")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("method", ["write", "write_atomic"])
@pytest.mark.parametrize("seeded", [False, True], ids=["free", "existing"])
def test_content_that_is_not_bytes_is_a_type_error_and_stores_nothing(runtime: str, method: str, seeded: bool) -> None:
    for content in _not_content(runtime):
        backend = _make(runtime)
        if seeded:
            _run(backend.write("f", b"old"))
        # Never an answer about the target, such as AlreadyExists for the existing file.
        with pytest.raises(TypeError, match=r"must be bytes|not bytes"):
            _run(getattr(backend, method)("f", content))
        assert _run(backend.exists("f")) is seeded
        if seeded:
            assert _run(backend.read_bytes("f")) == b"old"


class _Refusing(Exception):
    """An exception whose class refuses new attributes."""

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(name)


class _FailingStream(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise _Refusing("boom")


async def _failing_chunks() -> AsyncIterator[bytes]:
    raise _Refusing("boom")
    yield b""  # pragma: no cover - makes this an async generator


@pytest.mark.spec("MEM-020", "ASYNC-091")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("overwrite", [False, True])
def test_a_content_error_refusing_attributes_still_passes_verbatim(runtime: str, overwrite: bool) -> None:
    # Before the mark went into the instance dict, this error went to classify,
    # and without overwrite the probe answered AlreadyExists about the target.
    backend = _make(runtime)
    _run(backend.write("f", b"old"))
    content = _FailingStream() if runtime == "sync" else _failing_chunks()
    with pytest.raises(_Refusing, match="boom"):
        _run(backend.write("f", content, overwrite=overwrite))
    assert _run(backend.read_bytes("f")) == b"old"


def _released() -> memoryview:
    view = memoryview(bytearray(b"q"))
    view.release()
    return view


class _ReleasedStream(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> Any:  # type: ignore[override]
        return _released()


async def _released_chunks() -> AsyncIterator[Any]:
    yield _released()


class _AiterRaises:
    def __aiter__(self) -> Any:
        raise _Refusing("aiter-boom")


def _unreadable(runtime: str) -> list[Any]:
    return [_ReleasedStream()] if runtime == "sync" else [_released_chunks(), _AiterRaises()]


@pytest.mark.spec("MEM-020", "ASYNC-091")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("method", ["write", "write_atomic"])
def test_content_failing_as_it_is_read_is_the_callers_error_not_the_targets(runtime: str, method: str) -> None:
    # A buffer that cannot be read, or an iterator that cannot be begun, fails
    # in the caller's hands: never AlreadyExists for the existing file.
    for content in _unreadable(runtime):
        backend = _make(runtime)
        _run(backend.write("f", b"old"))
        with pytest.raises((ValueError, _Refusing), match="released|aiter-boom"):
            _run(getattr(backend, method)("f", content))
        assert _run(backend.read_bytes("f")) == b"old"


@pytest.mark.spec("MEM-020", "BE-008")
def test_async_buffer_chunks_are_stored_as_their_bytes() -> None:
    backend = AsyncMemoryBackend()
    _run(backend.write("f", _chunks(bytearray(b"ab"), memoryview(b"c"))))
    assert _run(backend.read_bytes("f")) == b"abc"


@pytest.mark.spec("MEM-020", "SAW-013")
def test_open_atomic_refuses_a_non_contiguous_buffer_as_a_file_does() -> None:
    backend = MemoryBackend()
    with pytest.raises(BufferError), backend.open_atomic("f") as stream:
        stream.write(memoryview(b"aXbXc")[::2])
    assert not backend.exists("f")
    with backend.open_atomic("f") as stream:
        stream.write(memoryview(b"abc"))
    assert backend.read_bytes("f") == b"abc"


@pytest.mark.spec("MEM-020")
def test_the_caller_can_reuse_a_bytearray_after_the_write() -> None:
    # The stored value is a copy: mutating the caller's buffer later changes nothing.
    backend = MemoryBackend()
    buf = bytearray(b"abc")
    backend.write("f", buf)  # type: ignore[arg-type]  # outside WritableContent; the kernel converts it
    buf[0:1] = b"Z"
    assert backend.read_bytes("f") == b"abc"
