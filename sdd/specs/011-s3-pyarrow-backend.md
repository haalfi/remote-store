# S3-PyArrow Hybrid Backend Specification

## Overview

`S3PyArrowBackend` implements the `Backend` ABC for S3-compatible object storage using a hybrid approach: **PyArrow's C++ S3 filesystem** for data-path operations (read, write, copy) and **s3fs** for control-path operations (listing, metadata, deletion). This combines PyArrow's high-throughput C++ I/O with s3fs's mature listing and metadata APIs.

This is a drop-in alternative to `S3Backend` with the same constructor signature. Users who need maximum read/write throughput for large files should prefer this backend.

**Dependencies:** `s3fs`, `pyarrow` (optional extra: `pip install "remote-store[s3-pyarrow]"`)

> This specification is a **delta** over [spec 008 (S3 Backend)](008-s3-backend.md).
> Any invariant not restated here follows the paired S3-NNN ID verbatim,
> substituting the backend name `"s3-pyarrow"` for `"s3"`. Only PyArrow-specific
> deltas (dual-library architecture, credential translation, the PyArrow read
> path, dual `unwrap()`, and the dual error-mapping context managers) carry a
> full body below. Tests reference both IDs per backend via per-parameter
> `pytest.mark.spec(...)` marks (see `tests/backends/test_s3_shared.py`).

### Paired IDs (delta map)

| This spec (S3PA-NNN)                  | Inherited from 008 (S3-NNN)            |
|---------------------------------------|----------------------------------------|
| S3PA-001 Constructor Parameters       | S3-001 (same signature)                |
| S3PA-004 Lazy Connection              | S3-004                                 |
| S3PA-005 Construction Validation      | S3-005                                 |
| S3PA-008 Virtual Folder Semantics     | S3-006                                 |
| S3PA-009 Folder Detection             | S3-007                                 |
| S3PA-010 Write Does Not Create Markers | S3-008                                |
| S3PA-011 Folder Lifecycle             | S3-009                                 |
| S3PA-013 Write Via PyArrow            | S3-010 (atomic write)                  |
| S3PA-014 Copy Via PyArrow             | S3-014 (server-side copy)              |
| S3PA-015 Move Via Hybrid              | S3-013 (copy + delete)                 |
| S3PA-016 Delete Via s3fs              | S3-011, S3-012                         |
| S3PA-017 Listing Via s3fs             | (implicit; s3fs control path)          |
| S3PA-018 Dual Error Context Managers  | S3-015, S3-016, S3-017                 |
| S3PA-019 No Native Exception Leakage  | S3-018                                 |
| S3PA-020 close()                      | S3-019                                 |
| S3PA-022 Client Options Passthrough   | S3-021                                 |
| S3PA-023 Endpoint URL Normalization   | S3-025                                 |
| S3PA-024 Default Credential Chain     | S3-022                                 |
| S3PA-026 config_kwargs + RetryPolicy  | S3-026                                 |

Full-body deltas (unique to S3-PyArrow): **S3PA-002, S3PA-003, S3PA-006,
S3PA-007, S3PA-012, S3PA-021**.

---

## Construction

### S3PA-001: Constructor Parameters

