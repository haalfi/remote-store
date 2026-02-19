# Azure Backend Specification

## Overview

`AzureBackend` implements the `Backend` ABC for Azure Storage using `azure-storage-file-datalake` directly. It targets ADLS Gen2 (Hierarchical Namespace) accounts as the primary use case, while remaining fully functional against plain Blob Storage accounts without HNS.

Unlike the S3 backends (which use `s3fs`, an fsspec wrapper), this backend uses the Azure SDK directly. This avoids the fragile string-based error mapping, gives access to native ADLS Gen2 semantics (atomic rename, real directories), and prevents the need for a second hybrid backend later. See [RFC-0002](../rfcs/rfc-0002-azure-backend.md) for the full rationale.

**Dependencies:** `azure-storage-file-datalake`, `azure-identity` (optional, for `DefaultAzureCredential`)
**Optional extra:** `pip install remote-store[azure]`

---

## Construction

### AZ-001: Constructor Parameters

**Invariant:** `AzureBackend` is constructed with a required `container` name and optional connection parameters.
**Signature:**
```python
AzureBackend(
    container: str,
    *,
    account_name: str | None = None,
    account_url: str | None = None,
    account_key: str | None = None,
    sas_token: str | None = None,
    connection_string: str | None = None,
    credential: Any | None = None,  # e.g. DefaultAzureCredential()
    client_options: dict[str, Any] | None = None,
)
```
**Postconditions:** The backend stores configuration but does not connect to Azure during construction (see AZ-004). At least one of `account_name`, `account_url`, or `connection_string` must be provided — otherwise `ValueError` is raised at construction time.

### AZ-002: Backend Name

**Invariant:** `name` property returns `"azure"`.

### AZ-003: Capability Declaration

**Invariant:** `AzureBackend` declares all capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `GLOB`, `RECURSIVE_LIST`, `METADATA`.
**Rationale:**
- `ATOMIC_WRITE`: HNS accounts use temp file + atomic rename; non-HNS accounts use direct upload (Azure PUT is atomic, same as S3). See AZ-006 and AZ-012.
- `MOVE`: HNS accounts use native atomic rename; non-HNS accounts use copy + delete. See AZ-006 and AZ-015.
- `COPY`: Implemented via server-side copy (`start_copy_from_url`). See AZ-016.

### AZ-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. The `FileSystemClient` (and HNS detection) are deferred to first use.
**Rationale:** Same as S3-004 — the backend may be created during application wiring before the network is available.

### AZ-005: Construction Validation

**Invariant:** `container` must be a non-empty string. Passing an empty or whitespace-only container raises `ValueError` at construction time. At least one of `account_name`, `account_url`, or `connection_string` must be provided — otherwise `ValueError` at construction.
**Postconditions:** No network validation of container existence at construction time. Invalid names are caught by Azure on first operation and mapped to the appropriate error.

---

## HNS Detection

### AZ-006: Adaptive Behavior Based on Hierarchical Namespace

**Invariant:** On first use, the backend calls `GetAccountInfo` to determine whether the storage account has Hierarchical Namespace (HNS) enabled. The result is cached for the lifetime of the backend instance.

**Behavior matrix:**

| Operation | HNS enabled (ADLS Gen2) | No HNS (plain Blob) |
|---|---|---|
| `write_atomic` | Temp file + atomic rename | Direct upload (PUT is atomic) |
| `move` | Atomic `rename_file` | Copy + delete |
| `is_folder` | Native directory check | Prefix-based detection |
| `list_files` / `list_folders` | Native directory listing | Prefix-based listing |
| `delete_folder(recursive=True)` | Single recursive delete | Iterate + delete each path |

**Rationale:** ADLS Gen2 has real directories and atomic rename — the backend should use these when available. Plain Blob Storage accounts are still supported by falling back to S3-equivalent semantics (virtual folders, copy+delete move, PUT atomicity).

**Postconditions:** The HNS check is performed at most once. If the check itself fails (e.g. permissions), the backend falls back to non-HNS behavior and logs a warning.

---

## Azure Storage Model

### AZ-007: Container Scope

**Invariant:** All operations are scoped to a single Azure Storage container, analogous to S3Backend's bucket scope. Cross-container operations are not supported.

### AZ-008: Directory Semantics (HNS Enabled)

**Invariant:** When HNS is enabled, directories are real entities. `is_folder(path)` checks for the existence of a directory object. Empty directories persist after their contents are deleted.
**Postconditions:** This matches SFTP behavior (SFTP-011, SFTP-013), not S3 behavior.

### AZ-009: Virtual Folder Semantics (No HNS)

**Invariant:** When HNS is not enabled, folder semantics match S3: "folders" are logical constructs derived from `/`-delimited path prefixes. A folder exists only as long as blobs exist under its prefix.
**Postconditions:** Same as S3-006 through S3-009.

### AZ-010: Write Does Not Create Folder Markers (No HNS)

**Invariant:** On non-HNS accounts, `write("a/b/c.txt", content)` creates only the blob with path `a/b/c.txt`. No folder marker blobs are created.
**Postconditions:** Same as S3-008. Not applicable to HNS accounts where directories are managed natively by the service.

### AZ-011: Path Encoding

**Invariant:** Azure paths use `/` as separator. The backend normalizes paths by stripping leading `/` and collapsing double separators, consistent with the `RemotePath` model (PATH-001 through PATH-014).

---

## Operations

### AZ-012: Atomic Write

