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
**Related:** ADR-0003 (fsspec is implementation detail), spec 011 (S3-PyArrow backend),
spec 001 (Store API), spec 004 (path model), spec 005 (error model)

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
  uses a tiered strategy to avoid this where possible.
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
- Guard against flushing a 0-byte buffer on `close()` — PA-016 avoids this
  class of bugs entirely by using a single flush on `close()` with no
  auto-flush (the library hit this as a real bug, issue #13).
- `delete_root_dir_contents` rejects root deletion — same safety in our PA-015.

**Issues we address:**
- `open_input_file` is identical to `open_input_stream` — same `PythonFile`
  wrapping, same GIL overhead. Our PA-010 uses a tiered strategy that avoids
  `PythonFile` entirely for backends with native PyArrow support.
- `get_file_info` lists the *parent directory* to find a single file. Our
  PA-007 calls `store.is_file()` / `store.get_file_info()` directly.
- No file-size caching — `seek(SEEK_END)` makes a network call every time.
  Our tiered strategy in PA-010 avoids this for small files (materialized) and
  for native backends (C++ handles it internally).
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
implementations. Our PA-010 Tier 1 (backend-native fast path) achieves similar
benefits for backends that expose a native PyArrow filesystem.

### PyArrow Native Filesystems (S3, GCS)

PyArrow's built-in `S3FileSystem` and `GcsFileSystem` implement
`CRandomAccessFile` entirely in C++. Critically, `ReadAt(offset, length)`
issues an HTTP Range request (`GET` with `Range: bytes=start-end`) and
materializes only the **requested byte range** (~64 KB–1 MB), not the entire
file. On top of this, PyArrow's Parquet reader supports **I/O coalescing**
([ARROW-8562](https://github.com/apache/arrow/pull/7022)) via `pre_buffer=True`:
small nearby ranges are coalesced into fewer, larger requests, yielding 4–6x
speedups on S3 ([benchmarks](https://github.com/apache/arrow/issues/36765)).

This is the performance target for our Tier 1 fast path: backends with
`unwrap()` access to a native PyArrow filesystem get the full C++ range-request
+ coalescing pipeline with zero overhead.

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

**Invariant:** `StoreFileSystemHandler` is constructed with a `Store` instance
and optional tuning parameters.

```python
StoreFileSystemHandler(
    store: Store,
    materialization_threshold: int = 64 * 1024 * 1024,  # PA-010
    write_spill_threshold: int = 64 * 1024 * 1024,       # PA-011
)
```

**Parameters:**
- `store` — the `Store` to expose as a PyArrow filesystem.
- `materialization_threshold` — maximum file size (bytes) for Tier 2 full-file
  materialization in `open_input_file`. `0` disables Tier 2 (always stream);
  `sys.maxsize` always materializes. See PA-010.
- `write_spill_threshold` — maximum in-memory buffer size (bytes) for
  `_StoreSink` before spilling to disk. See PA-011 / PA-016.

**Postconditions:**
- The handler holds a reference to the Store; it does not copy or wrap it.
- At construction time, the handler probes the Store for a native PyArrow
  filesystem via `store.unwrap(pyarrow.fs.FileSystem)`. If a native FS is
  available, the handler caches both the native FS reference and a
  path-translation closure for Tier 1 fast-path reads (PA-010). If `unwrap()`
  raises `TypeError` or returns a non-PyArrow type, Tier 1 is disabled.
  This pre-capture means Tier 1 never accesses private Store internals at
  call time.
- No other I/O occurs during construction.
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
   File paths are store-relative (as returned by `list_files`).
2. If `selector.recursive` is `False`, list immediate subfolders via
   `store.list_folders(base_dir)`. `list_folders` returns bare folder **names**
   (not paths), so the handler constructs the store-relative path by joining:
   `f"{base_dir}/{name}"` (or just `name` if `base_dir` is root `""`).
   Each entry maps to a `pyarrow.fs.FileInfo` with `FileType.Directory`,
   `mtime=None` (folder metadata is not available from `list_folders`).
3. If `selector.recursive` is `True`, **extract directory entries from file
   paths** rather than walking the folder tree: collect all unique parent
   prefixes from the file paths returned in step 1 (excluding `base_dir`
   itself) and emit a `FileType.Directory` entry for each. This avoids the
   N+1 RPC problem of recursive `list_folders` calls.
4. If the base directory does not exist and `selector.allow_not_found` is
   `False`, raise `FileNotFoundError`. If `True`, return an empty list.

**Rationale for step 3:** Two strategies exist for recursive directory entries:
- **Tree walk** — call `list_folders` at each level. O(depth × breadth) RPCs,
  the same N+1 problem criticized in FSSpecHandler.
- **Extract from file paths** — use `list_files(recursive=True)` and
  deduplicate parent paths. O(1) listing RPCs + O(n) client-side string work.

We use the second strategy. The file listing already traverses the full tree;
extracting directory prefixes from those paths is O(n) string processing with
no additional RPCs. The resulting directory entries are "synthetic" (derived
from file paths, not from a directory listing call), but this matches PyArrow's
own convention — object stores have no real directories, only key prefixes.

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
and avoids materializing the full file. Sequential reads make a small number
of large `Read()` calls (buffer-sized chunks), so GIL overhead is negligible
relative to I/O time.

**Error mapping:** `NotFound` → `FileNotFoundError`. Other errors per PA-019.

### PA-010: open_input_file

**Invariant:** `open_input_file(path)` returns a seekable `NativeFile` for
random access reading.

**Implementation:** A tiered strategy that selects the best approach based on
backend capabilities and file size:

#### Tier 1: Backend-native fast path (zero overhead)

If the Store's backend exposes a native PyArrow filesystem via the public
`Store.unwrap()` API (e.g., `S3PyArrowBackend`), the handler uses it for reads
instead of going through the Store abstraction:

```python
# At construction time (PA-001):
try:
    native_fs = store.unwrap(pyarrow.fs.FileSystem)
    # Pre-build path translator: store-relative key → native FS path
    self._native_fs = native_fs
    self._native_path = store.native_path  # returns backend-absolute path
except TypeError:
    self._native_fs = None

# At read time:
def open_input_file(self, path):
    if self._native_fs is not None:
        return self._native_fs.open_input_file(self._native_path(path))
    # ... fall through to Tier 2/3
```

**Encapsulation:** Tier 1 uses only public Store APIs — `store.unwrap()` for
the native filesystem handle and `store.native_path()` for path translation.
It never accesses `store._backend` or other private attributes. The
`store.unwrap(type_hint)` method delegates to `backend.unwrap()` through the
Store's public surface; `store.native_path(key)` converts a store-relative
key to the full backend-native path (prepending `root_path` and any
backend-specific prefix). Both methods are proposed additions to the Store
public API (spec 001 amendment, tracked separately).

**Path conversion:** Store-relative paths (e.g., `'file.parquet'`) cannot be
passed directly to the native filesystem — they lack the `root_path` prefix
and backend-specific path components (bucket, base path, etc.).
`store.native_path(key)` reconstructs the full native path:
- Store key: `'file.parquet'`
- With `root_path='data'`: `'data/file.parquet'`
- With S3 bucket `my-bucket`: `'my-bucket/data/file.parquet'`

This is the inverse of `store.to_key()` (spec STORE-011).

This gives the full C++ `ReadAt` → HTTP Range request → I/O coalescing
pipeline with zero GIL overhead and zero extra memory. The `S3PyArrowBackend`
already has `unwrap()` in this codebase.

**Design trade-off:** Tier 1 intentionally bypasses the Store abstraction for
the read hot path. This means no Store-level capability checking (Store gates
`read()` behind `Capability.READ`), no `RemotePath` validation, and no
Store-level logging/hooks if those are ever added. This is a conscious
performance trade-off — all non-read operations (listing, writing, deleting)
still go through the Store API. The capability check is redundant for Tier 1
because `unwrap()` succeeding already proves the backend is functional.

#### Tier 2: BufferReader for small files (≤ threshold)

For files at or below a configurable threshold (default: 64 MB), materialize
the full file and wrap in `BufferReader`:

```python
MATERIALIZATION_THRESHOLD = 64 * 1024 * 1024  # 64 MB

info = self._store.get_file_info(path)
if info.size <= MATERIALIZATION_THRESHOLD:
    data = self._store.read_bytes(path)
    return pa.BufferReader(pa.py_buffer(data))
```

`BufferReader` wraps a C++ `Buffer` and implements `CRandomAccessFile` entirely
in C++. `ReadAt` is a pointer + offset operation — no mutex, no GIL, no Python
calls. `GetSize()` returns the buffer length directly.

This is acceptable for small files because the memory cost is bounded and the
full-file download is comparable to a few range requests.

#### Tier 3: PythonFile for large files (> threshold)

For files exceeding the threshold, use `PythonFile` wrapping of the Store's
read stream:

```python
stream = self._store.read(path)
return pa.PythonFile(stream, mode="r")
```

**Seekability caveat:** `PythonFile` with `mode="r"` creates a
`PyReadableFile` which requires the underlying stream to support `seek()`.
`store.read()` returns seekable streams for `LocalBackend` (file handles) and
`S3PyArrowBackend` (PyArrow `RandomAccessFile`), but HTTP-based streams from
`S3Backend` and `AzureBackend` are **not seekable**. For non-seekable backends
without native PyArrow support, Tier 2 (full materialization) is used as the
fallback regardless of file size, and a `logging.warning` is emitted noting
the memory cost.

**Summary:**

| Condition | Strategy | Memory | GIL? | Network |
|---|---|---|---|---|
| `store.unwrap()` → PyArrow FS | **Tier 1**: native `open_input_file` | ~range size | No | Range requests |
| File ≤ 64 MB | **Tier 2**: `read_bytes()` → `BufferReader` | Full file | No | Full download |
| File > 64 MB, seekable stream | **Tier 3**: `read()` → `PythonFile` | ~range size | Yes | Streaming |
| File > 64 MB, non-seekable stream | **Tier 2 fallback** (with warning) | Full file | No | Full download |

**Rationale:** This tiered approach addresses the core tension between memory
usage and GIL overhead:

- **Tier 1** is the ideal path: zero overhead, range requests, I/O coalescing.
  It applies to `S3PyArrowBackend` today and any future backend that exposes
  a native PyArrow filesystem.
- **Tier 2** trades memory for speed. For files under 64 MB the memory cost
  is bounded and acceptable. `BufferReader`'s zero-GIL `ReadAt` is strictly
  better than `PythonFile` when the file fits comfortably in memory.
- **Tier 3** trades GIL overhead for bounded memory. For large files, the GIL
  cost is bounded by the actual bytes read (not the file size) — reading 20 MB
  of column chunks from a 2 GB file with GIL overhead is vastly better than
  downloading 2 GB into memory. Parquet typically does ~10–50 `ReadAt` calls
  per file (one per column chunk per row group); that's 10–50 GIL acquires,
  which is negligible compared to network I/O.

**Configuration:** The materialization threshold is set via the constructor
parameter `materialization_threshold` (see PA-001 for full signature). The
value is an `int` (bytes). Sentinel values: `0` disables Tier 2 (always stream
for non-native backends); `sys.maxsize` always materializes regardless of file
size.

**Error mapping:** `NotFound` → `FileNotFoundError`. Other errors per PA-019.

---

## Write Operations

### PA-011: open_output_stream

**Invariant:** `open_output_stream(path, metadata=None)` returns a writable
`NativeFile` that flushes data to the Store on `close()`.

**Implementation:** Returns `pyarrow.PythonFile(_StoreSink(store, path), mode="w")`.
The `_StoreSink` (PA-016) accumulates writes in memory up to a configurable
threshold, then spills to a temporary file on disk if exceeded.

**Buffering strategy:**

| Write size | Buffer location | Memory cost |
|---|---|---|
| ≤ `spill_threshold` (default 64 MB) | `BytesIO` (in-memory) | Exact write size |
| > `spill_threshold` | `tempfile.SpooledTemporaryFile` | `spill_threshold` + disk |

The `_StoreSink` uses `tempfile.SpooledTemporaryFile(max_size=spill_threshold)`
which transparently promotes from `BytesIO` to a disk-backed temporary file
when the threshold is exceeded. On `close()`, the full content is passed to
`store.write(path, buffer, overwrite=True)`.

**Postconditions:**
- Data is not visible in the Store until `close()` is called.
- `metadata` parameter is accepted but ignored (Store has no metadata-on-write
  API). Both FSSpecHandler and pyarrowfs-adlgen2 also ignore or partially
  handle this parameter.
- Calling `close()` twice is safe (second call is a no-op).
- If `close()` raises, partial data is not written.

**Rationale:** Store's `write()` is a single-shot operation taking content as
input. There is no streaming-write-then-commit API, so buffering is required.
The spill-to-tempfile approach bounds memory usage for data-lake workloads
where Parquet writes routinely reach 100+ MB, while keeping small writes
entirely in memory for speed.

**Configuration:** The spill threshold is set via the constructor parameter
`write_spill_threshold` (see PA-001 for full signature).

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
- `delete_dir(path)` — if `path` is empty or root (`""`), raises
  `NotImplementedError` (same safety as `delete_root_dir_contents`). PyArrow
  may call `delete_dir("")` expecting root deletion; we refuse this explicitly
  rather than letting it fall through to `Store.delete_folder()` which raises
  `InvalidPath` → `ValueError` (per PA-019). `NotImplementedError` is a
  clearer signal to PyArrow callers. For non-root paths, delegates to
  `store.delete_folder(path, recursive=True, missing_ok=False)`.
- `delete_dir_contents(path, missing_dir_ok=False)` lists and deletes all
  files in the directory, then deletes subfolders recursively. If the directory
  does not exist and `missing_dir_ok` is `False`, raises `FileNotFoundError`.
- `delete_root_dir_contents()` raises `NotImplementedError` to prevent
  accidental destruction of the entire Store.

**Error mapping:** `NotFound` → `FileNotFoundError` (unless `missing_dir_ok`).

**Rationale for `NotImplementedError`:** This is a deliberate safety guard, not
a permissions issue. Using `NotImplementedError` is consistent with PA-012
(`open_append_stream`) and clearly communicates that this operation is
intentionally unsupported, rather than misleading users into thinking they need
different credentials.

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
writable Python file-like object with bounded memory usage.

**Behavior:**
1. Constructed with a Store reference, a target path, and a spill threshold.
2. Internal buffer is a `tempfile.SpooledTemporaryFile(max_size=spill_threshold)`.
   Writes up to `spill_threshold` bytes stay in memory; beyond that, the
   buffer transparently spills to a temporary file on disk.
3. `write(data)` appends data to the buffer. Returns the number of bytes
   written.
4. `close()` seeks the buffer to position 0, reads all content, and passes
   it to `store.write(path, content, overwrite=True)`. This always writes,
   even if content is empty — creating an empty file matches PyArrow's
   `open_output_stream` + immediate `close()` semantics. Calling `close()`
   on an already-closed sink is a no-op (per `IOBase` contract).
5. `tell()` returns the current buffer position (bytes written so far).
6. `writable()` returns `True`.
7. `readable()` returns `False`.
8. Writing to a closed sink raises `ValueError`.
9. The `closed` property (inherited from `IOBase`) returns `True` after
   `close()`.
10. Calling `close()` twice is safe (second call is a no-op, per `IOBase`
    contract).

**Defensive checks (learned from pyarrowfs-adlgen2 issue #13):**
- pyarrowfs-adlgen2 hit a bug where a large write that exactly filled the
  buffer triggered an auto-flush, then `close()` tried to flush a second
  time against Azure which rejected the empty write. Our design avoids
  auto-flush entirely — the single write to the Store happens on `close()`,
  and `SpooledTemporaryFile` handles the in-memory-to-disk promotion
  transparently without triggering flushes.

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

**Capability gating:** The Store gates operations behind
`capabilities.require()` — e.g., `store.copy()` raises `CapabilityNotSupported`
if the backend lacks `Capability.COPY`. Per the mapping table above,
`CapabilityNotSupported` → `NotImplementedError`. PyArrow callers interpret
`NotImplementedError` as "this filesystem does not support this operation,"
which is the correct semantic. This means capability gating works correctly
through the error mapping without any special-case handling in the adapter.

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
- `_StoreSink`: write, tell, close, double-close, write-after-close, spill
  to tempfile above threshold
- Path normalization: leading slashes, redundant separators, root path
- Tiered read strategy: verify Tier 1 dispatch for native backends, Tier 2
  for small files, Tier 3 for large seekable files

### PA-025: Integration Tests

**Invariant:** Integration tests verify end-to-end interop with downstream
libraries:

- `pyarrow.parquet.write_table()` / `read_table()` round-trip
- `pyarrow.dataset.dataset()` discovery of partitioned data
- `pandas.read_parquet()` / `to_parquet()` with `filesystem=` parameter

These tests use `LocalBackend` to avoid infrastructure dependencies.

### PA-026: Conformance Across Backends

**Invariant:** The adapter works with any backend that passes the Store
conformance suite. No backend-specific code paths exist in the handler
**except** the Tier 1 `unwrap()` check in PA-010, which is opt-in and
gracefully falls through to Tier 2/3 for backends without native PyArrow
support.

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
- [ARROW-8562](https://github.com/apache/arrow/pull/7022) — I/O coalescing
  using S3 bandwidth-delay product metrics
- [#36765](https://github.com/apache/arrow/issues/36765) — `pre_buffer=True`
  benchmarks (4–6x speedups on S3)

### Project references

- **ADR-0003** — `sdd/adrs/0003-fsspec-is-implementation-detail.md`. Establishes
  that fsspec is an implementation detail; this adapter provides a *new* public
  extension point without exposing fsspec.
- **RFC-0002** — `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`. Original
  proposal and motivation.
