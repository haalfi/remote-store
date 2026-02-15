# S3 Backend Specification

## Overview

`S3Backend` implements the `Backend` ABC for S3-compatible object storage (AWS S3, MinIO, etc.) using `s3fs` internally. It maps the Backend contract onto S3's flat key-value model, bridging the gap between S3's prefix-based "folders" and the filesystem-like interface expected by Store.

This is the fsspec-based S3 backend. A future native backend using boto3 + pyarrow.fs directly may follow for advanced data engineering workloads.

**Dependencies:** `s3fs` (optional extra: `pip install remote-store[s3]`)

---

## Construction

### S3-001: Constructor Parameters

**Invariant:** `S3Backend` is constructed with a required `bucket` name and optional connection parameters.
**Signature:**
```python
S3Backend(
    bucket: str,
    *,
    endpoint_url: str | None = None,
    key: str | None = None,
    secret: str | None = None,
    region_name: str | None = None,
    client_options: dict[str, Any] | None = None,
)
```
**Postconditions:** The backend stores configuration but does not connect to S3 during construction (see S3-004).

### S3-002: Backend Name

**Invariant:** `name` property returns `"s3"`.

### S3-003: Capability Declaration

**Invariant:** `S3Backend` declares all capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `GLOB`, `RECURSIVE_LIST`, `METADATA`.
**Rationale:**
- `ATOMIC_WRITE`: S3 PUT is inherently atomic -- readers never see partial content (see S3-010).
- `MOVE`: Implemented via server-side copy + delete (see S3-013).
- `COPY`: Implemented via S3 server-side copy (see S3-014).

### S3-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. The s3fs filesystem is created lazily on first operation.
**Rationale:** Fail-fast at construction is undesirable -- the backend may be created during application wiring before the network is available.

### S3-005: Construction Validation

**Invariant:** `bucket` must be a non-empty string. Passing an empty or whitespace-only bucket raises `ValueError` at construction time.
**Postconditions:** No network validation of bucket existence at construction time. Invalid bucket names that are syntactically non-empty are caught by S3 on first operation and mapped to the appropriate error.

---

## S3 Object Model

### S3-006: Virtual Folder Semantics

**Invariant:** S3 has no native directories. "Folders" are logical constructs derived from key prefixes delimited by `/`. The S3 backend presents a filesystem-like view by interpreting common prefixes as folders.
**Postconditions:** This is a fundamental difference from local filesystems. Several Backend operations have S3-specific behavior documented in this section.

### S3-007: Folder Detection

**Invariant:** `is_folder(path)` returns `True` if any objects exist with prefix `{path}/` in the bucket.
**Postconditions:** Does not require an explicit folder marker object. An empty prefix (no objects) returns `False`.
**Example:**
```python
backend.write("data/file.txt", b"x")
assert backend.is_folder("data") is True
assert backend.is_folder("data/nonexistent") is False
```

### S3-008: Write Does Not Create Folder Markers

**Invariant:** `write("a/b/c.txt", content)` creates only the object with key `a/b/c.txt`. No folder marker objects are created for `a/` or `a/b/`.
**Rationale:** Folder markers add PUT overhead and clutter. S3's prefix-based folder detection (S3-007) makes them unnecessary.

### S3-009: Folder Lifecycle Tied to Contents

**Invariant:** A "folder" exists only as long as objects exist under its prefix. Deleting the last object under a prefix causes `is_folder()` to return `False`.
**Postconditions:** This differs from local filesystems where empty directories persist after their contents are deleted.
**Example:**
```python
backend.write("dir/file.txt", b"x")
assert backend.is_folder("dir") is True
backend.delete("dir/file.txt")
assert backend.is_folder("dir") is False  # folder vanishes
```

**Impact on conformance:** `delete_folder` on an already-empty prefix raises `NotFound` (with `missing_ok=False`), because the folder no longer exists.

---

## Operations

### S3-010: Atomic Write Via S3 PUT

**Invariant:** `write_atomic` is implemented identically to `write` -- as a direct S3 PUT.
**Rationale:** S3 PUT is inherently atomic. From a reader's perspective, the object transitions from non-existent (or old content) to new content in a single operation. No partial content is ever visible. The temp-file + rename pattern used by local backends is unnecessary and would add latency (extra PUT + COPY + DELETE).
**Postconditions:** Satisfies AW-001's postcondition: "No partial content is ever visible."

### S3-011: delete_folder Recursive

**Invariant:** `delete_folder(path, recursive=True)` deletes all objects with prefix `{path}/`.
**Postconditions:** After completion, no objects exist under that prefix. The "folder" ceases to exist (S3-009).
**Raises:** `NotFound` if no objects exist under the prefix and `missing_ok=False`.

### S3-012: delete_folder Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` succeeds only if no file objects exist under the prefix (the folder is "empty").
**Raises:** `NotFound` if the folder does not exist and `missing_ok=False`. Raises a non-empty error if file objects exist under the prefix.
**Postconditions:** Consistent with local filesystem semantics where `rmdir` fails on non-empty directories.

### S3-013: move Via Copy + Delete

**Invariant:** `move(src, dst)` is implemented as server-side copy followed by delete of the source.
**Postconditions:** Not atomic -- if copy succeeds but delete fails, both objects exist. This is inherent to S3 (no native rename).
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### S3-014: copy Via S3 Server-Side Copy

**Invariant:** `copy(src, dst)` uses S3 server-side copy (no data passes through the client).
**Postconditions:** Efficient for large files -- the S3 service handles the copy internally.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

---

## Error Mapping

### S3-015: NotFound Mapping

**Invariant:** S3 responses with HTTP 404 or error code `NoSuchKey` / `NoSuchBucket` are mapped to `NotFound`.
**Postconditions:** `path` and `backend` attributes are set on the error.

### S3-016: PermissionDenied Mapping

**Invariant:** S3 responses with HTTP 403 or error code `AccessDenied` are mapped to `PermissionDenied`.

### S3-017: BackendUnavailable Mapping

**Invariant:** Connection errors (DNS resolution failure, connection refused, timeouts) are mapped to `BackendUnavailable`.

### S3-018: No Native Exception Leakage

**Invariant:** No s3fs, botocore, or aiobotocore exceptions propagate to callers. All are mapped to `remote_store` error types per BE-021.
**Postconditions:** `backend` attribute is set to `"s3"` on all mapped errors.

---

## Resource Management

### S3-019: close()

**Invariant:** `close()` releases the underlying s3fs filesystem resources.
**Postconditions:** Safe to call multiple times. After close, further operations may fail.

### S3-020: unwrap()

**Invariant:** `unwrap(S3FileSystem)` returns the underlying `s3fs.S3FileSystem` instance.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need s3fs-specific features (per ADR-0003).

---

## Configuration

### S3-021: Client Options Passthrough

**Invariant:** The `client_options` dict is merged into the s3fs configuration, allowing advanced settings (custom SSL, proxy, timeouts, etc.).
**Postconditions:** Explicit constructor parameters (`endpoint_url`, `key`, `secret`, `region_name`) take precedence over keys in `client_options`.

### S3-022: Default Credential Chain

**Invariant:** When `key` and `secret` are not provided, the backend falls back to the standard AWS credential chain (environment variables `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, `~/.aws/credentials`, IAM role, etc.).
**Rationale:** Follows the principle of least surprise for AWS users.
