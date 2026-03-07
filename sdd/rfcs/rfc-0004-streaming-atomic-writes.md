# RFC-0004: Streaming Atomic Writes

## Status

Accepted

## Summary

Add `open_atomic()` to `Backend` and `Store`, returning a context manager that
yields a writable file object. Data is written to a temporary location; on
successful exit the file is atomically promoted to its final path. On failure
the temporary artifact is cleaned up and the target path is never modified.
This eliminates the memory-buffering requirement of `write_atomic()` for
multi-GB workloads (Parquet exports, log rotation, report generation).

## Motivation

`write_atomic(path, content)` accepts `WritableContent = BinaryIO | bytes`.
Even the `BinaryIO` variant requires the caller to have the complete content
available as a seekable stream before the call — there is no way to
incrementally produce content and have the backend handle atomicity.

Real-world data-lake workflows produce large files incrementally:

```python
# Current: caller must buffer everything
buf = io.BytesIO()
pq.write_table(table, buf)          # entire table in memory
store.write_atomic("out.parquet", buf.getvalue(), overwrite=True)
```

For a 2 GB Parquet file this requires 2 GB+ of Python heap. The desired API:

```python
# Proposed: streaming, constant memory
with store.open_atomic("out.parquet", overwrite=True) as f:
    pq.write_table(table, f)        # PyArrow writes directly to f
```

The context manager owns the temp-path lifecycle: on `__exit__(None)` it
promotes the temp file; on `__exit__(exc)` it deletes the temp file. The
caller never sees the temporary artifact.

### Prior art inside the codebase

`ext.arrow._StoreSink` already implements a write-buffer-then-flush pattern
using `SpooledTemporaryFile`. However it always calls `Store.write()` (not
`write_atomic()`) on close, so it provides no atomicity guarantee. It also
unconditionally uses `overwrite=True`, ignoring the caller's intent.
`open_atomic()` formalises and generalises this pattern at the backend level
where temp-path strategies can be backend-native.

## Proposal

### 1. New abstract method on `Backend`

```python
# src/remote_store/_backend.py

@abc.abstractmethod
@contextlib.contextmanager
def open_atomic(
    self, path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]:
    """Yield a writable file object backed by a temporary location.

    On successful exit the temp file is atomically promoted to *path*.
    On exception the temp file is removed and *path* is untouched.

    :raises AlreadyExists: If *path* exists and *overwrite* is ``False``.
    :raises CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
    """
```

The method is `@contextmanager` so backends return `Iterator[BinaryIO]`
(a `Generator`). Callers use it as `with backend.open_atomic(...) as f:`.

### 2. New public method on `Store`

```python
# src/remote_store/_store.py

@contextlib.contextmanager
def open_atomic(
    self, path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]:
    """Open a file for streaming atomic writing.

    Yields a writable file object. Content written to it is staged in a
    backend-specific temporary location. On successful context exit the
    file is atomically promoted to *path*. On exception the temporary
    artifact is removed and *path* is never modified.

    :param path: Store-relative key for the target file.
    :param overwrite: If ``False``, raise if the file already exists.
    :raises AlreadyExists: If *path* exists and *overwrite* is ``False``.
    :raises CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
    :raises InvalidPath: If *path* is empty.
    """
    _bk = self._backend.name
    log.debug(
        "open_atomic path=%r overwrite=%r", path, overwrite,
        extra={"op": "open_atomic", "path": path, "backend": _bk},
    )
    self._backend.capabilities.require(Capability.ATOMIC_WRITE, backend=_bk)
    with self._backend.open_atomic(
        self._require_file_path(path), overwrite=overwrite
    ) as f:
        yield f
    log.info(
        "open_atomic complete path=%r", path,
        extra={"op": "open_atomic", "path": path, "backend": _bk},
    )
```

### 3. Per-backend temp-path strategies

#### LocalBackend

Write to `tempfile.mkstemp(dir=parent)`, `os.replace()` on success,
`os.unlink()` on failure. Identical to the existing `write_atomic()` strategy.

