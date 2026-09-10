# Dagster Integration

How to use remote-store as the IO manager and compute log backend for Dagster pipelines.

## The idea

Teams already using remote-store should not duplicate their Store configuration (credentials, retry policy, caching, observability) into `dagster-aws` / `dagster-azure`. The `dagster_io_manager` adapter wraps any existing `Store` as a Dagster `IOManager` with zero config duplication.

This also fills a gap for **SFTP backends** — Dagster has no native SFTP IO manager, but remote-store covers that backend directly.

## Installation

```
pip install "remote-store[dagster]"

# For Parquet serializer support:
pip install "remote-store[dagster,arrow]"
```

## Quick start

```
from dagster import Definitions, asset, IOManager, io_manager
from remote_store import Store
from remote_store.backends import LocalBackend
from remote_store.ext.dagster import dagster_io_manager


@io_manager
def my_io_manager() -> IOManager:
    store = Store(LocalBackend(root="/data/dagster"))
    return dagster_io_manager(store, serializer="pickle")


@asset
def raw_data() -> dict:
    return {"rows": [1, 2, 3]}


defs = Definitions(
    assets=[raw_data],
    resources={"io_manager": my_io_manager},
)
```

## Serializers

The `serializer` parameter controls how Python objects are converted to bytes for storage and back.

| Name    | `serializer=`        | Extension  | Dependency      | Best for                                  |
| ------- | -------------------- | ---------- | --------------- | ----------------------------------------- |
| Pickle  | `"pickle"` (default) | `.pkl`     | stdlib          | Any picklable object                      |
| JSON    | `"json"`             | `.json`    | stdlib          | JSON-serializable data                    |
| Parquet | `"parquet"`          | `.parquet` | `pyarrow>=14.0` | DataFrames (pandas, polars), Arrow Tables |

### Pickle (default)

```
mgr = dagster_io_manager(store, serializer="pickle")
```

Universal — works with any picklable Python object. The default choice when you don't need human-readable storage.

### JSON

```
mgr = dagster_io_manager(store, serializer="json")
```

Human-readable, but limited to JSON-serializable types (dicts, lists, strings, numbers, booleans, None).

### Parquet

```
mgr = dagster_io_manager(store, serializer="parquet")
```

Efficient columnar storage for DataFrames. Requires PyArrow. Accepts pandas DataFrames, polars DataFrames (via `.to_arrow()`), and Arrow Tables. Deserializes to a PyArrow Table.

## Custom serializer

Any object matching the `Serializer` protocol can be used:

```
from remote_store.ext.dagster import Serializer, dagster_io_manager


class MsgpackSerializer:
    extension = ".msgpack"

    def serialize(self, obj):
        import msgpack
        return msgpack.packb(obj)

    def deserialize(self, data):
        import msgpack
        return msgpack.unpackb(data)


mgr = dagster_io_manager(store, serializer=MsgpackSerializer())
```

## Path generation

Storage paths are derived automatically from Dagster asset keys and partition keys:

| Asset key           | Partition   | Path                     |
| ------------------- | ----------- | ------------------------ |
| `["raw", "events"]` | *(none)*    | `raw/events.pkl`         |
| `["raw", "events"]` | `"2026-01"` | `raw/events/2026-01.pkl` |
| `["report"]`        | *(none)*    | `report.pkl`             |

The Store's `root_path` acts as a namespace prefix — it is not embedded in the path.

## Multi-partition loading

When a downstream asset consumes multiple partitions of an upstream asset (e.g. a time-window aggregation), `load_input` automatically returns a `dict[str, Any]` mapping each partition key to its deserialized object.

```
from dagster import (  # noqa: F811
    AssetIn,
    Definitions,
    MonthlyPartitionsDefinition,
    TimeWindowPartitionMapping,
    asset,
    io_manager,
)

from remote_store import Store  # noqa: F811
from remote_store.backends import LocalBackend
from remote_store.ext.dagster import dagster_io_manager  # noqa: F811

monthly = MonthlyPartitionsDefinition(start_date="2026-01-01")

@io_manager
def my_io_manager() -> IOManager:
    store = Store(LocalBackend(root="/data/dagster"))
    return dagster_io_manager(store, serializer="json")

@asset(partitions_def=monthly)
def sales_monthly() -> dict[str, int]:
    """Upstream asset — one partition per month."""
    return {"revenue": 100}

@asset(
    partitions_def=monthly,
    ins={
        "sales_monthly": AssetIn(
            partition_mapping=TimeWindowPartitionMapping(start_offset=-2),
        ),
    },
)
def sales_rolling_3m(sales_monthly: dict[str, Any]) -> dict[str, Any]:
    """Downstream — receives last 3 months as dict[str, Any].

    ``sales_monthly`` is ``{"2026-01": {...}, "2026-02": {...}, "2026-03": {...}}``
    when the current partition is ``"2026-03"``.
    """
    total = sum(v["revenue"] for v in sales_monthly.values())
    return {"rolling_revenue": total}

defs = Definitions(
    assets=[sales_monthly, sales_rolling_3m],
    resources={"io_manager": my_io_manager},
)
```

