"""S3 backend — connect to Amazon S3 or any S3-compatible service.

Demonstrates:
- Configuring an S3 backend via RegistryConfig
- Two stores sharing one bucket (different root_path)
- File operations: write, read, list, copy, move, delete
- S3 virtual-folder semantics (prefix-based, vanish when empty)
- Streaming reads

Prerequisites:
- pip install "remote-store[s3]"
- An S3-compatible service with a bucket already created

Environment variables:
    RS_S3_BUCKET    S3 bucket name (required)
    RS_S3_KEY       AWS access key ID
    RS_S3_SECRET    AWS secret access key
    RS_S3_ENDPOINT  Custom endpoint URL (e.g. http://localhost:9000 for MinIO)
    RS_S3_REGION    AWS region name
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
        "RS_S3_ENDPOINT=http://localhost:9000 python examples/s3_backend.py"
    )
    sys.exit(1)

if __name__ == "__main__":
    # --- Build options from environment ---
    options: dict[str, object] = {"bucket": BUCKET}
    if val := os.environ.get("RS_S3_KEY"):
        options["key"] = val
    if val := os.environ.get("RS_S3_SECRET"):
        options["secret"] = val
    if val := os.environ.get("RS_S3_ENDPOINT"):
        options["endpoint_url"] = val
    if val := os.environ.get("RS_S3_REGION"):
        options["region_name"] = val

    # --- Two stores on one bucket, different root_path ---
    config = RegistryConfig(
        backends={"s3": BackendConfig(type="s3", options=options)},
        stores={
            "data": StoreProfile(backend="s3", root_path="example/data"),
            "logs": StoreProfile(backend="s3", root_path="example/logs"),
        },
    )

    with Registry(config) as registry:
        data = registry.get_store("data")
        logs = registry.get_store("logs")

        # --- Write ---
        data.write("report.csv", b"revenue,profit\n100,20\n200,40\n")
        data.write("notes/todo.txt", b"Ship v1.0")
        logs.write("app.log", b"[INFO] started\n[WARN] disk 80%\n")
        print("Wrote 3 files across 2 stores.")

        # --- Read ---
        content = data.read_bytes("report.csv")
        print(f"\nreport.csv:\n{content.decode()}")

        # --- Metadata ---
        info = data.get_file_info("report.csv")
        print(f"report.csv  size={info.size}  modified={info.modified_at}")

        # --- List files (shallow) ---
        print("\ndata/ (shallow):")
        for f in data.list_files(""):
            print(f"  {f.name}  ({f.size} bytes)")

        # --- List files (recursive) ---
        print("\ndata/ (recursive):")
        for f in data.list_files("", recursive=True):
            print(f"  {f.path}  ({f.size} bytes)")

        # --- List folders ---
        print("\nFolders in data/:")
        for folder in data.list_folders(""):
            print(f"  {folder}/")

        # --- Folder info ---
        folder_info = data.get_folder_info("notes")
        print(f"\nnotes/ totals: {folder_info.file_count} files, {folder_info.total_size} bytes")

        # --- Copy ---
        data.copy("report.csv", "report_backup.csv")
        print(f"\nCopied report.csv -> report_backup.csv (exists: {data.exists('report_backup.csv')})")

        # --- Move ---
        data.move("report_backup.csv", "archive/report_old.csv")
        print(f"Moved to archive/report_old.csv (original exists: {data.exists('report_backup.csv')})")

        # --- Streaming read ---
        reader = data.read("report.csv")
        print("\nStreaming read (line by line):")
        newline = b"\n"
        for line in reader:
            text = line.rstrip(newline).decode()
            if text:
                print(f"  {text}")

        # --- Cleanup ---
        # S3 folders are virtual (prefix-based). Deleting all files under a
        # prefix makes the "folder" vanish automatically.
        for f in data.list_files("", recursive=True):
            data.delete(str(f.path))
        for f in logs.list_files("", recursive=True):
            logs.delete(str(f.path))
        print("\nCleaned up all example files.")

    print("\nDone!")
