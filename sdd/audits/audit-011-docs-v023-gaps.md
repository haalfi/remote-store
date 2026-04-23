# Audit-011: Handwritten Docs — v0.23.0+ Gaps

**Date:** 2026-04-23
**Scope:** Handwritten guides, tutorials, and example snippets. Auto-generated API reference excluded.
**Reference:** BK-159

---

## Scope & Methodology

Audit basis: CHANGELOG [Unreleased] items and direct inspection of `src/remote_store/_backend.py` against all handwritten documentation.

Key API changes after v0.23.0:
- `Backend.write()` and `Backend.write_atomic()` now return `WriteResult` (was `None`)
- Both write methods accept a new `metadata: Mapping[str, str] | None = None` kwarg
- New capabilities: `USER_METADATA`, `WRITE_RESULT_NATIVE`, `LAZY_READ`
- New `Store.head()` method (gated on `Capability.METADATA`)
- New `ext.write` module: `write_with_hash`, `open_atomic_with_hash`, `HashingAtomicWriter`
- New `aio.ext.write` module: async `write_with_hash`
- New `AsyncBackendSyncAdapter` (async backend → sync caller)

Files read and compared against the above:

| File | Verdict |
|------|---------|
| `guides/custom-backend-guide.md` | Multiple Critical/Major gaps |
| `examples/snippets/custom_backend_guide.py` | Critical gaps (snippet is test source for the guide) |
| `guides/async.md` | Major gaps |
| `guides/async-sync-bridges.md` | Current |
| `docs-src/write-integrity.md` | Current |
| `docs-src/capabilities-matrix.md` | Current |
| `guides/extensions.md` | Major gap |
| `guides/backends/local.md` | Minor gap |
| `guides/backends/s3.md` | Minor gap |
| `guides/backends/azure.md` | Minor gap |
| `guides/backends/memory.md` | Current |
| `guides/health-check.md` | Current |
| `guides/concurrency.md` | Current |
| `docs-src/architecture.md` | Current |
| `examples/snippets/write_integrity.py` | Current |
| `examples/snippets/write_integrity_async.py` | Current |
| `examples/snippets/async_sync_bridges.py` | Current (AsyncBackendSyncAdapter covered) |
| `examples/getting_started/atomic_writes.py` | Minor gap |
| `examples/getting_started/file_operations.py` | Minor gap |
| `examples/getting_started/streaming_io.py` | Minor gap |

Not read: `guides/backends/sftp.md`, `guides/backends/http.md`, `guides/backends/sql-blob.md`, `guides/backends/sql-query.md`, `guides/backends/s3-pyarrow.md`, `guides/backends/index.md`, `guides/choosing-a-backend.md`.

---

## Summary Table

| ID | Severity | File | Gap type | Description |
|----|----------|------|----------|-------------|
| F-01 | **Critical** | `guides/custom-backend-guide.md:568-569` | Stale | Quick-reference table: `write()` and `write_atomic()` show return `None` — should be `WriteResult` |
| F-02 | **Critical** | `examples/snippets/custom_backend_guide.py:218,248` | Stale | `write()` and `write_atomic()` annotated `-> None` — should be `-> WriteResult` |
| F-03 | **Critical** | `examples/snippets/custom_backend_guide.py:218,248` | Stale | `write()` and `write_atomic()` missing `metadata: Mapping[str, str] \| None = None` parameter |
| F-04 | **Critical** | `guides/custom-backend-guide.md:568` | Stale | Quick-reference table `write()` signature missing `metadata=` parameter |
| F-05 | **Major** | `guides/custom-backend-guide.md` Step 1 | Missing | `WriteResult` absent from Step 1 import table and snippet; needed to annotate return type |
| F-06 | **Major** | `guides/custom-backend-guide.md` Step 2 | Missing | `USER_METADATA`, `WRITE_RESULT_NATIVE`, `LAZY_READ` capabilities never mentioned |
| F-07 | **Major** | `guides/custom-backend-guide.md` Step 7 | Missing | `metadata=` kwarg and `WriteResult` return type absent from Step 7 narrative and snippet |
| F-08 | **Major** | `guides/async.md` | Missing | No mention of `WriteResult` from async writes; no `metadata=` kwarg; no `aio.ext.write` |
| F-09 | **Major** | `guides/extensions.md` | Missing | `aio.ext.write` entirely absent from the extensions table |
| F-10 | **Major** | `guides/extensions.md:34-51` | Missing | `ext.write` imports absent from the "always-available" import example block |
| F-11 | **Minor** | `guides/backends/local.md:32` | Stale | "All capabilities are supported" — Local lacks `USER_METADATA` per the capabilities matrix |
| F-12 | **Minor** | `guides/backends/s3.md:94-96` | Missing | No mention that write operations return `WriteResult` with digest (WRITE_RESULT_NATIVE); the digest note is read-only context, write context absent |
| F-13 | **Minor** | `guides/backends/azure.md:121` | Missing | No mention of `metadata=` kwarg support (`USER_METADATA`) or write-result fields (`WRITE_RESULT_NATIVE`) for Azure write operations |
| F-14 | **Minor** | `examples/getting_started/atomic_writes.py:25,36` | Stale | `write_atomic()` return discarded — example focused on atomicity but doesn't capture `WriteResult` |
| F-15 | **Minor** | `examples/getting_started/file_operations.py:24-27`, `streaming_io.py:19,31,45` | Stale | `write()` called without capturing return value — examples treat write as void |
| F-16 | **Minor** | `guides/async.md` | Missing | No cross-reference to `AsyncBackendSyncAdapter` or `guides/async-sync-bridges.md` for the async→sync direction |

