# Seekable Read Specification

## Overview

Seekable read provides `Store.read_seekable()` -- a method that always
returns a seekable `BinaryIO` stream, backend-optimized for random access.
Complements `Store.read()` (which returns the backend's natural stream,
possibly non-seekable). Follows [ADR-0017](../adrs/0017-seekable-read-on-store-api.md),
superseding the three-tier extension design in ADR-0016.

---

## SEEK-001: Capability Declaration

**Invariant:** `Capability.SEEKABLE_READ` is an enum member. Backends whose
`read()` always returns a seekable stream declare it in their `CapabilitySet`.
**Postconditions:** Local, Memory, S3, S3-PyArrow, and SFTP declare
`SEEKABLE_READ`. Azure and HTTP do not.

## SEEK-002: `Store.read_seekable()` Contract

**Invariant:** `Store.read_seekable(path)` always returns a seekable
`BinaryIO` stream positioned at byte 0.
**Postconditions:**
- The returned stream satisfies `stream.seekable() == True`.
- The stream content matches the file at *path*.
- The caller owns the stream and must close it.

## SEEK-003: `Backend.read_seekable()` Default

**Invariant:** `Backend.read_seekable(path)` has a concrete default
implementation. Calls `self.read(path)`. If the returned stream is
seekable, returns it directly (zero-copy passthrough). Otherwise, spools
into a `SpooledTemporaryFile(max_size=8_388_608)` and returns it
positioned at byte 0.
**Postconditions:** All backends support `read_seekable()` without
overriding. Backends MAY override for optimization.

## SEEK-004: Passthrough for Seekable Backends

**Invariant:** When `self.read(path)` returns a seekable stream,
`read_seekable()` returns the same stream instance with no copying.
**Postconditions:** Local, Memory, S3, S3-PyArrow, and SFTP return the
`read()` stream directly. Zero overhead.

## SEEK-005: Spool Fallback for Non-Seekable Backends

**Invariant:** When `self.read(path)` returns a non-seekable stream,
the default `read_seekable()` spools it into a `SpooledTemporaryFile`.
Content up to 8 MB stays in RAM; beyond that spills to a temporary file
on disk.
**Postconditions:** The returned stream is seekable at byte 0. The
original stream is closed after spooling.

## SEEK-006: Azure Range Reader Override

**Invariant:** `AzureBackend` overrides `read_seekable()` to return an
`_AzureRangeReader` -- a seekable `io.RawIOBase` where each `readinto()`
issues a single HTTP Range request via `download_blob(offset=, length=)`.
**Postconditions:**
- No data is downloaded until `read()` is called.
- `seek()` and `tell()` update position without I/O.
- Sequential `read()` calls issue one HTTP request per `readinto()` call.
- The stream is wrapped in `_ErrorMappingStream` (no `BufferedReader` -- its
  seek-invalidation would defeat range reads by turning each
  `PythonFile.read_at()` into a separate HTTP request).

## SEEK-007: Azure `read()` Unchanged

**Invariant:** `AzureBackend.read()` continues to return the chunked
forward-only `_AzureBinaryIO` stream. It is NOT replaced by the range
reader.
**Postconditions:** Sequential callers get efficient chunked streaming.
`read()` and `read_seekable()` serve different I/O patterns.

## SEEK-008: Arrow Integration

**Invariant:** `StoreFileSystemHandler.open_input_file()` calls
`store.read_seekable()` instead of `store.read()` for the Tier 3
streaming path (files larger than `materialization_threshold`).
**Postconditions:** PyArrow gets a seekable handle optimized for sparse
random access. Column pruning works on Azure without full-file
materialization.

## SEEK-009: ProxyStore Forwarding

**Invariant:** `ProxyStore.read_seekable()` delegates to
`self._inner.read_seekable()`. `ObservedStore` fires hooks.
`CachedStore` inherits the default.
**Postconditions:** All proxy layers forward correctly.

## SEEK-010: Error Propagation

**Invariant:** Backend errors (e.g. `NotFound`) propagate through
`read_seekable()` as Store errors.
**Postconditions:** No error remapping beyond the standard
`_ErrorMappingStream` behavior.

## SEEK-011: Stream Closure After Spooling

**Invariant:** When the default `read_seekable()` spools, the original
stream from `read()` is closed after the content is fully copied.
**Postconditions:** The caller owns only the returned spool.

## SEEK-012: `fileno()` Limitation

**Invariant:** When `read_seekable()` returns a `SpooledTemporaryFile`
(non-seekable backend, no override), `fileno()` may raise when content
is still in memory (Python < 3.12).
**Postconditions:** Documented in the method docstring.
