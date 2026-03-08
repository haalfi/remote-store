# ext.batch - Batch Operations Specification

## Overview

`ext.batch` provides convenience functions for operating on collections of paths:
batch delete, batch copy, and batch existence checks. All functions call Store
methods one-by-one by default (sequential execution) and collect errors instead
of failing on first error. Optional parallel execution via `concurrent=True`
uses `concurrent.futures.ThreadPoolExecutor` for cloud backends that benefit
from concurrent I/O. No backend-specific fast-paths (e.g., S3 native batch
delete) are used — the value is a clean convenience API with error aggregation
and optional parallelism.

**Module:** `src/remote_store/ext/batch.py`
**Dependencies:** None (pure Python, stdlib only, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API), ID-022, ID-035.

---

## Requirements

### BATCH-001: BatchResult Dataclass

**Invariant:** `BatchResult` is a frozen dataclass with two fields:
- `succeeded: tuple[str, ...]` — paths that completed successfully.
- `failed: dict[str, RemoteStoreError]` — mapping from path to the error raised.

Properties:
- `all_succeeded: bool` — `True` when `failed` is empty.
- `total: int` — `len(succeeded) + len(failed)`.

### BATCH-002: batch_delete Signature

**Invariant:** `batch_delete(store, paths, *, missing_ok=False, stop_on_error=False, concurrent=False, max_workers=None) -> BatchResult`. `store` is a `Store` instance. `paths` is an iterable of `str`.

### BATCH-003: batch_delete Sequential Execution

**Invariant:** When `concurrent=False` (default), `batch_delete` calls `store.delete(path, missing_ok=missing_ok)` for each path in order. Each call is independent — no batching or parallelism. See BATCH-020 for concurrent execution.

### BATCH-004: batch_delete Error Collection

**Invariant:** When `stop_on_error=False` (default), if `store.delete()` raises a `RemoteStoreError` subclass, the path is recorded in `failed` and processing continues with the next path.

### BATCH-005: batch_delete stop_on_error

**Invariant:** When `stop_on_error=True`, the first `RemoteStoreError` from `store.delete()` is recorded in `failed` and processing stops immediately. Already-succeeded paths remain in `succeeded`.

### BATCH-006: batch_delete missing_ok

**Invariant:** The `missing_ok` parameter is forwarded to each `store.delete()` call. When `True`, deleting a non-existent file does not raise an error.

### BATCH-007: batch_delete Empty Input

**Invariant:** When `paths` is empty, `batch_delete` returns a `BatchResult` with `succeeded=()` and `failed={}`.

### BATCH-008: batch_copy Signature

**Invariant:** `batch_copy(store, pairs, *, overwrite=False, stop_on_error=False, concurrent=False, max_workers=None) -> BatchResult`. `store` is a `Store` instance. `pairs` is an iterable of `(src, dst)` string tuples.

### BATCH-009: batch_copy Sequential Execution

**Invariant:** When `concurrent=False` (default), `batch_copy` calls `store.copy(src, dst, overwrite=overwrite)` for each pair in order. Each call is independent. See BATCH-020 for concurrent execution.

### BATCH-010: batch_copy Error Collection

**Invariant:** When `stop_on_error=False` (default), if `store.copy()` raises a `RemoteStoreError` subclass, the source path is recorded in `failed` and processing continues.

### BATCH-011: batch_copy stop_on_error

**Invariant:** When `stop_on_error=True`, the first `RemoteStoreError` from `store.copy()` is recorded in `failed` and processing stops immediately.

### BATCH-012: batch_copy overwrite

**Invariant:** The `overwrite` parameter is forwarded to each `store.copy()` call. When `True`, existing destinations are overwritten.

### BATCH-013: batch_copy Empty Input

**Invariant:** When `pairs` is empty, `batch_copy` returns a `BatchResult` with `succeeded=()` and `failed={}`.

### BATCH-014: batch_exists Signature

**Invariant:** `batch_exists(store, paths, *, concurrent=False, max_workers=None) -> dict[str, bool]`. `store` is a `Store` instance. `paths` is an iterable of `str`. Returns a dict mapping each path to its existence status.

### BATCH-015: batch_exists Sequential Execution

**Invariant:** When `concurrent=False` (default), `batch_exists` calls `store.exists(path)` for each path in order. See BATCH-020 for concurrent execution.

### BATCH-016: batch_exists Error Propagation

**Invariant:** `batch_exists` does **not** catch errors. If `store.exists()` raises, the exception propagates immediately. There is no `stop_on_error` parameter. Rationale: `exists()` should never raise under normal conditions; an exception indicates a backend failure that the caller must handle.

### BATCH-017: batch_exists Empty Input

**Invariant:** When `paths` is empty, `batch_exists` returns an empty dict `{}`.

### BATCH-018: No Backend Coupling

**Invariant:** All batch functions operate exclusively through the public `Store` API. They never access `store._backend` or any backend internals. This ensures they work correctly with `Store.child()`, capability gating, path rebasing, and any future Store wrapper.

### BATCH-019: Capability Gating Propagation

**Invariant:** Capability errors (`CapabilityNotSupported`) raised by Store methods are **not** caught by error collection. They propagate immediately regardless of `stop_on_error`. Rationale: a missing capability is a configuration error, not a per-path issue.

---

## Concurrent Execution (ID-035)

### BATCH-020: concurrent Parameter

**Invariant:** All three batch functions accept a `concurrent: bool = False` keyword argument. When `True`, operations execute in a `concurrent.futures.ThreadPoolExecutor` instead of sequentially. The default (`False`) preserves the original sequential behavior.

### BATCH-021: max_workers Parameter

**Invariant:** All three batch functions accept a `max_workers: int | None = None` keyword argument, forwarded to `ThreadPoolExecutor(max_workers=...)`. When `None`, the executor uses its default (typically `min(32, os.cpu_count() + 4)`). Ignored when `concurrent=False`.

### BATCH-022: stop_on_error + concurrent Incompatibility

**Invariant:** `batch_delete` and `batch_copy` raise `ValueError` when both `stop_on_error=True` and `concurrent=True` are passed. Rationale: concurrent execution has non-deterministic ordering, so "stop on first error" has no well-defined semantics.

### BATCH-023: Concurrent Result Ordering

**Invariant:** When `concurrent=True`, the order of paths in `BatchResult.succeeded` is non-deterministic (determined by thread completion order). Callers must not rely on insertion order. When `concurrent=False`, the original sequential order is preserved.

### BATCH-024: Concurrent Error Semantics

**Invariant:** Error collection in concurrent mode follows the same rules as sequential mode: `RemoteStoreError` subclasses are recorded in `failed`, `CapabilityNotSupported` propagates immediately, and `batch_exists` does not catch errors.

### BATCH-025: Concurrent Empty Input

**Invariant:** When input is empty and `concurrent=True`, the function returns the same empty result as sequential mode. The executor is created but submits no futures.
