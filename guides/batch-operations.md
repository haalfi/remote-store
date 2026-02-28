# Batch Operations

The `ext.batch` module provides convenience functions for operating on
collections of paths: batch delete, batch copy, and batch existence checks.

All functions call Store methods one-by-one (sequential, no parallelism) and
collect errors into a `BatchResult` instead of failing on the first error.
No extra dependencies are required — the module is pure Python and always
available.

## Quick Start

```python
from remote_store import Store, batch_delete, batch_copy, batch_exists
from remote_store.backends import MemoryBackend

store = Store(backend=MemoryBackend())
store.write("a.txt", b"hello")
store.write("b.txt", b"world")

# Check which files exist
exists_map = batch_exists(store, ["a.txt", "b.txt", "c.txt"])
# {"a.txt": True, "b.txt": True, "c.txt": False}

# Copy multiple files
result = batch_copy(store, [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")])
assert result.all_succeeded

# Delete multiple files
result = batch_delete(store, ["a.txt", "b.txt"], missing_ok=True)
assert result.all_succeeded
```

## BatchResult

`batch_delete` and `batch_copy` return a `BatchResult` — a frozen dataclass
that separates successes from failures:

```python
result = batch_delete(store, ["exists.txt", "missing.txt"])

result.succeeded   # ("exists.txt",)
result.failed      # {"missing.txt": NotFound(...)}
result.all_succeeded  # False
result.total          # 2
```

## Error Handling

By default, batch functions continue on error and collect failures:

```python
result = batch_delete(store, ["a.txt", "bad.txt", "c.txt"])
# a.txt deleted, bad.txt fails, c.txt still deleted
```

Use `stop_on_error=True` to halt on the first failure:

```python
result = batch_delete(store, ["a.txt", "bad.txt", "c.txt"], stop_on_error=True)
# a.txt deleted, bad.txt fails, c.txt never attempted
```

### Capability Errors

`CapabilityNotSupported` errors always propagate immediately, regardless of
`stop_on_error`. These indicate a configuration problem (wrong backend for
the operation), not a per-path issue.

## batch_delete

```python
batch_delete(store, paths, *, missing_ok=False, stop_on_error=False) -> BatchResult
```

Deletes each path via `store.delete(path, missing_ok=missing_ok)`.

- `missing_ok=True`: silently skip files that don't exist.
- `stop_on_error=True`: stop on first failure.

## batch_copy

```python
batch_copy(store, pairs, *, overwrite=False, stop_on_error=False) -> BatchResult
```

Copies each `(src, dst)` pair via `store.copy(src, dst, overwrite=overwrite)`.

- `overwrite=True`: overwrite existing destinations.
- `stop_on_error=True`: stop on first failure.

The source path is used as the key in both `succeeded` and `failed`.

## batch_exists

```python
batch_exists(store, paths) -> dict[str, bool]
```

Checks each path via `store.exists(path)`. Returns a dict mapping each path
to `True` or `False`.

Unlike the other batch functions, `batch_exists` does **not** catch errors.
If `store.exists()` raises (e.g., due to a backend failure), the exception
propagates immediately. This is intentional — `exists()` should never fail
under normal conditions.

## Works with Store.child()

All batch functions operate through the public Store API. They work correctly
with `Store.child()`, capability gating, and path rebasing:

```python
store = Store(backend=MemoryBackend())
store.write("reports/q1.csv", b"data")
store.write("reports/q2.csv", b"data")

reports = store.child("reports")
result = batch_delete(reports, ["q1.csv", "q2.csv"])
assert result.all_succeeded
```
