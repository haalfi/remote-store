"""Quickstart — minimal config, write, and read with remote-store.

Demonstrates:
- Creating a RegistryConfig with a local backend
- Opening a Registry and getting a Store
- Writing and reading a file
"""

from __future__ import annotations

import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"data": StoreProfile(backend="local", root_path="data")},
        )

        with Registry(config) as registry:
            store = registry.get_store("data")

            # Write a file
            store.write("hello.txt", b"Hello, world!")
            print(f"File exists: {store.exists('hello.txt')}")

            # Read it back
            content = store.read_bytes("hello.txt")
            print(f"Content: {content}")

            # Check metadata
            info = store.get_file_info("hello.txt")
            print(f"Size: {info.size} bytes")
            print(f"Modified: {info.modified_at}")

    print("Done! Temp directory cleaned up automatically.")