See [S3-001](008-s3-backend.md#s3-001-constructor-parameters). Same signature; the class name is `S3PyArrowBackend`. Constructor arguments are translated to each library's conventions internally (S3PA-007). Default credential chain follows [S3-022](008-s3-backend.md#s3-022-default-credential-chain).

### S3PA-002: Backend Name

**Invariant:** `name` property returns `"s3-pyarrow"`.

### S3PA-003: Capability Declaration

**Invariant:** `S3PyArrowBackend` declares capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`, `WRITE_RESULT_NATIVE`. Native glob via prefix-optimized listing (see [018-glob.md](018-glob.md) GLOB-019).

**Delta vs S3-003:** `USER_METADATA` is NOT declared — PyArrow's `open_output_stream()` does not support per-object user metadata. `WRITE_RESULT_NATIVE` IS declared: after upload, `write()` performs a `head_object(ChecksumMode="ENABLED")` round-trip via s3fs to populate `etag`, `digest`, and `last_modified`.

**Rationale:** Same as S3-003 for the declared capabilities. The `ATOMIC_MOVE` capability is not declared (move = copy+delete, so partial failure is observable — see S3PA-015).

### S3PA-004: Lazy Connection

See [S3-004](008-s3-backend.md#s3-004-lazy-connection). Applies to both the PyArrow and s3fs filesystem instances: each is created lazily on first use.

### S3PA-005: Construction Validation

See [S3-005](008-s3-backend.md#s3-005-construction-validation).

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

See [S3-006](008-s3-backend.md#s3-006-virtual-folder-semantics).

### S3PA-009: Folder Detection

See [S3-007](008-s3-backend.md#s3-007-folder-detection).

### S3PA-010: Write Does Not Create Folder Markers

See [S3-008](008-s3-backend.md#s3-008-write-does-not-create-folder-markers).

### S3PA-011: Folder Lifecycle Tied to Contents

See [S3-009](008-s3-backend.md#s3-009-folder-lifecycle-tied-to-contents).

---

## Operations

### S3PA-012: Read Via PyArrow

**Invariant:** `read()` uses `open_input_file()` (seekable `RandomAccessFile`) and returns the stream wrapped in `_ErrorMappingStream` without `BufferedReader`. `read_bytes()` uses `open_input_stream()` and reads all bytes directly. `readline()` uses a chunked scan (`_READLINE_CHUNK`-sized reads) with seek-back for over-read bytes, requiring a seekable stream from `open_input_file`.

**Rationale:** PyArrow's C++ I/O path provides higher throughput than s3fs for large files. Removing the `BufferedReader` eliminates a double-copy per chunk on the streaming read path (RFC-0003). The chunked `readline()` avoids the pathological byte-at-a-time fallback from `RawIOBase`.

**Note:** Unlike other backends which return `io.BufferedReader`, S3-PyArrow returns a raw `_ErrorMappingStream(RawIOBase)`. This means `io.TextIOWrapper(stream)` requires wrapping in `io.BufferedReader` first. The spec (SIO-001 in 008-streaming-io.md) only requires `BinaryIO`, so this is valid, but callers should not assume `BufferedIOBase`.

### S3PA-013: Write Via PyArrow

See [S3-010](008-s3-backend.md#s3-010-atomic-write-via-s3-put). `write()` and `write_atomic()` use `pyarrow.fs.S3FileSystem.open_output_stream()` for data transfer; existence checks go through s3fs.

### S3PA-014: Copy Via PyArrow

See [S3-014](008-s3-backend.md#s3-014-copy-via-s3-server-side-copy). Uses `pyarrow.fs.S3FileSystem.copy_file()` for the server-side copy; existence checks go through s3fs.

### S3PA-015: Move Via Hybrid

See [S3-013](008-s3-backend.md#s3-013-move-via-copy-delete). The copy step uses PyArrow; existence checks and the delete step go through s3fs. Not atomic — if copy succeeds but delete fails, both objects exist.

### S3PA-016: Delete Via s3fs

See [S3-011](008-s3-backend.md#s3-011-delete_folder-recursive) and [S3-012](008-s3-backend.md#s3-012-delete_folder-non-recursive). `delete()` and `delete_folder()` use s3fs, identical to `S3Backend`.

### S3PA-017: Listing Via s3fs

**Invariant:** `list_files()`, `list_folders()`, `get_file_info()`, `get_folder_info()` use s3fs, identical to `S3Backend`. `get_file_info()` returns a `FileInfo` carrying `etag` and (when the object has a stored checksum) `digest`.

---

## Error Mapping

### S3PA-018: Dual Error Context Managers

See [S3-015](008-s3-backend.md#s3-015-notfound-mapping), [S3-016](008-s3-backend.md#s3-016-permissiondenied-mapping), and [S3-017](008-s3-backend.md#s3-017-backendunavailable-mapping) for the NotFound / PermissionDenied / BackendUnavailable mappings.

**Delta vs S3-015/016/017:** Two context managers handle the two libraries:

- `_pyarrow_errors(path)`: catches `OSError` / `ArrowInvalid` from PyArrow operations and maps to `remote_store` errors.
- `_s3fs_errors(path)`: catches s3fs/botocore exceptions, same mapping as `S3Backend`.

**Postconditions:** `backend` attribute is set to `"s3-pyarrow"` on all mapped errors.

### S3PA-019: No Native Exception Leakage

See [S3-018](008-s3-backend.md#s3-018-no-native-exception-leakage). Extended to PyArrow: no PyArrow, s3fs, botocore, or aiobotocore exceptions propagate to callers.

---

## Resource Management

### S3PA-020: close()

See [S3-019](008-s3-backend.md#s3-019-close). `close()` releases both the PyArrow and s3fs filesystem instances. Safe to call multiple times.

### S3PA-021: Dual unwrap()

**Invariant:** `unwrap()` supports two type hints:
- `unwrap(pyarrow.fs.S3FileSystem)` returns the PyArrow filesystem.
- `unwrap(s3fs.S3FileSystem)` returns the s3fs filesystem.

**Raises:** `CapabilityNotSupported` for any other type hint.

**Rationale:** Escape hatch for users who need library-specific features. Delta vs S3-020 (which only unwraps to `s3fs.S3FileSystem`).

---

## Configuration

### S3PA-022: Client Options Passthrough

See [S3-021](008-s3-backend.md#s3-021-client-options-passthrough). Applies to s3fs only — PyArrow configuration is derived from the explicit constructor parameters, not from `client_options`.

### S3PA-023: Endpoint URL Normalization

See [S3-025](008-s3-backend.md#s3-025-endpoint-url-normalization).

### S3PA-024: Default Credential Chain

See [S3-022](008-s3-backend.md#s3-022-default-credential-chain).

### S3PA-026: config_kwargs is the only Config channel; client_kwargs['config'] is rejected

See [S3-026](008-s3-backend.md#s3-026). Applies to the s3fs control path only; the PyArrow data path (`_pa_fs`) is unaffected.
