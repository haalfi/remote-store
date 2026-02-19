# S3-PyArrow Hybrid Backend Specification

## Overview

`S3PyArrowBackend` implements the `Backend` ABC for S3-compatible object storage using a hybrid approach: **PyArrow's C++ S3 filesystem** for data-path operations (read, write, copy) and **s3fs** for control-path operations (listing, metadata, deletion). This combines PyArrow's high-throughput C++ I/O with s3fs's mature listing and metadata APIs.

This is a drop-in alternative to `S3Backend` with the same constructor signature. Users who need maximum read/write throughput for large files should prefer this backend.

**Dependencies:** `s3fs`, `pyarrow` (optional extra: `pip install remote-store[s3-pyarrow]`)

---

## Construction

### S3PA-001: Constructor Parameters

**Invariant:** `S3PyArrowBackend` is constructed with the same signature as `S3Backend`: a required `bucket` name and optional connection parameters.
**Signature:**
```python
S3PyArrowBackend(
    bucket: str,
    *,
    endpoint_url: str | None = None,
    key: str | None = None,
    secret: str | None = None,
    region_name: str | None = None,
    client_options: dict[str, Any] | None = None,
)
```
**Postconditions:** The backend stores configuration but does not connect to S3 during construction (see S3PA-004). Constructor arguments are translated to each library's conventions internally.

### S3PA-002: Backend Name

**Invariant:** `name` property returns `"s3-pyarrow"`.

### S3PA-003: Capability Declaration

**Invariant:** `S3PyArrowBackend` declares all capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `GLOB`, `RECURSIVE_LIST`, `METADATA`.
**Rationale:** Same as S3Backend -- S3 PUT is inherently atomic, move via copy+delete, copy via server-side copy.

### S3PA-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. Both the PyArrow and s3fs filesystem instances are created lazily on first use.
**Rationale:** Same as S3-004.

### S3PA-005: Construction Validation

**Invariant:** `bucket` must be a non-empty string. Passing an empty or whitespace-only bucket raises `ValueError` at construction time.

---

## Library Mapping

### S3PA-006: Dual-Library Architecture

**Invariant:** Operations are split between two libraries based on their strengths:

| PyArrow (C++ data path) | s3fs (control path) |
|---|---|
| `read`, `read_bytes` | `exists`, `is_file`, `is_folder` |
| `write`, `write_atomic` | `list_files`, `list_folders` |
| `copy` | `get_file_info`, `get_folder_info` |
| | `delete`, `delete_folder` |
| | `move` (s3fs checks + pyarrow copy + s3fs delete) |

**Rationale:** PyArrow's C++ S3 implementation offers superior throughput for bulk data transfer. s3fs (built on aiobotocore) has more mature and flexible listing, metadata, and deletion APIs.

### S3PA-007: Credential Translation

**Invariant:** Constructor credentials are translated per library:
- **PyArrow:** `access_key`, `secret_key`, `region`, `endpoint_override`, `scheme`
- **s3fs:** `key`, `secret`, `client_kwargs.region_name`, `endpoint_url`

**Postconditions:** Both libraries authenticate with the same credentials to the same endpoint.

---

## S3 Object Model

### S3PA-008: Virtual Folder Semantics

**Invariant:** Same as S3-006. S3 has no native directories; folders are logical constructs from key prefixes.

### S3PA-009: Folder Detection

**Invariant:** Same as S3-007. `is_folder(path)` returns `True` if any objects exist with prefix `{path}/`.

### S3PA-010: Write Does Not Create Folder Markers

**Invariant:** Same as S3-008. No folder marker objects are created.

### S3PA-011: Folder Lifecycle Tied to Contents

**Invariant:** Same as S3-009. Folders vanish when the last object under a prefix is deleted.

---

## Operations

### S3PA-012: Read Via PyArrow

**Invariant:** `read()` and `read_bytes()` use `pyarrow.fs.S3FileSystem.open_input_stream()` for data transfer.
**Rationale:** PyArrow's C++ I/O path provides higher throughput than s3fs for large files.

### S3PA-013: Write Via PyArrow

**Invariant:** `write()` and `write_atomic()` use `pyarrow.fs.S3FileSystem.open_output_stream()` for data transfer. Existence checks use s3fs.
**Postconditions:** Same as S3-010 -- S3 PUT is inherently atomic, so `write_atomic` delegates to `write`.

### S3PA-014: Copy Via PyArrow

**Invariant:** `copy(src, dst)` uses `pyarrow.fs.S3FileSystem.copy_file()` for server-side copy. Existence checks use s3fs.

### S3PA-015: Move Via Hybrid

**Invariant:** `move(src, dst)` uses s3fs for existence checks, PyArrow for the copy step, and s3fs for the delete step.
**Postconditions:** Same as S3-013 -- not atomic; if copy succeeds but delete fails, both objects exist.

### S3PA-016: Delete Via s3fs

**Invariant:** `delete()` and `delete_folder()` use s3fs, same as S3Backend.

### S3PA-017: Listing Via s3fs

**Invariant:** `list_files()`, `list_folders()`, `get_file_info()`, `get_folder_info()` use s3fs, same as S3Backend.

---

## Error Mapping

### S3PA-018: Dual Error Context Managers

**Invariant:** Two error-mapping context managers exist:
- `_pyarrow_errors(path)`: catches `OSError` / `ArrowInvalid` from PyArrow operations and maps to remote_store errors.
- `_s3fs_errors(path)`: catches s3fs/botocore exceptions, same mapping as S3Backend.

**Postconditions:** `backend` attribute is set to `"s3-pyarrow"` on all mapped errors.

### S3PA-019: No Native Exception Leakage

**Invariant:** No PyArrow, s3fs, botocore, or aiobotocore exceptions propagate to callers. All are mapped to `remote_store` error types per BE-021.

---

## Resource Management

### S3PA-020: close()

**Invariant:** `close()` releases both the PyArrow and s3fs filesystem instances.
**Postconditions:** Safe to call multiple times.

### S3PA-021: Dual unwrap()

**Invariant:** `unwrap()` supports two type hints:
- `unwrap(pyarrow.fs.S3FileSystem)` returns the PyArrow filesystem.
- `unwrap(s3fs.S3FileSystem)` returns the s3fs filesystem.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need library-specific features.

---

## Configuration

### S3PA-022: Client Options Passthrough

**Invariant:** Same as S3-021. The `client_options` dict is merged into the s3fs configuration.
**Postconditions:** `client_options` applies to s3fs only. PyArrow configuration is derived from the explicit constructor parameters.
