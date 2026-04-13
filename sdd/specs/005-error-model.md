# Error Model Specification

## Overview

All errors raised by `remote_store` inherit from a single base class `RemoteStoreError`. Errors carry structured context attributes for programmatic handling. Backend-native exceptions are never exposed to callers.

## ERR-001: Base Error

**Invariant:** `RemoteStoreError` is the root of the error hierarchy.
**Postconditions:** Carries optional `path: str | None` and `backend: str | None` attributes.
**Example:**
```python
try:
    store.read("missing.txt")
except RemoteStoreError as e:
    print(e.path, e.backend)
```

## ERR-002: NotFound

**Invariant:** Raised when a file or folder does not exist at the given path.
**Preconditions:** Caller requests an operation on a non-existent resource.
**Postconditions:** `path` attribute is set to the requested path.
**Example:**
```python
with pytest.raises(NotFound) as exc_info:
    store.read("nonexistent.txt")
assert exc_info.value.path == "nonexistent.txt"
```

## ERR-003: AlreadyExists

**Invariant:** Raised when a target already exists and overwrite is not allowed.
**Preconditions:** Caller writes to an existing path with `overwrite=False`.
**Postconditions:** `path` attribute is set to the conflicting path.
**Example:**
```python
store.write("file.txt", b"data")
with pytest.raises(AlreadyExists):
    store.write("file.txt", b"new", overwrite=False)
```

## ERR-004: PermissionDenied

**Invariant:** Raised when access is denied by the storage backend.
**Postconditions:** `path` and `backend` attributes are set.

## ERR-005: InvalidPath

**Invariant:** Raised for malformed, unsafe, or out-of-scope paths, and for node-type mismatches at a valid path.
**Preconditions:** Either (a) the caller provides a path containing `..`, null bytes, or that normalizes to empty; or (b) the operation targets a valid path that names the wrong node type — e.g. `read()` on a directory, `delete()` on a directory, `get_file_info()` on a directory, or `move()`/`copy()` with a directory as source. In case (b) the path is well-formed; the error is about type, not syntax. See BE-021 for the canonical per-method mapping.
**Postconditions:** `path` attribute is set to the offending path.
**Example (malformed path):**
```python
with pytest.raises(InvalidPath):
    RemotePath("foo/../bar")
```
**Example (type mismatch):**
```python
store.write("dir/file.txt", b"data")   # creates directory "dir"
with pytest.raises(InvalidPath):
    store.read("dir")                   # "dir" exists but is a directory, not a file
```

## ERR-006: CapabilityNotSupported

**Invariant:** Raised when an operation requires a capability the backend does not support.
**Postconditions:** Carries additional `capability: str` attribute.
**Example:**
```python
with pytest.raises(CapabilityNotSupported) as exc_info:
    backend.write_atomic(...)
assert exc_info.value.capability == "atomic_write"
```

## ERR-007: BackendUnavailable

**Invariant:** Raised when the backend cannot be reached or initialized.
**Postconditions:** `backend` attribute is set.

## ERR-008: Flat Hierarchy

**Invariant:** All concrete errors inherit directly from `RemoteStoreError`, never from each other.

## ERR-009: Meaningful String Representations

**Invariant:** `str()` and `repr()` produce meaningful messages including all non-None context attributes.
**Example:**
```python
e = NotFound("File not found", path="data/file.txt", backend="s3")
assert "data/file.txt" in str(e)
assert "NotFound" in repr(e)
```

## ERR-010: DirectoryNotEmpty

**Invariant:** Raised when `delete_folder(..., recursive=False)` targets a non-empty directory.
**Postconditions:** `path` attribute is set to the offending folder path.
**Example:**
```python
store.write("folder/file.txt", b"data")
with pytest.raises(DirectoryNotEmpty):
    store.delete_folder("folder", recursive=False)
```

## ERR-013: ResourceLocked

**Invariant:** Raised when a target resource exists and the caller is
authorised, but the resource is currently locked by another session
or process and the operation cannot proceed.
**Preconditions:** Caller targets a valid, accessible path whose
backing resource is held by another session (for example, an Office
co-authoring session, a SharePoint checked-out document, or a
concurrent upload session on the same item).
**Postconditions:** `path` and `backend` attributes are set. An
optional `lock_owner: str | None` attribute is reserved for backends
that can surface the holder; it is `None` when the backend cannot
determine ownership.
**Retry guidance:** Not treated as transient by the default retry
policy. Callers decide their own retry cadence, if any.
**Example:**
```python
with pytest.raises(ResourceLocked):
    store.write("contracts/report.docx", content, overwrite=True)
```
**See also:** [ADR-0024](../adrs/0024-resource-locked-error.md),
[044-graph-backend.md](044-graph-backend.md) (GR-045).

## Extension-scoped errors

Extension-specific errors inherit from `RemoteStoreError` but live in their
extension module (per ADR-0013), not in this file. See each extension's spec
for details:

- **ERR-011** `DatasetIncomplete`, **ERR-012** `ManifestCorrupted` — see [spec 042 § PDS-008](042-ext-parquet.md#pds-008-error-conditions)
