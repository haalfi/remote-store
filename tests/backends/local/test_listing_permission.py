"""What ``LocalBackend``'s single-level scans answer when the OS refuses to list a folder or ``stat`` an entry.

BE-021's canonical table maps an operation the OS denies to ``PermissionDenied``,
and its invariant says no native exception leaks. ``list_files`` (non-recursive),
``list_folders`` and ``iter_children`` met neither:

- a folder the OS refused to list let the raw ``PermissionError`` escape,
  carrying no ``path`` or ``backend``;
- each entry was classified with ``Path.is_file`` / ``is_dir``, which on 3.14
  answer ``False`` for an entry the OS refuses to ``stat``, so a folder that
  lists but cannot be traversed lost its entries silently, and which left a
  window between classifying a file and measuring it in which a removal leaked
  a raw ``FileNotFoundError``.

The cells enumerate entry point x denied site rather than sampling them. A
listing denial is injected at ``os.scandir`` and ``os.listdir``, the two calls
the scans list through on 3.11 to 3.14, and an entry denial at ``os.stat``. Real
denials repeat the cases: POSIX ``chmod`` (unlistable, and listable but not
traversable), a POSIX symlink into a locked folder, and on Windows an ACL and a
junction into a denied folder.

The recursive walks keep their traversal. The cells at the end pin two things
about them: ``list_files(recursive=True)`` reaches the caller mapped where it
raises, and the walks still drop a denied folder (the listed one or a
subfolder). The second is pinned as strict ``xfail``\\ s, so the change that
fixes the walks has to remove the marks.
"""

from __future__ import annotations

import contextlib
import errno
import genericpath
import getpass
import glob
import os
import stat
import subprocess
import sys
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from remote_store._errors import PermissionDenied, RemoteStoreError
from remote_store._store import Store
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager
    from pathlib import Path

# The denial reaches the scans through ``pathlib``, whose error handling differs
# by interpreter and platform — the reason this module runs wherever the mark does.
pytestmark = pytest.mark.os_sensitive

_REAL_SCANDIR = os.scandir
_REAL_LISTDIR = os.listdir
_REAL_STAT = os.stat
_REAL_LSTAT = os.lstat


def _tree(root: Path) -> LocalBackend:
    """``a/f.txt``, ``a/sub/g.txt``: one file at each of two levels."""
    (root / "a" / "sub").mkdir(parents=True)
    (root / "a" / "f.txt").write_bytes(b"f")
    (root / "a" / "sub" / "g.txt").write_bytes(b"g")
    return LocalBackend(root=str(root))


def _norm(p: Any) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(p)))


def _deny(target: Path, exc: OSError, hits: list[str] | None = None) -> AbstractContextManager[Any]:
    """Patch the directory-listing calls to raise *exc* for *target* only.

    Each injection is appended to *hits*, so a cell can prove the denial was
    met rather than assume it. On 3.13 ``Path.rglob`` lists through
    ``glob._StringGlobber.scandir``, a copy of ``os.scandir`` bound when
    ``glob`` is imported, which a patch on ``os`` never reaches; that copy is
    patched too. 3.14's wrapper looks ``os.scandir`` up at call time, and 3.11
    and 3.12 have no such class.
    """
    resolved = _norm(target.resolve())

    def scandir(p: object = ".") -> object:
        if _norm(p) == resolved:
            if hits is not None:
                hits.append("scandir")
            raise exc
        return _REAL_SCANDIR(p)  # type: ignore[arg-type]

    def listdir(p: object = ".") -> list[str]:
        if _norm(p) == resolved:
            if hits is not None:
                hits.append("listdir")
            raise exc
        return _REAL_LISTDIR(p)  # type: ignore[arg-type]

    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.multiple(os, scandir=scandir, listdir=listdir))
    globber = getattr(glob, "_StringGlobber", None)
    bound = vars(globber).get("scandir") if globber is not None else None
    if isinstance(bound, staticmethod) and bound.__func__ is _REAL_SCANDIR:
        stack.enter_context(mock.patch.object(globber, "scandir", staticmethod(scandir)))
    return stack


