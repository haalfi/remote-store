# SQLBlobBackend

API reference for `SQLBlobBackend` — stores files as key-value rows in any SQLAlchemy-supported SQL database.

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

SQL key-value blob store implementing the full Backend contract.

Uses a SQL table as key-value storage. Each row holds one "file" with its key, data, and metadata. SQLite receives WAL mode and PRAGMA tuning automatically.

Supports all capabilities except `LAZY_READ`.

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

## See also

- [SQL Blob Backend Guide](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md) — usage patterns, configuration, and examples
