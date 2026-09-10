# ext.cache

## cache

Store-level caching middleware with TTL-based expiration.

Wraps a Store in a proxy that caches read-only operations (existence checks, metadata, listings, content) and automatically invalidates on mutations.

Example

```
from remote_store.ext.cache import cache

cached = cache(store, ttl=300)
data = cached.read_bytes("key.csv")   # backend call
data = cached.read_bytes("key.csv")   # cache hit
cached.write("key.csv", b"new", overwrite=True)  # invalidates
data = cached.read_bytes("key.csv")   # backend call again
```

### CacheStats

```
CacheStats(hits: int, misses: int, size: int)
```

Snapshot of cache hit/miss statistics.

### CacheBackend

Bases: `Protocol`

Protocol for pluggable cache backends.

Implement this protocol to provide a custom cache backend to `cache(store, cache_backend=my_backend)`. The default implementation is `MemoryCache`.

#### get

```
get(key: tuple[str, ...]) -> Any
```

Return the cached value, or raise `KeyError` on a cache miss.

#### set

```
set(key: tuple[str, ...], value: Any, ttl: float) -> None
```

Store *value* under *key* with a time-to-live in seconds.

#### delete

```
delete(key: tuple[str, ...]) -> None
```

Remove *key* from the cache (no-op if absent).

#### clear

```
clear() -> None
```

Remove all entries from the cache.

#### clear_prefix

```
clear_prefix(prefix: str) -> None
```

Remove all entries whose first key component matches *prefix*.

#### size

```
size() -> int
```

Return the number of entries currently in the cache.

### MemoryCache

```
MemoryCache(*, max_entries: int | None = None)
```

Thread-safe in-memory cache backend with lazy TTL eviction.

Entries are stored as `{key: (value, expiry)}` where *expiry* is a `time.monotonic()` deadline.

When *max_entries* is set, the cache evicts the least-recently-used entry when the limit is exceeded (LRU eviction). Without a bound, metadata entries (`exists`, `is_file`, listings) for many distinct paths can grow without limit during the TTL window.

#### get

```
get(key: tuple[str, ...]) -> Any
```

Return cached value or raise `KeyError` on miss/expiry.

#### set

```
set(key: tuple[str, ...], value: Any, ttl: float) -> None
```

Store *value* with a TTL in seconds.

#### delete

```
delete(key: tuple[str, ...]) -> None
```

Remove a single entry (no-op if absent).

#### clear

```
clear() -> None
```

Remove all entries.

#### clear_prefix

```
clear_prefix(prefix: str) -> None
```

Remove all entries whose first key element equals *prefix*.

#### clear_prefixes

```
clear_prefixes(prefixes: frozenset[str]) -> None
```

Remove all entries whose first key element is in *prefixes*.

Single dict rebuild instead of one per prefix — O(n) vs O(k\*n).

#### size

```
size() -> int
```

Return count of non-expired entries.

### CachedStore

```
CachedStore(
    inner: Store,
    *,
    ttl: float,
    max_content_size: int | None,
    max_listing_size: int | None,
    max_entries: int | None,
    cache_backend: CacheBackend | None,
    _prefix: str = "",
)
```

Bases: `ProxyStore`

Proxy Store that caches read operations with TTL-based expiration.

All `Store` methods are delegated to the inner store. Read-only methods use the cache; mutating methods invalidate affected entries. Only methods with additional behavior (`invalidate`, `clear_cache`, `ping`, `close`, `child`) are documented individually below.

Do not construct directly -- use `cache()`.

#### stats

```
stats: CacheStats
```

Snapshot of cache hit/miss statistics.

#### invalidate

```
invalidate(path: str) -> None
```

Remove all cached entries for *path* and its ancestor directories.

#### clear_cache

```
clear_cache() -> None
```

Remove all cached entries.

### cache

```
cache(
    store: Store,
    *,
    ttl: float = 300.0,
    max_content_size: int | None = None,
    max_listing_size: int | None = None,
    max_entries: int | None = None,
    cache_backend: CacheBackend | None = None,
) -> CachedStore
```

Wrap a Store with read-through caching.

Parameters:

- **`store`** (`Store`) – The Store to wrap.
- **`ttl`** (`float`, default: `300.0` ) – Time-to-live in seconds for cache entries (default 300).
- **`max_content_size`** (`int | None`, default: `None` ) – Maximum byte length for read_bytes caching. Files larger than this are returned without caching. None means unlimited.
- **`max_listing_size`** (`int | None`, default: `None` ) – Maximum number of items in a listing result (iter_children, list_files, list_folders, glob) for caching. Listings with more items than this are returned without caching. None means unlimited.
- **`max_entries`** (`int | None`, default: `None` ) – Maximum number of cache entries. When exceeded, the least-recently-used entry is evicted. None means no limit. Ignored when cache_backend is provided.
- **`cache_backend`** (`CacheBackend | None`, default: `None` ) – Optional custom cache. When None, a MemoryCache is created.

Returns:

- `CachedStore` – A CachedStore proxy.

Raises:

- `ValueError` – If ttl, max_content_size, or max_listing_size is not positive when set.

## See also

- [Cache](https://docs.remotestore.dev/stable/guides/cache/index.md) — guide to Store-level caching with TTL
- [Caching example](https://docs.remotestore.dev/stable/tutorial/examples/caching/index.md) — caching middleware in action
