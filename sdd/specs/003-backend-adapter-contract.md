# Backend Adapter Contract Specification

## Overview

The `Backend` ABC defines the contract all storage backends must implement. It is the most critical spec in the system — every operation, error condition, and capability is defined here. Backends declare capabilities via a `Capability` enum and `CapabilitySet`.

---

## Capabilities

### CAP-001: Capability Enum Members

**Invariant:** `Capability` is an enum with members: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`, `SEEKABLE_READ`.

### CAP-002: CapabilitySet Construction

**Invariant:** `CapabilitySet` is constructed from a `set[Capability]`.
**Example:**
```python
cs = CapabilitySet({Capability.READ, Capability.WRITE})
```

### CAP-003: supports() Method

**Invariant:** `supports(cap)` returns `True` if `cap` is in the set, `False` otherwise.

### CAP-004: require() Method

**Invariant:** `require(cap)` raises `CapabilityNotSupported` if `cap` is not in the set.
**Raises:** `CapabilityNotSupported` with `capability` attribute set to the capability name.

### CAP-005: Iteration and Membership

**Invariant:** `CapabilitySet` supports `in` operator and `__iter__`.
**Example:**
```python
assert Capability.READ in cs
for cap in cs:
    print(cap)
```

### CAP-006: Immutability

**Invariant:** `CapabilitySet` is immutable after construction. The internal set cannot be modified.

---

## Backend ABC

### BE-001: Abstract Base Class

**Invariant:** `Backend` is an ABC. Subclasses must implement all abstract methods.

### BE-002: Name Property

**Invariant:** `name` property returns a unique identifier string for the backend type (e.g. `"local"`, `"s3"`).

### BE-003: Capabilities Property

**Invariant:** `capabilities` property returns a `CapabilitySet` declaring all supported operations.

### BE-004: exists()

**Invariant:** `exists(path)` returns `bool`. Returns `False` for missing paths — never raises `NotFound`.

### BE-005: is_file() / is_folder()

**Invariant:** `is_file(path)` returns `True` only if `path` is a file. `is_folder(path)` returns `True` only if `path` is a folder. Both return `False` for non-existent paths.

### BE-006: read()

**Invariant:** `read(path)` returns a `BinaryIO` stream for the file content.
**Raises:** `NotFound` if the file does not exist.
**See also:** [006-streaming-io.md](006-streaming-io.md)

### BE-007: read_bytes()

**Invariant:** `read_bytes(path)` returns the full file content as `bytes`.
**Raises:** `NotFound` if the file does not exist.

### BE-008: write()

**Invariant:** `write(path, content, overwrite=False)` creates or overwrites a file.
**Preconditions:** `content` is `bytes` or `BinaryIO`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.

### BE-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.

### BE-010: write_atomic()

**Invariant:** `write_atomic(path, content, overwrite=False)` writes via a temporary file + atomic rename.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.
**See also:** [007-atomic-writes.md](007-atomic-writes.md)

### BE-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.

### BE-012: delete()

**Invariant:** `delete(path, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`.
**Postconditions:** If `missing_ok=True`, no error for missing files.

### BE-013: delete_folder()

**Invariant:** `delete_folder(path, recursive=False, missing_ok=False)` removes a folder.
**Raises:** `NotFound` if the folder is missing and `missing_ok=False`. Fails if folder is non-empty and `recursive=False`.

### BE-014: list_files()

**Invariant:** `list_files(path, recursive=False)` returns `Iterator[FileInfo]`.
**Postconditions:** Returns only files, not folders. If `recursive=True`, includes files in all subdirectories.

### BE-015: list_folders()

**Invariant:** `list_folders(path)` returns `Iterator[FolderEntry]` of immediate subfolders.
Each `FolderEntry` has `.name` (folder name) and `.path` (backend-relative `RemotePath`).

### BE-016: get_file_info()

**Invariant:** `get_file_info(path)` returns `FileInfo`.
**Raises:** `NotFound` if the file does not exist.

### BE-017: get_folder_info()

**Invariant:** `get_folder_info(path)` returns `FolderInfo`.
**Raises:** `NotFound` if the folder does not exist.

### BE-018: move()

**Invariant:** `move(src, dst, overwrite=False)` renames/moves a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### BE-019: copy()

**Invariant:** `copy(src, dst, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### BE-020: close()

**Invariant:** `close()` is optional (default no-op). Called for resource cleanup.

### BE-021: Error Mapping

**Invariant:** Backend-native exceptions never leak. All exceptions are mapped to `remote_store` error types.

### BE-022: unwrap()

**Invariant:** `unwrap(type_hint)` returns the native backend handle if it matches the requested type.
**Raises:** `CapabilityNotSupported` if the backend cannot provide the requested type.
**Rationale:** See [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md).

### BE-023: to_key()

**Invariant:** `to_key(native_path)` converts a backend-native or absolute path to a backend-relative key by stripping the backend's own root/prefix. The default implementation is the identity function.
**Postconditions:** Pure, deterministic, total (never raises). If the input path does not start with the backend's root, it is returned unchanged.
**See also:** [010-native-path-resolution.md](010-native-path-resolution.md) (NPR-003 through NPR-009), [ADR-0005](../adrs/0005-native-path-resolution.md).

### BE-025: native_path()

**Invariant:** `native_path(path)` converts a backend-relative key to the backend-native path. The inverse of `to_key()`: `backend.to_key(backend.native_path(key)) == key`. The default implementation is the identity function — backends with a native root **must** override.
**Postconditions:** Pure, deterministic, total (never raises). The returned path is usable with the native handle from `unwrap()`.
**Overrides:** `LocalBackend` (prepends root dir), `S3Backend` (prepends bucket), `S3PyArrowBackend` (prepends bucket), `SFTPBackend` (prepends base_path), `AzureBackend` (prepends container).
**Example:** `S3PyArrowBackend(bucket="lake").native_path("data/file.parquet")` returns `"lake/data/file.parquet"`.
**See also:** [001-store-api.md](001-store-api.md) (STORE-015), [014-pyarrow-filesystem-adapter.md](014-pyarrow-filesystem-adapter.md) (PA-010 Tier 1).

### BE-026: iter_children()

**Invariant:** `iter_children(path)` returns `Iterator[FileInfo | FolderEntry]` — files as `FileInfo`, folders as `FolderEntry`. Concrete method with a default implementation that chains `list_files(path)` and `list_folders(path)`. Backends that can fetch both in a single I/O call override for efficiency.
**Postconditions:** Non-recursive (immediate children only). Non-existent paths yield nothing.
**See also:** [027-iter-children.md](027-iter-children.md) (ITER-004, ITER-005).

### BE-024: glob()

**Invariant:** `glob(pattern)` matches files against a glob pattern. Non-abstract — the default implementation raises `CapabilityNotSupported`. Backends with native glob support override this and declare `Capability.GLOB`.
**Postconditions:** Returns only files (not folders). Paths in returned `FileInfo` objects are backend-relative (same convention as `list_files`).
**Raises:** `CapabilityNotSupported` if the backend lacks `GLOB`.
**See also:** [018-glob.md](018-glob.md) (GLOB-003 through GLOB-005), [ADR-0009](../adrs/0009-glob-three-tier-design.md).
