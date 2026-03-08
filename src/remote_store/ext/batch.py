"""Batch operations — convenience wrappers for bulk delete, copy, and exists.

All functions call Store methods one-by-one by default (sequential). Pass
``concurrent=True`` to use a :class:`~concurrent.futures.ThreadPoolExecutor`
for parallel I/O — cloud backends benefit significantly from this.

Usage::

    from remote_store.ext.batch import batch_delete, batch_copy, batch_exists

    result = batch_delete(store, ["a.txt", "b.txt"], missing_ok=True)
    result = batch_copy(store, [("a.txt", "copy.txt")], overwrite=True)
    exists_map = batch_exists(store, ["a.txt", "missing.txt"])

    # Parallel execution (cloud backends):
    result = batch_delete(store, keys, concurrent=True, max_workers=8)
"""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    concurrent: bool = False,
    max_workers: int | None = None,
) -> BatchResult:
    """Delete multiple files, collecting errors.

    :param store: The Store to delete from.
    :param paths: File paths to delete.
    :param missing_ok: Forwarded to each ``store.delete()`` call.
    :param stop_on_error: Stop on first ``RemoteStoreError`` (sequential only).
    :param concurrent: Use a thread pool for parallel execution.
    :param max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).
    :returns: A :class:`BatchResult` with succeeded/failed paths.
    :raises ValueError: If both ``concurrent`` and ``stop_on_error`` are True.
    """
    if concurrent and stop_on_error:
        msg = "stop_on_error is not supported with concurrent=True"
        raise ValueError(msg)

    if concurrent:
        return _batch_delete_concurrent(store, paths, missing_ok, max_workers)

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


def _batch_delete_concurrent(
    store: Store,
    paths: Iterable[str],
    missing_ok: bool,
    max_workers: int | None,
) -> BatchResult:
    """Concurrent implementation of batch_delete."""
    paths_list = list(paths)
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {executor.submit(store.delete, p, missing_ok=missing_ok): p for p in paths_list}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                future.result()
            except CapabilityNotSupported:
                raise
            except RemoteStoreError as exc:
                failed[path] = exc
            else:
                succeeded.append(path)
    result = BatchResult(succeeded=tuple(succeeded), failed=failed)
    log.info(
        "batch_delete complete: %d succeeded, %d failed",
        len(result.succeeded),
        len(result.failed),
        extra={"op": "batch_delete", "concurrent": True},
    )
    return result


def batch_copy(
    store: Store,
    pairs: Iterable[tuple[str, str]],
    *,
    overwrite: bool = False,
    stop_on_error: bool = False,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> BatchResult:
    """Copy multiple files, collecting errors.

    :param store: The Store to copy within.
    :param pairs: ``(src, dst)`` tuples.
    :param overwrite: Forwarded to each ``store.copy()`` call.
    :param stop_on_error: Stop on first ``RemoteStoreError`` (sequential only).
    :param concurrent: Use a thread pool for parallel execution.
    :param max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).
    :returns: A :class:`BatchResult` with succeeded/failed source paths.
    :raises ValueError: If both ``concurrent`` and ``stop_on_error`` are True.
    """
    if concurrent and stop_on_error:
        msg = "stop_on_error is not supported with concurrent=True"
        raise ValueError(msg)

    if concurrent:
        return _batch_copy_concurrent(store, pairs, overwrite, max_workers)

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


def _batch_copy_concurrent(
    store: Store,
    pairs: Iterable[tuple[str, str]],
    overwrite: bool,
    max_workers: int | None,
) -> BatchResult:
    """Concurrent implementation of batch_copy."""
    pairs_list = list(pairs)
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_src = {executor.submit(store.copy, src, dst, overwrite=overwrite): src for src, dst in pairs_list}
        for future in as_completed(future_to_src):
            src = future_to_src[future]
            try:
                future.result()
            except CapabilityNotSupported:
                raise
            except RemoteStoreError as exc:
                failed[src] = exc
            else:
                succeeded.append(src)
    result = BatchResult(succeeded=tuple(succeeded), failed=failed)
    log.info(
        "batch_copy complete: %d succeeded, %d failed",
        len(result.succeeded),
        len(result.failed),
        extra={"op": "batch_copy", "concurrent": True},
    )
    return result


def batch_exists(
    store: Store,
    paths: Iterable[str],
    *,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> dict[str, bool]:
    """Check existence of multiple paths.

    Unlike :func:`batch_delete` and :func:`batch_copy`, this function does
    **not** catch errors — any exception from ``store.exists()`` propagates
    immediately.

    :param store: The Store to query.
    :param paths: Paths to check.
    :param concurrent: Use a thread pool for parallel execution.
    :param max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).
    :returns: Dict mapping each path to ``True``/``False``.
    """
    if concurrent:
        return _batch_exists_concurrent(store, paths, max_workers)
    return {path: store.exists(path) for path in paths}


def _batch_exists_concurrent(
    store: Store,
    paths: Iterable[str],
    max_workers: int | None,
) -> dict[str, bool]:
    """Concurrent implementation of batch_exists."""
    paths_list = list(paths)
    result: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {executor.submit(store.exists, p): p for p in paths_list}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            result[path] = future.result()
    return result
