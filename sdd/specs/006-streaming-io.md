# Streaming I/O Specification

## Overview

All I/O in `remote_store` is streaming-first. Read operations return `BinaryIO` streams by default. Write operations accept both `bytes` and `BinaryIO`. This spec defines the streaming semantics and cancellation behavior.

## SIO-001: Streaming Reads

**Invariant:** `Backend.read(path)` returns a `BinaryIO` stream positioned at the start.
**Postconditions:** The caller is responsible for consuming and closing the stream. The returned stream is not guaranteed to be seekable. Seekability is a backend-level property (e.g. local files are seekable, HTTP-based streams typically are not), not a Store API contract. Callers that require seekability should use `read_bytes()` and wrap in `BytesIO`.
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