**Invariant (HNS):** `write_atomic` writes to a temporary file `.~tmp.<name>.<uuid8>` in the same directory, then renames atomically to the target via `rename_file`. Orphan cleanup on failure follows the same pattern as SFTP-014.
**Invariant (no HNS):** `write_atomic` is implemented identically to `write` — as a direct upload. Azure PUT is atomic at the blob level (same rationale as S3-010).
**Postconditions:** Satisfies AW-001: no partial content is ever visible.

### AZ-013: delete_folder Recursive

**Invariant (HNS):** `delete_folder(path, recursive=True)` calls the ADLS Gen2 recursive delete API (single call).
**Invariant (no HNS):** `delete_folder(path, recursive=True)` lists and deletes all blobs with prefix `{path}/`.
**Raises:** `NotFound` if no directory/blobs exist under the path and `missing_ok=False`.

### AZ-014: delete_folder Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` succeeds only if the directory/prefix is empty.
**Raises:** `NotFound` if the folder does not exist and `missing_ok=False`. Raises a non-empty error if children exist.
**Postconditions:** Consistent with local filesystem and SFTP semantics.

### AZ-015: Move

**Invariant (HNS):** `move(src, dst)` uses ADLS Gen2's native `rename_file`, which is atomic.
**Invariant (no HNS):** `move(src, dst)` is implemented as server-side copy + delete (same as S3-013). Not atomic.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### AZ-016: Copy

**Invariant:** `copy(src, dst)` uses Azure's server-side copy via `start_copy_from_url`. No data passes through the client.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### AZ-017: Read and Write

**Invariant:** `read()` returns a `BinaryIO` stream via `download_file().readinto()` or equivalent. `write()` uploads via `upload_data()`.
**Raises:** `NotFound` on read if the file does not exist. `AlreadyExists` on write if the file exists and `overwrite=False`.

---

## Error Mapping

### AZ-018: Structured Error Classification

**Invariant:** Azure SDK exceptions are mapped to `remote_store` errors using structured attributes (`status_code`, `error_code`), not string matching.

| Azure SDK exception / code | remote_store error |
|---|---|
| `ResourceNotFoundError`; `status_code=404`; error codes `BlobNotFound`, `PathNotFound`, `FilesystemNotFound`, `ContainerNotFound` | `NotFound` |
| `status_code=403`; error codes `AuthorizationFailure`, `AuthorizationPermissionMismatch`, `InsufficientAccountPermissions` | `PermissionDenied` |
| `ResourceExistsError`; `status_code=409`; error codes `PathAlreadyExists`, `BlobAlreadyExists`, `ContainerAlreadyExists` | `AlreadyExists` |
| `ServiceRequestError`, `ServiceResponseError` (connection / DNS / timeout) | `BackendUnavailable` |
| `ClientAuthenticationError` | `PermissionDenied` |

**Rationale:** The Azure SDK provides `HttpResponseError` with `status_code` and `error_code` attributes, enabling reliable classification. This is a significant improvement over the S3 backends' fragile string-matching pattern (`"404" in msg.lower()`).

### AZ-019: No Native Exception Leakage

**Invariant:** No `azure-storage-file-datalake`, `azure-core`, or `azure-identity` exceptions propagate to callers. All are mapped to `remote_store` error types per BE-021.
**Postconditions:** `backend` attribute is set to `"azure"` on all mapped errors.

### AZ-020: to_key

**Invariant:** `AzureBackend.to_key(native_path)` strips the `{container}/` prefix from native paths.
**Example:**
```python
backend = AzureBackend(container="my-container", account_name="myaccount")
backend.to_key("my-container/data/file.txt")  # -> "data/file.txt"
backend.to_key("data/file.txt")               # -> "data/file.txt" (no prefix, unchanged)
```
**Postconditions:** Pure, deterministic, total (never raises). Same contract as NPR-004.

### AZ-021: Error Context Manager

**Invariant:** A single `_errors(path)` context manager catches all Azure SDK exceptions and maps them per AZ-018.
**Rationale:** Unlike S3PyArrowBackend's dual error contexts (one for PyArrow, one for s3fs), this backend uses a single SDK, so a single error context suffices.

---

## Resource Management

### AZ-022: close()

**Invariant:** `close()` closes the underlying `FileSystemClient` and `DataLakeServiceClient`.
**Postconditions:** Safe to call multiple times. After close, further operations will fail.

### AZ-023: unwrap()

**Invariant:** `unwrap(FileSystemClient)` returns the underlying `azure.storage.filedatalake.FileSystemClient`.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need Azure-specific features (per ADR-0003).

---

## Configuration

### AZ-024: Client Options Passthrough

**Invariant:** The `client_options` dict is merged into the `DataLakeServiceClient` configuration, allowing advanced settings (custom timeouts, retry policies, proxies, API version overrides, etc.).
**Postconditions:** Explicit constructor parameters (`account_key`, `sas_token`, `credential`, etc.) take precedence over keys in `client_options`.

### AZ-025: Default Credential Chain

**Invariant:** When no explicit credential is provided (`account_key`, `sas_token`, `connection_string`, and `credential` are all `None`), the backend attempts to use `DefaultAzureCredential` from `azure-identity`.
**Raises:** `BackendUnavailable` if `azure-identity` is not installed and no explicit credential is provided.
**Rationale:** Follows the principle of least surprise for Azure users. `DefaultAzureCredential` automatically resolves environment variables, managed identity, Azure CLI login, and other credential sources.
