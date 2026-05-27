# Async Store and Backend API Specification

## Status

Accepted — Phase 1 and Phase 2 implemented in ``remote_store.aio``.
Amended with research round 2 §2.4 items and Phase 2 spec.

## Overview

`AsyncBackend` and `AsyncStore` are the async equivalents of `Backend` ([003](003-backend-adapter-contract.md)) and `Store` ([001](001-store-api.md)). `SyncBackendAdapter` bridges sync backends into the async world via `asyncio.to_thread()`. `AsyncBackendSyncAdapter` is the inverse bridge — it exposes an `AsyncBackend` as a sync `Backend` via a private event loop on a dedicated background thread (see [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)). Phase 2 adds `AsyncAzureBackend` — the first native async backend. See [ADR-0012](../adrs/0012-async-store-backend-api.md) for design rationale.

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

**Invariant:** `async def write(path, content, *, overwrite=False, metadata=None) -> WriteResult` creates or overwrites a file and returns a `WriteResult`.
**Preconditions:** `content` is `bytes` or `AsyncIterator[bytes]` (see ASYNC-021).
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `InvalidPath` if `path` names an existing directory, or if any slash-aligned ancestor of `path` is a regular file (ID-209; flat-namespace backends opt in via the `reject_write_under_file_ancestor` kwarg — see BE-008 for the cross-reference and ID-211 for the per-call cost). `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out).
**See also:** [BE-008](003-backend-adapter-contract.md); [045-write-result.md](045-write-result.md) (WR-001, WR-004, WR-010). BE-008's precondition order — type check → file-ancestor check → overwrite conflict → I/O — applies verbatim here.

### ASYNC-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.
**See also:** [BE-009](003-backend-adapter-contract.md).

### ASYNC-010: write_atomic()

**Invariant:** `async def write_atomic(path, content, *, overwrite=False, metadata=None) -> WriteResult` writes via a temporary file + atomic rename and returns a `WriteResult`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `InvalidPath` if `path` names an existing directory, or if any slash-aligned ancestor of `path` is a regular file (ID-209; delegates to ASYNC-008's clause, including the ID-211 flat-namespace opt-in). `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out).
**See also:** [BE-010](003-backend-adapter-contract.md), [007-atomic-writes.md](007-atomic-writes.md); [045-write-result.md](045-write-result.md) (WR-001, WR-010). Same precondition order as ASYNC-008.

### ASYNC-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.
**See also:** [BE-011](003-backend-adapter-contract.md).

### ASYNC-012: delete()

**Invariant:** `async def delete(path, *, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`. `InvalidPath` if `path` names a directory, regardless of `missing_ok` — see [BE-012](003-backend-adapter-contract.md).
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
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory, or if any slash-aligned ancestor of `dst` is a regular file (ID-209; flat-namespace backends opt in via the `reject_write_under_file_ancestor` kwarg per BE-008 / ID-211). `AlreadyExists` if `dst` exists and `overwrite=False`.
**Precondition order:** Mirrors BE-018 — `src`-NotFound takes priority over dst-side preconditions; `move(missing_src, blocked_dst)` MUST raise `NotFound(src)`.
**See also:** [BE-018](003-backend-adapter-contract.md).

### ASYNC-019: copy()

