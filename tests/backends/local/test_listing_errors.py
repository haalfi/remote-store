"""How ``LocalBackend``'s three listings answer an OS error met during the walk.

A listing makes three kinds of syscall: it scans the folder it was asked for,
it scans each subfolder a recursive listing descends into, and it stats each
entry to learn its type and size. Any of them can fail, and BE-021 forbids the
native exception from reaching the caller. Each failure takes one answer by its
class, the same on every syscall:

* ``FileNotFoundError`` / ``NotADirectoryError``, a symlink that never
  resolves (``ELOOP``, or Windows' winerror 1921), or Windows' drive not ready
  (21) or invalid name (123): the thing is absent, and the listing goes on as
  if it were not there. An absent target is an empty listing; a subfolder or
  entry that vanished mid-walk, or a looping link, is skipped while its
  siblings are still listed.
* ``PermissionError``: ``PermissionDenied`` naming the denied key. A recursive
  listing raises rather than leaving out the subtree it could not read, since
  a short listing that ends cleanly reads as a complete one. The exception is
  an entry that is a link into a folder the caller cannot enter, which is
  skipped (BE-021).
* Any other ``OSError``: the base ``RemoteStoreError`` naming the key, never
  ``PermissionDenied``.

The cells below are the product of branch x site x error class, with the
subfolder scan enumerated for the recursive branches only (the others make
none), so a fix that maps one syscall and forgets another fails by name. Faults are injected
by patching ``os.scandir`` / ``os.stat`` for a single path and delegating every
other call, which keeps the cells portable. Real denials check the injected
model: a POSIX ``chmod`` and a Windows ACL, and for links a real symlink or a
Windows junction (recipes: ``sdd/TESTING-RUNBOOK.md`` § Real OS denials on
Windows).
"""

from __future__ import annotations

import contextlib
import errno
import getpass
import os
import shutil
import subprocess
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

# What each branch lists when nothing fails; an absent cell that does not raise
# lists this, less what the fault made absent.
_COMPLETE = {
    "list_files": {"a.txt"},
    "list_files-recursive": set(_FILES),
    "list_files-max_depth": set(_FILES),
    "list_folders": {"sub", "other"},
    "iter_children": {"a.txt", "sub", "other"},
}


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
    if kind == "drive-not-ready":
        # Built from its winerror, as Windows raises it: CPython maps 21 to
        # EACCES, so it arrives as a ``PermissionError``.
        return OSError(0, "The device is not ready", str(target), 21)
    if kind == "invalid-name":
        return OSError(0, "The filename, directory name, or volume label syntax is incorrect", str(target), 123)
    if kind == "loop":
        if sys.platform == "win32":
            # What Windows raises for a link that resolves to itself: winerror
            # 1921, which CPython maps to errno EINVAL, not ELOOP.
            return OSError(errno.EINVAL, "The name of the file cannot be resolved", str(target), 1921)
        return OSError(errno.ELOOP, "Too many levels of symbolic links", str(target))
    return OSError(errno.EIO, "Input/output error", str(target))


# (site, syscall, key of the path it fails on) -- the subfolder scan is reached
# by the recursive branches only, and is enumerated for them alone.
_SITES = [
    ("target-scan", "scandir", ""),
    ("subfolder-scan", "scandir", "sub"),
    ("entry-stat", "stat", "a.txt"),
]


# Windows' own "absent" errors: a drive not ready and an invalid name. Their
# winerror is what classifies them, and only Windows builds one.
_WINDOWS_KINDS = ("drive-not-ready", "invalid-name")
_ON_WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="an OSError carries a winerror on Windows only")


def _cells() -> Iterator[object]:
    for branch in _BRANCHES:
        for site, syscall, key in _SITES:
            if site == "subfolder-scan" and branch not in _RECURSIVE:
                continue
            for kind in ("denied", "absent", "loop", "other", *_WINDOWS_KINDS):
                marks = [_ON_WINDOWS] if kind in _WINDOWS_KINDS else []
                yield pytest.param(branch, syscall, key, kind, id=f"{branch}-{site}-{kind}", marks=marks)


