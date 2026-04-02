"""Tests for ext.cache -- Store-level caching middleware."""

from __future__ import annotations

import re
import tempfile
import time
from typing import Any

import pytest

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.cache import CachedStore, MemoryCache, cache


@pytest.fixture
def store() -> Store:
    backend = MemoryBackend()
    s = Store(backend)
    s.write("a.txt", b"alpha")
    s.write("b.txt", b"bravo")
    s.write("sub/c.txt", b"charlie")
    return s


@pytest.fixture
def cached(store: Store) -> CachedStore:
    return cache(store, ttl=60.0)


@pytest.fixture
def mcache() -> MemoryCache:
    return MemoryCache()


class TestMemoryCache:
    @pytest.mark.spec("CACHE-002")
    def test_get_set(self, mcache: MemoryCache) -> None:
        mcache.set(("x",), 42, ttl=10.0)
        assert mcache.get(("x",)) == 42

    @pytest.mark.spec("CACHE-002")
    @pytest.mark.parametrize(
        ("setup", "key"),
        [
            pytest.param(None, ("missing",), id="missing"),
            pytest.param(("x", 42, 0.01), ("x",), id="expired"),
        ],
    )
    def test_get_raises_key_error(
        self, mcache: MemoryCache, setup: tuple[str, Any, float] | None, key: tuple[str, ...]
    ) -> None:
        if setup is not None:
            mcache.set((setup[0],), setup[1], ttl=setup[2])
            time.sleep(0.02)
        with pytest.raises(KeyError, match=re.escape(str(key))):
            mcache.get(key)

    @pytest.mark.spec("CACHE-002")
    def test_delete(self, mcache: MemoryCache) -> None:
        mcache.set(("x",), 42, ttl=10.0)
        mcache.delete(("x",))
        with pytest.raises(KeyError, match="x"):
            mcache.get(("x",))

    @pytest.mark.spec("CACHE-002")
    def test_delete_missing_is_noop(self, mcache: MemoryCache) -> None:
        result = mcache.delete(("missing",))
        assert result is None

    @pytest.mark.spec("CACHE-002")
    def test_clear(self, mcache: MemoryCache) -> None:
        mcache.set(("a",), 1, ttl=10.0)
        mcache.set(("b",), 2, ttl=10.0)
        mcache.clear()
        assert mcache.size() == 0

    @pytest.mark.spec("CACHE-001")
    def test_clear_prefix(self, mcache: MemoryCache) -> None:
        mcache.set(("list_files", "x"), 1, ttl=10.0)
        mcache.set(("list_files", "y"), 2, ttl=10.0)
        mcache.set(("exists", "x"), True, ttl=10.0)
        mcache.clear_prefix("list_files")
        assert mcache.size() == 1
        assert mcache.get(("exists", "x")) is True

    @pytest.mark.spec("CACHE-001")
    def test_clear_prefixes_batch(self, mcache: MemoryCache) -> None:
        mcache.set(("list_files", "x"), 1, ttl=10.0)
        mcache.set(("glob", "*.txt"), 2, ttl=10.0)
        mcache.set(("exists", "x"), True, ttl=10.0)
        mcache.clear_prefixes(frozenset({"list_files", "glob"}))
        assert mcache.size() == 1
        assert mcache.get(("exists", "x")) is True

    @pytest.mark.spec("CACHE-002")
    def test_size_excludes_expired(self, mcache: MemoryCache) -> None:
        mcache.set(("a",), 1, ttl=0.01)
        mcache.set(("b",), 2, ttl=10.0)
        time.sleep(0.02)
        assert mcache.size() == 1

    @pytest.mark.spec("BK-127")
    def test_size_does_not_evict_expired(self, mcache: MemoryCache) -> None:
        """size() counts without evicting — expired entries stay in _data."""
        mcache.set(("a",), 1, ttl=0.01)
        mcache.set(("b",), 2, ttl=10.0)
        time.sleep(0.02)
        assert mcache.size() == 1
        assert len(mcache._data) == 2  # expired entry not purged

    @pytest.mark.spec("CACHE-002")
    def test_max_entries_evicts_lru(self) -> None:
        mc = MemoryCache(max_entries=2)
        mc.set(("a",), 1, ttl=10.0)
        mc.set(("b",), 2, ttl=10.0)
        mc.set(("c",), 3, ttl=10.0)
        assert mc.size() == 2
        with pytest.raises(KeyError, match="a"):
            mc.get(("a",))
        assert mc.get(("b",)) == 2
        assert mc.get(("c",)) == 3

    @pytest.mark.spec("CACHE-002")
    @pytest.mark.parametrize(
        ("refresh_op", "expected_a"),
        [
            pytest.param("get", 1, id="access-refreshes"),
            pytest.param("set", 10, id="set-refreshes"),
        ],
    )
    def test_max_entries_lru_refresh(self, refresh_op: str, expected_a: int) -> None:
        mc = MemoryCache(max_entries=2)
        mc.set(("a",), 1, ttl=10.0)
        mc.set(("b",), 2, ttl=10.0)
        if refresh_op == "get":
            mc.get(("a",))
        else:
            mc.set(("a",), 10, ttl=10.0)
        mc.set(("c",), 3, ttl=10.0)  # should evict ("b",)
        assert mc.get(("a",)) == expected_a
        assert mc.get(("c",)) == 3
        with pytest.raises(KeyError, match="b"):
            mc.get(("b",))

    @pytest.mark.spec("CACHE-002")
    @pytest.mark.parametrize("val", [0, -1], ids=["zero", "negative"])
    def test_max_entries_invalid_raises(self, val: int) -> None:
        with pytest.raises(ValueError, match="max_entries must be positive"):
            MemoryCache(max_entries=val)


