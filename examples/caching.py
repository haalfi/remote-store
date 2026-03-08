"""Example: Store-level caching with ext.cache.

Demonstrates cached reads, automatic invalidation on writes,
cache statistics, and max_content_size.
"""

from __future__ import annotations

from remote_store import Store, cached_store
from remote_store.backends._memory import MemoryBackend


def demo(store: Store) -> None:
    """Run the caching demo against the given store."""
    # Populate some files
    store.write("report.csv", b"id,value\n1,100\n2,200")
    store.write("config.json", b'{"env": "dev"}')
    store.write("data/raw.bin", b"\x00" * 5000)

    # Wrap with caching (60s TTL, max 1 KB content caching)
    cached = cached_store(store, ttl=60, max_content_size=1024)

    # -- Cached reads --
    print("--- Cached reads ---")
    data1 = cached.read_bytes("report.csv")
    data2 = cached.read_bytes("report.csv")
    print(f"read_bytes hit: {data1 == data2}")
    print(f"Stats after 2 reads: hits={cached.stats.hits}, misses={cached.stats.misses}")

    # -- Large file skips cache --
    print("\n--- Large file (exceeds max_content_size) ---")
    cached.read_bytes("data/raw.bin")
    cached.read_bytes("data/raw.bin")
    print(f"Stats: hits={cached.stats.hits} (large file not cached)")

    # -- Existence checks --
    print("\n--- Existence caching ---")
    cached.exists("report.csv")
    cached.exists("report.csv")
    cached.exists("missing.txt")
    cached.exists("missing.txt")
    print(f"Stats: hits={cached.stats.hits}, misses={cached.stats.misses}")

    # -- Automatic invalidation --
    print("\n--- Write invalidation ---")
    cached.read_bytes("config.json")
    cached.write("config.json", b'{"env": "prod"}', overwrite=True)
    updated = cached.read_bytes("config.json")
    print(f"After write: {updated.decode()}")

    # -- Manual invalidation --
    print("\n--- Manual invalidation ---")
    cached.read_bytes("report.csv")
    cached.invalidate("report.csv")
    cached.read_bytes("report.csv")
    print(f"Final stats: hits={cached.stats.hits}, misses={cached.stats.misses}, size={cached.stats.size}")


if __name__ == "__main__":
    backend = MemoryBackend()
    with Store(backend) as s:
        demo(s)
