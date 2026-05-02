"""Transfer operations — Upload, download, and cross-store transfer with progress tracking.

Demonstrates:
- upload: stream a local file to a Store
- download: stream a Store file to a local path
- transfer: stream between two Stores
- on_progress: tracking bytes transferred
- overwrite semantics for all three functions

---
see_also:
  - label: Transfer Operations
    url: ../../guides/transfer-operations.md
    note: upload, download, and cross-store transfer guide
"""

from __future__ import annotations

import os
import tempfile

from remote_store import (
    BackendConfig,
    Registry,
    RegistryConfig,
    StoreProfile,
    download,
    transfer,
    upload,
)


def demo(primary, archive, tmp_dir):
    """Upload, download, transfer between stores. Returns results dict."""
    results = {}

    # -- Create a local file to upload --
    local_file = os.path.join(tmp_dir, "hello.txt")
    with open(local_file, "wb") as f:
        f.write(b"Hello from local filesystem!")
    print(f"Created local file: {local_file}")

    # --- upload ---
    upload(primary, local_file, "hello.txt")
    results["uploaded_content"] = primary.read_bytes("hello.txt")
    print(f"\nUploaded to primary: {results['uploaded_content']}")

    # --- upload with progress ---
    large_file = os.path.join(tmp_dir, "large.bin")
    with open(large_file, "wb") as f:
        f.write(b"x" * 100_000)

    bytes_sent: list[int] = []
    upload(primary, large_file, "large.bin", on_progress=bytes_sent.append)
    results["upload_bytes"] = sum(bytes_sent)
    results["upload_chunks"] = len(bytes_sent)
    print(f"Uploaded large.bin: {results['upload_bytes']} bytes in {results['upload_chunks']} chunk(s)")

    # --- download ---
    download_path = os.path.join(tmp_dir, "downloaded.txt")
    download(primary, "hello.txt", download_path)
    with open(download_path, "rb") as f:
        results["downloaded_content"] = f.read()
    print(f"\nDownloaded: {results['downloaded_content']}")

    # --- download with progress ---
    download_large = os.path.join(tmp_dir, "downloaded_large.bin")
    bytes_received: list[int] = []
    download(primary, "large.bin", download_large, on_progress=bytes_received.append)
    results["download_bytes"] = sum(bytes_received)
    print(f"Downloaded large.bin: {results['download_bytes']} bytes in {len(bytes_received)} chunk(s)")

    # --- download overwrite guard ---
    try:
        download(primary, "hello.txt", download_path)
    except FileExistsError as e:
        results["download_overwrite_guard"] = e
        print(f"\nOverwrite guard: {e}")

    # --- download with overwrite ---
    download(primary, "hello.txt", download_path, overwrite=True)
    print("Download with overwrite=True: OK")

    # --- transfer between stores ---
    transfer(primary, "hello.txt", archive, "hello_archived.txt")
    results["transferred_content"] = archive.read_bytes("hello_archived.txt")
    print(f"\nTransferred to archive: {results['transferred_content']}")

    # --- transfer with progress ---
    bytes_transferred: list[int] = []
    transfer(
        primary,
        "large.bin",
        archive,
        "large_archived.bin",
        on_progress=bytes_transferred.append,
    )
    results["transfer_bytes"] = sum(bytes_transferred)
    print(f"Transferred large.bin: {results['transfer_bytes']} bytes in {len(bytes_transferred)} chunk(s)")

    # --- transfer overwrite ---
    transfer(primary, "hello.txt", archive, "hello_archived.txt", overwrite=True)
    print("Transfer with overwrite=True: OK")

    # --- Final state ---
    print("\nPrimary store files:")
    for fi in primary.list_files(""):
        print(f"  {fi.path}")
    print("Archive store files:")
    for fi in archive.list_files(""):
        print(f"  {fi.path}")

    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"mem": BackendConfig(type="memory", options={})},
            stores={
                "primary": StoreProfile(backend="mem", root_path="primary"),
                "archive": StoreProfile(backend="mem", root_path="archive"),
            },
        )

        with Registry(config) as registry:
            primary = registry.get_store("primary")
            archive = registry.get_store("archive")
            demo(primary, archive, tmp)

    print("\nDone!")
