"""Atomic writes — write_atomic, overwrite semantics, and error handling.

Demonstrates atomic write operations that use temp-file-and-rename
to prevent partial writes from being visible to readers.
"""

from __future__ import annotations

import tempfile

from remote_store import AlreadyExists, BackendConfig, Registry, RegistryConfig, StoreProfile

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")

            # --- Basic atomic write ---
            store.write_atomic("config.json", b'{"version": 1}')
            print(f"Atomic write: {store.read_bytes('config.json').decode()}")

            # --- Atomic write refuses to overwrite by default ---
            try:
                store.write_atomic("config.json", b'{"version": 2}')
            except AlreadyExists as exc:
                print(f"\nExpected error: {exc}")

            # --- Atomic overwrite ---
            store.write_atomic("config.json", b'{"version": 2}', overwrite=True)
            print(f"\nAfter atomic overwrite: {store.read_bytes('config.json').decode()}")

            # --- Regular write also supports overwrite ---
            store.write("data.txt", b"original")
            print(f"\nOriginal: {store.read_bytes('data.txt').decode()}")

            store.write("data.txt", b"updated", overwrite=True)
            print(f"After overwrite: {store.read_bytes('data.txt').decode()}")

            # --- Regular write also refuses overwrite by default ---
            try:
                store.write("data.txt", b"should fail")
            except AlreadyExists as exc:
                print(f"\nExpected error: {exc}")

    print("\nDone!")
