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
**Postconditions:** This is a Store-level convenience — no backend changes. Raises `UnicodeDecodeError` on decode failure with `errors="strict"`. See [028-read-text.md](028-read-text.md) (RTXT-001).

## SIO-008: Seekable Read Capability

**Invariant:** `Capability.SEEKABLE_READ` indicates that `Backend.read()` always returns a seekable stream (`stream.seekable()` is `True`).
**Postconditions:** This is a static guarantee — callers can check `store.supports(Capability.SEEKABLE_READ)` once at setup time instead of checking every stream. All backends support `Store.read_seekable()` regardless of this capability — the capability indicates zero-overhead (no spooling needed).
**See also:** [036-seekable-read.md](036-seekable-read.md), [ADR-0017](../adrs/0017-seekable-read-on-store-api.md).

## SIO-009: Lazy Read Capability

**Invariant:** `Capability.LAZY_READ` indicates that `Backend.read()` fetches data lazily on demand from the native source. Backends that load the full file contents into memory before returning a stream do **not** declare this capability.
**Postconditions:** When `Capability.LAZY_READ` is declared, the stream is connected to the native source and data is pulled as the caller reads. Reading only a small prefix of a large file is expected to avoid loading the full file, though the exact savings depend on backend-level buffering (e.g. s3fs read-ahead, TCP receive buffers). Callers can use `store.supports(Capability.LAZY_READ)` to decide whether partial reads are likely efficient. Backends without `LAZY_READ` (e.g. in-memory, SQL blob) still return a valid `BinaryIO` stream — it just wraps pre-loaded data.

## SIO-010: Releasing a Stream Whose Failure Condemned the Connection

**Invariant:** Where a backend supplies `_ErrorMappingStream` with an `is_fatal`
predicate, releasing a stream returned by that backend's `Backend.read()` does
not re-enter a connection the stream's own failure has already established is
unusable. Backends that supply no predicate release unconditionally, and this
clause makes no claim about them. Supplying one is optional by design, not an
omission each backend is expected to correct: it is worth the parameter only
where a close on a dead connection blocks, which is a property of the transport,
not of every stream. `SFTPBackend` is the only backend that supplies one.
**Postconditions:** A backend that can recognise such a failure supplies
`_ErrorMappingStream` with an `is_fatal` predicate over the raised exception.
Once it answers `True` for a mapped failure, the wrapper's `close()` skips the
inner close and marks itself closed; the caller sees an ordinary `close()`. A
backend that supplies no predicate closes unconditionally, which is the
behaviour every backend had before this clause.

**Why a predicate rather than the mapped error type.** The wrapper is shared, so
a rule derived from the classification would bind backends the symptom was never
measured on: `ReadOnlyHttpBackend._map_stream_error` maps *every* stream exception
to `BackendUnavailable`, and skipping the close there would trade a bounded wait
for an unreleased response body. Deciding by predicate keeps each backend
answering only for its own failures.

**What it buys.** On a connection whose bound is enforced by a timeout, a
synchronous close is a second round-trip that cannot complete: paramiko's
`SFTPFile.close()` issues `CMD_CLOSE` and waits for a reply that never comes, so
without this clause a caller consuming a stalled stream pays the bound twice and
sees nothing explaining the second wait — paramiko swallows the timeout raised
inside its own close, and the wrapper suppresses what reaches it. Measured on
`SFTPBackend` at a 2 s `io_timeout`, consuming part of a `read()` and then
stalling: 4.00 s before the guard and 2.00 s after.

**The handle is not leaked, but it is not released synchronously either.** It is
freed by the peer's own teardown of the dead connection, or at collection **of
the wrapper** — the skip leaves the inner handle bound, so it stays reachable for
as long as the closed stream object is held, which is later than the handle's own
collection would be. At that point paramiko's `SFTPFile.__del__` calls
`_close(async_=True)`, which sends `CMD_CLOSE` without waiting for a reply. The
clause trades a synchronous release that cannot succeed for an asynchronous one
that costs the caller nothing, and a caller retaining closed streams retains the
dead connections with them.

**The limit of the mechanism.** The guard is armed by an exception *reaching*
`_fail`, so anything that stops one arriving defeats it — whether the transport
discarded the failure, or raised something outside the `(OSError, EOFError)`
tuple the mapping paths catch. Neither is a gap in a backend's predicate: what
decides is the caught tuple, not the predicate. Where a failure does not arrive,
the close re-enters the connection exactly as it would have without this clause,
and whatever the mapper would have done — invalidating a cached client, marking a
session dead — is left undone too.

Both classes are non-empty on `SFTPBackend`, which is the only backend that has
been measured: a `SEEK_END` seek for the first (SFTP-030 states it; BK-357
carries the fix), and paramiko's `SSHException` / `SFTPError` for the second,
which additionally escape unmapped in breach of BE-021 (BK-358).

**See also:** SFTP-030 in [009-sftp-backend.md](009-sftp-backend.md), the bound
this clause completes, and where that limit is measured.
