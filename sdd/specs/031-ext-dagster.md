# ext.dagster - Dagster Integration Specification

## Overview

`ext.dagster` covers both of Dagster's storage extension points. The
`IOManager` adapter wraps any existing `Store` so teams already using
remote-store can reuse their Store configuration (credentials, retry policy,
caching, observability) inside Dagster pipelines without duplicating config
into `dagster-aws` / `dagster-azure`. The `RemoteStoreComputeLogManager`
(v3) is a Dagster *instance* component, configured in `dagster.yaml`, that
persists op/step `stdout` / `stderr` to any remote-store backend.

**Module:** `src/remote_store/ext/dagster.py`
**Dependencies:** `dagster>=1.9` (optional extra)
**Related:** [001-store-api.md](001-store-api.md) (Store API),
research (`sdd/research/research-dagster-extension.md`),
[RFC-0014](../rfcs/rfc-0014-dagster-compute-log-manager.md), ID-075, ID-208.

**Scope:** v1 — `dagster_io_manager(store)` factory function (DAG-001 – DAG-011).
v2 adds `DagsterStoreResource` and `RemoteStoreIOManager` (DAG-012 – DAG-020).
v3 adds `RemoteStoreComputeLogManager` (DAG-021 – DAG-033).

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
- `serialize`: converts a pandas DataFrame, polars DataFrame, or PyArrow Table
  to Parquet bytes via `pyarrow`.
- `deserialize`: reads Parquet bytes back to a PyArrow Table.
  Callers needing pandas or polars convert the result themselves
  (e.g. `table.to_pandas()` or `pl.from_arrow(table)`).

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

---

## v2: Dagster-Config-Driven Store

### DAG-012: DagsterStoreResource Builds Store

**Invariant:** `DagsterStoreResource` is a `ConfigurableResource` with fields:
- `backend_type: str` — registered backend type identifier
- `backend_options: dict[str, Any]` — kwargs for backend constructor (default `{}`)
- `root_path: str` — Store root path (default `""`)

`setup_for_execution` constructs the backend via the factory registry and creates a `Store`. `get_store()` returns the cached Store instance.

**Postcondition:** After `setup_for_execution`, `get_store()` returns a functional Store.

### DAG-013: DagsterStoreResource Teardown

**Invariant:** `teardown_after_execution` calls `store.close()` on the cached Store and resets the internal reference to `None`. If called before `setup_for_execution` (no Store exists), it is a no-op — does not raise.

### DAG-014: Unknown Backend Type

**Invariant:** `setup_for_execution` with an unregistered `backend_type` raises `ValueError` with a message containing the unknown type name and the list of registered types.

### DAG-015: RemoteStoreIOManager Factory

**Invariant:** `RemoteStoreIOManager` is a `ConfigurableIOManagerFactory` with fields:
- `backend_type: str` — registered backend type identifier
- `backend_options: dict[str, Any]` — kwargs for backend constructor (default `{}`)
- `root_path: str` — Store root path (default `""`)
- `serializer: str` — serializer name (default `"pickle"`)

`setup_for_execution` constructs the Store (same as `DagsterStoreResource`).
`teardown_after_execution` closes the Store.
`create_io_manager` returns an `IOManager` instance backed by the Store.

**Raises:** `ValueError` when `serializer` is an unrecognized string (same as DAG-011).

### DAG-016: RemoteStoreIOManager Roundtrip

**Invariant:** An object written via `handle_output` through the `RemoteStoreIOManager`-created IO manager can be read back via `load_input` with the same asset key.

### DAG-017: dagster_dataset_io_manager Factory

**Invariant:**

```python
def dagster_dataset_io_manager(store: Store) -> IOManager: ...
```

Returns an IO manager that uses `ParquetDatasetStore` for dataset-level I/O. Accepts DataFrames (pandas, polars, Arrow Table) on `handle_output` and returns Arrow Tables on `load_input`.

**Raises:** `ModuleNotFoundError` when `pyarrow` is not installed, with message containing `"pip install 'remote-store[dagster,arrow]'"`.

### DAG-018: Dataset IO Manager Path

**Invariant:** The dataset key is derived from `context.asset_key.path` (joined with `/`) plus the partition key when partitioned. No file extension — datasets are directories.

| Asset key | Partition | Dataset key |
|-----------|-----------|-------------|
| `["data", "orders"]` | *(none)* | `data/orders` |
| `["data", "orders"]` | `"2026-01"` | `data/orders/2026-01` |

### DAG-019: Dataset Mode via RemoteStoreIOManager

**Invariant:** `RemoteStoreIOManager(backend_type=..., serializer="parquet-dataset")` creates an IO manager that uses `ParquetDatasetStore` instead of the bytes-based Serializer protocol.

---

## Multi-Partition Loading

### DAG-020: load_input with Multiple Partition Keys

