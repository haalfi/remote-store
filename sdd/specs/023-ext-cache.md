# ext.cache - Store-Level Caching Middleware Specification

## Overview

`ext.cache` provides a Store-wrapping proxy that caches the results of
read-only operations with configurable TTL-based expiration, reducing
backend round-trips for read-heavy or metadata-heavy workloads. Mutating
operations automatically invalidate affected cache entries.

**Module:** `src/remote_store/ext/cache.py`
**Dependencies:** None (pure Python, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API),
[019-ext-observe.md](019-ext-observe.md) (proxy pattern), ADR-0010, ID-025.

---

## Cache Backend Protocol

### CACHE-001: CacheBackend Protocol

**Invariant:** `CacheBackend` is a `typing.Protocol` with the following
methods:

```python
class CacheBackend(Protocol):
    def get(self, key: tuple[str, ...]) -> Any: ...
    def set(self, key: tuple[str, ...], value: Any, ttl: float) -> None: ...
    def delete(self, key: tuple[str, ...]) -> None: ...
    def clear(self) -> None: ...
    def clear_prefix(self, prefix: str) -> None: ...
    def size(self) -> int: ...
```

- `get` returns the cached value or raises `KeyError` on miss or expiry.
- `set` stores a value with the given TTL in seconds.
- `delete` removes a single entry (no-op if absent).
- `clear` removes all entries.
- `clear_prefix` removes all entries whose first key element equals `prefix`.
- `size` returns the number of live (non-expired) entries.

### CACHE-002: MemoryCache Default Implementation

**Invariant:** `MemoryCache` implements `CacheBackend` using a plain
`dict[tuple[str, ...], tuple[Any, float]]` where the second element is
the expiry timestamp from `time.monotonic()`.

**Properties:**
- Thread-safe via `threading.Lock`.
- Lazy eviction: expired entries are removed on `get` (miss path) and
  during `clear_prefix` / `size` traversals. No background reaper.
- Optional `max_entries: int | None` parameter. When set, least-recently-used
  entries are evicted on `set` when the count exceeds the limit. When `None`
  (default), entries are only bounded by TTL expiry.
- `max_entries` must be positive; `ValueError` is raised on `<= 0`.

---

## Factory Function

### CACHE-003: cache() Signature

**Invariant:**

```python
def cache(
    store: Store,
    *,
    ttl: float = 300.0,
    max_content_size: int | None = None,
    max_listing_size: int | None = None,
    max_entries: int | None = None,
    cache_backend: CacheBackend | None = None,
) -> CachedStore: ...
```

**Parameters:**
- `store`: The Store to wrap.
- `ttl`: Time-to-live in seconds for cache entries. Default 300 (5 min).
  Must be positive; `ValueError` on `<= 0`.
- `max_content_size`: Maximum byte length for `read_bytes` caching.
  Files larger than this are returned without caching. `None` means
  unlimited. Must be positive when set; `ValueError` on `<= 0`.
- `max_listing_size`: Maximum item count for listing caches
  (`iter_children`, `list_files`, `list_folders`, `glob`). Listings
  with more items than this are returned without caching. `None` means
  unlimited. Must be positive when set; `ValueError` on `<= 0`.
- `max_entries`: Maximum number of cache entries for the default
  `MemoryCache`. Least-recently-used entries are evicted when exceeded.
  `None` means no limit. Ignored when `cache_backend` is provided.
- `cache_backend`: Optional custom cache backend. When `None`, a
  `MemoryCache` is created.

**Postconditions:**
- Returns a `CachedStore` instance wrapping `store`.
- `isinstance(result, Store)` is `True`.

---

## Proxy

### CACHE-004: CachedStore Proxy

**Invariant:** `CachedStore` is a subclass of `Store` that explicitly
overrides every public method. It bypasses `Store.__init__` and
delegates to the inner store, following the `ObservedStore` proxy
pattern (ADR-0010).

**Properties:**
- `inner: Store` — read-only property returning the wrapped store.
- `stats: CacheStats` — read-only property returning current statistics.

**Public cache-management methods:**
- `invalidate(path: str) -> None` — remove all cached entries for
  the given path and its ancestor directories.
- `clear_cache() -> None` — remove all cached entries.

### CACHE-005: CacheStats Dataclass

**Invariant:** `CacheStats` is a frozen dataclass:

```python
@dataclasses.dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    size: int
```

- `hits`: number of cache hits since creation.
- `misses`: number of cache misses since creation.
- `size`: current number of cached entries.

---

## Cacheable Operations

### CACHE-006: Cached Read Operations

**Invariant:** The following operations cache their results on success:

| Operation | Cache Key | Cached Value |
|-----------|-----------|--------------|
| `exists(path)` | `("exists", path)` | `bool` |
| `is_file(path)` | `("is_file", path)` | `bool` |
| `is_folder(path)` | `("is_folder", path)` | `bool` |
| `read_bytes(path)` | `("read_bytes", path)` | `bytes` |
| `get_file_info(path)` | `("get_file_info", path)` | `FileInfo` |
| `get_folder_info(path, max_depth)` | `("get_folder_info", path, str(max_depth))` | `FolderInfo` |
| `iter_children(path)` | `("iter_children", path)` | `tuple[FileInfo \| FolderEntry, ...]` |
| `list_files(path, recursive, pattern, max_depth)` | `("list_files", path, recursive_key, pattern_key, depth_key)` | `tuple[FileInfo, ...]` |
| `list_folders(path, max_depth)` | `("list_folders", path, depth_key)` | `tuple[FolderEntry, ...]` |
| `glob(pattern)` | `("glob", pattern)` | `tuple[FileInfo, ...]` |

