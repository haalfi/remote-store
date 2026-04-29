"""Memory backend — In-process memory backend for testing and caching — no filesystem access needed.

Demonstrates:
- Creating a MemoryBackend directly (no filesystem, no config)
- Using MemoryBackend through Store for scoped access
- Using MemoryBackend through Registry with config
- All standard Store operations work identically to other backends

---
see_also:
  - label: Memory Backend
    url: ../how-to/backends/memory.md
    note: backend guide
"""

from __future__ import annotations

from remote_store import BackendConfig, Registry, RegistryConfig, Store, StoreProfile
from remote_store.backends import MemoryBackend


def demo(store):
    """Standard Store operations on any backend."""
    store.write_text("hello.txt", "Hello from memory!")
    print(f"exists: {store.exists('hello.txt')}")
    print(f"content: {store.read_text('hello.txt')}")

    # Folders are created automatically
    store.write("reports/q1.csv", b"revenue,100\n")
    store.write("reports/q2.csv", b"revenue,200\n")
    print(f"\nFiles in reports/: {[f.name for f in store.list_files('reports')]}")
    print(f"Folders: {[f.name for f in store.list_folders('')]}")

    info = store.get_folder_info("reports")
    print(f"Folder info: {info.file_count} files, {info.total_size} bytes")

    # Move and copy
    store.copy("reports/q1.csv", "archive/q1.csv")
    store.move("reports/q2.csv", "archive/q2.csv")
    print("\nAfter move/copy:")
    print(f"  reports: {[f.name for f in store.list_files('reports')]}")
    print(f"  archive: {[f.name for f in store.list_files('archive')]}")


if __name__ == "__main__":
    # --- Option 1: Direct usage (simplest) ---
    backend = MemoryBackend()
    store = Store(backend=backend, root_path="data")

    demo(store)
    print(f"\nFinal state: {backend!r}")

    # --- Option 2: Via Registry config ---
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory")},
        stores={
            "uploads": StoreProfile(backend="mem", root_path="uploads"),
            "cache": StoreProfile(backend="mem", root_path="cache"),
        },
    )

    with Registry(config) as registry:
        uploads = registry.get_store("uploads")
        cache = registry.get_store("cache")

        uploads.write("photo.jpg", b"\xff\xd8fake-jpeg")
        cache.write("page.html", b"<html>cached</html>")

        print(f"\nRegistry uploads: {[f.name for f in uploads.list_files('')]}")
        print(f"Registry cache: {[f.name for f in cache.list_files('')]}")

    print("\nDone!")
