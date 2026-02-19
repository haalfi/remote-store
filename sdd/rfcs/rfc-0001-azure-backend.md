# RFC-0001: Azure Backend via Direct ADLS Gen2 SDK

## Status

Accepted

## Summary

Add an `AzureBackend` that implements the `Backend` ABC for Azure Storage using the `azure-storage-file-datalake` SDK directly, rather than the `adlfs` fsspec wrapper originally proposed in BK-001. The backend targets ADLS Gen2 (Hierarchical Namespace) accounts as the primary use case, while remaining fully functional against plain Blob Storage accounts without HNS enabled.

## Motivation

Azure Data Lake Storage Gen2 is the standard for analytics-grade storage on Azure. Users who adopt `remote-store` in Azure environments need a backend that leverages ADLS Gen2's native semantics — real directories, atomic rename, and per-path ACLs — rather than papering over them with a flat-blob abstraction.

The original backlog item (BK-001) proposed using `adlfs`, the fsspec wrapper. After evaluating both approaches against the lessons learned from the S3 backends, we chose the direct SDK path. See *Alternatives Considered* below for the full rationale.

## Proposal

### New backend: `AzureBackend`

**Module:** `remote_store.backends._azure`
**Optional extra:** `pip install remote-store[azure]`
**Dependencies:** `azure-storage-file-datalake`, `azure-identity` (optional, for `DefaultAzureCredential`)
**Spec:** `sdd/specs/012-azure-backend.md`

### Constructor

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

### HNS detection and adaptive behavior

On first use, the backend issues a single `GetAccountInfo` call to determine whether the storage account has Hierarchical Namespace enabled. The result is cached for the lifetime of the backend instance.

| Operation | HNS enabled (ADLS Gen2) | No HNS (plain Blob) |
|---|---|---|
| `write_atomic` | Temp file + atomic rename | Direct upload (PUT is atomic, same as S3) |
| `move` | Atomic `rename_file` | Copy + delete (same as S3) |
| `is_folder` | Native directory check | Prefix-based detection (same as S3) |
| `list_files` / `list_folders` | Native directory listing | Prefix-based listing |
| `delete_folder(recursive)` | Single recursive delete call | Iterate + delete each blob |

This is specified as AZ-006 in the spec.

### Capability declaration

All capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `GLOB`, `RECURSIVE_LIST`, `METADATA`.

`ATOMIC_WRITE` is declared for both account types: HNS provides true atomic rename; non-HNS provides atomic PUT (same guarantee as S3).

### Error mapping

Azure SDK exceptions are structured (`HttpResponseError` with `error_code` and `status_code`), enabling reliable error mapping without the fragile string-matching pattern used in the S3 backends:

| Azure SDK | remote_store |
|---|---|
| `status_code=404`, `BlobNotFound`, `PathNotFound`, `FilesystemNotFound` | `NotFound` |
| `status_code=403`, `AuthorizationFailure`, `AuthorizationPermissionMismatch` | `PermissionDenied` |
| `status_code=409`, `PathAlreadyExists`, `BlobAlreadyExists` | `AlreadyExists` |
| `ResourceExistsError` | `AlreadyExists` |
| `ResourceNotFoundError` | `NotFound` |
| Connection errors (`ServiceRequestError`, DNS, timeout) | `BackendUnavailable` |

This is a significant improvement over the S3 backends' `"404" in msg.lower()` pattern.

### `to_key` implementation

Strips the `{container}/` prefix from native paths (analogous to S3Backend stripping the bucket prefix). Specified as AZ-020 in the spec.

### `unwrap` support

`unwrap(FileSystemClient)` returns the underlying `azure.storage.filedatalake.FileSystemClient`. `CapabilityNotSupported` for any other type hint.

### New spec sections

