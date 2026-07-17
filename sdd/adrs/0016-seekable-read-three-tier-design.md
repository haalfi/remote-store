# ADR-0016: Seekable Read — Three-Tier Design

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

`Store.read()` returns `BinaryIO` but spec SIO-001 explicitly does not
guarantee seekability. Whether the returned stream is seekable depends
on the backend: Local, Memory, SFTP, and both S3 backends return
seekable streams; Azure and HTTP do not.

The recommended workaround is `io.BytesIO(store.read_bytes("file"))`,
which loads the entire file into memory before the caller can process
a single byte. This defeats streaming for large files and is
unnecessary for backends that already return seekable streams.

Users shouldn't need to know backend internals to write correct code.
The current situation forces them into either hoping the stream is
seekable (breaks when switching backends) or always materializing to
memory (wastes resources everywhere).

ADR-0009 (Glob — Three-Tier Design) established a proven pattern for
this class of problem: capability flag → native Store method →
portable extension fallback.

## Decision

<!-- adr:decision -->
Apply the ADR-0009 three-tier pattern to seekable reads:
<!-- /adr:decision -->

### Tier 1: `Capability.SEEKABLE_READ`

A new `Capability` enum member. Backends that always return seekable
streams from `read()` declare it. Users query with
`store.supports(Capability.SEEKABLE_READ)`.

Backends declaring `SEEKABLE_READ`: Local, Memory, S3, S3-PyArrow,
SFTP. Backends that do not: Azure (forward-only chunk iterator),
HTTP (response body stream).

### Tier 2: `Store.read()` — existing contract

No new Store method. The existing `Store.read()` already returns
`BinaryIO`, and `stream.seekable()` already tells the caller whether
the stream supports seeking. The capability flag adds a **static**
guarantee alongside the per-stream dynamic check.

### Tier 3: `ext.seekable.seekable_read()` — portable fallback

```python
from remote_store.ext.seekable import seekable_read

with seekable_read(store, "report.csv") as f:
    f.seek(0)  # works on any backend
```

Algorithm:

1. Call `store.read(path)`.
2. If `stream.seekable()` is `True`, return as-is (zero-copy).
3. Otherwise, spool into `SpooledTemporaryFile(max_size=max_memory)`:
   content ≤ `max_memory` (default 8 MB) stays in RAM, beyond that
   spills to a temporary file on disk.
4. Return the spool, positioned at byte 0.

If a backend declares `SEEKABLE_READ` but returns a non-seekable
stream, the extension issues a warning and falls back to spooling.

## Consequences

- **Follows ADR-0009 precedent.** Same three-tier escalation pattern,
  same extension architecture (ADR-0008), same capability declaration
  model (spec 003).
- **No core API changes.** No new Store methods, no new Backend
  abstract methods. ProxyStore doesn't need updates.
- **Streaming-friendly fallback.** `SpooledTemporaryFile` avoids the
  memory bomb of `read_bytes() + BytesIO` while providing seekability.
- **Zero overhead on seekable backends.** The passthrough path adds
  only a `seekable()` call.
- **`fileno()` limitation.** `SpooledTemporaryFile.fileno()` raises
  when content is still in memory. Documented in the extension's
  docstring and spec.
- **Pure Python, stdlib only.** No new dependencies.
