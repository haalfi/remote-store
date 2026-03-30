# Features — remote-store v0.20.0

Authoritative snapshot of backends, extensions, capabilities, and install
extras for the current version. Updated each release.

---

## Backends

| Type string | Description | Class | Extras | Always available | Capabilities |
|---|---|---|---|---|---|
| `local` | Local filesystem storage | `LocalBackend` | — | Yes | All 10 |
| `memory` | In-memory store for testing and caching | `MemoryBackend` | — | Yes | All except GLOB |
| `http` | Read-only HTTP file access (stdlib urllib; optional `requests`/`httpx` adapters) | `ReadOnlyHttpBackend` | — (`requests`, `httpx` optional) | Yes | READ, METADATA |
| `s3` | Amazon S3 via s3fs | `S3Backend` | `pip install remote-store[s3]` | No | All 10 |
| `s3-pyarrow` | Amazon S3 via PyArrow C++ filesystem | `S3PyArrowBackend` | `pip install remote-store[s3-pyarrow]` | No | All 10 |
| `sftp` | SFTP via paramiko | `SFTPBackend` | `pip install remote-store[sftp]` | No | All except GLOB |
| `azure` | Azure Data Lake Storage via Azure SDK | `AzureBackend` | `pip install remote-store[azure]` | No | All except SEEKABLE_READ |
| `sql-blob` | SQL blob store via SQLAlchemy | `SQLBlobBackend` | `pip install remote-store[sql]` | No | All 10 |
| `sql-query` | SQL query store for tabular data via SQLAlchemy + PyArrow | `SQLQueryBackend` | `pip install remote-store[sql-query]` | No | READ, LIST, METADATA, GLOB, SEEKABLE_READ |

---

## Store API

Methods grouped by capability gate. Query at runtime with
`store.supports(Capability.X)`.

### Ungated (always available)

| Method | Description |
|---|---|
| `exists(path)` | Check whether a file exists |
| `is_file(path)` | Check whether a path is a file |
| `is_folder(path)` | Check whether a path is a folder |
| `ping()` | Health check — verify backend is reachable |
| `close()` | Release backend resources |
| `child(subpath)` | Create a scoped sub-store |
| `unwrap(type_hint)` | Extract underlying backend by type |
| `resolve(key)` | Return the resolution plan for a key |
| `native_path(key)` | Return the backend-native path for a key |
| `to_key(path)` | Convert a native path back to a store key |
| `supports(capability)` | Query whether a capability is available |

### READ

| Method | Description |
|---|---|
| `read(path)` | Open a binary stream for reading |
| `read_bytes(path)` | Read entire file into bytes |
| `read_text(path)` | Read entire file as decoded string |

### SEEKABLE_READ

| Method | Description |
|---|---|
| `read_seekable(path)` | Open a seekable binary stream for reading |

### WRITE

| Method | Description |
|---|---|
| `write(path, content)` | Create or overwrite a file |
| `write_text(path, text)` | Write a string as a file |

### ATOMIC_WRITE

| Method | Description |
|---|---|
| `write_atomic(path, content)` | Write via temp-and-rename (no partial reads) |
| `open_atomic(path)` | Context manager for streaming atomic writes |

### DELETE

| Method | Description |
|---|---|
| `delete(path)` | Remove a file |
| `delete_folder(path)` | Remove a folder |

### LIST

| Method | Description |
|---|---|
| `list_files(path)` | Enumerate files under a path |
| `list_folders(path)` | Enumerate subfolders under a path |
| `iter_children(path)` | Iterate files and folders together |

### MOVE

| Method | Description |
|---|---|
| `move(src, dst)` | Rename or relocate within same backend |

### COPY

| Method | Description |
|---|---|
| `copy(src, dst)` | Duplicate within same backend |

### METADATA

| Method | Description |
|---|---|
| `get_file_info(path)` | Retrieve file metadata (size, modified, etc.) |
| `get_folder_info(path)` | Retrieve folder metadata and contents |

### GLOB

| Method | Description |
|---|---|
| `glob(pattern)` | Native pattern matching on file paths |