def _raised(kind: str) -> type[RemoteStoreError] | None:
    """The error a cell raises, or ``None`` for an absent cell, which lists."""
    if kind == "denied":
        return PermissionDenied
    if kind == "other":
        # The control: an error that is not a denial must not be reported as one.
        return RemoteStoreError
    return None


def _without(branch: str, key: str) -> set[str]:
    """What *branch* lists when *key*, and everything under it, is absent.

    For ``key == "sub"`` this is the subfolder skip spec 003 lists under BE-021's
    Known divergences (BUG-318): those cells pin what ships, not the clause.
    """
    if not key:
        return set()
    return {k for k in _COMPLETE[branch] if k != key and not k.startswith(f"{key}/")}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(("branch", "syscall", "key", "kind"), list(_cells()))
def test_a_listing_maps_every_os_error_it_meets(
    backend: LocalBackend, branch: str, syscall: str, key: str, kind: str
) -> None:
    target = backend._root / key if key else backend._root
    real = _REAL_SCANDIR if syscall == "scandir" else _REAL_STAT
    expected = _raised(kind)
    with mock.patch(f"os.{syscall}", _failing(real, target, _error(kind, target))):
        if expected is None:
            assert _keys(_BRANCHES[branch](backend)) == _without(branch, key)
            return
        with pytest.raises(RemoteStoreError) as info:
            list(_BRANCHES[branch](backend))
    err = info.value
    assert type(err) is expected
    assert err.path == key
    assert err.backend == "local"
    assert err.__cause__ is None


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


# Each branch run where it reaches ``sub``: a flat listing must be asked for
# ``sub`` itself, a recursive one descends into it from the root.
_REACHING_SUB: dict[str, Callable[[LocalBackend], Iterator[object]]] = {
    "list_files": lambda b: b.list_files("sub"),
    "list_files-recursive": lambda b: b.list_files("", recursive=True),
    "list_files-max_depth": lambda b: b.list_files("", recursive=True, max_depth=5),
    "list_folders": lambda b: b.list_folders("sub"),
    "iter_children": lambda b: b.iter_children("sub"),
}

_NOT_ROOT = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores permission bits")


@contextlib.contextmanager
def _acl_denied(folder: Path, rights: str) -> Iterator[None]:
    """Deny the current user *rights* on *folder*, and lift the deny afterwards.

    Only a liftable shape, per ``sdd/TESTING-RUNBOOK.md`` § Real OS denials on Windows.
    """
    user = getpass.getuser()
    denied = subprocess.run(["icacls", str(folder), "/deny", f"{user}:{rights}"], capture_output=True, check=False)
    if denied.returncode != 0:
        pytest.skip(f"icacls could not deny {rights} on this runner")
    try:
        yield
    finally:
        subprocess.run(["icacls", str(folder), "/remove:d", user], capture_output=True, check=False)


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows denies through ACLs")
@_NOT_ROOT
@pytest.mark.parametrize("branch", list(_BRANCHES))
@pytest.mark.parametrize(
    ("mode", "refused"),
    [
        pytest.param(0, {"sub"}, id="unlistable"),
        # Lists, but every entry's stat is refused; which entry is met first is scan order.
        pytest.param(0o444, {"sub/b.txt", "sub/deep"}, id="listable-not-traversable"),
    ],
)
def test_a_real_unreadable_subfolder(backend: LocalBackend, branch: str, mode: int, refused: set[str]) -> None:
    sub = backend._root / "sub"
    sub.chmod(mode)
    try:
        with pytest.raises(PermissionDenied) as info:
            list(_REACHING_SUB[branch](backend))
    finally:
        sub.chmod(0o755)
    assert info.value.path in refused


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs; POSIX is the chmod test above")
@pytest.mark.parametrize("branch", list(_BRANCHES))
def test_a_subfolder_denied_by_acl(backend: LocalBackend, branch: str) -> None:
    """``(RD)`` refuses listing the folder; its own ``stat`` still succeeds."""
    with _acl_denied(backend._root / "sub", "(RD)"), pytest.raises(PermissionDenied) as info:
        list(_REACHING_SUB[branch](backend))
    assert info.value.path == "sub"


