# Azure Backend Specification

## Overview

`AzureBackend` implements the `Backend` ABC for Azure Storage using a dual-client architecture: `azure-storage-blob` (BlobServiceClient) for non-HNS accounts and `azure-storage-file-datalake` (DataLakeServiceClient) for HNS-only features. It targets ADLS Gen2 (Hierarchical Namespace) accounts as the primary use case, while remaining fully functional against plain Blob Storage accounts without HNS.

Unlike the S3 backends (which use `s3fs`, an fsspec wrapper), this backend uses the Azure SDK directly. The dual-client design exists because the DFS wire protocol (used by `azure-storage-file-datalake`) is not supported by Azurite or plain Blob Storage accounts — only the Blob API works everywhere. HNS-only features (atomic rename, real directories) use the DataLake SDK; all other operations use the Blob SDK. See [RFC-0001](../rfcs/rfc-0001-azure-backend.md) for the full rationale.

**Dependencies:** `azure-storage-file-datalake`, `azure-identity` (optional, for `DefaultAzureCredential`)
**Optional extra:** `pip install "remote-store[azure]"`

---

## Construction

### AZ-001: Constructor Parameters

**Invariant:** `AzureBackend` is constructed with a required `container` name and optional connection parameters.
**Signature:**
```python
AzureBackend(
    container: str,
    *,
    hns: bool,  # required — see AZ-006; no default, no auto-detection
    account_name: str | None = None,
    account_url: str | None = None,
    account_key: str | None = None,
    sas_token: str | None = None,
    connection_string: str | None = None,
    credential: Any | None = None,  # e.g. DefaultAzureCredential()
    client_options: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,  # see spec 025
    max_concurrency: int = 1,  # see AZ-033
)
```
**Postconditions:** The backend stores configuration but does not connect to Azure during construction (see AZ-004). `hns` must be declared explicitly (`True` or `False`) and at least one of `account_name`, `account_url`, or `connection_string` must be provided — otherwise `ValueError` is raised at construction time.

### AZ-002: Backend Name

**Invariant:** `name` property returns `"azure"`.

### AZ-003: Capability Declaration