def _deny_child_stat(folder: Path) -> AbstractContextManager[Any]:
    """Refuse ``stat`` on every entry directly inside *folder*, but not on *folder*.

    That is what a folder the caller may list but not traverse does: a POSIX
    ``0o444`` directory for a non-root user lists its names and fails every
    child's ``stat`` with ``EACCES``. ``os.path.isfile`` and ``isdir`` are swapped
    for POSIX's ``genericpath`` forms too, because on 3.14 ``Path.is_file`` and
    ``is_dir`` ask them, and the POSIX forms turn that ``EACCES`` into ``False``
    — the silent skip — while Windows' native forms never reach this patch.
    """
    # Compared lexically: resolving inside a ``stat`` patch would re-enter it.
    denied_parent = _norm(folder.resolve())

    def stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if os.path.dirname(_norm(p)) == denied_parent:
            raise PermissionError(errno.EACCES, "Permission denied", os.fspath(p))
        return _REAL_STAT(p, *args, **kwargs)

    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.object(os, "stat", stat))
    stack.enter_context(mock.patch.object(os.path, "isfile", genericpath.isfile))
    stack.enter_context(mock.patch.object(os.path, "isdir", genericpath.isdir))
    return stack


def _denied() -> PermissionError:
    return PermissionError(errno.EACCES, "Permission denied")


def _keys(items: Iterable[Any]) -> set[str]:
    return {str(item.path) for item in items}


# Each entry runs one scan of ``a`` to completion and returns the listed keys.
_ENTRY_POINTS: dict[str, Callable[[LocalBackend], set[str]]] = {
    "list_files": lambda b: _keys(b.list_files("a")),
    "list_folders": lambda b: _keys(b.list_folders("a")),
    "iter_children": lambda b: _keys(b.iter_children("a")),
}

# The clause each entry point's absence answer is traced to.
_ABSENCE_CLAUSE = {"list_files": "BE-014", "list_folders": "BE-015", "iter_children": "BE-026"}


def _traced(entries: Iterable[str]) -> list[Any]:
    return [pytest.param(e, id=e, marks=pytest.mark.spec(_ABSENCE_CLAUSE[e])) for e in entries]


def _assert_mapped(info: pytest.ExceptionInfo[PermissionDenied], path: str = "a") -> None:
    err = info.value
    assert type(err) is PermissionDenied
    assert err.path == path
    assert err.backend == "local"
    # ``from None``, like every other mapped raise in the module: the native
    # exception is not chained onto the one the caller sees.
    assert err.__cause__ is None
    assert err.__suppress_context__ is True


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_denied_listed_folder_raises_permission_denied(tmp_path: Path, entry: str) -> None:
    backend = _tree(tmp_path)
    with _deny(tmp_path / "a", _denied()), pytest.raises(PermissionDenied) as info:
        _ENTRY_POINTS[entry](backend)
    _assert_mapped(info)


# What each scan answers for ``a`` when only ``a/sub`` is denied: a single-level
# scan never opens ``a/sub``, so the denial must not reach it.
_WITH_SUB_DENIED: dict[str, set[str]] = {
    "list_files": {"a/f.txt"},
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_denied_subfolder_does_not_reach_a_single_level_scan(tmp_path: Path, entry: str) -> None:
    backend = _tree(tmp_path)
    with _deny(tmp_path / "a" / "sub", _denied()):
        assert _ENTRY_POINTS[entry](backend) == _WITH_SUB_DENIED[entry]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_an_entry_the_os_refuses_to_stat_raises_permission_denied(tmp_path: Path, entry: str) -> None:
    """A folder that lists but cannot be traversed raises, rather than listing as empty.

    The message names the refused entry, so the caller can tell it from a
    refusal of the listed folder itself.
    """
    backend = _tree(tmp_path)
    with _deny_child_stat(tmp_path / "a"), pytest.raises(PermissionDenied) as info:
        _ENTRY_POINTS[entry](backend)
    _assert_mapped(info)
    assert "f.txt" in str(info.value) or "sub" in str(info.value)


_ON_SUB: dict[str, Callable[[LocalBackend], set[str]]] = {
    "list_files": lambda b: _keys(b.list_files("a/sub")),
    "list_folders": lambda b: _keys(b.list_folders("a/sub")),
    "iter_children": lambda b: _keys(b.iter_children("a/sub")),
}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ON_SUB))
def test_a_folder_whose_parent_cannot_be_traversed_raises_rather_than_reading_as_absent(
    tmp_path: Path, entry: str
) -> None:
    """The scanned folder is classified by a ``stat`` that may be refused too.

    A missing folder lists as nothing, so a folder the OS refuses to ``stat``
    must not be taken for a missing one.
    """
    backend = _tree(tmp_path)
    with _deny_child_stat(tmp_path / "a"), pytest.raises(PermissionDenied) as info:
        _ON_SUB[entry](backend)
    _assert_mapped(info, path="a/sub")


