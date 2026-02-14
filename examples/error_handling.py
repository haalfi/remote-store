"""Error handling — catching NotFound, AlreadyExists, InvalidPath, etc.

Demonstrates the normalized error hierarchy and how to handle errors
programmatically using structured attributes.
"""

from __future__ import annotations

import tempfile

from remote_store import (
    AlreadyExists,
    BackendConfig,
    InvalidPath,
    NotFound,
    Registry,
    RegistryConfig,
    RemoteStoreError,
    StoreProfile,
)

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")

            # --- NotFound ---
            try:
                store.read_bytes("nonexistent.txt")
            except NotFound as exc:
                print(f"NotFound: {exc}")
                print(f"  path={exc.path}, backend={exc.backend}")

            # --- AlreadyExists ---
            store.write("existing.txt", b"data")
            try:
                store.write("existing.txt", b"new data")
            except AlreadyExists as exc:
                print(f"\nAlreadyExists: {exc}")
                print(f"  path={exc.path}")

            # --- InvalidPath (path traversal attempt) ---
            try:
                store.read_bytes("../../etc/passwd")
            except InvalidPath as exc:
                print(f"\nInvalidPath: {exc}")
                print(f"  path={exc.path}")

            # --- Catch any remote-store error with the base class ---
            for path in ["missing.txt", "../../escape"]:
                try:
                    store.read_bytes(path)
                except RemoteStoreError as exc:
                    print(f"\nRemoteStoreError ({type(exc).__name__}): {exc}")

            # --- delete with missing_ok ---
            store.delete("nonexistent.txt", missing_ok=True)
            print("\ndelete(missing_ok=True) succeeded silently.")

            # --- KeyError for unknown store names ---
            try:
                registry.get_store("unknown")
            except KeyError as exc:
                print(f"\nKeyError: {exc}")

    print("\nDone!")
