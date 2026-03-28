# SQL Blob Backend Specification

## Overview

`SQLBlobBackend` implements the `Backend` ABC using a SQLAlchemy-managed SQL
table as key-value blob storage. Each row holds one "file" with its key, data,
and metadata.

Shares a `_SQLAlchemyBaseBackend` abstract base with future `SQLQueryBackend`
(v2). This spec covers only `SQLBlobBackend` (v1).

**Primary use cases:** zero-infrastructure persistent store (SQLite), shared
database-backed file storage (PostgreSQL, MySQL), embedded metadata+blob
co-location, portable single-file archives.

**Dependencies:** `sqlalchemy>=2.0` (optional extra: `sql`).

**Architecture:** Two-class design with shared base — see
[ADR-0018](../adrs/0018-sqlalchemy-two-class-architecture.md).

---

## Construction

### SQL-BLOB-001: Constructor

**Signature:**
```python
SQLBlobBackend(
    url: str | None = None,
    *,
    engine: Engine | None = None,
    table_name: str = "remote_store_objects",
    create_table: bool = True,
    max_blob_size: int | None = None,
)
```

**Preconditions:**
- Exactly one of `url` or `engine` must be provided. Both or neither raises
  `ValueError`.
- `table_name` must be a non-empty string.
- `max_blob_size`, if provided, must be a positive integer.

**Postconditions:**
- Engine is created (if `url`) or stored (if `engine`).
- If SQLite: `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` are set.
- If `create_table=True`: the table is created if it doesn't exist.
- If `create_table=False`: the table must already exist. The backend
  introspects the table to detect available optional columns.

### SQL-BLOB-002: Backend Name

**Invariant:** `name` property returns `"sql-blob"`.

### SQL-BLOB-003: Capability Declaration

**Invariant:** `SQLBlobBackend` declares all 10 capabilities: `READ`, `WRITE`,
`DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`,
`SEEKABLE_READ`.

### SQL-BLOB-004: Repr

**Invariant:** `repr(backend)` returns:
```
SQLBlobBackend(dialect='sqlite', table='remote_store_objects')
```

Credential-bearing URL components are never included.

### SQL-BLOB-005: Registration

**Invariant:** The `"sql-blob"` backend type is registered in
`_register_builtin_backends()` behind a `try/except ImportError` guard.

---

## Schema

### SQL-BLOB-010: Default Table Schema

```sql
CREATE TABLE IF NOT EXISTS remote_store_objects (
    key          TEXT    PRIMARY KEY,
    data         BLOB    NOT NULL,
    size         INTEGER NOT NULL,
    modified_at  REAL    NOT NULL,
    content_type TEXT,
    digest       TEXT,
    extra        TEXT
);
```

- `key`: forward-slash-separated path, validated identically to other backends.
- `data`: file content as binary blob.
- `size`: byte length of `data`, maintained by the backend on every write.
- `modified_at`: UTC timestamp stored as Unix epoch float for cross-dialect
  portability.
- `content_type`: optional MIME type string.
- `digest`: optional content hash as `"algorithm:hex"` string.
- `extra`: optional JSON-encoded metadata dict.

The `PRIMARY KEY` on `key` creates a B-tree index supporting prefix scans.

### SQL-BLOB-011: Custom Table Name

**Invariant:** `table_name` parameter changes the table name. The schema
is identical.

### SQL-BLOB-012: Existing Table (create_table=False)

**Invariant:** When `create_table=False`, the backend requires at minimum
`(key TEXT PK, data BLOB)`. Optional columns (`size`, `modified_at`,
`content_type`, `digest`, `extra`) are detected by table introspection.
Missing columns degrade gracefully:

- No `size` → computed from `len(data)` on read (not stored).
- No `modified_at` → `FileInfo.modified_at` uses `datetime.min`.
- No `content_type` → `FileInfo.content_type` is `None`.
- No `digest` → `FileInfo.digest` is `None`.
- No `extra` → `FileInfo.extra` is `{}`.

---

## Operations

All operations follow the `Backend` ABC contract (spec 003). This section
documents SQL-specific behavior only.

### SQL-BLOB-020: read()

**Invariant:** `read(path)` returns a seekable `BinaryIO`.

**Implementation:** `SELECT data FROM t WHERE key = :key` → wraps the result
in `BufferedReader(BytesIO(data))`. Full materialization on every read.
Raises `NotFound` if no row matches.

### SQL-BLOB-021: read_bytes()

**Invariant:** `read_bytes(path)` executes `SELECT data FROM t WHERE key = :key`
and returns the blob as `bytes`. Raises `NotFound` if no row matches.

### SQL-BLOB-022: write()

**Invariant:** Uses `INSERT ... ON CONFLICT(key) DO UPDATE` when
`overwrite=True`. Uses plain `INSERT` when `overwrite=False` (raises
`AlreadyExists` on conflict). Sets `size = len(data)` and
`modified_at = now()`.

**max_blob_size guard:** If `max_blob_size` is set and content exceeds it,
raises `ValueError` before executing the SQL.

### SQL-BLOB-023: write_atomic() / open_atomic()

**Invariant:** `write_atomic()` delegates to `write()` — a single SQL
statement is inherently atomic within a transaction.

`open_atomic()` yields a `BytesIO` buffer. On successful exit, commits via
`write()`. On exception, discards the buffer. Mirrors `MemoryBackend` pattern.

