"""Atomic writes — Atomic writes and overwrite semantics.

Demonstrates atomic write operations that use temp-file-and-rename
to prevent partial writes from being visible to readers.

---
see_also:
  - label: Concurrency
    url: ../concurrency.md
    note: atomicity and overwrite semantics
"""

from __future__ import annotations

import tempfile

from remote_store import AlreadyExists, BackendConfig, Registry, RegistryConfig, StoreProfile


def demo(store):
    """Atomic writes with overwrite semantics. Returns caught exceptions."""
    results = {}

    # --- Basic atomic write ---
    result = store.write_atomic("config.json", b'{"version": 1}')
    print(f"Atomic write: {store.read_bytes('config.json').decode()} ({result.size} bytes)")

    # --- Atomic write refuses to overwrite by default ---
    try:
        store.write_atomic("config.json", b'{"version": 2}')
    except AlreadyExists as exc:
        results["atomic_already_exists"] = exc
        print(f"\nExpected error: {exc}")

    # --- Atomic overwrite ---
    result = store.write_atomic("config.json", b'{"version": 2}', overwrite=True)
    print(f"\nAfter atomic overwrite: {store.read_bytes('config.json').decode()} ({result.size} bytes)")

    # --- Regular write also supports overwrite ---
    result = store.write("data.txt", b"original")
    print(f"\nOriginal: {store.read_bytes('data.txt').decode()} ({result.size} bytes)")

    result = store.write("data.txt", b"updated", overwrite=True)
    print(f"After overwrite: {store.read_bytes('data.txt').decode()} ({result.size} bytes)")

    # --- Regular write also refuses overwrite by default ---
    try:
        store.write("data.txt", b"should fail")
    except AlreadyExists as exc:
        results["write_already_exists"] = exc
        print(f"\nExpected error: {exc}")

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

    print("\nDone!")