**Postconditions:**
- Iterator-returning methods (`iter_children`, `list_files`, `list_folders`, `glob`)
  materialize results into a tuple on first call and return
  `iter(cached_tuple)` on cache hits.
- Only successful results are cached. Exceptions (e.g., `NotFound`) are
  never cached — subsequent calls retry the backend.
- `read_bytes`: if `max_content_size` is set and `len(result) >
  max_content_size`, the result is returned but not cached.
- Listing methods (`iter_children`, `list_files`, `list_folders`, `glob`):
  if `max_listing_size` is set and `len(result) > max_listing_size`, the
  result is returned but not cached.

### CACHE-007: Non-Cached Operations

**Invariant:** The following operations always delegate directly to the
inner store without caching:

- `read(path)` — returns `BinaryIO` (not serializable/reusable).
- `read_text(path)` — delegates to `self.read_bytes()` (uses cached
  `read_bytes` result). No separate cache key. See RTXT-005.
- `head(path)` — always live; sidecar metadata is not cached.
- `close()`, `child()`, `to_key()`, `unwrap()`, `native_path()`,
  `supports()` — no backend I/O worth caching.

---

## Invalidation

### CACHE-008: Write Invalidation

**Invariant:** `write()`, `write_text()`, `write_atomic()`, and `open_atomic()` (on
successful context exit) return a `WriteResult` forwarded from the inner store and invalidate:

1. All per-path cache entries for the written path **and every ancestor
   directory** of that path (all operation prefixes: `exists`, `is_file`,
   `is_folder`, `read_bytes`, `get_file_info`). Writing a nested path
   (e.g. `dir/file.txt`) implicitly creates parent directories, so their
   cached metadata must also be cleared.
2. All listing cache entries (`iter_children`, `list_files`, `list_folders`,
   `glob`, `get_folder_info`).

### CACHE-009: Delete Invalidation

**Invariant:** `delete()` invalidates:

1. All per-path cache entries for the deleted path **and every ancestor
   directory** of that path. After deleting the last file in a directory
   the ancestor may become non-existent; stale `True` entries must be
   cleared.
2. All listing cache entries.

`delete_folder()` invalidates all cache entries (full clear), since
recursive folder deletion may affect any cached path.

### CACHE-010: Move/Copy Invalidation

**Invariant:**
- `move(src, dst)` clears the entire cache. When moving a path (file or
  folder), all nested paths are relocated, requiring full invalidation to
  prevent stale entries for paths like `dst/file.txt`. Consistent with
  `delete_folder()` safety strategy.
- `copy(src, dst)` clears the entire cache. When copying to an existing
  destination with `overwrite=True`, nested paths may be overwritten,
  requiring full invalidation. Full cache clear ensures no stale entries
  persist for affected paths.

---

## Safety

### CACHE-011: Drift-Protection Test

**Invariant:** The test suite includes a test that asserts `CachedStore`
overrides every public method of `Store` (same pattern as OBS-007).

### CACHE-012: Thread Safety

**Invariant:** `MemoryCache` is thread-safe via `threading.Lock`.
`CachedStore` hit/miss counters use `threading.Lock` for atomic updates.
`CachedStore` is safe for concurrent use from multiple threads (e.g.,
with `batch_exists(concurrent=True)`).

### CACHE-013: Error Semantics

**Invariant:** Exceptions from the inner store are never cached. They
propagate to the caller unchanged. If `exists()` returns `False`, that
result IS cached (it is a valid return value, not an error).

### CACHE-014: Stale Data Contract

**Invariant:** The cache does not detect external mutations (writes from
other processes or Store instances sharing the same backend). Users must
either set an appropriate TTL or call `invalidate()` / `clear_cache()`
manually when external mutations are expected. This limitation is
documented in the user guide.

### CACHE-016: Child Cache Sharing

**Invariant:** `CachedStore.child(subpath)` returns a `CachedStore` that
shares the parent's cache backend. The child tracks a path prefix
derived from `subpath` so that mutations through the child also
invalidate the parent's fully-qualified cache keys.

**Postconditions:**
- `child._cache is parent._cache` — the same `CacheBackend` instance.
- When the child calls `_invalidate_path(path)`, it invalidates both
  `(op, path)` (the child-local key) and `(op, prefix/path)` (the
  parent-visible key) for all per-path operation prefixes.
- Ancestor invalidation (CACHE-008/CACHE-009) applies to both the
  child-local and parent-visible paths.
- Nesting is composable: `cache.child("a").child("b")` produces prefix
  `"a/b"`, so a write to `"file.txt"` invalidates `"file.txt"`,
  `"b/file.txt"`, and `"a/b/file.txt"` in the shared cache.

### CACHE-015: Lifecycle

**Invariant:** `CachedStore.close()` delegates to the inner store's
`close()`. The cache itself has no resources requiring cleanup. Follows
the same no-lifecycle-ownership principle as `ObservedStore` (OBS-010).
