"""Tests for ext.cache -- Store-level caching middleware."""

from __future__ import annotations

import time

import pytest

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.cache import CachedStore, MemoryCache, cached_store

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store() -> Store:
    """A MemoryBackend-backed store with some test data."""
    backend = MemoryBackend()
    s = Store(backend)
    s.write("a.txt", b"alpha")
    s.write("b.txt", b"bravo")
    s.write("sub/c.txt", b"charlie")
    return s


@pytest.fixture()
def cached(store: Store) -> CachedStore:
    """A CachedStore wrapping the test store."""
    return cached_store(store, ttl=60.0)


# ===========================================================================
# CACHE-001: CacheBackend protocol -- MemoryCache
# ===========================================================================


class TestMemoryCache:
    """Unit tests for the MemoryCache implementation."""

    @pytest.mark.spec("CACHE-002")
    def test_get_set(self) -> None:
        cache = MemoryCache()
        cache.set(("x",), 42, ttl=10.0)
        assert cache.get(("x",)) == 42

    @pytest.mark.spec("CACHE-002")
    def test_get_missing_raises_key_error(self) -> None:
        cache = MemoryCache()
        with pytest.raises(KeyError):
            cache.get(("missing",))

    @pytest.mark.spec("CACHE-002")
    def test_get_expired_raises_key_error(self) -> None:
        cache = MemoryCache()
        cache.set(("x",), 42, ttl=0.01)
        time.sleep(0.02)
        with pytest.raises(KeyError):
            cache.get(("x",))

    @pytest.mark.spec("CACHE-002")
    def test_delete(self) -> None:
        cache = MemoryCache()
        cache.set(("x",), 42, ttl=10.0)
        cache.delete(("x",))
        with pytest.raises(KeyError):
            cache.get(("x",))

    @pytest.mark.spec("CACHE-002")
    def test_delete_missing_is_noop(self) -> None:
        cache = MemoryCache()
        cache.delete(("missing",))  # should not raise

    @pytest.mark.spec("CACHE-002")
    def test_clear(self) -> None:
        cache = MemoryCache()
        cache.set(("a",), 1, ttl=10.0)
        cache.set(("b",), 2, ttl=10.0)
        cache.clear()
        assert cache.size() == 0

    @pytest.mark.spec("CACHE-001")
    def test_clear_prefix(self) -> None:
        cache = MemoryCache()
        cache.set(("list_files", "x"), 1, ttl=10.0)
        cache.set(("list_files", "y"), 2, ttl=10.0)
        cache.set(("exists", "x"), True, ttl=10.0)
        cache.clear_prefix("list_files")
        assert cache.size() == 1
        assert cache.get(("exists", "x")) is True

    @pytest.mark.spec("CACHE-001")
    def test_clear_prefixes_batch(self) -> None:
        cache = MemoryCache()
        cache.set(("list_files", "x"), 1, ttl=10.0)
        cache.set(("glob", "*.txt"), 2, ttl=10.0)
        cache.set(("exists", "x"), True, ttl=10.0)
        cache.clear_prefixes(frozenset({"list_files", "glob"}))
        assert cache.size() == 1
        assert cache.get(("exists", "x")) is True

    @pytest.mark.spec("CACHE-002")
    def test_size_excludes_expired(self) -> None:
        cache = MemoryCache()
        cache.set(("a",), 1, ttl=0.01)
        cache.set(("b",), 2, ttl=10.0)
        time.sleep(0.02)
        assert cache.size() == 1

    @pytest.mark.spec("CACHE-002")
    def test_max_entries_evicts_lru(self) -> None:
        cache = MemoryCache(max_entries=2)
        cache.set(("a",), 1, ttl=10.0)
        cache.set(("b",), 2, ttl=10.0)
        cache.set(("c",), 3, ttl=10.0)  # should evict ("a",)
        assert cache.size() == 2
        with pytest.raises(KeyError):
            cache.get(("a",))
        assert cache.get(("b",)) == 2
        assert cache.get(("c",)) == 3

    @pytest.mark.spec("CACHE-002")
    def test_max_entries_lru_access_refreshes(self) -> None:
        cache = MemoryCache(max_entries=2)
        cache.set(("a",), 1, ttl=10.0)
        cache.set(("b",), 2, ttl=10.0)
        cache.get(("a",))  # refresh ("a",), making ("b",) the LRU
        cache.set(("c",), 3, ttl=10.0)  # should evict ("b",)
        assert cache.get(("a",)) == 1
        assert cache.get(("c",)) == 3
        with pytest.raises(KeyError):
            cache.get(("b",))

    @pytest.mark.spec("CACHE-002")
    def test_max_entries_lru_set_refreshes(self) -> None:
        """set() on an existing key moves it to end (LRU refresh)."""
        cache = MemoryCache(max_entries=2)
        cache.set(("a",), 1, ttl=10.0)
        cache.set(("b",), 2, ttl=10.0)
        cache.set(("a",), 10, ttl=10.0)  # refresh ("a",), making ("b",) the LRU
        cache.set(("c",), 3, ttl=10.0)  # should evict ("b",)
        assert cache.get(("a",)) == 10
        assert cache.get(("c",)) == 3
        with pytest.raises(KeyError):
            cache.get(("b",))

    @pytest.mark.spec("CACHE-002")
    def test_max_entries_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="max_entries must be positive"):
            MemoryCache(max_entries=0)
        with pytest.raises(ValueError, match="max_entries must be positive"):
            MemoryCache(max_entries=-1)


