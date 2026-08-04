"""Shared path-type helpers for flat-namespace backends.

Two contracts live here, both about the same blind spot: a flat namespace
stores keys, not nodes, so "this path is a directory" is never an answer
the store gives back — it has to be inferred from a prefix listing.

* **File-ancestor pre-check** — an opt-in *pre*-check on the write path,
  documented immediately below.
* **Wrong-type reclassification** — a mandatory *post*-check on the error
  path, documented at ``_wrong_type_if_folder``.

Hierarchical backends (Local, SFTP, Memory) detect a file-ancestor path on
``write`` / ``move`` / ``copy`` for free because their native APIs cannot
descend through a regular-file path component (``parent.mkdir`` raises
``NotADirectoryError``; ``sftp.mkdir`` raises ``ENOTDIR``). Flat-namespace
backends (S3, Azure non-HNS, SQLBlob) need an extra round trip per
slash-aligned ancestor to spot the case. The pre-check is offered behind
an opt-in client kwarg so callers that need the cross-backend
``InvalidPath`` promise can pay for it explicitly.

This module is the shared shape: every flat-NS backend constructs a
backend-specific ``head_one`` callable (``head_object`` on S3,
``get_blob_properties`` on Azure, ``SELECT 1`` on SQLBlob) and threads it
through the same walk. The walk skips on no-slash paths, so the cost is
only paid for nested-path writes.

Two contracts the call sites rely on:

* **Path normalisation.** The walk operates on slash-aligned ancestors of
  the normalised key, so the helper strips leading slashes before
  splitting. A caller that bypasses ``Store``'s canonicalisation and
  passes ``"//a/b/file"`` would otherwise see ``head_one`` invoked on
  empty / ``"/a"`` ancestor keys -- on S3 those produce a 404 (silently
  False under the fail-open semantics below) and the real file-ancestor
  on the normalised path goes undetected.
* **Fail-open ``head_one``.** Every backend's ``head_one`` closure
  swallows *environmental* probe failures and returns ``False`` ("treat
  unknown state as not-a-file"). Each backend's closure narrows the
  swallow to its own error shapes: S3 catches
  ``(ClientError, BotoCoreError, OSError)``, Azure catches
  ``(AzureError, OSError)`` (after the dedicated ``ResourceNotFoundError``
  branch), SQLBlob catches ``(sqlalchemy.exc.SQLAlchemyError, OSError)``.
  Programmer errors (``TypeError``, ``AttributeError``, etc.) are *not*
  swallowed — they signal an integration bug and surface as the bug
  they are. A transient HEAD failure (503, throttling, network blip)
  therefore lets the write proceed; the pre-check is best-effort, not a
  hard barrier. The opt-in is default-off, so the choice is deliberate:
  users who turned the gate on get the protection on a clean network
  path and accept that control-plane errors don't halt the data path.
  Tightening the closures to fail-closed flips this contract -- expect
  that to be a spec-amendment-class change rather than a local bug fix.

  Two related properties the opt-in audience should be aware of:

  - *Start-of-call check, not atomic guarantee.* The walk runs once at
    the start of each ``write`` / ``move`` / ``copy`` call. A concurrent
    writer that creates a file at one of the walked ancestor keys
    *between* the walk and the data-plane operation slips past the
    gate; the orphan-key shape the gate exists to prevent then lands
    anyway. Callers that need an atomic "no ancestor was a file"
    guarantee need a backend-level lock or a CAS layer above the gate.
  - *Silent degradation under partial failure.* A walk that does five
    successful HEADs and one swallowed transient failure is
    indistinguishable from a clean walk by the caller. The opt-in user
    has no signal that the gate ran in a degraded mode. Logging-at-WARN
    on the swallow would surface this; we leave it out of this module
    so the helper has no logger dependency, and document the
    consequence here.
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
    backend calls.

    The cost is O(N) backend round trips for a depth-N path with no
    file-ancestor hit. The opt-in kwarg on each flat-NS backend gates
    every call site, so backends with the default-off setting pay
    nothing.
    """
    # Normalise leading slashes for the walk but keep the original
    # caller-supplied form for the raised ``InvalidPath`` so error
    # handlers that grep for the input path still match. See the
    # module docstring -- "Path normalisation".
    original_path = path
    normalised = path.lstrip("/")
    if "/" not in normalised:
        return
    parts = normalised.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if head_one(ancestor):
            raise InvalidPath(
                f"Cannot write under file ancestor: {ancestor!r} is a regular file (path={original_path!r})",
                path=original_path,
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
    # Normalise leading slashes for the walk but raise with the
    # original caller-supplied form. See ``_check_no_file_ancestor``.
    original_path = path
    normalised = path.lstrip("/")
    if "/" not in normalised:
        return
    parts = normalised.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if await head_one(ancestor):
            raise InvalidPath(
                f"Cannot write under file ancestor: {ancestor!r} is a regular file (path={original_path!r})",
                path=original_path,
                backend=backend,
            )


def _folder_not_file(path: str, backend: str) -> InvalidPath:
    """Build the "wrong type: folder where a file was expected" error.

    Constructed rather than raised so a backend that discovers the type
    conflict some other way — s3fs hands back a synthetic directory entry
    instead of failing, Azure HNS reads it off ``hdi_isfolder`` — can raise
    the same error without paying for the prefix probe it does not need.
    """
    return InvalidPath(f"Path is a folder, not a file: {path!r}", path=path, backend=backend)


def _file_not_folder(path: str, backend: str) -> InvalidPath:
    """Build the "wrong type: file where a folder was expected" error."""
    return InvalidPath(f"Path is a file, not a folder: {path!r}", path=path, backend=backend)


def _wrong_type_if_folder(path: str, *, has_children: Callable[[str], bool], backend: str) -> None:
    """Raise ``InvalidPath`` when *path* names a virtual folder.

    Call this **only from an error path** — after a file-shaped operation
    (``read``, ``read_bytes``, ``delete``, ``get_file_info``, ``move``/``copy``
    source) has already failed to find an object at *path*. The type-mismatch
    rule outranks the existence rule, so a miss that is really a folder must
    surface as ``InvalidPath``, not ``NotFound``.

    ``has_children`` performs one prefix listing bounded to a single key and
    returns ``True`` iff any key lives under ``path + "/"``. The success path
    never reaches here, so a normal operation pays nothing; the extra listing
    is charged only to calls that were going to raise anyway.

    The root (``""``) is exempt: it is always a folder, and every caller that
    reaches here with an empty path has already rejected it for another
    reason.
    """
    if path and has_children(path):
        raise _folder_not_file(path, backend)


def _wrong_type_if_file(path: str, *, is_object: Callable[[str], bool], backend: str) -> None:
    """Raise ``InvalidPath`` when *path* names a file.

    Mirror of ``_wrong_type_if_folder`` for the folder-shaped operations
    (``delete_folder``, ``get_folder_info``): call it after the prefix listing
    came back empty, so the single ``is_object`` probe (one HEAD / one exact
    key lookup) is charged only to a call that was already failing.
    """
    if path and is_object(path):
        raise _file_not_folder(path, backend)


async def _awrong_type_if_folder(path: str, *, has_children: Callable[[str], Awaitable[bool]], backend: str) -> None:
    """Async sibling of ``_wrong_type_if_folder``; ``has_children`` is awaitable."""
    if path and await has_children(path):
        raise _folder_not_file(path, backend)


async def _awrong_type_if_file(path: str, *, is_object: Callable[[str], Awaitable[bool]], backend: str) -> None:
    """Async sibling of ``_wrong_type_if_file``; ``is_object`` is awaitable."""
    if path and await is_object(path):
        raise _file_not_folder(path, backend)


__all__ = [
    "_acheck_no_file_ancestor",
    "_awrong_type_if_file",
    "_awrong_type_if_folder",
    "_check_no_file_ancestor",
    "_file_not_folder",
    "_folder_not_file",
    "_wrong_type_if_file",
    "_wrong_type_if_folder",
]
