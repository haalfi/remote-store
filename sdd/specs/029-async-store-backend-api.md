# Async Store and Backend API Specification

## Status

Draft -- pending second research round to validate design against current
sync API surface before implementation proceeds.

## Overview

`AsyncBackend` and `AsyncStore` are the async equivalents of `Backend` ([003](003-backend-adapter-contract.md)) and `Store` ([001](001-store-api.md)). `SyncBackendAdapter` bridges sync backends into the async world via `asyncio.to_thread()`. This spec covers Phase 1 scope only — native async backends and async extensions are future specs. See [ADR-0012](../adrs/0012-async-store-backend-api.md) for design rationale.

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

**Invariant:** `async def list_files(path, *, recursive=False) -> AsyncIterator[FileInfo]`.
**Postconditions:** Returns only files, not folders. If `recursive=True`, includes files in all subdirectories.
**See also:** [BE-014](003-backend-adapter-contract.md).

### ASYNC-015: list_folders()

**Invariant:** `async def list_folders(path) -> AsyncIterator[str]` of immediate subfolder names.
**See also:** [BE-015](003-backend-adapter-contract.md).

### ASYNC-016: get_file_info()

**Invariant:** `async def get_file_info(path) -> FileInfo`.
**Raises:** `NotFound` if the file does not exist.
**See also:** [BE-016](003-backend-adapter-contract.md).

### ASYNC-017: get_folder_info()

**Invariant:** `async def get_folder_info(path) -> FolderInfo`.
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

**Invariant:** `async def iter_children(path) -> AsyncIterator[FileInfo | str]` — files as `FileInfo`, folders as `str` names. Concrete method with a default implementation that chains `list_files(path)` and `list_folders(path)`.
**See also:** [BE-026](003-backend-adapter-contract.md), [027-iter-children.md](027-iter-children.md).

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

**Invariant:** `name`, `capabilities`, `to_key()`, `unwrap()`, and `native_path()` delegate directly to the wrapped backend without `asyncio.to_thread()` — they are sync, non-I/O properties/methods.

### ASYNC-035: aclose() Delegation

**Invariant:** `aclose()` calls `await asyncio.to_thread(self._sync.close)`.

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

**Invariant:** Capability-gated methods raise `CapabilityNotSupported` before delegating if the capability is missing.
**See also:** [STORE-006](001-store-api.md).

### ASYNC-046: Full API Surface

**Invariant:** `AsyncStore` exposes async equivalents of all `Store` methods: `read`, `read_bytes`, `read_text`, `write`, `write_atomic`, `delete`, `delete_folder`, `exists`, `is_file`, `is_folder`, `iter_children`, `list_files`, `list_folders`, `glob`, `get_file_info`, `get_folder_info`, `move`, `copy`, `aclose`, `supports`, `to_key`, `native_path`, `unwrap`, `child`.
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

### ASYNC-055: Concurrency Safety

**Invariant:** `AsyncStore` is safe for concurrent coroutines on the same event loop. It is not safe across multiple event loops (each event loop requires its own `AsyncStore` instance).

### ASYNC-056: No New Dependencies

**Invariant:** Phase 1 uses only stdlib `asyncio`. No dependency on anyio, trio, or any third-party async library.
**See also:** [006-streaming-io.md](006-streaming-io.md) (SIO-006), [ADR-0012](../adrs/0012-async-store-backend-api.md).

---

## Deferred (out of scope)

- Native async backends (`AsyncS3Backend`, `AsyncAzureBackend`, `AsyncSFTPBackend`) — Phase 2, separate specs.
- Async extensions (`async_batch`, `async_transfer`, `AsyncObservedStore`) — Phase 3, separate specs.
- anyio / trio support — future ADR if demand materializes.
- `AsyncRegistry` — Phase 3, if needed for coordinated async lifecycle.
