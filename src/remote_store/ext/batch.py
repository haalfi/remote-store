"""Batch operations — convenience wrappers for bulk delete, copy, and exists.

All functions call Store methods one-by-one (sequential, no parallelism) and
collect errors into a :class:`BatchResult` instead of failing on first error.

Usage::

    from remote_store.ext.batch import batch_delete, batch_copy, batch_exists

    result = batch_delete(store, ["a.txt", "b.txt"], missing_ok=True)
    result = batch_copy(store, [("a.txt", "copy.txt")], overwrite=True)
    exists_map = batch_exists(store, ["a.txt", "missing.txt"])
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING

from remote_store._errors import CapabilityNotSupported, RemoteStoreError

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from remote_store._store import Store

__all__ = ["BatchResult", "batch_copy", "batch_delete", "batch_exists"]


@dataclasses.dataclass(frozen=True)
class BatchResult:
    """Outcome of a batch operation.

    :param succeeded: Paths that completed without error.
    :param failed: Mapping from path to the error that occurred.
    """

    succeeded: tuple[str, ...]
    failed: dict[str, RemoteStoreError]

    @property
    def all_succeeded(self) -> bool:
        """``True`` when every path succeeded."""
        return len(self.failed) == 0

    @property
    def total(self) -> int:
        """Total number of paths processed (succeeded + failed)."""
        return len(self.succeeded) + len(self.failed)


def batch_delete(
    store: Store,
    paths: Iterable[str],
    *,
    missing_ok: bool = False,
    stop_on_error: bool = False,
) -> BatchResult:
    """Delete multiple files, collecting errors.

    :param store: The Store to delete from.
    :param paths: File paths to delete.
    :param missing_ok: Forwarded to each ``store.delete()`` call.
    :param stop_on_error: Stop on first ``RemoteStoreError``.
    :returns: A :class:`BatchResult` with succeeded/failed paths.
    """
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    for path in paths:
        try:
            store.delete(path, missing_ok=missing_ok)
        except CapabilityNotSupported:
            raise
        except RemoteStoreError as exc:
            failed[path] = exc
            if stop_on_error:
                break
        else:
            succeeded.append(path)
    result = BatchResult(succeeded=tuple(succeeded), failed=failed)
    log.info(
        "batch_delete complete: %d succeeded, %d failed",
        len(result.succeeded),
        len(result.failed),
        extra={"op": "batch_delete"},
    )
    return result


def batch_copy(
    store: Store,
    pairs: Iterable[tuple[str, str]],
    *,
    overwrite: bool = False,
    stop_on_error: bool = False,
) -> BatchResult:
    """Copy multiple files, collecting errors.

    :param store: The Store to copy within.
    :param pairs: ``(src, dst)`` tuples.
    :param overwrite: Forwarded to each ``store.copy()`` call.
    :param stop_on_error: Stop on first ``RemoteStoreError``.
    :returns: A :class:`BatchResult` with succeeded/failed source paths.
    """
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    for src, dst in pairs:
        try:
            store.copy(src, dst, overwrite=overwrite)
        except CapabilityNotSupported:
            raise
        except RemoteStoreError as exc:
            failed[src] = exc
            if stop_on_error:
                break
        else:
            succeeded.append(src)
    result = BatchResult(succeeded=tuple(succeeded), failed=failed)
    log.info(
        "batch_copy complete: %d succeeded, %d failed",
        len(result.succeeded),
        len(result.failed),
        extra={"op": "batch_copy"},
    )
    return result


def batch_exists(store: Store, paths: Iterable[str]) -> dict[str, bool]:
    """Check existence of multiple paths.

    Unlike :func:`batch_delete` and :func:`batch_copy`, this function does
    **not** catch errors — any exception from ``store.exists()`` propagates
    immediately.

    :param store: The Store to query.
    :param paths: Paths to check.
    :returns: Dict mapping each path to ``True``/``False``.
    """
    return {path: store.exists(path) for path in paths}
