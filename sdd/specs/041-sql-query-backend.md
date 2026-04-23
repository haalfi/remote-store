# SQL Query Backend Specification

## Overview

`SQLQueryBackend` implements the `Backend` ABC as a read-only query
materializer. It maps path keys to SQL queries and serializes result sets to
bytes in the format implied by the key's file extension (Parquet, CSV, Arrow
IPC).

Shares `_SQLAlchemyBaseBackend` with `SQLBlobBackend` (v1). This spec covers
only `SQLQueryBackend` (v2).

**Primary use cases:** exposing SQL query results as portable data products,
on-demand materialization of views/reports, bridging SQL databases into the
Store abstraction for downstream consumers who don't need to know the source is
a database.

**Dependencies:** `sqlalchemy>=2.0`, `pyarrow>=12.0.0` (optional extra:
`sql-query`).

**Architecture:** Two-class design with shared base — see
[ADR-0018](../adrs/0018-sqlalchemy-two-class-architecture.md).

---

## Construction

### SQL-QUERY-001: Constructor

**Signature:**
```python
SQLQueryBackend(
    url: str | None = None,
    *,
    engine: Engine | None = None,
    queries: dict[str, str] | None = None,
    strict: bool = True,
    serializer: ResultSerializer | None = None,
)
```

**Preconditions:**
- Exactly one of `url` or `engine` must be provided. Both or neither raises
  `ValueError`.
- `queries`, if provided, must have non-empty string keys and non-empty string
  values. Empty keys or values raise `ValueError`.
- If `strict=False`, raises `NotImplementedError` (view/convention discovery
  deferred to future version).

**Postconditions:**
- Engine is created (if `url`) or stored (if `engine`).
- If SQLite: `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` are set.
- Key registry is built from the `queries` dict.
- If `serializer` is `None`, defaults to `ArrowSerializer()`.

### SQL-QUERY-002: Backend Name

**Invariant:** `name` property returns `"sql-query"`.

### SQL-QUERY-003: Capability Declaration

**Invariant:** `SQLQueryBackend` declares 5 capabilities: `READ`, `LIST`,
`METADATA`, `GLOB`, `SEEKABLE_READ`.

### SQL-QUERY-004: Repr

**Invariant:** `repr(backend)` returns:
```
SQLQueryBackend(dialect='sqlite', keys=3, strict=True)
```

Credential-bearing URL components are never included.

### SQL-QUERY-005: Registration

**Invariant:** The `"sql-query"` backend type is registered in
`_register_builtin_backends()` behind a `try/except ImportError` guard.
The registration guard checks for `sqlalchemy` (required for import).
`pyarrow` is checked eagerly at construction time (`__init__`) with a
clear error message directing users to install `remote-store[sql-query]`.

---

## Key Resolution

### SQL-QUERY-010: Explicit Query Mapping

**Invariant:** Keys are resolved by exact lookup in the `queries` dict.
If the key is not found, `NotFound` is raised. No partial matching, no
normalization beyond standard path validation.

Resolution precedence (v2 implements level 1 only):
1. Explicit mapping (`queries` dict) — highest priority
2. View-based (deferred)
3. Convention-based (deferred)

### SQL-QUERY-011: Strict Mode

**Invariant:** `strict=True` (default) restricts resolution to the explicit
`queries` dict only. Setting `strict=False` raises `NotImplementedError` in
v2 — view-based and convention-based discovery are deferred to a future
version.

### SQL-QUERY-012: Format Detection

**Invariant:** The serialization format is determined by the key's file
extension:

| Extension | Format |
|-----------|--------|
| `.parquet` | Apache Parquet |
| `.csv` | CSV |
| `.arrow`, `.ipc` | Arrow IPC |

Keys without a recognized extension raise `InvalidPath` with a message listing
supported extensions.

---

## Serialization

### SQL-QUERY-013: ResultSerializer Protocol

**Invariant:** `ResultSerializer` is a `typing.Protocol`:
```python
@runtime_checkable
class ResultSerializer(Protocol):
    def serialize(self, rows: Sequence[Any], columns: Sequence[str], format: str) -> bytes: ...
```

The `format` parameter is the lowercase extension without the dot (e.g.,
`"parquet"`, `"csv"`, `"arrow"`). The `rows` parameter is a sequence of
row tuples. The `columns` parameter is the column name list.

### SQL-QUERY-014: ArrowSerializer

**Invariant:** The built-in `ArrowSerializer` converts rows + columns to a
`pyarrow.Table`, then serializes to the requested format:
- `"parquet"` — `pyarrow.parquet.write_table()`
- `"csv"` — `pyarrow.csv.write_csv()`
- `"arrow"` / `"ipc"` — `pyarrow.ipc.RecordBatchFileWriter`

An empty result set (zero rows) produces a valid file with schema but no data.

Unsupported format strings raise `ValueError`.

---

## Operations

### SQL-QUERY-020: read()

**Invariant:** `read(path)` resolves the key to SQL, executes the query,
serializes the result, and returns a seekable `BinaryIO`.

