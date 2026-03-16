# Data Lake Patterns

How to use remote-store as the storage plumbing layer for a multi-layer
Parquet data lake — and where to draw the line.

## The idea

remote-store provides a **unified, backend-agnostic I/O layer** that makes
data lake patterns portable across storage backends. A team can develop
locally against Memory or Local backends, test in CI without cloud
credentials, and deploy to S3 or Azure without changing application code.

The value proposition is not competing with Databricks, Spark, or any
query/compute engine. It is making **the storage layer underneath them
swappable and testable**. remote-store owns the I/O path; table formats
(Delta Lake, Iceberg) and query engines (Spark, DuckDB, Polars) sit on top
via the PyArrow adapter.

| Layer | Components |
|-------|------------|
| **Query / Compute** | Polars, DuckDB, Pandas, Spark, Databricks |
| **Table Format** (optional) | Delta Lake, PyIceberg, plain Parquet |
| **PyArrow FileSystem** | `pyarrow_fs(store)` |
| **remote-store** | `Store`, `child()`, `ext.batch`, `ext.transfer` |
| **Backend** | Local, Memory, S3, S3-PyArrow, SFTP, Azure |

## What this gets you

1. **Backend portability.** Develop against `MemoryBackend`, deploy to S3/Azure.
   Same code, zero cloud dependencies in dev.
2. **Layer isolation.** `store.child("bronze")`, `store.child("silver")`,
   `store.child("gold")` — each layer gets its own namespace without
   separate credentials, connections, or config.
3. **Streaming by default.** Reads and writes never fully materialize large
   files in memory. Critical for multi-GB Parquet partitions.
4. **Atomic writes.** `write_atomic()` uses rename-based semantics, reducing
   partial-write risk for individual files.
5. **Batch operations.** `batch_delete`, `batch_copy`, `batch_exists` for
   partition-scale workflows with error aggregation.
6. **Observability.** `ext.observe` hooks and OpenTelemetry bridge give
   visibility into every I/O operation without instrumenting application code.

## What this does not get you

Being honest about the boundary:

- **No table format protocol.** remote-store does not implement the Delta Lake
  transaction log, Iceberg manifest management, or any table format's commit
  protocol. Libraries like `deltalake` (delta-rs) or `pyiceberg` handle that —
  remote-store is the I/O layer they write through.
- **No query execution.** No SQL, no predicate pushdown, no shuffle.
  Polars, DuckDB, or Spark handle query planning and execution.
- **No catalog integration.** Unity Catalog, Hive Metastore, and Glue Catalog
  are metadata services remote-store does not interact with.
- **No Databricks-native credential passthrough.** Databricks clusters use
  instance profiles, workspace tokens, and Unity Catalog vended credentials.
  remote-store's `BackendConfig` takes explicit credentials. On Databricks,
  you would either pass credentials explicitly or use the native DBFS/ABFSS
  paths directly and skip the abstraction.
- **GIL-free fast path for native backends.** When the backend exposes a native
  PyArrow filesystem (e.g., `S3PyArrowBackend`), the adapter uses Tier 1
  fast-path reads that bypass Python I/O entirely — full C++ range requests
  with I/O coalescing and zero GIL overhead. Backends without native PyArrow
  support fall back to Tier 2 (full-file materialization) or Tier 3
  (PythonFile streaming).

The bridge metaphor works best with a clear boundary: **remote-store owns
portable, testable, observable storage I/O. Everything above the storage
layer — formats, queries, catalogs — belongs to purpose-built tools.**

## Bronze / Silver / Gold with `Store.child()`

The medallion architecture maps naturally to child stores:

```python
from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

config = RegistryConfig(
    backends={
        "lake": BackendConfig(
            type="s3",
            options={"bucket": "my-data-lake"},
        ),
    },
    stores={"lake": StoreProfile(backend="lake", root_path="v1")},
)

with Registry(config) as registry:
    lake = registry.get_store("lake")

    bronze = lake.child("bronze")   # raw ingestion
    silver = lake.child("silver")   # cleaned and typed
    gold = lake.child("gold")       # aggregated / business-ready
```

Each layer is a full `Store` — same API, same backend connection, independent
namespace. In dev/test, swap the backend to `MemoryBackend` or `LocalBackend`
with zero code changes.

## Writing Parquet via PyArrow

```python
import pyarrow as pa
import pyarrow.parquet as pq
from remote_store.ext.arrow import pyarrow_fs

# Bronze: ingest raw data as Parquet
bronze_fs = pyarrow_fs(bronze)
raw = pa.table({
    "timestamp": ["2026-03-01T10:00:00", "2026-03-01T10:01:00"],
    "sensor_id": ["s-001", "s-002"],
    "reading": [23.4, 19.8],
})
pq.write_table(raw, "readings/2026-03-01.parquet", filesystem=bronze_fs)
```

## Reading and transforming with Polars

```python
import polars as pl
import pyarrow.parquet as pq
from remote_store.ext.arrow import pyarrow_fs

# Read bronze partition via PyArrow, convert to Polars
bronze_fs = pyarrow_fs(bronze)
raw = pq.read_table("readings/2026-03-01.parquet", filesystem=bronze_fs)
df = pl.from_arrow(raw)

# Clean and type (bronze -> silver)
silver_df = (
    df.with_columns(
        pl.col("timestamp").str.to_datetime(),
        pl.col("reading").cast(pl.Float64),
    )
    .filter(pl.col("reading").is_not_null())
)

# Write to silver layer via PyArrow
silver_fs = pyarrow_fs(silver)
pq.write_table(silver_df.to_arrow(), "readings/2026-03-01.parquet", filesystem=silver_fs)
```

