# SQL Blob Backend

The SQL blob backend stores files as key-value rows in any SQLAlchemy-supported database. Each row holds one file with its key, binary data, and metadata.

**Primary use cases:** zero-infrastructure persistent store (SQLite), shared database-backed file storage (PostgreSQL, MySQL), embedded metadata+blob co-location, portable single-file archives.

## Installation

```bash
pip install remote-store[sql]
```

Requires `sqlalchemy>=2.0`.

## Usage

### SQLite (simplest — zero infrastructure)

```python
from remote_store import Store
from remote_store.backends import SQLBlobBackend

backend = SQLBlobBackend(url="sqlite:///store.db")
store = Store(backend=backend)

store.write("models/v3.pkl", model_bytes)
data = store.read_bytes("models/v3.pkl")
```

### PostgreSQL

```python
backend = SQLBlobBackend(url="postgresql://user:pass@localhost/mydb")
store = Store(backend=backend)
```

### Shared engine (web apps)

```python
from sqlalchemy import create_engine

# App's connection pool — shared across the application
engine = create_engine("postgresql://...", pool_size=10)

# Backend borrows the engine; close() is a no-op
backend = SQLBlobBackend(engine=engine)
store = Store(backend=backend)
```

### Via Registry

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={"db": BackendConfig(type="sql-blob", options={"url": "sqlite:///store.db"})},
    stores={"files": StoreProfile(backend="db", root_path="data")},
)

with Registry(config) as registry:
    store = registry.get_store("files")
    store.write("readme.txt", b"Hello!")
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `url` | `str \| None` | `None` | SQLAlchemy database URL. Mutually exclusive with `engine`. |
| `engine` | `Engine \| None` | `None` | Pre-built SQLAlchemy engine. Mutually exclusive with `url`. |
| `table_name` | `str` | `"remote_store_objects"` | Name of the storage table. |
| `create_table` | `bool` | `True` | Auto-create the table if it doesn't exist. |
| `max_blob_size` | `int \| None` | `None` | Maximum blob size in bytes. Raises `ValueError` on write if exceeded. |

Exactly one of `url` or `engine` must be provided.

## Schema

The default table schema:

```sql
CREATE TABLE remote_store_objects (
    key           TEXT    PRIMARY KEY,
    data          BLOB    NOT NULL,
    size          INTEGER NOT NULL,
    modified_at   REAL    NOT NULL,
    content_type  TEXT,
    digest        TEXT,
    extra         TEXT,
    user_metadata TEXT
);
```

### User metadata column

When the `user_metadata` column is present, `SQLBlobBackend` declares the
`WRITE_RESULT_NATIVE` and `USER_METADATA` capabilities. When absent (legacy
tables), neither is declared — a `Store.write*()` call with a non-empty
`metadata=` kwarg raises `CapabilityNotSupported` before any I/O runs.

To add the column to an existing table:

```sql
-- hand-written: schema migrations cannot run in CI
ALTER TABLE remote_store_objects ADD COLUMN user_metadata TEXT;
```

### Using an existing table

Set `create_table=False` to use a pre-existing table. Minimum required columns: `key TEXT` (primary key) and `data BLOB`. Optional columns (`size`, `modified_at`, `content_type`, `digest`, `extra`, `user_metadata`) are detected automatically; missing ones degrade gracefully.

## Capabilities

Supports all capabilities except `LAZY_READ` — the entire blob is loaded into memory before a stream is returned.
See the [capabilities matrix](../capabilities-matrix.md) for full details.

### Implementation notes

- **Non-lazy writes.** `write()` materializes the full stream into memory
  before issuing the SQL INSERT/UPDATE. This is inherent to SQL BLOB columns,
  which require complete data in a single statement. For files larger than
  process memory, use a blob-storage backend (S3, Local, Azure) instead.
- `write_atomic()` delegates to `write()` — single SQL statements are inherently atomic.
- `glob()` uses SQL-side narrowing (SQLite `GLOB` or `LIKE`) then client-side regex to enforce standard glob semantics (GLOB-014).

## SQLite Optimizations

When using SQLite, the backend automatically:

- Enables **WAL mode** (`PRAGMA journal_mode=WAL`) for better concurrent read performance.
- Sets **`PRAGMA synchronous=NORMAL`** for improved write throughput.

These are set on every new connection via SQLAlchemy event listeners. If you pass a shared engine that already has `pool_events.connect` listeners, they will coexist — the backend guards against duplicate registration.

## Folder Semantics

Folders are virtual (prefix-based), not explicit nodes:

- `is_folder("data")` returns `True` if any key starts with `data/`.
- `list_folders("data")` extracts unique first-level subfolder names from stored keys.
- `delete_folder("data", recursive=True)` deletes all keys starting with `data/`.

## Performance Guidelines

| Blob size | Recommendation |
|-----------|---------------|
| < 10 MB | Works well across all databases |
| 10 - 100 MB | Use with caution; set `max_blob_size` |
| > 100 MB | Use a blob storage backend (S3, Local) instead |

## Engine Lifecycle

- **Owned engine** (`url` provided): `close()` calls `engine.dispose()`.
- **Borrowed engine** (`engine` provided): `close()` is a no-op.
- **`unwrap(Engine)`**: Returns the underlying SQLAlchemy `Engine`.
- **`check_health()`**: Executes `SELECT 1` to verify connectivity.

## See also

- [Example script](../examples/sql-blob-backend.md)
- [Capabilities matrix](../capabilities-matrix.md)
- [API reference](../api/store.md)
