# Features — remote-store v0.29.1

Authoritative snapshot of what remote-store delivers in this version. Updated each release. **This is the single reference for the package's feature surface.**

______________________________________________________________________

## What this package does

remote-store gives application code a single, portable file-storage API. Write against `Store` once; swap the backend by changing one line of config — the same `read()`, `write()`, and `list_files()` calls work across all supported backends (see the [Backends](#backends) section).

Three primitives do all the work:

- **`Store`** wraps a backend and exposes capability-gated methods. An operation is available only if the backend supports it. Capability is queried at runtime with `store.supports(Capability.X)`, so code can adapt gracefully instead of failing at import time.
- **`Backend`** is the storage-specific adapter. Built-in backends cover the common targets; a public ABC makes it straightforward to add new ones.
- **`Registry`** loads named backend and store definitions from config (TOML, YAML, dict, or Pydantic models), resolves `${ENV_VAR}` placeholders, and wraps credentials in `Secret` automatically.

______________________________________________________________________

## Store API

Methods are grouped by the capability that gates them. All methods share one invariant: they raise typed errors from `remote_store.errors` and never leak backend-native exceptions to the caller.

The table below is generated from the documentation graph (`graph.json`): each gating capability maps to the methods it gates. The descriptive per-capability subsections that follow add return types and behaviour. Quality-flag capabilities (`SEEKABLE_READ`, `LAZY_READ`, `ATOMIC_MOVE`, `WRITE_RESULT_NATIVE`, `USER_METADATA`) are not gates and so do not appear here — see [Capabilities](#capabilities).

### Methods by capability gate

| Capability     | Gated methods                                              |
| -------------- | ---------------------------------------------------------- |
| `ATOMIC_WRITE` | `open_atomic()`, `write_atomic()`                          |
| `COPY`         | `copy()`                                                   |
| `DELETE`       | `delete()`, `delete_folder()`                              |
| `GLOB`         | `glob()`                                                   |
| `LIST`         | `iter_children()`, `list_files()`, `list_folders()`        |
| `METADATA`     | `get_file_info()`, `get_folder_info()`\*, `head()`         |
| `MOVE`         | `move()`                                                   |
| `READ`         | `read()`, `read_bytes()`, `read_seekable()`, `read_text()` |
| `WRITE`        | `write()`, `write_text()`                                  |

\* `get_folder_info()` is additionally gated on `LIST` when called with `max_depth` (depth-limited traversal).

### Ungated (always available)

These methods carry no capability gate — they are available on every backend. The set is derived from the graph (Store method nodes with `gated: false`).

| Method                 | Returns          | Description                                               |
| ---------------------- | ---------------- | --------------------------------------------------------- |
| `exists(path)`         | `bool`           | Whether a file exists at the path                         |
| `is_file(path)`        | `bool`           | Whether the path resolves to a file (not a folder)        |
| `is_folder(path)`      | `bool`           | Whether the path resolves to a folder                     |
| `ping()`               | `None`           | Health check — raises `BackendUnavailable` if unreachable |
| `close()`              | `None`           | Release backend resources                                 |
| `child(subpath)`       | `Store`          | Scoped sub-store rooted at `subpath`                      |
| `unwrap(type_hint)`    | `T`              | Extract the underlying backend by type                    |
| `resolve(key)`         | `ResolutionPlan` | Resolution plan for a key (type, resolved path, options)  |
| `native_path(key)`     | `str`            | Backend-native path string for a store key                |
| `to_key(path)`         | `str`            | Convert a native path back to a store key                 |
| `supports(capability)` | `bool`           | Query whether a capability is active                      |

### READ

| Method                         | Returns    | Description                                                                                                                                                            |
| ------------------------------ | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `read(path)`                   | `BinaryIO` | Open a binary stream for reading; lazy where the backend supports `LAZY_READ`                                                                                          |
| `read_bytes(path)`             | `bytes`    | Read the entire file into memory                                                                                                                                       |
| `read_text(path, *, encoding)` | `str`      | Read the entire file as a decoded string                                                                                                                               |
| `read_seekable(path)`          | `BinaryIO` | Seekable binary stream; zero-copy where `read()` is already seekable (`SEEKABLE_READ` backends), a native HTTP-Range reader on sync Azure, else spooled to a temp file |

### WRITE

All write methods accept an optional `metadata=` mapping. If the backend declares `Capability.USER_METADATA`, the mapping is persisted alongside the file; otherwise a non-empty `metadata=` raises `CapabilityNotSupported`. All write methods return a `WriteResult` (see Data Models).

| Method                                                     | Returns       | Description                                              |
| ---------------------------------------------------------- | ------------- | -------------------------------------------------------- |
| `write(path, content, *, overwrite, metadata)`             | `WriteResult` | Create or overwrite a file from bytes or a binary stream |
| `write_text(path, text, *, encoding, overwrite, metadata)` | `WriteResult` | Write a string as a file                                 |

### ATOMIC_WRITE

Atomic writes use a temp-and-rename strategy: no reader ever sees a partial file, and a crash mid-write leaves the previous version intact.

| Method                                                | Returns                         | Description                                                  |
| ----------------------------------------------------- | ------------------------------- | ------------------------------------------------------------ |
| `write_atomic(path, content, *, overwrite, metadata)` | `WriteResult`                   | Atomic write from bytes or a stream                          |
| `open_atomic(path, *, overwrite, metadata)`           | context manager → `WriteResult` | Streaming atomic write; `WriteResult` returned on `__exit__` |

### DELETE

| Method                              | Returns | Description                                             |
| ----------------------------------- | ------- | ------------------------------------------------------- |
| `delete(path, *, missing_ok)`       | `None`  | Remove a file; `missing_ok=True` suppresses `NotFound`  |
| `delete_folder(path, *, recursive)` | `None`  | Remove a folder; requires `recursive=True` if non-empty |

### LIST

| Method                                      | Returns                             | Description                                                                                                                            |
| ------------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `list_files(path, *, max_depth, pattern)`   | `Iterator[FileInfo]`                | Enumerate files under a prefix as `FileInfo` records (use `.path` for the path); optional `pattern=` filters basenames via `fnmatch`   |
| `list_folders(path, *, max_depth, pattern)` | `Iterator[FolderEntry]`             | Enumerate immediate subfolders as `FolderEntry` records (`.name`, `.path`); optional `pattern=` filters folder basenames via `fnmatch` |
| `iter_children(path)`                       | `Iterator[FileInfo \| FolderEntry]` | Iterate files and folders together (`FileInfo` for files, `FolderEntry` for folders)                                                   |

### GLOB

| Method          | Returns              | Description                                                                                 |
| --------------- | -------------------- | ------------------------------------------------------------------------------------------- |
| `glob(pattern)` | `Iterator[FileInfo]` | Native glob pattern matching (`*`, `**`, `?`), yielding matched files as `FileInfo` records |

Backends without native `GLOB` capability can use the `ext.glob` extension as a portable fallback.

### MOVE / COPY

| Method                         | Returns | Description                                |
| ------------------------------ | ------- | ------------------------------------------ |
| `move(src, dst, *, overwrite)` | `None`  | Rename or relocate within the same backend |
| `copy(src, dst, *, overwrite)` | `None`  | Duplicate a file within the same backend   |

### METADATA

| Method                  | Returns       | Description                                                             |
| ----------------------- | ------------- | ----------------------------------------------------------------------- |
| `head(path)`            | `WriteResult` | File metadata without reading content (size, etag, last_modified, etc.) |
| `get_file_info(path)`   | `FileInfo`    | Full file metadata record                                               |
| `get_folder_info(path)` | `FolderInfo`  | Folder metadata with aggregate file count and total size                |

______________________________________________________________________

## Data Models

All models are importable from `remote_store` and are frozen dataclasses.

### `WriteResult`

Returned by every write method and by `head()`.

| Field           | Type                    | Populated when                                                |
| --------------- | ----------------------- | ------------------------------------------------------------- |
| `path`          | `str`                   | Always                                                        |
| `size`          | `int`                   | Always                                                        |
| `source`        | `WriteSource`           | Always (`NativeSource`, `BasicSource`, or `SidecarSource`)    |
| `digest`        | `ContentDigest \| None` | Backend declares `WRITE_RESULT_NATIVE`                        |
| `etag`          | `str \| None`           | Backend declares `WRITE_RESULT_NATIVE`                        |
| `version_id`    | `str \| None`           | Backend declares `WRITE_RESULT_NATIVE` (S3 versioning, Azure) |
| `last_modified` | `datetime \| None`      | Backend declares `WRITE_RESULT_NATIVE`                        |
| `metadata`      | `dict[str, str]`        | Echo of caller's `metadata=` input                            |

`source` signals where the rich fields came from: `NativeSource` = populated from the backend's write response; `BasicSource` = populated from a post-write stat/head; `SidecarSource` = populated by the `ext.write` hash helper.

### `FileInfo`

Returned by `get_file_info()` and yielded by `iter_children()`.

| Field          | Type               |
| -------------- | ------------------ |
| `path`         | `str`              |
| `size`         | `int`              |
| `modified_at`  | `datetime \| None` |
| `etag`         | `str \| None`      |
| `version_id`   | `str \| None`      |
| `content_type` | `str \| None`      |
| `metadata`     | `dict[str, str]`   |

### Other models

| Model            | Description                                                                      |
| ---------------- | -------------------------------------------------------------------------------- |
| `FolderInfo`     | `path`, `file_count`, `total_size` — returned by `get_folder_info()`             |
| `FolderEntry`    | `path`, `name` — folder identity yielded by `list_folders()` / `iter_children()` |
| `ContentDigest`  | `algorithm` (e.g. `"crc32"`, `"sha256"`) + `value` (hex)                         |
| `ResolutionPlan` | Backend type, resolved path, and options — returned by `resolve()`               |
| `BackendConfig`  | `type` string + `options` dict — one entry in a `RegistryConfig`                 |
| `RegistryConfig` | Named backends and stores; the entry point for config-driven setup               |

______________________________________________________________________

## Capabilities

Capabilities are declared by backends at construction time. Two flavours exist:

- **Method gates**: the capability is a hard prerequisite for calling the method. `store.supports()` returns `False` and the method raises `CapabilityNotSupported` if called without it.
- **Quality flags**: the capability signals that a method delivers a stronger guarantee. The method is available regardless; the flag lets callers decide whether to rely on the native behaviour or fall back to an extension.

| Capability            | Flavour      | Gated / signalled methods                                  | Notes                                                                                                                                                                                                                                    |
| --------------------- | ------------ | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `READ`                | Gate         | `read()`, `read_bytes()`, `read_text()`, `read_seekable()` | Declared by all built-in backends                                                                                                                                                                                                        |
| `WRITE`               | Gate         | `write()`, `write_text()`                                  | Declared by all built-in backends                                                                                                                                                                                                        |
| `DELETE`              | Gate         | `delete()`, `delete_folder()`                              | Declared by all built-in backends                                                                                                                                                                                                        |
| `LIST`                | Gate         | `list_files()`, `list_folders()`, `iter_children()`        | Declared by all built-in backends                                                                                                                                                                                                        |
| `GLOB`                | Gate         | `glob()`                                                   | Not declared by `memory`; use `ext.glob` as fallback                                                                                                                                                                                     |
| `MOVE`                | Gate         | `move()`                                                   | Declared by all built-in backends                                                                                                                                                                                                        |
| `COPY`                | Gate         | `copy()`                                                   | Declared by all built-in backends                                                                                                                                                                                                        |
| `ATOMIC_WRITE`        | Gate         | `write_atomic()`, `open_atomic()`                          | Declared by all built-in backends                                                                                                                                                                                                        |
| `METADATA`            | Gate         | `head()`, `get_file_info()`, `get_folder_info()`           | Declared by all built-in backends                                                                                                                                                                                                        |
| `SEEKABLE_READ`       | Quality flag | `read()`                                                   | `read()` returns a natively seekable stream. Absence means only that `read()` is forward-only — the sync `Store.read_seekable()` still serves it (native range read on sync Azure, else spooled); the async API has no `read_seekable()` |
| `LAZY_READ`           | Quality flag | `read()`                                                   | `read()` fetches data lazily; partial reads avoid loading the full file                                                                                                                                                                  |
| `ATOMIC_MOVE`         | Quality flag | `move()`                                                   | `move()` is crash-safe under concurrent access                                                                                                                                                                                           |
| `WRITE_RESULT_NATIVE` | Quality flag | `write*()`, `head()`                                       | Rich `WriteResult` fields (`etag`, `digest`, `version_id`, `last_modified`) come from the backend's own write response                                                                                                                   |
| `USER_METADATA`       | Strict gate  | `metadata=` kwarg on write methods                         | A non-empty `metadata=` raises `CapabilityNotSupported` when unset                                                                                                                                                                       |

______________________________________________________________________

## Backends

Built-in backends cover the most common targets. All implement the same `Backend` ABC; `SFTPUtils`, `S3PyArrowBackend`, and the SQL backends expose additional backend-specific options via `BackendConfig.options`.

| Type         | Class                 | Extra                                   | Capabilities                                        |
| ------------ | --------------------- | --------------------------------------- | --------------------------------------------------- |
| `azure`      | `AzureBackend`        | `remote-store[azure]`                   | All except `ATOMIC_MOVE`, `SEEKABLE_READ`           |
| `http`       | `ReadOnlyHttpBackend` | — (stdlib; `requests`/`httpx` optional) | `LAZY_READ`, `METADATA`, `READ`                     |
| `local`      | `LocalBackend`        | —                                       | All                                                 |
| `memory`     | `MemoryBackend`       | —                                       | All except `GLOB`, `LAZY_READ`                      |
| `s3`         | `S3Backend`           | `remote-store[s3]`                      | All except `ATOMIC_MOVE`                            |
| `s3-pyarrow` | `S3PyArrowBackend`    | `remote-store[s3-pyarrow]`              | All except `ATOMIC_MOVE`                            |
| `sftp`       | `SFTPBackend`         | `remote-store[sftp]`                    | All except `ATOMIC_MOVE`, `GLOB`                    |
| `sql-blob`   | `SQLBlobBackend`      | `remote-store[sql]`                     | All except `LAZY_READ`                              |
| `sql-query`  | `SQLQueryBackend`     | `remote-store[sql-query]`               | `GLOB`, `LIST`, `METADATA`, `READ`, `SEEKABLE_READ` |

The `SEEKABLE_READ` exclusions above concern `read()` only — `read_seekable()` remains available on the sync `Store`, and on Azure it is a native HTTP-Range reader (no temp-file spill), not a spool. See [Streaming and seekable reads](https://docs.remotestore.dev/stable/guides/backends/azure/#streaming-and-seekable-reads).

**Write-result quality flags by backend:**

| Backend      | `WRITE_RESULT_NATIVE`               | `USER_METADATA`                       |
| ------------ | ----------------------------------- | ------------------------------------- |
| `azure`      | Yes                                 | Yes                                   |
| `http`       | —                                   | —                                     |
| `local`      | Yes                                 | —                                     |
| `memory`     | Yes                                 | Yes                                   |
| `s3`         | Yes                                 | Yes                                   |
| `s3-pyarrow` | Yes                                 | —                                     |
| `sftp`       | Yes                                 | —                                     |
| `sql-blob`   | Yes (requires `modified_at` column) | Yes (requires `user_metadata` column) |
| `sql-query`  | —                                   | —                                     |

**Write and move atomicity by backend** — whether each mutating operation completes atomically or via a non-atomic mechanism that can leave partial state on failure. `read`, `list`, and `metadata` are non-mutating (atomicity N/A); `delete` and folder operations carry no atomicity guarantee and are omitted.

| Backend      | `write`       | `write_atomic` | `move`        | `copy`        |
| ------------ | ------------- | -------------- | ------------- | ------------- |
| `azure`      | Atomic§       | Atomic         | Copy+delete†  | Copy+delete   |
| `http`       | — (read-only) | — (read-only)  | — (read-only) | — (read-only) |
| `local`      | Direct        | Atomic         | Atomic\*      | Copy+delete   |
| `memory`     | Atomic        | Atomic         | Atomic        | Atomic        |
| `s3`         | Atomic        | Atomic         | Copy+delete   | Copy+delete   |
| `s3-pyarrow` | Streamed‡     | Atomic         | Copy+delete   | Copy+delete   |
| `sftp`       | Streamed      | Atomic         | Copy+delete†  | Copy+delete   |
| `sql-blob`   | Atomic        | Atomic         | Atomic        | Atomic        |
| `sql-query`  | — (read-only) | — (read-only)  | — (read-only) | — (read-only) |

\* `local` `move` is atomic within one filesystem (`os.rename`); a cross-filesystem move falls back to copy-then-delete. † Azure and SFTP `move` use a native rename that is atomic (Azure HNS `rename_file`, SFTP `posix_rename`), but `ATOMIC_MOVE` is not advertised because it cannot be guaranteed across all configurations (non-HNS Azure accounts, non-POSIX SFTP servers). ‡ `s3-pyarrow` plain `write` streams straight to a multipart upload; PyArrow's stream exposes no abort, so a mid-stream failure finalises a *truncated* object. `write_atomic` buffers the body first, so a failure leaves no object. § `azure` `write` commits atomically on flat (non-HNS) accounts; on hierarchical-namespace accounts use `write_atomic` for a guaranteed atomic replace.

**Read-after-write consistency by backend** — whether a read or listing issued after a write, overwrite, or delete reflects that change. remote-store normalises to **strong** read-after-write on every read/write backend: the object you just wrote or deleted is immediately visible to a subsequent `read`, `head`, or `list_files` on the same store, with no eventual-consistency window to code around. This is a per-caller *visibility* guarantee, not mutual exclusion between *simultaneous* writers — `overwrite=False` remains a TOCTOU convenience guard, and concurrent writers to one key resolve last-writer-wins. See [Concurrency and atomicity](https://docs.remotestore.dev/stable/explanation/concurrency/) for the ordering and race semantics.

| Backend      | Read-after-write | Listing consistency |
| ------------ | ---------------- | ------------------- |
| `azure`      | Strong           | Strong              |
| `http`       | — (read-only)    | — (read-only)       |
| `local`      | Strong           | Strong              |
| `memory`     | Strong           | Strong              |
| `s3`         | Strong           | Strong\*            |
| `s3-pyarrow` | Strong           | Strong\*            |
| `sftp`       | Strong           | Strong              |
| `sql-blob`   | Strong           | Strong              |
| `sql-query`  | — (read-only)    | — (read-only)       |

The async-native backends inherit their sync peer's consistency; the async-only `GraphBackend` is the one distinct case.

| Async backend        | Read-after-write | Listing consistency |
| -------------------- | ---------------- | ------------------- |
| `AsyncAzureBackend`  | Strong           | Strong              |
| `AsyncMemoryBackend` | Strong           | Strong              |
| `GraphBackend`       | Strong†          | Strong†             |

\* `s3` / `s3-pyarrow` listings are strongly consistent by default: the backend leaves the s3fs directory cache **off** (`use_listings_cache=False`), so a listing taken after a write reflects it. Opting into `client_options['use_listings_cache']` trades this for a cache that never expires — a listing can then stay blind to a cross-writer change until the backend is rebuilt. † `GraphBackend` read-your-writes holds on one instance (a write is committed to two datacentre regions before it is acknowledged). `copy` (always) and a large or cross-folder `move` (sometimes) run server-side and are polled to completion before the call returns, so a read or listing afterwards reflects the result.

**Per-operation cost by backend** — the *structural* cost each backend forces per call: whether `read` streams (constant memory) or materializes the whole object, and what a `metadata` probe and a `list` cost per invocation. This is the cost the API shape dictates, distinct from measured latency — see [Performance](https://docs.remotestore.dev/stable/explanation/performance/) for benchmarked overhead. Write-path cost (streaming vs full-buffer, atomic vs copy+delete) is in the atomicity table above; `list` cost scales with the number of entries returned, and enabling hierarchical-write safety (`reject_write_under_file_ancestor`, or the native HNS / SFTP / Graph parent checks) adds one metadata probe per path ancestor on the guarded write path.

| Backend      | `read`                  | `metadata`          | `list`           |
| ------------ | ----------------------- | ------------------- | ---------------- |
| `azure`      | Streaming               | 1 HEAD              | Paginated `LIST` |
| `http`       | Streaming               | 1 HEAD              | — (no `LIST`)    |
| `local`      | Streaming               | `stat` syscall      | `scandir` walk   |
| `memory`     | Buffered in memory\*    | Dict lookup         | Dict scan        |
| `s3`         | Streaming               | 1 HEAD              | Paginated `LIST` |
| `s3-pyarrow` | Streaming               | 1 HEAD              | Paginated `LIST` |
| `sftp`       | Streaming               | 1 `stat` round-trip | Directory walk   |
| `sql-blob`   | Full BLOB into memory\* | 1 `SELECT`          | 1 `SELECT`       |
| `sql-query`  | Query run, buffered\*   | Registry lookup     | Registry scan    |

The async-native backends inherit their sync peer's per-op cost; the async-only `GraphBackend` streams reads but blocks `copy` (always) and a large or cross-folder `move` on a server-side monitor polled to completion — a per-call latency the columns below do not show.

| Async backend        | `read`    | `metadata`  | `list`           |
| -------------------- | --------- | ----------- | ---------------- |
| `AsyncAzureBackend`  | Streaming | 1 HEAD      | Paginated `LIST` |
| `AsyncMemoryBackend` | Streaming | Dict lookup | Dict scan        |
| `GraphBackend`       | Streaming | 1 GET       | Paginated GETs   |

\* `memory` (sync), `sql-blob`, and `sql-query` do not stream a read (`LAZY_READ` absent): each holds the whole object in memory before `read()` returns — `sql-blob` loads the full BLOB, `sql-query` buffers the serialised query result, and sync `memory` keeps the value resident (its async peer `AsyncMemoryBackend` yields chunks and *does* stream). `sql-blob` likewise buffers the entire body before the write `INSERT`/`UPDATE`. For objects larger than process memory use a streaming backend (Local, S3, Azure, SFTP).

**Native async backends** — constructed directly via `AsyncStore(backend=…)`; no RegistryConfig `type=` string (there is no async config registry).

| Class                | Extra                 | Capabilities                                      |
| -------------------- | --------------------- | ------------------------------------------------- |
| `AsyncAzureBackend`  | `remote-store[azure]` | All except `ATOMIC_MOVE`, `SEEKABLE_READ`         |
| `AsyncMemoryBackend` | —                     | All except `GLOB`                                 |
| `GraphBackend`       | `remote-store[graph]` | All except `ATOMIC_MOVE`, `GLOB`, `SEEKABLE_READ` |

The async API has no `read_seekable()`: an async-native backend that omits `SEEKABLE_READ` (`AsyncAzureBackend`, `GraphBackend`) has no seekable read until bridged to sync via `AsyncBackendSyncAdapter`, which spools.

**Write-result quality flags by native async backend:**

| Class                | `WRITE_RESULT_NATIVE` | `USER_METADATA` |
| -------------------- | --------------------- | --------------- |
| `AsyncAzureBackend`  | Yes                   | Yes             |
| `AsyncMemoryBackend` | Yes                   | Yes             |
| `GraphBackend`       | Yes                   | —               |

______________________________________________________________________

## Configuration

`RegistryConfig` decouples storage topology from application code. Define named backends and stores in a config file; application code calls `registry.store("name")` and never sees connection strings. Credentials in standard-looking keys (`password`, `secret_key`, etc.) are wrapped in `Secret` automatically and masked in logs.

```
[backends.primary]
type = "s3"
options.bucket = "my-bucket"
options.access_key = "${AWS_ACCESS_KEY_ID}"
options.secret_key = "${AWS_SECRET_ACCESS_KEY}"

[stores.data]
backend = "primary"
root = "data/"
```

| API                                                          | Location                    | Description                                                        |
| ------------------------------------------------------------ | --------------------------- | ------------------------------------------------------------------ |
| `RegistryConfig.from_dict(data)`                             | `remote_store`              | Construct from a plain dict                                        |
| `RegistryConfig.from_toml(path, *, table, resolve_env_vars)` | `remote_store`              | Load from a TOML file                                              |
| `from_yaml(path, *, resolve_env_vars)`                       | `remote_store.ext.yaml`     | Load from a YAML file                                              |
| `from_pydantic(model)`                                       | `remote_store.ext.pydantic` | Convert a Pydantic settings model                                  |
| `resolve_env(data, *, environ)`                              | `remote_store`              | Resolve `${VAR}` / `${VAR:-default}` placeholders in a config dict |

______________________________________________________________________

## Extensions

Extensions are composable layers on top of `Store` or utility helpers. They use only the public `Store`/`Backend` API and carry no lifecycle ownership — they never call `store.close()`.

### Always available (base install)

| Extension     | Problem it solves                                                                             | Module                       | Key exports                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------- |
| **Batch**     | Apply copy/delete/exists across many paths in one call with partial-failure reporting         | `remote_store.ext.batch`     | `BatchResult`, `batch_copy`, `batch_delete`, `batch_exists`                                  |
| **Cache**     | Transparent read-through caching — subsequent reads of the same key go to a fast local store  | `remote_store.ext.cache`     | `CachedStore`, `CacheBackend`, `CacheStats`, `MemoryCache`, `cache`                          |
| **Glob**      | Portable glob for backends that do not declare `Capability.GLOB`                              | `remote_store.ext.glob`      | `glob_files`                                                                                 |
| **Integrity** | Client-side content checksums and verification independent of backend digest support          | `remote_store.ext.integrity` | `checksum`, `verify`, `verify_hex`, `content_digest`                                         |
| **Observe**   | Structured event hooks for every store operation — logging, metrics, tracing, audit trails    | `remote_store.ext.observe`   | `ObservedStore`, `StoreEvent`, `BufferedObserver`, `observe`, `set_correlation_id`           |
| **Partition** | Parse and construct Hive-style partition paths (`key=value/…`)                                | `remote_store.ext.partition` | `ParsedPartition`, `parse_partition`, `partition_path`                                       |
| **Streams**   | Wrap any stream with progress callbacks or rolling checksums without buffering                | `remote_store.ext.streams`   | `ChecksumReader`, `ChecksumWriter`, `ProgressReader`, `ProgressWriter`, `read_with_progress` |
| **Transfer**  | High-level upload / download / store-to-store copy with streaming and progress                | `remote_store.ext.transfer`  | `upload`, `download`, `transfer`                                                             |
| **Write**     | Guaranteed client-side digest on write regardless of backend capability; atomic write variant | `remote_store.ext.write`     | `write_with_hash`, `open_atomic_with_hash`                                                   |

### Optional (require extras)

| Extension         | Problem it solves                                                                       | Module                      | Key exports                                                                                          | Extra                    |
| ----------------- | --------------------------------------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------ |
| **Arrow**         | Use any `Store` as a PyArrow filesystem for Arrow / Parquet tooling                     | `remote_store.ext.arrow`    | `StoreFileSystemHandler`, `pyarrow_fs`                                                               | `remote-store[arrow]`    |
| **Parquet**       | Read and write Parquet datasets (single files or partitioned) via PyArrow               | `remote_store.ext.parquet`  | `ParquetDatasetStore`, `DatasetManifest`                                                             | `remote-store[arrow]`    |
| **OpenTelemetry** | Emit distributed tracing spans for every store operation                                | `remote_store.ext.otel`     | `otel_hooks`, `otel_observe`                                                                         | `remote-store[otel]`     |
| **Pydantic**      | Derive `RegistryConfig` from a Pydantic settings model                                  | `remote_store.ext.pydantic` | `from_pydantic`                                                                                      | `remote-store[pydantic]` |
| **YAML**          | Load `RegistryConfig` from a YAML file                                                  | `remote_store.ext.yaml`     | `from_yaml`                                                                                          | `remote-store[yaml]`     |
| **Dagster**       | IO manager, config-driven Store resource, and compute log manager for Dagster pipelines | `remote_store.ext.dagster`  | `RemoteStoreIOManager`, `DagsterStoreResource`, `RemoteStoreComputeLogManager`, `dagster_io_manager` | `remote-store[dagster]`  |

______________________________________________________________________

## Error Model

All errors are subclasses of `RemoteStoreError` (importable from `remote_store`). Backend-native exceptions are mapped at the adapter boundary — callers always receive a typed error, never an `S3ServiceError` or `azure.core.…`.

| Error                    | Raised when                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `NotFound`               | File or folder does not exist                                                                                |
| `AlreadyExists`          | Target path already exists and `overwrite=False`                                                             |
| `InvalidPath`            | Path is malformed or points at the wrong node type (e.g. a directory where a file is expected)               |
| `CapabilityNotSupported` | A method is called without the required capability                                                           |
| `BackendUnavailable`     | The backend is unreachable (network, auth, service down)                                                     |
| `PermissionDenied`       | Caller lacks access rights                                                                                   |
| `DirectoryNotEmpty`      | Directory is not empty and the operation requires it to be                                                   |
| `ResourceLocked`         | Target resource is held by another session (e.g. an open co-authoring session); maps from Graph `423 Locked` |
| `RemoteStoreError`       | Base class for all errors above                                                                              |

**Retryable vs. terminal** — the HTTP statuses the HTTP-transport backends (`graph`, `http`) classify, and the typed error each surfaces as. Retried statuses are re-attempted under the backend's `RetryPolicy` (default 3 attempts, 1–60 s exponential backoff) and honour `Retry-After`; the typed error is raised only once the attempt budget is exhausted. The other backends reach the *same typed-error vocabulary* by mapping native SDK/OS exceptions rather than HTTP status codes, so the outcome is shared — but the status classification and `Retry-After` handling shown here are specific to the HTTP transports (`s3` and `azure` honour only `max_attempts`; `local`, `memory`, and `sql-*` make no remote calls and do not retry).

| Status | Disposition                     | Surfaced as          |
| ------ | ------------------------------- | -------------------- |
| `429`  | Retried — honours `Retry-After` | `BackendUnavailable` |
| `500`  | Retried                         | `BackendUnavailable` |
| `502`  | Retried                         | `BackendUnavailable` |
| `503`  | Retried                         | `BackendUnavailable` |
| `504`  | Retried                         | `BackendUnavailable` |
| `403`  | Not retried                     | `PermissionDenied`   |
| `404`  | Not retried                     | `NotFound`           |
| `409`  | Not retried                     | `AlreadyExists`      |
| `423`  | Not retried                     | `ResourceLocked`     |
| `507`  | Not retried                     | `BackendUnavailable` |

| Backend      | Transport retry mechanism                                       |
| ------------ | --------------------------------------------------------------- |
| `azure`      | Azure SDK `ExponentialRetry` (all five `RetryPolicy` fields)    |
| `http`       | Hand-rolled loop over the shared backoff helpers†               |
| `local`      | — (no `retry` parameter)                                        |
| `memory`     | — (no `retry` parameter)                                        |
| `s3`         | botocore `standard` mode — honours `max_attempts` only          |
| `s3-pyarrow` | `AwsStandardS3RetryStrategy` — honours `max_attempts` only      |
| `sftp`       | `tenacity` — connection-scope only (reconnect, not per-request) |
| `sql-blob`   | — (errors mapped, not retried)                                  |
| `sql-query`  | — (errors mapped, not retried)                                  |

† `http` additionally retries `408 Request Timeout` (classified as `BackendUnavailable`) — a transport-local extension of the shared retryable set above.

Native async backends inherit their sync peer's mechanism; the async-only `GraphBackend` runs hand-rolled retry loops over the shared backoff helpers, honouring all five `RetryPolicy` fields. `local`, `memory`, `sftp`, and the SQL backends leave a closed backend reusable; `azure`, `s3`, and `graph` treat use after `close()` as terminal (`close_is_terminal`).

______________________________________________________________________

## Async API

`remote_store.aio` provides native `async`/`await` support and two bridge adapters for mixing sync and async backends.

**Native async classes:**

| Class                  | Description                                                                                                                  |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `AsyncStore`           | Async counterpart to `Store`; coroutine methods for all operations; `write*()` returns `WriteResult` and accepts `metadata=` |
| `AsyncBackend`         | ABC for native async backends                                                                                                |
| `AsyncMemoryBackend`   | In-memory async backend (for testing)                                                                                        |
| `AsyncAzureBackend`    | Native async Azure backend via Azure SDK async clients                                                                       |
| `GraphBackend`         | Native async Microsoft Graph backend (OneDrive / SharePoint / Teams) via httpx + msal; companions `GraphAuth`, `GraphUtils`  |
| `AsyncWritableContent` | Type alias: `bytes \| AsyncIterator[bytes]`                                                                                  |

**Sync ↔ async backend equivalence** — generated from the graph's `mirrors` edges. The capability delta names capabilities one side declares that its peer does not. Async-only backends (`GraphBackend`) have no sync mirror and are listed above only.

| Sync backend    | Async backend        | Capability delta       |
| --------------- | -------------------- | ---------------------- |
| `AzureBackend`  | `AsyncAzureBackend`  | —                      |
| `MemoryBackend` | `AsyncMemoryBackend` | async adds `LAZY_READ` |

**Bridge adapters** — when you need to cross the sync/async boundary:

| Class                     | Direction                                  | Mechanism                                                           |
| ------------------------- | ------------------------------------------ | ------------------------------------------------------------------- |
| `SyncBackendAdapter`      | sync `Backend` → usable in async code      | Dispatches each call via `asyncio.to_thread` (thread-pool executor) |
| `AsyncBackendSyncAdapter` | async `AsyncBackend` → usable in sync code | Runs the async backend on a dedicated daemon-thread event loop      |

Both adapters translate capabilities faithfully and are covered by the same conformance suite as native backends.

**Async extensions:**

| Module          | Description                                                               |
| --------------- | ------------------------------------------------------------------------- |
| `aio.ext.write` | `write_with_hash` — client-side SHA-256 checksumming on async write paths |

______________________________________________________________________

## Install extras

```
pip install remote-store[arrow]       # PyArrow filesystem bridge + Parquet extension
pip install remote-store[azure]       # Azure ADLS Gen2 via Azure SDK
pip install remote-store[dagster]     # Dagster IO manager
pip install remote-store[graph]       # Microsoft Graph (OneDrive / SharePoint / Teams) via httpx + msal
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

Each extra declares a floor in `pyproject.toml` and in most cases deliberately no ceiling (the `arrow` and `sql-query` extras carry a `pyarrow<25` ceiling). For the exact upper-bound versions CI was last green against, see [Tested upper-bound versions](https://docs.remotestore.dev/stable/reference/tested-versions/).