## Partitioned datasets with PyArrow

PyArrow's dataset API handles Hive-style partitioned layouts automatically:

```python
import pyarrow.dataset as ds

# Write partitioned by date
part = pa.table({
    "date": ["2026-03-01", "2026-03-01", "2026-03-02"],
    "sensor": ["s-001", "s-002", "s-001"],
    "value": [23.4, 19.8, 21.1],
})
ds.write_dataset(
    part,
    "sensors",
    filesystem=pyarrow_fs(silver),
    format="parquet",
    partitioning=ds.partitioning(pa.schema([("date", pa.string())])),
)

# Read with partition pruning
dataset = ds.dataset(
    "sensors",
    filesystem=pyarrow_fs(silver),
    format="parquet",
    partitioning="hive",
)
march_1 = dataset.to_table(filter=ds.field("date") == "2026-03-01")
```

## DuckDB integration

```python
import duckdb
import pyarrow.dataset as ds
from remote_store.ext.arrow import pyarrow_fs

silver_fs = pyarrow_fs(silver)
dataset = ds.dataset("readings", filesystem=silver_fs, format="parquet")

# DuckDB queries PyArrow datasets directly
result = duckdb.sql("""
    SELECT sensor_id, AVG(reading) as avg_reading
    FROM dataset
    GROUP BY sensor_id
""")
print(result.fetchdf())
```

## Delta Lake (via deltalake)

The `deltalake` library accepts PyArrow filesystems for storage:

```python
from deltalake import DeltaTable, write_deltalake

gold_fs = pyarrow_fs(gold)

# Write a Delta table
write_deltalake(
    "aggregates",
    silver_df.to_arrow(),
    filesystem=gold_fs,
)

# Read it back
dt = DeltaTable("aggregates", filesystem=gold_fs)
df = pl.from_arrow(dt.to_pyarrow_table())
```

Note: `deltalake` (delta-rs) owns the transaction log and commit protocol.
remote-store provides the I/O — it does not replace Delta's ACID guarantees.

## Batch operations across partitions

```python
from remote_store import batch_delete, batch_copy

# Archive old bronze partitions within the same store
old_files = [
    f.path for f in bronze.list_files("readings", recursive=True)
    if f.path < "readings/2026-01-01"
]
batch_copy(bronze, [(f, f"archive/{f}") for f in old_files])
batch_delete(bronze, old_files)
```

## Cross-backend transfer

Move data between backends without intermediate files:

```python
from remote_store import transfer

# Stream a partition from S3 bronze to Azure silver
transfer(
    s3_bronze, "readings/2026-03-01.parquet",
    azure_silver, "readings/2026-03-01.parquet",
    on_progress=lambda n: print(f"{n} bytes transferred"),
)
```

## Testing without cloud credentials

The entire pipeline can run against `MemoryBackend` in unit tests:

```python
import pytest
from remote_store import Store
from remote_store.backends import MemoryBackend
from remote_store.ext.arrow import pyarrow_fs


@pytest.fixture
def lake():
    """In-memory data lake for testing."""
    store = Store(backend=MemoryBackend())
    return {
        "bronze": store.child("bronze"),
        "silver": store.child("silver"),
        "gold": store.child("gold"),
    }


def test_bronze_to_silver(lake):
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Write raw data to bronze
    bronze_fs = pyarrow_fs(lake["bronze"])
    table = pa.table({"id": [1, 2], "value": [10.0, 20.0]})
    pq.write_table(table, "batch.parquet", filesystem=bronze_fs)

    # Transform and write to silver
    silver_fs = pyarrow_fs(lake["silver"])
    raw = pq.read_table("batch.parquet", filesystem=bronze_fs)
    # ... apply transformations ...
    pq.write_table(raw, "batch.parquet", filesystem=silver_fs)

    # Verify silver has the data
    result = pq.read_table("batch.parquet", filesystem=silver_fs)
    assert result.num_rows == 2
```

## Features that complement this pattern

These extensions work well with data lake workflows:

| Feature | What it does |
|---------|-------------|
| [Parallel batch operations](batch-operations.md) | Concurrent I/O for partition-scale deletes and copies (`concurrent=True`) |
| [Hive partition helpers](https://docs.remotestore.dev/stable/api/ext-partition/) | Build and parse `year=2026/month=03/` paths with `partition_path()` and `parse_partition()` |
| [PyArrow Tier 1 fast-path](pyarrow-adapter.md) | Zero-GIL C++ range requests for large Parquet workloads (S3-PyArrow) |
| [Streaming atomic writes](https://docs.remotestore.dev/stable/api/store/#remote_store.Store.open_atomic) | `open_atomic()` context manager for multi-GB Parquet exports |
| [Caching middleware](cache.md) | Reduces round-trips for metadata-heavy listing workflows |

## See also

- [Medallion + Dagster Showcase](examples/medallion-dagster.md) — end-to-end
  Bronze/Silver/Gold pipeline demonstrating 5 extensions over live MeteoSwiss data
- [Data Lake Medallion notebook](https://github.com/haalfi/remote-store/blob/master/examples/notebooks/04_data_lake_medallion.ipynb) — runnable end-to-end Bronze/Silver/Gold pipeline
- [Dagster Integration](dagster.md) — use any Store as a Dagster IO manager for orchestrated pipelines
- [PyArrow FileSystem Adapter](pyarrow-adapter.md) — adapter configuration and tiered read strategy
- [Transfer Operations](transfer-operations.md) — cross-store and local-path transfers
- [Batch Operations](batch-operations.md) — bulk delete, copy, exists
- [Concurrency](concurrency.md) — TOCTOU and atomicity considerations