**Invariant:** `async def copy(src, dst, *, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory, or if any slash-aligned ancestor of `dst` is a regular file (ID-209; flat-namespace backends opt in via the `reject_write_under_file_ancestor` kwarg per BE-008 / ID-211). `AlreadyExists` if `dst` exists and `overwrite=False`.
**Precondition order:** Mirrors BE-019 — `src`-NotFound takes priority over dst-side preconditions; `copy(missing_src, blocked_dst)` MUST raise `NotFound(src)`.
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

**Invariant:** `AsyncStore` exposes async equivalents of all `Store` methods: `read`, `read_bytes`, `read_text`, `write`, `write_text`, `write_atomic`, `delete`, `delete_folder`, `exists`, `is_file`, `is_folder`, `iter_children`, `list_files`, `list_folders`, `glob`, `get_file_info`, `get_folder_info`, `head`, `move`, `copy`, `ping`, `resolve`, `aclose`, `supports`, `to_key`, `native_path`, `unwrap`, `child`.
**Deferred:** `read_seekable` and `open_atomic` are not available in the async API — see ASYNC-061, ASYNC-062.
**See also:** [STORE-008](001-store-api.md); [045-write-result.md](045-write-result.md) (WR-001, WR-008) for `write*` return type widening and `head()` semantics; ASYNC-052f for the normative async `head()` invariant.

### ASYNC-047: Same-Path Move and Copy

**Invariant:** `move(src, dst)` or `copy(src, dst)` where `src` and `dst` resolve to the same path is a no-op. Precondition: `src` must name an existing file. `InvalidPath` if `src` names a directory; `NotFound` if `src` does not exist.
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

**Invariant:** `async def write_text(path, text, *, encoding="utf-8", overwrite=False, metadata=None) -> WriteResult` encodes the string and delegates to `write(path, encoded, overwrite=overwrite, metadata=metadata)`, forwarding the returned `WriteResult` unchanged. Convenience method — no separate backend call. `metadata` is a pass-through: the `USER_METADATA` capability gate and validation are applied inside `write()` (per WR-010 / WR-011).
**Raises:** `CapabilityNotSupported` before any I/O when a non-`None`, non-empty `metadata` mapping is passed and the backend does not declare `USER_METADATA` (per WR-010 empty-mapping carve-out).
**See also:** [045-write-result.md](045-write-result.md) (WR-001, WR-010) for the return-type widening and the `metadata=` capability gate.

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

### ASYNC-052f: head()

**Invariant:** `async def head(path) -> WriteResult` returns a sidecar
`WriteResult` constructed from the `FileInfo` returned by
`await self.get_file_info(path)`. Convenience method — no separate
backend call; implemented at the `AsyncStore` level using the same
`FileInfo → WriteResult` field mapping as the sync `Store.head()`.
**Gating:** Capability-gated on `Capability.METADATA` only; **not**
gated on `Capability.WRITE`.
**Raises:** `NotFound` if the path does not exist.
`CapabilityNotSupported` if the backend lacks `METADATA`.
**Postconditions:** Returns `WriteResult` with `source == "sidecar"`.
**See also:** [045-write-result.md](045-write-result.md) (WR-008) for
the full `FileInfo → WriteResult` field mapping and sync-parity
semantics.

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

Native async Azure backend using `azure.storage.blob.aio` and `azure.storage.filedatalake.aio`. Implemented in `remote_store.aio.backends._azure`. See [012-azure-backend.md](012-azure-backend.md) for the sync counterpart.

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

---

## AsyncBackendSyncAdapter

The inverse of `SyncBackendAdapter`: implements the sync `Backend` ABC by
delegating to a wrapped `AsyncBackend` running on a private event loop in a
dedicated background thread.  Lands in `src/remote_store/_async_to_sync_adapter.py`.
See [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md) for the decision
record. The invariants below pin the behaviours the ADR records in prose so
that the implementation test suite can trace every case to a stable spec ID
per `sdd/000-process.md` Rule 2.

### ASYNC-080: Single-chunk In-flight Pump

**Invariant:** The adapter has **at most one** outstanding `__anext__` (or
equivalent pull) per read stream and per listing iterator. No look-ahead, no
read-ahead pool, no parallel prefetch. The only sanctioned per-stream buffer
is the unread tail of the most recently fetched chunk held by the sync
`read()` stream (see ASYNC-081).
**Rationale:** Native-async backends exist precisely to stream. Materialising
ahead of the sync caller would reintroduce the memory blow-up the bridge is
designed to avoid.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Streaming iterators and open streams.

### ASYNC-081: `read()` `BinaryIO` Flavour and Short-read Semantics

**Invariant:** `Backend.read(path)` on the adapter returns a forward-only
`BinaryIO`-typed object whose `read(n)` returns **at most** *n* bytes, drawing
first from an internal tail buffer carrying the unread remainder of the most
recently fetched chunk, and submitting a new `__anext__` coroutine to the
private loop only when that buffer is empty and more bytes are still required.
`read(-1)` / `read()` drains to EOF.  The stream exposes `read`, `close`,
`seekable()` (returns `False`), and `readable()` (returns `True`); `seek`,
`tell`, and `fileno` are not provided.  `close()` submits the async
iterator's `aclose()` to the loop.
**Closed-stream reads:** Calling `read()` or `readinto()` after the caller
explicitly invokes `close()` raises `ValueError: I/O operation on closed file.`,
matching the `io.IOBase` contract.  Streams closed as a side effect of an
async error or adapter shutdown (see ASYNC-090) instead return `b""` / `0`
from subsequent `read()` / `readinto()` calls.  Error-close is sticky: if a
stream already transitioned to error-closed state, a subsequent caller-invoked
`close()` is a no-op per `io.IOBase` and does not switch the stream to the
user-closed (`ValueError`) contract.
**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-001, SIO-009),
ASYNC-080, ASYNC-090.

### ASYNC-082: Fail-fast on Running Event Loop

**Invariant:** Every blocking sync method checks `asyncio.get_running_loop()`
at entry. If a running loop is detected on the calling thread, the method
raises `RuntimeError` with a message stem
`"AsyncBackendSyncAdapter cannot be called from a running event loop"`
(suitable for `pytest.raises(RuntimeError, match=...)`).  The message
directs the caller to use `AsyncStore` instead. Detection is per-call,
not per-construction.
**Rationale:** The sync `Store` API is not coroutine-safe by design
(ADR-0012 § Async posture).  Fail-fast beats deadlock.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Behaviour when the caller is in a running loop.

### ASYNC-083: Closed-adapter Reuse

**Invariant:** After `close()` has been called, any subsequent sync method
call on the same adapter raises `RuntimeError` with message stem
`"AsyncBackendSyncAdapter is closed"` (stable for
`pytest.raises(RuntimeError, match=...)`). The adapter does **not** silently
restart the loop; it is a one-shot resource.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Lifecycle.

### ASYNC-084: Capability Translation Table

**Invariant (translation).** The adapter exposes `capabilities` derived
from the wrapped `AsyncBackend` with the following translation:

- **`SEEKABLE_READ`** — **masked off** unconditionally. The chunk-pull
  stream (ASYNC-081) is forward-only; no native `seek()` exists.
- **`LAZY_READ`** — **preserved** verbatim. The single-chunk in-flight
  invariant (ASYNC-080) keeps laziness end-to-end.
- **`ATOMIC_WRITE`, `ATOMIC_MOVE`, `GLOB`, and all remaining flags
  declared by the wrapped backend** — **preserved** verbatim.

No new capability flag is introduced.

**Invariant (gating).** Operations without a dedicated capability flag
remain available on the adapter exactly when the wrapped backend
declares the corresponding read / write capability:

- `list_folders` is gated by `LIST`; `delete_folder` by `DELETE`.
- `read_seekable` remains callable on the adapter even with
  `SEEKABLE_READ` masked off — SIO-008 requires every sync backend to
  support `Store.read_seekable()` regardless of the capability flag,
  and the adapter inherits the same spool fallback every non-seekable
  sync backend uses. The adapter contributes no seek accelerator of
  its own.

**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-008, SIO-009),
[ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md) § Capability
translation.

### ASYNC-085: `open_atomic` Spool-and-flush Synthesis

**Invariant:** `open_atomic(path, *, overwrite=False)` is synthesised by the
adapter as a context manager that yields a `tempfile.SpooledTemporaryFile`.
On clean `__exit__`, the spool is rewound and submitted to the wrapped
async backend's `write_atomic(path, <spool>, overwrite=overwrite)` (a single
`bytes`/`BinaryIO` write); on exception propagating through `__exit__`, the
spool is dropped and `path` is left untouched.
**Capability gate:** observed **on flush**, not on entry. Backends without
`ATOMIC_WRITE` raise `CapabilityNotSupported` when the spool is submitted
to `write_atomic`; the adapter forwards that error unchanged.
**See also:** [007-atomic-writes.md](007-atomic-writes.md),
[ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md) § Write-side
content.

### ASYNC-086: `unwrap()` Default and Sync-safe-handle Exemption

**Invariant:** `unwrap(type_hint)` raises `CapabilityNotSupported` by default,
because an async SDK handle (e.g. `httpx.AsyncClient`) returned from the
wrapped backend is bound to the adapter's private loop and is unsafe to use
from the caller's thread. A wrapped backend may expose a sync-safe handle
through an explicit protocol (mirroring `SyncBackendAdapter.unwrap`'s
exemption for wrappers that provide one); for such handles, the adapter
forwards the call and returns the sync-safe object unchanged.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Capability translation, [BE-022](003-backend-adapter-contract.md).

### ASYNC-087: Verbatim Error Propagation

**Invariant:** Exceptions raised by the wrapped async coroutine are re-raised
**verbatim** in the sync caller via
`concurrent.futures.Future.set_exception` → `Future.result()`.  The adapter
does not wrap, translate, or re-label exceptions.  Specifically:

- Error **type** is preserved (`NotFound` stays `NotFound`,
  `TimeoutError` stays `TimeoutError`, `ResourceLocked` stays
  `ResourceLocked`, `CapabilityNotSupported` stays
  `CapabilityNotSupported`, etc.).
- ERR-001 attributes (`path`, `backend`) survive unchanged.
- Traceback chain preservation follows standard
  `concurrent.futures` behaviour.

**See also:** [005-error-model.md](005-error-model.md) (ERR-001),
ADR-0012 § error-mapping rules.

### ASYNC-088: Lifecycle — `close(timeout)`

**Invariant:** `close(timeout: float | None = 30.0)` performs the
following drain order:

1. Submit `self._async_backend.aclose()` to the loop.
2. Wait for in-flight tasks (including the `aclose()` submission) to drain.
3. Call `loop.call_soon_threadsafe(loop.stop)`.
4. Join the daemon thread with the supplied bound.
5. Close the private event loop (`loop.close()`), releasing its self-pipe
   sockets.  After `close()` returns, `loop.is_closed()` is `True`.

If the timeout expires before the thread joins, the adapter logs one
record at `WARNING` level with message stem
`"AsyncBackendSyncAdapter close timed out"` (stable for
`caplog.messages` substring assertions), including the count and
`repr()` of the unfinished tasks; it then returns. The daemon thread
is reaped by process exit.  Passing `timeout=None` waits indefinitely.
`__exit__` delegates to `close()`.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Lifecycle.

### ASYNC-089: Concurrent-callers No-deadlock Invariant

**Invariant:** The adapter is safe for concurrent calls from multiple sync
threads. At least *N = 32* threads issuing mixed `read` / `write` / `list` /
`delete` / `copy` / `move` calls (*M ≥ 16* iterations per thread, each with a
caller-unique payload tag) on the same adapter instance all complete without
deadlock, and every call's `Future` resolves to the value/exception of the
coroutine submitted from that caller — no cross-thread result or exception
crossover is observable. Ordering between concurrent callers is **not**
guaranteed; callers that need deterministic ordering coordinate externally.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Ownership model.

### ASYNC-090: Async Iterator Failure Modes

**Invariant:** Failures originating on the async side during iterator
consumption propagate as follows:

- **Mid-stream `__anext__` raise** — the exception is re-raised verbatim
  from the current sync `read(n)` / `next()` / `list.__next__()` call
  (ASYNC-087).  The iterator / stream transitions to a closed-on-error
  state; subsequent `read(n)` returns `b""` / subsequent `next()` raises
  `StopIteration`.
- **Hung iterator at `close()`** — a `close()` with the configured
  `timeout` bound observes the hang, logs a warning per ASYNC-088, and
  returns rather than blocking indefinitely.
- **`aclose()` raise during shutdown** — logged at `WARNING` and
  swallowed; `close()` continues the drain sequence and joins the
  thread.  Exceptions during shutdown never mask the primary reason
  the caller invoked `close()`.

**See also:** ASYNC-080, ASYNC-087, ASYNC-088.

### ASYNC-091: Write-side `BinaryIO` Failure Mid-write

**Invariant:** When `write()` / `write_atomic()` is driven from a sync
`BinaryIO` whose `read()` raises mid-write, the exception surfaces
**verbatim** from the blocking sync call (ASYNC-087).  Partial-write
rollback follows the wrapped async backend's atomicity guarantee — the
adapter performs no rollback of its own.  For `write_atomic()` on a
backend with `ATOMIC_WRITE`, the destination `path` is untouched on
failure; for `write()`, whatever bytes reached the backend before the
exception are visible per that backend's non-atomic write semantics.
**See also:** [007-atomic-writes.md](007-atomic-writes.md),
[ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md) § Write-side
content.

### ASYNC-092: Sync Context-manager Protocol

**Invariant:** The adapter implements the sync context-manager protocol.
`__enter__` returns `self` and does **not** touch the wrapped async
backend's `__aenter__` / `__aexit__` — the async context manager is not
entered implicitly from sync code.  `__exit__` delegates to `close()`
with its default timeout, propagating any exception from the `with`
body unchanged.
**See also:** [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
§ Lifecycle.

### ASYNC-093: `check_health()` Propagates Connectivity Errors

**Invariant:** `check_health()` on the adapter submits
`await self._async_backend.check_health()` to the private loop and
blocks on the result. Connectivity errors raised by the wrapped
backend — `PermissionDenied`, `NotFound`, `BackendUnavailable`,
`TimeoutError` — reach the sync caller **verbatim** (ASYNC-087).
`check_health()` is **not** a no-op: the adapter performs no
connectivity probe of its own, but it also does not swallow the
backend's probe errors.
**See also:** [026-health-check.md](026-health-check.md), ASYNC-057,
ASYNC-087.
