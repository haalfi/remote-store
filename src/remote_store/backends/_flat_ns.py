"""Shared file-ancestor pre-check for flat-namespace backends (ID-211).

Hierarchical backends (Local, SFTP, Memory) detect a file-ancestor path on
``write`` / ``move`` / ``copy`` for free because their native APIs cannot
descend through a regular-file path component (``parent.mkdir`` raises
``NotADirectoryError``; ``sftp.mkdir`` raises ``ENOTDIR``). Flat-namespace
backends (S3, Azure non-HNS, SQLBlob) need an extra round trip per
slash-aligned ancestor to spot the case. ID-209 left this exempt; ID-211
ships the pre-check behind an opt-in client kwarg so callers that need the
cross-backend ``InvalidPath`` promise can pay for it explicitly.

This module is the shared shape: every flat-NS backend constructs a
backend-specific ``head_one`` callable (``head_object`` on S3,
``get_blob_properties`` on Azure, ``SELECT 1`` on SQLBlob) and threads it
through the same walk. The walk skips on no-slash paths -- the
user-nominated optimisation that collapses the cost to nested-path writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._errors import InvalidPath

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def _check_no_file_ancestor(
    path: str,
    *,
    head_one: Callable[[str], bool],
    backend: str,
) -> None:
    """Walk ``path`` and raise ``InvalidPath`` if a slash-aligned ancestor is a file.

    ``head_one`` returns ``True`` iff the given key exists as a regular
    file on the backend. The walk short circuits on the first file
    ancestor; a path with no slash returns immediately without any
    backend calls (the no-slash early exit described in ID-211).

    The cost is O(N) backend round trips for a depth-N path with no
    file-ancestor hit. The opt-in kwarg on each flat-NS backend gates
    every call site, so backends with the default-off setting pay
    nothing.
    """
    if "/" not in path:
        return
    parts = path.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if head_one(ancestor):
            raise InvalidPath(
                f"Cannot write under file ancestor: {ancestor!r} is a regular file (path={path!r})",
                path=path,
                backend=backend,
            )


async def _acheck_no_file_ancestor(
    path: str,
    *,
    head_one: Callable[[str], Awaitable[bool]],
    backend: str,
) -> None:
    """Async sibling of ``_check_no_file_ancestor``.

    Same shape; ``head_one`` is an awaitable. Use from ``AsyncBackend``
    write/move/copy paths on flat-NS async backends.
    """
    if "/" not in path:
        return
    parts = path.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if await head_one(ancestor):
            raise InvalidPath(
                f"Cannot write under file ancestor: {ancestor!r} is a regular file (path={path!r})",
                path=path,
                backend=backend,
            )


__all__ = ["_acheck_no_file_ancestor", "_check_no_file_ancestor"]