# What each scan answers when ``a/f.txt`` is there for its first ``stat`` and
# gone for every later one.
_WITH_F_GONE_AFTER_FIRST_STAT: dict[str, set[str]] = {
    "list_files": {"a/f.txt"},
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_file_removed_after_it_was_classified_does_not_leak(tmp_path: Path, entry: str) -> None:
    """Each entry is classified and measured by one ``stat``, so no later one can find it gone.

    Classifying with ``is_file()`` and then measuring with a second ``stat``
    leaves a window in which a removed file surfaces as a raw
    ``FileNotFoundError``. Frozen here by letting ``a/f.txt``'s first ``stat``
    succeed and every later one fail.
    """
    backend = _tree(tmp_path)
    target = _norm((tmp_path / "a" / "f.txt").resolve())
    seen: list[int] = []

    def stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if _norm(p) == target:
            seen.append(1)
            if len(seen) > 1:
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", os.fspath(p))
        return _REAL_STAT(p, *args, **kwargs)

    with mock.patch.object(os, "stat", stat):
        assert _ENTRY_POINTS[entry](backend) == _WITH_F_GONE_AFTER_FIRST_STAT[entry]


# What each scan answers when ``a/f.txt`` is listed but already gone when its
# ``stat`` runs: everything but that file.
_WITH_F_GONE_BEFORE_STAT: dict[str, set[str]] = {
    "list_files": set(),
    "list_folders": {"a/sub"},
    "iter_children": {"a/sub"},
}


# The errors a ``stat`` answers for a path that is not there, which the scans
# read as absence: the set ``Path.is_file`` / ``is_dir`` read as ``False`` on
# 3.11 to 3.13, one cell per member. ``winerror`` exists only on Windows, where
# Python builds 21 (drive not ready) as a ``PermissionError``.
_ON_WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="winerror exists on Windows only")
_ABSENCE: list[Any] = [
    pytest.param(lambda p: OSError(errno.ENOENT, os.strerror(errno.ENOENT), p), id="ENOENT"),
    pytest.param(lambda p: OSError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), p), id="ENOTDIR"),
    pytest.param(lambda p: OSError(errno.EBADF, os.strerror(errno.EBADF), p), id="EBADF"),
    pytest.param(lambda p: OSError(errno.ELOOP, os.strerror(errno.ELOOP), p), id="ELOOP-link-loop"),
    pytest.param(lambda p: OSError(0, "drive not ready", p, 21), id="winerror-21", marks=_ON_WINDOWS),
    pytest.param(lambda p: OSError(0, "invalid name", p, 123), id="winerror-123", marks=_ON_WINDOWS),
    pytest.param(lambda p: OSError(0, "cannot resolve", p, 1921), id="winerror-1921", marks=_ON_WINDOWS),
]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("absence", _ABSENCE)
@pytest.mark.parametrize("entry", _traced(_WITH_F_GONE_BEFORE_STAT))
def test_an_entry_gone_before_its_stat_is_skipped(
    tmp_path: Path, entry: str, absence: Callable[[str], OSError]
) -> None:
    """An entry the scan listed but its ``stat`` no longer finds drops out of the answer."""
    backend = _tree(tmp_path)
    target = _norm((tmp_path / "a" / "f.txt").resolve())

    def stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if _norm(p) == target:
            raise absence(os.fspath(p))
        return _REAL_STAT(p, *args, **kwargs)

    with mock.patch.object(os, "stat", stat):
        assert _ENTRY_POINTS[entry](backend) == _WITH_F_GONE_BEFORE_STAT[entry]


