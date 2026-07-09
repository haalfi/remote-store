# ext.dagster

## dagster

Dagster IO Manager adapter — wraps any Store as a Dagster [IOManager](https://docs.dagster.io/_apidocs/io-managers#dagster.IOManager).

Lets teams already using remote-store reuse their Store configuration (credentials, retry policy, caching, observability) inside Dagster pipelines without duplicating config into dagster-aws / dagster-azure.

Install with `pip install "remote-store[dagster]"`.

Example

```
from remote_store.ext.dagster import dagster_io_manager

io_mgr = dagster_io_manager(store, serializer="pickle")
```

### Serializer

Bases: `Protocol`

Protocol for pluggable serializers.

Implement this to provide a custom serializer to `dagster_io_manager(store, serializer=my_serializer)`.

#### serialize

```
serialize(obj: Any) -> bytes
```

Convert a Python object to bytes.

#### deserialize

```
deserialize(data: bytes) -> Any
```

Convert bytes back to a Python object.

### PickleSerializer

Pickle-based serializer. Universal; opaque format.

#### serialize

```
serialize(obj: Any) -> bytes
```

Serialize using pickle.

#### deserialize

```
deserialize(data: bytes) -> Any
```

Deserialize using pickle.

### JsonSerializer

JSON serializer. JSON-serializable objects only.

#### serialize

```
serialize(obj: Any) -> bytes
```

Serialize to JSON bytes.

#### deserialize

```
deserialize(data: bytes) -> Any
```

Deserialize from JSON bytes.

### ParquetSerializer

```
ParquetSerializer()
```

Parquet serializer via PyArrow. DataFrames and Arrow Tables.

#### serialize

```
serialize(obj: Any) -> bytes
```

Serialize a DataFrame to Parquet bytes.

#### deserialize

```
deserialize(data: bytes) -> Table
```

Deserialize Parquet bytes to a PyArrow Table.

### DagsterStoreResource

Bases: `ConfigurableResource`

Dagster resource that constructs a Store from config fields.

Unlike stateless utility extensions, this class owns Store lifecycle because it is a Dagster Resource with `setup_for_execution` / `teardown_after_execution` hooks.

Attributes:

- **`backend_type`** (`str`) – Backend type string (e.g. "local", "s3", "memory"). Must be registered in the backend factory registry.
- **`backend_options`** (`dict[str, Any]`) – Keyword arguments passed to the backend constructor.
- **`root_path`** (`str`) – Optional root path for the Store.

#### setup_for_execution

```
setup_for_execution(context: InitResourceContext) -> None
```

Instantiate and cache the Store (called by Dagster before execution).

Raises:

- `ValueError` – If backend_type is not registered, or if the backend constructor rejects the supplied backend_options.

#### teardown_after_execution

```
teardown_after_execution(
    context: InitResourceContext,
) -> None
```

Close the Store and release resources (called by Dagster after execution).

#### get_store

```
get_store() -> Store
```

Return the underlying Store instance.

Returns:

- `Store` – The Store constructed during setup_for_execution.

Raises:

- `RuntimeError` – If called before setup_for_execution has run.

### RemoteStoreIOManager

Bases: `ConfigurableIOManagerFactory`

IO manager factory that constructs a Store from config fields.

Embeds backend configuration directly so the IO manager owns the full Store lifecycle (setup and teardown). For direct Store access in assets, use `DagsterStoreResource` as a separate resource.

Attributes:

- **`backend_type`** (`str`) – Backend type string (e.g. "local", "s3", "memory").
- **`backend_options`** (`dict[str, Any]`) – Keyword arguments passed to the backend constructor.
- **`root_path`** (`str`) – Optional root path for the Store.
- **`serializer`** (`str`) – Serializer name. Use "parquet-dataset" for multi-file Parquet dataset output via ParquetDatasetStore.

#### setup_for_execution

```
setup_for_execution(context: InitResourceContext) -> None
```

Build and cache the Store before execution.

#### teardown_after_execution

```
teardown_after_execution(
    context: InitResourceContext,
) -> None
```

Close the Store and release resources.

#### create_io_manager

```
create_io_manager(context: Any) -> IOManager
```

Construct the IOManager for the given execution context.

Returns:

- `IOManager` – A \_DatasetIOManagerImpl when serializer="parquet-dataset",
- `IOManager` – otherwise a \_RemoteStoreIOManagerImpl with the resolved serializer.

Raises:

- `RuntimeError` – If called before setup_for_execution.
- `ValueError` – If serializer is an unrecognized string.

### RemoteStoreComputeLogManager

```
RemoteStoreComputeLogManager(
    backend_type: str,
    backend_options: dict[str, Any] | None = None,
    root_path: str = "",
    local_dir: str | None = None,
    prefix: str = "dagster",
    skip_empty_files: bool = False,
    upload_interval: int | None = None,
    inst_data: ConfigurableClassData | None = None,
)
```

Bases: `TruncatingCloudStorageComputeLogManager`, `ConfigurableClass`

Captures op/step `stdout` / `stderr` to any remote-store backend.

A Dagster `ComputeLogManager` wired into `dagster.yaml` as an instance component. Logs are captured to a local staging directory at the file-descriptor level, then uploaded to a `Store` the manager builds itself from `backend_type` + `backend_options`. When `upload_interval` is set, partial uploads also run periodically while a step executes so the Dagster UI can tail them. Subclasses Dagster's `TruncatingCloudStorageComputeLogManager` (capture-then-upload machinery, 50 MB upload truncation) and `ConfigurableClass` (`dagster.yaml` plumbing).

Configure it in `dagster.yaml`:

```
compute_logs:
  module: remote_store.ext.dagster
  class: RemoteStoreComputeLogManager
  config:
    backend_type: s3
    backend_options:
      bucket: my-logs-bucket
    root_path: dagster/compute-logs
    upload_interval: 30
```

Attributes:

- **`backend_type`** – Registered backend type ("local", "s3", "sftp", "azure", "memory", ...).
- **`backend_options`** – Keyword arguments for the backend constructor.
- **`root_path`** – Store root prefix applied to every log object.
- **`local_dir`** – Local staging directory for capture. Defaults to the system temp directory.
- **`prefix`** – Path prefix within the Store. Defaults to "dagster".
- **`skip_empty_files`** – Skip uploading zero-byte log files.
- **`upload_interval`** (`int | None`) – Seconds between partial uploads while a step runs; None (default) disables live tailing.

Build the Store, validate its capabilities, and wire the local manager.

Raises:

- `ValueError` – If backend_type is not registered, if the backend rejects backend_options, or if the backend is missing a capability the manager requires (READ, WRITE, DELETE, METADATA, LIST).

#### inst_data

```
inst_data: ConfigurableClassData | None
```

The `ConfigurableClassData` this manager was rehydrated from, if any.

#### local_manager

```
local_manager: LocalComputeLogManager
```

The `LocalComputeLogManager` that stages captures before upload.

#### upload_interval

```
upload_interval: int | None
```

Seconds between partial uploads, or `None` when live tailing is off.

#### config_type

```
config_type() -> dict[str, Any]
```

The `dagster.yaml` config schema for this manager.

#### from_config_value

```
from_config_value(
    inst_data: ConfigurableClassData | None,
    config_value: Mapping[str, Any],
) -> RemoteStoreComputeLogManager
```

Construct a manager from a validated `dagster.yaml` config value.

#### download_from_cloud_storage

```
download_from_cloud_storage(
    log_key: Sequence[str],
    io_type: ComputeIOType,
    partial: bool = False,
) -> None
```

Stream a log object from the Store into the local staging file.

#### cloud_storage_has_logs

```
cloud_storage_has_logs(
    log_key: Sequence[str],
    io_type: ComputeIOType,
    partial: bool = False,
) -> bool
```

Return whether the Store holds a log object for this key.

#### display_path_for_type

```
display_path_for_type(
    log_key: Sequence[str], io_type: ComputeIOType
) -> str | None
```

A human-readable Store location for the Dagster UI, once capture is done.

#### download_url_for_type

```
download_url_for_type(
    log_key: Sequence[str], io_type: ComputeIOType
) -> str | None
```

No signed-URL primitive in v1 — the webserver streams logs itself.

#### delete_logs

```
delete_logs(
    log_key: Sequence[str] | None = None,
    prefix: Sequence[str] | None = None,
) -> None
```

Delete captured logs by `log_key` or by `prefix`, local and remote.

Raises:

- `CheckError` – If neither log_key nor prefix is given.

#### get_log_keys_for_log_key_prefix

```
get_log_keys_for_log_key_prefix(
    log_key_prefix: Sequence[str], io_type: ComputeIOType
) -> Sequence[Sequence[str]]
```

Enumerate the stored log keys under a log-key prefix.

#### on_subscribe

```
on_subscribe(subscription: CapturedLogSubscription) -> None
```

Register a UI live-tail subscription with the polling manager.

#### on_unsubscribe

```
on_unsubscribe(
    subscription: CapturedLogSubscription,
) -> None
```

Deregister a UI live-tail subscription from the polling manager.

#### dispose

```
dispose() -> None
```

Dispose the subscription and local managers and close the Store.

### dagster_io_manager

```
dagster_io_manager(
    store: Store, *, serializer: str | Serializer = "pickle"
) -> IOManager
```

Wrap a Store as a Dagster IOManager.

Parameters:

- **`store`** (`Store`) – An existing Store instance. The caller owns its lifecycle — the IO manager does not close the Store.
- **`serializer`** (`str | Serializer`, default: `'pickle'` ) – "pickle" (default), "json", "parquet", or a custom object satisfying the Serializer protocol.

Returns:

- `IOManager` – A Dagster IOManager backed by the given Store.

Raises:

- `ValueError` – If serializer is an unrecognized string.

### dagster_dataset_io_manager

```
dagster_dataset_io_manager(store: Store) -> IOManager
```

Wrap a Store as a Dagster IOManager using ParquetDatasetStore.

Unlike `dagster_io_manager` which serializes objects to single files, this manager writes Parquet datasets (multi-file with manifest) via `ParquetDatasetStore`.

Parameters:

- **`store`** (`Store`) – An existing Store instance. The caller owns its lifecycle.

Returns:

- `IOManager` – A Dagster IOManager backed by ParquetDatasetStore.

## See also

- [Dagster](https://docs.remotestore.dev/stable/guides/dagster/index.md) — guide to the Dagster integration (IO manager and compute log manager)
- [Dagster IO Manager example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-io-manager/index.md) — basic Dagster usage (v1)
- [Dagster v2 resource example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-v2-resource/index.md) — config-driven Store with RemoteStoreIOManager
- [Dagster compute log example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-compute-log-manager/index.md) — capturing op stdout/stderr with RemoteStoreComputeLogManager
- [Medallion Dagster example](https://docs.remotestore.dev/stable/tutorial/examples/medallion-dagster/index.md) — multi-layer data pipeline showcase
