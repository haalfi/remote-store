"""Store-level caching middleware with TTL-based expiration.

Wraps a Store in a proxy that caches read-only operations (existence checks,
metadata, listings, content) and automatically invalidates on mutations.

!!! example

    ```python
    from remote_store.ext.cache import cache

    cached = cache(store, ttl=300)
    data = cached.read_bytes("key.csv")   # backend call
    data = cached.read_bytes("key.csv")   # cache hit
    cached.write("key.csv", b"new", overwrite=True)  # invalidates
    data = cached.read_bytes("key.csv")   # backend call again
    ```
"""

from __future__ import annotations

import contextlib
import dataclasses
import threading
import time
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, cast, runtime_checkable

from remote_store import FileInfo, FolderInfo, ProxyStore  # noqa: TCH003 — runtime ref needed for CodeQL

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._models import FolderEntry, WriteResult
    from remote_store._store import Store
    from remote_store._types import WritableContent

__all__ = [
    "CacheBackend",
    "CacheStats",
    "CachedStore",
    "MemoryCache",
    "cache",
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
    """Protocol for pluggable cache backends.

    Implement this protocol to provide a custom cache backend to
    ``cache(store, cache_backend=my_backend)``. The default implementation
    is ``MemoryCache``.
    """

    def get(self, key: tuple[str, ...]) -> Any:
        """Return the cached value, or raise ``KeyError`` on a cache miss."""

    def set(self, key: tuple[str, ...], value: Any, ttl: float) -> None:
        """Store *value* under *key* with a time-to-live in seconds."""

    def delete(self, key: tuple[str, ...]) -> None:
        """Remove *key* from the cache (no-op if absent)."""

    def clear(self) -> None:
        """Remove all entries from the cache."""

    def clear_prefix(self, prefix: str) -> None:
        """Remove all entries whose first key component matches *prefix*."""

    def size(self) -> int:
        """Return the number of entries currently in the cache."""


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
            return sum(1 for v in self._data.values() if v[1] > now)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _delete_path_and_ancestors(cache: CacheBackend, path: str) -> None:
    """Delete per-path cache entries for *path* and all ancestor directories.

    Writing ``dir/file.txt`` implicitly creates ``dir``, so cached
    ``exists`` / ``is_folder`` / ``is_file`` entries for ``dir`` must
    also be invalidated.
    """
    for op in _PATH_PREFIXES:
        cache.delete((op, path))
    parts = path.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        for op in _PATH_PREFIXES:
            cache.delete((op, ancestor))


# ---------------------------------------------------------------------------
# CachedStore proxy
# ---------------------------------------------------------------------------


class CachedStore(ProxyStore):
    """Proxy Store that caches read operations with TTL-based expiration.

    All ``Store`` methods are delegated to the inner store. Read-only
    methods use the cache; mutating methods invalidate affected entries.
    Only methods with additional behavior (``invalidate``, ``clear_cache``,
    ``ping``, ``close``, ``child``) are documented individually below.

    Do not construct directly -- use ``cache()``.
    """

    _cache: CacheBackend
    _ttl: float
    _max_content_size: int | None
    _max_listing_size: int | None
    _max_entries: int | None
    _prefix: str
    _hits: int
    _misses: int

    def __init__(
        self,
        inner: Store,
        *,
        ttl: float,
        max_content_size: int | None,
        max_listing_size: int | None,
        max_entries: int | None,
        cache_backend: CacheBackend | None,
        _prefix: str = "",
    ) -> None:
        super().__init__(inner)
        self._cache = cache_backend if cache_backend is not None else MemoryCache(max_entries=max_entries)
        self._ttl = ttl
        self._max_content_size = max_content_size
        self._max_listing_size = max_listing_size
        self._max_entries = max_entries
        self._prefix = _prefix
        self._hits = 0
        self._misses = 0
        self._stats_lock = threading.Lock()

    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        assert isinstance(other, CachedStore)
        return (
            self._inner == other._inner
            and self._cache is other._cache
            and self._ttl == other._ttl
            and self._max_content_size == other._max_content_size
            and self._max_listing_size == other._max_listing_size
            and self._max_entries == other._max_entries
            and self._prefix == other._prefix
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._inner,
                id(self._cache),
                self._ttl,
                self._max_content_size,
                self._max_listing_size,
                self._max_entries,
                self._prefix,
            )
        )

    # region: properties

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
        """Remove all cached entries for *path* and its ancestor directories."""
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
        """Invalidate per-path entries for path, its ancestors, and all listings."""
        _delete_path_and_ancestors(self._cache, path)
        # BUG-138: if this is a child store, also invalidate the parent's
        # fully-qualified key for the same path in the shared cache.
        if self._prefix:
            _delete_path_and_ancestors(self._cache, f"{self._prefix}/{path}")
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
        parts = [f"inner={self._inner!r}", f"ttl={self._ttl}"]
        if self._max_content_size is not None:
            parts.append(f"max_content_size={self._max_content_size}")
        if self._max_listing_size is not None:
            parts.append(f"max_listing_size={self._max_listing_size}")
        return f"CachedStore({', '.join(parts)})"

    # endregion

    # region: public method overrides -- cached operations

    def exists(self, path: str) -> bool:
        key = ("exists", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(bool, cached)  # noqa: TC006
        result = self._inner.exists(path)
        self._cache.set(key, result, self._ttl)
        return result

    def is_file(self, path: str) -> bool:
        key = ("is_file", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(bool, cached)  # noqa: TC006
        result = self._inner.is_file(path)
        self._cache.set(key, result, self._ttl)
        return result

    def is_folder(self, path: str) -> bool:
        key = ("is_folder", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(bool, cached)  # noqa: TC006
        result = self._inner.is_folder(path)
        self._cache.set(key, result, self._ttl)
        return result

    def read_bytes(self, path: str) -> bytes:
        key = ("read_bytes", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(bytes, cached)  # noqa: TC006
        # Pre-flight: skip caching if file size is known to exceed limit.
        # Uses self._cache.get() directly to avoid polluting hit/miss stats.
        skip_cache = False
        if self._max_content_size is not None:
            with contextlib.suppress(KeyError, AttributeError):
                fi = self._cache.get(("get_file_info", path))
                if fi.size > self._max_content_size:
                    skip_cache = True
        result = self._inner.read_bytes(path)
        if not skip_cache and (self._max_content_size is None or len(result) <= self._max_content_size):
            self._cache.set(key, result, self._ttl)
        return result

    def get_file_info(self, path: str) -> FileInfo:
        key = ("get_file_info", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(FileInfo, cached)  # noqa: TC006
        result = self._inner.get_file_info(path)
        self._cache.set(key, result, self._ttl)
        return result

    def get_folder_info(self, path: str, *, max_depth: int | None = None) -> FolderInfo:
        key = ("get_folder_info", path, str(max_depth))
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return cast(FolderInfo, cached)  # noqa: TC006
        result = self._inner.get_folder_info(path, max_depth=max_depth)
        self._cache.set(key, result, self._ttl)
        return result

    def head(self, path: str) -> WriteResult:
        return self._inner.head(path)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        key = ("iter_children", path)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.iter_children(path))
        if self._max_listing_size is None or len(result) <= self._max_listing_size:
            self._cache.set(key, result, self._ttl)
        return iter(result)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        pattern: str | None = None,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        pattern_key = pattern if pattern is not None else "\x00"
        depth_key = str(max_depth) if max_depth is not None else "\x00"
        # When max_depth is set, recursive is ignored by Store -- normalize key
        recursive_key = "\x00" if max_depth is not None else str(recursive)
        key = ("list_files", path, recursive_key, pattern_key, depth_key)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.list_files(path, recursive=recursive, pattern=pattern, max_depth=max_depth))
        if self._max_listing_size is None or len(result) <= self._max_listing_size:
            self._cache.set(key, result, self._ttl)
        return iter(result)

    def list_folders(
        self, path: str, *, pattern: str | None = None, max_depth: int | None = None
    ) -> Iterator[FolderEntry]:
        pattern_key = pattern if pattern is not None else "\x00"
        depth_key = str(max_depth) if max_depth is not None else "\x00"
        key = ("list_folders", path, pattern_key, depth_key)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.list_folders(path, pattern=pattern, max_depth=max_depth))
        if self._max_listing_size is None or len(result) <= self._max_listing_size:
            self._cache.set(key, result, self._ttl)
        return iter(result)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        key = ("glob", pattern)
        cached = self._cache_get(key)
        if cached is not _MISSING:
            return iter(cached)
        result = tuple(self._inner.glob(pattern))
        if self._max_listing_size is None or len(result) <= self._max_listing_size:
            self._cache.set(key, result, self._ttl)
        return iter(result)

    # endregion

    # region: public method overrides -- non-cached (direct delegation)

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        return self.read_bytes(path).decode(encoding, errors)

    def _wrap_child(self, inner_child: Store) -> Store:
        # Derive the child's subpath by comparing store roots, then build
        # the fully-qualified prefix for cross-store cache invalidation.
        parent_root = self._inner._root or ""
        child_root = inner_child._root or ""
        if parent_root:
            assert child_root.startswith(parent_root + "/"), (
                f"child root {child_root!r} does not start with parent root {parent_root!r}"
            )
        subpath = child_root[len(parent_root) + 1 :] if parent_root else child_root
        prefix = f"{self._prefix}/{subpath}" if self._prefix else subpath
        return CachedStore(
            inner_child,
            ttl=self._ttl,
            max_content_size=self._max_content_size,
            max_listing_size=self._max_listing_size,
            max_entries=self._max_entries,
            cache_backend=self._cache,
            _prefix=prefix,
        )

    # endregion

    # region: public method overrides -- mutating (invalidate + delegate)

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        result = self._inner.write(path, content, overwrite=overwrite, metadata=metadata)
        self._invalidate_path(path)
        return result

    def write_text(
        self,
        path: str,
        text: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        result = self._inner.write_text(path, text, encoding=encoding, overwrite=overwrite, metadata=metadata)
        self._invalidate_path(path)
        return result

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        result = self._inner.write_atomic(path, content, overwrite=overwrite, metadata=metadata)
        self._invalidate_path(path)
        return result

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
        # When moving a path (file or folder), invalidate the entire cache
        # because any nested paths under src are now under dst.
        self._cache.clear()

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.copy(src, dst, overwrite=overwrite)
        # When copying, destination paths (file or nested paths in a folder)
        # can change. Clear entire cache to ensure no stale entries remain.
        self._cache.clear()

    # endregion


# ---------------------------------------------------------------------------
# cache() factory
# ---------------------------------------------------------------------------


def cache(
    store: Store,
    *,
    ttl: float = 300.0,
    max_content_size: int | None = None,
    max_listing_size: int | None = None,
    max_entries: int | None = None,
    cache_backend: CacheBackend | None = None,
) -> CachedStore:
    """Wrap a Store with read-through caching.

    Args:
        store: The Store to wrap.
        ttl: Time-to-live in seconds for cache entries (default 300).
        max_content_size: Maximum byte length for ``read_bytes`` caching.
            Files larger than this are returned without caching. ``None`` means
            unlimited.
        max_listing_size: Maximum number of items in a listing result
            (``iter_children``, ``list_files``, ``list_folders``, ``glob``)
            for caching. Listings with more items than this are returned
            without caching. ``None`` means unlimited.
        max_entries: Maximum number of cache entries. When exceeded, the
            least-recently-used entry is evicted. ``None`` means no limit.
            Ignored when *cache_backend* is provided.
        cache_backend: Optional custom cache. When ``None``, a
            ``MemoryCache`` is created.

    Returns:
        A ``CachedStore`` proxy.

    Raises:
        ValueError: If *ttl*, *max_content_size*, or *max_listing_size*
            is not positive when set.
    """
    if ttl <= 0:
        msg = f"ttl must be positive, got {ttl}"
        raise ValueError(msg)
    if max_content_size is not None and max_content_size <= 0:
        msg = f"max_content_size must be positive, got {max_content_size}"
        raise ValueError(msg)
    if max_listing_size is not None and max_listing_size <= 0:
        msg = f"max_listing_size must be positive, got {max_listing_size}"
        raise ValueError(msg)
    return CachedStore(
        store,
        ttl=ttl,
        max_content_size=max_content_size,
        max_listing_size=max_listing_size,
        max_entries=max_entries,
        cache_backend=cache_backend,
    )
