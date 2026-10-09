"""What ``LocalBackend``'s listings answer when the OS refuses to list a folder.

BE-021's canonical table maps an operation the OS denies to ``PermissionDenied``,
and its invariant says no native exception leaks. The listings met neither, in
two different ways:

- the single-level scans (``list_files``, ``list_folders``, ``iter_children``)
  let the raw ``PermissionError`` escape, carrying no ``path`` or ``backend``;
- both recursive ``list_files`` branches dropped a denied subtree **silently** —
  ``os.walk``'s default ``onerror=None`` and ``Path.rglob``'s selector each
  swallow the error — so a partly unreadable tree came back as a short listing
  indistinguishable from a complete one, and a denied top folder as empty.

The cells enumerate entry point x denied site rather than sampling them, because
the two shapes above live in different branches of one method and a fix to one
says nothing about the other. The denial is injected at ``os.scandir`` and
``os.listdir``, the two calls every branch lists through on 3.11 to 3.14, so the
cells do not depend on which one a given interpreter's ``pathlib`` uses. One
POSIX cell repeats the recursive case against a real ``chmod``.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from remote_store._errors import PermissionDenied
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
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


_ENTRY_POINTS: dict[str, Callable[[LocalBackend], Iterator[object]]] = {
    "list_files": lambda b: b.list_files("a"),
    "list_files-recursive": lambda b: b.list_files("a", recursive=True),
    "list_files-recursive-max_depth": lambda b: b.list_files("a", recursive=True, max_depth=5),
    "list_folders": lambda b: b.list_folders("a"),
    "iter_children": lambda b: b.iter_children("a"),
}

# What each entry point lists from ``a`` when only ``a/sub`` is denied. The
# single-level scans never open ``a/sub``, so the denial must not reach them;
# ``None`` marks the recursive walks, which do open it and must raise.
_WITH_SUB_DENIED: dict[str, set[str] | None] = {
    "list_files": {"a/f.txt"},
    "list_files-recursive": None,
    "list_files-recursive-max_depth": None,
    "list_folders": {"a/sub"},
    "iter_children": {"a/f.txt", "a/sub"},
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
        list(_ENTRY_POINTS[entry](backend))
    _assert_mapped(info)


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_a_denied_subfolder_raises_only_where_the_listing_descends(tmp_path: Path, entry: str) -> None:
    """A recursive walk raises rather than returning the readable part of the tree."""
    backend = _tree(tmp_path)
    expected = _WITH_SUB_DENIED[entry]
    with _deny(tmp_path / "a" / "sub", _denied()):
        if expected is None:
            with pytest.raises(PermissionDenied) as info:
                list(_ENTRY_POINTS[entry](backend))
            _assert_mapped(info)
        else:
            listed = {str(item.path) for item in _ENTRY_POINTS[entry](backend)}  # type: ignore[attr-defined]
            assert listed == expected


@pytest.mark.spec("BE-021")
def test_a_depth_bound_that_stops_above_the_denied_folder_never_opens_it(tmp_path: Path) -> None:
    """Pruning happens before the walk descends, so the denial is never met."""
    backend = _tree(tmp_path)
    with _deny(tmp_path / "a" / "sub", _denied()):
        listed = {str(fi.path) for fi in backend.list_files("a", recursive=True, max_depth=0)}
    assert listed == {"a/f.txt"}


@pytest.mark.spec("BE-014")
@pytest.mark.parametrize("max_depth", [None, 5], ids=["unbounded", "max_depth"])
def test_a_subfolder_vanishing_mid_walk_is_still_an_absence(tmp_path: Path, max_depth: int | None) -> None:
    """Only a denial raises: a subfolder gone by the time the walk opens it lists as nothing.

    The control that keeps the fix narrow. A missing path yields nothing under
    BE-014, and a walk that started before a subfolder was removed meets exactly
    that; turning every ``OSError`` into a raise would make it an error.
    """
    backend = _tree(tmp_path)
    gone = FileNotFoundError(errno.ENOENT, "No such file or directory")
    with _deny(tmp_path / "a" / "sub", gone):
        listed = {str(fi.path) for fi in backend.list_files("a", recursive=True, max_depth=max_depth)}
    assert listed == {"a/f.txt"}


@pytest.mark.spec("BE-014")
def test_a_file_removed_between_scan_and_stat_is_not_listed(tmp_path: Path) -> None:
    """The recursive walk re-checks each name it was handed before statting it.

    ``os.walk`` reports names from a scan that is already stale by the time the
    caller stats them. A file removed in that window must drop out of the
    listing, not surface as a raw ``FileNotFoundError`` from the stat. Driven by
    handing the walk a name that is not on disk, which is that window frozen.
    """
    backend = _tree(tmp_path)
    real_walk = os.walk

    def walk_with_a_ghost(top: object, **kwargs: Any) -> Iterator[tuple[str, list[str], list[str]]]:
        for dirpath, dirnames, filenames in real_walk(top, **kwargs):  # type: ignore[call-overload]
            yield dirpath, dirnames, [*filenames, "ghost.txt"]

    with mock.patch.object(os, "walk", walk_with_a_ghost):
        listed = {str(fi.path) for fi in backend.list_files("a", recursive=True)}
    assert listed == {"a/f.txt", "a/sub/g.txt"}


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


@pytest.mark.spec("BE-021")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows denies through ACLs")
@pytest.mark.skipif(getattr(os, "geteuid", lambda: -1)() == 0, reason="root ignores permission bits")
@pytest.mark.parametrize("max_depth", [None, 5], ids=["unbounded", "max_depth"])
def test_a_really_unreadable_subfolder_raises_permission_denied(tmp_path: Path, max_depth: int | None) -> None:
    """The recursive case against the OS rather than an injection."""
    backend = _tree(tmp_path)
    sub = tmp_path / "a" / "sub"
    sub.chmod(0)
    try:
        with pytest.raises(PermissionDenied) as info:
            list(backend.list_files("a", recursive=True, max_depth=max_depth))
    finally:
        sub.chmod(0o755)
    _assert_mapped(info)
