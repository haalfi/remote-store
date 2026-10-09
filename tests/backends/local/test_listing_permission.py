"""What ``LocalBackend``'s folder walks answer when the OS refuses to list a folder or ``stat`` an entry.

BE-021's canonical table maps an operation the OS denies to ``PermissionDenied``,
and its invariant says no native exception leaks. The walks met neither, in
three different ways:

- the single-level scans (``list_files``, ``list_folders``, ``iter_children``)
  let the raw ``PermissionError`` escape, carrying no ``path`` or ``backend``;
- the recursive walks — both ``list_files`` branches and ``get_folder_info`` —
  dropped a denied subtree **silently**: ``os.walk``'s default ``onerror=None``
  and ``Path.rglob``'s selector each swallow the error, so a partly unreadable
  tree came back as a short listing or an under-counted aggregate that looked
  complete, and a denied top folder as empty;
- every walk classified an entry with ``Path.is_file`` / ``is_dir``, which on
  3.14 answer ``False`` for an entry the OS refuses to ``stat``, so a folder
  that lists but cannot be traversed lost all its entries silently, and which
  left a window between classifying a file and measuring it in which a removal
  leaked a raw ``FileNotFoundError``.

The cells enumerate entry point x denied site rather than sampling them, because
the shapes above live in different branches and methods, and a fix to one says
nothing about the others. ``Store.get_folder_info`` is enumerated too, because it
reaches the backend's aggregate for ``max_depth=None`` and ``list_files`` for any
other value: one method, two walks, which must answer a denial alike. They do at
every site but one, a starting folder whose parent cannot be traversed, where
the ``max_depth`` form asks ``is_folder`` first; that cell is a strict ``xfail``.

A listing denial is injected at ``os.scandir`` and ``os.listdir``, the two calls
every walk here lists through on 3.11 to 3.14, and an entry denial at
``os.stat``. One POSIX cell repeats the recursive cases against a real
``chmod`` (unlistable, and listable but not traversable), and one Windows cell
against a real ACL denial.
"""

from __future__ import annotations

import contextlib
import errno
import genericpath
import getpass
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from remote_store._errors import PermissionDenied
from remote_store._store import Store
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from contextlib import AbstractContextManager

# The denial reaches the listings through ``pathlib`` and ``os.walk``, whose
# error handling differs by interpreter and platform — the reason this module
# runs wherever the mark does.
pytestmark = pytest.mark.os_sensitive

_REAL_SCANDIR = os.scandir
_REAL_LISTDIR = os.listdir


def _tree(root: Path) -> LocalBackend:
    """``a/f.txt``, ``a/sub/g.txt``: one file at each of two levels."""
    (root / "a" / "sub").mkdir(parents=True)
    (root / "a" / "f.txt").write_bytes(b"f")
    (root / "a" / "sub" / "g.txt").write_bytes(b"g")
    return LocalBackend(root=str(root))


def _deny(target: Path, exc: OSError) -> AbstractContextManager[Any]:
    """Patch both directory-listing calls to raise *exc* for *target* only."""
    resolved = target.resolve()

    def _is_target(p: object) -> bool:
        return Path(os.fspath(p)).resolve() == resolved  # type: ignore[arg-type]

    def scandir(p: object = ".") -> object:
        if _is_target(p):
            raise exc
        return _REAL_SCANDIR(p)  # type: ignore[arg-type]

    def listdir(p: object = ".") -> list[str]:
        if _is_target(p):
            raise exc
        return _REAL_LISTDIR(p)  # type: ignore[arg-type]

    return mock.patch.multiple(os, scandir=scandir, listdir=listdir)


def _denied() -> PermissionError:
    return PermissionError(errno.EACCES, "Permission denied")


def _keys(items: Iterable[Any]) -> set[str]:
    return {str(item.path) for item in items}


# Each entry runs one walk of ``a`` to completion and returns what it answered:
# the listed keys, or the aggregate's file count.
_ENTRY_POINTS: dict[str, Callable[[LocalBackend], object]] = {
    "list_files": lambda b: _keys(b.list_files("a")),
    "list_files-recursive": lambda b: _keys(b.list_files("a", recursive=True)),
    "list_files-recursive-max_depth": lambda b: _keys(b.list_files("a", recursive=True, max_depth=5)),
    "list_folders": lambda b: _keys(b.list_folders("a")),
    "iter_children": lambda b: _keys(b.iter_children("a")),
    "get_folder_info": lambda b: b.get_folder_info("a").file_count,
    "Store.get_folder_info": lambda b: Store(backend=b).get_folder_info("a").file_count,
    "Store.get_folder_info-max_depth": lambda b: Store(backend=b).get_folder_info("a", max_depth=5).file_count,
}