---

## Extensions

### Always available (included in base install)

| Extension | Description | Module | Key exports |
|---|---|---|---|
| Batch | Bulk copy, delete, and existence checks across files | `remote_store.ext.batch` | `batch_copy`, `batch_delete`, `batch_exists` |
| Cache | Transparent read-through caching layer | `remote_store.ext.cache` | `CachedStore`, `MemoryCache`, `cache` |
| Glob | Portable glob for backends without native GLOB capability | `remote_store.ext.glob` | `glob_files` |
| Integrity | Content checksums and digest verification | `remote_store.ext.integrity` | `checksum`, `verify`, `content_digest` |
| Observe | Event hooks and operation logging | `remote_store.ext.observe` | `ObservedStore`, `observe` |
| Partition | Hive-style partition path parsing and construction | `remote_store.ext.partition` | `parse_partition`, `partition_path` |
| Streams | Progress reporting and checksum wrappers for streams | `remote_store.ext.streams` | `ProgressReader`, `ChecksumWriter` |
| Transfer | High-level upload, download, and store-to-store transfer | `remote_store.ext.transfer` | `upload`, `download`, `transfer` |

### Optional (require extras)

| Extension | Description | Module | Extras |
|---|---|---|---|
| Arrow | PyArrow filesystem bridge | `remote_store.ext.arrow` | `pip install remote-store[arrow]` |
| Parquet | Read and write Parquet files via PyArrow | `remote_store.ext.parquet` | `pip install remote-store[arrow]` |
| OpenTelemetry | Distributed tracing spans for store operations | `remote_store.ext.otel` | `pip install remote-store[otel]` |
| Pydantic | Pydantic settings integration for store configuration | `remote_store.ext.pydantic` | `pip install remote-store[pydantic]` |
| YAML | YAML configuration file loading | `remote_store.ext.yaml` | `pip install remote-store[yaml]` |
| Dagster | Dagster IO manager and resource integration | `remote_store.ext.dagster` | `pip install remote-store[dagster]` |

---

## Capabilities

The `Capability` enum (10 values) gates every `Store` method. Query at
runtime with `store.supports(Capability.X)`.

| Capability | Description | Gated methods |
|---|---|---|
| `READ` | Stream or bulk-read file content | `read()`, `read_bytes()`, `read_text()` |
| `WRITE` | Create or overwrite files | `write()`, `write_text()` |
| `DELETE` | Remove files and folders | `delete()`, `delete_folder()` |
| `LIST` | Enumerate files and subfolders | `list_files()`, `list_folders()`, `iter_children()` |
| `MOVE` | Rename/relocate within same backend | `move()` |
| `COPY` | Duplicate within same backend | `copy()` |
| `ATOMIC_WRITE` | Write via temp-and-rename (no partial reads) | `write_atomic()`, `open_atomic()` |
| `METADATA` | Retrieve file/folder metadata | `get_file_info()`, `get_folder_info()` |
| `GLOB` | Native pattern matching on file paths | `glob()` |
| `SEEKABLE_READ` | `read()` returns a seekable stream | `read()`, `read_seekable()` |

---

## Install extras

```
pip install remote-store[s3]          # S3 via s3fs
pip install remote-store[s3-pyarrow]  # S3 via s3fs + PyArrow
pip install remote-store[sftp]        # SFTP via paramiko
pip install remote-store[azure]       # Azure Data Lake via azure SDK
pip install remote-store[sql]         # SQL blob store via SQLAlchemy
pip install remote-store[sql-query]   # SQL query store via SQLAlchemy + PyArrow
pip install remote-store[arrow]       # PyArrow filesystem + Parquet extension
pip install remote-store[otel]        # OpenTelemetry tracing
pip install remote-store[pydantic]    # Pydantic settings integration
pip install remote-store[yaml]        # YAML config loading
pip install remote-store[dagster]     # Dagster IO manager
pip install remote-store[toml]        # TOML config (stdlib on 3.11+)
pip install remote-store[requests]    # requests HTTP adapter
pip install remote-store[httpx]       # httpx HTTP adapter
```
