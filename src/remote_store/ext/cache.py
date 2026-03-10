"""Store-level caching middleware with TTL-based expiration.

Wraps a Store in a proxy that caches read-only operations (existence checks,
metadata, listings, content) and automatically invalidates on mutations.

Usage:

```python
from remote_store.ext.cache import cached_store

cached = cached_store(store, ttl=300)
data = cached.read_bytes("key.csv")   # backend call
data = cached.read_bytes("key.csv")   # cache hit
cached.write("key.csv", b"new", overwrite=True)  # invalidates
data = cached.read_bytes("key.csv")   # backend call again
```
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, TypeVar, runtime_checkable

from remote_store._store import Store

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._capabilities import Capability
    from remote_store._models import FileInfo, FolderInfo
    from remote_store._types import WritableContent

T = TypeVar("T")

log = logging.getLogger(__name__)

__all__ = [
    "CacheBackend",
    "CacheStats",
    "CachedStore",
    "MemoryCache",
    "cached_store",
]

# ---------------------------------------------------------------------------
# Sentinel for cache misses
# ---------------------------------------------------------------------------

_MISSING = object()

# ---------------------------------------------------------------------------
# Listing operation prefixes (cleared on any mutation)
# ---------------------------------------------------------------------------

_LISTING_PREFIXES = frozenset({"iter_children", "list_files", "list_folders", "glob", "get_folder_info"})

# Per-path operation prefixes
_PATH_PREFIXES = frozenset({"exists", "is_file", "is_folder", "read_bytes", "get_file_info"})

# ---------------------------------------------------------------------------
# CacheStats
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CacheStats:
    """Snapshot of cache hit/miss statistics."""

    hits: int
    misses: int
    size: int


# ---------------------------------------------------------------------------
# CacheBackend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CacheBackend(Protocol):
    """Protocol for pluggable cache backends (CACHE-001).

    Implement this protocol to provide a custom cache backend to
    ``cached_store(store, cache_backend=my_backend)``. The default implementation
    is ``MemoryCache``.
    """

    def get(self, key: tuple[str, ...]) -> Any:
        """Return the cached value, or raise ``KeyError`` on a cache miss."""
        ...

    def set(self, key: tuple[str, ...], value: Any, ttl: float) -> None:
        """Store *value* under *key* with a time-to-live in seconds."""
        ...

    def delete(self, key: tuple[str, ...]) -> None:
        """Remove *key* from the cache (no-op if absent)."""
        ...

    def clear(self) -> None:
        """Remove all entries from the cache."""
        ...

    def clear_prefix(self, prefix: str) -> None:
        """Remove all entries whose first key component matches *prefix*."""
        ...

    def size(self) -> int:
        """Return the number of entries currently in the cache."""
        ...


# ---------------------------------------------------------------------------
# MemoryCache
# ---------------------------------------------------------------------------


class MemoryCache:
    """Thread-safe in-memory cache backend with lazy TTL eviction.

    Entries are stored as ``{key: (value, expiry)}`` where *expiry* is a
    ``time.monotonic()`` deadline.

    When *max_entries* is set, the cache evicts the least-recently-used
    entry when the limit is exceeded (LRU eviction).  Without a bound,
    metadata entries (``exists``, ``is_file``, listings) for many distinct
    paths can grow without limit during the TTL window.
    """

    def __init__(self, *, max_entries: int | None = None) -> None:
        if max_entries is not None and max_entries <= 0:
            msg = f"max_entries must be positive, got {max_entries}"
            raise ValueError(msg)
        self._data: dict[tuple[str, ...], tuple[Any, float]] = {}
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def get(self, key: tuple[str, ...]) -> Any:
        """Return cached value or raise ``KeyError`` on miss/expiry."""
        with self._lock:
            entry = self._data.get(key, None)
            if entry is None:
                raise KeyError(key)
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._data[key]
                raise KeyError(key)
            # LRU: move to end so least-recently-used is at the front.
            if self._max_entries is not None:
                del self._data[key]
                self._data[key] = (value, expiry)
            return value

    def set(self, key: tuple[str, ...], value: Any, ttl: float) -> None:
        """Store *value* with a TTL in seconds."""
        expiry = time.monotonic() + ttl
        with self._lock:
            if key in self._data:
                # Update existing -- del + re-insert to move to end for LRU.
                # Plain __setitem__ on an existing key does NOT change
                # insertion order in CPython 3.7+ dicts.
                del self._data[key]
                self._data[key] = (value, expiry)
            else:
                self._data[key] = (value, expiry)
                # Evict LRU entries if over limit.
                if self._max_entries is not None:
                    while len(self._data) > self._max_entries:
                        self._data.pop(next(iter(self._data)))

    def delete(self, key: tuple[str, ...]) -> None:
        """Remove a single entry (no-op if absent)."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._data.clear()

    def clear_prefix(self, prefix: str) -> None:
        """Remove all entries whose first key element equals *prefix*."""
        now = time.monotonic()
        with self._lock:
            self._data = {k: v for k, v in self._data.items() if k[0] != prefix and v[1] > now}

    def clear_prefixes(self, prefixes: frozenset[str]) -> None:
        """Remove all entries whose first key element is in *prefixes*.

        Single dict rebuild instead of one per prefix — O(n) vs O(k*n).
        """
        now = time.monotonic()
        with self._lock:
            self._data = {k: v for k, v in self._data.items() if k[0] not in prefixes and v[1] > now}

    def size(self) -> int:
        """Return count of non-expired entries."""
        now = time.monotonic()
        with self._lock:
            # Lazy cleanup during size check
            self._data = {k: v for k, v in self._data.items() if v[1] > now}
            return len(self._data)