---

## Findings

### F-01 — `guides/custom-backend-guide.md` Quick-reference table: wrong return types (Critical)

**Location:** `guides/custom-backend-guide.md`, lines 568-569.

Current:
```
| `write(path, content, overwrite)` | `None` | ... |
| `write_atomic(path, content, overwrite)` | `None` | ... |
```

Actual Backend ABC (`src/remote_store/_backend.py:187`, `215`):
```python
def write(...) -> WriteResult: ...
def write_atomic(...) -> WriteResult: ...
```

A developer copying the guide's table would believe the methods return nothing and omit the `WriteResult` from their implementation. The Backend ABC now requires `WriteResult` as the return type for both methods. Any custom backend built from this guide will fail type-checking and may not integrate correctly with `Store.write_result`-dependent callers.

---

### F-02 — `examples/snippets/custom_backend_guide.py`: `-> None` annotations (Critical)

**Location:** Lines 218, 248.

Current:
```python
# line 218
def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
# line 248
def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
```

These snippets are the *tested source* embedded verbatim into the guide via `--8<--` includes. Developers who adapt this code create a non-conformant backend that cannot satisfy the Backend ABC's return type constraint.

---

### F-03 — `examples/snippets/custom_backend_guide.py`: `metadata=` kwarg missing (Critical)

**Location:** Lines 218 (`write`) and 248 (`write_atomic`).

Backend ABC (`src/remote_store/_backend.py:186`, `214`):
```python
metadata: Mapping[str, str] | None = None,
```

Neither method signature in the snippet includes this parameter. A backend that doesn't accept `metadata=` cannot be called with it even when the `Store` passes it through, causing a `TypeError` at runtime for backends registering `USER_METADATA`.

---

### F-04 — `guides/custom-backend-guide.md` Quick-reference table: `metadata=` missing (Critical)

**Location:** `guides/custom-backend-guide.md:568`.

Current:
```
| `write(path, content, overwrite)` | ...
```

Should include `metadata=None` in the signature. Combined with F-01, the entire quick-reference table for write methods is wrong on both the return type and parameter list.

---

### F-05 — `guides/custom-backend-guide.md` Step 1 imports: `WriteResult` absent (Major)

**Location:** `guides/custom-backend-guide.md:47-52` (import table), `examples/snippets/custom_backend_guide.py:34-49` (step1-imports snippet).

`WriteResult` is exported from `remote_store` (`src/remote_store/__init__.py:28`, `70`). It is the required return type for `write()` and `write_atomic()`, so any implementation needs to import it. Neither the guide's import table nor the snippet's imports block includes it.

---

### F-06 — `guides/custom-backend-guide.md` Step 2 capabilities: three new capabilities not mentioned (Major)

**Location:** `guides/custom-backend-guide.md:55-67` (Step 2 narrative and snippet).

The Step 2 snippet demonstrates a capability set without `USER_METADATA`, `WRITE_RESULT_NATIVE`, or `LAZY_READ`. The narrative never mentions these flags. Developers won't know to consider them when declaring their backend's capabilities:

- `USER_METADATA` gates whether `metadata=` values are stored (a strict gate — passing non-empty metadata to a backend without this capability raises `CapabilityNotSupported`)
- `WRITE_RESULT_NATIVE` signals that `WriteResult` fields beyond `path`/`size` are populated
- `LAZY_READ` signals that `read()` fetches lazily (affects caller strategies for large files)

---

### F-07 — `guides/custom-backend-guide.md` Step 7: write narrative omits `metadata=` and `WriteResult` (Major)