**Pipeline:**
1. Validate path (same rules as SQL-BLOB-060).
2. Resolve key to SQL string via the `queries` dict.
3. Detect format from file extension.
4. Execute SQL: `connection.execute(sa.text(sql))` within `_map_errors()`.
5. Serialize: `self._serializer.serialize(rows, columns, format)`.
6. Return `BufferedReader(BytesIO(data))`.

An empty result set is valid — not an error.

### SQL-QUERY-021: read_bytes()

**Invariant:** Same pipeline as `read()`, returns raw `bytes`.

### SQL-QUERY-030: list_files()

**Invariant:** Enumerates keys from the key registry (not database tables).
Filters by prefix matching. Returns `FileInfo` for each matching key with
`size=0` (sentinel — size unknown until materialized) and
`modified_at=datetime.min(tzinfo=utc)`.

- Non-recursive: only direct children of the prefix.
- Recursive: all keys under the prefix.
- `max_depth`: limits depth of suffix beyond prefix.

### SQL-QUERY-031: list_folders()

**Invariant:** Derives virtual folders from key registry paths. Same
prefix-based deduplication logic as `SQLBlobBackend.list_folders()`.

### SQL-QUERY-032: glob()

**Invariant:** Applies `pattern_to_regex(pattern)` from `_glob.py` against
the key registry. Returns `FileInfo` for all matching keys. No SQL-side
narrowing needed since the key set is in-memory.

---

## Metadata

### SQL-QUERY-040: get_file_info()

**Invariant:** Returns `FileInfo` with:
- `path`: the requested key as `RemotePath`
- `name`: final path component
- `size`: `0` (sentinel — unknown until materialized)
- `modified_at`: `datetime.min.replace(tzinfo=timezone.utc)`
- `extra`: `{"materialized": False}`

Raises `NotFound` if the key is not in the registry.

### SQL-QUERY-041: get_folder_info()

**Invariant:** Computes folder info from the key registry:
- `file_count`: number of keys under prefix
- `total_size`: `0` (all files have sentinel size)
- `modified_at`: `None`

Raises `NotFound` if no keys match the prefix and path is non-empty.

---

## Existence Checks

### SQL-QUERY-042: exists()

**Invariant:** Returns `True` if path matches a registered key (file) or
any key starts with `path/` (virtual folder). Empty path returns `True`
(root).

### SQL-QUERY-043: is_file()

**Invariant:** Returns `True` if path is an exact key in the registry.
Empty path returns `False`.

### SQL-QUERY-044: is_folder()

**Invariant:** Returns `True` if any registered key starts with `path/`.
Empty path returns `True` (root).

---

## Unsupported Operations

### SQL-QUERY-050: Write Operations

**Invariant:** The following methods raise `CapabilityNotSupported` with
`backend=self.name`:

- `write()` — capability `"write"`
- `write_atomic()` — capability `"atomic_write"`
- `open_atomic()` — capability `"atomic_write"`
- `delete()` — capability `"delete"`
- `delete_folder()` — capability `"delete"`
- `move()` — capability `"move"`
- `copy()` — capability `"copy"`

---

## Engine & Connection

### SQL-QUERY-060: check_health()

**Invariant:** Inherited from `_SQLAlchemyBaseBackend`. Executes `SELECT 1`.
Raises `BackendUnavailable` on failure.

### SQL-QUERY-061: close()

**Invariant:** Inherited. Disposes owned engines; no-op for borrowed.

### SQL-QUERY-062: unwrap()

**Invariant:** Inherited. `unwrap(Engine)` returns the SQLAlchemy `Engine`.

### SQL-QUERY-063: SQLite PRAGMAs

**Invariant:** Inherited. WAL mode and `synchronous=NORMAL` for SQLite.

---

## Error Mapping

### SQL-QUERY-070: Exception Translation

| Condition | remote-store error |
|-----------|-------------------|
| Key not in registry | `NotFound` |
| Unsupported file extension | `InvalidPath` |
| `strict=False` | `NotImplementedError` |
| SQL execution error (`ProgrammingError`, `OperationalError`) | `RemoteStoreError` / `BackendUnavailable` |
| Other `SQLAlchemyError` | `RemoteStoreError` |
| Unsupported operation | `CapabilityNotSupported` |

Backend-native exceptions must never leak.

---

## Path Handling

### SQL-QUERY-080: Path Validation

**Invariant:** Same rules as SQL-BLOB-060:
- No null bytes -> `InvalidPath`
- No absolute paths (leading `/`) -> `InvalidPath`
- No `..` segments -> `InvalidPath`
- Empty path allowed for folder operations (root), rejected for file operations.

---

## Performance

### SQL-QUERY-090: Query Execution

**Invariant:** Queries execute via SQLAlchemy Core `connection.execute()`.
Full materialization of result sets in memory. Streaming/chunked execution
is deferred to a future version.

### SQL-QUERY-091: Serialization Overhead

**Invariant:** The `ArrowSerializer` converts SQL rows to a PyArrow Table,
then serializes. This is a full copy. Zero-copy paths (ADBC) are deferred
to v3.
