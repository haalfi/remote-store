# PyArrow FileSystem Adapter Specification

## Overview

`StoreFileSystemHandler` is a `pyarrow.fs.FileSystemHandler` implementation
that wraps any `Store` into a `pyarrow.fs.PyFileSystem`. This is the inverse
of `unwrap()`: instead of reaching *into* a backend's native handle, this wraps
any Store *into* a PyArrow filesystem.

A single adapter unlocks seamless interop with the entire PyArrow-based data
ecosystem: PyArrow datasets, Pandas, Polars, DuckDB, PyIceberg, and Delta Lake
all accept `pyarrow.fs.FileSystem` objects for I/O.

**Module:** `src/remote_store/ext/arrow.py`
**Dependencies:** `pyarrow >= 12.0.0` (optional extra: `pip install "remote-store[arrow]"`)
**RFC:** `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`
**Related:** ADR-0003 (fsspec is implementation detail), spec 011 (S3-PyArrow backend)

---

## Prior Art

This spec draws lessons from existing `FileSystemHandler` implementations and
ecosystem usage patterns. We aim to match or exceed their performance while
avoiding their known issues.

### PyArrow FSSpecHandler

PyArrow's built-in adapter from fsspec filesystems to `FileSystemHandler`
(source: `python/pyarrow/fs.py` in [apache/arrow](https://github.com/apache/arrow)).

**Patterns adopted:**
- `PythonFile` wrapping for I/O bridge between Python file objects and Arrow's
  C++ `NativeFile` types.
- `metadata` parameter accepted but ignored on `open_output_stream` (fsspec
  has no metadata-on-write API; neither does Store).
- `create_dir` swallows `FileExistsError` for idempotent behavior.

**Issues we address:**
- `open_input_stream` and `open_input_file` are *identical* — both return
  `PythonFile(fs.open(path, "rb"), mode="r")`, which creates a
  `PyReadableFile` (C++ `CRandomAccessFile`). Every `ReadAt` call acquires a
  mutex *and* the GIL, then does `Seek` + `Read` through Python dispatch. This
  serializes concurrent column-chunk reads in Parquet workloads. Our PA-010
  uses `BufferReader` instead, which operates at C++ speed with no GIL.
- `get_file_info` makes one RPC per path (N+1 problem). We inherit this
  limitation from the Store API but document it explicitly (PA-007).
- `get_file_info_selector` makes two validation RPCs (`isdir` + `exists`)
  *before* the listing call. Our PA-008 avoids these extra calls by catching
  `NotFound` from the listing itself.
- `delete_dir_contents` makes N+1 RPCs — lists, then calls `isdir()`/`isfile()`
  for each entry before deleting. Our PA-015 delegates to
  `store.delete_folder(recursive=True)` in a single call.
- `normalize_path` is a no-op. Our PA-006 performs actual normalization
  (leading-slash strip, separator collapse).
- Error handling is minimal — most backend exceptions propagate raw to
  callers. Our PA-019/PA-020 provide complete error translation.

### pyarrowfs-adlgen2

Third-party Azure Data Lake Gen2 adapter by Robin Kaveland
([kaaveland/pyarrowfs-adlgen2](https://github.com/kaaveland/pyarrowfs-adlgen2)).

**Patterns adopted:**
- `normalize_path` strips leading and trailing slashes — same approach in our
  PA-006.
- `DatalakeGen2File` class serves as a writable buffer with `close()`-on-flush
  semantics — similar to our `_StoreSink` (PA-016).
- Guard against flushing a 0-byte buffer on `close()` — we adopt this
  defensive check in PA-016 (the library hit this as a real bug, issue #13).
- `delete_root_dir_contents` rejects root deletion — same safety in our PA-015.

**Issues we address:**
- `open_input_file` is identical to `open_input_stream` — same `PythonFile`
  wrapping, same GIL overhead. Our PA-010 uses `BufferReader` for true
  zero-copy random access.
- `get_file_info` lists the *parent directory* to find a single file. Our
  PA-007 calls `store.is_file()` / `store.get_file_info()` directly.
- No file-size caching — `seek(SEEK_END)` makes a network call every time.
  Our `BufferReader` approach in PA-010 sidesteps this entirely since the full
  content is materialized.
- Error handling lets Azure SDK exceptions propagate raw in most paths. Our
  PA-019/PA-020 catch all `RemoteStoreError` subtypes.
- `copy_file` downloads then re-uploads (no server-side copy). Our PA-018
  delegates to `store.copy()`, which uses server-side copy where available.

### object-store-python (ArrowFileSystemHandler)

Rust-backed `FileSystemHandler` via PyO3 by roeap
([roeap/object-store-python](https://github.com/roeap/object-store-python)),
using the same `object_store` crate that powers DataFusion, Polars, and
InfluxDB.

**Key insight:** By implementing the handler in Rust, it avoids the `PythonFile`
overhead entirely — I/O methods return data through native Arrow FFI without
GIL contention. This represents the performance ceiling for FileSystemHandler
implementations. Our PA-010 (`BufferReader`) approach achieves similar benefits
for the random-access read hot path without requiring a compiled extension.

### Ecosystem Hot Paths

Analysis of how downstream tools call `FileSystem` methods, compiled from
PyIceberg, DuckDB, Polars, and PyArrow dataset internals:

| Method | When called | Performance criticality |
|---|---|---|
| `open_input_file` | Parquet/ORC reading (random access to row groups, column chunks) | **Highest** — every Parquet read |
| `get_file_info_selector` | Dataset discovery, partition walking | **High** — recursive, many RPCs |
| `open_output_stream` | Writing data files (Parquet, Arrow IPC) | Medium — once per file |
| `get_file_info` (paths) | Existence checks, metadata lookups | Medium — small batches |
| `open_input_stream` | Sequential formats (CSV, line-delimited JSON) | Low — less common |
| `move` / `copy_file` | Commit protocols (Delta Lake, Iceberg) | Low — once per commit |

This prioritization drives our design: PA-010 (`open_input_file`) gets the most
optimization attention, PA-008 (`get_file_info_selector`) avoids unnecessary
RPCs, and PA-009 (`open_input_stream`) uses a lighter-weight approach.

---

## Construction

### PA-001: Constructor

**Invariant:** `StoreFileSystemHandler` is constructed with a single `Store`
instance.

```python
StoreFileSystemHandler(store: Store)
```

**Postconditions:**
- The handler holds a reference to the Store; it does not copy or wrap it.
- No I/O occurs during construction.
- The Store's lifetime is managed externally — the handler does not own it.

### PA-002: Convenience Factory

**Invariant:** A module-level `pyarrow_fs(store)` factory creates a ready-to-use
`PyFileSystem`:

```python
def pyarrow_fs(store: Store) -> pyarrow.fs.PyFileSystem:
    return pyarrow.fs.PyFileSystem(StoreFileSystemHandler(store))
```

**Rationale:** Users should not need to know about `FileSystemHandler` or
`PyFileSystem` internals. One call, one usable filesystem.

### PA-003: Type String

**Invariant:** The handler's `get_type_name()` returns `"remote-store"`.

**Rationale:** PyArrow uses this for serialization and display. A stable, unique
name avoids collisions with built-in handlers.

---

## Path Model

### PA-004: Path Convention

**Invariant:** All paths exchanged with PyArrow use forward slashes and no
leading slash. The handler strips any leading `/` from paths received from
PyArrow before passing them to the Store.

**Rationale:** PyArrow normalizes paths with a leading `/` in some code paths
(e.g. `get_file_info`). The Store's `RemotePath` rejects leading slashes, so
the handler must strip them. Store-relative paths are already `/`-separated and
have no leading slash, so they can be returned to PyArrow as-is.

### PA-005: Root Path is Empty String

**Invariant:** The PyArrow path `""` or `"/"` maps to the Store's root
(empty string `""`). File-targeted operations (read, write, delete) on the
root path raise `FileNotFoundError`.

### PA-006: normalize_path

**Invariant:** `normalize_path(path)` strips leading and trailing `/` and
collapses redundant separators, matching `RemotePath` normalization rules but
returning a plain `str` (not raising on empty result — returns `""` for root).

**Rationale:** FSSpecHandler's `normalize_path` is a no-op, which causes subtle
path-matching failures. pyarrowfs-adlgen2 strips leading/trailing slashes.
We adopt the latter approach, extended with separator collapse.

---

## File Information

### PA-007: get_file_info (paths)

**Invariant:** `get_file_info(paths)` returns a list of `pyarrow.fs.FileInfo`
objects, one per input path.

**Mapping per path:**

| Condition | `pyarrow.fs.FileInfo` result |
|---|---|
| `store.is_file(path)` | `FileType.File`, size and mtime from `store.get_file_info(path)` |
| `store.is_folder(path)` | `FileType.Directory`, size omitted |
| Neither exists | `FileType.NotFound` |

**Error handling:** `NotFound` from the Store is caught and mapped to
`FileType.NotFound` (not raised). Other `RemoteStoreError` subtypes are
translated per PA-019.

**Performance note:** This method makes at least one backend call per path.
PyArrow's `dataset()` discovery may call this for many paths. Both FSSpecHandler
and pyarrowfs-adlgen2 have the same per-path cost; the Store API does not offer
batch info. This is acceptable because `get_file_info_selector` (PA-008) is the
primary listing path for discovery, and `get_file_info` is typically called for
a small number of known paths.

### PA-008: get_file_info_selector

**Invariant:** `get_file_info_selector(selector)` lists files and folders under
`selector.base_dir`.

**Mapping:**

```
selector.base_dir     → store path (after leading-slash strip)
selector.recursive    → list_files(path, recursive=True/False)
selector.allow_not_found → if True, return [] for missing dir; else raise
```

**Behavior:**
1. List files via `store.list_files(base_dir, recursive=selector.recursive)`.
   Each `FileInfo` maps to a `pyarrow.fs.FileInfo` with `FileType.File`.
2. List immediate subfolders via `store.list_folders(base_dir)`. Each maps to
   a `pyarrow.fs.FileInfo` with `FileType.Directory`.
3. If `selector.recursive` is `True`, subfolders discovered at each level are
   included as `FileType.Directory` entries. (The recursive `list_files` already
   traverses into them; this step ensures the directories themselves appear.)
4. If the base directory does not exist and `selector.allow_not_found` is
   `False`, raise `FileNotFoundError`. If `True`, return an empty list.

**Postconditions:** Paths in returned `FileInfo` objects are relative to the
Store root (not to `base_dir`), matching PyArrow's convention.

**Performance rationale:** FSSpecHandler makes two validation RPCs (`isdir` +
`exists`) before listing. We skip these — if the directory doesn't exist,
`list_files` raises `NotFound`, which we catch and handle per
`allow_not_found`. This saves two round-trips per listing call. For data-lake
workloads (Iceberg table scans, partitioned datasets), `get_file_info_selector`
is the hot path — every saved RPC matters.

---

## Read Operations

### PA-009: open_input_stream

**Invariant:** `open_input_stream(path)` returns a `pyarrow.NativeFile` for
sequential reading.

**Implementation:** Delegates to `store.read(path)`, wraps the returned
`BinaryIO` in `pyarrow.PythonFile(stream, mode="r")`.

**Rationale:** `PythonFile` bridges a Python file object to Arrow's C++
`NativeFile` interface. Each `Read()` call crosses the GIL boundary, but for
sequential workloads (CSV streaming, line-delimited JSON) this is acceptable
and avoids materializing the full file.

**Error mapping:** `NotFound` → `FileNotFoundError`. Other errors per PA-019.

### PA-010: open_input_file

**Invariant:** `open_input_file(path)` returns a seekable `NativeFile` for
random access reading.

**Implementation:** Calls `store.read_bytes(path)` and wraps the result in
`pyarrow.BufferReader(pyarrow.py_buffer(data))`.

**Rationale:** This is the key performance differentiator from prior art.

Both FSSpecHandler and pyarrowfs-adlgen2 return `PythonFile` for
`open_input_file`, which creates a `PyReadableFile` (C++ `CRandomAccessFile`).
Every `ReadAt` call acquires a C++ mutex, enters `SafeCallIntoPython` to grab
the GIL, then dispatches `Seek()` + `Read()` back through Python. This means:

- Concurrent `ReadAt` calls (Parquet column-chunk reads) are **serialized** by
  the mutex.
- Each `ReadAt` makes **two** Python-to-C++ round-trips (seek + read).
- `GetSize()` makes **three** seeks (save pos → seek end → tell → seek back).

`BufferReader` wraps a C++ `Buffer` and implements `CRandomAccessFile` entirely
in C++. `ReadAt` is a pointer + offset operation — no mutex, no GIL, no
Python calls. `GetSize()` returns the buffer length directly.

**Trade-off:** Materializes the entire file in memory. This is acceptable
because:
1. `open_input_file` is called when random access is explicitly needed (Parquet
   row-group seeking, ORC stripe access). These formats are designed around
   random access into materialized column chunks.
2. PyArrow's own `S3FileSystem` and `GcsFileSystem` also materialize ranges
   into buffers for `ReadAt`.
3. For sequential access, PyArrow uses `open_input_stream` instead (PA-009),
   which streams without materialization.

---

## Write Operations

### PA-011: open_output_stream

**Invariant:** `open_output_stream(path, metadata=None)` returns a writable
`NativeFile` that flushes data to the Store on `close()`.

**Implementation:** Returns `pyarrow.PythonFile(_StoreSink(store, path), mode="w")`.
The `_StoreSink` (PA-016) accumulates writes in a `BytesIO` and calls
`store.write(path, buffer, overwrite=True)` on `close()`.

**Postconditions:**
- Data is not visible in the Store until `close()` is called.
- `metadata` parameter is accepted but ignored (Store has no metadata-on-write
  API). Both FSSpecHandler and pyarrowfs-adlgen2 also ignore or partially
  handle this parameter.
- Calling `close()` twice is safe (second call is a no-op).
- If `close()` raises, partial data is not written.

**Rationale:** Store's `write()` is a single-shot operation taking content as
input. There is no streaming-write-then-commit API, so buffering is required.
FSSpecHandler delegates buffering to the underlying fsspec backend (which may
or may not buffer — s3fs buffers entire files in memory). pyarrowfs-adlgen2
uses chunked uploads via Azure's append+flush protocol. Our approach is
explicit: the full content is buffered and written in one `store.write()` call.

**Memory note:** The entire output is buffered in memory before writing. For
very large files, this may be significant. This is a consequence of the Store
API design (single-shot writes) and is consistent with how most fsspec backends
behave behind FSSpecHandler. A future enhancement could add a spill-to-tempfile
option for writes exceeding a configurable threshold.

### PA-012: open_append_stream

**Invariant:** `open_append_stream(path, metadata=None)` raises
`NotImplementedError`.

**Rationale:** The Store API has no append operation. Backends like S3 do not
support append semantics natively. pyarrowfs-adlgen2 can implement append
because Azure Data Lake Gen2's HNS provides an `append_data` API — this is
specific to ADLS, not generalizable across backends. Raising immediately is
better than silently overwriting.

**Ecosystem context:** `open_append_stream` was deprecated on `FileSystem` in
PyArrow 6.0 with the note *"several filesystems don't support this
functionality and it will be later removed."* As of PyArrow 23.x it still
exists on `FileSystemHandler` but most implementations raise
`NotImplementedError`. Our choice aligns with the ecosystem direction.

---

## Mutation Operations

### PA-013: delete_file

**Invariant:** `delete_file(path)` deletes a single file.

**Implementation:** `store.delete(path, missing_ok=False)`.

**Error mapping:** `NotFound` → `FileNotFoundError`.

**Note:** FSSpecHandler makes an extra `exists()` check before deleting. We
skip this — `store.delete(missing_ok=False)` already raises `NotFound` for
missing files. One call instead of two.

### PA-014: create_dir

**Invariant:** `create_dir(path, recursive)` is a no-op that always succeeds.

**Rationale:** Most backends (S3, Azure non-HNS) have virtual directories that
are created implicitly when files are written. LocalBackend creates
intermediate directories on write. There is no `mkdir()` in the Store API.
Silently succeeding matches the behavior of PyArrow's built-in `S3FileSystem`
and `GcsFileSystem`. FSSpecHandler delegates to `fs.mkdir()` and swallows
`FileExistsError`, achieving the same idempotent effect with an extra call.

### PA-015: delete_dir / delete_dir_contents

**Invariant:**
- `delete_dir(path)` delegates to
  `store.delete_folder(path, recursive=True, missing_ok=False)`.
- `delete_dir_contents(path, missing_dir_ok=False)` lists and deletes all
  files in the directory, then deletes subfolders recursively. If the directory
  does not exist and `missing_dir_ok` is `False`, raises `FileNotFoundError`.
- `delete_root_dir_contents()` raises `PermissionError` to prevent accidental
  destruction of the entire Store.

**Error mapping:** `NotFound` → `FileNotFoundError` (unless `missing_dir_ok`).

**Performance rationale:** FSSpecHandler's `delete_dir_contents` makes N+1
RPCs — it lists the directory, then calls `isdir()`/`isfile()` for each entry
before deleting. Our `delete_dir` delegates to `store.delete_folder` in a
single call, letting the backend handle bulk deletion natively.

### PA-017: move

**Invariant:** `move(src, dest)` delegates to
`store.move(src, dest, overwrite=True)`.

**Rationale:** PyArrow's `move()` has overwrite-by-default semantics.

### PA-018: copy_file

**Invariant:** `copy_file(src, dest)` delegates to
`store.copy(src, dest, overwrite=True)`.

**Rationale:** PyArrow's `copy_file()` has overwrite-by-default semantics.
Unlike pyarrowfs-adlgen2 which downloads and re-uploads (no server-side copy),
`store.copy()` delegates to the backend which uses server-side copy where
available (S3 CopyObject, Azure copy-from-URL).

---

## Internal Helpers

### PA-016: _StoreSink Buffer

**Invariant:** `_StoreSink` is an `io.RawIOBase` subclass that implements a
writable Python file-like object.

**Behavior:**
1. Constructed with a Store reference and a target path.
2. `write(data)` appends data to an internal `BytesIO`. Returns the number of
   bytes written.
3. `close()` calls `store.write(path, buffer.getvalue(), overwrite=True)` if
   the buffer is non-empty, then marks the sink as closed. If the buffer is
   empty, writes an empty `bytes` object (creating an empty file, matching
   PyArrow's semantics).
4. `tell()` returns the current buffer position (bytes written so far).
5. `writable()` returns `True`.
6. `readable()` returns `False`.
7. Writing to a closed sink raises `ValueError`.
8. The `closed` property (inherited from `IOBase`) returns `True` after
   `close()`.
9. Calling `close()` twice is safe (second call is a no-op, per `IOBase`
   contract).

**Defensive checks (learned from pyarrowfs-adlgen2 issue #13):**
- `close()` guards against flushing when the internal buffer is in an
  unexpected state. pyarrowfs-adlgen2 hit a bug where a large write that
  exactly filled the buffer triggered an auto-flush, then `close()` tried
  to flush an empty 0-byte buffer which Azure rejected. Our design avoids
  auto-flush entirely (single flush on `close()`), but we still guard the
  close path defensively.

---

## Error Mapping

### PA-019: Error Translation

**Invariant:** All `RemoteStoreError` subtypes are translated to standard Python
exceptions that PyArrow understands:

| `RemoteStoreError` subtype | Python exception |
|---|---|
| `NotFound` | `FileNotFoundError` |
| `AlreadyExists` | `FileExistsError` |
| `PermissionDenied` | `PermissionError` |
| `InvalidPath` | `ValueError` |
| `CapabilityNotSupported` | `NotImplementedError` |
| `DirectoryNotEmpty` | `OSError` |
| `BackendUnavailable` | `OSError` |
| `RemoteStoreError` (base) | `OSError` |

**Rationale:** PyArrow catches `OSError` and its subclasses (`FileNotFoundError`,
`PermissionError`, etc.) and translates them into `ArrowIOError` for C++ callers.
Using standard exceptions ensures clean interop without PyArrow-specific imports
in the error path.

**Quality note:** This is a deliberate improvement over prior art. FSSpecHandler
has minimal error handling — most backend exceptions propagate raw.
pyarrowfs-adlgen2 only catches HTTP 404 in a few paths; other Azure SDK
exceptions (403, 409, 429, 500) propagate unwrapped. Our handler catches *all*
`RemoteStoreError` subtypes at every method boundary, ensuring callers always
see standard Python exceptions.

### PA-020: No RemoteStoreError Leakage

**Invariant:** No `RemoteStoreError` propagates to PyArrow callers. All Store
exceptions are caught and re-raised as standard Python exceptions per PA-019.
The original exception is chained with `from` for debuggability.

**Implementation:** Every handler method wraps its Store calls in a
`try/except RemoteStoreError` block. This is implemented as a shared context
manager or decorator to avoid repeating the mapping table in every method.

---

## Resource Management

### PA-021: Lifetime Model

**Invariant:** The handler does not own the Store. Callers are responsible for
closing the Store independently. Using the handler after the Store is closed
produces `OSError` (from the backend's own closed-state behavior, translated
per PA-019).

**Rationale:** PyArrow filesystems do not have a `close()` lifecycle. Tying
Store closure to garbage collection would be unreliable. Explicit external
management is clearer and consistent with how the Store context manager works.

---

## Public API Surface

### PA-022: Exports

**Invariant:** The `ext.arrow` module exports exactly two names:

```python
__all__ = ["StoreFileSystemHandler", "pyarrow_fs"]
```

Both are also importable from the top-level `remote_store` package when PyArrow
is installed. When PyArrow is not installed, importing `ext.arrow` raises
`ImportError` with a helpful message.

### PA-023: Optional Dependency

**Invariant:** PyArrow is declared as an optional extra in `pyproject.toml`:

```toml
[project.optional-dependencies]
arrow = ["pyarrow>=12.0.0"]
```

**Minimum version:** 12.0.0. `FileSystemHandler` was introduced in PyArrow
2.0.0. However, PyArrow 5.0 changed the `open_output_stream` signature to add
the `metadata` parameter (this broke pyarrowfs-adlgen2, issue #11). PyArrow
12.0 is the minimum actively supported release that includes all `metadata`
parameter signatures, stable `FileSystemHandler` semantics, and `PythonFile`
behavior we depend on.

---

## Testing Strategy

### PA-024: Unit Tests

**Invariant:** Unit tests exercise every `FileSystemHandler` method through a
`PyFileSystem` backed by a `LocalBackend` Store. Tests verify:

- Round-trip: write via PyArrow, read via Store (and vice versa)
- File info: type, size, mtime mapping
- Selector: recursive/non-recursive, allow_not_found
- Error paths: missing file, missing directory, closed sink double-write
- `_StoreSink`: write, tell, close, double-close, write-after-close
- Path normalization: leading slashes, redundant separators, root path

### PA-025: Integration Tests

**Invariant:** Integration tests verify end-to-end interop with downstream
libraries:

- `pyarrow.parquet.write_table()` / `read_table()` round-trip
- `pyarrow.dataset.dataset()` discovery of partitioned data
- `pandas.read_parquet()` / `to_parquet()` with `filesystem=` parameter

These tests use `LocalBackend` to avoid infrastructure dependencies.

### PA-026: Conformance Across Backends

**Invariant:** The adapter works with any backend that passes the Store
conformance suite. No backend-specific code paths exist in the handler.

**Rationale:** The handler delegates entirely to the Store API, which is
backend-agnostic by design. Backend-specific behavior (virtual directories,
atomic writes, etc.) is already handled by each backend's implementation.

---

## References

### External implementations studied

- **PyArrow FSSpecHandler** — `python/pyarrow/fs.py` in
  [apache/arrow](https://github.com/apache/arrow). Canonical reference for
  `FileSystemHandler` implementation patterns. Studied for I/O wrapping
  (`PythonFile`), error handling, and listing strategies.
- **pyarrowfs-adlgen2** — [kaaveland/pyarrowfs-adlgen2](https://github.com/kaaveland/pyarrowfs-adlgen2).
  Real-world Azure Data Lake Gen2 adapter; source of defensive checks and
  lessons on write buffering (issues #11, #13, #25).
- **object-store-python** — [roeap/object-store-python](https://github.com/roeap/object-store-python).
  Rust-backed `FileSystemHandler` via PyO3; demonstrates the performance
  ceiling when GIL/PythonFile overhead is eliminated.

### PyArrow documentation

- [FileSystemHandler API](https://arrow.apache.org/docs/python/generated/pyarrow.fs.FileSystemHandler.html)
- [FSSpecHandler API](https://arrow.apache.org/docs/python/generated/pyarrow.fs.FSSpecHandler.html)
- [Filesystem interface guide](https://arrow.apache.org/docs/python/filesystems.html)
- [Memory and IO — NativeFile vs PythonFile](https://arrow.apache.org/docs/python/memory.html)

### Relevant PyArrow issues

- [#36983](https://github.com/apache/arrow/issues/36983) — `get_file_info`
  behavior difference between native S3 and FSSpecHandler
- [#41357](https://github.com/apache/arrow/issues/41357) — proposed
  `use_cache` for `get_file_info` (15 min on 3k SAMBA files)
- [#33618](https://github.com/apache/arrow/issues/33618) — `FileSelector`
  10x slower than `std::filesystem` due to per-entry `stat()`
- [#47559](https://github.com/apache/arrow/issues/47559) —
  `FSSpecHandler.delete_root_dir_contents` missing argument bug

### Project references

- **ADR-0003** — `sdd/adrs/0003-fsspec-is-implementation-detail.md`. Establishes
  that fsspec is an implementation detail; this adapter provides a *new* public
  extension point without exposing fsspec.
- **RFC-0002** — `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`. Original
  proposal and motivation.
