# SQL Blob Backend

The SQL blob backend stores files as key-value rows in any SQLAlchemy-supported database. Each row holds one file with its key, binary data, and metadata.

**Primary use cases:** zero-infrastructure persistent store (SQLite), shared database-backed file storage (PostgreSQL, MySQL), embedded metadata+blob co-location, portable single-file archives.

## Installation

```
pip install remote-store[sql]
```

Requires `sqlalchemy>=2.0`.

## Usage

### SQLite (simplest — zero infrastructure)

```
from remote_store import Store
from remote_store.backends import SQLBlobBackend

backend = SQLBlobBackend(url="sqlite:///store.db")
store = Store(backend=backend)

store.write("models/v3.pkl", model_bytes)
data = store.read_bytes("models/v3.pkl")
```

### PostgreSQL

```
backend = SQLBlobBackend(url="postgresql://user:pass@localhost/mydb")
store = Store(backend=backend)
```

### Shared engine (web apps)

```
from sqlalchemy import create_engine

# App's connection pool — shared across the application
engine = create_engine("postgresql://...", pool_size=10)

# Backend borrows the engine; close() is a no-op
backend = SQLBlobBackend(engine=engine)
store = Store(backend=backend)
```

### Via Registry

```
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

| Option          | Type             | Default                  | Description                                                           |
| --------------- | ---------------- | ------------------------ | --------------------------------------------------------------------- |
| `url`           | `str \| None`    | `None`                   | SQLAlchemy database URL. Mutually exclusive with `engine`.            |
| `engine`        | `Engine \| None` | `None`                   | Pre-built SQLAlchemy engine. Mutually exclusive with `url`.           |
| `table_name`    | `str`            | `"remote_store_objects"` | Name of the storage table.                                            |
| `create_table`  | `bool`           | `True`                   | Auto-create the table if it doesn't exist.                            |
| `max_blob_size` | `int \| None`    | `None`                   | Maximum blob size in bytes. Raises `ValueError` on write if exceeded. |

Exactly one of `url` or `engine` must be provided.

## Schema

The default table schema:

```
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

When the `user_metadata` column is present, `SQLBlobBackend` declares the `WRITE_RESULT_NATIVE` and `USER_METADATA` capabilities. When absent (legacy tables), neither is declared — a `Store.write*()` call with a non-empty `metadata=` kwarg raises `CapabilityNotSupported` before any I/O runs.

To add the column to an existing table:

```
-- hand-written: schema migrations cannot run in CI
ALTER TABLE remote_store_objects ADD COLUMN user_metadata TEXT;
```

### Using an existing table

Set `create_table=False` to use a pre-existing table. Minimum required columns: `key TEXT` (primary key) and `data BLOB`. Optional columns (`size`, `modified_at`, `content_type`, `digest`, `extra`, `user_metadata`) are detected automatically; missing ones degrade gracefully.

## Capabilities

Supports all capabilities except `LAZY_READ` — the entire blob is loaded into memory before a stream is returned. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

### Implementation notes

- **Non-lazy writes.** `write()` materializes the full stream into memory before issuing the SQL INSERT/UPDATE. This is inherent to SQL BLOB columns, which require complete data in a single statement. For files larger than process memory, use a blob-storage backend (S3, Local, Azure) instead.
- `write_atomic()` delegates to `write()` — single SQL statements are inherently atomic.
- `glob()` uses SQL-side narrowing (SQLite `GLOB` or `LIKE`) then client-side regex to enforce standard glob semantics.

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

| Blob size   | Recommendation                                 |
| ----------- | ---------------------------------------------- |
| < 10 MB     | Works well across all databases                |
| 10 - 100 MB | Use with caution; set `max_blob_size`          |
| > 100 MB    | Use a blob storage backend (S3, Local) instead |

## Engine Lifecycle

- **Owned engine** (`url` provided): `close()` calls `engine.dispose()`.
- **Borrowed engine** (`engine` provided): `close()` is a no-op.
- **`unwrap(Engine)`**: Returns the underlying SQLAlchemy `Engine`.
- **`check_health()`**: Executes `SELECT 1` to verify connectivity.