class TestFactory:
    @pytest.mark.spec("CACHE-003")
    def test_returns_cache(self, store: Store) -> None:
        result = cache(store, ttl=60.0)
        assert isinstance(result, CachedStore)
        assert isinstance(result, Store)
        assert result.read_bytes("a.txt") == b"alpha"

    @pytest.mark.spec("CACHE-003")
    def test_default_ttl(self, store: Store) -> None:
        assert cache(store)._ttl == 300.0

    @pytest.mark.spec("CACHE-003")
    def test_custom_cache_backend(self, store: Store) -> None:
        backend = MemoryCache()
        cached = cache(store, cache_backend=backend)
        cached.read_bytes("a.txt")
        assert backend.size() >= 1

    @pytest.mark.spec("CACHE-003")
    @pytest.mark.parametrize(
        ("kwarg", "val", "match"),
        [
            pytest.param("ttl", 0, "ttl must be positive", id="ttl-zero"),
            pytest.param("ttl", -1, "ttl must be positive", id="ttl-negative"),
            pytest.param("max_content_size", 0, "max_content_size must be positive", id="mcs-zero"),
            pytest.param("max_content_size", -5, "max_content_size must be positive", id="mcs-negative"),
        ],
    )
    def test_invalid_param_raises(self, store: Store, kwarg: str, val: Any, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            cache(store, **{kwarg: val})

    @pytest.mark.spec("CACHE-004")
    def test_inner_property(self, store: Store, cached: CachedStore) -> None:
        assert cached.inner is store

    @pytest.mark.spec("CACHE-004")
    def test_repr(self, cached: CachedStore) -> None:
        r = repr(cached)
        assert "CachedStore" in r
        assert "ttl=60" in r

    @pytest.mark.spec("CACHE-015")
    def test_close_delegates(self, store: Store) -> None:
        cs = cache(store, ttl=60.0)
        result = cs.close()
        assert result is None


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
        with pytest.raises(AttributeError):
            cached.stats.hits = 99  # type: ignore[misc]


class TestCachedReads:
    @pytest.mark.spec("CACHE-006")
    @pytest.mark.parametrize(
        ("method", "args", "kwargs"),
        [
            pytest.param("exists", ("a.txt",), {}, id="exists-true"),
            pytest.param("exists", ("missing.txt",), {}, id="exists-false"),
            pytest.param("is_file", ("a.txt",), {}, id="is_file"),
            pytest.param("is_folder", ("sub",), {}, id="is_folder"),
            pytest.param("read_bytes", ("a.txt",), {}, id="read_bytes"),
            pytest.param("get_file_info", ("a.txt",), {}, id="get_file_info"),
            pytest.param("get_folder_info", ("",), {}, id="get_folder_info"),
        ],
    )
    def test_operation_cached(
        self, cached: CachedStore, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        fn = getattr(cached, method)
        r1 = fn(*args, **kwargs)
        r2 = fn(*args, **kwargs)
        assert r1 == r2
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    @pytest.mark.parametrize(
        ("method", "args", "kwargs"),
        [
            pytest.param("list_files", ("",), {"recursive": True}, id="list_files"),
            pytest.param("list_folders", ("",), {}, id="list_folders"),
            pytest.param("iter_children", ("",), {}, id="iter_children"),
        ],
    )
    def test_iterable_operation_cached(
        self, cached: CachedStore, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        fn = getattr(cached, method)
        r1 = list(fn(*args, **kwargs))
        r2 = list(fn(*args, **kwargs))
        assert r1 == r2
        assert cached.stats.hits == 1

    @pytest.mark.spec("ITER-007")
    def test_iter_children_cached(self, cached: CachedStore) -> None:
        children1 = list(cached.iter_children(""))
        children2 = list(cached.iter_children(""))
        assert children1 == children2
        assert cached.stats.hits == 1

    @pytest.mark.spec("RTXT-005")
    def test_read_text_uses_cached_read_bytes(self, cached: CachedStore) -> None:
        cached.read_bytes("a.txt")
        assert cached.stats.misses == 1
        assert cached.read_text("a.txt") == "alpha"
        assert cached.stats.hits == 1
        assert cached.stats.misses == 1

    @pytest.mark.spec("CACHE-006")
    def test_glob_cached(self) -> None:

        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            inner = Store(backend)
            inner.write("a.txt", b"alpha")
            inner.write("b.txt", b"bravo")
            cs = cache(inner, ttl=60.0)
            files1 = list(cs.glob("*.txt"))
            files2 = list(cs.glob("*.txt"))
            assert files1 == files2
            assert len(files1) == 2
            assert cs.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    @pytest.mark.parametrize(
        ("call1_kwargs", "call2_kwargs"),
        [
            pytest.param({"recursive": True}, {"recursive": False}, id="different-recursive"),
            pytest.param({"pattern": None}, {"pattern": "None"}, id="none-vs-string-none"),
        ],
    )
    def test_list_files_different_params_separate_keys(
        self, cached: CachedStore, call1_kwargs: dict[str, Any], call2_kwargs: dict[str, Any]
    ) -> None:
        list(cached.list_files("", **call1_kwargs))
        list(cached.list_files("", **call2_kwargs))
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0

    @pytest.mark.spec("CACHE-006")
    def test_list_files_max_depth_normalizes_recursive_key(self, cached: CachedStore) -> None:
        """When max_depth is set, recursive is ignored -- both calls share one cache entry."""
        list(cached.list_files("", recursive=False, max_depth=1))
        list(cached.list_files("", recursive=True, max_depth=1))
        assert cached.stats.misses == 1
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-006")
    @pytest.mark.parametrize(
        ("max_size", "expected_hits"),
        [
            pytest.param(3, 0, id="large-content-not-cached"),
            pytest.param(100, 1, id="small-content-cached"),
        ],
    )
    def test_content_size_guard(self, store: Store, max_size: int, expected_hits: int) -> None:
        cs = cache(store, ttl=60.0, max_content_size=max_size)
        assert cs.read_bytes("a.txt") == b"alpha"
        assert cs.read_bytes("a.txt") == b"alpha"
        assert cs.stats.hits == expected_hits

    @pytest.mark.spec("CACHE-006")
    def test_expired_entry_causes_refetch(self, store: Store) -> None:
        cs = cache(store, ttl=0.05)
        assert cs.exists("a.txt") is True
        time.sleep(0.06)
        assert cs.exists("a.txt") is True
        assert cs.stats.misses == 2

    @pytest.mark.spec("CACHE-013")
    def test_not_found_not_cached(self, cached: CachedStore) -> None:
        from remote_store import NotFound

        with pytest.raises(NotFound):
            cached.get_file_info("missing.txt")
        with pytest.raises(NotFound):
            cached.get_file_info("missing.txt")
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0

    @pytest.mark.spec("CACHE-013")
    def test_exists_false_is_cached(self, cached: CachedStore) -> None:
        assert cached.exists("missing.txt") is False
        assert cached.exists("missing.txt") is False
        assert cached.stats.hits == 1

    @pytest.mark.spec("CACHE-014")
    def test_external_write_returns_stale(self, store: Store) -> None:
        cs = cache(store, ttl=60.0)
        assert cs.read_bytes("a.txt") == b"alpha"
        store.write("a.txt", b"external-update", overwrite=True)
        assert cs.read_bytes("a.txt") == b"alpha"
        assert cs.stats.hits == 1


class TestNonCached:
    @pytest.mark.spec("CACHE-007")
    def test_read_not_cached(self, cached: CachedStore) -> None:
        cached.read("a.txt").close()
        cached.read("a.txt").close()
        assert cached.stats.hits == 0
        assert cached.stats.misses == 0

    @pytest.mark.spec("CACHE-007")
    def test_supports_delegates(self, cached: CachedStore) -> None:
        from remote_store import Capability

        assert cached.supports(Capability.READ) is True

    @pytest.mark.spec("CACHE-007")
    def test_child_returns_cache(self, cached: CachedStore) -> None:
        child = cached.child("sub")
        assert isinstance(child, CachedStore)
        assert isinstance(child, Store)

    @pytest.mark.spec("CACHE-007")
    def test_child_propagates_caching(self, cached: CachedStore) -> None:
        """BUG-003: child() must propagate cache behavior."""
        cached.inner.write("sub/file.txt", b"content", overwrite=True)
        child = cached.child("sub")
        assert isinstance(child, CachedStore)
        child.read_bytes("file.txt")
        child.read_bytes("file.txt")
        assert child.stats.hits >= 1

    def test_child_propagates_max_entries(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        s.write("sub/a.txt", b"a", overwrite=True)
        parent = cache(s, max_entries=2)
        child = parent.child("sub")
        assert isinstance(child, CachedStore)
        assert child._max_entries == 2  # noqa: SLF001

    @pytest.mark.spec("CACHE-007")
    def test_native_path_delegates(self, cached: CachedStore) -> None:
        assert isinstance(cached.native_path("a.txt"), str)


class TestBug137:
    """BUG-137: write doesn't invalidate parent directory metadata."""

    @pytest.mark.spec("BUG-137")
    def test_write_nested_invalidates_parent_exists(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.exists("newdir") is False  # cached as False
        cs.write("newdir/file.txt", b"hello")
        assert cs.exists("newdir") is True  # must see fresh True

    @pytest.mark.spec("BUG-137")
    def test_write_nested_invalidates_parent_is_folder(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.is_folder("newdir") is False  # cached as False
        cs.write("newdir/file.txt", b"hello")
        assert cs.is_folder("newdir") is True  # must see fresh True

    @pytest.mark.spec("BUG-137")
    def test_write_deeply_nested_invalidates_all_ancestors(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.exists("a") is False
        assert cs.exists("a/b") is False
        cs.write("a/b/c.txt", b"data")
        assert cs.exists("a") is True
        assert cs.exists("a/b") is True

    @pytest.mark.spec("BUG-137")
    @pytest.mark.parametrize(
        ("write_method", "write_args", "write_kwargs"),
        [
            pytest.param("write_text", ("hello",), {}, id="write_text"),
            pytest.param("write_atomic", (b"hello",), {}, id="write_atomic"),
        ],
    )
    def test_other_write_methods_invalidate_ancestor(
        self, write_method: str, write_args: tuple[Any, ...], write_kwargs: dict[str, Any]
    ) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.exists("newdir") is False  # cached as False
        getattr(cs, write_method)("newdir/file.txt", *write_args, **write_kwargs)
        assert cs.exists("newdir") is True  # must see fresh True

    @pytest.mark.spec("BUG-137")
    def test_open_atomic_success_invalidates_ancestor(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.exists("newdir") is False  # cached as False
        with cs.open_atomic("newdir/file.txt") as f:
            f.write(b"hello")
        assert cs.exists("newdir") is True  # must see fresh True

    @pytest.mark.spec("BUG-137")
    def test_delete_invalidates_ancestor(self) -> None:
        """delete() invalidates ancestor cache entries — next read is a miss, not stale hit."""
        backend = MemoryBackend()
        s = Store(backend)
        s.write("dir/file.txt", b"data")
        cs = cache(s, ttl=60.0)
        assert cs.exists("dir") is True  # miss 1 — cached as True
        assert cs.stats.misses == 1
        cs.delete("dir/file.txt")
        cs.exists("dir")  # must be miss 2 — cache entry was invalidated
        assert cs.stats.misses == 2


class TestBug138:
    """BUG-138: child() creates isolated cache."""

    @pytest.mark.spec("BUG-138")
    def test_child_shares_cache_backend(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        child = cs.child("sub")
        assert isinstance(child, CachedStore)
        assert child._cache is cs._cache  # noqa: SLF001

    @pytest.mark.spec("BUG-138")
    def test_child_write_invalidates_parent_read_bytes(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        cs.write("sub/file.txt", b"version1", overwrite=True)
        assert cs.read_bytes("sub/file.txt") == b"version1"  # cached

        child = cs.child("sub")
        child.write("file.txt", b"version2", overwrite=True)

        assert cs.read_bytes("sub/file.txt") == b"version2"  # must be fresh

    @pytest.mark.spec("BUG-138")
    def test_child_write_invalidates_parent_exists(self) -> None:
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        assert cs.exists("sub/file.txt") is False  # cached as False

        child = cs.child("sub")
        child.write("file.txt", b"data")

        assert cs.exists("sub/file.txt") is True  # must be fresh

    @pytest.mark.spec("BUG-138")
    def test_child_delete_invalidates_parent_cache(self) -> None:
        """Child delete() should evict parent's cached read_bytes and exists entries."""
        backend = MemoryBackend()
        s = Store(backend)
        s.write("sub/file.txt", b"data")
        cs = cache(s, ttl=60.0)
        assert cs.read_bytes("sub/file.txt") == b"data"  # cached
        assert cs.exists("sub/file.txt") is True  # cached

        child = cs.child("sub")
        child.delete("file.txt")

        assert cs.exists("sub/file.txt") is False  # must be fresh

    @pytest.mark.spec("BUG-138")
    def test_grandchild_shares_cache_and_invalidates(self) -> None:
        """cache.child('a').child('b') shares cache; write invalidates root entries."""
        backend = MemoryBackend()
        s = Store(backend)
        cs = cache(s, ttl=60.0)
        cs.write("a/b/file.txt", b"v1", overwrite=True)
        assert cs.read_bytes("a/b/file.txt") == b"v1"  # cached

        grandchild = cs.child("a").child("b")
        assert isinstance(grandchild, CachedStore)
        assert grandchild._cache is cs._cache  # noqa: SLF001

        grandchild.write("file.txt", b"v2", overwrite=True)
        assert cs.read_bytes("a/b/file.txt") == b"v2"  # root cache sees fresh data


class TestInvalidation:
    @pytest.mark.spec("CACHE-008")
    @pytest.mark.parametrize(
        ("write_method", "write_args", "write_kwargs"),
        [
            pytest.param("write", (b"updated",), {"overwrite": True}, id="write"),
            pytest.param("write_atomic", (b"atomic-update",), {"overwrite": True}, id="write_atomic"),
        ],
    )
    def test_write_op_invalidates_read_bytes(
        self,
        cached: CachedStore,
        write_method: str,
        write_args: tuple[Any, ...],
        write_kwargs: dict[str, Any],
    ) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        getattr(cached, write_method)("a.txt", *write_args, **write_kwargs)
        assert cached.read_bytes("a.txt") == write_args[0]
        assert cached.stats.misses == 2

    @pytest.mark.spec("WTXT-005")
    def test_write_text_invalidates(self, cached: CachedStore) -> None:
        assert cached.read_bytes("a.txt") == b"alpha"
        cached.write_text("a.txt", "updated", overwrite=True)
        assert cached.read_text("a.txt") == "updated"
        assert cached.stats.misses == 2

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
        with pytest.raises(RuntimeError, match="abort"), cached.open_atomic("a.txt", overwrite=True) as f:  # noqa: PT012
            f.write(b"will be discarded")
            raise RuntimeError("abort")
        assert cached.read_bytes("a.txt") == b"alpha"
        assert cached.stats.hits == 1

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
        assert cached.stats.size == 0

    @pytest.mark.spec("CACHE-010")
    def test_move_invalidates_src_and_dst(self, cached: CachedStore) -> None:
        cached.exists("a.txt")
        cached.exists("moved.txt")
        cached.move("a.txt", "moved.txt")
        assert cached.exists("a.txt") is False
        assert cached.exists("moved.txt") is True
        assert cached.stats.misses == 4

    @pytest.mark.spec("CACHE-010")
    def test_copy_invalidates_entire_cache(self, cached: CachedStore) -> None:
        # Read and cache source file (1 miss)
        data = cached.read_bytes("a.txt")
        assert cached.stats.misses == 1

        # Copy operation invalidates entire cache to prevent stale entries
        # for nested paths that may have been overwritten
        cached.copy("a.txt", "copied.txt")

        # Subsequent reads are now misses (cache was cleared)
        assert cached.read_bytes("a.txt") == data
        assert cached.stats.misses == 2
        assert cached.stats.hits == 0


class TestDriftProtection:
    @pytest.mark.spec("CACHE-011")
    @pytest.mark.parametrize(
        ("attr_kind", "filter_fn"),
        [
            pytest.param(
                "methods",
                lambda cls, name: not name.startswith("_") and callable(getattr(cls, name)),
                id="methods",
            ),
            pytest.param(
                "properties",
                lambda cls, name: not name.startswith("_") and isinstance(getattr(cls, name, None), property),
                id="properties",
            ),
        ],
    )
    def test_all_store_attrs_overridden(self, attr_kind: str, filter_fn: Any) -> None:
        """CachedStore (or ProxyStore) must override every public method/property of Store."""
        from remote_store._proxy import ProxyStore

        store_attrs = {name for name in dir(Store) if filter_fn(Store, name)}
        overridden: set[str] = set()
        for cls in (CachedStore, ProxyStore):
            if attr_kind == "methods":
                overridden |= {
                    name for name in cls.__dict__ if not name.startswith("_") and callable(cls.__dict__[name])
                }
            else:
                overridden |= {
                    name
                    for name in cls.__dict__
                    if not name.startswith("_") and isinstance(cls.__dict__.get(name), property)
                }
        missing = store_attrs - overridden
        assert not missing, f"CachedStore/ProxyStore missing overrides for: {missing}"


class TestThreadSafety:
    @pytest.mark.spec("CACHE-012")
    def test_concurrent_reads(self, cached: CachedStore) -> None:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: cached.exists("a.txt"), range(20)))
        assert all(r is True for r in results)

    @pytest.mark.spec("CACHE-012")
    def test_concurrent_mixed_operations(self, store: Store) -> None:
        import concurrent.futures
        import random

        cs = cache(store, ttl=60.0)
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
        assert cs.stats.hits >= 0
        assert cs.stats.misses >= 0

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


class TestListingSizeGuard:
    """BK-123 M-1: max_listing_size prevents caching large listings."""

    @pytest.fixture
    def big_store(self) -> Store:
        """Store with 5 files for testing listing size limits."""
        backend = MemoryBackend()
        s = Store(backend)
        for i in range(5):
            s.write(f"file{i}.txt", f"data{i}".encode())
        s.write("sub/nested.txt", b"nested")
        return s

    @pytest.mark.spec("BK-123")
    def test_listing_exceeding_limit_not_cached(self, big_store: Store) -> None:
        """Listing with items > max_listing_size is NOT cached."""
        cs = cache(big_store, ttl=60.0, max_listing_size=2)
        # 5 files at root level -- exceeds limit of 2
        list(cs.list_files("", recursive=True))
        list(cs.list_files("", recursive=True))
        # Both calls should be misses (second call hits backend again)
        assert cs.stats.misses == 2
        assert cs.stats.hits == 0

    @pytest.mark.spec("BK-123")
    def test_listing_within_limit_is_cached(self, big_store: Store) -> None:
        """Listing with items <= max_listing_size IS cached."""
        cs = cache(big_store, ttl=60.0, max_listing_size=10)
        list(cs.list_files("", recursive=True))
        list(cs.list_files("", recursive=True))
        assert cs.stats.misses == 1
        assert cs.stats.hits == 1

    @pytest.mark.spec("BK-123")
    def test_default_none_always_caches(self, big_store: Store) -> None:
        """max_listing_size=None (default) always caches."""
        cs = cache(big_store, ttl=60.0)
        list(cs.list_files("", recursive=True))
        list(cs.list_files("", recursive=True))
        assert cs.stats.hits == 1

    @pytest.mark.spec("BK-123")
    @pytest.mark.parametrize(
        ("method", "args", "kwargs"),
        [
            pytest.param("list_files", ("",), {"recursive": True}, id="list_files"),
            pytest.param("list_folders", ("",), {}, id="list_folders"),
            pytest.param("iter_children", ("",), {}, id="iter_children"),
        ],
    )
    def test_all_listing_methods_respect_guard(
        self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        """All listing methods respect max_listing_size guard."""
        backend = MemoryBackend()
        s = Store(backend)
        # Create structure: 3 folders + 3 files at root so every listing > 2
        s.write("a.txt", b"a")
        s.write("d1/x.txt", b"x")
        s.write("d2/y.txt", b"y")
        s.write("d3/z.txt", b"z")
        cs = cache(s, ttl=60.0, max_listing_size=2)
        list(getattr(cs, method)(*args, **kwargs))
        list(getattr(cs, method)(*args, **kwargs))
        # Result has 3+ items > limit of 2, so second call is a miss
        assert cs.stats.misses == 2
        assert cs.stats.hits == 0

    @pytest.mark.spec("BK-123")
    def test_glob_respects_listing_size_guard(self) -> None:
        """glob() respects max_listing_size guard."""
        from remote_store.backends._local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            inner = Store(backend)
            inner.write("a.txt", b"a")
            inner.write("b.txt", b"b")
            inner.write("c.txt", b"c")
            cs = cache(inner, ttl=60.0, max_listing_size=2)
            list(cs.glob("*.txt"))
            list(cs.glob("*.txt"))
            # 3 matches > limit of 2
            assert cs.stats.misses == 2
            assert cs.stats.hits == 0

    @pytest.mark.spec("BK-123")
    def test_listing_at_exact_limit_is_cached(self, big_store: Store) -> None:
        """Listing with item count == max_listing_size IS cached (boundary)."""
        # big_store has 6 files (5 root + 1 nested)
        cs = cache(big_store, ttl=60.0, max_listing_size=6)
        list(cs.list_files("", recursive=True))
        list(cs.list_files("", recursive=True))
        assert cs.stats.misses == 1
        assert cs.stats.hits == 1

    @pytest.mark.spec("BK-123")
    @pytest.mark.parametrize("value", [0, -1], ids=["zero", "negative"])
    def test_max_listing_size_invalid_raises(self, value: int) -> None:
        """max_listing_size <= 0 raises ValueError."""
        backend = MemoryBackend()
        s = Store(backend)
        with pytest.raises(ValueError, match="max_listing_size must be positive"):
            cache(s, ttl=60.0, max_listing_size=value)


class TestPreFlightSizeCheck:
    """BK-123 M-2: pre-flight size check skips content caching when file_info is cached."""

    @pytest.mark.spec("BK-123")
    def test_cached_file_info_skips_content_caching(self) -> None:
        """When file_info is cached with size > max_content_size, read_bytes skips caching."""
        backend = MemoryBackend()
        s = Store(backend)
        s.write("big.txt", b"x" * 100)
        cs = cache(s, ttl=60.0, max_content_size=50)

        # First: cache file_info (size=100, which exceeds max_content_size=50)
        fi = cs.get_file_info("big.txt")
        assert fi.size == 100
        assert cs.stats.misses == 1

        # Now read_bytes -- should read from backend but NOT cache the content
        data = cs.read_bytes("big.txt")
        assert data == b"x" * 100
        assert cs.stats.misses == 2  # read_bytes is a miss

        # Second read_bytes -- should be a miss again (content was not cached)
        data2 = cs.read_bytes("big.txt")
        assert data2 == b"x" * 100
        assert cs.stats.misses == 3  # still a miss
        assert cs.stats.hits == 0  # no hits for read_bytes

    @pytest.mark.spec("BK-123")
    def test_no_cached_file_info_still_checks_size(self) -> None:
        """Without cached file_info, read_bytes still checks content size after fetch."""
        backend = MemoryBackend()
        s = Store(backend)
        s.write("big.txt", b"x" * 100)
        cs = cache(s, ttl=60.0, max_content_size=50)

        # read_bytes without prior get_file_info -- no pre-flight info available
        data = cs.read_bytes("big.txt")
        assert data == b"x" * 100
        # Content exceeds max_content_size, so it should not be cached
        data2 = cs.read_bytes("big.txt")
        assert data2 == b"x" * 100
        assert cs.stats.hits == 0  # never cached

    @pytest.mark.spec("BK-123")
    def test_small_file_info_cached_content_still_cached(self) -> None:
        """When file_info is cached with size <= max_content_size, content IS cached."""
        backend = MemoryBackend()
        s = Store(backend)
        s.write("small.txt", b"hi")
        cs = cache(s, ttl=60.0, max_content_size=50)

        cs.get_file_info("small.txt")  # cache file_info (size=2)
        cs.read_bytes("small.txt")  # should cache content (2 <= 50)
        cs.read_bytes("small.txt")  # should be a hit
        assert cs.stats.hits == 1
