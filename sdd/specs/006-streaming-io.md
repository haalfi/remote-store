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
discarded the failure, or raised something outside the caught set the mapping
paths intercept. Neither is a gap in a backend's predicate: what decides is the
caught set, not the predicate. Where a failure does not arrive, the close
re-enters the connection exactly as it would have without this clause, and
whatever the mapper would have done — invalidating a cached client, marking a
session dead — is left undone too.

The first class is non-empty on `SFTPBackend`, the only backend that has been
measured: a send-side `EOFError` that `BufferedFile.read` swallows into a short
read before it reaches the wrapper at all. A `SEEK_END` seek was a second case,
and the one that cost most — the swallowed size request answered `0` rather than
merely losing a failure — until
[SIO-011](#sio-011-sizing-a-stream-for-an-end-relative-seek) moved that request
into the wrapper, where its failure has a mapping path to travel. That clause
repairs one discarding call site; it does not empty the class, which is a
property of the transport rather than of this one.

The second class was non-empty on the same backend and is not any longer:
paramiko's `SSHException` / `SFTPError` used to escape unmapped in breach of
BE-021, and defeated this guard on the way past (BK-358). They are now inside
that backend's caught set — [SIO-012](#sio-012-the-set-of-exception-shapes-a-stream-maps)
owns that, and owns what the set holds for any other site. **The class is not
closed by construction**, only empty where it has been looked at: a backend
supplying a set that misses one of its transport's shapes puts the shape back
into it, which is a defect of that supply and not of this clause.

**A supplied shape reaches `_fail` but need not arm the guard, and on SFTP it
does not.** `_is_connection_dead` deliberately excludes the `SSHException`
family (`_map_exception` gives it its own arm), so a dropped connection is
mapped, invalidates the cached client, and still closes the inner handle. That
close is free: measured **0.00 s** on a hard drop and on a half-close alike,
because paramiko's transport-reader thread tears the socket down on EOF before
`SFTPFile.close()` can issue its `CMD_CLOSE`. There is therefore nothing here to
buy, which is why `SFTPBackend.read` was left passing the predicate unchanged
when its caught set widened. Derivation: the drop and half-close relays on
BK-358's branch, paramiko 5.0.0. Contrast the stall this clause was written for,
where the socket stays open and the close does wait.

**See also:** SFTP-030 in [009-sftp-backend.md](009-sftp-backend.md), the bound
this clause completes, and where that limit is measured.

## SIO-011: Sizing a Stream for an End-Relative Seek

**Invariant:** Where a backend supplies `_ErrorMappingStream` with a
`size_probe` callable, `seek(offset, SEEK_END)` resolves the stream's size
through that callable and then delegates an absolute seek, so a failed size
request is mapped by SIO-010's machinery rather than reaching the caller as a
position. Backends that supply no probe delegate the end-relative seek to the
inner stream unchanged, and this clause makes no claim about them.
**Postconditions:** The seek returns `size + offset`. A size request that fails
raises the mapped error, arms the SIO-010 guard when the backend's `is_fatal`
agrees, and leaves the position unchanged. `SEEK_SET` and `SEEK_CUR` never call
the probe.

**Why this is a clause and not an implementation detail.** paramiko's
`SFTPFile.seek` resolves `SEEK_END` through `_get_size()`, whose whole body is
`try: return self.stat().st_size` under a bare `except: return 0`. On a stalled
channel that `stat` blocked for `io_timeout` and was then discarded, so the seek
*answered* `0` on a file of any size and raised nothing. Three consequences, and
the first is the one a caller could act on wrongly:

- The answer was wrong and indistinguishable from an empty file, so a caller
  sizing a file by seeking to its end read zero bytes and had nothing to catch.
- Nothing reached `_fail`, so SIO-010's guard stayed unarmed and the close paid
  the bound a second time.
- Nothing reached the backend's mapper, so the dead client stayed cached and the
  next operation re-entered the same channel.

Measured on `SFTPBackend` at a 2 s `io_timeout`, consuming part of a `read()`
and then stalling: **4.00 s** answering `0` on a 1 MiB file with the dead client
still cached, against **2.00 s** raising `BackendUnavailable` with the client
dropped. Derivation: the stall relay
`test_seek_to_end_on_a_stalled_channel_costs_one_bound` drives, run once as
shipped and once with `size_probe` withheld from the wrapper — which is exactly
the pre-clause delegation, so the two runs differ in that argument alone.

**Why a probe rather than a wider catch.** Nothing was raised to catch. The
inner stream's own failure was consumed before the wrapper could see it, so the
only repair is to stop delegating the request that fails.

**Why opt-in.** The probe is a round-trip, and unlike SIO-010's predicate it
runs on the success path. It also has no generic form: the wrapper holds no size
of its own, so an unconditional version would need a per-backend source anyway.
What decided it is that **paramiko is the only inner stream measured to discard
its own size failure**. The enumeration below is by *construction site* rather
than by backend, because `AzureBackend` builds the wrapper twice over two
different inner streams and a per-backend list gets it wrong — an earlier draft
attributed Azure's range reader to its `read()`, which does not use it. The six
non-SFTP sites reach `SEEK_END` by **four** routes:

- **A size captured at open, added to the offset.** `_S3RangeReader.seek`, which
  `S3Boto3Backend` builds once in `_open_range_stream` and serves to both
  `read()` and `read_seekable()`; and `_AzureRangeReader.seek`, which
  `AzureBackend` builds for `read_seekable()` alone.
- **A size held on the handle.** `S3Backend.read()` wraps an fsspec file, whose
  `AbstractBufferedFile.seek` computes `self.size + loc`.
- **Resolved inside the inner implementation.** `S3PyArrowBackend.read()` wraps
  a pyarrow `NativeFile` through `_PyArrowBinaryIO`, which passes the whence
  down and returns the resulting position.
- **Not seekable at all.** `AzureBackend.read()` wraps `_AzureBinaryIO`, and
  `ReadOnlyHttpBackend.read()` wraps whatever body its transport yields — an
  adapter over the response for the `requests` and `httpx` transports, and the
  `http.client.HTTPResponse` itself for the stdlib one. None defines `seek` or
  `seekable`, so `IOBase.seekable()` answers `False` for all three; the shared
  fact is the missing methods, not a shared base class.

None of those has a failure for a probe to repair, so probing on their behalf
would buy a round-trip per seek and nothing else — or, on the forward-only
streams, a request against something that cannot seek. `SFTPBackend.read()` is
the only site that supplies a probe.

**The probe's own failure is bounded by the same caught set as every other
path**, deliberately, and that has held through a change in what the set is. It
was written when the set was `(OSError, EOFError)` everywhere, so a
`paramiko.SFTPError` raised by the probe escaped unmapped exactly as one raised
by a read did; widening for this path alone would have made it better than the
rest with no clause saying why. [SIO-012](#sio-012-the-set-of-exception-shapes-a-stream-maps)
answered that question per construction site instead, and the probe moved with
its site rather than ahead of it (BK-358). The rule is the same either way: the
probe neither leads the set nor lags it.

**See also:** SFTP-030 in [009-sftp-backend.md](009-sftp-backend.md), where the
`SEEK_END` case was a stated exception to the bound until this clause closed it.

## SIO-012: The Set of Exception Shapes a Stream Maps

**Invariant:** `_ErrorMappingStream` maps `(OSError, EOFError)` plus whatever
additional exception types the constructing backend supplies, and a supplied type
is mapped on **every** path the wrapper intercepts — `read`, `readinto`,
`readline`, `seek` including its SIO-011 size probe, `tell`, and iteration —
identically to a base-tuple type. A backend that supplies nothing is bounded by
the base tuple alone, which is the behaviour every backend had before this clause.
**Postconditions:** A supplied type raises the mapped `RemoteStoreError` with the
original as `__cause__`, and arms SIO-010's guard exactly when the backend's
`is_fatal` says so. A type outside the resulting set propagates unmapped, on
every path, whether or not the site supplied anything.

**What this is for.** The wrapper is what BE-021's never-leak rule rests on once
a backend's `_errors()` context manager has exited, and the base tuple is not
wide enough for every transport it serves. On paramiko the ordinary mid-read drop
is outside it: `SFTPClient._read_response` catches the underlying `EOFError` and
re-raises `SSHException("Server connection dropped: ...")`, and `_read_packet`
raises `SFTPError` on a malformed one. Neither subclasses `OSError` or
`EOFError`, so both reached callers raw — while the *same drop* on `read_bytes`,
which fails inside `_errors()`, was mapped correctly. One connection, one fault,
two answers depending on which method the caller used (BK-358).

Measured on an in-process SFTP server behind a relay that closes the connection
while a reply is outstanding, paramiko 5.0.0 / CPython 3.11:

| Path | Before | After |
|---|---|---|
| `read_bytes()` | `BackendUnavailable`, client cleared | unchanged |
| `read()` stream — `read` / `readinto` / `readline` | raw `paramiko.SSHException` | `BackendUnavailable`, client cleared |
| `read()` stream — `seek(0, SEEK_END)` probe | raw `paramiko.SSHException` | `BackendUnavailable`, client cleared |

**Why per construction site rather than a wider base.** The wrapper is shared by
seven construction sites across six backends — `rg -n '_ErrorMappingStream\(' src`
is the derivation, less the class statement itself — and the evidence for
widening came from one of them. A base tuple grown to fit paramiko would change
what S3 (fsspec, boto3 and PyArrow), Azure (both its sites) and HTTP map, on no
measurement of any of them.
Keeping the widening on the site that argued for it is what lets a backend answer
for its own transport and nothing else — the same reasoning SIO-010 gives for
deciding the futile close by predicate rather than by mapped error type.

**Why not `Exception` with the mapper deciding.** It is the shortest fix and it
would map the programming errors the wrapper deliberately lets propagate —
`TypeError`, `AttributeError`, a bug in an inner stream — turning a defect into a
`RemoteStoreError` that reads like a backend fault. It would also re-introduce
the previous paragraph's problem in a stronger form, since it widens every site at
once.

**Why not convert at the source.** The HTTP transports take that route: their
adapters re-raise `httpx` / `requests` stream errors as `OSError` so the base
tuple catches them. It works there because those exceptions carry nothing the
mapper dispatches on. It would not work for SFTP, where the type *is* the
information: `SFTPError` reaches `BackendUnavailable` through
`_is_connection_dead` and `SSHException` through its own arm, and both clear the
cached client so the next operation reconnects (SFTP-010 tier 2). An
`OSError(str(exc))` carries no errno, so it would land in the generic
`RemoteStoreError` arm and lose the classification and the invalidation with it —
strictly worse than the leak it replaced.

**One backend supplies a set today.** `SFTPBackend.read()` supplies
`(paramiko.SSHException, paramiko.SFTPError)`. No other site does, and none is
expected to on principle: what belongs in a set is a shape that backend's
transport was *measured* to raise outside the base, not one a reader thinks it
might.

**See also:** SFTP-024 in [009-sftp-backend.md](009-sftp-backend.md), the
never-leak clause this mechanism carries for a caller-facing handle, and BE-021
in [003-backend-adapter-contract.md](003-backend-adapter-contract.md), which it
serves.