# What each branch lists for ``sub`` when nothing fails; the links below sit in
# ``sub`` beside these entries.
_COMPLETE_SUB = {
    "list_files": {"sub/b.txt"},
    "list_files-recursive": {"sub/b.txt", "sub/deep/c.txt"},
    "list_files-max_depth": {"sub/b.txt", "sub/deep/c.txt"},
    "list_folders": {"sub/deep"},
    "iter_children": {"sub/b.txt", "sub/deep"},
}

_IN_SUB: dict[str, Callable[[LocalBackend], Iterator[object]]] = {
    "list_files": lambda b: b.list_files("sub"),
    "list_files-recursive": lambda b: b.list_files("sub", recursive=True),
    "list_files-max_depth": lambda b: b.list_files("sub", recursive=True, max_depth=5),
    "list_folders": lambda b: b.list_folders("sub"),
    "iter_children": lambda b: b.iter_children("sub"),
}


@contextlib.contextmanager
def _links_into_a_locked_folder(root: Path) -> Iterator[str]:
    """Put links in ``sub`` into a folder the caller cannot enter; yield a folder link's key.

    Windows: a directory junction, which needs no privilege, into a folder
    denied ``(S)``, so a ``stat`` through the junction is refused. POSIX: a file
    and a folder symlink into a folder at mode 000. The locked folder sits
    outside ``sub``, so only the links lead into it.
    """
    locked = root / "locked"
    (locked / "inner").mkdir(parents=True)
    (locked / "x.txt").write_bytes(b"x")
    if sys.platform == "win32":
        import _winapi  # type: ignore[import-not-found,unused-ignore]  # Windows-only module

        _winapi.CreateJunction(str(locked), str(root / "sub" / "j"))
        with _acl_denied(locked, "(S)"):
            yield "sub/j"
        return
    (root / "sub" / "lf").symlink_to(locked / "x.txt")
    (root / "sub" / "ld").symlink_to(locked / "inner", target_is_directory=True)
    locked.chmod(0)
    try:
        yield "sub/ld"
    finally:
        locked.chmod(0o755)


@pytest.mark.spec("BE-021")
@_NOT_ROOT
@pytest.mark.parametrize("branch", list(_BRANCHES))
def test_a_link_into_a_folder_the_caller_cannot_enter_is_skipped(backend: LocalBackend, branch: str) -> None:
    """The link is readable as a link; only its target is refused, so the listed folder was not denied."""
    with _links_into_a_locked_folder(backend._root):
        assert _keys(_IN_SUB[branch](backend)) == _COMPLETE_SUB[branch]


@pytest.mark.spec("BE-021")
@_NOT_ROOT
@pytest.mark.parametrize("branch", list(_BRANCHES))
def test_listing_a_link_into_a_folder_the_caller_cannot_enter_raises(backend: LocalBackend, branch: str) -> None:
    """The skip is for an entry: asked for the link itself, the listing is refused the folder it lists."""
    lister = {
        "list_files": lambda b, k: b.list_files(k),
        "list_files-recursive": lambda b, k: b.list_files(k, recursive=True),
        "list_files-max_depth": lambda b, k: b.list_files(k, recursive=True, max_depth=5),
        "list_folders": lambda b, k: b.list_folders(k),
        "iter_children": lambda b, k: b.iter_children(k),
    }[branch]
    with _links_into_a_locked_folder(backend._root) as link, pytest.raises(PermissionDenied) as info:
        list(lister(backend, link))
    assert info.value.path == link


