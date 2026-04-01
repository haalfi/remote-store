# Async Store and Backend API Specification

## Status

Accepted -- Phase 1 and Phase 2 implemented in ``remote_store.aio``.
Amended with research round 2 §2.4 items and Phase 2 spec.

## Overview

`AsyncBackend` and `AsyncStore` are the async equivalents of `Backend` ([003](003-backend-adapter-contract.md)) and `Store` ([001](001-store-api.md)). `SyncBackendAdapter` bridges sync backends into the async world via `asyncio.to_thread()`. Phase 2 adds `AsyncAzureBackend` — the first native async backend. See [ADR-0012](../adrs/0012-async-store-backend-api.md) for design rationale.

---

## AsyncBackend ABC

### ASYNC-001: Abstract Base Class

**Invariant:** `AsyncBackend` is an ABC. Subclasses must implement all abstract methods.
**See also:** [BE-001](003-backend-adapter-contract.md).

### ASYNC-002: Name Property

**Invariant:** `name` property returns a unique identifier string for the backend type. Sync — no I/O.
**See also:** [BE-002](003-backend-adapter-contract.md).

### ASYNC-003: Capabilities Property

**Invariant:** `capabilities` property returns a `CapabilitySet`. Sync — no I/O.
**See also:** [BE-003](003-backend-adapter-contract.md).

### ASYNC-004: exists()

**Invariant:** `async def exists(path) -> bool`. Returns `False` for missing paths — never raises `NotFound`.
**See also:** [BE-004](003-backend-adapter-contract.md).

### ASYNC-005: is_file() / is_folder()

**Invariant:** `async def is_file(path) -> bool` and `async def is_folder(path) -> bool`. Both return `False` for non-existent paths.
**See also:** [BE-005](003-backend-adapter-contract.md).

### ASYNC-006: read()

**Invariant:** `async def read(path) -> AsyncIterator[bytes]`. Returns an async iterator of byte chunks for the file content.
**Raises:** `NotFound` if the file does not exist.
**See also:** [BE-006](003-backend-adapter-contract.md), ASYNC-020.

### ASYNC-007: read_bytes()

**Invariant:** `async def read_bytes(path) -> bytes`. Returns the full file content as bytes.
**Raises:** `NotFound` if the file does not exist.
**See also:** [BE-007](003-backend-adapter-contract.md).

### ASYNC-008: write()

**Invariant:** `async def write(path, content, *, overwrite=False)` creates or overwrites a file.
**Preconditions:** `content` is `bytes` or `AsyncIterator[bytes]` (see ASYNC-021).
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.
**See also:** [BE-008](003-backend-adapter-contract.md).

### ASYNC-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.
**See also:** [BE-009](003-backend-adapter-contract.md).

### ASYNC-010: write_atomic()

**Invariant:** `async def write_atomic(path, content, *, overwrite=False)` writes via a temporary file + atomic rename.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.
**See also:** [BE-010](003-backend-adapter-contract.md), [007-atomic-writes.md](007-atomic-writes.md).

### ASYNC-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.
**See also:** [BE-011](003-backend-adapter-contract.md).

### ASYNC-012: delete()

**Invariant:** `async def delete(path, *, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`.
**See also:** [BE-012](003-backend-adapter-contract.md).

### ASYNC-013: delete_folder()

**Invariant:** `async def delete_folder(path, *, recursive=False, missing_ok=False)` removes a folder.
**Raises:** `NotFound` if the folder is missing and `missing_ok=False`. Fails if folder is non-empty and `recursive=False`.
**See also:** [BE-013](003-backend-adapter-contract.md).

### ASYNC-014: list_files()

**Invariant:** `async def list_files(path, *, recursive=False, max_depth=None) -> AsyncIterator[FileInfo]`.
**Postconditions:** Returns only files, not folders. If `recursive=True`, includes files in all subdirectories. `max_depth` limits traversal depth (when set, `recursive` is ignored).
**See also:** [BE-014](003-backend-adapter-contract.md), [037-depth-limited-listing.md](037-depth-limited-listing.md) (DEPTH-003).

