# Caching Guide

`ext.cache` wraps a Store in a caching proxy that reduces backend
round-trips for read-heavy and metadata-heavy workloads.

## Quick Start

```python
from remote_store import Store, cache
from remote_store.backends import MemoryBackend

store = Store(MemoryBackend())
store.write("config.json", b'{"key": "value"}')

# Wrap with a 5-minute cache
cached = cache(store, ttl=300)

# First call hits the backend
data = cached.read_bytes("config.json")

# Second call returns from cache (no backend I/O)
data = cached.read_bytes("config.json")

# Writes automatically invalidate the cache
cached.write("config.json", b'{"key": "new"}', overwrite=True)

# Next read goes to the backend again
data = cached.read_bytes("config.json")  # b'{"key": "new"}'
```

## What Gets Cached

| Operation | Cached? | Notes |
|-----------|---------|-------|
| `exists()` | Yes | Including `False` results |
| `is_file()` | Yes | |
| `is_folder()` | Yes | |
| `read_bytes()` | Yes | Subject to `max_content_size` |
| `get_file_info()` | Yes | |
| `get_folder_info()` | Yes | |
| `list_files()` | Yes | Materialized on first call; subject to `max_listing_size` |
| `list_folders()` | Yes | Materialized on first call; subject to `max_listing_size` |
| `iter_children()` | Yes | Materialized on first call; subject to `max_listing_size` |
| `glob()` | Yes | Materialized on first call; subject to `max_listing_size` |
| `read()` | — | Returns `BinaryIO` stream |

`read()` is deliberately not cached because it returns a `BinaryIO`
stream that may be lazily consumed. Use `read_bytes()` when you want
cached content reads.

## Automatic Invalidation

Mutating operations automatically invalidate affected cache entries:

- **`write`, `write_atomic`, `open_atomic`** — invalidate the written
  path and all listing/folder caches.
- **`delete`** — invalidate the deleted path and all listings.
- **`delete_folder`** — clear the entire cache (folder deletion can
  affect any cached path).
- **`move`** — invalidate both source and destination paths plus listings.
- **`copy`** — invalidate destination path plus listings.

## Limiting Memory Usage

By default, `read_bytes()` caches files of any size. For workloads with
large files, set `max_content_size` to prevent memory pressure:

```python
# Only cache files up to 1 MB
cached = cache(store, ttl=300, max_content_size=1_048_576)
```

Files larger than the limit are still returned correctly — they just
bypass the cache.

Similarly, listing operations (`list_files`, `list_folders`,
`iter_children`, `glob`) cache their full result set. For stores with
very large directories, set `max_listing_size` to skip caching listings
that exceed a given item count:

```python
# Cache listings up to 500 items; larger ones bypass the cache
cached = cache(store, ttl=300, max_listing_size=500)
```

Both limits can be combined:

```python
cached = cache(store, ttl=300, max_content_size=1_048_576, max_listing_size=500)
```

## Cache Statistics

```python
stats = cached.stats
print(f"Hits: {stats.hits}, Misses: {stats.misses}, Size: {stats.size}")
```

## Manual Invalidation

```python
# Invalidate a specific path
cached.invalidate("config.json")

# Clear the entire cache
cached.clear_cache()
```

## Stale Data

The cache cannot detect writes made by other processes or other Store
instances sharing the same backend. If your workload involves external
mutations, either:

1. Set a short TTL (e.g., `ttl=10`).
2. Call `invalidate(path)` or `clear_cache()` when you know external
   writes occurred.

## Composing with Observability

`CachedStore` composes with `ObservedStore`. The ordering determines
what gets observed:

```python
from remote_store import observe, cache

# Observe only cache misses (actual backend calls)
cached = cache(observe(store, on_read=my_hook), ttl=300)

# Observe all reads including cache hits
observed = observe(cache(store, ttl=300), on_read=my_hook)
```

## Thread Safety

`CachedStore` and `MemoryCache` are thread-safe. They work correctly
with `batch_exists(concurrent=True)` and similar concurrent access
patterns.

## See also

- [API reference](api/extensions/cache.md)
- [Example script](https://github.com/haalfi/remote-store/blob/master/examples/caching.py)
