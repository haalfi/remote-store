# SQLQueryBackend

API reference for `SQLQueryBackend` --- read-only SQL query materializer that maps path keys to SQL queries and serializes results to Parquet, CSV, or Arrow IPC.

## SQLQueryBackend

```
SQLQueryBackend(
    url: str | None = None,
    *,
    engine: Engine | None = None,
    queries: dict[str, str] | None = None,
    strict: bool = True,
    serializer: ResultSerializer | None = None,
)
```

Read-only SQL query materializer implementing a subset of the Backend contract.

Maps path keys to SQL queries. On `read()`, executes the query and serializes the result set to the format implied by the key's file extension (Parquet, CSV, or Arrow IPC).

Capabilities: `READ`, `LIST`, `METADATA`, `GLOB`, `SEEKABLE_READ`.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with SQL query details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="sql-query" and details containing
- `ResolutionPlan` – source and format.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

Yield files under *path*, one `FileInfo` at a time.

The key set is the configured query registry, held in memory, so a listing issues no database round trip. Folder structure is derived from `/` in the key suffix, and `recursive` / `max_depth` filter client-side — there is no traversal to prune. A prefix matching no registered key yields nothing.

Raises:

- `InvalidPath` – If path is absolute, contains a null byte, or contains a .. segment.

## Serialization

## ResultSerializer

Converts SQL result rows to bytes in a specific format.

### serialize

```
serialize(
    rows: Sequence[Any], columns: Sequence[str], format: str
) -> bytes
```

Serialize rows with given column names to the specified format.

Parameters:

- **`rows`** (`Sequence[Any]`) – Sequence of row tuples from SQL execution.
- **`columns`** (`Sequence[str]`) – Column name list.
- **`format`** (`str`) – Target format ("parquet", "csv", "arrow").

Returns:

- `bytes` – Serialized bytes.

## ArrowSerializer

Serializes SQL result sets via PyArrow.

Converts rows + columns to a `pyarrow.Table`, then writes to the requested format. Imports `pyarrow` lazily so that `SQLBlobBackend` remains importable without it.

### serialize

```
serialize(
    rows: Sequence[Any], columns: Sequence[str], format: str
) -> bytes
```

Serialize rows to Parquet, CSV, or Arrow IPC.