@pytest.mark.skipif(sys.platform != "win32", reason="the classic delete disposition is a Windows state")
@pytest.mark.parametrize("branch", _RECURSIVE)
def test_a_subfolder_in_the_classic_delete_pending_state_raises(backend: LocalBackend, branch: str) -> None:
    """A folder whose classic delete disposition is set while another handle stays open.

    It is still listed by its parent and still ``stat``\\ s, but its scan fails
    with ``winerror`` 5, the code a real denial carries, so the walk raises
    ``PermissionDenied`` where master skipped it. Python's own ``rmdir`` and
    ``rmtree`` delete the POSIX way and never leave this state. Pins what ships,
    not BE-021: spec 003 lists it under BE-021's Known divergences, so the test
    carries no spec mark.
    """
    import ctypes
    from ctypes import wintypes

    sub = backend._root / "sub"
    shutil.rmtree(sub / "deep")
    (sub / "b.txt").unlink()
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    k32.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    share_all, open_existing, backup_semantics = 0x7, 3, 0x02000000
    list_directory, delete = 0x1, 0x00010000
    file_disposition_info = 4

    def open_handle(access: int) -> int:
        handle = k32.CreateFileW(str(sub), access, share_all, None, open_existing, backup_semantics, None)
        if handle == wintypes.HANDLE(-1).value:
            pytest.fail(f"CreateFileW failed: winerror {ctypes.get_last_error()}")
        return handle

    holder = open_handle(list_directory)
    try:
        deleter = open_handle(delete)
        delete_file = wintypes.BOOLEAN(1)
        disposed = k32.SetFileInformationByHandle(
            deleter, file_disposition_info, ctypes.byref(delete_file), ctypes.sizeof(delete_file)
        )
        k32.CloseHandle(deleter)
        if not disposed:
            pytest.fail(f"the delete disposition was not set: winerror {ctypes.get_last_error()}")
        with pytest.raises(PermissionError) as state:
            os.scandir(sub).close()
        assert state.value.winerror == 5  # type: ignore[attr-defined]
        with pytest.raises(PermissionDenied) as info:
            list(_BRANCHES[branch](backend))
    finally:
        k32.CloseHandle(holder)
    assert info.value.path == "sub"


@pytest.mark.parametrize("branch", _RECURSIVE)
def test_a_subfolder_deleted_during_the_walk_is_skipped(backend: LocalBackend, branch: str) -> None:
    """The walk is lazy and top-down: the root's files come before ``sub`` is scanned.

    Pins what ships, not BE-021: spec 003 lists this skip under BE-021's Known
    divergences (BUG-318), so the test carries no spec mark.
    """
    listing = _BRANCHES[branch](backend)
    assert str(next(listing).path) == "a.txt"  # type: ignore[attr-defined]
    shutil.rmtree(backend._root / "sub")
    assert _keys(listing) == {"other/d.txt"}


@pytest.mark.spec("BE-014")
@pytest.mark.parametrize(
    "listing",
    [
        lambda b: b.list_files("a.txt"),
        lambda b: b.list_files("a.txt", recursive=True),
        lambda b: b.list_files("a.txt", recursive=True, max_depth=5),
        lambda b: b.list_folders("a.txt"),
        lambda b: b.iter_children("a.txt"),
    ],
    ids=list(_BRANCHES),
)
def test_a_file_path_lists_empty(backend: LocalBackend, listing: Callable[[LocalBackend], Iterator[object]]) -> None:
    """A real non-folder target: its scan answers ``NotADirectoryError``, which is absent."""
    assert _keys(listing(backend)) == set()


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="creating a symlink needs a privilege Windows does not grant")
@pytest.mark.parametrize("branch", list(_BRANCHES))
def test_a_real_symlink_loop_is_skipped(backend: LocalBackend, branch: str) -> None:
    for link in (backend._root / "loop", backend._root / "sub" / "loop"):
        link.symlink_to(link)
    assert _keys(_BRANCHES[branch](backend)) == _COMPLETE[branch]