# Where a scan meets an ``OSError`` that is neither a denial nor an absence.
# ``entry-lstat``: the entry's ``stat`` is refused, and the ``lstat`` that
# asks whether it is a link fails with ``EIO``.
_EIO_SITES = ["listed-folder-stat", "entry-stat", "entry-lstat", "listed-folder-scan"]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("site", _EIO_SITES)
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_an_os_error_that_is_neither_denial_nor_absence_raises_a_mapped_error(
    tmp_path: Path, entry: str, site: str
) -> None:
    """An I/O error is reported, not read as an empty folder or a missing entry.

    BE-021 permits a silent answer only for the absences and links it names;
    everything else is mapped and raised, as SFTP does for ``EIO``.
    """
    backend = _tree(tmp_path)
    patch: AbstractContextManager[Any]
    if site == "listed-folder-scan":
        patch = _deny(tmp_path / "a", OSError(errno.EIO, os.strerror(errno.EIO)))
    elif site == "entry-lstat":
        entry_path = _norm((tmp_path / "a" / "f.txt").resolve())

        def refused_stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            if _norm(p) == entry_path:
                raise PermissionError(errno.EACCES, "Permission denied", os.fspath(p))
            return _REAL_STAT(p, *args, **kwargs)

        def failing_lstat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            if _norm(p) == entry_path:
                raise OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(p))
            return _REAL_LSTAT(p, *args, **kwargs)

        patch = mock.patch.multiple(os, stat=refused_stat, lstat=failing_lstat)
    else:
        leaf = "a" if site == "listed-folder-stat" else "a/f.txt"
        target = _norm((tmp_path / leaf).resolve())

        def stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            if _norm(p) == target:
                raise OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(p))
            return _REAL_STAT(p, *args, **kwargs)

        patch = mock.patch.object(os, "stat", stat)
    with patch, pytest.raises(RemoteStoreError) as info:
        _ENTRY_POINTS[entry](backend)
    err = info.value
    assert type(err) is RemoteStoreError
    assert err.path == "a"
    assert err.backend == "local"
    assert err.__cause__ is None
    assert err.__suppress_context__ is True
    # The message names what failed, so an entry's error is not read as the
    # listed folder's.
    assert os.strerror(errno.EIO) in str(err)
    if site in ("entry-stat", "entry-lstat"):
        assert "f.txt" in str(err)


@pytest.mark.parametrize("gone", [FileNotFoundError, NotADirectoryError], ids=["removed", "replaced-by-a-file"])
@pytest.mark.parametrize("entry", _traced(_ENTRY_POINTS))
def test_a_folder_gone_between_its_stat_and_its_scan_is_an_absence(
    tmp_path: Path, entry: str, gone: type[OSError]
) -> None:
    """The scanned folder may vanish after it was classified, before it is opened.

    It answers as the absent folder it now is, listing nothing, not with the
    raw ``FileNotFoundError`` or ``NotADirectoryError`` the scan meets.
    """
    backend = _tree(tmp_path)
    errno_ = errno.ENOENT if gone is FileNotFoundError else errno.ENOTDIR
    with _deny(tmp_path / "a", gone(errno_, os.strerror(errno_))):
        assert _ENTRY_POINTS[entry](backend) == set()


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", ["list_files", "iter_children"])
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
)
def test_a_broken_symlink_is_not_listed(tmp_path: Path, entry: str) -> None:
    """A dangling link is skipped rather than failing its ``stat``."""
    backend = _tree(tmp_path)
    (tmp_path / "a" / "dangling.txt").symlink_to(tmp_path / "nowhere.txt")
    expected = {"list_files": {"a/f.txt"}, "iter_children": {"a/f.txt", "a/sub"}}[entry]
    assert _ENTRY_POINTS[entry](backend) == expected


