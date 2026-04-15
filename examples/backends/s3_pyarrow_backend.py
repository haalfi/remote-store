"""S3-PyArrow backend — High-throughput S3 via PyArrow's C++ filesystem. Drop-in swap from the S3 backend.

Drop-in alternative to the S3 backend. PyArrow handles the data path
(reads, writes, copies) while s3fs handles the control path (listing,
metadata, deletion). Only the ``type`` changes in your config.

Demonstrates:
- Configuring an S3-PyArrow backend via RegistryConfig
- Write, read, and chunked streaming read (64 KB chunks)
- Escape hatch: unwrap() to access PyArrow and s3fs filesystems

Prerequisites:
- pip install "remote-store[s3-pyarrow]"
- An S3-compatible service with a bucket already created

Environment variables:
    RS_S3_BUCKET    S3 bucket name (required)
    RS_S3_KEY       AWS access key ID
    RS_S3_SECRET    AWS secret access key
    RS_S3_ENDPOINT  Custom endpoint URL (e.g. http://localhost:9000 for MinIO)
    RS_S3_REGION    AWS region name

---
see_also:
  - label: S3-PyArrow Backend
    url: ../backends/s3-pyarrow.md
    note: backend guide
"""

from __future__ import annotations

import os
import sys

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

BUCKET = os.environ.get("RS_S3_BUCKET", "")

if not BUCKET:
    print(
        "Set RS_S3_BUCKET to run this example.\n"
        "Optional: RS_S3_KEY, RS_S3_SECRET, RS_S3_ENDPOINT, RS_S3_REGION\n\n"
        "Example with MinIO:\n"
        "  RS_S3_BUCKET=my-bucket RS_S3_KEY=minioadmin RS_S3_SECRET=minioadmin "
        "RS_S3_ENDPOINT=http://localhost:9000 python examples/s3_pyarrow_backend.py"
    )
    sys.exit(1)

if __name__ == "__main__":
    # --- Build options (identical to the S3 example) ---
    options: dict[str, object] = {"bucket": BUCKET}
    if val := os.environ.get("RS_S3_KEY"):
        options["key"] = val
    if val := os.environ.get("RS_S3_SECRET"):
        options["secret"] = val
    if val := os.environ.get("RS_S3_ENDPOINT"):
        options["endpoint_url"] = val
    if val := os.environ.get("RS_S3_REGION"):
        options["region_name"] = val

    # --- Only the type changes: "s3" -> "s3-pyarrow" ---
    config = RegistryConfig(
        backends={"s3pa": BackendConfig(type="s3-pyarrow", options=options)},
        stores={"data": StoreProfile(backend="s3pa", root_path="example/pyarrow")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")

        # --- Write ---
        store.write("report.csv", b"col1,col2\n1,2\n3,4\n")
        print("Wrote report.csv via PyArrow C++ data path.")

        # --- Read ---
        content = store.read_bytes("report.csv")
        print(f"\nreport.csv:\n{content.decode()}")

        # --- Chunked streaming read ---
        # Write a 1 MB payload and read it in 64 KB chunks.
        payload = b"X" * 1_000_000
        store.write("large.bin", payload, overwrite=True)

        reader = store.read("large.bin")
        total = 0
        chunks = 0
        while True:
            chunk = reader.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            chunks += 1
        print(f"Read large.bin: {total:,} bytes in {chunks} chunk(s).")

        # --- Cleanup registry files ---
        for f in store.list_files("", recursive=True):
            store.delete(str(f.path))
        print("\nCleaned up registry files.")

    # --- Escape hatch: unwrap() via direct construction ---
    # Construct the backend directly to access the underlying filesystems.
    # See ADR-0003 for background on the hybrid architecture.
    from remote_store.backends import S3PyArrowBackend

    backend = S3PyArrowBackend(
        bucket=BUCKET,
        key=os.environ.get("RS_S3_KEY"),
        secret=os.environ.get("RS_S3_SECRET"),
        endpoint_url=os.environ.get("RS_S3_ENDPOINT"),
        region_name=os.environ.get("RS_S3_REGION"),
    )

    try:
        import s3fs
        from pyarrow.fs import S3FileSystem as PyArrowS3

        # PyArrow filesystem (data path — reads, writes, copies)
        pa_fs = backend.unwrap(PyArrowS3)
        print(f"\nPyArrow filesystem: {type(pa_fs).__name__}")

        # s3fs filesystem (control path — listing, metadata, deletion)
        s3_fs = backend.unwrap(s3fs.S3FileSystem)
        print(f"s3fs filesystem:    {type(s3_fs).__name__}")
    finally:
        backend.close()

    print("\nDone!")