**Invariant:** When `load_input` receives an `InputContext` with multiple
partition keys (e.g. a downstream asset consuming a time-window aggregation
of an upstream partitioned asset), both `_RemoteStoreIOManagerImpl` and
`_DatasetIOManagerImpl` return `dict[str, Any]` mapping each partition key
to its deserialized object.

**Behaviour:**

1. If `context.has_asset_partitions` is true **and**
   `len(context.asset_partition_keys) > 1`:
   - For each key in `context.asset_partition_keys`, derive the storage
     path (or dataset key) using the asset key plus that partition key.
   - Read and deserialize each partition independently.
   - Return `{partition_key: deserialized_object, ...}`.
2. Otherwise (single or no partition): existing behaviour — return a single
   deserialized object.

**Applies to:** both the bytes-serializer IO manager (`_RemoteStoreIOManagerImpl`)
and the dataset IO manager (`_DatasetIOManagerImpl`).

**Raises:** The first missing partition raises immediately (no partial results).
The bytes-serializer IO manager raises `NotFound`; the dataset IO manager
raises `DatasetIncomplete` (from `ext.parquet`) when the `_SUCCESS` marker
is absent.

**Note:** `handle_output` remains single-partition per Dagster convention —
Dagster calls `handle_output` once per partition key. Multi-partition
aggregation only applies on the `load_input` side.

---

## v3: Compute Log Manager

