# Streaming Atomic Writes Specification

## Overview

`open_atomic()` on `Backend` and `Store` returns a context manager that yields
a writable file object. Data is written to a temporary location; on successful
exit the file is atomically promoted to its final path. On failure the temporary
artifact is cleaned up and the target path is never modified.

This eliminates the memory-buffering requirement of `write_atomic()` for
multi-GB workloads (Parquet exports, log rotation, report generation).

RFC: `sdd/rfcs/rfc-0004-streaming-atomic-writes.md`

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| SAW-001 | `Backend.open_atomic()` is abstract, returns context manager yielding `BinaryIO` | Done |
| SAW-002 | `Store.open_atomic()` gates on `Capability.ATOMIC_WRITE` | Done |
| SAW-003 | On successful exit, file is atomically visible at target path | Done |
| SAW-004 | On exception, target path is unchanged (no partial file) | Done |
| SAW-005 | Temp artifact is cleaned up on both success and failure | Done |
| SAW-006 | `AlreadyExists` raised if file exists and `overwrite=False` | Done |
| SAW-007 | `InvalidPath` raised if path is empty | Done |
| SAW-008 | LocalBackend uses `mkstemp` + `os.replace` | Done |
| SAW-009 | SFTPBackend uses `.~tmp.*` + `posix_rename` (with fallback) | Done |
| SAW-010 | S3Backend / S3PyArrowBackend buffer via `SpooledTemporaryFile` then PUT | Done |
| SAW-011 | AzureBackend non-HNS buffers then PUT; HNS uses temp + DFS rename | Done |
| SAW-012 | MemoryBackend buffers in `BytesIO` then commits | Done |
| SAW-013 | Yielded file supports `write()` and `tell()`; seekability is backend-dependent | Done |
| SAW-014 | `ext.observe` fires `on_write` hook after successful promotion | Done |
| SAW-015 | `ext.otel` emits a span covering the full open-write-promote lifecycle | Done |

## Capacity note

S3Backend, S3PyArrowBackend, and AzureBackend (non-HNS) buffer the entire file
via `SpooledTemporaryFile` before uploading. Files <= 8 MB are held in memory;
larger files spill to disk. For streams exceeding ~10 GB, callers should
consider native multipart methods or splitting the file.

## Per-backend strategies

### LocalBackend (SAW-008)

`tempfile.mkstemp(dir=parent)` creates the temp file in the same directory.
On success `os.replace()` atomically promotes it. On failure `os.unlink()`
removes the temp file.

### SFTPBackend (SAW-009)

Writes to `.~tmp.{name}.{uuid}` in the same directory. On success,
`posix_rename()` (with `rename()` fallback) promotes it. On failure,
`sftp.remove()` cleans up. Setup (existence check, parent dirs) runs inside
`_errors()` for exception mapping; the yield runs outside `_errors()` so
caller exceptions propagate without remapping.

### S3Backend / S3PyArrowBackend (SAW-010)

S3 PUT is inherently atomic. The implementation buffers via
`SpooledTemporaryFile(max_size=8MB)` then calls `self.write()` on success.
On exception the buffer is discarded without uploading.

### AzureBackend (SAW-011)

Non-HNS: same `SpooledTemporaryFile` + `write()` strategy as S3.
HNS: buffers then uploads to a temp blob, followed by atomic `rename_file()`.
On failure the temp blob is deleted.

### MemoryBackend (SAW-012)

Buffers in `BytesIO`, commits via `self.write()` on successful exit.

## Observability

`ext.observe` maps `open_atomic` to the `on_write` hook (SAW-014), consistent
with `write` and `write_atomic`. `ext.otel` spans cover the full lifecycle
via the existing `around` context-manager pattern (SAW-015).

## Test coverage

- Success path: multi-chunk write, content verification (all backends)
- Exception path: no partial file, temp artifact cleaned up
- `AlreadyExists` guard: `overwrite=False` raises, `overwrite=True` replaces
- `InvalidPath`: empty path raises
- Capability gating: `ATOMIC_WRITE` required
- Observe hook: `on_write` fires after promotion, includes error on failure
- Conformance tests: `TestBackendOpenAtomic` in `tests/backends/conformance/test_atomic.py`
- Store-level tests: `test_store.py`, `test_open_atomic.py`
