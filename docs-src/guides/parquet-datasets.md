# Parquet Datasets

Write and read managed Parquet datasets with manifests, completion markers,
and multi-part file layouts using `ext.parquet.ParquetDatasetStore`.

## When to use this

Use `ParquetDatasetStore` when you need:

- **Reliable write completion** — `_SUCCESS` markers prevent consumers from
  reading partially-written datasets.
- **Manifest metadata** — row counts, schema hashes, run IDs, and custom
  metadata travel with the data.
- **Multi-part layouts** — split large tables into part files with
  `max_rows_per_file` to control per-file memory.
- **Consistent conventions** — every dataset follows the same file layout,
  eliminating ad-hoc manifest schemas.

For raw PyArrow filesystem access without manifests, use
[`ext.arrow`](pyarrow-adapter.md) directly.

## Background

The pattern behind `ParquetDatasetStore` — multi-file Parquet datasets with a
manifest and a completion marker — evolved from big-data execution frameworks,
not from a single formal specification:

- **Apache Hadoop / MapReduce** pioneered the `_SUCCESS` marker file convention.
  A job's output directory is considered complete only when the empty `_SUCCESS`
  file is present, preventing downstream consumers from reading partial results.
  ([Hadoop FileOutputCommitter](https://hadoop.apache.org/docs/stable/api/org/apache/hadoop/mapreduce/lib/output/FileOutputCommitter.html))

- **Apache Spark** adopted and popularized the `part-NNNNN.parquet` naming
  convention for partitioned writes. Spark's `DataFrameWriter` splits output
  into numbered part files and writes a `_SUCCESS` marker on commit.
  ([Spark SQL Guide — Data Sources](https://spark.apache.org/docs/latest/sql-data-sources.html))

- **Databricks DBIO** (Delta Lake's predecessor) extended the pattern with
  manifest files that describe dataset contents, enabling incremental reads
  and schema evolution without listing the directory.
  ([Delta Lake Protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md))

- **Apache Hive** uses the same `_SUCCESS` / part-file layout for its managed
  tables, with metastore-level schemas serving a similar role to manifests.

`ParquetDatasetStore` distills the common subset of these conventions into a
lightweight library-level abstraction: part files + JSON manifest + `_SUCCESS`
marker, without requiring a metastore, transaction log, or full table format.
Teams that outgrow this pattern can graduate to
[Delta Lake](https://delta.io/) or [Apache Iceberg](https://iceberg.apache.org/)
via the existing [`ext.arrow`](pyarrow-adapter.md) PyArrow filesystem adapter.

## Installation

`ParquetDatasetStore` requires PyArrow:

```bash
pip install "remote-store[arrow]"
```

## Quick start

```python
import pyarrow as pa
from remote_store import Store
from remote_store.backends import LocalBackend
from remote_store.ext.parquet import ParquetDatasetStore

store = Store(LocalBackend("/data/warehouse"))
pds = ParquetDatasetStore(store)

# Write
table = pa.table({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})
manifest = pds.write_dataset(table, "silver/customers")

# Read
customers = pds.read_dataset("silver/customers")

# Read with column projection
ids_only = pds.read_dataset("silver/customers", columns=["id"])
```

## Multi-part writes

For large tables, split into multiple Parquet files:

```python
pds = ParquetDatasetStore(store, max_rows_per_file=100_000)
manifest = pds.write_dataset(large_table, "silver/events")
print(f"Written as {len(manifest.parts)} parts")
```

This produces:

```
silver/events/
├── part-00000.parquet
├── part-00001.parquet
├── ...
├── manifest.json
└── _SUCCESS
```

## Overwrite semantics

By default, writing to an existing dataset raises `AlreadyExists`:

```python
from remote_store import AlreadyExists

pds.write_dataset(table, "silver/customers")
# Raises AlreadyExists:
pds.write_dataset(table, "silver/customers")
# Replaces the dataset:
pds.write_dataset(updated_table, "silver/customers", overwrite=True)
```

## Manifest inspection

Read the manifest without loading the full dataset:

```python
manifest = pds.read_manifest("silver/customers")
print(manifest.row_count)    # 3
print(manifest.schema_hash)  # deterministic hash of the Arrow schema
print(manifest.compression)  # "zstd"
print(manifest.run_id)       # pipeline run ID, if provided
```

## Pipeline integration

Embed pipeline metadata via `run_id` and `metadata`:

```python
manifest = pds.write_dataset(
    table,
    "silver/orders",
    run_id="dagster-abc123",
    metadata={"source": "meteoswiss", "version": "3"},
)
```

## Scoping with `Store.child()`

Combine with `Store.child()` for layer-scoped stores:

```python
silver = Store(LocalBackend("/data/warehouse")).child("silver")
pds = ParquetDatasetStore(silver)
pds.write_dataset(table, "customers")  # writes to /data/warehouse/silver/customers/
```

## Error handling

```python
from remote_store.ext.parquet import DatasetIncomplete, ManifestCorrupted

try:
    table = pds.read_dataset("silver/orders")
except DatasetIncomplete:
    print("Dataset write did not complete -- missing _SUCCESS or parts")
except ManifestCorrupted as e:
    print(f"Bad manifest: {e.reason}")
```

## Capability requirements

| Operation | Required capabilities |
|-----------|---------------------|
| `write_dataset` | `ATOMIC_WRITE` (always), `DELETE` (if `overwrite=True`) |
| `read_dataset` | `READ` |
| `delete_dataset` | `DELETE` |
| `dataset_exists` | `READ` |

## See also

- [ext.parquet API reference](../reference/api/extensions/parquet.md) — full class and method docs
- [Parquet Dataset example](../tutorial/examples/parquet-dataset.md) — runnable example
- [PyArrow Adapter](pyarrow-adapter.md) — lower-level Store-as-FileSystem bridge
- [Data Lake Patterns](data-lake-patterns.md) — medallion architecture patterns
