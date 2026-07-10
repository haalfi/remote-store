"""Cache hit/miss benchmarks — measure CachedStore read performance.

Compares read latency with and without caching to quantify the real I/O
savings from CachedStore. Cold reads (cache miss) should match uncached
latency; warm reads (cache hit) should be near-instant.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# Cache hit/miss performance
# ---------------------------------------------------------------------------


class TestCachePerformance:
    """Cache read latency — remote-store only (bench_backend)."""

    def test_cache_cold_read(self, bench_backend: Backend, benchmark: Any) -> None:
        """Read through CachedStore with empty cache (miss on every call)."""
        from remote_store import Store
        from remote_store.ext.cache import cache

        store = Store(bench_backend)
        path = _unique("cache_cold")
        data = b"X" * 65_536  # 64KB
        store.write(path, data)

        def _cold_read() -> None:
            # Fresh cache each call — always a miss. read_bytes() is the
            # cached operation (CachedStore caches read_bytes, not the
            # streaming read()); it also fully consumes and closes the
            # backend handle, so no reader is left for GC to reclaim.
            cached = cache(store, ttl=300.0)
            cached.read_bytes(path)

        benchmark(_cold_read)
        benchmark.extra_info["payload_bytes"] = len(data)

    def test_cache_warm_read(self, bench_backend: Backend, benchmark: Any) -> None:
        """Read through CachedStore with primed cache (hit on every call)."""
        from remote_store import Store
        from remote_store.ext.cache import cache

        store = Store(bench_backend)
        cached = cache(store, ttl=300.0)
        path = _unique("cache_warm")
        data = b"X" * 65_536  # 64KB
        cached.write(path, data)
        # Prime the cache (read_bytes is the cached op).
        cached.read_bytes(path)

        def _warm_read() -> None:
            cached.read_bytes(path)

        benchmark(_warm_read)
        benchmark.extra_info["payload_bytes"] = len(data)

    def test_uncached_read_baseline(self, bench_backend: Backend, benchmark: Any) -> None:
        """Baseline: read without cache for direct comparison."""
        from remote_store import Store

        store = Store(bench_backend)
        path = _unique("nocache")
        data = b"X" * 65_536  # 64KB
        store.write(path, data)

        def _uncached_read() -> None:
            store.read_bytes(path)

        benchmark(_uncached_read)
        benchmark.extra_info["payload_bytes"] = len(data)
