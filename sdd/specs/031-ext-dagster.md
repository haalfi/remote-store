# ext.dagster - Dagster IO Manager Adapter Specification

## Overview

`ext.dagster` provides a thin adapter that wraps any existing `Store` as a
Dagster `IOManager`, enabling teams already using remote-store to reuse their
Store configuration (credentials, retry policy, caching, observability) inside
Dagster pipelines without duplicating config into `dagster-aws` /
`dagster-azure`.

**Module:** `src/remote_store/ext/dagster.py`
**Dependencies:** `dagster>=1.9` (optional extra)
**Related:** [001-store-api.md](001-store-api.md) (Store API),
research (`sdd/research/research-dagster-extension.md`), ID-075.

**Scope:** v1 only — `dagster_io_manager(store)` factory function.
v2 (`DagsterStoreResource`, `RemoteStoreIOManager`) is deferred.

---

## Serializer Protocol

### DAG-001: Serializer Protocol

**Invariant:** `Serializer` is a `typing.Protocol` (runtime-checkable) with:

```python
@runtime_checkable
class Serializer(Protocol):
    extension: str
    def serialize(self, obj: Any) -> bytes: ...
    def deserialize(self, data: bytes) -> Any: ...
```

- `extension`: file extension including the dot (e.g., `".pkl"`, `".json"`,
  `".parquet"`).
- `serialize(obj)`: converts a Python object to bytes.
- `deserialize(data)`: converts bytes back to a Python object.

### DAG-002: PickleSerializer

**Invariant:** `PickleSerializer` implements `Serializer` with:
- `extension = ".pkl"`
- `serialize`: uses `pickle.dumps(obj)`.
- `deserialize`: uses `pickle.loads(data)`.

**Roundtrip:** for any picklable object `obj`,
`PickleSerializer().deserialize(PickleSerializer().serialize(obj)) == obj`.

### DAG-003: JsonSerializer

**Invariant:** `JsonSerializer` implements `Serializer` with:
- `extension = ".json"`
- `serialize`: uses `json.dumps(obj).encode("utf-8")`.
- `deserialize`: uses `json.loads(data)`.

**Roundtrip:** for any JSON-serializable object `obj`,
`JsonSerializer().deserialize(JsonSerializer().serialize(obj)) == obj`.

### DAG-004: ParquetSerializer

**Invariant:** `ParquetSerializer` implements `Serializer` with:
- `extension = ".parquet"`
- `serialize`: converts a pandas or polars DataFrame to Parquet bytes via
  `pyarrow`.
- `deserialize`: reads Parquet bytes back to a pandas DataFrame via
  `pyarrow`.

**Guard:** instantiating `ParquetSerializer` when `pyarrow` is not installed
raises `ModuleNotFoundError` with the message:
`"PyArrow is required for the parquet serializer. Install it with: pip install 'remote-store[dagster,arrow]'"`.

---

## Path Generation

### DAG-005: Asset Path Derivation

**Invariant:** the storage path for an asset is derived from
`context.asset_key.path` (joined with `/`) plus the partition key
(when `context.has_partition_key` is true) plus the serializer extension:

| Asset key | Partition key | Derived path |
|-----------|--------------|--------------|
| `["foo", "bar"]` | *(none)* | `foo/bar.<ext>` |
| `["foo", "bar"]` | `"2026-01"` | `foo/bar/2026-01.<ext>` |
| `["report"]` | *(none)* | `report.<ext>` |

The `Store`'s `root_path` acts as a namespace prefix — path generation
does not embed it.

### DAG-006: Multi-Segment Asset Key

**Invariant:** asset keys with multiple path segments produce nested paths.
`AssetKey(["ns", "group", "table"])` → `ns/group/table.<ext>`.

---

## IO Manager Behavior

### DAG-007: handle_output Writes and Adds Metadata

**Invariant:** `handle_output(context, obj)`:

1. Serializes `obj` using the configured serializer.
2. Writes the serialized bytes to the Store at the derived path via
   `store.write(path, data, overwrite=True)`.
3. Calls `context.add_output_metadata({"path": path, "size": len(data)})`.

When `obj` is `None`, it is still serialized and written (Dagster convention:
allows distinguishing "never materialized" from "materialized as None").

### DAG-008: load_input Reads and Deserializes

**Invariant:** `load_input(context)`:

1. Derives the path from the upstream output context's asset identifier.
2. Reads bytes from the Store via `store.read_bytes(path)`.
3. Deserializes the bytes using the configured serializer.
4. Returns the deserialized object.

**Raises:** `NotFound` (from Store) when the file does not exist.

### DAG-009: Custom Serializer

**Invariant:** any object satisfying the `Serializer` protocol can be passed
to `dagster_io_manager(store, serializer=my_serializer)`. The IO manager
uses `my_serializer.extension`, `.serialize()`, and `.deserialize()`.

### DAG-010: Missing PyArrow Error

**Invariant:** passing `serializer="parquet"` when `pyarrow` is not installed
raises `ModuleNotFoundError` with a message containing
`"pip install 'remote-store[dagster,arrow]'"`.

---

## Factory Function

### DAG-011: dagster_io_manager Signature

**Invariant:**

```python
def dagster_io_manager(
    store: Store,
    *,
    serializer: str | Serializer = "pickle",
) -> IOManager: ...
```

**Parameters:**
- `store`: an existing `Store` instance. The caller owns its lifecycle.
- `serializer`: `"pickle"` (default), `"json"`, `"parquet"`, or a custom
  `Serializer` object.

**Postconditions:**
- Returns an `IOManager` instance wrapping the Store.
- The Store is not closed by the IO manager.

**Raises:**
- `ValueError` when `serializer` is an unrecognized string.