# ===========================================================================
# CACHE-003: cached_store() factory
# ===========================================================================


class TestFactory:
    @pytest.mark.spec("CACHE-003")
    def test_returns_cached_store(self, store: Store) -> None:
        result = cached_store(store, ttl=60.0)
        assert isinstance(result, CachedStore)
        assert isinstance(result, Store)

    @pytest.mark.spec("CACHE-003")
    def test_default_ttl(self, store: Store) -> None:
        result = cached_store(store)
        assert result._ttl == 300.0

    @pytest.mark.spec("CACHE-003")
    def test_custom_cache_backend(self, store: Store) -> None:
        backend = MemoryCache()
        result = cached_store(store, cache_backend=backend)
        assert result._cache is backend

    @pytest.mark.spec("CACHE-003")
    def test_invalid_ttl_raises(self, store: Store) -> None:
        with pytest.raises(ValueError, match="ttl must be positive"):
            cached_store(store, ttl=0)
        with pytest.raises(ValueError, match="ttl must be positive"):
            cached_store(store, ttl=-1)

    @pytest.mark.spec("CACHE-003")
    def test_invalid_max_content_size_raises(self, store: Store) -> None:
        with pytest.raises(ValueError, match="max_content_size must be positive"):
            cached_store(store, max_content_size=0)
        with pytest.raises(ValueError, match="max_content_size must be positive"):
            cached_store(store, max_content_size=-5)

    @pytest.mark.spec("CACHE-004")
    def test_inner_property(self, store: Store, cached: CachedStore) -> None:
        assert cached.inner is store


# ===========================================================================
# CACHE-005: CacheStats
# ===========================================================================


class TestCacheStats:
    @pytest.mark.spec("CACHE-005")
    def test_initial_stats(self, cached: CachedStore) -> None:
        s = cached.stats
        assert s.hits == 0
        assert s.misses == 0
        assert s.size == 0

    @pytest.mark.spec("CACHE-005")
    def test_stats_after_hit_and_miss(self, cached: CachedStore) -> None:
        cached.exists("a.txt")  # miss
        cached.exists("a.txt")  # hit
        s = cached.stats
        assert s.hits == 1
        assert s.misses == 1
        assert s.size >= 1

    @pytest.mark.spec("CACHE-005")
    def test_stats_frozen(self, cached: CachedStore) -> None:
        s = cached.stats
        with pytest.raises(AttributeError):
            s.hits = 99  # type: ignore[misc]