**Invariant:** `AzureBackend` declares capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`. Native glob via prefix-optimized listing (see [018-glob.md](018-glob.md) GLOB-020).
**Rationale:**
- `ATOMIC_WRITE`: HNS accounts use temp file + atomic rename; non-HNS accounts use direct upload (Azure PUT is atomic, same as S3). See AZ-006 and AZ-014.
- `MOVE`: HNS accounts use native atomic rename; non-HNS accounts use copy + delete. See AZ-006 and AZ-017.
- `COPY`: Implemented via server-side copy (`start_copy_from_url`). See AZ-018.
- `GLOB`: Native prefix-optimized glob since v0.12.0 (BK-002).

### AZ-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. The `BlobServiceClient` and `DataLakeServiceClient` (HNS only) are deferred to first use. HNS status is not discovered at runtime at all — it is a declared input (see AZ-006).
**Rationale:** Same as S3-004 — the backend may be created during application wiring before the network is available.

### AZ-005: Construction Validation

**Invariant:** `container` must be a non-empty string. Passing an empty or whitespace-only container raises `ValueError` at construction time. `hns` must be declared explicitly (`True` or `False`); omitting it raises `ValueError` (see AZ-006). At least one of `account_name`, `account_url`, or `connection_string` must be provided — otherwise `ValueError` at construction.
**Postconditions:** No network validation of container existence at construction time. Invalid names are caught by Azure on first operation and mapped to the appropriate error.

---

## HNS Declaration

### AZ-006: Adaptive Behavior Based on Hierarchical Namespace

**Invariant:** Whether the storage account has Hierarchical Namespace (HNS) enabled is a **mandatory, explicit** constructor and config input: `AzureBackend(..., hns: bool)`. There is no default and no runtime auto-detection. A backend constructed without `hns` raises `ValueError` at construction time (fail loud — the account's nature is never silently inferred). The declared value is stored as an immutable attribute and governs every adaptive code path below; because it is a constant, no operation can observe a different HNS state than the one declared (no probe, no cache, no per-operation snapshot).

**Discovery:** Users who do not know an account's HNS status call the public one-shot helper `AzureUtils.detect_hns(...)` (sync) / `AzureUtils.adetect_hns(...)` (async), which issues a single `GetAccountInfo` call and returns a `bool`. The helper is **fail-loud**: a probe error is mapped to a `remote_store` error and raised, not swallowed. This mirrors `SFTPUtils.scan_host_keys` / `GraphUtils.resolve_drive_id`. See [ADR-0030](../adrs/0030-azure-hns-explicit-declaration.md).

**Behavior matrix:**

| Operation | HNS enabled (ADLS Gen2) | No HNS (plain Blob) |
|---|---|---|
| `write_atomic` | Temp file + atomic rename | Direct upload (PUT is atomic) |
| `move` | Atomic `rename_file` | Copy + delete |
| `exists` / `is_file` / `is_folder` | Native path property check | HEAD request + prefix check |
| `list_files` / `list_folders` | Native directory listing | Prefix-based listing |
| `delete_folder(recursive=True)` | Single recursive delete | Iterate + delete each path |

**Rationale:** ADLS Gen2 has real directories and atomic rename — the backend should use these when available. Plain Blob Storage accounts are still supported by declaring `hns=False` and falling back to S3-equivalent semantics (virtual folders, copy+delete move, PUT atomicity). Making the account's nature an explicit declaration rather than a runtime probe makes the backend deterministic from construction and removes the sticky-misdetection, re-probe-storm, and torn-read failure modes a network probe is subject to.

**Postconditions:** No network call determines HNS status — the declared value is authoritative for the lifetime of the instance.

---

## Azure Storage Model

### AZ-007: Container Scope

**Invariant:** All operations are scoped to a single Azure Storage container, analogous to S3Backend's bucket scope. Cross-container operations are not supported.

### AZ-008: Directory Semantics (HNS Enabled)

**Invariant:** When HNS is enabled, directories are real entities. `is_folder(path)` checks for the existence of a directory object. Empty directories persist after their contents are deleted.
**Postconditions:** This matches SFTP behavior (SFTP-011, SFTP-013), not S3 behavior. Type-mismatch safety on HNS is captured by [AZ-036](#az-036-hns-directory-marker-probe-contract): every file-API op probes `hdi_isfolder` before delegating to the SDK, and folder-API ops probe its absence — without this, the Azure SDK silently accepts directory-vs-file mismatches that would corrupt or destroy account state.

### AZ-009: Virtual Folder Semantics (No HNS)

**Invariant:** When HNS is not enabled, folder semantics match S3: "folders" are logical constructs derived from `/`-delimited path prefixes. A folder exists only as long as blobs exist under its prefix.
**Postconditions:** Same as S3-006 through S3-009.

### AZ-010: Write Does Not Create Folder Markers (No HNS)

**Invariant:** On non-HNS accounts, `write("a/b/c.txt", content)` creates only the blob with path `a/b/c.txt`. No folder marker blobs are created.
**Postconditions:** Same as S3-008. Not applicable to HNS accounts where directories are managed natively by the service.

### AZ-011: Path Encoding

**Invariant:** Azure paths use `/` as separator. The backend normalizes paths by stripping leading `/` and collapsing double separators, consistent with the `RemotePath` model (PATH-001 through PATH-014).

---

## Path Inspection

### AZ-012: exists()

**Invariant (HNS):** `exists(path)` first checks for a blob via `BlobClient.get_blob_properties()`, then checks for a directory via `DataLakeDirectoryClient.get_directory_properties()`. Returns `True` if either exists, `False` on `ResourceNotFoundError`.
**Invariant (no HNS):** `exists(path)` issues a HEAD request for the blob via `BlobClient.get_blob_properties()`. Returns `True` if found, `False` on `ResourceNotFoundError`. Falls back to prefix check for folders.
**Postconditions:** Never raises `NotFound` — returns `False` instead (per BE-004).

### AZ-013: is_file() and is_folder()

**Invariant (HNS):** Both predicates use the `hdi_isfolder` metadata marker — not the SDK's `is_directory` attribute — because on real ADLS Gen2, `get_directory_properties()` returns HTTP 200 for any path entity, file or directory. `is_file(path)` calls `BlobClient.get_blob_properties()` and returns `True` when the `hdi_isfolder` marker is absent. `is_folder(path)` calls `DataLakeDirectoryClient.get_directory_properties()` and returns `True` when the `hdi_isfolder=true` marker is present. Both return `False` for non-existent paths or marker-mismatched entities.
**Invariant (no HNS):** `is_file(path)` issues a HEAD request for the blob — returns `True` if the blob exists. `is_folder(path)` returns `True` if any blobs exist with prefix `{path}/` (same as S3-007).
**Postconditions:** Both return `False` for non-existent paths — never raise (per BE-005). Both honour [AZ-036](#az-036-hns-directory-marker-probe-contract).

---

## Operations

### AZ-014: Atomic Write

**Invariant (HNS):** `write_atomic` writes to a temporary file `.~tmp.<name>.<uuid8>` in the same directory as the target, then renames atomically to the target via `rename_file`.
**Cleanup:** If the rename fails, the backend attempts to delete the temporary file. If cleanup also fails (e.g. connection lost), the orphan temp file remains — this is an inherent limitation of simulated atomicity over a network. Temp files are identifiable by their `.~tmp.` prefix for manual cleanup.
**Invariant (no HNS):** `write_atomic` is implemented identically to `write` — as a direct upload. Azure PUT is atomic at the blob level (same rationale as S3-010).
**Streaming chunk granularity (intentional twin divergence):** the HNS streaming-upload path bounds each DFS `append_data` differently across twins — the sync backend owns the `BinaryIO.read(N)` call and caps every append at `_AZURE_BLOCK_SIZE`; the async backend issues one `append_data` per chunk yielded by the producer's `AsyncIterable[bytes]`, so the per-call size is producer-controlled and unbounded. Both keep client memory bounded to the working chunk; only the per-append HTTP granularity differs.
**Postconditions:** Satisfies AW-001: no partial content is ever visible.

### AZ-015: delete_folder Recursive

**Invariant (HNS):** `delete_folder(path, recursive=True)` calls the ADLS Gen2 recursive delete API (single call).
**Invariant (no HNS):** `delete_folder(path, recursive=True)` lists and deletes all blobs with prefix `{path}/`.
**Raises:** `NotFound` if no directory/blobs exist under the path and `missing_ok=False`.

### AZ-016: delete_folder Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` succeeds only if the directory/prefix is empty.
**Raises:** `NotFound` if the folder does not exist and `missing_ok=False`. Raises a non-empty error if children exist.
**Postconditions:** Consistent with local filesystem and SFTP semantics.

