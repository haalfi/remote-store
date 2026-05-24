<!-- doc: dual dest=reference/FEATURES.md -->
# Features — remote-store v0.25.0

Authoritative snapshot of what remote-store delivers in this version.
Updated each release. **This is the single reference for the package's feature surface.**

---

## What this package does

remote-store gives application code a single, portable file-storage API.
Write against `Store` once; swap the backend by changing one line of config —
the same `read()`, `write()`, and `list_files()` calls work across all supported
backends (see the [Backends](#backends) section).

Three primitives do all the work:

- **`Store`** wraps a backend and exposes capability-gated methods. An
  operation is available only if the backend supports it. Capability is
  queried at runtime with `store.supports(Capability.X)`, so code can
  adapt gracefully instead of failing at import time.
- **`Backend`** is the storage-specific adapter. Built-in backends cover the
  common targets; a public ABC makes it straightforward to add new ones.
- **`Registry`** loads named backend and store definitions from config
  (TOML, YAML, dict, or Pydantic models), resolves `${ENV_VAR}` placeholders,
  and wraps credentials in `Secret` automatically.

---

## Store API

Methods are grouped by the capability that gates them.
All methods share one invariant: they raise typed errors from `remote_store.errors`
and never leak backend-native exceptions to the caller.

### Ungated (always available)

| Method | Returns | Description |
|---|---|---|
| `exists(path)` | `bool` | Whether a file exists at the path |
| `is_file(path)` | `bool` | Whether the path resolves to a file (not a folder) |
| `is_folder(path)` | `bool` | Whether the path resolves to a folder |
| `ping()` | `None` | Health check — raises `BackendUnavailable` if unreachable |
| `close()` | `None` | Release backend resources |
| `child(subpath)` | `Store` | Scoped sub-store rooted at `subpath` |
| `unwrap(type_hint)` | `T` | Extract the underlying backend by type |
| `resolve(key)` | `ResolutionPlan` | Resolution plan for a key (type, resolved path, options) |
| `native_path(key)` | `str` | Backend-native path string for a store key |
| `to_key(path)` | `str` | Convert a native path back to a store key |
| `supports(capability)` | `bool` | Query whether a capability is active |

### READ

| Method | Returns | Description |
|---|---|---|
| `read(path)` | `BinaryIO` | Open a binary stream for reading; lazy where the backend supports `LAZY_READ` |
| `read_bytes(path)` | `bytes` | Read the entire file into memory |
| `read_text(path, *, encoding)` | `str` | Read the entire file as a decoded string |
| `read_seekable(path)` | `BinaryIO` | Seekable binary stream; spools to a temp file if the backend is non-seekable |

### WRITE

All write methods accept an optional `metadata=` mapping. If the backend
declares `Capability.USER_METADATA`, the mapping is persisted alongside the
file; otherwise a non-empty `metadata=` raises `CapabilityNotSupported`.
All write methods return a `WriteResult` (see Data Models).

| Method | Returns | Description |
|---|---|---|
| `write(path, content, *, overwrite, metadata)` | `WriteResult` | Create or overwrite a file from bytes or a binary stream |
| `write_text(path, text, *, encoding, overwrite, metadata)` | `WriteResult` | Write a string as a file |

### ATOMIC_WRITE

Atomic writes use a temp-and-rename strategy: no reader ever sees a partial
file, and a crash mid-write leaves the previous version intact.

| Method | Returns | Description |
|---|---|---|
| `write_atomic(path, content, *, overwrite, metadata)` | `WriteResult` | Atomic write from bytes or a stream |
| `open_atomic(path, *, overwrite, metadata)` | context manager → `WriteResult` | Streaming atomic write; `WriteResult` returned on `__exit__` |

### DELETE

| Method | Returns | Description |
|---|---|---|
| `delete(path, *, missing_ok)` | `None` | Remove a file; `missing_ok=True` suppresses `NotFound` |
| `delete_folder(path, *, recursive)` | `None` | Remove a folder; requires `recursive=True` if non-empty |

### LIST

| Method | Returns | Description |
|---|---|---|
| `list_files(path, *, max_depth, pattern)` | `Iterator[str]` | Enumerate file paths under a prefix; optional `pattern=` filters basenames via `fnmatch` |
| `list_folders(path, *, max_depth, pattern)` | `Iterator[str]` | Enumerate immediate subfolder paths; optional `pattern=` filters folder basenames via `fnmatch` |
| `iter_children(path)` | `Iterator[FileInfo \| FolderInfo]` | Iterate files and folders together, with metadata |

### GLOB

| Method | Returns | Description |
|---|---|---|
| `glob(pattern)` | `Iterator[str]` | Native glob pattern matching (`*`, `**`, `?`) on file paths |

Backends without native `GLOB` capability can use the `ext.glob` extension as a
portable fallback.

### MOVE / COPY

| Method | Returns | Description |
|---|---|---|
| `move(src, dst, *, overwrite)` | `None` | Rename or relocate within the same backend |
| `copy(src, dst, *, overwrite)` | `None` | Duplicate a file within the same backend |

### METADATA

| Method | Returns | Description |
|---|---|---|
| `head(path)` | `WriteResult` | File metadata without reading content (size, etag, last_modified, etc.) |
| `get_file_info(path)` | `FileInfo` | Full file metadata record |
| `get_folder_info(path)` | `FolderInfo` | Folder metadata with aggregate file count and total size |

---

## Data Models

All models are importable from `remote_store` and are frozen dataclasses.

### `WriteResult`

Returned by every write method and by `head()`.

| Field | Type | Populated when |
|---|---|---|
| `path` | `str` | Always |
| `size` | `int` | Always |
| `source` | `WriteSource` | Always (`NativeSource`, `BasicSource`, or `SidecarSource`) |
| `digest` | `ContentDigest \| None` | Backend declares `WRITE_RESULT_NATIVE` |
| `etag` | `str \| None` | Backend declares `WRITE_RESULT_NATIVE` |
| `version_id` | `str \| None` | Backend declares `WRITE_RESULT_NATIVE` (S3 versioning, Azure) |
| `last_modified` | `datetime \| None` | Backend declares `WRITE_RESULT_NATIVE` |
| `metadata` | `dict[str, str]` | Echo of caller's `metadata=` input (WR-012) |

`source` signals where the rich fields came from:
`NativeSource` = populated from the backend's write response;
`BasicSource` = populated from a post-write stat/head;
`SidecarSource` = populated by the `ext.write` hash helper.

### `FileInfo`

Returned by `get_file_info()` and yielded by `iter_children()`.

| Field | Type |
|---|---|
| `path` | `str` |
| `size` | `int` |
| `modified_at` | `datetime \| None` |
| `etag` | `str \| None` |
| `version_id` | `str \| None` |
| `content_type` | `str \| None` |
| `metadata` | `dict[str, str]` |

### Other models

| Model | Description |
|---|---|
| `FolderInfo` | `path`, `file_count`, `total_size` — returned by `get_folder_info()` |
| `ContentDigest` | `algorithm` (e.g. `"crc32"`, `"sha256"`) + `value` (hex) |
| `ResolutionPlan` | Backend type, resolved path, and options — returned by `resolve()` |
| `BackendConfig` | `type` string + `options` dict — one entry in a `RegistryConfig` |
| `RegistryConfig` | Named backends and stores; the entry point for config-driven setup |

---

## Capabilities

Capabilities are declared by backends at construction time.
Two flavours exist:

- **Method gates**: the capability is a hard prerequisite for calling the
  method. `store.supports()` returns `False` and the method raises
  `CapabilityNotSupported` if called without it.
- **Quality flags**: the capability signals that a method delivers a stronger
  guarantee. The method is available regardless; the flag lets callers decide
  whether to rely on the native behaviour or fall back to an extension.

| Capability | Flavour | Gated / signalled methods | Notes |
|---|---|---|---|
| `READ` | Gate | `read()`, `read_bytes()`, `read_text()`, `read_seekable()` | Declared by all built-in backends |
| `WRITE` | Gate | `write()`, `write_text()` | Declared by all built-in backends |
| `DELETE` | Gate | `delete()`, `delete_folder()` | Declared by all built-in backends |
| `LIST` | Gate | `list_files()`, `list_folders()`, `iter_children()` | Declared by all built-in backends |
| `GLOB` | Gate | `glob()` | Not declared by `memory`; use `ext.glob` as fallback |
| `MOVE` | Gate | `move()` | Declared by all built-in backends |
| `COPY` | Gate | `copy()` | Declared by all built-in backends |
| `ATOMIC_WRITE` | Gate | `write_atomic()`, `open_atomic()` | Declared by all built-in backends |
| `METADATA` | Gate | `head()`, `get_file_info()`, `get_folder_info()` | Declared by all built-in backends |
| `SEEKABLE_READ` | Quality flag | `read()` | `read()` returns a natively seekable stream |
| `LAZY_READ` | Quality flag | `read()` | `read()` fetches data lazily; partial reads avoid loading the full file |
| `ATOMIC_MOVE` | Quality flag | `move()` | `move()` is crash-safe under concurrent access |
| `WRITE_RESULT_NATIVE` | Quality flag | `write*()`, `head()` | Rich `WriteResult` fields (`etag`, `digest`, `version_id`, `last_modified`) come from the backend's own write response |
| `USER_METADATA` | Strict gate | `metadata=` kwarg on write methods | A non-empty `metadata=` raises `CapabilityNotSupported` when unset |

---

## Backends

Built-in backends cover the most common targets. All implement the same
`Backend` ABC; `SFTPUtils`, `S3PyArrowBackend`, and the SQL backends expose
additional backend-specific options via `BackendConfig.options`.

<!-- BEGIN_GENERATED:backends_main -->
| Type | Class | Extra | Capabilities |
|---|---|---|---|
| `azure` | `AzureBackend` | `remote-store[azure]` | All except `ATOMIC_MOVE`, `SEEKABLE_READ` |
| `http` | `ReadOnlyHttpBackend` | — (stdlib; `requests`/`httpx` optional) | `LAZY_READ`, `METADATA`, `READ` |
| `local` | `LocalBackend` | — | All |
| `memory` | `MemoryBackend` | — | All except `GLOB`, `LAZY_READ` |
| `s3` | `S3Backend` | `remote-store[s3]` | All except `ATOMIC_MOVE` |
| `s3-pyarrow` | `S3PyArrowBackend` | `remote-store[s3-pyarrow]` | All except `ATOMIC_MOVE` |
| `sftp` | `SFTPBackend` | `remote-store[sftp]` | All except `ATOMIC_MOVE`, `GLOB` |
| `sql-blob` | `SQLBlobBackend` | `remote-store[sql]` | All except `LAZY_READ` |
| `sql-query` | `SQLQueryBackend` | `remote-store[sql-query]` | `GLOB`, `LIST`, `METADATA`, `READ`, `SEEKABLE_READ` |
<!-- END_GENERATED:backends_main -->

**Write-result quality flags by backend:**

<!-- BEGIN_GENERATED:backends_flags -->
| Backend | `WRITE_RESULT_NATIVE` | `USER_METADATA` |
|---|---|---|
| `azure` | Yes | Yes |
| `http` | — | — |
| `local` | Yes | — |
| `memory` | Yes | Yes |
| `s3` | Yes | Yes |
| `s3-pyarrow` | Yes | — |
| `sftp` | Yes | — |
| `sql-blob` | Yes (requires `modified_at` column) | Yes (requires `user_metadata` column) |
| `sql-query` | — | — |
<!-- END_GENERATED:backends_flags -->

---

## Configuration

`RegistryConfig` decouples storage topology from application code.
Define named backends and stores in a config file; application code
calls `registry.store("name")` and never sees connection strings.
Credentials in standard-looking keys (`password`, `secret_key`, etc.)
are wrapped in `Secret` automatically and masked in logs.

```toml
[backends.primary]
type = "s3"
options.bucket = "my-bucket"
options.access_key = "${AWS_ACCESS_KEY_ID}"
options.secret_key = "${AWS_SECRET_ACCESS_KEY}"

[stores.data]
backend = "primary"
root = "data/"
```

| API | Location | Description |
|---|---|---|
| `RegistryConfig.from_dict(data)` | `remote_store` | Construct from a plain dict |
| `RegistryConfig.from_toml(path, *, table, resolve_env_vars)` | `remote_store` | Load from a TOML file |
| `from_yaml(path, *, resolve_env_vars)` | `remote_store.ext.yaml` | Load from a YAML file |
| `from_pydantic(model)` | `remote_store.ext.pydantic` | Convert a Pydantic settings model |
| `resolve_env(data, *, environ)` | `remote_store` | Resolve `${VAR}` / `${VAR:-default}` placeholders in a config dict |

---

## Extensions

Extensions are composable layers on top of `Store` or utility helpers.
They use only the public `Store`/`Backend` API and carry no lifecycle
ownership — they never call `store.close()`.

### Always available (base install)

| Extension | Problem it solves | Module | Key exports |
|---|---|---|---|
| **Batch** | Apply copy/delete/exists across many paths in one call with partial-failure reporting | `remote_store.ext.batch` | `BatchResult`, `batch_copy`, `batch_delete`, `batch_exists` |
| **Cache** | Transparent read-through caching — subsequent reads of the same key go to a fast local store | `remote_store.ext.cache` | `CachedStore`, `CacheBackend`, `CacheStats`, `MemoryCache`, `cache` |
| **Glob** | Portable glob for backends that do not declare `Capability.GLOB` | `remote_store.ext.glob` | `glob_files` |
| **Integrity** | Client-side content checksums and verification independent of backend digest support | `remote_store.ext.integrity` | `checksum`, `verify`, `verify_hex`, `content_digest` |
| **Observe** | Structured event hooks for every store operation — logging, metrics, tracing, audit trails | `remote_store.ext.observe` | `ObservedStore`, `StoreEvent`, `BufferedObserver`, `observe`, `set_correlation_id` |
| **Partition** | Parse and construct Hive-style partition paths (`key=value/…`) | `remote_store.ext.partition` | `ParsedPartition`, `parse_partition`, `partition_path` |
| **Streams** | Wrap any stream with progress callbacks or rolling checksums without buffering | `remote_store.ext.streams` | `ChecksumReader`, `ChecksumWriter`, `ProgressReader`, `ProgressWriter`, `read_with_progress` |
| **Transfer** | High-level upload / download / store-to-store copy with streaming and progress | `remote_store.ext.transfer` | `upload`, `download`, `transfer` |
| **Write** | Guaranteed client-side digest on write regardless of backend capability; atomic write variant | `remote_store.ext.write` | `write_with_hash`, `open_atomic_with_hash` |

### Optional (require extras)

| Extension | Problem it solves | Module | Key exports | Extra |
|---|---|---|---|---|
| **Arrow** | Use any `Store` as a PyArrow filesystem for Arrow / Parquet tooling | `remote_store.ext.arrow` | `StoreFileSystemHandler`, `pyarrow_fs` | `remote-store[arrow]` |
| **Parquet** | Read and write Parquet datasets (single files or partitioned) via PyArrow | `remote_store.ext.parquet` | `ParquetDatasetStore`, `DatasetManifest` | `remote-store[arrow]` |
| **OpenTelemetry** | Emit distributed tracing spans for every store operation | `remote_store.ext.otel` | `otel_hooks`, `otel_observe` | `remote-store[otel]` |
| **Pydantic** | Derive `RegistryConfig` from a Pydantic settings model | `remote_store.ext.pydantic` | `from_pydantic` | `remote-store[pydantic]` |
| **YAML** | Load `RegistryConfig` from a YAML file | `remote_store.ext.yaml` | `from_yaml` | `remote-store[yaml]` |
| **Dagster** | IO manager, config-driven Store resource, and compute log manager for Dagster pipelines | `remote_store.ext.dagster` | `RemoteStoreIOManager`, `DagsterStoreResource`, `RemoteStoreComputeLogManager`, `dagster_io_manager` | `remote-store[dagster]` |

---

## Error Model

All errors are subclasses of `RemoteStoreError` (importable from `remote_store`).
Backend-native exceptions are mapped at the adapter boundary — callers
always receive a typed error, never an `S3ServiceError` or `azure.core.…`.

| Error | Raised when |
|---|---|
| `NotFound` | File or folder does not exist |
| `AlreadyExists` | Target path already exists and `overwrite=False` |
| `InvalidPath` | Path is malformed or points at the wrong node type (e.g. a directory where a file is expected) |
| `CapabilityNotSupported` | A method is called without the required capability |
| `BackendUnavailable` | The backend is unreachable (network, auth, service down) |
| `PermissionDenied` | Caller lacks access rights |
| `DirectoryNotEmpty` | Directory is not empty and the operation requires it to be |
| `RemoteStoreError` | Base class for all errors above |

---

## Async API

`remote_store.aio` provides native `async`/`await` support and two bridge
adapters for mixing sync and async backends.

**Native async classes:**

| Class | Description |
|---|---|
| `AsyncStore` | Async counterpart to `Store`; coroutine methods for all operations; `write*()` returns `WriteResult` and accepts `metadata=` |
| `AsyncBackend` | ABC for native async backends |
| `AsyncMemoryBackend` | In-memory async backend (for testing) |
| `AsyncAzureBackend` | Native async Azure backend via Azure SDK async clients |
| `AsyncWritableContent` | Type alias: `bytes \| AsyncIterator[bytes]` |

**Bridge adapters** — when you need to cross the sync/async boundary:

| Class | Direction | Mechanism |
|---|---|---|
| `SyncBackendAdapter` | sync `Backend` → usable in async code | Dispatches each call via `asyncio.to_thread` (thread-pool executor) |
| `AsyncBackendSyncAdapter` | async `AsyncBackend` → usable in sync code | Runs the async backend on a dedicated daemon-thread event loop |

Both adapters translate capabilities faithfully and are covered by the same
conformance suite as native backends.

**Async extensions:**

| Module | Description |
|---|---|
| `aio.ext.write` | `write_with_hash` — client-side SHA-256 checksumming on async write paths |

---

## Install extras

<!-- BEGIN_GENERATED:install_extras -->
```
pip install remote-store[arrow]       # PyArrow filesystem bridge + Parquet extension
pip install remote-store[azure]       # Azure ADLS Gen2 via Azure SDK
pip install remote-store[dagster]     # Dagster IO manager
pip install remote-store[httpx]       # httpx HTTP adapter for ReadOnlyHttpBackend
pip install remote-store[otel]        # OpenTelemetry distributed tracing
pip install remote-store[pydantic]    # Pydantic settings integration
pip install remote-store[requests]    # requests HTTP adapter for ReadOnlyHttpBackend
pip install remote-store[s3]          # S3 via s3fs
pip install remote-store[s3-pyarrow]  # S3 via PyArrow C++ filesystem
pip install remote-store[sftp]        # SFTP via paramiko
pip install remote-store[sql]         # SQL blob store via SQLAlchemy
pip install remote-store[sql-query]   # SQL query store via SQLAlchemy + PyArrow
pip install remote-store[toml]        # TOML config (stdlib on Python 3.11+)
pip install remote-store[yaml]        # YAML config loading
```
<!-- END_GENERATED:install_extras -->

Each extra declares a floor in `pyproject.toml` and in most cases
deliberately no ceiling (the `arrow` and `sql-query` extras carry a
`pyarrow<25` ceiling). For the exact upper-bound versions CI was last
green against, see [Tested upper-bound versions](https://docs.remotestore.dev/stable/reference/tested-versions/).