### SQL-BLOB-024: delete()

**Invariant:** `DELETE FROM t WHERE key = :key`. Checks rowcount; if 0 and
`missing_ok=False`, raises `NotFound`.

### SQL-BLOB-025: delete_folder()

**Invariant:** Folder semantics are virtual (prefix-based). A "folder" is any
prefix that has keys starting with `prefix/`.

- `recursive=True`: `DELETE FROM t WHERE key LIKE :prefix || '/%'`
- `recursive=False`: Check if any keys exist with prefix. If yes, raise
  `DirectoryNotEmpty`. If no keys exist, raise `NotFound` (unless
  `missing_ok`).

### SQL-BLOB-026: exists() / is_file() / is_folder()

- `exists(path)`: Returns `True` if path matches a key (file) OR if any key
  starts with `path/` (folder). Empty path returns `True` (root).
- `is_file(path)`: `SELECT 1 FROM t WHERE key = :key`.
- `is_folder(path)`: Empty path → `True`. Otherwise
  `SELECT 1 FROM t WHERE key LIKE :prefix LIMIT 1` where prefix = `path/`.

### SQL-BLOB-027: list_files()

**Invariant:** `SELECT key, size, modified_at, content_type, digest, extra
FROM t WHERE key LIKE :prefix || '%'`.

- Non-recursive: filter results to include only direct children (no additional
  `/` in the suffix after prefix).
- Recursive: return all matching keys.
- `max_depth`: count `/` separators in suffix; exclude entries deeper than
  `max_depth`.

### SQL-BLOB-028: list_folders()

**Invariant:** Virtual folders derived from stored keys. Extract the first
path segment after the prefix from all matching keys, deduplicate.

### SQL-BLOB-029: get_file_info()

**Invariant:** `SELECT size, modified_at, content_type, digest, extra
FROM t WHERE key = :key`. Maps columns to `FileInfo` fields. Raises
`NotFound` if no row.

### SQL-BLOB-030: get_folder_info()

**Invariant:** `SELECT COUNT(*), SUM(size), MAX(modified_at) FROM t
WHERE key LIKE :prefix || '%'`. Returns `FolderInfo`. Raises `NotFound` if
count is 0 and path is not empty string.

### SQL-BLOB-031: move()

**Invariant:** Within a single transaction:
1. Check source exists (else `NotFound`).
2. Check destination doesn't exist (else `AlreadyExists`, unless `overwrite`).
3. If `overwrite` and dst exists, delete dst row.
4. `UPDATE t SET key = :dst WHERE key = :src`.

### SQL-BLOB-032: copy()

**Invariant:** Within a single transaction:
1. Check source exists (else `NotFound`).
2. Check destination doesn't exist (else `AlreadyExists`, unless `overwrite`).
3. `INSERT INTO t SELECT :dst, data, size, :now, content_type, digest, extra
   FROM t WHERE key = :src` (or UPDATE if overwrite and dst exists).

### SQL-BLOB-033: glob()

**Invariant:** Convert glob patterns to SQL:
- SQLite: use native `GLOB` operator (case-sensitive, `*` = any, `?` = single).
- Other dialects: convert `*` → `%`, `?` → `_`, use `LIKE`.
- `**` patterns: match any depth (`%` in LIKE).

Return `FileInfo` for all matching keys.

---

## Engine & Connection

### SQL-BLOB-040: check_health()

**Invariant:** Executes `SELECT 1` via the engine. Raises
`BackendUnavailable` on failure.

### SQL-BLOB-041: close()

**Invariant:** If engine is owned, calls `engine.dispose()`. If borrowed,
no-op.

### SQL-BLOB-042: unwrap()

**Invariant:** `unwrap(Engine)` returns the SQLAlchemy `Engine`. Any other
type raises `CapabilityNotSupported`.

### SQL-BLOB-043: SQLite PRAGMAs

**Invariant:** When the dialect is SQLite, the backend sets on connection:
- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`

These are set via a `pool_events.connect` listener so every new connection
gets them.

---

## Error Mapping

### SQL-BLOB-050: Exception Translation

| SQLAlchemy exception | remote-store error |
|---------------------|-------------------|
| `IntegrityError` (on INSERT) | `AlreadyExists` |
| `OperationalError` (connection) | `BackendUnavailable` |
| No row returned for read/info | `NotFound` |
| Other `SQLAlchemyError` | `RemoteStoreError` |

Backend-native exceptions must never leak.

---

## Path Handling

### SQL-BLOB-060: Path Validation

**Invariant:** Same rules as all backends:
- No null bytes → `InvalidPath`
- No absolute paths (leading `/`) → `InvalidPath`
- No `..` segments → `InvalidPath`
- Empty path allowed for folder operations (root), rejected for file operations.

### SQL-BLOB-061: Prefix Matching

**Invariant:** For folder-like operations, the prefix is `path + "/"`. The
trailing slash prevents `"data"` from matching `"dataset/file.txt"`.

---

## Performance

### SQL-BLOB-070: Blob Size Guidelines

- <10 MB: works well across all dialects.
- 10–100 MB: use with caution; `max_blob_size` guard recommended.
- >100 MB: discouraged — use a blob storage backend (S3, Local) instead.

### SQL-BLOB-071: Connection Pooling

**Invariant:** Uses SQLAlchemy's default connection pool. No custom pool
configuration. Users can tune via engine kwargs when passing a pre-built
engine.
