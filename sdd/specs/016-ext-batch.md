# ext.batch — Batch Operations Specification

## Overview

`ext.batch` provides convenience functions for operating on collections of paths:
batch delete, batch copy, and batch existence checks. All functions call Store
methods one-by-one (sequential execution) and collect errors instead of failing
on first error. No backend-specific fast-paths (e.g., S3 native batch delete)
are used — the value is a clean convenience API with error aggregation.

**Module:** `src/remote_store/ext/batch.py`
**Dependencies:** None (pure Python, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API), ID-022.

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

**Invariant:** `batch_delete(store, paths, *, missing_ok=False, stop_on_error=False) -> BatchResult`. `store` is a `Store` instance. `paths` is an iterable of `str`.

### BATCH-003: batch_delete Sequential Execution

**Invariant:** `batch_delete` calls `store.delete(path, missing_ok=missing_ok)` for each path in order. Each call is independent — no batching or parallelism.

### BATCH-004: batch_delete Error Collection

**Invariant:** When `stop_on_error=False` (default), if `store.delete()` raises a `RemoteStoreError` subclass, the path is recorded in `failed` and processing continues with the next path.

### BATCH-005: batch_delete stop_on_error

**Invariant:** When `stop_on_error=True`, the first `RemoteStoreError` from `store.delete()` is recorded in `failed` and processing stops immediately. Already-succeeded paths remain in `succeeded`.

### BATCH-006: batch_delete missing_ok

**Invariant:** The `missing_ok` parameter is forwarded to each `store.delete()` call. When `True`, deleting a non-existent file does not raise an error.

### BATCH-007: batch_delete Empty Input

**Invariant:** When `paths` is empty, `batch_delete` returns a `BatchResult` with `succeeded=()` and `failed={}`.

### BATCH-008: batch_copy Signature

**Invariant:** `batch_copy(store, pairs, *, overwrite=False, stop_on_error=False) -> BatchResult`. `store` is a `Store` instance. `pairs` is an iterable of `(src, dst)` string tuples.

### BATCH-009: batch_copy Sequential Execution

**Invariant:** `batch_copy` calls `store.copy(src, dst, overwrite=overwrite)` for each pair in order. Each call is independent.

### BATCH-010: batch_copy Error Collection

**Invariant:** When `stop_on_error=False` (default), if `store.copy()` raises a `RemoteStoreError` subclass, the source path is recorded in `failed` and processing continues.

### BATCH-011: batch_copy stop_on_error

**Invariant:** When `stop_on_error=True`, the first `RemoteStoreError` from `store.copy()` is recorded in `failed` and processing stops immediately.

### BATCH-012: batch_copy overwrite

**Invariant:** The `overwrite` parameter is forwarded to each `store.copy()` call. When `True`, existing destinations are overwritten.

### BATCH-013: batch_copy Empty Input

**Invariant:** When `pairs` is empty, `batch_copy` returns a `BatchResult` with `succeeded=()` and `failed={}`.

### BATCH-014: batch_exists Signature

**Invariant:** `batch_exists(store, paths) -> dict[str, bool]`. `store` is a `Store` instance. `paths` is an iterable of `str`. Returns a dict mapping each path to its existence status.

### BATCH-015: batch_exists Sequential Execution

**Invariant:** `batch_exists` calls `store.exists(path)` for each path in order.

### BATCH-016: batch_exists Error Propagation

**Invariant:** `batch_exists` does **not** catch errors. If `store.exists()` raises, the exception propagates immediately. There is no `stop_on_error` parameter. Rationale: `exists()` should never raise under normal conditions; an exception indicates a backend failure that the caller must handle.

### BATCH-017: batch_exists Empty Input

**Invariant:** When `paths` is empty, `batch_exists` returns an empty dict `{}`.

### BATCH-018: No Backend Coupling

**Invariant:** All batch functions operate exclusively through the public `Store` API. They never access `store._backend` or any backend internals. This ensures they work correctly with `Store.child()`, capability gating, path rebasing, and any future Store wrapper.

### BATCH-019: Capability Gating Propagation

**Invariant:** Capability errors (`CapabilityNotSupported`) raised by Store methods are **not** caught by error collection. They propagate immediately regardless of `stop_on_error`. Rationale: a missing capability is a configuration error, not a per-path issue.