# What each scan answers for ``a`` when it also holds a link it may not follow:
# the tree without that link.
_WITH_LINK_SKIPPED: dict[str, set[str]] = {
    "list_files": {"a/f.txt"},
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("lstat_meets", ["a-link", "the-link-gone"])
@pytest.mark.parametrize("entry", list(_WITH_LINK_SKIPPED))
def test_a_link_whose_target_the_os_refuses_to_stat_is_skipped(tmp_path: Path, entry: str, lstat_meets: str) -> None:
    """A link into a folder the caller cannot enter is skipped, like a dangling one.

    Its ``stat`` follows it and is refused, but the folder being listed is not
    the thing denied. Simulated here, so it runs where symlinks cannot be made:
    ``a/link`` is a plain file whose ``lstat`` reports a link and whose ``stat``
    is refused. A refused ``stat`` on an entry that is not a link still raises
    (``test_an_entry_the_os_refuses_to_stat_raises_permission_denied``). The
    ``the-link-gone`` cell removes the link between the two calls, which BE-021
    skips as an entry gone before its metadata was read.
    """
    backend = _tree(tmp_path)
    (tmp_path / "a" / "link").write_bytes(b"")
    target = _norm((tmp_path / "a" / "link").resolve())
    link_mode = os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def stat_(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if _norm(p) == target:
            raise PermissionError(errno.EACCES, "Permission denied", os.fspath(p))
        return _REAL_STAT(p, *args, **kwargs)

    def lstat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if _norm(p) == target:
            if lstat_meets == "the-link-gone":
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), os.fspath(p))
            return link_mode
        return _REAL_LSTAT(p, *args, **kwargs)

    with mock.patch.multiple(os, stat=stat_, lstat=lstat):
        assert _ENTRY_POINTS[entry](backend) == _WITH_LINK_SKIPPED[entry]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_WITH_LINK_SKIPPED))
@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need a privilege; the simulated cell above runs here")
@pytest.mark.skipif(getattr(os, "geteuid", lambda: -1)() == 0, reason="root ignores permission bits")
def test_a_real_link_into_an_unenterable_folder_is_skipped(tmp_path: Path, entry: str) -> None:
    """The link cell above against a real symlink and a real ``chmod``."""
    backend = _tree(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "x.txt").write_bytes(b"x")
    (tmp_path / "a" / "link").symlink_to(locked / "x.txt")
    locked.chmod(0)
    try:
        listed = _ENTRY_POINTS[entry](backend)
    finally:
        locked.chmod(0o755)
    assert listed == _WITH_LINK_SKIPPED[entry]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_WITH_LINK_SKIPPED))
@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions exist on Windows only")
def test_a_junction_into_a_folder_denied_by_acl_is_skipped(tmp_path: Path, entry: str) -> None:
    """A Windows directory junction is a link too, though ``lstat`` does not report it as one.

    Junctions need no privilege to create, so they are the link a Windows user
    most often has. Its target is denied by a real ACL: ``SYNCHRONIZE``, which
    every open asks for, so the junction's ``stat`` is refused. Denying full
    control would also deny the read-control and write-DAC rights ``icacls``
    needs to lift the denial again, leaving a folder only an administrator can
    remove.
    """
    import _winapi  # type: ignore[import-not-found]  # Windows-only module

    backend = _tree(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    _winapi.CreateJunction(str(locked), str(tmp_path / "a" / "j"))
    user = getpass.getuser()
    denied = subprocess.run(["icacls", str(locked), "/deny", f"{user}:(S)"], capture_output=True, check=False)
    if denied.returncode != 0:
        pytest.skip("icacls could not deny access on this runner")
    try:
        listed = _ENTRY_POINTS[entry](backend)
    finally:
        subprocess.run(["icacls", str(locked), "/remove:d", user], capture_output=True, check=False)
    assert listed == _WITH_LINK_SKIPPED[entry]


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows denies through ACLs")
@pytest.mark.skipif(getattr(os, "geteuid", lambda: -1)() == 0, reason="root ignores permission bits")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
@pytest.mark.parametrize(
    "mode",
    [pytest.param(0, id="unlistable"), pytest.param(0o444, id="listable-not-traversable")],
)
def test_a_really_unreadable_folder_raises_permission_denied(tmp_path: Path, entry: str, mode: int) -> None:
    """The scans against a real ``chmod`` rather than an injection.

    ``0o444`` is the shape ``Path.is_file`` used to hide on 3.14: the folder
    lists, and every entry's ``stat`` fails.
    """
    backend = _tree(tmp_path)
    folder = tmp_path / "a"
    folder.chmod(mode)
    try:
        with pytest.raises(PermissionDenied) as info:
            _ENTRY_POINTS[entry](backend)
    finally:
        folder.chmod(0o755)
    _assert_mapped(info)


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs; POSIX is the chmod cell above")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_folder_denied_by_acl_raises_permission_denied(tmp_path: Path, entry: str) -> None:
    """The scans against a real ACL denial of "list folder" on Windows."""
    backend = _tree(tmp_path)
    folder = tmp_path / "a"
    user = getpass.getuser()
    denied = subprocess.run(["icacls", str(folder), "/deny", f"{user}:(RD)"], capture_output=True, check=False)
    if denied.returncode != 0:
        pytest.skip("icacls could not deny list access on this runner")
    try:
        with pytest.raises(PermissionDenied) as info:
            _ENTRY_POINTS[entry](backend)
    finally:
        subprocess.run(["icacls", str(folder), "/remove:d", user], capture_output=True, check=False)
    _assert_mapped(info)


# The recursive walks are left as they were: a folder the OS refuses to list,
# the listed one or a subfolder, is dropped from a recursive listing and from
# ``get_folder_info``'s total with no error. Moving them onto RFC-0017's listing
# kernel (BK-416) is what fixes that; strict, so that change has to remove
# these marks. ``raises=AssertionError``: only the missing ``PermissionDenied``
# is the expected failure; a denial the walk never met fails the cell outright.
_RECURSIVE_SKIP_DENIED = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BK-416: the recursive walks still drop a folder the OS refuses to list",
)