**Location:** `guides/custom-backend-guide.md:142-153`.

Step 7's narrative says:

> "`content` is `bytes | BinaryIO`. Normalize with `content if isinstance(content, bytes) else content.read()`."

It then lists implementation notes. Neither the `metadata=` kwarg nor the `WriteResult` return value are mentioned anywhere in the step. A developer implementing the backend from the step-by-step instructions has no indication that their `write()` must accept `metadata` and return a populated `WriteResult`.

---

### F-08 — `guides/async.md`: missing `WriteResult`, `metadata=`, and `aio.ext.write` (Major)

**Location:** `guides/async.md`, multiple.

Three separate gaps:

**1. `WriteResult` from async writes.** The quick start (line 16), FastAPI example (line 84), and iterator write (lines 53-58) all discard the `await store.write(...)` return value with no mention that a `WriteResult` is returned.

**2. `metadata=` kwarg on async writes.** Not mentioned in the guide. `AsyncStore` write methods accept `metadata=` in parallel with the sync API.

**3. `aio.ext.write` module.** The guide has no mention of `aio.ext.write` or `write_with_hash` for async stores. The write-integrity guide documents the sync ext and the async ext, but async.md is the natural entry point for async users discovering the full async API surface.

---

### F-09 — `guides/extensions.md`: `aio.ext.write` absent from extensions table (Major)

**Location:** `guides/extensions.md`, the extensions table.

The table lists `ext.write` (line 18) but has no entry for `aio.ext.write`. This is a new module (`src/remote_store/aio/ext/write.py`) with a distinct `write_with_hash` function for `AsyncStore`. A user scanning the extensions table for async-specific extensions will not find it.

---

### F-10 — `guides/extensions.md`: `ext.write` absent from "always-available" import block (Major)

**Location:** `guides/extensions.md:34-51`.

The "always-available" imports section lists `batch_delete`, `glob_files`, `observe`, `upload`, `download`, `cache`, `checksum`, `verify`, `partition_path`, `parse_partition`, `ProgressReader`, `ChecksumReader` — but not `write_with_hash`, `open_atomic_with_hash`, or `HashingAtomicWriter`.

These three symbols are re-exported from the top-level package:
```python
# src/remote_store/__init__.py:48, 132
from remote_store.ext.write import HashingAtomicWriter, open_atomic_with_hash, write_with_hash
"write_with_hash",  # in __all__
```

`ext.write` has no optional dependency (the table marks it `*(none)*`), so the omission from the import block is inconsistent with how every other no-extra extension is presented.

---

### F-11 — `guides/backends/local.md`: "All capabilities supported" is wrong (Minor)

**Location:** `guides/backends/local.md:32`.

Current:
> "All capabilities are supported. The local backend is the reference implementation."

Per `docs-src/capabilities-matrix.md:25`, Local has `USER_METADATA = —` (not supported). Passing `metadata={"key": "val"}` to a Local-backed store raises `CapabilityNotSupported`. A user reading only the local guide would believe metadata= is safe to use with Local.

---

### F-12 — `guides/backends/s3.md`: write-result fields not documented (Minor)

**Location:** `guides/backends/s3.md:88-96`.

The "File Metadata" section notes that `digest` is `Always None` (for `get_file_info()` and `list_files()`). That statement is accurate for read operations. However, S3 now declares `WRITE_RESULT_NATIVE` and populates `WriteResult.digest` with an auto-CRC32 on write operations (BUG-177). The guide has no write-result section, so users are unaware that:

1. `store.write(...)` on S3 now returns a `WriteResult` with `digest`, `etag`, and `last_modified` populated.
2. S3 supports `USER_METADATA` — `metadata=` in write calls is stored as S3 object metadata.

The "Capabilities" section (line 236) says "all except `ATOMIC_MOVE`" which is correct per the matrix, but a prose note on write-result behavior would prevent the "always None" note from misleading users who then see a non-None digest in write results.

---

### F-13 — `guides/backends/azure.md`: no write-result or metadata= documentation (Minor)

**Location:** `guides/backends/azure.md:121`.

"Capabilities: Supports all capabilities except `SEEKABLE_READ` and `ATOMIC_MOVE`." — correct per matrix. However, nothing in the guide calls out:

- `metadata=` kwarg support (Azure declares `USER_METADATA`)
- Rich write results (Azure declares `WRITE_RESULT_NATIVE`; `WriteResult.etag`, `last_modified`, `metadata` are populated)
- HNS-specific `WriteResult.version_id` field (HNS write_atomic result)

