"""SFTP backend — connect to any SSH/SFTP server.

Demonstrates:
- Configuring an SFTP backend via RegistryConfig
- File operations: write, read, list, copy, move, delete, delete_folder
- Streaming line iteration
- Escape hatch: unwrap() to access paramiko.SFTPClient

Prerequisites:
- pip install "remote-store[sftp]"
- An accessible SFTP server

Environment variables:
    RS_SFTP_HOST    SFTP hostname (required)
    RS_SFTP_USER    SSH username (required)
    RS_SFTP_PASS    SSH password
    RS_SFTP_PORT    SSH port (default: 22)
    RS_SFTP_BASE    Base path on the server (default: /)
"""

from __future__ import annotations

import os
import sys

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile
from remote_store.backends._sftp import HostKeyPolicy

HOST = os.environ.get("RS_SFTP_HOST", "")
USER = os.environ.get("RS_SFTP_USER", "")

if not HOST or not USER:
    print(
        "Set RS_SFTP_HOST and RS_SFTP_USER to run this example.\n"
        "Optional: RS_SFTP_PASS, RS_SFTP_PORT, RS_SFTP_BASE\n\n"
        "Example with a local Docker SFTP server:\n"
        "  RS_SFTP_HOST=localhost RS_SFTP_USER=benchuser RS_SFTP_PASS=benchpass "
        "RS_SFTP_PORT=2222 RS_SFTP_BASE=/upload python examples/sftp_backend.py"
    )
    sys.exit(1)

if __name__ == "__main__":
    # --- Build options from environment ---
    options: dict[str, object] = {
        "host": HOST,
        "username": USER,
    }
    if val := os.environ.get("RS_SFTP_PASS"):
        options["password"] = val
    if val := os.environ.get("RS_SFTP_PORT"):
        options["port"] = int(val)
    if val := os.environ.get("RS_SFTP_BASE"):
        options["base_path"] = val

    # host_key_policy is an enum — it works in Python config-as-code (below)
    # but cannot be serialized to JSON/TOML. When loading from a file, use
    # direct backend construction instead (see commented section at the end).
    # The default is STRICT; for dev/testing with unknown hosts use AUTO_ADD.
    options["host_key_policy"] = HostKeyPolicy.AUTO_ADD

    config = RegistryConfig(
        backends={"sftp": BackendConfig(type="sftp", options=options)},
        stores={"files": StoreProfile(backend="sftp", root_path="example")},
    )

    with Registry(config) as registry:
        store = registry.get_store("files")

        # --- Write ---
        store.write("readme.txt", b"Hello from SFTP!\n")
        store.write("data/report.csv", b"col1,col2\n10,20\n30,40\n")
        print("Wrote 2 files.")

        # --- Read ---
        content = store.read_bytes("readme.txt")
        print(f"\nreadme.txt: {content.decode().strip()}")

        # --- Metadata ---
        info = store.get_file_info("readme.txt")
        print(f"readme.txt  size={info.size}  modified={info.modified_at}")

        # --- List files (recursive) ---
        print("\nAll files (recursive):")
        for f in store.list_files("", recursive=True):
            print(f"  {f.path}  ({f.size} bytes)")

        # --- List folders ---
        print("\nFolders:")
        for folder in store.list_folders(""):
            print(f"  {folder.name}/")

        # --- Folder info ---
        folder_info = store.get_folder_info("data")
        print(f"\ndata/ totals: {folder_info.file_count} files, {folder_info.total_size} bytes")

        # --- Copy (SFTP copy = read + write, no server-side copy) ---
        store.copy("readme.txt", "readme_backup.txt")
        print(f"\nCopied readme.txt -> readme_backup.txt (exists: {store.exists('readme_backup.txt')})")

        # --- Move (uses posix_rename with fallback) ---
        store.move("readme_backup.txt", "archive/readme_old.txt")
        print(f"Moved to archive/readme_old.txt (original exists: {store.exists('readme_backup.txt')})")

        # --- Streaming line iteration ---
        reader = store.read("data/report.csv")
        print("\nStreaming read (line by line):")
        newline = b"\n"
        for line in reader:
            text = line.rstrip(newline).decode()
            if text:
                print(f"  {text}")

        # --- Delete files and folders ---
        for f in store.list_files("", recursive=True):
            store.delete(str(f.path))
        store.delete_folder("data")
        store.delete_folder("archive")
        print("\nCleaned up all example files and folders.")

    # --- Escape hatch: unwrap() via direct construction ---
    # Construct the backend directly to access paramiko.SFTPClient and to
    # set host_key_policy for dev/testing environments.
    from remote_store.backends import SFTPBackend
    from remote_store.backends._sftp import HostKeyPolicy

    backend = SFTPBackend(
        host=HOST,
        port=int(os.environ.get("RS_SFTP_PORT", "22")),
        username=USER,
        password=os.environ.get("RS_SFTP_PASS"),
        base_path=os.environ.get("RS_SFTP_BASE", "/"),
        host_key_policy=HostKeyPolicy.AUTO_ADD,  # Dev/testing only!
    )

    try:
        import paramiko

        sftp_client = backend.unwrap(paramiko.SFTPClient)
        print(f"\nparamiko SFTPClient: {type(sftp_client).__name__}")
    finally:
        backend.close()

    # --- Host key policies (commented out) ---
    #
    # from remote_store.backends._sftp import HostKeyPolicy
    #
    # # STRICT (default) — reject unknown hosts; key must be in known_hosts
    # backend = SFTPBackend(host="...", username="...", password="...",
    #                       host_key_policy=HostKeyPolicy.STRICT)
    #
    # # TRUST_ON_FIRST_USE — accept and save on first connect, verify after
    # backend = SFTPBackend(host="...", username="...", password="...",
    #                       host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE)
    #
    # # AUTO_ADD — accept any key silently (dev/testing only)
    # backend = SFTPBackend(host="...", username="...", password="...",
    #                       host_key_policy=HostKeyPolicy.AUTO_ADD)

    # --- Key-based authentication (commented out) ---
    #
    # from remote_store.backends._sftp import load_private_key
    #
    # # From a file
    # pkey = load_private_key("/path/to/id_rsa", from_file=True)
    # backend = SFTPBackend(host="...", username="...", pkey=pkey)
    #
    # # From a PEM string (e.g. from a secrets manager)
    # pkey = load_private_key(pem_string)
    # backend = SFTPBackend(host="...", username="...", pkey=pkey)

    print("\nDone!")