## See also

- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/sql-blob-backend/index.md)
- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)

## API Reference

## SQLBlobBackend

```
SQLBlobBackend(
    url: str | None = None,
    *,
    engine: Engine | None = None,
    table_name: str = "remote_store_objects",
    create_table: bool = True,
    max_blob_size: int | None = None,
    reject_write_under_file_ancestor: bool = False,
)
```

Bases: `_SQLAlchemyBaseBackend`

SQL key-value blob store implementing the full Backend contract.

Uses a SQL table as key-value storage. Each row holds one "file" with its key, data, and metadata. SQLite receives WAL mode and PRAGMA tuning automatically.

Supports all capabilities except `LAZY_READ`.

Every mutating operation runs inside a single database transaction, so `write`, `write_atomic`, `move`, and `copy` are atomic — a failure rolls back with no partial row left behind (`ATOMIC_MOVE` is advertised).

Note

**Non-lazy reads and writes.** Both `read()` and `write()` materialize the full content in memory. `read()` loads the entire BLOB before returning a stream (no `LAZY_READ`). `write()` reads the full stream before issuing the SQL INSERT/UPDATE because BLOB columns require complete data in a single statement. For files larger than process memory, use a blob-storage backend (S3, Local, Azure) instead.

Parameters:

- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / open_atomic / move / copy issue one SELECT 1 per slash-aligned ancestor of the target path and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. Default False; paths without slashes short-circuit.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with SQL blob details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="sql-blob" and details containing
- `ResolutionPlan` – table_name.

### exists

```
exists(path: str) -> bool
```

Return `True` if a key or key-prefix exists at *path*; never `NotFound`.

Folders are virtual — *path* counts as a folder when any key begins with `path + "/"`. The root (`""`) always exists. Costs one or two `SELECT`s.

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.
- `BackendUnavailable` – If the database is unreachable.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if an exact key exists at *path* (one `SELECT`).

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.
- `BackendUnavailable` – If the database is unreachable.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if any key begins with `path + "/"` (a virtual folder).

The root is always a folder. Costs one `SELECT`.

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.
- `BackendUnavailable` – If the database is unreachable.

### read

```
read(path: str) -> BinaryIO
```

Return a binary stream over the stored BLOB for *path*.

Loads the entire BLOB into memory before returning the stream — the read does not stream (`LAZY_READ` is not advertised), so peak memory scales with the object size. For objects larger than process memory use a blob-storage backend (S3, Local, Azure).

Raises:

- `NotFound` – If no key exists at path.
- `InvalidPath` – If path is empty, absolute, or malformed.
- `BackendUnavailable` – If the database is unreachable.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Return the full stored BLOB for *path* as bytes.

Like `read`, materialises the whole object in memory.

Raises:

- `NotFound` – If no key exists at path.
- `InvalidPath` – If path is empty, absolute, or malformed.
- `BackendUnavailable` – If the database is unreachable.

### write