The "File Metadata" section (lines 113-119) covers `get_file_info()` fields but omits the write-side counterpart.

---

### F-14 — `examples/getting_started/atomic_writes.py`: `WriteResult` not captured (Minor)

**Location:** Lines 25 and 36.

```python
store.write_atomic("config.json", b'{"version": 1}')      # line 25 — result discarded
store.write_atomic("config.json", b'{"version": 2}', overwrite=True)  # line 36 — result discarded
```

This example is specifically about write semantics. Not capturing the `WriteResult` treats the API as void and misses an opportunity to demonstrate `result.size`, `result.path`, or `result.digest`.

---

### F-15 — `examples/getting_started/file_operations.py`, `streaming_io.py`: void-style writes (Minor)

**Location:** `file_operations.py:24-27`, `streaming_io.py:19,31,45`.

Write calls throughout these examples:
```python
store.write("docs/readme.txt", b"First file")  # result discarded
store.write("streamed.txt", stream)            # result discarded
```

These examples are demonstrating other aspects of the Store API, but all write() calls treat the API as if it returns None. Minor because the examples' focus is not write results, but they implicitly model void usage to new users.

---

### F-16 — `guides/async.md`: no reference to `AsyncBackendSyncAdapter` (Minor)

**Location:** `guides/async.md:26-28` (adapter section), `164-170` (See also).

The guide explains the sync→async direction (`SyncBackendAdapter`) but has no mention of the async→sync direction (`AsyncBackendSyncAdapter`). A user with an `AsyncAzureBackend` who needs to call it from sync code has no hint that a solution exists in this guide. The `guides/async-sync-bridges.md` guide covers it correctly, but `async.md`'s See also section (line 166) links to `api/aio.md`, not to the bridges guide.

---

## Files Checked and Found Current

| File | Reason for checking | Verdict |
|------|---------------------|---------|
| `guides/async-sync-bridges.md` | `AsyncBackendSyncAdapter` coverage | Current — decision table and usage examples present |
| `docs-src/write-integrity.md` | New page for ext.write, head(), metadata= | Current — comprehensive and accurate |
| `docs-src/capabilities-matrix.md` | Three new capabilities expected | Current — `LAZY_READ`, `WRITE_RESULT_NATIVE`, `USER_METADATA` present with correct per-backend values |
| `guides/backends/memory.md` | `WRITE_RESULT_NATIVE`, `last_modified` post-BUG-169 | Current — "all except GLOB and LAZY_READ" implicitly includes the new capabilities correctly |
| `guides/health-check.md` | `Store.head()` mention expected | Current — guide scope is `ping()`; `head()` belongs in write-integrity which covers it |
| `guides/concurrency.md` | Write atomicity / `None`-return patterns | Current — guide is about move/overwrite semantics, no write return type dependency |
| `docs-src/architecture.md` | `AsyncBackendSyncAdapter` layer diagram | Current — architecture overview does not need adapter-level detail |
| `examples/snippets/write_integrity.py` | ext.write correctness | Current — accurate usage of `write_with_hash`, `open_atomic_with_hash`, `store.head()` |
| `examples/snippets/write_integrity_async.py` | aio.ext.write correctness | Current — accurate usage of `aio.ext.write.write_with_hash` |
| `examples/snippets/async_sync_bridges.py` | `AsyncBackendSyncAdapter` snippet | Current — uses `AsyncMemoryBackend` and `AsyncBackendSyncAdapter` correctly |

---

## Files Not Checked (Out of Scope for This Pass)

- `guides/backends/sftp.md` — check `USER_METADATA`/`WRITE_RESULT_NATIVE` capability notes; SFTP has both as `—`
- `guides/backends/http.md` — read-only; `WRITE_RESULT_NATIVE` and `USER_METADATA` are `—`; likely fine
- `guides/backends/sql-blob.md` — conditional `†` for `WRITE_RESULT_NATIVE`/`USER_METADATA`; may need schema note alignment
- `guides/backends/sql-query.md` — read-only; likely fine
- `guides/backends/s3-pyarrow.md` — `USER_METADATA = —`, `WRITE_RESULT_NATIVE = Yes`; guide may say "same as S3" incorrectly for metadata= kwarg
- `guides/backends/index.md` — capability overview; may reference old capability set
- `guides/choosing-a-backend.md` — capability decision tree; may not include new flags
- `docs-src/security-model.md` — credential scope; unlikely affected
- All `examples/backends/` scripts — write() result not expected to be captured in connection demos
- All `examples/integrations/` scripts — Dagster, PyArrow: indirect write usage