```python
@contextlib.contextmanager
def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
    full = self._resolve(path)
    if not overwrite and full.exists():
        raise AlreadyExists(...)
    full.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(full.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            yield f
        os.replace(tmp_path, str(full))
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

#### SFTPBackend

Write to `.~tmp.<name>.<random>` in the same directory, `posix_rename()` on
success (with `rename()` fallback), `remove()` on failure. Matches existing
`write_atomic()`.

```python
@contextlib.contextmanager
def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
    with self._errors(path):
        sftp_path = self._sftp_path(path)
        if not overwrite:
            # existence check (same as write_atomic)
            ...
        self._ensure_parent_dirs(sftp_path)
        tmp_path = self._make_tmp_path(sftp_path)
        try:
            with self._sftp.file(tmp_path, "w") as f:
                yield f
            # rename (same posix_rename + fallback as write_atomic)
            self._atomic_rename(tmp_path, sftp_path, overwrite)
        except Exception:
            with contextlib.suppress(Exception):
                self._sftp.remove(tmp_path)
            raise
```

Private helpers `_make_tmp_path` and `_atomic_rename` can be extracted from
the existing `write_atomic()` to share logic (DRY, not a new public surface).

#### S3Backend

S3 PUT is atomic. There is no server-side temp file concept. Buffer locally
using `SpooledTemporaryFile` (same pattern as `_StoreSink`), then upload on
close via `self.write()`.

```python
@contextlib.contextmanager
def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
    with self._errors(path):
        if not overwrite and self._fs.exists(self._s3_path(path)):
            raise AlreadyExists(...)
    buf: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
        max_size=8 * 1024 * 1024  # 8 MB before spilling to disk
    )
    try:
        yield cast("BinaryIO", buf)
        buf.seek(0)
        self.write(path, cast("BinaryIO", buf), overwrite=overwrite)
    finally:
        buf.close()
```

**Note on S3 multipart upload:** S3 supports multipart upload for files >5 MB,
which would enable true streaming without local buffering. However, multipart
upload introduces significant complexity (part tracking, abort on failure,
minimum 5 MB part size) and `s3fs` already handles multipart transparently
inside `pipe_file()` / `open("wb")`. Adding our own multipart layer is out of
scope for this RFC. If profiling shows local spill is a bottleneck, a follow-up
RFC can address S3-native streaming.

#### S3PyArrowBackend

Same `SpooledTemporaryFile` strategy as S3Backend. PyArrow's
`open_output_stream` writes synchronously and doesn't support incremental
commit, so buffering is necessary.

#### AzureBackend

- **Non-HNS (flat namespace):** Same `SpooledTemporaryFile` strategy — Azure
  Blob PUT is atomic.
- **HNS (Data Lake Storage Gen2):** Write to temp blob via DFS, then atomic
  rename. Matches the existing `write_atomic()` HNS path.

#### MemoryBackend

Buffer in `BytesIO`, commit to the internal tree on successful exit.

```python
@contextlib.contextmanager
def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
    segments = self._split_path(path)
    if not segments:
        raise InvalidPath(...)
    if not overwrite and self._find_file(segments):
        raise AlreadyExists(...)
    buf = io.BytesIO()
    yield buf
    buf.seek(0)
    self.write(path, buf.getvalue(), overwrite=overwrite)
```

### 4. Observe and OTel integration

`ext.observe.ObservedBackend` wraps `open_atomic` the same way it wraps other
methods:

```python
@contextlib.contextmanager
def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
    with self._observe_op("open_atomic", path, {"overwrite": overwrite}):
        with self._inner.open_atomic(path, overwrite=overwrite) as f:
            yield f
