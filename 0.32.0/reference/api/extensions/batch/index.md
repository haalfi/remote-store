# ext.batch

## batch

Batch operations — convenience wrappers for bulk delete, copy, and exists.

All functions call Store methods one-by-one by default (sequential). Pass `concurrent=True` to use a `ThreadPoolExecutor` for parallel I/O — cloud backends benefit significantly from this.

Example

```
from remote_store.ext.batch import batch_delete, batch_copy, batch_exists

result = batch_delete(store, ["a.txt", "b.txt"], missing_ok=True)
result = batch_copy(store, [("a.txt", "copy.txt")], overwrite=True)
exists_map = batch_exists(store, ["a.txt", "missing.txt"])

# Parallel execution (cloud backends):
result = batch_delete(store, keys, concurrent=True, max_workers=8)
```

### BatchResult

```
BatchResult(
    succeeded: tuple[str, ...],
    failed: dict[str, RemoteStoreError],
)
```

Outcome of a batch operation.

Attributes:

- **`succeeded`** (`tuple[str, ...]`) – Paths that completed without error.
- **`failed`** (`dict[str, RemoteStoreError]`) – Mapping from path to the error that occurred.

#### all_succeeded

```
all_succeeded: bool
```

`True` when every path succeeded.

#### total

```
total: int
```

Total number of paths processed (succeeded + failed).

### batch_delete

```
batch_delete(
    store: Store,
    paths: Iterable[str],
    *,
    missing_ok: bool = False,
    stop_on_error: bool = False,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> BatchResult
```

Delete multiple files, collecting errors.

Parameters:

- **`store`** (`Store`) – The Store to delete from.
- **`paths`** (`Iterable[str]`) – File paths to delete.
- **`missing_ok`** (`bool`, default: `False` ) – Forwarded to each store.delete() call.
- **`stop_on_error`** (`bool`, default: `False` ) – Stop on first RemoteStoreError (sequential only).
- **`concurrent`** (`bool`, default: `False` ) – Use a thread pool for parallel execution.
- **`max_workers`** (`int | None`, default: `None` ) – Max threads (forwarded to ThreadPoolExecutor).

Returns:

- `BatchResult` – A BatchResult with succeeded/failed paths.

Raises:

- `ValueError` – If both concurrent and stop_on_error are True.

### batch_copy

```
batch_copy(
    store: Store,
    pairs: Iterable[tuple[str, str]],
    *,
    overwrite: bool = False,
    stop_on_error: bool = False,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> BatchResult
```

Copy multiple files, collecting errors.

Parameters:

- **`store`** (`Store`) – The Store to copy within.
- **`pairs`** (`Iterable[tuple[str, str]]`) – (src, dst) tuples.
- **`overwrite`** (`bool`, default: `False` ) – Forwarded to each store.copy() call.
- **`stop_on_error`** (`bool`, default: `False` ) – Stop on first RemoteStoreError (sequential only).
- **`concurrent`** (`bool`, default: `False` ) – Use a thread pool for parallel execution.
- **`max_workers`** (`int | None`, default: `None` ) – Max threads (forwarded to ThreadPoolExecutor).

Returns:

- `BatchResult` – A BatchResult with succeeded/failed source paths.

Raises:

- `ValueError` – If both concurrent and stop_on_error are True.

### batch_exists

```
batch_exists(
    store: Store,
    paths: Iterable[str],
    *,
    concurrent: bool = False,
    max_workers: int | None = None,
) -> dict[str, bool]
```

Check existence of multiple paths.

Unlike `batch_delete()` and `batch_copy()`, this function does **not** catch errors — any exception from `store.exists()` propagates immediately.

Parameters:

- **`store`** (`Store`) – The Store to query.
- **`paths`** (`Iterable[str]`) – Paths to check.
- **`concurrent`** (`bool`, default: `False` ) – Use a thread pool for parallel execution.
- **`max_workers`** (`int | None`, default: `None` ) – Max threads (forwarded to ThreadPoolExecutor).

Returns:

- `dict[str, bool]` – Dict mapping each path to True/False.

## See also

- [Batch Operations](https://docs.remotestore.dev/stable/guides/batch-operations/index.md) — guide to bulk delete, copy, and exists
- [Batch Operations example](https://docs.remotestore.dev/stable/tutorial/examples/batch-operations/index.md) — batch operations in action