`RemoteStoreComputeLogManager` is a Dagster
[`ComputeLogManager`](https://docs.dagster.io/api/dagster/internals) that
captures op/step `stdout` / `stderr` and persists it to any remote-store
backend. Unlike the `IOManager` (a resource), it is a Dagster *instance*
component wired in `dagster.yaml`, so Dagster instantiates it from a config
dict rather than from a live `Store`. It subclasses Dagster's
`TruncatingCloudStorageComputeLogManager` (capture-locally-then-upload
machinery, partial-upload polling, 50 MB upload truncation) and
`ConfigurableClass` (`dagster.yaml` plumbing). Design: RFC-0014.

### DAG-021: ConfigurableClass Plumbing

**Invariant:** `RemoteStoreComputeLogManager` subclasses
`TruncatingCloudStorageComputeLogManager` and `ConfigurableClass`. It is
referenced by string from `dagster.yaml` (`module: remote_store.ext.dagster`,
`class: RemoteStoreComputeLogManager`), so the import path is part of the
public contract. The `ConfigurableClass` hooks are:

- `config_type()` returns a config schema with fields:

  | Field | Type | Required | Default |
  |-------|------|----------|---------|
  | `backend_type` | `StringSource` | yes | — |
  | `backend_options` | `Permissive` dict | no | `{}` |
  | `root_path` | `StringSource` | no | `""` |
  | `local_dir` | `StringSource` | no | system temp dir |
  | `prefix` | `StringSource` | no | `"dagster"` |
  | `skip_empty_files` | `bool` | no | `false` |
  | `upload_interval` | `Noneable(int)` | no | `None` |

- `inst_data` (property) returns the `ConfigurableClassData` passed to the
  constructor, or `None` when constructed directly.
- `from_config_value(inst_data, config_value)` returns
  `cls(inst_data=inst_data, **config_value)`.

### DAG-022: Store Construction and Capability Validation

**Invariant:** the constructor builds its own `Store` from config via the
shared `_build_store(backend_type, backend_options, root_path)` helper (the
same helper used by `DagsterStoreResource` and `RemoteStoreIOManager`). After
construction it validates that the backend declares every capability the
manager needs: `READ`, `WRITE`, `DELETE`, `METADATA`, and `LIST`, queried via
`store.supports(...)`.

**Raises:** `ValueError` if `backend_type` is not registered, if the backend
constructor rejects `backend_options` (both from `_build_store`), or if any
required capability is missing — the message names the missing capabilities.
When a required capability is missing the Store is closed before the error is
raised.

### DAG-023: `local_manager` and `upload_interval` Properties

**Invariant:** `local_manager` returns a `LocalComputeLogManager` rooted at
`local_dir` (the configured directory, or the system temp directory when
unset). Capture is performed against this local manager before upload.
`upload_interval` returns the configured interval in seconds, or `None` when
unset or zero — `None` disables the partial-upload polling thread (no live
tailing).

### DAG-024: Remote Path Scheme

**Invariant:** the Store-relative path for one captured log stream is:

```
{prefix}/storage/{*log_key[:-1]}/{log_key[-1]}.{ext}[.partial]
```

where `ext` is `out` for `ComputeIOType.STDOUT` and `err` for
`ComputeIOType.STDERR` (Dagster's `IO_TYPE_EXTENSION`), and the `.partial`
suffix is appended for in-progress partial uploads. Empty path segments (e.g.
an empty `prefix`) are dropped. The Store's `root_path` is a separate
namespace prefix and is **not** embedded in this derivation — identical to the
path-derivation contract for the IOManager (DAG-005).

| `log_key` | `io_type` | `partial` | Path (default `prefix="dagster"`) |
|-----------|-----------|-----------|-----------------------------------|
| `["run1", "compute_logs", "step_a"]` | `STDOUT` | `False` | `dagster/storage/run1/compute_logs/step_a.out` |
| `["run1", "compute_logs", "step_a"]` | `STDERR` | `True` | `dagster/storage/run1/compute_logs/step_a.err.partial` |
| `["report"]` | `STDOUT` | `False` | `dagster/storage/report.out` |

### DAG-025: `_upload_file_obj`

**Invariant:** `_upload_file_obj(data, log_key, io_type, partial=False)` writes
the captured local log file to the Store at the DAG-024 path via
`store.write(path, data, overwrite=True)`, where `data` is the open binary
file object. When `skip_empty_files` is set, or the upload is `partial`, a
zero-byte local file is not uploaded.

### DAG-026: `download_from_cloud_storage`

**Invariant:** `download_from_cloud_storage(log_key, io_type, partial=False)`
reads the Store object at the DAG-024 path via `store.read(path)` and streams
it into the local staging file
`local_manager.get_captured_local_path(log_key, ext, partial=partial)`,
creating the parent directory if needed. This is how the Dagster webserver
serves logs for a completed run whose worker is gone.

### DAG-027: `cloud_storage_has_logs`

**Invariant:** `cloud_storage_has_logs(log_key, io_type, partial=False)`
returns `store.is_file(path)` for the DAG-024 path.

### DAG-028: `display_path_for_type` / `download_url_for_type`

**Invariant:** `display_path_for_type(log_key, io_type)` returns
`store.native_path(path)` for the DAG-024 path — a human-readable location for
the Dagster UI — once capture is complete, and `None` otherwise.
`download_url_for_type(log_key, io_type)` returns `None`: remote-store has no
URL-minting primitive, so the Dagster webserver streams log bytes through
itself via `get_log_data` (the same behaviour as `LocalComputeLogManager`).

### DAG-029: `delete_logs`

**Invariant:** `delete_logs` deletes both the local copies (via
`local_manager.delete_logs`) and the Store copies.

- Called with `log_key`: deletes the Store object for each `io_type`
  (`STDOUT`, `STDERR`) × each partial variant (`False`, `True`) via
  `store.delete(path, missing_ok=True)`.
- Called with `prefix`: deletes the Store folder
  `{prefix}/storage/{*prefix}` via
  `store.delete_folder(folder, recursive=True, missing_ok=True)`.

**Raises:** a `dagster._check` failure when neither `log_key` nor `prefix` is
passed — matching `LocalComputeLogManager.delete_logs`.

### DAG-030: `on_subscribe` / `on_unsubscribe`

**Invariant:** the manager holds a `PollingComputeLogSubscriptionManager`.
`on_subscribe` delegates to its `add_subscription`, `on_unsubscribe` to its
`remove_subscription`. This drives the Dagster UI's live-tail polling.

### DAG-031: `get_log_keys_for_log_key_prefix`

**Invariant:** `get_log_keys_for_log_key_prefix(log_key_prefix, io_type)`
lists the files under `{prefix}/storage/{*log_key_prefix}` via
`store.list_files` and returns one log key `[*log_key_prefix, filebase]` per
file whose extension matches `io_type` (`out` for `STDOUT`, `err` for
`STDERR`). Partial-upload files (`.partial`) are excluded. Returns an empty
list when the prefix contains no matching files. This enables the Dagster
UI's per-run log-file listing.

### DAG-032: Lifecycle

**Invariant:** the manager is a process-lifetime singleton. The `Store` is
built once in `__init__` and closed in `dispose()`, which also disposes the
`PollingComputeLogSubscriptionManager` and the `LocalComputeLogManager`.

### DAG-033: Credential Masking in `_build_store`

**Invariant:** `_build_store` wraps any value in `backend_options` whose key
name is in `_SENSITIVE_KEYS` (the authoritative set in `remote_store._config`,
not re-enumerated here per principle 4) in a `Secret` before passing it to the
backend constructor, so credentials are masked in `repr()` and tracebacks.
Wrapping is applied to a copy; the caller's `backend_options` mapping is not
mutated. Because `_build_store` is the shared construction helper, this masking
applies equally to `DagsterStoreResource` (DAG-012) and `RemoteStoreIOManager`
(DAG-015). It reuses the exact `_SENSITIVE_KEYS` set that
`RegistryConfig._from_dict` applies, so the two config paths mask the same keys.

**Scope note:** the `ConfigurableClass` `inst_data` config-YAML fragment is
owned and serialised by Dagster, not by `_build_store`; masking it is out of
scope. Credentials in `dagster.yaml` should be supplied through environment
indirection where the field type allows it.