```

The `_OP_TO_HOOK` mapping gains `"open_atomic": "on_write"` (same hook as
`write` and `write_atomic`).

`ext.otel` gains a corresponding span via the same backend-wrapper pattern.

### 5. Proposed spec IDs

New spec `022-streaming-atomic-writes.md` with IDs.

**Capacity note (S3-010, AZ-007 scope):** S3Backend, S3PyArrowBackend, and
AzureBackend (non-HNS) buffer the entire file via `SpooledTemporaryFile`
before uploading. Files <= 8 MB are held in memory; larger files spill to
disk. For streams exceeding ~10 GB, callers should consider native multipart
methods or splitting the file. A follow-up RFC may add S3-native streaming
to eliminate this constraint.

Spec IDs:

| ID | Requirement |
|----|-------------|
| SAW-001 | `Backend.open_atomic()` is abstract, returns `Iterator[BinaryIO]` |
| SAW-002 | `Store.open_atomic()` gates on `Capability.ATOMIC_WRITE` |
| SAW-003 | On successful exit, file is atomically visible at target path |
| SAW-004 | On exception, target path is unchanged (no partial file) |
| SAW-005 | Temp artifact is cleaned up on both success and failure |
| SAW-006 | `AlreadyExists` raised if file exists and `overwrite=False` |
| SAW-007 | `InvalidPath` raised if path is empty |
| SAW-008 | LocalBackend uses `mkstemp` + `os.replace` |
| SAW-009 | SFTPBackend uses `.~tmp.*` + `posix_rename` (with fallback) |
| SAW-010 | S3Backend / S3PyArrowBackend buffer then PUT (atomic by nature) |
| SAW-011 | AzureBackend non-HNS buffers then PUT; HNS uses temp + DFS rename |
| SAW-012 | MemoryBackend buffers in `BytesIO` then commits |
| SAW-013 | Yielded file object supports `write()` and `tell()`; seekability is backend-dependent and MUST NOT be relied upon by callers |
| SAW-014 | `ext.observe` fires `on_write` hook after successful promotion |
| SAW-015 | `ext.otel` emits a span covering the full open-write-promote lifecycle |

### 6. Refactoring opportunity

With `open_atomic()` in place, `write_atomic()` can be reimplemented in terms
of it on backends where the two share identical temp-path logic (Local, SFTP):

```python
def write_atomic(self, path, content, *, overwrite=False):
    with self.open_atomic(path, overwrite=overwrite) as f:
        if isinstance(content, bytes):
            f.write(content)
        else:
            shutil.copyfileobj(content, f)