# ===========================================================================
# CACHE-006: Cached read operations
# ===========================================================================


class TestCachedReads:
    @pytest.mark.spec("CACHE-006")
    def test_exists_cached(self, cached: CachedStore) -> None:
        assert cached.exists("a.txt") is True
        assert cached.exists("a.txt") is True
        assert cached.stats.hits == 1
        assert cached.stats.misses == 1

    @pytest.mark.spec("CACHE-006")
    def test_exists_false_cached(self, cached: CachedStore) -> None:
        assert cached.exists("missing.txt") is False
        assert cached.exists("missing.txt") is False
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_is_file_cached(self, cached: CachedStore) -> None:
        assert cached.is_file("a.txt") is True
        assert cached.is_file("a.txt") is True
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_is_folder_cached(self, cached: CachedStore) -> None:
        assert cached.is_folder("sub") is True
        assert cached.is_folder("sub") is True
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_read_bytes_cached(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 1

    @pytest.mark.spec("RTXT-005")
    def test_read_text_uses_cached_read_bytes(self, cached: CachedStore) -> None:
        # Prime read_bytes cache
        cached.read_bytes("a.txt")
        assert cached.stats.misses == 1
        # read_text should use cached read_bytes (no new miss)
        assert cached.read_text("a.txt") == "alpha"
        assert cached.stats.hits == 1
        assert cached.stats.misses == 1

    @pytest.mark.spec("CACHE-006")
    def test_get_file_info_cached(self, cached: CachedStore) -> None:
        info1 = cached.get_file_info("a.txt")
        info2 = cached.get_file_info("a.txt")
        assert info1 == info2
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_get_folder_info_cached(self, cached: CachedStore) -> None:
        info1 = cached.get_folder_info("")
        info2 = cached.get_folder_info("")
        assert info1 == info2
        assert cached.stats.hits == 1

    @pytest.mark.spec("ITER-007")
    def test_iter_children_cached(self, cached: CachedStore) -> None:
        children1 = list(cached.iter_children(""))
        children2 = list(cached.iter_children(""))
        assert children1 == children2
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_list_files_cached(self, cached: CachedStore) -> None:
        files1 = list(cached.list_files("", recursive=True))
        files2 = list(cached.list_files("", recursive=True))
        assert files1 == files2
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_list_folders_cached(self, cached: CachedStore) -> None:
        folders1 = list(cached.list_folders(""))
        folders2 = list(cached.list_folders(""))
        assert folders1 == folders2
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_glob_cached(self) -> None:
        import tempfile

        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            inner = Store(backend)
            inner.write("a.txt", b"alpha")
            inner.write("b.txt", b"bravo")
            cs = cached_store(inner, ttl=60.0)
            files1 = list(cs.glob("*.txt"))
            files2 = list(cs.glob("*.txt"))
            assert files1 == files2
            assert len(files1) == 2
            assert cs.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    def test_list_files_different_params_separate_keys(self, cached: CachedStore) -> None:
        list(cached.list_files("", recursive=True))
        list(cached.list_files("", recursive=False))
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0

    @pytest.mark.spec("CACHE-006")
    def test_list_files_none_pattern_distinct_from_string_none(self, cached: CachedStore) -> None:
        """pattern=None and pattern='None' must not share a cache key."""
        list(cached.list_files("", pattern=None))
        list(cached.list_files("", pattern="None"))
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0


# ===========================================================================
# CACHE-007: Non-cached operations
# ===========================================================================


class TestNonCached:
    @pytest.mark.spec("CACHE-007")
    def test_read_not_cached(self, cached: CachedStore) -> None:
        stream1 = cached.read("a.txt")
        stream1.close()
        stream2 = cached.read("a.txt")
        stream2.close()
        # read() doesn't touch cache at all
        assert cached.stats.hits == 0
        assert cached.stats.misses == 0

    @pytest.mark.spec("CACHE-007")
    def test_supports_delegates(self, cached: CachedStore) -> None:
        from remote_store import Capability

        assert cached.supports(Capability.READ) is True

    @pytest.mark.spec("CACHE-007")
    def test_child_returns_cached_store(self, cached: CachedStore) -> None:
        child = cached.child("sub")
        assert isinstance(child, CachedStore)
        assert isinstance(child, Store)

    @pytest.mark.spec("CACHE-007")
    def test_child_propagates_caching(self, cached: CachedStore) -> None:
        """BUG-003: child() must propagate cache behavior."""
        cached.inner.write("sub/file.txt", b"content", overwrite=True)
        child = cached.child("sub")
        assert isinstance(child, CachedStore)
        # Read twice through child — second should be a cache hit
        child.read_bytes("file.txt")
        child.read_bytes("file.txt")
        assert child.stats.hits >= 1

    @pytest.mark.spec("CACHE-007")
    def test_native_path_delegates(self, cached: CachedStore) -> None:
        result = cached.native_path("a.txt")
        assert isinstance(result, str)


# ===========================================================================
# CACHE-008: Write invalidation
# ===========================================================================


class TestWriteInvalidation:
    @pytest.mark.spec("CACHE-008")
    def test_write_invalidates_path(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        cached.write("a.txt", b"updated", overwrite=True)
        assert cached.read_bytes("a.txt") == b"updated"
        assert cached.stats.misses == 2  # both calls are misses

    @pytest.mark.spec("CACHE-008")
    def test_write_invalidates_listings(self, cached: CachedStore) -> None:
        list(cached.list_files(""))
        cached.write("new.txt", b"data")
        list(cached.list_files(""))
        assert cached.stats.misses == 2

    @pytest.mark.spec("ITER-007")
    def test_write_invalidates_iter_children(self, cached: CachedStore) -> None:
        list(cached.iter_children(""))
        cached.write("new2.txt", b"data")
        list(cached.iter_children(""))
        assert cached.stats.misses == 2

    @pytest.mark.spec("CACHE-008")
    def test_write_invalidates_exists(self, cached: CachedStore) -> None:
        assert cached.exists("new.txt") is False
        cached.write("new.txt", b"data")
        assert cached.exists("new.txt") is True
        assert cached.stats.misses == 2

    @pytest.mark.spec("WTXT-005")
    def test_write_text_invalidates(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        cached.write_text("a.txt", "updated", overwrite=True)
        assert cached.read_text("a.txt") == "updated"
        assert cached.stats.misses == 2  # both calls are misses

    @pytest.mark.spec("CACHE-008")
    def test_write_atomic_invalidates(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        cached.write_atomic("a.txt", b"atomic-update", overwrite=True)
        assert cached.read_bytes("a.txt") == b"atomic-update"
        assert cached.stats.misses == 2

    @pytest.mark.spec("CACHE-008")
    def test_open_atomic_invalidates_on_success(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        with cached.open_atomic("a.txt", overwrite=True) as f:
            f.write(b"streamed-update")
        assert cached.read_bytes("a.txt") == b"streamed-update"
        assert cached.stats.misses == 2

    @pytest.mark.spec("CACHE-008")
    def test_open_atomic_no_invalidation_on_error(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        with pytest.raises(RuntimeError, match="abort"), cached.open_atomic("a.txt", overwrite=True) as f:
            f.write(b"will be discarded")
            raise RuntimeError("abort")
        # Cache should still have the old value (no invalidation happened).
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 1


# ===========================================================================
# CACHE-009: Delete invalidation
# ===========================================================================


class TestDeleteInvalidation:
    @pytest.mark.spec("CACHE-009")
    def test_delete_invalidates_path(self, cached: CachedStore) -> None:
        assert cached.exists("a.txt") is True
        cached.delete("a.txt")
        assert cached.exists("a.txt") is False
        assert cached.stats.misses == 2

    @pytest.mark.spec("CACHE-009")
    def test_delete_folder_clears_all(self, cached: CachedStore) -> None:
        cached.exists("sub/c.txt")
        cached.exists("a.txt")
        cached.delete_folder("sub", recursive=True)
        # All cache should be cleared
        assert cached.stats.size == 0


# ===========================================================================
# CACHE-010: Move/Copy invalidation
# ===========================================================================


class TestMoveCopyInvalidation:
    @pytest.mark.spec("CACHE-010")
    def test_move_invalidates_src_and_dst(self, cached: CachedStore) -> None:
        cached.exists("a.txt")
        cached.exists("moved.txt")
        cached.move("a.txt", "moved.txt")
        # Both should be misses now
        assert cached.exists("a.txt") is False
        assert cached.exists("moved.txt") is True
        # 2 initial misses + 2 after invalidation = 4
        assert cached.stats.misses == 4

    @pytest.mark.spec("CACHE-010")
    def test_copy_invalidates_dst_only(self, cached: CachedStore) -> None:
        data = cached.read_bytes("a.txt")
        cached.copy("a.txt", "copied.txt")
        # Source should still be cached
        assert cached.read_bytes("a.txt") == data
        assert cached.stats.hits == 1


# ===========================================================================
# CACHE-011: Drift-protection test
# ===========================================================================


class TestDriftProtection:
    @pytest.mark.spec("CACHE-011")
    def test_all_store_methods_overridden(self) -> None:
        """CachedStore (or ProxyStore) must override every public method of Store."""
        from remote_store._proxy import ProxyStore

        store_public = {name for name in dir(Store) if not name.startswith("_") and callable(getattr(Store, name))}
        # Methods overridden in CachedStore itself or in ProxyStore base
        overridden = set()
        for cls in (CachedStore, ProxyStore):
            overridden |= {name for name in cls.__dict__ if not name.startswith("_") and callable(cls.__dict__[name])}
        missing = store_public - overridden
        assert not missing, f"CachedStore/ProxyStore missing overrides for: {missing}"

    @pytest.mark.spec("CACHE-011")
    def test_all_store_properties_overridden(self) -> None:
        """CachedStore (or ProxyStore) must override every public property of Store."""
        from remote_store._proxy import ProxyStore

        store_props = {
            name for name in dir(Store) if not name.startswith("_") and isinstance(getattr(Store, name, None), property)
        }
        overridden = set()
        for cls in (CachedStore, ProxyStore):
            overridden |= {
                name
                for name in cls.__dict__
                if not name.startswith("_") and isinstance(cls.__dict__.get(name), property)
            }
        missing = store_props - overridden
        assert not missing, f"CachedStore/ProxyStore missing property overrides for: {missing}"


# ===========================================================================
# CACHE-012: Thread safety
# ===========================================================================


class TestThreadSafety:
    @pytest.mark.spec("CACHE-012")
    def test_concurrent_reads(self, cached: CachedStore) -> None:
        """Smoke test: concurrent reads should not crash."""
        import concurrent.futures

        def read_exists(_: int) -> bool:
            return cached.exists("a.txt")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(read_exists, range(20)))
        assert all(r is True for r in results)

    @pytest.mark.spec("CACHE-012")
    def test_concurrent_mixed_operations(self, store: Store) -> None:
        """Stress test: concurrent reads, writes, and invalidations."""
        import concurrent.futures
        import random

        cs = cached_store(store, ttl=60.0)

        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                rng = random.Random(idx)
                for _ in range(20):
                    op = rng.choice(["read", "write", "invalidate", "list"])
                    if op == "read":
                        cs.exists("a.txt")
                    elif op == "write":
                        cs.write("a.txt", b"updated", overwrite=True)
                    elif op == "invalidate":
                        cs.invalidate("a.txt")
                    elif op == "list":
                        list(cs.list_files(""))
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(16)))

        assert not errors, f"Concurrent operations raised: {errors}"
        # Stats should be consistent (non-negative, sum makes sense).
        s = cs.stats
        assert s.hits >= 0
        assert s.misses >= 0


# ===========================================================================
# CACHE-013: Error semantics
# ===========================================================================


class TestErrorSemantics:
    @pytest.mark.spec("CACHE-013")
    def test_not_found_not_cached(self, cached: CachedStore) -> None:
        from remote_store import NotFound

        with pytest.raises(NotFound):
            cached.get_file_info("missing.txt")
        # The error should not be cached -- next call hits backend again.
        with pytest.raises(NotFound):
            cached.get_file_info("missing.txt")
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0

    @pytest.mark.spec("CACHE-013")
    def test_exists_false_is_cached(self, cached: CachedStore) -> None:
        assert cached.exists("missing.txt") is False
        assert cached.exists("missing.txt") is False
        assert cached.stats.hits == 1


# ===========================================================================
# CACHE-006: max_content_size guard
# ===========================================================================


class TestMaxContentSize:
    @pytest.mark.spec("CACHE-006")
    def test_large_content_not_cached(self, store: Store) -> None:
        cached = cached_store(store, ttl=60.0, max_content_size=3)
        assert cached.read_bytes("a.txt") == b"alpha"  # 5 bytes > 3
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 0  # never cached

    @pytest.mark.spec("CACHE-006")
    def test_small_content_cached(self, store: Store) -> None:
        cached = cached_store(store, ttl=60.0, max_content_size=100)
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 1


# ===========================================================================
# CACHE-006: TTL expiration
# ===========================================================================


class TestTTLExpiration:
    @pytest.mark.spec("CACHE-006")
    def test_expired_entry_causes_refetch(self, store: Store) -> None:
        cached = cached_store(store, ttl=0.05)
        assert cached.exists("a.txt") is True
        time.sleep(0.06)
        assert cached.exists("a.txt") is True
        assert cached.stats.misses == 2


# ===========================================================================
# CACHE-012: Manual invalidation
# ===========================================================================


class TestManualInvalidation:
    @pytest.mark.spec("CACHE-012")
    def test_invalidate_path(self, cached: CachedStore) -> None:
        cached.exists("a.txt")
        cached.invalidate("a.txt")
        cached.exists("a.txt")
        assert cached.stats.misses == 2

    @pytest.mark.spec("CACHE-012")
    def test_clear_cache(self, cached: CachedStore) -> None:
        cached.exists("a.txt")
        cached.exists("b.txt")
        cached.clear_cache()
        assert cached.stats.size == 0


# ===========================================================================
# CACHE-015: Lifecycle
# ===========================================================================


class TestLifecycle:
    @pytest.mark.spec("CACHE-015")
    def test_close_delegates(self, store: Store) -> None:
        cached = cached_store(store, ttl=60.0)
        cached.close()  # should not raise

    @pytest.mark.spec("CACHE-004")
    def test_repr(self, cached: CachedStore) -> None:
        r = repr(cached)
        assert "CachedStore" in r
        assert "ttl=60" in r


# ===========================================================================
# CACHE-014: Stale data contract (documented behavior)
# ===========================================================================


class TestStaleData:
    @pytest.mark.spec("CACHE-014")
    def test_external_write_returns_stale(self, store: Store) -> None:
        cached = cached_store(store, ttl=60.0)
        assert cached.read_bytes("a.txt") == b"alpha"
        # Write directly to inner store (simulating external mutation).
        store.write("a.txt", b"external-update", overwrite=True)
        # Cache still returns old value.
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 1
