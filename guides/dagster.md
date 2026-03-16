# Dagster Integration

How to use remote-store as the IO manager backend for Dagster pipelines.

## The idea

Teams already using remote-store should not duplicate their Store
configuration (credentials, retry policy, caching, observability) into
`dagster-aws` / `dagster-azure`. The `remote_store_io_manager` adapter wraps
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
from remote_store.ext.dagster import remote_store_io_manager


@io_manager
def my_io_manager() -> IOManager:
    store = Store(LocalBackend(root="/data/dagster"))
    return remote_store_io_manager(store, serializer="pickle")


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
| Parquet | `"parquet"` | `.parquet` | `pyarrow>=14.0` | DataFrames (pandas, polars) |

### Pickle (default)

```python
mgr = remote_store_io_manager(store, serializer="pickle")
```

Universal — works with any picklable Python object. The default choice when
you don't need human-readable storage.

### JSON

```python
mgr = remote_store_io_manager(store, serializer="json")
```

Human-readable, but limited to JSON-serializable types (dicts, lists,
strings, numbers, booleans, None).

### Parquet

```python
mgr = remote_store_io_manager(store, serializer="parquet")
```

Efficient columnar storage for DataFrames. Requires PyArrow. Accepts pandas
DataFrames, polars DataFrames (via `.to_arrow()`), and Arrow Tables.
Deserializes to pandas DataFrame.

## Custom serializer

Any object matching the `Serializer` protocol can be used:

```python
from remote_store.ext.dagster import Serializer, remote_store_io_manager


class MsgpackSerializer:
    extension = ".msgpack"

    def serialize(self, obj):
        import msgpack
        return msgpack.packb(obj)

    def deserialize(self, data):
        import msgpack
        return msgpack.unpackb(data)


mgr = remote_store_io_manager(store, serializer=MsgpackSerializer())
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

## Using with Registry

For teams using `Registry` for multi-backend configuration:

```python
from remote_store import Registry

@io_manager
def production_io_manager() -> IOManager:
    registry = Registry(config)
    store = registry.get_store("production")
    return remote_store_io_manager(store, serializer="pickle")
```

## Lifecycle

The caller owns the Store. The IO manager does not close it. If the Store
was created inline, the caller is responsible for cleanup.

## See also

- [Medallion + Dagster Showcase](examples/medallion-dagster.md) — end-to-end
  Bronze/Silver/Gold pipeline demonstrating 5 extensions over live MeteoSwiss data
- [Data Lake Patterns](data-lake-patterns.md) — medallion architecture with
  `Store.child()` and PyArrow, complementary to Dagster orchestration
- [PyArrow Adapter](pyarrow-adapter.md) — use Store as a PyArrow filesystem
  for Parquet I/O

## What's next

v2 (deferred) will add `DagsterStoreResource` — a Dagster `ConfigurableResource`
that constructs a Store from Dagster config fields. This targets Dagster-first
users who don't already have a Store.