```
write(
    path: str,
    content: WritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Store *content* at *path* in a single, atomic transaction.

The whole body is buffered in memory before the `INSERT`/`UPDATE` (BLOB columns need the complete value in one statement — no streaming write), and the row is written inside one transaction, so a failure rolls back with no partial row left behind.

Raises:

- `AlreadyExists` – If a key exists at path and overwrite is False.
- `InvalidPath` – If path is empty/malformed, or (with the reject_write_under_file_ancestor opt-in) an ancestor key exists as a file.
- `BackendUnavailable` – If the database operation fails.

### write_atomic

```
write_atomic(
    path: str,
    content: WritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Store *content* at *path* atomically (delegates to `write`).

SQL writes are already transactional, so this is exactly `write`; the whole body is buffered first.

Raises:

- `AlreadyExists` – If a key exists at path and overwrite is False.
- `InvalidPath` – If path is empty/malformed, or (opt-in) an ancestor key exists as a file.
- `BackendUnavailable` – If the database operation fails.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield an in-memory buffer committed to *path* atomically on clean exit.

Writes accumulate in a `BytesIO`; on exit the buffer is stored via `write` in one transaction. An exception before exit leaves *path* untouched.

Raises:

- `AlreadyExists` – If a key exists at path and overwrite is False.
- `InvalidPath` – If path is empty/malformed, or (opt-in) an ancestor key exists as a file.
- `BackendUnavailable` – If the database operation fails.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the row at *path* in one transaction.

Raises:

- `NotFound` – If no key exists at path and missing_ok is False.
- `InvalidPath` – If path is empty, absolute, or malformed.
- `BackendUnavailable` – If the database operation fails.

### delete_folder

```
delete_folder(
    path: str,
    *,
    recursive: bool = False,
    missing_ok: bool = False,
) -> None
```

Delete every key under the virtual folder *path*.

Folders are key prefixes, not stored rows, so a folder "exists" only when it has children: a non-recursive call on an existing folder therefore always raises `DirectoryNotEmpty`. `recursive=True` deletes all keys under `path + "/"` in one atomic transaction.

Raises:

- `NotFound` – If no key exists under path and missing_ok is False.
- `DirectoryNotEmpty` – If recursive is False (an existing virtual folder is never empty).
- `InvalidPath` – If path is empty, absolute, or malformed.
- `BackendUnavailable` – If the database operation fails.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

Yield files under *path*.

One `SELECT` fetches every key under the prefix; folder structure is derived from `/` in the key suffix, and `recursive` / `max_depth` filter client-side. A missing prefix yields nothing.

Raises:

- `BackendUnavailable` – If the database operation fails, surfaced during iteration.

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

Yield immediate virtual subfolders of *path* as `FolderEntry` records.

One `SELECT` over keys under the prefix; folder names are the distinct first segments of the key suffixes. A missing prefix yields nothing.

Raises:

- `BackendUnavailable` – If the database operation fails, surfaced during iteration.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield the immediate files and virtual folders under *path* in one `SELECT`.

Overrides the base two-pass default: a single query over the prefix yields `FileInfo` for direct-child keys and `FolderEntry` for the distinct first suffix segments. A missing prefix yields nothing.

Raises:

- `BackendUnavailable` – If the database operation fails, surfaced during iteration.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return metadata for the file at *path* from one `SELECT`.

Raises:

- `NotFound` – If no key exists at path.
- `InvalidPath` – If path is empty, absolute, or malformed.
- `BackendUnavailable` – If the database is unreachable.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregate metadata for the virtual folder *path*.

File count, total size, and latest modification time come from one aggregate `SELECT` (`COUNT`/`SUM`/`MAX`) over keys under the prefix — no per-file round-trips.

Raises:

- `NotFound` – If no key exists under path.
- `InvalidPath` – If path is absolute or malformed.
- `BackendUnavailable` – If the database is unreachable.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move (rename) the key *src* to *dst* in one atomic transaction.

Implemented as an `UPDATE` of the row's key — the BLOB is never transferred through Python. The whole operation (source check, optional destination replace, rename) runs in one transaction, so a failure rolls back cleanly. `src == dst` verifies the source exists and is otherwise a no-op.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists and overwrite is False.
- `InvalidPath` – If src or dst is malformed, or (opt-in) an ancestor of dst exists as a file.
- `BackendUnavailable` – If the database operation fails.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the key *src* to *dst* in one atomic transaction.

Implemented as a single `INSERT ... SELECT`, so the BLOB is duplicated entirely inside the database — no bytes pass through Python. `src == dst` verifies the source exists and is otherwise a no-op.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists and overwrite is False.
- `InvalidPath` – If src or dst is malformed, or (opt-in) an ancestor of dst exists as a file.
- `BackendUnavailable` – If the database operation fails.

### glob

```
glob(pattern: str) -> Iterator[FileInfo]
```

Yield files whose key matches the glob *pattern*.

Narrows SQL-side with a prefix `LIKE` where the pattern allows (on every dialect — SQLite's native `GLOB` is deliberately avoided because it mishandles `**`), then applies the full glob regex to each row. Costs one `SELECT`.

Raises:

- `BackendUnavailable` – If the database operation fails, surfaced during iteration.
