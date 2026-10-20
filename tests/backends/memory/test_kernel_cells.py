"""Memory's own cells for the key rule and the protocol, on both classes (spec 053 BE-030, 003 BE-025, 052 BE-033).

The key-rule cells are the ones BK-389's decision 6 table marks as changing when
Memory moves onto the contract kernel: the root spellings of
``get_folder_info``, the addressing column, and the backslash row. None of them
is reachable through ``Store``, which hands a backend a ``RemotePath``-normalised
key, so each calls the backend directly. The two protocol cells,
``test_memory_stays_open_across_repeated_closes`` and
``test_async_memory_closes_a_refused_caller_generator``, are BE-033's rows on
Memory; they call the backend directly because BE-033 binds the class on the
kernel.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from remote_store._errors import CapabilityNotSupported, InvalidPath
from remote_store._path import RemotePath
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

RUNTIMES = ("sync", "async")


def _make(runtime: str) -> Any:
    return MemoryBackend() if runtime == "sync" else AsyncMemoryBackend()


def _run(result: Any) -> Any:
    """Settle a call of either runtime: await a coroutine, drain an iterator."""
    if inspect.isasyncgen(result):

        async def drain() -> list[Any]:
            return [item async for item in result]

        return asyncio.run(drain())
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    if inspect.isgenerator(result):
        return list(result)
    return result


def _read(backend: Any, key: str) -> bytes:
    if isinstance(backend, MemoryBackend):
        with backend.read(key) as stream:
            return bytes(stream.read())
    return bytes(b"".join(_run(backend.read(key))))


@pytest.mark.spec("BE-030", "MEM-DS-005")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("spelling", ["./", ".//", "./."])
def test_root_spellings_answer_the_root_folder_info(runtime: str, spelling: str) -> None:
    backend = _make(runtime)
    _run(backend.write("d/f", b"abc"))
    info = _run(backend.get_folder_info(spelling))
    assert info.path == RemotePath.ROOT
    assert info.file_count == 1
    assert info.total_size == 3


_FOLDED = [("./", ""), (".//", ""), ("./.", ""), ("d//f", "d/f"), ("d/./f", "d/f"), ("d/", "d")]


@pytest.mark.spec("BE-030", "BE-025", "NPR-020")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(("key", "canonical"), _FOLDED)
def test_addressing_folds_a_non_canonical_key(runtime: str, key: str, canonical: str) -> None:
    backend = _make(runtime)
    assert backend.native_path(key) == canonical
    plan = backend.resolve(key)
    assert plan.native_path == canonical
    assert plan.key == key  # the caller's spelling, unchanged
    assert backend.to_key(key) == key  # an address, forwarded unchanged


_BACKSLASH = ["d\\f", "e\\g", "\\"]


def _ops(key: str) -> list[tuple[str, Any]]:
    return [
        ("exists", lambda b: b.exists(key)),
        ("is_file", lambda b: b.is_file(key)),
        ("is_folder", lambda b: b.is_folder(key)),
        ("read", lambda b: _read(b, key)),
        ("read_bytes", lambda b: b.read_bytes(key)),
        ("write", lambda b: b.write(key, b"x")),
        ("write_atomic", lambda b: b.write_atomic(key, b"x")),
        ("delete", lambda b: b.delete(key)),
        ("delete_folder", lambda b: b.delete_folder(key, recursive=True)),
        ("get_file_info", lambda b: b.get_file_info(key)),
        ("get_folder_info", lambda b: b.get_folder_info(key)),
        ("list_files", lambda b: b.list_files(key, recursive=True)),
        ("list_folders", lambda b: b.list_folders(key)),
        ("iter_children", lambda b: b.iter_children(key)),
        ("move_src", lambda b: b.move(key, "dst")),
        ("move_dst", lambda b: b.move("src", key)),
        ("copy_src", lambda b: b.copy(key, "dst")),
        ("copy_dst", lambda b: b.copy("src", key)),
    ]


@pytest.mark.spec("BE-030", "MEM-DS-005")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("key", _BACKSLASH)
@pytest.mark.parametrize("op", [name for name, _ in _ops("k")])
def test_a_backslash_key_is_refused_and_touches_nothing(runtime: str, key: str, op: str) -> None:
    backend = _make(runtime)
    _run(backend.write("src", b"s"))
    call = dict(_ops(key))[op]
    with pytest.raises(InvalidPath):
        _run(call(backend))
    # Nothing stored, moved or removed: the tree holds exactly the seeded file.
    listed = _run(backend.list_files("", recursive=True))
    assert sorted(str(f.path) for f in listed) == ["src"]
    assert _run(backend.read_bytes("src")) == b"s"


def _open_atomic_and_write(backend: MemoryBackend, key: str) -> None:
    with backend.open_atomic(key) as handle:
        handle.write(b"x")


@pytest.mark.spec("BE-030", "MEM-DS-005")
@pytest.mark.parametrize("key", _BACKSLASH)
@pytest.mark.parametrize(
    "call",
    [_open_atomic_and_write, lambda b, k: b.read_seekable(k)],
    ids=["open_atomic", "read_seekable"],
)
def test_a_backslash_key_is_refused_on_the_sync_only_members(key: str, call: Any) -> None:
    # open_atomic and read_seekable take their own key paths, and only the sync
    # class has them.
    backend = MemoryBackend()
    backend.write("src", b"s")
    with pytest.raises(InvalidPath):
        call(backend, key)
    assert sorted(str(f.path) for f in backend.list_files("", recursive=True)) == ["src"]


def _close(backend: Any) -> None:
    _run(backend.close() if isinstance(backend, MemoryBackend) else backend.aclose())


@pytest.mark.spec("BE-033", "BE-020", "BE-022")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_memory_stays_open_across_repeated_closes(runtime: str) -> None:
    # Memory's posture is non-terminal: close, reuse, close; unwrap keeps the driver's answer.
    backend = _make(runtime)
    _close(backend)
    _close(backend)
    _run(backend.write("f", b"F"))
    assert _read(backend, "f") == b"F"
    _close(backend)
    with pytest.raises(CapabilityNotSupported):
        backend.unwrap(dict)


@pytest.mark.spec("BE-033", "ASYNC-091")
def test_async_memory_closes_a_refused_caller_generator() -> None:
    finalised: list[bool] = []

    async def chunks() -> Any:
        try:
            yield b"ab"
            yield "text"
        finally:
            finalised.append(True)

    async def write_then_look() -> list[bool]:
        content = chunks()
        with pytest.raises(TypeError, match="str, not bytes"):
            await AsyncMemoryBackend().write("f", content)
        # Inside the loop: asyncio.run's shutdown would finalise it anyway.
        return list(finalised)

    assert asyncio.run(write_then_look()) == [True]