Single-partition inputs continue to return a single deserialized object (not wrapped in a dict). If any partition is missing, `load_input` raises `NotFound` immediately — no partial results are returned. This applies to both the [bytes-serializer IO manager](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/index.md) and the [dataset IO manager](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/#remote_store.ext.dagster.dagster_dataset_io_manager).

Each partition is loaded individually. For high partition counts over remote backends, consider pre-aggregating upstream or limiting the time-window span.

## Using with Registry

For teams using `Registry` for multi-backend configuration:

```
from remote_store import Registry

@io_manager
def production_io_manager() -> IOManager:
    registry = Registry(config)
    store = registry.get_store("production")
    return dagster_io_manager(store, serializer="pickle")
```

## Lifecycle

The caller owns the Store. The IO manager does not close it. If the Store was created inline, the caller is responsible for cleanup.

## Dagster-config-driven Store (v2)

Use v1 (`dagster_io_manager`) when you already have a Store. Use v2 (`RemoteStoreIOManager`) when Dagster should construct the Store from config — for example in `Definitions` files where no Store exists outside Dagster.

```
from dagster import Definitions, asset
from remote_store.ext.dagster import RemoteStoreIOManager


@asset
def raw_data() -> dict:
    return {"rows": [1, 2, 3]}


defs = Definitions(
    assets=[raw_data],
    resources={
        "io_manager": RemoteStoreIOManager(
            backend_type="local",
            backend_options={"root": "/data/dagster"},
            serializer="pickle",
        )
    },
)
```

`RemoteStoreIOManager` is a Dagster `ConfigurableIOManagerFactory` that constructs and owns the Store lifecycle — setup and teardown happen automatically when Dagster initialises and cleans up resources.

The `backend_type` field accepts `"local"`, `"s3"`, `"azure"`, `"sftp"`, `"memory"`, `"sql-blob"`, and any other backend registered with the remote-store factory. `backend_options` accepts the same keyword arguments as the corresponding backend constructor.

For direct Store access in assets (outside the IO manager), use `DagsterStoreResource` as a standalone resource.

### Dataset mode

For Parquet dataset I/O via `ParquetDatasetStore`, use `dagster_dataset_io_manager(store)` (v1-style) or pass `serializer="parquet-dataset"` on `RemoteStoreIOManager`:

```
from remote_store.ext.dagster import RemoteStoreIOManager

resources = {
    "io_manager": RemoteStoreIOManager(
        backend_type="s3",
        backend_options={"bucket": "my-bucket", "prefix": "dagster/"},
        serializer="parquet-dataset",
    )
}
```

Requires `pip install "remote-store[dagster,arrow]"`.

## Compute logs

`RemoteStoreComputeLogManager` is the second half of the Dagster integration. Where the IO manager persists asset and op *return values*, the compute log manager persists the raw `stdout` / `stderr` a step emits while it runs — the text the Dagster UI shows under a run's stdout/stderr tabs.

A [`ComputeLogManager`](https://docs.dagster.io/api/dagster/internals) is not a resource. It is a Dagster *instance* component, so it is configured in `dagster.yaml` rather than wired into `Definitions`:

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

With this in place every run worker, the webserver, and the daemon stream compute logs to the same backend the rest of your Dagster storage already uses — no `dagster-aws` / `dagster-azure` needed. This is the standard fix for ephemeral run workers (Kubernetes, ECS): logs survive the pod or task being reclaimed.

### Config fields

| Field              | Type   | Default         | Purpose                                                                         |
| ------------------ | ------ | --------------- | ------------------------------------------------------------------------------- |
| `backend_type`     | string | *(required)*    | Registered backend type (`local`, `s3`, `sftp`, `azure`, `memory`, ...)         |
| `backend_options`  | dict   | `{}`            | Keyword arguments for the backend constructor                                   |
| `root_path`        | string | `""`            | Store root prefix for all log objects                                           |
| `local_dir`        | string | system temp dir | Local staging directory for capture                                             |
| `prefix`           | string | `"dagster"`     | Path prefix within the Store                                                    |
| `skip_empty_files` | bool   | `false`         | Skip uploading zero-byte log files                                              |
| `upload_interval`  | int    | `None`          | Seconds between partial uploads while a step runs; `None` disables live tailing |

Logs are captured to `local_dir` at the file-descriptor level — a descriptor cannot point at a remote object — then uploaded to the Store on step completion. Each stream is stored at `{prefix}/storage/<log-key>/<step>.out` (or `.err`); uploads are truncated at 50 MB, matching Dagster's own cloud compute log managers. Credential-named `backend_options` (`secret`, `password`, ...) are wrapped in `Secret` so they are masked in `repr()` and tracebacks.

The webserver streams log bytes through itself rather than minting a signed download URL, so the process running the Dagster UI must also be able to reach the backend.

## See also

- [ext.dagster API reference](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/index.md) — full API docs
- [Dagster v2 resource example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-v2-resource/index.md) — config-driven Store construction with `RemoteStoreIOManager`
- [Dagster compute log example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-compute-log-manager/index.md) — capturing op `stdout` / `stderr` to a Store with `RemoteStoreComputeLogManager`
- [Medallion + Dagster Showcase](https://docs.remotestore.dev/stable/tutorial/examples/medallion-dagster/index.md) — end-to-end Bronze/Silver/Gold pipeline demonstrating extensions over live MeteoSwiss data
- [Data Lake Patterns](https://docs.remotestore.dev/stable/guides/data-lake-patterns/index.md) — medallion architecture with `Store.child()` and PyArrow, complementary to Dagster orchestration
- [PyArrow Adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — use Store as a PyArrow filesystem for Parquet I/O
