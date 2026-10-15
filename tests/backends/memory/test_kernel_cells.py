"""Memory's own cells for the key rule, on both classes (spec 003 BE-030, BE-025).

None of these is reachable through ``Store``, which hands a backend a
``RemotePath``-normalised key, so each calls the backend directly. They are the
cells BK-389's decision 6 table marks as changing when Memory moves onto the
contract kernel: the root spellings of ``get_folder_info``, the addressing
column, and the backslash row.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from remote_store._errors import InvalidPath
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