# ---------------------------------------------------------------------------
# CachedStore proxy
# ---------------------------------------------------------------------------


class CachedStore(Store):
    """Proxy Store that caches read operations with TTL-based expiration.

    All ``Store`` methods are delegated to the inner store. Read-only
    methods use the cache; mutating methods invalidate affected entries.
    Only methods with additional behavior (``invalidate``, ``clear_cache``,
    ``ping``, ``close``, ``child``) are documented individually below.

    Do not construct directly -- use ``cached_store()``.
    """

    _inner: Store
    _cache: CacheBackend
    _ttl: float
    _max_content_size: int | None
    _hits: int
    _misses: int

    def __init__(
        self,
        inner: Store,
        *,
        ttl: float,
        max_content_size: int | None,
        max_entries: int | None,
        cache_backend: CacheBackend | None,
    ) -> None:
        # Bypass Store.__init__ -- delegate everything to inner.
        self._inner = inner
        self._cache = cache_backend if cache_backend is not None else MemoryCache(max_entries=max_entries)
        self._ttl = ttl
        self._max_content_size = max_content_size
        self._hits = 0
        self._misses = 0
        self._stats_lock = threading.Lock()
        # Coupling: access private state so inherited helpers work if someone
        # bypasses our overrides.  If Store's internals change, this breaks --
        # the drift-protection test (CACHE-011) covers method/property surface
        # but not these private attributes.
        self._backend = inner._backend
        self._root = inner._root
        self._owns_backend = False

    # region: properties

    @property
    def inner(self) -> Store:
        """The wrapped Store instance."""
        return self._inner

    @property
    def stats(self) -> CacheStats:
        """Snapshot of cache hit/miss statistics."""
        with self._stats_lock:
            h, m = self._hits, self._misses
        # Read size outside _stats_lock to avoid blocking concurrent
        # _cache_get calls while MemoryCache.size() rebuilds the dict.
        return CacheStats(hits=h, misses=m, size=self._cache.size())

    # endregion

    # region: public cache-management methods

    def invalidate(self, path: str) -> None:
        """Remove all cached entries for *path*."""
        self._invalidate_path(path)

    def clear_cache(self) -> None:
        """Remove all cached entries."""
        self._cache.clear()

    # endregion

    # region: helpers

    def _cache_get(self, key: tuple[str, ...]) -> Any:
        """Lookup *key* in cache, updating stats."""
        try:
            value = self._cache.get(key)
        except KeyError:
            with self._stats_lock:
                self._misses += 1
            return _MISSING
        with self._stats_lock:
            self._hits += 1
        return value

    def _invalidate_path(self, path: str) -> None:
        """Invalidate per-path entries + all listings."""
        for prefix in _PATH_PREFIXES:
            self._cache.delete((prefix, path))
        self._invalidate_listings()

    def _invalidate_listings(self) -> None:
        """Clear all listing/glob/folder-info cache entries."""
        clear_batch = getattr(self._cache, "clear_prefixes", None)
        if clear_batch is not None:
            clear_batch(_LISTING_PREFIXES)
        else:
            for prefix in _LISTING_PREFIXES:
                self._cache.clear_prefix(prefix)

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return f"CachedStore(inner={self._inner!r}, ttl={self._ttl})"

    # endregion

    # region: public method overrides -- cached operations

    def exists(self, path: str) -> bool:
        key = ("exists", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.exists(path)
        self._cache.set(key, result, self._ttl)
        return result

    def is_file(self, path: str) -> bool:
        key = ("is_file", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.is_file(path)
        self._cache.set(key, result, self._ttl)
        return result

    def is_folder(self, path: str) -> bool:
        key = ("is_folder", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.is_folder(path)
        self._cache.set(key, result, self._ttl)
        return result

    def read_bytes(self, path: str) -> bytes:
        key = ("read_bytes", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.read_bytes(path)
        if self._max_content_size is None or len(result) <= self._max_content_size:
            self._cache.set(key, result, self._ttl)
        return result

    def get_file_info(self, path: str) -> FileInfo:
        key = ("get_file_info", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.get_file_info(path)
        self._cache.set(key, result, self._ttl)
        return result

    def get_folder_info(self, path: str) -> FolderInfo:
        key = ("get_folder_info", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[no-any-return]
        result = self._inner.get_folder_info(path)
        self._cache.set(key, result, self._ttl)
        return result

    def iter_children(self, path: str) -> Iterator[FileInfo | str]:
        key = ("iter_children", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.iter_children(path))
        self._cache.set(key, result, self._ttl)
        return iter(result)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        pattern: str | None = None,
    ) -> Iterator[FileInfo]:
        pattern_key = pattern if pattern is not None else "\x00"
        key = ("list_files", path, str(recursive), pattern_key)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.list_files(path, recursive=recursive, pattern=pattern))
        self._cache.set(key, result, self._ttl)
        return iter(result)

    def list_folders(self, path: str) -> Iterator[str]:
        key = ("list_folders", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.list_folders(path))
        self._cache.set(key, result, self._ttl)
        return iter(result)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        key = ("glob", pattern)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.glob(pattern))
        self._cache.set(key, result, self._ttl)
        return iter(result)

    # endregion

    # region: public method overrides -- non-cached (direct delegation)

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        return self.read_bytes(path).decode(encoding, errors)

    def read(self, path: str) -> BinaryIO:
        return self._inner.read(path)

    def ping(self) -> None:  # noqa: D401
        """Delegate ping to inner store (not cached)."""
        self._inner.ping()

    def close(self) -> None:  # noqa: D401
        """Delegate close to inner store."""
        self._inner.close()

    def child(self, subpath: str) -> Store:
        log.debug("CachedStore.child(%r) returns an unwrapped Store (no caching)", subpath)
        return self._inner.child(subpath)

    def to_key(self, path: str) -> str:
        return self._inner.to_key(path)

    def unwrap(self, type_hint: type[T]) -> T:
        return self._inner.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        return self._inner.native_path(key)

    def supports(self, capability: Capability) -> bool:
        return self._inner.supports(capability)

    # endregion

    # region: public method overrides -- mutating (invalidate + delegate)

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self._inner.write(path, content, overwrite=overwrite)
        self._invalidate_path(path)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self._inner.write_atomic(path, content, overwrite=overwrite)
        self._invalidate_path(path)

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        with self._inner.open_atomic(path, overwrite=overwrite) as f:
            yield f
        # Invalidate only on successful exit (exception skips this line).
        self._invalidate_path(path)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._inner.delete(path, missing_ok=missing_ok)
        self._invalidate_path(path)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._inner.delete_folder(path, recursive=recursive, missing_ok=missing_ok)
        # Folder deletion can affect any cached path -- full clear.
        self._cache.clear()

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.move(src, dst, overwrite=overwrite)
        self._invalidate_path(src)
        self._invalidate_path(dst)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.copy(src, dst, overwrite=overwrite)
        # Source is unchanged, only invalidate destination + listings.
        self._invalidate_path(dst)

    # endregion


# ---------------------------------------------------------------------------
# cached_store() factory
# ---------------------------------------------------------------------------


def cached_store(
    store: Store,
    *,
    ttl: float = 300.0,
    max_content_size: int | None = None,
    max_entries: int | None = None,
    cache_backend: CacheBackend | None = None,
) -> CachedStore:
    """Wrap a Store with read-through caching.

    :param store: The Store to wrap.
    :param ttl: Time-to-live in seconds for cache entries (default 300).
    :param max_content_size: Maximum byte length for ``read_bytes`` caching.
        Files larger than this are returned without caching. ``None`` means
        unlimited.
    :param max_entries: Maximum number of cache entries. When exceeded, the
        least-recently-used entry is evicted. ``None`` means no limit.
        Ignored when *cache_backend* is provided.
    :param cache_backend: Optional custom cache. When ``None``, a
        :class:`MemoryCache` is created.
    :returns: A :class:`CachedStore` proxy.
    """
    if ttl <= 0:
        msg = f"ttl must be positive, got {ttl}"
        raise ValueError(msg)
    if max_content_size is not None and max_content_size <= 0:
        msg = f"max_content_size must be positive, got {max_content_size}"
        raise ValueError(msg)
    return CachedStore(
        store,
        ttl=ttl,
        max_content_size=max_content_size,
        max_entries=max_entries,
        cache_backend=cache_backend,
    )