# What each entry point answers for ``a`` when only ``a/sub`` is denied. The
# single-level scans never open ``a/sub``, so the denial must not reach them;
# ``None`` marks the recursive walks, which do open it and must raise.
_WITH_SUB_DENIED: dict[str, object] = {
    "list_files": {"a/f.txt"},
    "list_files-recursive": None,
    "list_files-recursive-max_depth": None,
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
    "get_folder_info": None,
    "Store.get_folder_info": None,
    "Store.get_folder_info-max_depth": None,
}


def _assert_mapped(info: pytest.ExceptionInfo[PermissionDenied]) -> None:
    err = info.value
    assert type(err) is PermissionDenied
    assert err.path == "a"
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


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_denied_subfolder_raises_only_where_the_listing_descends(tmp_path: Path, entry: str) -> None:
    """A recursive walk raises rather than answering from the readable part of the tree."""
    backend = _tree(tmp_path)
    expected = _WITH_SUB_DENIED[entry]
    with _deny(tmp_path / "a" / "sub", _denied()):
        if expected is None:
            with pytest.raises(PermissionDenied) as info:
                _ENTRY_POINTS[entry](backend)
            _assert_mapped(info)
        else:
            assert _ENTRY_POINTS[entry](backend) == expected


_REAL_STAT = os.stat


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


def _norm(p: Any) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(p)))


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_child_the_os_refuses_to_stat_raises_permission_denied(tmp_path: Path, entry: str) -> None:
    """A folder that lists but cannot be traversed raises, rather than listing as empty."""
    backend = _tree(tmp_path)
    with _deny_child_stat(tmp_path / "a"), pytest.raises(PermissionDenied) as info:
        _ENTRY_POINTS[entry](backend)
    _assert_mapped(info)


_ON_SUB: dict[str, Callable[[LocalBackend], object]] = {
    "list_files": lambda b: _keys(b.list_files("a/sub")),
    "list_files-recursive": lambda b: _keys(b.list_files("a/sub", recursive=True)),
    "list_folders": lambda b: _keys(b.list_folders("a/sub")),
    "iter_children": lambda b: _keys(b.iter_children("a/sub")),
    "get_folder_info": lambda b: b.get_folder_info("a/sub").file_count,
    "Store.get_folder_info": lambda b: Store(backend=b).get_folder_info("a/sub").file_count,
    "Store.get_folder_info-max_depth": lambda b: Store(backend=b).get_folder_info("a/sub", max_depth=5).file_count,
}

# The one cell of this table the walks cannot reach. ``Store.get_folder_info``
# with a ``max_depth`` asks ``is_folder`` before it walks, and BE-021 forbids
# that predicate from raising, so no walk-side fix makes it answer a denial;
# today it leaks the bare ``PermissionError`` on 3.11 to 3.13 and answers
# ``NotFound`` on 3.14. Strict, so the day it raises ``PermissionDenied`` this
# cell fails and the mark has to go.
_START_DENIAL_DIVERGES = pytest.mark.xfail(
    strict=True,
    reason="BUG-313: Store's max_depth branch classifies the start through is_folder",
)


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(e, id=e, marks=_START_DENIAL_DIVERGES if e == "Store.get_folder_info-max_depth" else ())
        for e in _ON_SUB
    ],
)
def test_a_folder_whose_parent_cannot_be_traversed_raises_rather_than_reading_as_absent(
    tmp_path: Path, entry: str
) -> None:
    """The walk's own starting folder is classified by a ``stat`` that may be refused too.

    A missing folder lists as nothing (BE-014) and has no aggregate
    (``NotFound``, BE-017), so a starting folder the OS refuses to ``stat`` must
    not be taken for a missing one.
    """
    backend = _tree(tmp_path)
    with _deny_child_stat(tmp_path / "a"), pytest.raises(PermissionDenied) as info:
        _ON_SUB[entry](backend)
    assert type(info.value) is PermissionDenied
    assert info.value.path == "a/sub"
    assert info.value.backend == "local"
    assert info.value.__cause__ is None


