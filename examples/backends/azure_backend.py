"""Azure backend — Connect to Azure Blob Storage or Azure Data Lake Storage Gen2.

Demonstrates:
- Configuring an Azure backend via RegistryConfig
- Two stores on one container (data + archive, showing isolation)
- File operations: write, read, list, copy, move, delete
- Streaming read (forward-only) and BytesIO hint for seekability
- Escape hatch: unwrap() to access FileSystemClient

Prerequisites:
- pip install "remote-store[azure]"
- An Azure Storage account with a container already created

Environment variables:
    RS_AZURE_CONTAINER  Container name (required)
    RS_AZURE_CONN       Connection string (simplest auth method)
    RS_AZURE_ACCOUNT    Storage account name
    RS_AZURE_KEY        Storage account key

---
see_also:
  - label: Azure Backend
    url: ../how-to/backends/azure.md
    note: backend guide
"""

from __future__ import annotations

import io
import os
import sys

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

CONTAINER = os.environ.get("RS_AZURE_CONTAINER", "")

if not CONTAINER:
    print(
        "Set RS_AZURE_CONTAINER to run this example.\n"
        "Auth (pick one): RS_AZURE_CONN, or RS_AZURE_ACCOUNT + RS_AZURE_KEY\n\n"
        "Example with Azurite:\n"
        '  RS_AZURE_CONTAINER=test RS_AZURE_CONN="DefaultEndpointsProtocol=http;'
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
        "/K1SZFPTOtr/KBHBeksoGMGw==;"
        'BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;" '
        "python examples/azure_backend.py"
    )
    sys.exit(1)

if __name__ == "__main__":
    # --- Build options dynamically from whichever env vars are set ---
    options: dict[str, object] = {"container": CONTAINER}
    if val := os.environ.get("RS_AZURE_CONN"):
        options["connection_string"] = val
    if val := os.environ.get("RS_AZURE_ACCOUNT"):
        options["account_name"] = val
    if val := os.environ.get("RS_AZURE_KEY"):
        options["account_key"] = val

    # --- Two stores on one container, different root_path ---
    config = RegistryConfig(
        backends={"azure": BackendConfig(type="azure", options=options)},
        stores={
            "data": StoreProfile(backend="azure", root_path="example/data"),
            "archive": StoreProfile(backend="azure", root_path="example/archive"),
        },
    )

    with Registry(config) as registry:
        data = registry.get_store("data")
        archive = registry.get_store("archive")

        # --- Write ---
        data.write("report.csv", b"revenue,profit\n100,20\n200,40\n")
        data.write("notes/todo.txt", b"Ship v1.0")
        archive.write("2024/summary.txt", b"Year-end summary")
        print("Wrote 3 files across 2 stores.")

        # --- Read ---
        content = data.read_bytes("report.csv")
        print(f"\nreport.csv:\n{content.decode()}")

        # --- Metadata ---
        info = data.get_file_info("report.csv")
        print(f"report.csv  size={info.size}  modified={info.modified_at}")

        # --- List files (recursive) ---
        print("\ndata/ (recursive):")
        for f in data.list_files("", recursive=True):
            print(f"  {f.path}  ({f.size} bytes)")

        # --- Folder info ---
        folder_info = data.get_folder_info("notes")
        print(f"\nnotes/ totals: {folder_info.file_count} files, {folder_info.total_size} bytes")

        # --- Copy (server-side) ---
        data.copy("report.csv", "report_backup.csv")
        print(f"\nCopied report.csv -> report_backup.csv (exists: {data.exists('report_backup.csv')})")

        # --- Move ---
        # On HNS-enabled accounts (ADLS Gen2), move is an atomic rename.
        # On non-HNS (plain Blob Storage / Azurite), it's copy + delete.
        data.move("report_backup.csv", "archive_report.csv")
        print(f"Moved to archive_report.csv (original exists: {data.exists('report_backup.csv')})")

        # --- Streaming read ---
        # Azure read() returns a forward-only stream (not seekable).
        # Data is fetched on demand, not loaded into memory upfront.
        reader = data.read("report.csv")
        print("\nStreaming read (line by line):")
        newline = b"\n"
        for line in reader:
            text = line.rstrip(newline).decode()
            if text:
                print(f"  {text}")

        # If you need seekability, use read_bytes() + BytesIO:
        seekable = io.BytesIO(data.read_bytes("report.csv"))
        seekable.seek(0)
        print(f"Seekable stream size: {len(seekable.getvalue())} bytes")

        # --- Cleanup ---
        for f in data.list_files("", recursive=True):
            data.delete(str(f.path))
        for f in archive.list_files("", recursive=True):
            archive.delete(str(f.path))
        print("\nCleaned up all example files.")

    # --- Escape hatch: unwrap() via direct construction ---
    # Construct the backend directly to access the underlying FileSystemClient.
    from remote_store.backends import AzureBackend

    backend = AzureBackend(
        container=CONTAINER,
        connection_string=os.environ.get("RS_AZURE_CONN"),
        account_name=os.environ.get("RS_AZURE_ACCOUNT"),
        account_key=os.environ.get("RS_AZURE_KEY"),
    )

    try:
        from azure.storage.filedatalake import FileSystemClient

        fs_client = backend.unwrap(FileSystemClient)
        print(f"\nFileSystemClient: {type(fs_client).__name__}")
    finally:
        backend.close()

    # --- Authentication methods (commented out) ---
    #
    # # 1. Account key
    # backend = AzureBackend(
    #     container="my-container",
    #     account_name="mystorageaccount",
    #     account_key="base64-key-here",
    # )
    #
    # # 2. SAS token
    # backend = AzureBackend(
    #     container="my-container",
    #     account_name="mystorageaccount",
    #     sas_token="sv=2023-11-03&...",
    # )
    #
    # # 3. Connection string
    # backend = AzureBackend(
    #     container="my-container",
    #     connection_string="DefaultEndpointsProtocol=https;AccountName=...;",
    # )
    #
    # # 4. DefaultAzureCredential (auto: env vars, managed identity, CLI)
    # backend = AzureBackend(
    #     container="my-container",
    #     account_name="mystorageaccount",
    #     # No key/token — falls back to DefaultAzureCredential
    # )

    print("\nDone!")
