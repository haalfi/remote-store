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
root path raise `pyarrow.ArrowInvalid`.

### PA-006: normalize_path

**Invariant:** `normalize_path(path)` strips leading `/` and collapses
redundant separators, matching `RemotePath` normalization rules but returning
a plain `str` (not raising on empty result — returns `""` for root).

---

## File Information

### PA-007: get_file_info (paths)

**Invariant:** `get_file_info(paths)` returns a list of `pyarrow.fs.FileInfo`
objects, one per input path.

**Mapping per path:**

| Condition | `pyarrow.fs.FileInfo` result |
|---|---|
| `store.is_file(path)` | `FileType.File`, size and mtime from `store.get_file_info(path)` |
| `store.is_folder(path)` | `FileType.Directory`, size=0, mtime omitted |
| Neither exists | `FileType.NotFound` |

**Error handling:** `NotFound` from the Store is caught and mapped to
`FileType.NotFound` (not raised). Other `RemoteStoreError` subtypes propagate
as `ArrowIOError`.

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
   `False`, raise `ArrowIOError`. If `True`, return an empty list.

**Postconditions:** Paths in returned `FileInfo` objects are relative to the
Store root (not to `base_dir`), matching PyArrow's convention.

---

## Read Operations

### PA-009: open_input_stream

**Invariant:** `open_input_stream(path)` returns a `pyarrow.NativeFile` (or
Python file-like object accepted by PyArrow) for sequential reading.

**Implementation:** Delegates to `store.read(path)`, which returns a `BinaryIO`
stream. PyArrow accepts Python file objects that implement `read()`, `close()`,
and `readable()`, which `BinaryIO` satisfies.

**Error mapping:**
- `NotFound` → `FileNotFoundError` (which PyArrow translates to `ArrowIOError`)
- Other `RemoteStoreError` → `OSError`

### PA-010: open_input_file

**Invariant:** `open_input_file(path)` returns a seekable file for random access.

**Implementation:** Calls `store.read_bytes(path)` and wraps the result in
`pyarrow.BufferReader(pyarrow.py_buffer(data))`.

**Rationale:** Store's `read()` returns forward-only streams (SIO-001 does not
guarantee seekability). Random access requires materializing the full content.
`BufferReader` gives PyArrow a zero-copy seekable view over the bytes.

**Trade-off:** Materializes the entire file in memory. This is acceptable because
`open_input_file` is called by PyArrow when random access is explicitly needed
(e.g. Parquet row-group seeking). For sequential access, PyArrow uses
`open_input_stream` instead.

---

## Write Operations

### PA-011: open_output_stream

**Invariant:** `open_output_stream(path, metadata=None)` returns a writable
`NativeFile` (or Python file-like object) that flushes data to the Store on
`close()`.

**Implementation:** Returns a `_StoreSink` buffer (see PA-016) that accumulates
writes in a `BytesIO` and calls `store.write(path, buffer, overwrite=True)` on
`close()`.

**Postconditions:**
- Data is not visible in the Store until `close()` is called.
- `metadata` parameter is accepted but ignored (Store has no metadata-on-write API).
- Calling `close()` twice is safe (second call is a no-op).
- If `close()` raises, partial data is not written.

**Rationale:** Store's `write()` is a single-shot operation taking content as
input. There is no streaming-write-then-commit API, so buffering is required.
This matches the pattern used by `pyarrow.fs.FSSpecHandler`.

### PA-012: open_append_stream

**Invariant:** `open_append_stream(path, metadata=None)` raises
`NotImplementedError`.

**Rationale:** The Store API has no append operation. Backends like S3 do not
support append semantics. Raising immediately is better than silently
overwriting.

---

## Mutation Operations

### PA-013: delete_file

**Invariant:** `delete_file(path)` deletes a single file.

**Implementation:** `store.delete(path, missing_ok=False)`.

**Error mapping:** `NotFound` → `FileNotFoundError`.

### PA-014: create_dir

**Invariant:** `create_dir(path, recursive)` is a no-op.

**Rationale:** Most backends (S3, Azure non-HNS) have virtual directories that
are created implicitly when files are written. LocalBackend creates intermediate
directories on write. There is no `mkdir()` in the Store API. Silently
succeeding matches the behavior of `pyarrow.fs.FSSpecHandler` and S3FileSystem.

### PA-015: delete_dir / delete_dir_contents

**Invariant:**
- `delete_dir(path)` delegates to `store.delete_folder(path, recursive=True, missing_ok=False)`.
- `delete_dir_contents(path, missing_dir_ok=False)` deletes the contents of a
  directory but not the directory itself. Implemented as recursive delete +
  implicit directory survival (virtual directories on S3/Azure vanish with their
  last file, but that matches PyArrow's semantics for `delete_dir_contents`).
- `delete_root_dir_contents()` raises `PermissionError` to prevent accidental
  destruction of the entire Store.

**Error mapping:** `NotFound` → `FileNotFoundError` (unless `missing_dir_ok`).

### PA-017: move

**Invariant:** `move(src, dest)` delegates to `store.move(src, dest, overwrite=True)`.

**Rationale:** PyArrow's `move()` has overwrite-by-default semantics.

### PA-018: copy_file

**Invariant:** `copy_file(src, dest)` delegates to `store.copy(src, dest, overwrite=True)`.

**Rationale:** PyArrow's `copy_file()` has overwrite-by-default semantics.

---

## Internal Helpers

### PA-016: _StoreSink Buffer

**Invariant:** `_StoreSink` is an internal class that implements a writable
Python file-like object (at minimum: `write()`, `close()`, `writable()`,
`closed`, `tell()`).

**Behavior:**
1. Constructed with a Store reference and a target path.
2. `write(data)` appends data to an internal `BytesIO`.
3. `close()` calls `store.write(path, buffer.getvalue(), overwrite=True)` and
   marks the sink as closed.
4. `tell()` returns the current buffer position (bytes written so far).
5. `writable()` returns `True`.
6. Writing to a closed sink raises `ValueError`.
7. The `closed` property returns `True` after `close()`.

**Rationale:** PyArrow expects `open_output_stream` to return an object that
behaves like a writable file. The buffer-then-flush pattern is the standard
approach when the underlying storage is single-shot (see `FSSpecHandler`).

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

### PA-020: No RemoteStoreError Leakage

**Invariant:** No `RemoteStoreError` propagates to PyArrow callers. All Store
exceptions are caught and re-raised as standard Python exceptions per PA-019.
The original exception is chained with `from` for debuggability.

---

## Resource Management

### PA-021: Lifetime Model

**Invariant:** The handler does not own the Store. Callers are responsible for
closing the Store independently. Using the handler after the Store is closed
produces `OSError` (from the backend's own closed-state behavior).

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

**Minimum version:** 12.0.0. `FileSystemHandler` was introduced in PyArrow 2.0,
but 12.0 is the minimum that provides stable `FileSystemHandler` with all
abstract methods used here and is within the actively supported range.

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
