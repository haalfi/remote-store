# Errors Specification

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

**Invariant:** Raised for malformed, unsafe, or out-of-scope paths.
**Preconditions:** Caller provides a path containing `..`, null bytes, or that normalizes to empty.
**Postconditions:** `path` attribute is set to the offending input.
**Example:**
```python
with pytest.raises(InvalidPath):
    RemotePath("foo/../bar")
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
