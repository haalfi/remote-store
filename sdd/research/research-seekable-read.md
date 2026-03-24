# Research: Seekable Read

**Date:** 2026-03-24
**Scope:** Seekability of `Store.read()` streams, a new `SEEKABLE_READ`
capability, and a portable `ext.seekable` extension.

---

## 1. Problem Statement

`Store.read()` returns `BinaryIO` but spec SIO-001 explicitly does not
guarantee seekability. Whether the stream is seekable depends on the backend:

| Backend | Seekable? | Inner type |
|---------|-----------|------------|
| Local | Yes | `open()` file handle |
| Memory | Yes | `BufferedReader(BytesIO)` |
| S3 PyArrow | Yes | `_PyArrowBinaryIO` (C++ filesystem) |
| SFTP | Yes | paramiko `SFTPFile` (with `seek()` quirk) |
| S3 (s3fs) | No | HTTP-based streaming handle |
| Azure | No | Forward-only chunk iterator |
| HTTP | No | Response body stream |

The recommended workaround today is:

```python
seekable = io.BytesIO(store.read_bytes("report.csv"))
```

This appears in examples and guides as the standard pattern. The problem:
**it defeats streaming entirely.** The full file is loaded into memory before
the caller can process a single byte. For large files this is a memory bomb,
and for backends that already return seekable streams it's unnecessary copying.

Users shouldn't need to know backend internals to write correct code. The
current situation forces them into either:

1. **Hope the stream is seekable** — breaks silently when switching backends.
2. **Always use `read_bytes() + BytesIO`** — works everywhere, wastes memory
   everywhere.

Neither is acceptable for a library that promises backend independence.

---

## 2. Goals

1. Make seekability a **queryable capability** so callers and extensions can
   branch on it at runtime.
2. Provide a **portable seekable read** that works across all backends —
   optimized when the backend already returns seekable streams, with a
   streaming-friendly fallback (spool to temp file) when it doesn't.
3. Follow the **glob three-tier pattern** (ADR-0009): native → Store API →
   portable extension.

---

## 3. Design: Three-Tier Seekable Read

### Tier 1: Capability Declaration

Add `Capability.SEEKABLE_READ` to the enum. Backends that always return
seekable streams from `read()` declare this capability:

| Backend | Declares `SEEKABLE_READ`? | Reason |
|---------|---------------------------|--------|
| Local | Yes | OS file handles are seekable |
| Memory | Yes | BytesIO is seekable |
| S3 PyArrow | Yes | PyArrow C++ filesystem is seekable |
| SFTP | Yes | paramiko SFTPFile supports seek/tell |
| S3 (s3fs) | No | HTTP-based, forward-only |
| Azure | No | Forward-only chunk adapter |
| HTTP | No | Response body, forward-only |

User code can query: `store.supports(Capability.SEEKABLE_READ)`.

This costs nothing — it's a single enum member and one extra value in the
capability sets of 4 backends. No new methods, no behavior change.

### Tier 2: Store-Level Contract Clarification

No new Store method needed at this tier. The existing `Store.read()` already
returns `BinaryIO`, and `BinaryIO.seekable()` already tells the caller whether
the stream supports seeking. The capability flag adds a **static** guarantee
("all streams from this store are seekable") on top of the per-stream
**dynamic** check.

The distinction matters: a caller that needs seekability can check the
capability once at setup time rather than handling the non-seekable case on
every read.

### Tier 3: Extension — `ext.seekable`

A new extension module `remote_store.ext.seekable` with a single public
function:

```python
def seekable_read(
    store: Store,
    path: str,
    *,
    max_memory: int = 8 * 1024 * 1024,  # 8 MB, matches atomic write default
) -> BinaryIO:
    """Return a seekable stream for *path*.

    If the store declares ``SEEKABLE_READ``, delegates directly to
    ``store.read()`` — zero overhead.

    Otherwise, spools the stream into a ``SpooledTemporaryFile``:
    content up to *max_memory* bytes stays in RAM, beyond that spills
    to a temporary file on disk. The returned stream is always seekable
    and positioned at byte 0.
    """
```

**Algorithm:**

