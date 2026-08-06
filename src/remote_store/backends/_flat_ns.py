"""Shared path-type helpers for flat-namespace backends.

Three contracts live here. The first two are about the same blind spot: a
flat namespace stores keys, not nodes, so "this path is a directory" is
never an answer the store gives back — it has to be inferred from a prefix
listing.

* **File-ancestor pre-check** — an opt-in *pre*-check on the write path,
  documented immediately below.
* **Wrong-type reclassification** — a mandatory *post*-check on the error
  path, documented at ``_wrong_type_if_folder``.
* **Absent container reads as absent path** — the folder-existence probe's
  answer when the bucket / container itself is gone, documented at
  ``_children_or_absent_container``.

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
from remote_store._path import is_root

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


def _reject_root_as_file(path: str, backend: str) -> None:
    """Raise ``InvalidPath`` when a file-shaped operation is handed the store root.

    The root is a folder, so ``read``, ``read_bytes``, ``read_seekable``,
    ``get_file_info``, ``delete`` and the ``move``/``copy`` source all owe it
    the same answer they owe any other folder path — and owe it under both
    spellings.

    This is a **pre**-check, unlike the probes below, and it is the one case
    where that costs nothing: root-ness is decidable from the string, with no
    round trip. Running it first is also what keeps the root out of the SDK,
    where a zero-length object key is rejected at parameter validation and
    surfaces as a transport-shaped error — a retryable classification for a
    permanently wrong request.

    Not a mutation guard: deleting or writing *the root itself* is a
    ``Store``-layer concern, and this says nothing about ``delete_folder`` or
    ``get_folder_info``, which are folder-shaped and legitimately accept it.
    """
    if is_root(path):
        raise _folder_not_file(path, backend)


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

    Because it is error-path-only, ``has_children`` MAY fail open — answer
    ``False`` when the listing itself failed — since the operation's own error
    is still there to stand. Fail-open belongs to *this* call site, not to the
    probe: a backend that also uses the same listing as its plain existence
    check must not swallow failures there, where there is no prior error to
    preserve and a swallowed denial would be reported as a missing path.

    Both spellings of the root are exempt, and by the same predicate: the
    root is a folder whether or not it has children, so a probe answer about
    it is meaningless. Callers reject it up front via ``_reject_root_as_file``
    instead. Testing ``if path`` here rather than ``is_root`` is what let the
    dot spelling reach the probe, where on a flat namespace it answered for
    the whole bucket.
    """
    if not is_root(path) and has_children(path):
        raise _folder_not_file(path, backend)


def _wrong_type_if_file(path: str, *, is_object: Callable[[str], bool], backend: str) -> None:
    """Raise ``InvalidPath`` when *path* names a file.

    Mirror of ``_wrong_type_if_folder`` for the folder-shaped operations
    (``delete_folder``, ``get_folder_info``): call it after the prefix listing
    came back empty, so the single ``is_object`` probe (one HEAD / one exact
    key lookup) is charged only to a call that was already failing.
    """
    if not is_root(path) and is_object(path):
        raise _file_not_folder(path, backend)


def _children_or_absent_container(
    path: str,
    *,
    has_children: Callable[[str], bool],
    absent_container: Callable[[BaseException], bool],
) -> bool:
    """Run the folder-existence probe, reading an absent container as "no children".

    A tolerant delete treats an absent *container* — the bucket, the Azure
    container — exactly as it treats an absent path, because a container that
    does not exist holds no path either. Deciding that at the contract is what
    stops the wire shape from deciding it per backend:

    * ``HeadObject`` answers a bodyless 404, so the file-shaped probe cannot
      distinguish a missing bucket from a missing key even in principle, and
      ``delete`` tolerates both without being asked to.
    * ``ListObjectsV2`` answers an absent *prefix* with ``200 KeyCount=0``, so
      the only 404 it can raise is the container's, and it arrives with a body
      that names it. Left alone, ``delete_folder`` raised where its sibling
      returned — against the same absent bucket.

    This helper is the folder-shaped half catching up, and it costs nothing: the
    404 is already in hand. Making the *pair* strict instead would have cost
    ``delete`` a second ``HeadBucket`` on every miss, against a spec that
    budgets one probe per miss — and it would have split flat-namespace
    backends from the hierarchical ones, where an absent store root is already
    just an absent path (``LocalBackend.delete_folder`` returns silently under
    ``missing_ok``).

    Returning ``False`` is not the same as tolerating the call: the caller still
    runs its wrong-type probe and still raises ``NotFound`` when ``missing_ok``
    is ``False``. The absent container is reported as a missing path, which is
    what it is.

    ``absent_container`` narrows the catch to the one wire shape that means
    "the container is not there" — ``FileNotFoundError`` from ``s3fs``, a
    404-coded ``ClientError`` from botocore, ``ResourceNotFoundError`` from the
    Azure SDK. Everything else propagates, so a denial stays ``PermissionDenied``
    and a 503 stays ``BackendUnavailable``. Widening it to swallow those would
    reintroduce, in a new place, the defect this backend family has already
    shipped once: a probe that invents an answer instead of reporting that it
    could not get one.
    """
    # Contract: 003-backend-adapter-contract BE-012 / BE-013, and the shared
    # rule under BE-021 ("An absent container reads as an absent path").
    # The invented-answer regression this narrows against was BUG-242.
    try:
        return has_children(path)
    except Exception as exc:  # noqa: BLE001 -- re-raised unless it is the absent container
        if absent_container(exc):
            return False
        raise


async def _achildren_or_absent_container(
    path: str,
    *,
    has_children: Callable[[str], Awaitable[bool]],
    absent_container: Callable[[BaseException], bool],
) -> bool:
    """Async sibling of ``_children_or_absent_container``; ``has_children`` is awaitable."""
    try:
        return await has_children(path)
    except Exception as exc:  # noqa: BLE001 -- re-raised unless it is the absent container
        if absent_container(exc):
            return False
        raise


async def _awrong_type_if_folder(path: str, *, has_children: Callable[[str], Awaitable[bool]], backend: str) -> None:
    """Async sibling of ``_wrong_type_if_folder``; ``has_children`` is awaitable."""
    if not is_root(path) and await has_children(path):
        raise _folder_not_file(path, backend)


async def _awrong_type_if_file(path: str, *, is_object: Callable[[str], Awaitable[bool]], backend: str) -> None:
    """Async sibling of ``_wrong_type_if_file``; ``is_object`` is awaitable."""
    if not is_root(path) and await is_object(path):
        raise _file_not_folder(path, backend)


__all__ = [
    "_achildren_or_absent_container",
    "_acheck_no_file_ancestor",
    "_awrong_type_if_file",
    "_awrong_type_if_folder",
    "_check_no_file_ancestor",
    "_children_or_absent_container",
    "_file_not_folder",
    "_folder_not_file",
    "_reject_root_as_file",
    "_wrong_type_if_file",
    "_wrong_type_if_folder",
]