_RECURSIVE: dict[str, Callable[[LocalBackend], object]] = {
    "list_files-recursive": lambda b: _keys(b.list_files("a", recursive=True)),
    "list_files-recursive-max_depth": lambda b: _keys(b.list_files("a", recursive=True, max_depth=5)),
    "get_folder_info": lambda b: b.get_folder_info("a").file_count,
    "Store.get_folder_info": lambda b: Store(backend=b).get_folder_info("a").file_count,
}


@_RECURSIVE_SKIP_DENIED
@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("denied", ["a/sub", "a"], ids=["subfolder", "listed-folder"])
@pytest.mark.parametrize("entry", list(_RECURSIVE))
def test_a_recursive_walk_raises_on_a_denied_folder(tmp_path: Path, entry: str, denied: str) -> None:
    """What BE-021 asks of a recursive walk that meets a folder it may not list."""
    backend = _tree(tmp_path)
    hits: list[str] = []
    raised = False
    with _deny(tmp_path / denied, _denied(), hits):
        try:
            _RECURSIVE[entry](backend)
        except PermissionDenied:
            raised = True
    if not hits:
        pytest.fail("the denial never reached the walk, so this cell tests nothing")
    assert raised, "the walk met the denied folder and dropped it silently"


# Plain ``rglob`` classifies with ``Path.is_file``, which on 3.14 answers
# ``False`` for an entry it may not ``stat`` and so skips it; BK-416 owns that.
_SKIPS_ON_314 = pytest.mark.xfail(
    sys.version_info >= (3, 14),
    strict=True,
    raises=pytest.fail.Exception,
    reason="BK-416: on 3.14 the plain recursive walk skips an entry it may not stat",
)


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda b: list(b.list_files("a", recursive=True)), id="recursive", marks=_SKIPS_ON_314),
        pytest.param(lambda b: list(b.list_files("a", recursive=True, max_depth=5)), id="recursive-max_depth"),
    ],
)
def test_a_recursive_list_files_maps_a_denial_it_meets(tmp_path: Path, call: Callable[[LocalBackend], object]) -> None:
    """Where a recursive walk does raise on a denial, it raises ``PermissionDenied``, never the bare error.

    The walks stay inside ``list_files``' mapping, so an entry in ``a/sub``
    that the OS refuses to ``stat`` reaches the caller mapped. Moving the walk
    out of that ``try`` would leak the native error again.
    """
    backend = _tree(tmp_path)
    with _deny_child_stat(tmp_path / "a" / "sub"), pytest.raises(PermissionDenied) as info:
        call(backend)
    _assert_mapped(info)