```
if store.supports(Capability.SEEKABLE_READ):
    return store.read(path)           # already seekable, zero-copy

stream = store.read(path)
spool = SpooledTemporaryFile(max_size=max_memory)
try:
    shutil.copyfileobj(stream, spool)
finally:
    stream.close()
spool.seek(0)
return spool
```

**Key properties:**

- **Streaming-friendly fallback.** `SpooledTemporaryFile` stays in memory for
  small files (≤8 MB default) and spills to disk for large ones. This avoids
  the memory bomb of `read_bytes() + BytesIO` while still providing
  seekability.
- **Zero overhead on seekable backends.** When the capability is declared, no
  copying happens at all.
- **Caller doesn't need to know the backend.** The extension handles the
  branching.
- **`max_memory` is tunable.** Callers who know their files are small can raise
  it (or set it to `math.inf` for pure in-memory). Callers with tight memory
  budgets can lower it to 0 (always spool to disk).

---

## 4. Alternatives Considered

### A. `read(path, seekable=True)` Parameter on Store

Adding a parameter to the core `read()` method.

**Pros:** Single call site, no import needed.
**Cons:**
- Pollutes the core API with an optimization concern.
- Requires all backends and all ProxyStore subclasses to handle the parameter.
- Breaks the clean `Backend.read(path) -> BinaryIO` contract.
- The spooling behavior (temp file, memory threshold) would need configuration
  on the Store or Backend, not just per-call.

**Verdict:** Rejected. Extensions are the right place for optional behavior
that wraps the core API.

### B. `read_seekable()` Method on Store

A new method alongside `read()` and `read_bytes()`.

**Pros:** Discoverable, no extension import.
**Cons:**
- Adds surface area to the core Store (every ProxyStore must forward it).
- The spooling behavior still needs configuration.
- Conflates "what the backend can do" with "how the caller wants to consume."

**Verdict:** Rejected for the same reasons as A. The glob pattern (capability +
extension) is proven and keeps the core lean.

### C. Always Wrap Non-Seekable Backends Transparently

Make `Store.read()` always return seekable streams by wrapping internally.

**Pros:** Zero API changes, "just works."
**Cons:**
- Hides significant cost (temp file creation, full content copy) behind an
  innocent-looking `read()` call.
- Breaks streaming use cases where the caller only wants forward reads.
- Violates the principle that `read()` returns the backend's natural stream.

**Verdict:** Rejected. Silent spooling is a footgun.

### D. Do Nothing — Keep `read_bytes() + BytesIO` Pattern

**Pros:** Already documented, no code changes.
**Cons:** Memory bomb for large files. Forces users to understand backend
internals. Defeats the purpose of backend abstraction.

**Verdict:** Insufficient. The extension is low-cost and solves a real problem.

---

## 5. Comparison with Glob Pattern

| Aspect | Glob | Seekable Read |
|--------|------|---------------|
| Capability | `Capability.GLOB` | `Capability.SEEKABLE_READ` |
| Native (Tier 2) | `Store.glob(pattern)` | `Store.read(path)` (when seekable) |
| Portable (Tier 3) | `ext.glob.glob_files()` | `ext.seekable.seekable_read()` |
| Fallback mechanism | `list_files()` + client regex | `read()` + `SpooledTemporaryFile` |
| Backend optimization | Prefix extraction | Zero-copy passthrough |
| Module dependencies | None (pure Python) | None (pure Python, stdlib only) |

The parallel is clean. Both follow the same "declare capability, provide
portable wrapper" pattern.

---

## 6. Impact Assessment

### Files Changed (Capability)

| File | Change |
|------|--------|
| `src/remote_store/_capabilities.py` | Add `SEEKABLE_READ` enum member |
| `src/remote_store/backends/_local.py` | Add to capability set |
| `src/remote_store/backends/_memory.py` | Add to capability set |
| `src/remote_store/backends/_s3_pyarrow.py` | Add to capability set |
| `src/remote_store/backends/_sftp.py` | Add to capability set |
| `sdd/specs/006-streaming-io.md` | Add SIO-008 for capability |
| `sdd/specs/003-backend-adapter-contract.md` | Update capability table |

### Files Added (Extension)

| File | Purpose |
|------|---------|
| `src/remote_store/ext/seekable.py` | Extension module |
| `tests/test_ext_seekable.py` | Unit tests |
| `sdd/specs/036-seekable-read.md` | Spec |

