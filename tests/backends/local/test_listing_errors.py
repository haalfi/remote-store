"""How ``LocalBackend``'s three listings answer an OS error met during the walk.

A listing makes three kinds of syscall: it scans the folder it was asked for,
it scans each subfolder a recursive listing descends into, and it stats each
entry to learn its type and size. Any of them can fail, and BE-021 forbids the
native exception from reaching the caller. Each failure takes one answer by its
class, the same on every syscall:

* ``FileNotFoundError`` / ``NotADirectoryError``: the thing is absent. An absent
  target is an empty listing, and a subfolder or entry that vanished
  mid-walk is skipped while its siblings are still listed.
* ``PermissionError``: ``PermissionDenied`` naming the denied key. A recursive
  listing raises rather than leaving out the subtree it could not read, since
  a short listing that ends cleanly reads as a complete one.
* Any other ``OSError``: the base ``RemoteStoreError`` naming the key, never
  ``PermissionDenied``.

The cells below are the whole product of branch x site x error class, so a fix
that maps one syscall and forgets another fails by name. Faults are injected
by patching ``os.scandir`` / ``os.stat`` for a single path and delegating every
other call, which keeps the cells portable; ``test_a_real_unreadable_subfolder``
checks the injected model against a real ``chmod`` on POSIX.
"""

from __future__ import annotations

import errno
import os
import sys
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from remote_store import Store
from remote_store._errors import PermissionDenied, RemoteStoreError
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = pytest.mark.os_sensitive

_REAL_SCANDIR = os.scandir
_REAL_STAT = os.stat

# Every listing below is taken at the store root over this tree.
_FILES = ("a.txt", "sub/b.txt", "sub/deep/c.txt", "other/d.txt")

_BRANCHES: dict[str, Callable[[LocalBackend], Iterator[object]]] = {
    "list_files": lambda b: b.list_files(""),
    "list_files-recursive": lambda b: b.list_files("", recursive=True),
    "list_files-max_depth": lambda b: b.list_files("", recursive=True, max_depth=5),
    "list_folders": lambda b: b.list_folders(""),
    "iter_children": lambda b: b.iter_children(""),
}
_RECURSIVE = ("list_files-recursive", "list_files-max_depth")

# What each branch lists when nothing fails, and when the fault makes its
# target absent. The absent answers are the only cells whose listing is not
# all-or-nothing, so they are stated in full rather than derived.
_COMPLETE = {
    "list_files": {"a.txt"},
    "list_files-recursive": set(_FILES),
    "list_files-max_depth": set(_FILES),
    "list_folders": {"sub", "other"},
    "iter_children": {"a.txt", "sub", "other"},
}
_WITHOUT_SUB_SUBTREE = {"a.txt", "other/d.txt"}


def _norm(p: object) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(p)))  # type: ignore[arg-type]


@pytest.fixture
def backend(tmp_path: Path) -> LocalBackend:
    b = LocalBackend(str(tmp_path))
    for key in _FILES:
        b.write(key, b"x")
    return b


def _keys(entries: Iterator[object]) -> set[str]:
    return {str(e.path) for e in entries}  # type: ignore[attr-defined]


def _failing(real: Callable[..., object], target: Path, exc: OSError) -> Callable[..., object]:
    want = _norm(target)

    def fake(path: object = ".", *args: object, **kwargs: object) -> object:
        if _norm(path) == want:
            raise exc
        return real(path, *args, **kwargs)

    return fake


def _error(kind: str, target: Path) -> OSError:
    if kind == "denied":
        return PermissionError(errno.EACCES, "Permission denied", str(target))
    if kind == "absent":
        return FileNotFoundError(errno.ENOENT, "No such file or directory", str(target))
    return OSError(errno.EIO, "Input/output error", str(target))


# (site, syscall, key of the path it fails on) -- the subfolder scan is reached
# by the recursive branches only, and is enumerated for them alone.
_SITES = [
    ("target-scan", "scandir", ""),
    ("subfolder-scan", "scandir", "sub"),
    ("entry-stat", "stat", "a.txt"),
]


def _cells() -> Iterator[object]:
    for branch in _BRANCHES:
        for site, syscall, key in _SITES:
            if site == "subfolder-scan" and branch not in _RECURSIVE:
                continue
            for kind in ("denied", "absent", "other"):
                yield pytest.param(branch, syscall, key, kind, id=f"{branch}-{site}-{kind}")


def _absent_answer(branch: str, key: str) -> set[str]:
    if key == "":
        return set()
    if key == "sub":
        return _WITHOUT_SUB_SUBTREE
    return _COMPLETE[branch] - {"a.txt"}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(("branch", "syscall", "key", "kind"), list(_cells()))
def test_a_listing_maps_every_os_error_it_meets(
    backend: LocalBackend, branch: str, syscall: str, key: str, kind: str
) -> None:
    target = backend._root / key if key else backend._root
    real = _REAL_SCANDIR if syscall == "scandir" else _REAL_STAT
    with mock.patch(f"os.{syscall}", _failing(real, target, _error(kind, target))):
        if kind == "absent":
            assert _keys(_BRANCHES[branch](backend)) == _absent_answer(branch, key)
            return
        with pytest.raises(RemoteStoreError) as info:
            list(_BRANCHES[branch](backend))
    err = info.value
    assert err.path == key
    assert err.backend == "local"
    assert err.__cause__ is None
    if kind == "denied":
        assert type(err) is PermissionDenied
    else:
        # The control: an error that is not a denial must not be reported as one.
        assert type(err) is RemoteStoreError


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("branch", list(_BRANCHES))
def test_an_unfaulted_listing_is_complete(backend: LocalBackend, branch: str) -> None:
    """The baseline the absent cells subtract from: nothing is lost without a fault."""
    assert _keys(_BRANCHES[branch](backend)) == _COMPLETE[branch]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("method", ["list_files", "list_folders", "iter_children"])
def test_a_denied_listing_is_a_remote_store_error_through_the_store(backend: LocalBackend, method: str) -> None:
    store = Store(backend)
    denied = _failing(_REAL_SCANDIR, backend._root, _error("denied", backend._root))
    with mock.patch("os.scandir", denied), pytest.raises(PermissionDenied) as info:
        list(getattr(store, method)(""))
    assert isinstance(info.value, RemoteStoreError)
    assert info.value.backend == "local"


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows denies through ACLs")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads through mode 000")
@pytest.mark.parametrize("branch", _RECURSIVE)
def test_a_real_unreadable_subfolder(backend: LocalBackend, branch: str) -> None:
    sub = backend._root / "sub"
    sub.chmod(0)
    try:
        with pytest.raises(PermissionDenied) as info:
            list(_BRANCHES[branch](backend))
    finally:
        sub.chmod(0o755)
    assert info.value.path == "sub"
