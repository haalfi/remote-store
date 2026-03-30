# Features — remote-store v0.20.0

Authoritative snapshot of backends, extensions, capabilities, and install
extras for the current version. Updated each release.

---

## Backends

| Type string | Class | Extras | Always available | Capabilities |
|---|---|---|---|---|
| `local` | `LocalBackend` | — | Yes | All 10 |
| `memory` | `MemoryBackend` | — | Yes | All except GLOB |
| `http` | `ReadOnlyHttpBackend` | — | Yes | READ, METADATA |
| `s3` | `S3Backend` | `pip install remote-store[s3]` | No | All 10 |
| `s3-pyarrow` | `S3PyArrowBackend` | `pip install remote-store[s3-pyarrow]` | No | All 10 |
| `sftp` | `SFTPBackend` | `pip install remote-store[sftp]` | No | All except GLOB |
| `azure` | `AzureBackend` | `pip install remote-store[azure]` | No | All except SEEKABLE_READ |
| `sql-blob` | `SQLBlobBackend` | `pip install remote-store[sql]` | No | All 10 |
| `sql-query` | `SQLQueryBackend` | `pip install remote-store[sql-query]` | No | READ, LIST, METADATA, GLOB, SEEKABLE_READ |

---

## Extensions

### Always available (included in base install)

| Extension | Module | Key exports |
|---|---|---|
| Batch | `remote_store.ext.batch` | `batch_copy`, `batch_delete`, `batch_exists` |
| Cache | `remote_store.ext.cache` | `CachedStore`, `MemoryCache`, `cache` |
| Glob | `remote_store.ext.glob` | `glob_files` |
| Integrity | `remote_store.ext.integrity` | `checksum`, `verify`, `content_digest` |
| Observe | `remote_store.ext.observe` | `ObservedStore`, `observe` |
| Partition | `remote_store.ext.partition` | `parse_partition`, `partition_path` |
| Streams | `remote_store.ext.streams` | `ProgressReader`, `ChecksumWriter` |
| Transfer | `remote_store.ext.transfer` | `upload`, `download`, `transfer` |

### Optional (require extras)

| Extension | Module | Extras |
|---|---|---|
| Arrow | `remote_store.ext.arrow` | `pip install remote-store[arrow]` |
| Parquet | `remote_store.ext.parquet` | `pip install remote-store[arrow]` |
| OpenTelemetry | `remote_store.ext.otel` | `pip install remote-store[otel]` |
| Pydantic | `remote_store.ext.pydantic` | `pip install remote-store[pydantic]` |
| YAML | `remote_store.ext.yaml` | `pip install remote-store[yaml]` |
| Dagster | `remote_store.ext.dagster` | `pip install remote-store[dagster]` |

---

## Capabilities

The `Capability` enum (10 values) gates every `Store` method. Query at
runtime with `store.supports(Capability.X)`.

| Capability | Description | Gated methods |
|---|---|---|
| `READ` | Stream or bulk-read file content | `read()`, `read_bytes()` |
| `WRITE` | Create or overwrite files | `write()` |
| `DELETE` | Remove files and folders | `delete()`, `delete_folder()` |
| `LIST` | Enumerate files and subfolders | `list_files()`, `list_folders()` |
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