### Files Updated (Docs, Examples)

| File | Change |
|------|--------|
| `src/remote_store/ext/__init__.py` | Re-export `seekable_read` |
| `src/remote_store/__init__.py` | Re-export from top-level |
| `examples/backends/azure_backend.py` | Replace `BytesIO` workaround |
| `docs-src/api/extensions.md` | Add seekable section |
| `CHANGELOG.md` | New capability + extension |

### Ripple Check (per CLAUDE-REFERENCE.md)

- **Capabilities changed** → update capability table in spec 003, backend
  tests that assert capability sets, `test_capabilities.py`.
- **New extension** → `ext/__init__.py` exports, `__init__.py` re-export,
  API doc coverage (`test_api_coverage.py`).
- **Spec added** → backlog entry, cross-references.

---

## 7. Edge Cases

### SFTP `seek()` Returning `None`

`_ErrorMappingStream` already handles this (falls back to `tell()`). Since
SFTP declares `SEEKABLE_READ`, the extension will pass through the stream
directly. The existing workaround handles the quirk transparently.

### S3 PyArrow Not Wrapped in BufferedReader

S3 PyArrow returns `_ErrorMappingStream(_PyArrowBinaryIO(...))` — a
`RawIOBase`, not `BufferedIOBase`. It's still seekable. The extension returns
it as-is. Callers who want buffered reads can wrap in `BufferedReader`
themselves, but that's orthogonal to seekability.

### Dynamic Seekability Mismatch

A backend could theoretically return a non-seekable stream even if it declares
`SEEKABLE_READ`. This would be a backend bug (violating its own capability
declaration). The extension trusts the capability flag. For defense-in-depth,
the extension could check `stream.seekable()` at runtime and fall back to
spooling — but this adds complexity for a scenario that shouldn't happen.

**Recommendation:** Trust the capability. Add a debug assertion in tests
that all backends declaring `SEEKABLE_READ` actually return seekable streams.

### `SpooledTemporaryFile` on Windows

`SpooledTemporaryFile` uses `tempfile.mkstemp()` internally when spilling to
disk. On Windows, the temp file is created in `%TEMP%` (or `TMP`). This
works fine — the project already uses `SpooledTemporaryFile` for atomic writes
on all platforms.

### Stream Ownership

When the extension spools, it closes the original stream and returns the spool.
The caller owns the spool and must close it. When the extension passes through
(seekable backend), the caller owns the original stream. Either way: caller
closes what they get. Same contract as `Store.read()`.

---

## 8. Test Strategy

1. **Capability declaration tests** — Assert that Local, Memory, S3 PyArrow,
   and SFTP declare `SEEKABLE_READ`. Assert that S3, Azure, and HTTP do not.
2. **Passthrough test** — `seekable_read()` on a seekable backend returns the
   same stream object (no wrapping).
3. **Spool test** — `seekable_read()` on a non-seekable backend returns a
   seekable `SpooledTemporaryFile` with correct content.
4. **Large file spool test** — Content exceeding `max_memory` spills to disk
   (check `SpooledTemporaryFile._rolled`).
5. **`max_memory=0` test** — Always spools to disk.
6. **Error propagation** — Backend errors during spooling propagate as Store
   errors (not raw OS errors).
7. **Stream closure** — Original stream is closed after spooling.

---

## 9. Effort Estimate

| Phase | Effort |
|-------|--------|
| Capability enum + backend declarations | Small (mechanical) |
| Extension implementation | Small (~50 lines) |
| Spec (036-seekable-read.md) | Medium |
| Tests | Medium (~100 lines) |
| Docs + examples update | Small |
| **Total** | **~1 day** |

This is a small, well-scoped change with clear precedent (glob pattern).

---

## 10. Recommendation

**Proceed with implementation.** The three-tier approach (capability flag →
Store.read() passthrough → ext.seekable fallback) solves the real problem
(backend-independent seekability) without polluting the core API or hiding
costs. The implementation is small, the pattern is proven, and the
`SpooledTemporaryFile` mechanism is already battle-tested in this codebase.

**Backlog item:** `ID-084 — Seekable Read Capability + Extension`
