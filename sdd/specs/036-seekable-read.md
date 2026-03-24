# Seekable Read Specification

## Overview

Seekable read adds a `Capability.SEEKABLE_READ` flag for backends that always return seekable streams from `read()`, plus a portable `ext.seekable.seekable_read()` wrapper that guarantees seekability on any backend. Follows the three-tier pattern established in [ADR-0009](../adrs/0009-glob-three-tier-design.md) and formalized in [ADR-0016](../adrs/0016-seekable-read-three-tier-design.md).

---

## SEEK-001: Capability Declaration

**Invariant:** `Capability.SEEKABLE_READ` is an enum member. Backends whose `read()` always returns a seekable stream declare it in their `CapabilitySet`.
**Postconditions:** Local, Memory, S3, S3-PyArrow, and SFTP declare `SEEKABLE_READ`. Azure and HTTP do not.

## SEEK-002: Passthrough for Seekable Streams

**Invariant:** `seekable_read(store, path)` returns the stream from `store.read(path)` directly when `stream.seekable()` is `True`.
**Postconditions:** No wrapping, no copying. The returned object is the same stream instance.

## SEEK-003: Spool for Non-Seekable Streams

**Invariant:** When `stream.seekable()` is `False`, `seekable_read()` spools the content and returns a seekable stream. Content up to `max_memory` bytes returns a `BytesIO`; larger content spills to a temporary file on disk.
**Postconditions:** The returned stream is seekable and positioned at byte 0. Content matches the original stream exactly.

## SEEK-004: Large File Spool Spills to Disk

**Invariant:** When the streamed content exceeds `max_memory` bytes, the content spills to a temporary file on disk.
**Postconditions:** The returned stream is not a `BytesIO`. Content is preserved.

## SEEK-005: max_memory=0 Forces Disk Spool

**Invariant:** Setting `max_memory=0` causes immediate spooling to disk regardless of content size.

## SEEK-006: Error Propagation

**Invariant:** Backend errors (e.g. `NotFound`) propagate through `seekable_read()` as Store errors.
**Postconditions:** No error remapping. `NotFound` stays `NotFound`.

## SEEK-007: Stream Closure After Spooling

**Invariant:** When spooling occurs, the original stream from `store.read()` is closed after the content is fully copied.
**Postconditions:** The caller owns only the returned spool. The original stream is not leaked.

## SEEK-008: Runtime Guard for Capability Mismatch

**Invariant:** If a backend declares `SEEKABLE_READ` but `stream.seekable()` returns `False`, the extension issues a `UserWarning` and falls back to spooling.
**Postconditions:** The warning message mentions `SEEKABLE_READ`. The returned stream is still seekable.

## SEEK-009: fileno() Availability

**Invariant:** In-memory spools (`BytesIO`) do not support `fileno()`. Disk spools (temp file) do.
**Postconditions:** Callers requiring `fileno()` must set `max_memory=0` to force a disk spool.
