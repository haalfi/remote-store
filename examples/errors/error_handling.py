"""Error handling — Catching `NotFound`, `AlreadyExists`, and more.

Demonstrates the normalized error hierarchy and how to handle errors
programmatically using structured attributes.

---
see_also:
  - label: Troubleshooting
    url: ../troubleshooting.md
    note: error diagnosis guide
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


def demo(store):
    """Exercise error paths. Returns caught exceptions for test verification."""
    results = {}

    # --- NotFound ---
    try:
        store.read_bytes("nonexistent.txt")
    except NotFound as exc:
        results["not_found"] = exc
        print(f"NotFound: {exc}")
        print(f"  path={exc.path}, backend={exc.backend}")

    # --- AlreadyExists ---
    store.write("existing.txt", b"data")
    try:
        store.write("existing.txt", b"new data")
    except AlreadyExists as exc:
        results["already_exists"] = exc
        print(f"\nAlreadyExists: {exc}")
        print(f"  path={exc.path}")

    # --- InvalidPath (path traversal attempt) ---
    try:
        store.read_bytes("../../etc/passwd")
    except InvalidPath as exc:
        results["invalid_path"] = exc
        print(f"\nInvalidPath: {exc}")
        print(f"  path={exc.path}")

    # --- Catch any remote-store error with the base class ---
    base_errors = []
    for path in ["missing.txt", "../../escape"]:
        try:
            store.read_bytes(path)
        except RemoteStoreError as exc:
            base_errors.append(exc)
            print(f"\nRemoteStoreError ({type(exc).__name__}): {exc}")
    results["base_class_errors"] = base_errors

    # --- delete with missing_ok ---
    store.delete("nonexistent.txt", missing_ok=True)
    results["missing_ok_succeeded"] = True
    print("\ndelete(missing_ok=True) succeeded silently.")

    # --- KeyError for unknown store names ---
    # (Requires a registry, so only exercised in __main__ standalone mode.)

    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")
            demo(store)

            # --- KeyError for unknown store names ---
            try:
                registry.get_store("unknown")
            except KeyError as exc:
                print(f"\nKeyError: {exc}")

    print("\nDone!")