The full spec (`012-azure-backend.md`) defines invariants AZ-001 through AZ-032, covering:
- Construction and validation (AZ-001 through AZ-005)
- HNS detection and adaptive behavior (AZ-006)
- Filesystem model (AZ-007 through AZ-011)
- Path inspection: exists, is_file, is_folder (AZ-012 through AZ-013)
- Operations: atomic write, delete, move, copy, glob, read, write, metadata (AZ-014 through AZ-024)
- Error mapping (AZ-025 through AZ-028)
- Resource management (AZ-029 through AZ-030)
- Configuration (AZ-031 through AZ-032)

## Alternatives Considered

### Option A: `adlfs` (fsspec wrapper)

This was the original BK-001 proposal and mirrors the S3Backend's use of `s3fs`. Rejected for the following reasons:

1. **Fragile error translation.** The S3 backends rely on string-matching exception messages (`"404" in msg.lower()`, `"nosuchkey"`) because s3fs/botocore does not expose structured error codes consistently. `adlfs` would have the same problem — errors from the underlying Azure SDK get wrapped and the structured codes are lost. The direct Azure SDK provides `HttpResponseError.status_code` and `error_code` attributes, enabling reliable error classification.

2. **The S3PyArrow precedent.** The project already went through the cycle of shipping an fsspec-based S3 backend (S3Backend via s3fs), then needing a hybrid variant (S3PyArrowBackend) to work around throughput limitations on the data path. Starting with adlfs would likely repeat this trajectory — ship a wrapper now, build a native variant later.

3. **Loss of ADLS Gen2 native semantics.** adlfs wraps `azure-storage-blob` under the hood and hides the ADLS Gen2 file/directory distinction. Key advantages are lost or attenuated:
   - **Atomic rename/move** — ADLS Gen2's strongest differentiator. adlfs may not use the native rename API in all code paths.
   - **True `write_atomic`** — With the direct SDK, temp-file + rename works natively (like LocalBackend), which is more robust than relying on PUT-level atomicity.
   - **Real directory operations** — Native `list_files`/`list_folders` without prefix hacking.

4. **Transitive dependency weight.** adlfs pulls in `azure-core`, `azure-identity`, `azure-storage-blob`, and `fsspec` as runtime dependencies. The direct SDK (`azure-storage-file-datalake`) also depends on `azure-core` and `azure-storage-blob` internally, but does not require `fsspec` — keeping the dependency footprint focused.

5. **Metadata dict inconsistency.** Like s3fs, adlfs returns unstructured info dicts with variant key names across versions, requiring fragile manual parsing (see S3Backend lines 143-159). The direct SDK returns typed `PathProperties` / `FileProperties` objects with stable attribute names.

### Option C: `azure-storage-blob` directly (flat blob API only)

Rejected because it would not support ADLS Gen2 semantics at all. Users with HNS-enabled accounts — the primary target audience — would lose atomic rename, real directories, and per-path ACLs. The `azure-storage-file-datalake` SDK works against both HNS and non-HNS accounts, making this a strictly inferior choice.

## Impact

- **Public API:** Adds `AzureBackend` to `__all__`. New optional extra `azure`.
- **Backwards compatibility:** Non-breaking. Purely additive.
- **Performance:** Direct SDK access avoids fsspec overhead. HNS accounts benefit from native directory operations (single-call recursive delete, atomic rename).
- **Testing:** Azurite (Azure Storage Emulator) for integration tests, following the pattern of moto for S3. Unit tests with mocked SDK clients.

## Open Questions

None — all design decisions resolved during review.

## References

- Backend contract: `sdd/specs/003-backend-adapter-contract.md`
- S3 backend spec (pattern reference): `sdd/specs/008-s3-backend.md`
- S3-PyArrow hybrid spec (precedent): `sdd/specs/011-s3-pyarrow-backend.md`
- Error model: `sdd/specs/005-error-model.md`
- Atomic writes: `sdd/specs/007-atomic-writes.md`
- fsspec ADR: `sdd/adrs/0003-fsspec-is-implementation-detail.md`
- Native path resolution: `sdd/specs/010-native-path-resolution.md` (NPR-009)
- Azure SDK docs: https://learn.microsoft.com/en-us/python/api/azure-storage-file-datalake/
- Azurite emulator: https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite
