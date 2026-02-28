"""Transfer operations -- upload, download, and cross-store transfer.

Demonstrates:
- upload: stream a local file to a Store
- download: stream a Store file to a local path
- transfer: stream between two Stores
- on_progress: tracking bytes transferred
- overwrite semantics for all three functions
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

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        # -- Create a local file to upload --
        local_file = os.path.join(tmp, "hello.txt")
        with open(local_file, "wb") as f:
            f.write(b"Hello from local filesystem!")
        print(f"Created local file: {local_file}")

        # -- Set up two in-memory stores --
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

            # --- upload ---
            upload(primary, local_file, "hello.txt")
            print(f"\nUploaded to primary: {primary.read_bytes('hello.txt')}")

            # --- upload with progress ---
            large_file = os.path.join(tmp, "large.bin")
            with open(large_file, "wb") as f:
                f.write(b"x" * 100_000)

            bytes_sent: list[int] = []
            upload(primary, large_file, "large.bin", on_progress=bytes_sent.append)
            print(f"Uploaded large.bin: {sum(bytes_sent)} bytes in {len(bytes_sent)} chunk(s)")

            # --- download ---
            download_path = os.path.join(tmp, "downloaded.txt")
            download(primary, "hello.txt", download_path)
            with open(download_path, "rb") as f:
                print(f"\nDownloaded: {f.read()}")

            # --- download with progress ---
            download_large = os.path.join(tmp, "downloaded_large.bin")
            bytes_received: list[int] = []
            download(primary, "large.bin", download_large, on_progress=bytes_received.append)
            print(f"Downloaded large.bin: {sum(bytes_received)} bytes in {len(bytes_received)} chunk(s)")

            # --- download overwrite guard ---
            try:
                download(primary, "hello.txt", download_path)
            except FileExistsError as e:
                print(f"\nOverwrite guard: {e}")

            # --- download with overwrite ---
            download(primary, "hello.txt", download_path, overwrite=True)
            print("Download with overwrite=True: OK")

            # --- transfer between stores ---
            transfer(primary, "hello.txt", archive, "hello_archived.txt")
            print(f"\nTransferred to archive: {archive.read_bytes('hello_archived.txt')}")

            # --- transfer with progress ---
            bytes_transferred: list[int] = []
            transfer(
                primary,
                "large.bin",
                archive,
                "large_archived.bin",
                on_progress=bytes_transferred.append,
            )
            print(f"Transferred large.bin: {sum(bytes_transferred)} bytes in {len(bytes_transferred)} chunk(s)")

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

    print("\nDone!")
