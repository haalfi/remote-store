# Streaming I/O Specification

## Overview

All I/O in `remote_store` is streaming-first. Read operations return `BinaryIO` streams by default. Write operations accept both `bytes` and `BinaryIO`. This spec defines the streaming semantics and cancellation behavior.

## SIO-001: Streaming Reads

**Invariant:** `Backend.read(path)` returns a `BinaryIO` stream positioned at the start.
**Postconditions:** The caller is responsible for consuming and closing the stream. The returned stream is not guaranteed to be seekable. Seekability is a backend-level property (e.g. local files are seekable, HTTP-based streams typically are not), not a Store API contract. Callers that require seekability should use `Store.read_seekable()`. Pre-loading the full file into memory before returning (e.g. returning `io.BytesIO`) is acceptable for backends that do not declare `Capability.LAZY_READ` — the requirement is only that a valid `BinaryIO` is returned, not that data is fetched lazily. See SIO-009.
**Acquire-then-wrap safety invariant:** Between acquiring a raw native handle
(e.g. an s3fs file object, a paramiko `SFTPFile`, an Azure downloader) and
returning the wrapped `BinaryIO` to the caller, the backend MUST guarantee the
raw handle is closed if any part of the wrapping step raises. The recommended
implementation is a helper that closes `raw` on exception before re-raising:

```python
raw = self._native_open(path)
try:
    return _ErrorMappingStream(raw, ...)
except BaseException:
    raw.close()
    raise
```

Failure to observe this invariant causes resource leaks even when the caller
never receives the stream and therefore cannot close it.
**Example:**
```python
stream = backend.read("data.bin")
chunk = stream.read(4096)
```

## SIO-002: Convenience Reads

**Invariant:** `Backend.read_bytes(path)` reads the full content into memory and returns `bytes`.
**Postconditions:** This is a convenience method — internally it reads the full stream.

## SIO-003: Writable Content

**Invariant:** Write operations accept `WritableContent = BinaryIO | bytes`.
**Postconditions:** If `BinaryIO` is provided, the backend reads from the current position to EOF. If `bytes` is provided, the full byte string is written.

## SIO-004: No Partial Reads on Error

**Invariant:** If a read operation fails (e.g. `NotFound`), no partial stream is returned.
**Postconditions:** The error is raised before any data is returned.

## SIO-005: Cancellation Propagation

**Invariant:** Cancellation (e.g. closing a stream mid-read) propagates naturally through the I/O stack.
**Postconditions:** Partially opened resources are cleaned up where possible. Cancellation is never swallowed or remapped.

## SIO-006: No Framework Dependencies

**Invariant:** Streaming I/O uses only `typing.BinaryIO` (stdlib). No dependency on anyio, asyncio, or trio.
**Rationale:** See [ADR-0001](../adrs/0001-architecture-store-registry-backends.md).

## SIO-007: Text Convenience Reads

**Invariant:** `Store.read_text(path, *, encoding="utf-8", errors="strict")` reads the full content via `read_bytes()` and decodes it to `str`.
**Postconditions:** This is a Store-level convenience -- no backend changes. Raises `UnicodeDecodeError` on decode failure with `errors="strict"`. See [028-read-text.md](028-read-text.md) (RTXT-001).

## SIO-008: Seekable Read Capability

**Invariant:** `Capability.SEEKABLE_READ` indicates that `Backend.read()` always returns a seekable stream (`stream.seekable()` is `True`).
**Postconditions:** This is a static guarantee — callers can check `store.supports(Capability.SEEKABLE_READ)` once at setup time instead of checking every stream. All backends support `Store.read_seekable()` regardless of this capability — the capability indicates zero-overhead (no spooling needed).
**See also:** [036-seekable-read.md](036-seekable-read.md), [ADR-0017](../adrs/0017-seekable-read-on-store-api.md).

## SIO-009: Lazy Read Capability

**Invariant:** `Capability.LAZY_READ` indicates that `Backend.read()` fetches data lazily on demand from the native source. Backends that load the full file contents into memory before returning a stream do **not** declare this capability.
**Postconditions:** When `Capability.LAZY_READ` is declared, the stream is connected to the native source and data is pulled as the caller reads. Reading only a small prefix of a large file is expected to avoid loading the full file, though the exact savings depend on backend-level buffering (e.g. s3fs read-ahead, TCP receive buffers). Callers can use `store.supports(Capability.LAZY_READ)` to decide whether partial reads are likely efficient. Backends without `LAZY_READ` (e.g. in-memory, SQL blob) still return a valid `BinaryIO` stream — it just wraps pre-loaded data.
