"""SQL Blob Backend — SQLite key-value store — zero-infrastructure persistent file storage.

Demonstrates using SQLBlobBackend with SQLite as a zero-infrastructure
persistent file store. All data lives in a single .db file.

Run:
    python examples/backends/sql_blob_backend.py

---
see_also:
  - label: SQL Blob Backend
    url: ../../guides/backends/sql-blob.md
    note: backend guide
"""

from __future__ import annotations

from remote_store import Store
from remote_store.backends import SQLBlobBackend


def main() -> None:
    # Use an in-memory SQLite database (no file on disk)
    backend = SQLBlobBackend(url="sqlite:///:memory:")
    store = Store(backend=backend)

    # --- Write files ---
    store.write("reports/q1.csv", b"date,revenue\n2024-01-01,1000\n")
    store.write("reports/q2.csv", b"date,revenue\n2024-04-01,1500\n")
    store.write("models/v1.pkl", b"\x80\x05model-data-here")
    print("Wrote 3 files")

    # --- Read back ---
    data = store.read_bytes("reports/q1.csv")
    print(f"Q1 report: {data.decode()[:30]}...")

    # --- List files ---
    print("\nAll files (recursive):")
    for info in store.list_files("", recursive=True):
        print(f"  {info.path} ({info.size} bytes)")

    # --- List folders ---
    print("\nTop-level folders:")
    for folder in store.list_folders(""):
        print(f"  {folder.name}/")

    # --- Metadata ---
    info = store.get_file_info("models/v1.pkl")
    print(f"\nModel info: size={info.size}, modified={info.modified_at}")

    folder_info = store.get_folder_info("reports")
    print(f"Reports folder: {folder_info.file_count} files, {folder_info.total_size} bytes")

    # --- Move & copy ---
    store.copy("reports/q1.csv", "archive/q1.csv")
    store.move("reports/q2.csv", "archive/q2.csv")
    print("\nAfter move+copy, archive contents:")
    for info in store.list_files("archive"):
        print(f"  {info.name}")

    # --- Glob ---
    print("\nGlob '*.csv':")
    for info in store.glob("*.csv"):
        print(f"  {info.path}")

    # --- Delete ---
    store.delete("models/v1.pkl")
    print(f"\nAfter delete, models/v1.pkl exists: {store.exists('models/v1.pkl')}")

    # --- Health check ---
    backend.check_health()
    print("Health check passed")

    # --- Cleanup ---
    backend.close()
    print("Done!")


if __name__ == "__main__":
    main()
