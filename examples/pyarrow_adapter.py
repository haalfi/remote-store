"""PyArrow FileSystem adapter -- use any Store as a pyarrow.fs.FileSystem.

Requires: pip install "remote-store[arrow]"

Demonstrates:
- Creating a PyArrow filesystem from a Store
- Writing and reading Parquet files through the adapter
- Dataset discovery
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


def main() -> None:
    # Create a Store with an in-memory backend
    backend = MemoryBackend()
    store = Store(backend=backend)

    # Wrap the Store as a PyArrow filesystem
    fs = pyarrow_fs(store)
    print(f"Filesystem type: {fs.type_name}")

    # Write a Parquet file
    table = pa.table({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})
    pq.write_table(table, "people.parquet", filesystem=fs)
    print("Wrote people.parquet")

    # Read it back
    result = pq.read_table("people.parquet", filesystem=fs)
    print(f"Read back {result.num_rows} rows:")
    print(result.to_pydict())

    # File info
    info = fs.get_file_info("people.parquet")
    print(f"\nFile info: type={info.type}, size={info.size} bytes")

    # Write multiple files for dataset discovery
    for i in range(3):
        part = pa.table({"value": [i * 10 + j for j in range(5)]})
        pq.write_table(part, f"dataset/part{i}.parquet", filesystem=fs)
    print("\nWrote 3 partitions to dataset/")

    # Discover and read all partitions
    import pyarrow.dataset as ds

    dataset = ds.dataset("dataset", filesystem=fs, format="parquet")
    all_data = dataset.to_table()
    print(f"Dataset: {all_data.num_rows} total rows from {len(dataset.files)} files")

    # Clean up — release PyArrow objects that reference the handler and force
    # garbage collection while the interpreter is still alive. Without this,
    # PyArrow's C++ destructors may deadlock during interpreter shutdown on
    # Linux (GIL re-acquisition from a C++ finalizer thread).
    del dataset, all_data, result, fs
    import gc

    gc.collect()

    store.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
