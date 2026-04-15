"""PyArrow FileSystem adapter — Use any Store as a `pyarrow.fs.FileSystem` for Parquet, CSV, and dataset I/O.

Requires: pip install "remote-store[arrow]"

Demonstrates:
- Creating a PyArrow filesystem from a Store
- Writing and reading Parquet files through the adapter
- Dataset discovery

---
see_also:
  - label: PyArrow Adapter
    url: ../pyarrow-adapter.md
    note: PyArrow filesystem integration guide
"""

from __future__ import annotations

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as _exc:
    print("This example requires PyArrow: pip install 'remote-store[arrow]'")
    raise SystemExit(1) from _exc

from remote_store import Store
from remote_store.backends import MemoryBackend
from remote_store.ext.arrow import pyarrow_fs


def demo(store):
    """PyArrow filesystem: Parquet round-trip and dataset discovery. Returns results dict."""
    import pyarrow.dataset as ds

    results = {}

    fs = pyarrow_fs(store)
    results["type_name"] = fs.type_name
    print(f"Filesystem type: {fs.type_name}")

    # Write a Parquet file
    table = pa.table({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})
    pq.write_table(table, "people.parquet", filesystem=fs)
    print("Wrote people.parquet")

    # Read it back
    result = pq.read_table("people.parquet", filesystem=fs)
    results["people_rows"] = result.num_rows
    results["people_data"] = result.to_pydict()
    print(f"Read back {result.num_rows} rows:")
    print(result.to_pydict())

    # File info
    info = fs.get_file_info("people.parquet")
    results["file_size"] = info.size
    print(f"\nFile info: type={info.type}, size={info.size} bytes")

    # Write multiple files for dataset discovery
    for i in range(3):
        part = pa.table({"value": [i * 10 + j for j in range(5)]})
        pq.write_table(part, f"dataset/part{i}.parquet", filesystem=fs)
    print("\nWrote 3 partitions to dataset/")

    # Discover and read all partitions
    dataset = ds.dataset("dataset", filesystem=fs, format="parquet")
    all_data = dataset.to_table()
    results["dataset_rows"] = all_data.num_rows
    results["dataset_files"] = len(dataset.files)
    print(f"Dataset: {all_data.num_rows} total rows from {len(dataset.files)} files")

    return results


def main() -> None:
    backend = MemoryBackend()
    store = Store(backend=backend)
    demo(store)
    store.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
