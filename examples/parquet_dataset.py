"""Parquet Dataset Store -- managed Parquet datasets with manifests and completion markers.

Requires: pip install "remote-store[arrow]"

Demonstrates:
- Writing a PyArrow table as a managed Parquet dataset
- Reading a dataset back with column projection
- Multi-part writes with max_rows_per_file
- Inspecting dataset manifests
- Overwrite semantics
"""

from __future__ import annotations

try:
    import pyarrow as pa

    from remote_store.ext.parquet import ParquetDatasetStore
except ImportError as _exc:
    print("This example requires PyArrow: pip install 'remote-store[arrow]'")
    raise SystemExit(1) from _exc

from remote_store import Store
from remote_store.backends import MemoryBackend


def demo(store: Store) -> dict:
    """ParquetDatasetStore: managed Parquet datasets. Returns results dict."""
    results: dict = {}

    # -- Basic write/read roundtrip --
    pds = ParquetDatasetStore(store)
    table = pa.table({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "score": [95.0, 87.5, 92.0]})

    manifest = pds.write_dataset(table, "silver/students")
    print(f"Wrote dataset: {manifest.dataset_key}")
    print(f"  Parts: {manifest.parts}")
    print(f"  Rows:  {manifest.row_count}")
    print(f"  Hash:  {manifest.schema_hash}")
    results["single_parts"] = manifest.parts
    results["single_rows"] = manifest.row_count

    # Read it back
    result = pds.read_dataset("silver/students")
    print(f"Read back {result.num_rows} rows")
    results["read_rows"] = result.num_rows

    # -- Column projection --
    subset = pds.read_dataset("silver/students", columns=["id", "name"])
    print(f"Projected columns: {subset.column_names}")
    results["projected_columns"] = subset.column_names

    # -- Multi-part write --
    pds_multi = ParquetDatasetStore(store, max_rows_per_file=2)
    manifest_multi = pds_multi.write_dataset(table, "silver/students-multi")
    print(f"Multi-part: {len(manifest_multi.parts)} files")
    results["multi_parts"] = len(manifest_multi.parts)

    # -- Overwrite --
    updated = pa.table({"id": [4, 5], "name": ["Dave", "Eve"], "score": [88.0, 91.0]})
    manifest_new = pds.write_dataset(updated, "silver/students", overwrite=True)
    print(f"Overwritten: {manifest_new.row_count} rows")
    results["overwrite_rows"] = manifest_new.row_count

    # -- Manifest inspection --
    m = pds.read_manifest("silver/students")
    print(f"Manifest compression: {m.compression}")
    results["compression"] = m.compression

    # -- Existence check --
    print(f"Dataset exists: {pds.dataset_exists('silver/students')}")
    print(f"Missing exists: {pds.dataset_exists('silver/nonexistent')}")
    results["exists"] = pds.dataset_exists("silver/students")
    results["missing"] = pds.dataset_exists("silver/nonexistent")

    return results


if __name__ == "__main__":
    demo(Store(MemoryBackend()))
