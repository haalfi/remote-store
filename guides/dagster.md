# Dagster Integration

How to use remote-store as the IO manager backend for Dagster pipelines.

## The idea

Teams already using remote-store should not duplicate their Store
configuration (credentials, retry policy, caching, observability) into
`dagster-aws` / `dagster-azure`. The `dagster_io_manager` adapter wraps
any existing `Store` as a Dagster `IOManager` with zero config duplication.

This also fills a gap for **SFTP backends** — Dagster has no native SFTP IO
manager, but remote-store covers that backend directly.

## Installation

```bash
pip install "remote-store[dagster]"

# For Parquet serializer support:
pip install "remote-store[dagster,arrow]"
```

## Quick start

```python
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

The `serializer` parameter controls how Python objects are converted to bytes
for storage and back.

| Name | `serializer=` | Extension | Dependency | Best for |
|------|---------------|-----------|------------|----------|
| Pickle | `"pickle"` (default) | `.pkl` | stdlib | Any picklable object |
| JSON | `"json"` | `.json` | stdlib | JSON-serializable data |
| Parquet | `"parquet"` | `.parquet` | `pyarrow>=14.0` | DataFrames (pandas, polars), Arrow Tables |

### Pickle (default)

```python
mgr = dagster_io_manager(store, serializer="pickle")
```

Universal — works with any picklable Python object. The default choice when
you don't need human-readable storage.

### JSON

```python
mgr = dagster_io_manager(store, serializer="json")
```

Human-readable, but limited to JSON-serializable types (dicts, lists,
strings, numbers, booleans, None).

### Parquet

```python
mgr = dagster_io_manager(store, serializer="parquet")
```

Efficient columnar storage for DataFrames. Requires PyArrow. Accepts pandas
DataFrames, polars DataFrames (via `.to_arrow()`), and Arrow Tables.
Deserializes to a PyArrow Table.

## Custom serializer

Any object matching the `Serializer` protocol can be used:

```python
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

Storage paths are derived automatically from Dagster asset keys and
partition keys:

| Asset key | Partition | Path |
|-----------|-----------|------|
| `["raw", "events"]` | *(none)* | `raw/events.pkl` |
| `["raw", "events"]` | `"2026-01"` | `raw/events/2026-01.pkl` |
| `["report"]` | *(none)* | `report.pkl` |

The Store's `root_path` acts as a namespace prefix — it is not embedded in
the path.

## Multi-partition loading

When a downstream asset consumes multiple partitions of an upstream asset
(e.g. a time-window aggregation), `load_input` automatically returns a
`dict[str, Any]` mapping each partition key to its deserialized object.

```python
--8<-- "examples/snippets/dagster_guide.py:multi-partition"
```

Single-partition inputs continue to return a single deserialized object
(not wrapped in a dict). If any partition is missing, `load_input` raises
`NotFound` immediately — no partial results are returned. This applies to
both the [bytes-serializer IO manager](api/extensions/dagster.md) and the
[dataset IO manager](api/extensions/dagster.md#remote_store.ext.dagster.dagster_dataset_io_manager).

Each partition is loaded individually. For high partition counts over remote
backends, consider pre-aggregating upstream or limiting the time-window span.

## Using with Registry

For teams using `Registry` for multi-backend configuration:

```python
from remote_store import Registry

@io_manager
def production_io_manager() -> IOManager:
    registry = Registry(config)
    store = registry.get_store("production")
    return dagster_io_manager(store, serializer="pickle")
```

## Lifecycle

The caller owns the Store. The IO manager does not close it. If the Store
was created inline, the caller is responsible for cleanup.

## Dagster-config-driven Store (v2)

Use v1 (`dagster_io_manager`) when you already have a Store. Use v2
(`RemoteStoreIOManager`) when Dagster should construct the Store from
config — for example in `Definitions` files where no Store exists
outside Dagster.

```python
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

`RemoteStoreIOManager` is a Dagster `ConfigurableIOManagerFactory` that
constructs and owns the Store lifecycle — setup and teardown happen
automatically when Dagster initialises and cleans up resources.

The `backend_type` field accepts `"local"`, `"s3"`, `"azure"`, `"sftp"`,
`"memory"`, `"sql-blob"`, and any other backend registered with the
remote-store factory. `backend_options` accepts the same keyword arguments
as the corresponding backend constructor.

For direct Store access in assets (outside the IO manager), use
`DagsterStoreResource` as a standalone resource.

### Dataset mode

For Parquet dataset I/O via `ParquetDatasetStore`, use
`dagster_dataset_io_manager(store)` (v1-style) or pass
`serializer="parquet-dataset"` on `RemoteStoreIOManager`:

```python
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

## See also

- [ext.dagster API reference](api/extensions/dagster.md) — full API docs
- [Dagster v2 resource example](examples/dagster-v2-resource.md) — config-driven
  Store construction with `RemoteStoreIOManager`
- [Medallion + Dagster Showcase](examples/medallion-dagster.md) — end-to-end
  Bronze/Silver/Gold pipeline demonstrating 4 extensions over live MeteoSwiss data
- [Data Lake Patterns](data-lake-patterns.md) — medallion architecture with
  `Store.child()` and PyArrow, complementary to Dagster orchestration
- [PyArrow Adapter](pyarrow-adapter.md) — use Store as a PyArrow filesystem
  for Parquet I/O