```

This is optional — it reduces duplication but adds a function-call layer. The
spec should not require this; backends may keep separate implementations if
profiling shows the overhead matters.

## Alternatives Considered

1. **Extension-only (`ext.atomic`).** Put the context manager in `ext/` rather
   than on `Store`. Rejected: atomicity is a core backend concern. The temp-path
   strategy is backend-specific (mkstemp vs `.~tmp.*` vs PUT semantics). An
   extension can't access backend internals and would have to buffer-then-call
   `write_atomic()`, defeating the purpose for backends that support true
   streaming (Local, SFTP).

2. **Generator-based protocol (no context manager).** Have `open_atomic()`
   return a special writer object with explicit `.commit()` / `.abort()`.
   Rejected: context managers are idiomatic Python for resource lifecycle. An
   explicit commit API risks forgotten `abort()` calls on error paths.
   `contextlib.contextmanager` gives us try/finally cleanup for free.

3. **S3 multipart upload.** Use S3's native multipart upload to avoid local
   buffering entirely. Rejected for this RFC: significant complexity (part
   tracking, 5 MB minimum part size, explicit abort). `s3fs` handles multipart
   internally for large `pipe_file()` calls, so the `SpooledTemporaryFile`
   approach gets multipart upload "for free" once it flushes. A follow-up RFC
   can add native multipart if profiling shows the spill-to-disk is a
   bottleneck.

4. **Add `open_write()` (non-atomic) instead.** A streaming write without
   atomicity guarantees. Rejected: the primary motivation is safely producing
   large files. A non-atomic streaming write leaves partial files on failure,
   which is the exact problem users want to avoid in data-lake workflows.
   Non-atomic streaming can be added separately if needed.

## Impact

- **Public API:** `Store.open_atomic()` added. `Backend.open_atomic()` added
  (abstract). `__all__` unchanged (Store is already exported; Backend is not in
  `__all__`).
- **Backwards compatibility:** Non-breaking. New method, no changes to existing
  methods. Third-party `Backend` subclasses will need to implement
  `open_atomic()` — this is a breaking change for external backend
  implementations, but the library is Beta and the Backend ABC is documented as
  unstable.
- **Performance:** For Local and SFTP, streaming avoids buffering the entire
  file in memory — peak memory drops from O(file_size) to O(chunk_size). For
  S3/Azure (non-HNS), memory profile is similar to `write_atomic()` with
  `SpooledTemporaryFile` providing disk spill for files > 8 MB.
- **Testing:** Spec `022-streaming-atomic-writes.md` must include tests for:
  - **Success path (SAW-003):** temp file created during write, promoted to
    target on `__exit__(None)`, temp artifact no longer exists, target
    readable with correct content.
  - **Exception path (SAW-004, SAW-005):** exception inside `with` block,
    target path unchanged (no partial file), temp artifact cleaned up.
  - **Early close (SAW-005):** caller calls `f.close()` before exiting
    context — behaviour defined (promote or raise).
  - **`AlreadyExists` guard (SAW-006):** `overwrite=False` raises when
    target exists; `overwrite=True` succeeds and replaces content.
  - **`InvalidPath` (SAW-007):** empty path raises `InvalidPath`.
  - **Per-backend temp-path validation (SAW-008/009/010/011/012):**
    - Local: `mkstemp` temp file exists in parent dir during write.
    - SFTP: `.~tmp.*` file exists on server during write, removed after.
    - S3/S3-PyArrow: `SpooledTemporaryFile` used (no server-side temp).
    - Azure non-HNS: buffered PUT; Azure HNS: temp blob + DFS rename.
    - Memory: `BytesIO` buffer, committed on success.
  - **Content correctness:** multi-chunk write, content matches after
    promotion (all 6 backends).
  - **Observe hook (SAW-014):** `on_write` fires after successful promotion,
    does not fire on exception path.
  - **OTel span (SAW-015):** span covers full open-write-promote lifecycle.
  - Integration with PyArrow `pq.write_table()` (example, not unit test).

## Open Questions

1. **Spill threshold for cloud backends.** The proposal uses 8 MB as the
   `SpooledTemporaryFile` threshold for S3/Azure. Should this be configurable?
   The `_StoreSink` in `ext.arrow` uses a configurable `write_spill_threshold`
   (default 5 MB). Using the same default and making it a backend config option
   adds complexity. Recommendation: hardcode 8 MB for now, add configurability
   if users request it.

2. **Should `open_atomic` be on `Store` or in `ext/`?** This RFC proposes
   `Store.open_atomic()` (core). The argument: atomicity is already a core
   concern (`write_atomic` is on Store), and the temp-path strategy requires
   backend internals. Counter-argument: it adds surface area to the core API.
   Recommendation: core, matching `write_atomic()`.

3. **Seekability of the yielded stream.** Should callers be able to `seek()`
   on the yielded file object? For Local/SFTP, the underlying temp file is
   seekable. For cloud backends using `SpooledTemporaryFile`, it's also
   seekable. However, seeking mid-write is an unusual pattern, and documenting
   seekability as guaranteed would constrain future backends (e.g. native
   multipart). **Resolution:** SAW-013 declares seekability as
   backend-dependent — callers MUST NOT rely on it. All current backends
   happen to yield seekable streams, but this is an implementation detail,
   not a contract. Future backends (e.g. native S3 multipart) may yield
   non-seekable streams.

## References

- Backlog: ID-026 (Streaming atomic writes)
- ADR-0008 (Extension architecture) — mentions ID-026 needs context manager protocol
- Existing implementation: `write_atomic()` on all 6 backends
- Related pattern: `ext.arrow._StoreSink` (buffer-then-flush)
- Data lake guide: `guides/data-lake-patterns.md` (references ID-026)
- Spec prefix: `SAW` (Streaming Atomic Writes)