# Every entry point that reads ``a/f.txt``'s size or type, with what it answers
# when that file is still there for its first ``stat`` and gone after it.
_WITH_F_GONE_AFTER_FIRST_STAT: dict[str, object] = {
    "list_files": {"a/f.txt"},
    "list_files-recursive": {"a/f.txt", "a/sub/g.txt"},
    "list_files-recursive-max_depth": {"a/f.txt", "a/sub/g.txt"},
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
    "get_folder_info": 2,
    "Store.get_folder_info": 2,
    "Store.get_folder_info-max_depth": 2,
}


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_WITH_F_GONE_AFTER_FIRST_STAT))
def test_a_file_removed_after_it_was_classified_does_not_leak(tmp_path: Path, entry: str) -> None:
    """Each child is classified and measured by one ``stat``, so no later one can find it gone.

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


@pytest.mark.spec("BE-021")
def test_a_depth_bound_that_stops_above_the_denied_folder_never_opens_it(tmp_path: Path) -> None:
    """Pruning happens before the walk descends, so the denial is never met."""
    backend = _tree(tmp_path)
    with _deny(tmp_path / "a" / "sub", _denied()):
        listed = {str(fi.path) for fi in backend.list_files("a", recursive=True, max_depth=0)}
    assert listed == {"a/f.txt"}


# What each recursive walk answers for ``a`` when ``a/sub`` is gone by the time
# the walk opens it: the readable part, since an absent subfolder holds nothing.
_WITH_SUB_GONE: dict[str, object] = {
    "list_files-recursive": {"a/f.txt"},
    "list_files-recursive-max_depth": {"a/f.txt"},
    "get_folder_info": 1,
    "Store.get_folder_info": 1,
    "Store.get_folder_info-max_depth": 1,
}


# The clause each entry point's absence answer is traced to. Every one that
# reaches ``list_files`` is BE-014's; the backend aggregate is BE-017's.
_ABSENCE_CLAUSE = {
    "list_files": "BE-014",
    "list_files-recursive": "BE-014",
    "list_files-recursive-max_depth": "BE-014",
    "list_folders": "BE-015",
    "iter_children": "BE-026",
    "get_folder_info": "BE-017",
    "Store.get_folder_info": "BE-017",
    "Store.get_folder_info-max_depth": "BE-014",
}


def _traced(entries: Iterable[str]) -> list[Any]:
    return [pytest.param(e, id=e, marks=pytest.mark.spec(_ABSENCE_CLAUSE[e])) for e in entries]


@pytest.mark.parametrize("entry", _traced(_WITH_SUB_GONE))
def test_a_subfolder_vanishing_mid_walk_is_still_an_absence(tmp_path: Path, entry: str) -> None:
    """Only a denial raises: a subfolder gone by the time the walk opens it holds nothing.

    The control that keeps the fix narrow. There are two error-hook sites,
    ``list_files``' walk and ``get_folder_info``'s, and five entry points reach
    them by different routes, so each route is held. A walk that started before a
    subfolder was removed meets a missing path, which lists as nothing (BE-014)
    and holds no files to aggregate (BE-017); turning every ``OSError`` into a
    raise would make it an error.
    """
    backend = _tree(tmp_path)
    gone = FileNotFoundError(errno.ENOENT, "No such file or directory")
    with _deny(tmp_path / "a" / "sub", gone):
        assert _ENTRY_POINTS[entry](backend) == _WITH_SUB_GONE[entry]


# What each entry point answers for ``a`` when ``a/f.txt`` is listed by the scan
# but already gone when its ``stat`` runs: everything but that file.
_WITH_F_GONE_BEFORE_STAT: dict[str, object] = {
    "list_files": set(),
    "list_files-recursive": {"a/sub/g.txt"},
    "list_files-recursive-max_depth": {"a/sub/g.txt"},
    "list_folders": {"a/sub"},
    "iter_children": {"a/sub"},
    "get_folder_info": 1,
    "Store.get_folder_info": 1,
    "Store.get_folder_info-max_depth": 1,
}


@pytest.mark.parametrize("entry", _traced(_WITH_F_GONE_BEFORE_STAT))
def test_an_entry_gone_before_its_stat_is_skipped(tmp_path: Path, entry: str) -> None:
    """An entry the scan listed but its ``stat`` no longer finds drops out of the answer.

    Each walk classifies an entry by its ``stat``, and a ``None`` from that
    ``stat`` has to mean "skip it", not "classify it": every entry point
    takes that branch here, ``iter_children``'s included.
    """
    backend = _tree(tmp_path)
    target = _norm((tmp_path / "a" / "f.txt").resolve())

    def stat(p: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if _norm(p) == target:
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", os.fspath(p))
        return _REAL_STAT(p, *args, **kwargs)

    with mock.patch.object(os, "stat", stat):
        assert _ENTRY_POINTS[entry](backend) == _WITH_F_GONE_BEFORE_STAT[entry]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        pytest.param(
            "list_files-recursive", {"a/f.txt", "a/sub/g.txt"}, id="list_files", marks=pytest.mark.spec("BE-014")
        ),
        pytest.param("get_folder_info", 2, id="get_folder_info", marks=pytest.mark.spec("BE-017")),
    ],
)
def test_a_file_removed_between_scan_and_stat_is_not_counted(tmp_path: Path, entry: str, expected: object) -> None:
    """Each recursive walk skips a name it was handed that is no longer there.

    ``os.walk`` reports names from a scan that is already stale by the time the
    caller stats them. A file removed in that window must drop out of the
    answer, not surface as a raw ``FileNotFoundError`` from its ``stat``. Driven
    by handing the walk a name that is not on disk, which is that window frozen.
    The window after the ``stat`` is pinned by
    ``test_a_file_removed_after_it_was_classified_does_not_leak``, and the
    single-level scans' version of this one by
    ``test_an_entry_gone_before_its_stat_is_skipped``.
    """
    backend = _tree(tmp_path)
    real_walk = os.walk

    def walk_with_a_ghost(top: object, **kwargs: Any) -> Iterator[tuple[str, list[str], list[str]]]:
        for dirpath, dirnames, filenames in real_walk(top, **kwargs):  # type: ignore[call-overload]
            yield dirpath, dirnames, [*filenames, "ghost.txt"]

    with mock.patch.object(os, "walk", walk_with_a_ghost):
        assert _ENTRY_POINTS[entry](backend) == expected


@pytest.mark.spec("BE-014")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
)
@pytest.mark.parametrize("max_depth", [None, 5], ids=["unbounded", "max_depth"])
def test_a_broken_symlink_is_not_listed_as_a_file(tmp_path: Path, max_depth: int | None) -> None:
    """Both recursive branches skip a dangling link rather than failing to stat it."""
    backend = _tree(tmp_path)
    (tmp_path / "a" / "dangling.txt").symlink_to(tmp_path / "nowhere.txt")
    listed = {str(fi.path) for fi in backend.list_files("a", recursive=True, max_depth=max_depth)}
    assert listed == {"a/f.txt", "a/sub/g.txt"}


_RECURSIVE = [name for name, answer in _WITH_SUB_DENIED.items() if answer is None]


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows denies through ACLs")
@pytest.mark.skipif(getattr(os, "geteuid", lambda: -1)() == 0, reason="root ignores permission bits")
@pytest.mark.parametrize("entry", _RECURSIVE)
@pytest.mark.parametrize(
    "mode",
    [pytest.param(0, id="unlistable"), pytest.param(0o444, id="listable-not-traversable")],
)
def test_a_really_unreadable_subfolder_raises_permission_denied(tmp_path: Path, entry: str, mode: int) -> None:
    """The recursive walks against a real ``chmod`` rather than an injection.

    ``0o444`` is the shape ``Path.is_file`` used to hide on 3.14: the folder
    lists, and every entry's ``stat`` fails.
    """
    backend = _tree(tmp_path)
    sub = tmp_path / "a" / "sub"
    sub.chmod(mode)
    try:
        with pytest.raises(PermissionDenied) as info:
            _ENTRY_POINTS[entry](backend)
    finally:
        sub.chmod(0o755)
    _assert_mapped(info)


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs; POSIX is the chmod cell above")
@pytest.mark.parametrize("entry", _RECURSIVE)
def test_a_subfolder_denied_by_acl_raises_permission_denied(tmp_path: Path, entry: str) -> None:
    """The recursive walks against a real ACL denial of "list folder" on Windows.

    The injection cells patch ``os.scandir``; this one shows the same answer
    when it is the OS refusing, through ``icacls``' deny-ReadData right.
    """
    backend = _tree(tmp_path)
    sub = tmp_path / "a" / "sub"
    user = getpass.getuser()
    denied = subprocess.run(["icacls", str(sub), "/deny", f"{user}:(RD)"], capture_output=True, check=False)
    if denied.returncode != 0:
        pytest.skip("icacls could not deny list access on this runner")
    try:
        with pytest.raises(PermissionDenied) as info:
            _ENTRY_POINTS[entry](backend)
    finally:
        subprocess.run(["icacls", str(sub), "/remove:d", user], capture_output=True, check=False)
    _assert_mapped(info)
