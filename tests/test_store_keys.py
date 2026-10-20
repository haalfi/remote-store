"""Store keys — derived from sdd/specs/054-store-key.md.

KEY-002 (surrogate refusal) and KEY-008 (backend refusal under a declared
profile) carry no mark: the store breaks both today, which BK-469 tracks. For
the same reason KEY-003 and KEY-006 are asserted over inputs without a
surrogate, KEY-007 on Memory and Local only, and KEY-009 as a strict xfail on
Windows Local, which breaks it (BK-469).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath
from remote_store._path import RemotePath
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from pathlib import Path

# Inputs no section refuses or only refuses, surrogates left out (KEY-002).
_ODD_INPUTS = [
    "",
    ".",
    "..",
    "./",
    "/",
    "\\",
    "a\\..\\b",
    "a/\0",
    "a..b",
    ".a/b.",
    " a /b ",
    "a\x01b",
    "a\nb",
    "日本/語",
    "a" * 300,
    "//a//b//",
    "./a/./b/.",
]


def _store() -> Store:
    return Store(backend=MemoryBackend())


@pytest.mark.spec("KEY-001")
@pytest.mark.parametrize("raw", _ODD_INPUTS)
def test_every_input_maps_to_a_key_or_is_refused(raw: str) -> None:
    outcome: object
    try:
        outcome = _store().exists(raw)
    except InvalidPath as exc:
        outcome = exc
    if isinstance(outcome, InvalidPath):
        assert outcome.path == raw
    else:
        assert isinstance(outcome, bool)


@pytest.mark.spec("KEY-003")
@pytest.mark.parametrize("raw", ["./..", "/..", "\\..", "/\0", ".\0", "a/../", "../a"])
def test_refusal_outranks_the_root_and_a_key(raw: str) -> None:
    store = _store()
    with pytest.raises(InvalidPath):
        store.is_folder(raw)
    with pytest.raises(InvalidPath):
        store.write(raw, b"x")
    assert list(store.list_files("", recursive=True)) == []


@pytest.mark.spec("KEY-004")
@pytest.mark.parametrize(
    ("raw", "key"),
    [
        pytest.param("a", "a", id="canonical"),
        pytest.param("a/b", "a/b", id="canonical-nested"),
        pytest.param("/a", "a", id="leading"),
        pytest.param("a/", "a", id="trailing"),
        pytest.param("a//b", "a/b", id="doubled"),
        pytest.param("a/./b", "a/b", id="dot"),
        pytest.param("a\\b", "a/b", id="backslash"),
        pytest.param("a\\/b", "a/b", id="mixed-separators"),
        pytest.param("   ", "   ", id="spaces-only"),
        pytest.param("a/ /b", "a/ /b", id="space-segment"),
        pytest.param("a/\t/b", "a/\t/b", id="tab-segment"),
    ],
)
def test_input_maps_to_its_canonical_key(raw: str, key: str) -> None:
    store = _store()
    result = store.write(raw, b"x")
    assert str(result.path) == key
    assert [str(f.path) for f in store.list_files("", recursive=True)] == [key]


@pytest.mark.spec("KEY-006")
@pytest.mark.parametrize("raw", [r for r in _ODD_INPUTS if r] + ["a\\b/c", "x/./y\\z"])
def test_every_key_is_addressable_and_its_own_key(raw: str) -> None:
    try:
        key = RemotePath(raw)
    except InvalidPath:
        return
    for name in key.parts:
        assert name not in {".", ".."}
        assert not {"/", "\\", "\0"} & set(name)
    assert RemotePath(str(key)) == key


_FLOOR_KEYS = [
    "a",
    "A-1_b.c",
    "d/e/f.txt",
    "con1/lpt",
    "n" * 255,
    "/".join(["seg"] * 63) + "/abc",
]


def _local_room_for_floor(root: Path) -> bool:
    """KEY-A-01: a Windows root without long paths may leave less than 255 bytes."""
    return sys.platform != "win32" or len(str(root)) + 1 + 255 < 260


@pytest.mark.os_sensitive
@pytest.mark.spec("KEY-007", "KEY-A-01")
@pytest.mark.parametrize("key", _FLOOR_KEYS)
@pytest.mark.parametrize("backend_name", ["memory", "local"])
def test_floor_key_is_stored_by_memory_and_local(key: str, backend_name: str, tmp_path: Path) -> None:
    assert len(key.encode()) <= 255
    if backend_name == "local":
        if not _local_room_for_floor(tmp_path):
            pytest.skip("KEY-A-01 does not hold: Windows path limit leaves less than 255 bytes")
        store = Store(backend=LocalBackend(root=str(tmp_path)))
    else:
        store = _store()
    store.write(key, b"floor")
    assert store.read_bytes(key) == b"floor"
    assert store.is_file(key)
    assert [str(f.path) for f in store.list_files("", recursive=True)] == [key]


@pytest.mark.os_sensitive
@pytest.mark.spec("KEY-009")
@pytest.mark.parametrize(
    ("key", "alias"), [("a/     ", "a"), ("a ", "a"), ("a.", "a"), ("d/x. ", "d/x"), ("a./b", "a/b")]
)
@pytest.mark.parametrize("backend_name", ["memory", "local"])
def test_admitted_key_reaches_its_own_entity(
    key: str, alias: str, backend_name: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """A name with a trailing space or dot is its own entity, not its stripped spelling."""
    if backend_name == "local":
        if sys.platform == "win32":
            # Measures the documented Win32 stripping on CI's Windows lane: an XPASS fails it.
            request.applymarker(pytest.mark.xfail(strict=True, reason="Windows Local aliases the name (BK-469)"))
        store = Store(backend=LocalBackend(root=str(tmp_path)))
    else:
        store = _store()
    store.write(key, b"key")
    assert store.read_bytes(key) == b"key"
    assert not store.is_file(alias)
