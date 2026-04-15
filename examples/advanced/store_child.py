"""Store.child() — Runtime sub-scoping: create child stores that share a backend but isolate paths.

Demonstrates:
- Creating child stores with child(subpath)
- Children share the parent's backend (no new connections)
- Path isolation: children only see their own namespace
- Chaining: parent.child("a").child("b") == parent.child("a/b")
- Close semantics: closing a child does NOT close the backend
- Context manager usage with children
"""

from __future__ import annotations

import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile


def demo(store):
    """Child store creation, isolation, chaining, close semantics."""
    # --- Create child stores ---
    reports = store.child("reports")
    archive = store.child("archive")
    print(f"Parent:  {store!r}")
    print(f"Child 1: {reports!r}")
    print(f"Child 2: {archive!r}")

    # --- Write via children ---
    reports.write("q1.csv", b"revenue,100\n")
    reports.write("q2.csv", b"revenue,200\n")
    archive.write("2024/summary.txt", b"Year-end summary")
    print("\nWrote 3 files across 2 child stores.")

    # --- Path isolation ---
    print("\nreports/ files:")
    for f in reports.list_files("", recursive=True):
        print(f"  {f.path}")

    print("archive/ files:")
    for f in archive.list_files("", recursive=True):
        print(f"  {f.path}")

    print("Parent (all files):")
    for f in store.list_files("", recursive=True):
        print(f"  {f.path}")

    # --- Read from child ---
    content = reports.read_bytes("q1.csv")
    print(f"\nreports/q1.csv: {content.decode().strip()}")

    # --- Chaining ---
    deep = store.child("archive").child("2024")
    direct = store.child("archive/2024")
    print(f"\nChained:  {deep!r}")
    print(f"Direct:   {direct!r}")
    print(f"Equal:    {deep == direct}")

    content = deep.read_bytes("summary.txt")
    print(f"Read via chained child: {content.decode()}")

    # --- Close semantics ---
    child = store.child("reports")
    child.close()
    print(f"\nParent works after child.close(): {store.read_bytes('reports/q1.csv').decode().strip()}")

    # --- Context manager ---
    with store.child("reports") as scoped:
        info = scoped.get_file_info("q1.csv")
        print(f"\nContext manager child: {info.size} bytes")
    print(f"Parent still works: {store.exists('reports/q1.csv')}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"data": StoreProfile(backend="local", root_path="data")},
        )

        with Registry(config) as registry:
            store = registry.get_store("data")
            demo(store)

    print("\nDone!")