### AZ-017: Move

**Invariant (HNS):** `move(src, dst)` uses ADLS Gen2's native `rename_file`, which is atomic.
**Invariant (no HNS):** `move(src, dst)` is implemented as server-side copy + delete (same as S3-013). Not atomic — if copy succeeds but delete fails, both files exist.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### AZ-018: Copy

**Invariant:** `copy(src, dst)` uses Azure's server-side copy via `start_copy_from_url`. No data passes through the client.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

### AZ-019: Glob

**Invariant:** `glob(pattern)` uses Azure's `list_paths` with a prefix filter derived from the non-wildcard prefix of the pattern. The wildcard portion is matched client-side using `fnmatch`.
**Example:** `glob("data/2024/*.csv")` sends `list_paths(path="data/2024")` to the server, then filters results client-side against `*.csv`.
**Rationale:** Azure (like S3) supports prefix-based listing but not full glob syntax server-side. The prefix optimization reduces the result set sent over the wire; `fnmatch` handles the rest locally.

### AZ-020: read()

**Invariant:** `read(path)` returns a `BinaryIO` stream via `_AzureBinaryIO`, a forward-only streaming adapter wrapping `StorageStreamDownloader.chunks()`. The raw adapter is wrapped in `io.BufferedReader` for efficient buffered reads.
**Postconditions:** Data is streamed on demand — the full file is not loaded into memory. The stream is forward-only (not seekable). Callers that require seekability should use `read_bytes()` + `BytesIO`.
**Raises:** `NotFound` if the file does not exist. `InvalidPath` per [AZ-036](#az-036-hns-directory-marker-probe-contract) if the path names an HNS directory.

### AZ-021: read_bytes()

**Invariant:** `read_bytes(path)` returns the full file content as `bytes`. Implemented via `BlobClient.download_blob().readall()`.
**Raises:** `NotFound` if the file does not exist. `InvalidPath` per [AZ-036](#az-036-hns-directory-marker-probe-contract) if the path names an HNS directory.

### AZ-022: write()

**Invariant:** `write(path, content, overwrite=False)` uploads content via `BlobClient.upload_blob()` (Blob SDK).
**Preconditions:** `content` is `bytes` or `BinaryIO`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. Existence check uses `ResourceNotFoundError` (not broad exception catch) to avoid swallowing auth/network errors. `InvalidPath` per [AZ-036](#az-036-hns-directory-marker-probe-contract) if the path names an HNS directory.
**Postconditions (HNS):** Intermediate directories are created automatically by the ADLS Gen2 service.
**Postconditions (no HNS):** No intermediate directory creation needed (flat blob namespace).

### AZ-023: get_file_info()

**Invariant:** `get_file_info(path)` returns a `FileInfo` populated from `BlobClient.get_blob_properties()`.
**Mapped fields:**
- `path`: the store-relative key
- `name`: filename component of the path
- `size`: from `content_length` (or `size` for HNS path objects)
- `modified_at`: from `last_modified` (UTC datetime)
- `etag`: see AZ-034
- `digest`: see AZ-034

**Note:** `content_type` is not included in `FileInfo`.

**Raises:** `NotFound` if the file does not exist. `InvalidPath` per [AZ-036](#az-036-hns-directory-marker-probe-contract) if the path names an HNS directory.

### AZ-024: get_folder_info()

**Invariant:** `get_folder_info(path)` returns a `FolderInfo`.
**Invariant (HNS):** Uses `DataLakeDirectoryClient.get_directory_properties()` on the directory object to confirm the entity exists, then probes `hdi_isfolder` (per [AZ-036](#az-036-hns-directory-marker-probe-contract)) to reject file-path mismatches. When `path == ""` (filesystem root), the per-path probe is skipped — the root is always a folder, and real ADLS Gen2 rejects `get_directory_client("")` with `"Please specify a file system name and file path"` (BUG-213). Child file count and total size are aggregated via `_fs.get_paths(recursive=True)`, skipping entries with `is_directory=True` (BUG-199).
**Invariant (no HNS):** Checks for the existence of blobs under the prefix `{path}/`.
**Raises:** `NotFound` if the folder does not exist. `InvalidPath` per [AZ-036](#az-036-hns-directory-marker-probe-contract) if the path names a file on HNS (`hdi_isfolder` absent).

---

## Error Mapping

### AZ-025: Structured Error Classification

**Invariant:** Azure SDK exceptions are mapped to `remote_store` errors using structured attributes — the exception subtype (which the SDK derives from the HTTP status and `error_code`) and `status_code` — not string matching.

| Azure SDK exception / status | remote_store error |
|---|---|
| `ResourceNotFoundError`; `status_code=404` | `NotFound` |
| `ResourceExistsError`; `status_code=409` | `AlreadyExists` |
| `ClientAuthenticationError`; `status_code=401`; `status_code=403` | `PermissionDenied` |
| `status_code=429` (throttle); `status_code` in `{500, 502, 503, 504}` (server / gateway) | `BackendUnavailable` |
| `ServiceRequestError`, `ServiceResponseError` (connection / DNS / timeout) | `BackendUnavailable` |
| Any other `HttpResponseError` status (e.g. `412` precondition) | `RemoteStoreError` (base) |

**Rationale:** The Azure SDK provides `HttpResponseError` with a `status_code` attribute and raises typed subclasses (`ResourceNotFoundError`, `ResourceExistsError`, `ClientAuthenticationError`) that it derives from the response status and `error_code`. Classification keys on those structured attributes — never on the error *message* — a significant improvement over the S3 backends' fragile string-matching pattern (`"404" in msg.lower()`). Throttling (`429`, and server-side `503` ServerBusy) and `5xx` map to `BackendUnavailable` so a caller backing off on it catches a throttle, matching the Graph backend (GR-033/GR-034). `412` (precondition failed) has no dedicated `remote_store` error type and is not reachable through the public API (no `if_match` parameter is exposed), so it stays the generic base error.

**Note:** the classifier does not read `error_code` directly: the SDK has already consumed it to choose the exception subtype, and `status_code` distinguishes the remaining HTTP-shaped cases. The one place `error_code` is read explicitly is the inline `DirectoryIsNotEmpty` check in `delete()` (which has no distinct exception subtype). The earlier enumeration of per-status `error_code` strings has been dropped from this table as redundant.

### AZ-026: No Native Exception Leakage

**Invariant:** No `azure-storage-file-datalake`, `azure-core`, or `azure-identity` exceptions propagate to callers. All are mapped to `remote_store` error types per BE-021.
**Postconditions:** The `backend` attribute on mapped errors carries the backend's own `name`: `"azure"` for the sync `AzureBackend`, `"async-azure"` for the async `AsyncAzureBackend` twin (which classifies with `backend_name=self.name` throughout). The two twins are distinguishable by this attribute, matching the sync/async naming split used elsewhere.

### AZ-027: to_key

**Invariant:** `AzureBackend.to_key(native_path)` strips the `{container}/` prefix from native paths.
**Example:**
```python
backend = AzureBackend(container="my-container", account_name="myaccount")
backend.to_key("my-container/data/file.txt")  # -> "data/file.txt"
backend.to_key("data/file.txt")               # -> "data/file.txt" (no prefix, unchanged)
```
**Postconditions:** Pure, deterministic, total (never raises). Same contract as NPR-004.

### AZ-028: Error Context Manager

**Invariant:** A single `_errors(path)` context manager catches all Azure SDK exceptions and maps them per AZ-025.
**Rationale:** Unlike S3PyArrowBackend's dual error contexts (one for PyArrow, one for s3fs), this backend uses a single SDK, so a single error context suffices.

---

## Resource Management

### AZ-029: close()

**Invariant:** `close()` closes the underlying `BlobServiceClient`, `ContainerClient`, and (if HNS) `FileSystemClient` and `DataLakeServiceClient`. Resets all cached client instances. The declared `hns` value is immutable config and is not reset.
**Postconditions:** Safe to call multiple times. Note: because lazy properties re-initialize on next use, the backend is technically reusable after `close()`. This is consistent with S3Backend's behavior.

### AZ-030: unwrap()

**Invariant:** `unwrap(FileSystemClient)` returns the underlying `azure.storage.filedatalake.FileSystemClient`.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need Azure-specific features (per ADR-0003).

---

## Configuration

### AZ-034: ETag and Content-MD5 Digest Population

**Invariant:** `_props_to_fileinfo` populates `FileInfo.etag` and `FileInfo.digest` from blob properties.

**ETag (`FileInfo.etag`):**
- Source: `BlobProperties.etag` (always present for existing blobs).
- Azure returns it double-quoted (e.g. `'"0x8D4BCC2E4835CD0"'`); the backend strips the outer quotes and lowercases before storing.
- Populated for all operations that call `_props_to_fileinfo`: `get_file_info`, `list_files`, `iter_children`.

**Digest (`FileInfo.digest`):**
- Source: `BlobProperties.content_settings.content_md5` — a `bytes` object when set, `None` when absent.
- Azure does not auto-compute Content-MD5; it is set explicitly by the client at upload time. Blobs uploaded without Content-MD5 yield `digest=None`.
- When present: converted to lowercase hex and stored as `ContentDigest("md5", hex_value)`.

**Postconditions:**
- `FileInfo.etag` is a non-empty lowercase string for all existing blobs.
- `FileInfo.digest` is a `ContentDigest("md5", …)` when Content-MD5 is set, `None` otherwise.

---

### AZ-033: Transfer Concurrency

**Invariant:** `AzureBackend` accepts a `max_concurrency: int = 1` constructor parameter that controls the number of parallel connections used for blob uploads and downloads. The value is threaded through to `BlobClient.upload_blob()`, `BlobClient.download_blob()`, and `DataLakeFileClient.upload_data()` (HNS atomic writes).
**Preconditions:** `max_concurrency` must be >= 1; `ValueError` is raised at construction time otherwise.
**Default:** `1` (sequential transfer, matching prior behavior). Users opt in to parallelism for large-file workloads.
**Rationale:** The Azure SDK natively supports parallel block uploads and parallel chunk downloads. Exposing this parameter lets users improve throughput for large files without changing application code. SFTP has no equivalent (Paramiko is sequential); S3 concurrency is controlled at the `s3fs`/`aiobotocore` level.

---

### AZ-031: Client Options Passthrough

**Invariant:** The `client_options` dict is merged into both the `BlobServiceClient` and `DataLakeServiceClient` configurations, allowing advanced settings (custom timeouts, retry policies, proxies, API version overrides, etc.).
**Postconditions:** Explicit constructor parameters (`account_key`, `sas_token`, `credential`, etc.) take precedence over keys in `client_options`.

### AZ-035: Staged-Block Upload Defaults

**Invariant:** `_blob_service` and `_datalake_service` set `max_block_size` and `max_single_put_size` to `_AZURE_BLOCK_SIZE` (1 MiB) via `setdefault`, and force `min_large_block_upload_threshold = 1` (1 byte — always stage). User-supplied `client_options` values take precedence (AZ-031).

**Rationale:** Bounds Azure SDK in-flight memory to ~2 × `_AZURE_BLOCK_SIZE` ≈ 2 MiB, within the streaming integrity threshold (65% × 7 MiB minimum file). `_AZURE_BLOCK_SIZE` is kept separate from `_COPY_BUFSIZE` (the pipe-layer copy buffer) because HTTP block granularity and Python-level streaming are independent concerns.

### AZ-032: Default Credential Chain

**Invariant:** When no explicit credential is provided (`account_key`, `sas_token`, `connection_string`, and `credential` are all `None`), the backend attempts to use `DefaultAzureCredential` from `azure-identity`.
**Raises:** `BackendUnavailable` if `azure-identity` is not installed and no explicit credential is provided.
**Rationale:** Follows the principle of least surprise for Azure users. `DefaultAzureCredential` automatically resolves environment variables, managed identity, Azure CLI login, and other credential sources.

### AZ-036: HNS Directory-Marker Probe Contract

**Invariant (HNS only):** Every file-API operation on HNS — `read`, `read_bytes`, `read_seekable`, `delete`, `write`, `write_atomic`, `open_atomic`, `get_file_info`, `is_file`, `move(src, dst)`, `copy(src, dst)` — probes the `hdi_isfolder` metadata marker on the target before delegating to the SDK. If the marker is present on what the caller treats as a file path, the operation raises `InvalidPath` (BE-021) without mutating account state. Symmetric for folder-API operations on file paths: `delete_folder` and `get_folder_info` inspect the same marker and raise `InvalidPath` when it is absent on the target. `is_folder` and `is_file` are predicates and return `False` (not raise) when the marker disagrees with the call — see [AZ-013](#az-013-is_file-and-is_folder) for the predicate contract.
**Rationale:** Real ADLS Gen2 accepts SDK calls Azurite correctly rejects: `download_blob()`, `delete_blob()`, `get_blob_properties()`, `get_directory_properties()` all return HTTP 200 against the wrong entity type. Without the probe, file-API `delete()` on a directory marker silently destroys the directory; file-API `read()` silently returns `b""`; folder-API `delete_folder()` on a file path silently destroys the file. The probe is the single load-bearing safety invariant that closes the BE-021 type-mismatch contract on HNS.
**Probe placement:** Sync `read()` and `read_seekable()` pre-probe via `BlobClient.get_blob_properties()` (HEAD) before opening the stream — the stream is lazy and may never be drained, so a post-probe would leak the response. Async `read()` post-probes via `downloader.properties` (populated by the awaited `download_blob`) and explicitly closes the downloader before raising so the unconsumed HTTP body is returned to the pool — no separate HEAD round-trip is incurred. `read_bytes()` post-probes (the full body has already been read). Sync and async `delete()` pre-probe so the marker is preserved on the failure path. Folder-API operations probe `DataLakeDirectoryClient.get_directory_properties().metadata.hdi_isfolder` and treat absence-of-marker as "this is a file, not a folder." Root-path carve-out: `get_folder_info("")` skips the per-path probe entirely (see [AZ-024](#az-024-get_folder_info)) — the root is always a folder and the SDK rejects the empty path.
**Postconditions:** Adds one HEAD round-trip per affected sync read/delete call on HNS; async paths reuse the eager-awaited SDK response for the probe (no extra RTT).
**Originated in:** BUG-190, BUG-192 (write/open_atomic), then extended by BUG-195 (get_file_info), BUG-197 (read/delete), BUG-198 (folder-API on file), BUG-200 (move/copy directory checks), BUG-203 (is_file/is_folder).

### AZ-037: Concurrent-Use Posture

**Invariant:** `AzureBackend` is `thread_safe` (the BE-028 default): a single instance is safe to share across threads. The Azure SDK service clients (`BlobServiceClient`, `DataLakeServiceClient`) are immutable after construction and documented safe for concurrent use; per-blob operations are atomic at the object level. The async sibling `AsyncAzureBackend` meets the async mirror [ASYNC-094](029-async-store-backend-api.md#async-094): safe for concurrent coroutines on one loop, never across loops. On non-HNS accounts `move` is a non-atomic copy-then-delete (BE-018); HNS rename is server-side but still not transactional across a concurrent racer.

**See also:** [003-backend-adapter-contract.md](003-backend-adapter-contract.md) (BE-028), [029-async-store-backend-api.md](029-async-store-backend-api.md) (ASYNC-094).
