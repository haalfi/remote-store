"""Batch operations — convenience wrappers for bulk delete, copy, and exists.

All functions call Store methods one-by-one by default (sequential). Pass
``concurrent=True`` to use a ``ThreadPoolExecutor``
for parallel I/O — cloud backends benefit significantly from this.

!!! example

    ```python
    from remote_store.ext.batch import batch_delete, batch_copy, batch_exists

    result = batch_delete(store, ["a.txt", "b.txt"], missing_ok=True)
    result = batch_copy(store, [("a.txt", "copy.txt")], overwrite=True)
    exists_map = batch_exists(store, ["a.txt", "missing.txt"])

    # Parallel execution (cloud backends):
    result = batch_delete(store, keys, concurrent=True, max_workers=8)
    ```
"""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, TypeVar

from remote_store import CapabilityNotSupported, RemoteStoreError

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from remote_store._store import Store

T = TypeVar("T")

__all__ = ["BatchResult", "batch_copy", "batch_delete", "batch_exists"]


@dataclasses.dataclass(frozen=True)
class BatchResult:
    """Outcome of a batch operation.

    Attributes:
        succeeded: Paths that completed without error.
        failed: Mapping from path to the error that occurred.
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


# ---------------------------------------------------------------------------
# Generic batch executor
# ---------------------------------------------------------------------------


def _run_batch(
    items: Iterable[T],
    fn: Callable[[T], None],
    key: Callable[[T], str],
    *,
    stop_on_error: bool,
    concurrent: bool,
    max_workers: int | None,
    label: str,
) -> BatchResult:
    """Execute *fn* on each item, collecting successes and failures.

    Args:
        items: Work items to process.
        fn: Operation to call on each item.  Must raise
            ``RemoteStoreError`` on failure.
        key: Extract the path string from an item (for result tracking).
        stop_on_error: Stop on first error (sequential only).
        concurrent: Use a thread pool for parallel execution.
        max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).
        label: Operation name for log messages.
    """
    if concurrent:
        result = _run_batch_concurrent(items, fn, key, max_workers=max_workers)
    else:
        result = _run_batch_sequential(items, fn, key, stop_on_error=stop_on_error)
    log.info(
        "%s complete: %d succeeded, %d failed",
        label,
        len(result.succeeded),
        len(result.failed),
        extra={"op": label, "concurrent": concurrent},
    )
    return result


def _run_batch_sequential(
    items: Iterable[T],
    fn: Callable[[T], None],
    key: Callable[[T], str],
    *,
    stop_on_error: bool,
) -> BatchResult:
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    for item in items:
        try:
            fn(item)
        except CapabilityNotSupported:
            raise
        except RemoteStoreError as exc:
            failed[key(item)] = exc
            if stop_on_error:
                break
        else:
            succeeded.append(key(item))
    return BatchResult(succeeded=tuple(succeeded), failed=failed)


def _run_batch_concurrent(
    items: Iterable[T],
    fn: Callable[[T], None],
    key: Callable[[T], str],
    *,
    max_workers: int | None,
) -> BatchResult:
    # Materialise upfront — futures need random access by key.
    items_list = list(items)
    succeeded: list[str] = []
    failed: dict[str, RemoteStoreError] = {}
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_key = {executor.submit(fn, item): key(item) for item in items_list}
        for future in as_completed(future_to_key):
            k = future_to_key[future]
            try:
                future.result()
            except CapabilityNotSupported:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except RemoteStoreError as exc:
                failed[k] = exc
            else:
                succeeded.append(k)
    finally:
        executor.shutdown(wait=True)
    return BatchResult(succeeded=tuple(succeeded), failed=failed)


# ---------------------------------------------------------------------------
# Public batch functions
# ---------------------------------------------------------------------------


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

    Args:
        store: The Store to delete from.
        paths: File paths to delete.
        missing_ok: Forwarded to each ``store.delete()`` call.
        stop_on_error: Stop on first ``RemoteStoreError`` (sequential only).
        concurrent: Use a thread pool for parallel execution.
        max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).

    Returns:
        A ``BatchResult`` with succeeded/failed paths.

    Raises:
        ValueError: If both ``concurrent`` and ``stop_on_error`` are True.
    """
    if concurrent and stop_on_error:
        msg = "stop_on_error is not supported with concurrent=True"
        raise ValueError(msg)

    def _delete(path: str) -> None:
        store.delete(path, missing_ok=missing_ok)

    return _run_batch(
        paths,
        _delete,
        key=lambda p: p,
        stop_on_error=stop_on_error,
        concurrent=concurrent,
        max_workers=max_workers,
        label="batch_delete",
    )


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

    Args:
        store: The Store to copy within.
        pairs: ``(src, dst)`` tuples.
        overwrite: Forwarded to each ``store.copy()`` call.
        stop_on_error: Stop on first ``RemoteStoreError`` (sequential only).
        concurrent: Use a thread pool for parallel execution.
        max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).

    Returns:
        A ``BatchResult`` with succeeded/failed source paths.

    Raises:
        ValueError: If both ``concurrent`` and ``stop_on_error`` are True.
    """
    if concurrent and stop_on_error:
        msg = "stop_on_error is not supported with concurrent=True"
        raise ValueError(msg)

    def _copy(pair: tuple[str, str]) -> None:
        store.copy(pair[0], pair[1], overwrite=overwrite)

    return _run_batch(
        pairs,
        _copy,
        key=lambda pair: pair[0],
        stop_on_error=stop_on_error,
        concurrent=concurrent,
        max_workers=max_workers,
        label="batch_copy",
    )


def batch_exists(
    store: Store,
    paths: Iterable[str],
    *,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> dict[str, bool]:
    """Check existence of multiple paths.

    Unlike ``batch_delete()`` and ``batch_copy()``, this function does
    **not** catch errors — any exception from ``store.exists()`` propagates
    immediately.

    Args:
        store: The Store to query.
        paths: Paths to check.
        concurrent: Use a thread pool for parallel execution.
        max_workers: Max threads (forwarded to ``ThreadPoolExecutor``).

    Returns:
        Dict mapping each path to ``True``/``False``.
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
    # Materialise upfront — futures need random access by path.
    paths_list = list(paths)
    result: dict[str, bool] = {}
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_path = {executor.submit(store.exists, p): p for p in paths_list}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result[path] = future.result()
            except Exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
    finally:
        executor.shutdown(wait=True)
    return result