### ASYNC-015: list_folders()

**Invariant:** `async def list_folders(path) -> AsyncIterator[FolderEntry]` of immediate subfolders. The `AsyncBackend` ABC does not accept `max_depth` — depth expansion is an `AsyncStore`-level concern (see ASYNC-052b).
**See also:** [BE-015](003-backend-adapter-contract.md).

### ASYNC-016: get_file_info()

**Invariant:** `async def get_file_info(path) -> FileInfo`.
**Raises:** `NotFound` if the file does not exist.
**See also:** [BE-016](003-backend-adapter-contract.md).

### ASYNC-017: get_folder_info()

**Invariant:** `async def get_folder_info(path) -> FolderInfo`. The `AsyncBackend` ABC does not accept `max_depth` — depth-limited aggregation is an `AsyncStore`-level concern (see ASYNC-052c).
**Raises:** `NotFound` if the folder does not exist.
**See also:** [BE-017](003-backend-adapter-contract.md).

### ASYNC-018: move()

**Invariant:** `async def move(src, dst, *, overwrite=False)` renames/moves a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.
**See also:** [BE-018](003-backend-adapter-contract.md).

### ASYNC-019: copy()

**Invariant:** `async def copy(src, dst, *, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.
**See also:** [BE-019](003-backend-adapter-contract.md).

### ASYNC-020: Async Streaming Reads

**Invariant:** `read()` returns `AsyncIterator[bytes]`. Caller consumes with `async for chunk in stream`. The iterator is not seekable. Chunk size is backend-defined (typically 65536 bytes). `read_bytes()` is the convenience method for loading the full content into memory.
**Rationale:** There is no standard `AsyncBinaryIO` in Python. `AsyncIterator[bytes]` is the idiomatic async streaming pattern (httpx, aiohttp).
**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-001), [ADR-0012](../adrs/0012-async-store-backend-api.md).

### ASYNC-021: Async Writable Content

**Invariant:** `AsyncWritableContent = bytes | AsyncIterator[bytes]`. Write operations accept either type. If `AsyncIterator[bytes]` is provided, the backend consumes it to EOF. If `bytes` is provided, the full byte string is written.
**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-003).

### ASYNC-022: aclose()

**Invariant:** `async def aclose()` is optional (default no-op). Called for resource cleanup. Named `aclose` per Python convention (async generators, `asyncio.StreamWriter`).
**See also:** [BE-020](003-backend-adapter-contract.md).

### ASYNC-023: Async Context Manager

**Invariant:** `AsyncBackend` supports `async with`. `__aenter__` returns `self`. `__aexit__` calls `aclose()`.

### ASYNC-024: Error Mapping

**Invariant:** Backend-native exceptions never leak. All exceptions are mapped to `remote_store` error types.
**See also:** [BE-021](003-backend-adapter-contract.md), [005-error-model.md](005-error-model.md).

### ASYNC-025: unwrap()

**Invariant:** `unwrap(type_hint)` returns the native backend handle if it matches the requested type. **Sync** — returns a cached handle, no I/O.
**Raises:** `CapabilityNotSupported` if the backend cannot provide the requested type.
**See also:** [BE-022](003-backend-adapter-contract.md).

### ASYNC-026: to_key()

**Invariant:** `to_key(native_path)` converts a backend-native path to a backend-relative key. **Sync** — pure string manipulation, no I/O.
**See also:** [BE-023](003-backend-adapter-contract.md).

### ASYNC-027: native_path()

**Invariant:** `native_path(path)` converts a backend-relative key to the backend-native path. **Sync** — pure string manipulation, no I/O.
**See also:** [BE-025](003-backend-adapter-contract.md).

### ASYNC-028: glob()

**Invariant:** `async def glob(pattern) -> AsyncIterator[FileInfo]`. Non-abstract — the default implementation raises `CapabilityNotSupported`. Backends with native glob support override and declare `Capability.GLOB`.
**See also:** [BE-024](003-backend-adapter-contract.md), [018-glob.md](018-glob.md).

### ASYNC-029: iter_children()

**Invariant:** `async def iter_children(path) -> AsyncIterator[FileInfo | FolderEntry]` — files as `FileInfo`, folders as `FolderEntry`. Concrete method with a default implementation that chains `list_files(path)` and `list_folders(path)`.
**See also:** [BE-026](003-backend-adapter-contract.md), [027-iter-children.md](027-iter-children.md).

### ASYNC-057: check_health()

**Invariant:** `async def check_health() -> None` is a concrete method (default no-op). Native async backends override to verify connectivity (e.g., container probe). `SyncBackendAdapter` delegates to the sync backend's `check_health()` via `asyncio.to_thread()` (see ASYNC-037).
**See also:** [026-health-check.md](026-health-check.md).

### ASYNC-058: resolve()

**Invariant:** `def resolve(path) -> ResolutionPlan` is a concrete method with a default implementation. **Sync** — pure introspection, no I/O. Returns a frozen `ResolutionPlan` with `kind`, `backend`, `key`, `native_path`, and `details`.
**See also:** [043-resolution-plan.md](043-resolution-plan.md) (RES-020).

---

## SyncBackendAdapter

### ASYNC-030: Adapter Construction

**Invariant:** `SyncBackendAdapter(backend: Backend)` wraps any sync `Backend` as an `AsyncBackend`. The adapter is itself an `AsyncBackend` subclass.

### ASYNC-031: Thread Delegation

**Invariant:** All I/O methods delegate to the wrapped sync backend via `asyncio.to_thread()`. Each call runs in the default executor's thread pool.

### ASYNC-032: Iterator Materialization

**Invariant:** `list_files()`, `list_folders()`, `glob()`, and `iter_children()` collect the sync iterator to a list in the thread, then yield items one by one from the async generator. This materializes the full result set in memory.
**Rationale:** Python cannot yield values across a thread boundary. Native async backends (Phase 2) stream without materialization.

### ASYNC-033: Streaming Read Bridging

**Invariant:** `read()` opens the sync `BinaryIO` stream via `asyncio.to_thread()`, then reads fixed-size chunks (65536 bytes) via `asyncio.to_thread(stream.read, 65536)` in a loop, yielding each chunk. The stream is closed in a `finally` block via `asyncio.to_thread(stream.close)`.

### ASYNC-034: Property Passthrough

**Invariant:** `name`, `capabilities`, `to_key()`, `unwrap()`, `native_path()`, and `resolve()` delegate directly to the wrapped backend without `asyncio.to_thread()` — they are sync, non-I/O properties/methods.

### ASYNC-035: aclose() Delegation

**Invariant:** `aclose()` calls `await asyncio.to_thread(self._sync.close)`.

### ASYNC-036: Streaming Write Bridging

**Invariant:** `write()` and `write_atomic()` materialize `AsyncIterator[bytes]` content to `bytes` via an internal `_materialize()` helper before delegating to the sync backend. The sync `write()` receives a single `bytes` object, not an iterator.
**Rationale:** Sync backends accept `bytes | BinaryIO` — there is no way to stream an `AsyncIterator` across the thread boundary. Native async backends (Phase 2) handle `AsyncIterator[bytes]` directly.

### ASYNC-037: check_health() Delegation

**Invariant:** `check_health()` delegates to `await asyncio.to_thread(self._sync.check_health)`.

---

## AsyncStore

### ASYNC-040: Construction

**Invariant:** `AsyncStore(backend: AsyncBackend | Backend, root_path: str = "")`. If `backend` is a sync `Backend` (and not an `AsyncBackend`), it is auto-wrapped via `SyncBackendAdapter`. A non-empty `root_path` is validated and normalized via `RemotePath`.
**See also:** [STORE-001](001-store-api.md), ASYNC-030.

### ASYNC-041: Path Validation

**Invariant:** Non-empty path arguments are validated via `RemotePath`. Empty string `""` and `"."` are both accepted as root aliases by folder/query methods. File-targeted methods reject empty path or `"."`.
**See also:** [STORE-002](001-store-api.md).

### ASYNC-042: Root Path Scoping

**Invariant:** `AsyncStore` prepends `root_path` to all relative paths before delegating to the async backend.
**See also:** [STORE-003](001-store-api.md).

### ASYNC-043: Delegation

**Invariant:** All I/O is delegated to the `AsyncBackend`. `AsyncStore` adds no I/O logic of its own.
**See also:** [STORE-004](001-store-api.md).

### ASYNC-044: Capability Check

**Invariant:** `supports(capability)` checks whether the backend supports a capability. **Sync** — no I/O.
**See also:** [STORE-005](001-store-api.md).

### ASYNC-045: Capability Gating

**Invariant:** Capability-gated methods raise `CapabilityNotSupported` before delegating if the capability is missing. For methods that return `AsyncIterator` (`read`, `list_files`, `list_folders`, `iter_children`, `glob`), validation happens eagerly on call (these are regular ``def`` methods that validate, then return an inner async generator), not lazily on first iteration.
**See also:** [STORE-006](001-store-api.md).

### ASYNC-046: Full API Surface

**Invariant:** `AsyncStore` exposes async equivalents of all `Store` methods: `read`, `read_bytes`, `read_text`, `write`, `write_text`, `write_atomic`, `delete`, `delete_folder`, `exists`, `is_file`, `is_folder`, `iter_children`, `list_files`, `list_folders`, `glob`, `get_file_info`, `get_folder_info`, `move`, `copy`, `ping`, `resolve`, `aclose`, `supports`, `to_key`, `native_path`, `unwrap`, `child`.
**Deferred:** `read_seekable` and `open_atomic` are not available in the async API — see ASYNC-061, ASYNC-062.
**See also:** [STORE-008](001-store-api.md).

### ASYNC-047: Same-Path Move and Copy

**Invariant:** `move(src, dst)` or `copy(src, dst)` where `src` and `dst` resolve to the same path is a no-op. The source must be an existing file; otherwise `NotFound` is raised.
**See also:** [STORE-008a](001-store-api.md).

### ASYNC-048: Resource Management

**Invariant:** `AsyncStore` supports the async context manager protocol (`__aenter__` / `__aexit__`). Exiting the context calls `aclose()`, which delegates to `AsyncBackend.aclose()` if the store owns the backend. Stores created via `child()` do not own the backend — their `aclose()` is a no-op.
**See also:** [STORE-009](001-store-api.md), [CHILD-006](015-store-child.md).

### ASYNC-049: Equality

**Invariant:** Two `AsyncStore` instances are equal if they share the same backend instance and have the same root path.
**See also:** [STORE-010](001-store-api.md).

### ASYNC-050: to_key()

**Invariant:** `to_key(path)` converts an absolute or backend-native path to a store-relative key. **Sync** — same composition as `Store.to_key()`.
**Raises:** `InvalidPath` if the path does not belong to this store.
**See also:** [STORE-011](001-store-api.md).

### ASYNC-051: native_path()

**Invariant:** `native_path(key)` converts a store-relative key to the backend-native path. **Sync** — same composition as `Store.native_path()`.
**See also:** [STORE-015](001-store-api.md).

### ASYNC-052: list_files(pattern=)

**Invariant:** `list_files(path, *, recursive=False, pattern=None)` accepts an optional `pattern` keyword. Files whose name does not match the pattern (via `fnmatch.fnmatch`) are excluded. Filtering is applied at the AsyncStore level after path rebasing.
**See also:** [STORE-014](001-store-api.md), [018-glob.md](018-glob.md) (GLOB-001).

### ASYNC-053: glob()

**Invariant:** `glob(pattern)` is capability-gated on `Capability.GLOB`. Pattern is relative to the store root; `AsyncStore` prepends `root_path` before delegating. Returned `FileInfo.path` values are store-relative.
**See also:** [STORE-015](001-store-api.md), [018-glob.md](018-glob.md).

### ASYNC-054: child()

**Invariant:** `child(subpath) -> AsyncStore`. Returns a new `AsyncStore` scoped to a subfolder. Same semantics as `Store.child()`: shared backend identity, composed root path, no-op `aclose()`, supports chaining.
**See also:** [015-store-child.md](015-store-child.md) (CHILD-001 through CHILD-011).

### ASYNC-052a: write_text()

**Invariant:** `async def write_text(path, text, *, encoding="utf-8", overwrite=False)` encodes the string and delegates to `write()`. Convenience method — no separate backend call.

### ASYNC-052b: list_folders(max_depth=)

**Invariant:** `list_folders(path, *, max_depth=None)` accepts an optional `max_depth` keyword. Depth expansion is implemented at the `AsyncStore` level via BFS traversal over the backend's `list_folders()`. `max_depth=None` returns immediate subfolders only (same as omitting).
**See also:** [037-depth-limited-listing.md](037-depth-limited-listing.md) (DEPTH-002).

### ASYNC-052c: get_folder_info(max_depth=)

**Invariant:** `get_folder_info(path, *, max_depth=None)` accepts an optional `max_depth` keyword for depth-limited aggregation. Implemented at the `AsyncStore` level.
**See also:** [037-depth-limited-listing.md](037-depth-limited-listing.md).

### ASYNC-052d: resolve()

**Invariant:** `resolve(key) -> ResolutionPlan` is **sync** — no I/O. Delegates to `backend.resolve()` and rebases the key to store-relative. Same composition as `Store.resolve()`.
**See also:** [043-resolution-plan.md](043-resolution-plan.md) (RES-010, RES-025).

### ASYNC-052e: ping()

**Invariant:** `async def ping()` verifies backend connectivity. Delegates to `await backend.check_health()`. The threading concern is handled by the backend layer: `SyncBackendAdapter.check_health()` uses `asyncio.to_thread()` (ASYNC-037); native async backends execute directly.
**Raises:** `PermissionDenied` if credentials are invalid. `NotFound` if the bucket, container, or root path does not exist. `BackendUnavailable` if the backend cannot be reached.
**See also:** [026-health-check.md](026-health-check.md).

### ASYNC-055: Concurrency Safety

**Invariant:** `AsyncStore` is safe for concurrent coroutines on the same event loop. It is not safe across multiple event loops (each event loop requires its own `AsyncStore` instance).

### ASYNC-056: No New Dependencies

**Invariant:** Phase 1 uses only stdlib `asyncio`. No dependency on anyio, trio, or any third-party async library.
**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-006), [ADR-0012](../adrs/0012-async-store-backend-api.md).

---

## Deferred (async API gaps)

### ASYNC-061: read_seekable() Deferral

`read_seekable()` is not available in the async API. Python has no standard async seekable stream protocol. Callers should use `read_bytes()` + `io.BytesIO()` for small files, or native async SDK features for large files via a native async backend.
**See also:** [036-seekable-read.md](036-seekable-read.md), research round 2 §3.1.

### ASYNC-062: open_atomic() Deferral

`open_atomic()` is not available in the async API. The incremental-write-to-file context-manager pattern is inherently sync. Use `write_atomic(path, content)` with `bytes | AsyncIterator[bytes]` instead.
**See also:** research round 2 §3.2.

## Deferred (future phases)

- Native async backends for remaining backends (`AsyncS3Backend`, `AsyncSFTPBackend`) — future specs.
- Async extensions (`async_batch`, `async_transfer`, `AsyncObservedStore`) — Phase 3, separate specs. Dagster `AsyncIOManager` blocked until Dagster exposes a public async IO manager interface.
- anyio / trio support — future ADR if demand materializes.
- `AsyncRegistry` — Phase 3, if needed for coordinated async lifecycle.

---

## Phase 2: AsyncAzureBackend

Native async Azure backend using `azure.storage.blob.aio` and `azure.storage.filedatalake.aio`. Implemented in `remote_store.aio._async_azure`. See [012-azure-backend.md](012-azure-backend.md) for the sync counterpart.

### ASYNC-070: Dual-Mode Architecture

**Invariant:** `AsyncAzureBackend` supports both plain Blob Storage and ADLS Gen2 (HNS-enabled) accounts. HNS is detected lazily on first I/O via `_ensure_hns()` and cached. Non-HNS accounts use the Blob SDK (`BlobServiceClient`, `ContainerClient`). HNS accounts use the DataLake SDK (`DataLakeServiceClient`, `FileSystemClient`).
**See also:** [012-azure-backend.md](012-azure-backend.md) (AZ-002).

### ASYNC-071: Lazy Client Initialization

**Invariant:** All four SDK clients (`_blob_service`, `_cc`, `_datalake_service`, `_fs`) are created lazily on first access. This avoids I/O during construction and allows the backend to be instantiated outside an event loop.

### ASYNC-072: Atomic Write Strategy

**Invariant:** `write_atomic()` uses different strategies per account type:
- **Non-HNS:** Direct `upload_blob()` is atomic (single PUT semantics).
- **HNS:** Write to a temporary file (`.~tmp.{basename}.{uuid4[:8]}`), then atomic rename via DFS `rename_file()`.

**See also:** [007-atomic-writes.md](007-atomic-writes.md), [012-azure-backend.md](012-azure-backend.md) (AZ-006).

### ASYNC-073: Move and Copy

**Invariant:** `move()` uses atomic `rename_file()` on HNS accounts, or server-side `start_copy_from_url()` + delete on non-HNS. `copy()` uses `start_copy_from_url()` on both.
**See also:** [012-azure-backend.md](012-azure-backend.md) (AZ-011, AZ-012).

### ASYNC-074: Content Materialization

**Invariant:** `write()` and `write_atomic()` materialize `AsyncIterator[bytes]` to `bytes` before calling `upload_blob()` / `upload_data()`. The Azure SDK async upload methods do not support streaming from an `AsyncIterator`.

### ASYNC-075: check_health() Override

**Invariant:** `check_health()` probes the container (non-HNS: `get_container_properties()`) or filesystem (HNS: `get_file_system_properties()`).
**Raises:** `PermissionDenied` if credentials are invalid. `NotFound` if the container does not exist. `BackendUnavailable` if the backend cannot be reached.

### ASYNC-076: Capabilities

**Invariant:** `AsyncAzureBackend` declares all capabilities except `SEEKABLE_READ`. Same capability set as the sync `AzureBackend`.
**See also:** [012-azure-backend.md](012-azure-backend.md) (AZ-001).

### ASYNC-077: Shared Helpers

**Invariant:** `_azure_common.py` contains sync/async-shared utilities: error classification (`classify_azure_error()`), retry policy application, credential resolution, and path normalization. Both `AzureBackend` and `AsyncAzureBackend` import from this module.
**Rationale:** Eliminates code duplication between sync and async Azure backends.

### ASYNC-078: Resource Cleanup

**Invariant:** `aclose()` closes all four lazily-created SDK clients and any auto-created async credential. Safe to call multiple times. Idempotent.

### ASYNC-079: Error Mapping

**Invariant:** All Azure SDK exceptions are mapped to `remote_store` error types via `classify_azure_error()` from `_azure_common`. Same mapping as the sync `AzureBackend`.
**See also:** [012-azure-backend.md](012-azure-backend.md) (AZ-013 through AZ-016), [005-error-model.md](005-error-model.md).
