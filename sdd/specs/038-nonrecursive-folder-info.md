# Non-Recursive `get_folder_info` Optimization

Adds `max_depth` parameter to `Store.get_folder_info()` for controlling
traversal depth, avoiding catastrophic rescanning on large buckets.

**Related:** [Depth-limited listing](037-depth-limited-listing.md), ID-112.

---

## FOLDERINFO-001: get_folder_info(max_depth=N)

**Invariant:** `get_folder_info(path, *, max_depth=None)` accepts an optional
`max_depth` keyword controlling how deep to aggregate file statistics:

- `max_depth=None` (default): full recursive traversal via backend (current
  behavior).
- `max_depth=0`: aggregate only files directly in `path`.
- `max_depth=N` (N > 0): aggregate files up to N folder levels below `path`.

**Validation:** `max_depth < 0` raises `ValueError`.

**Folder existence:** When `max_depth` is set, folder existence is verified via
`is_folder()` before aggregation. If the folder does not exist, `NotFound` is
raised — matching the backend-delegated behavior.

**Implementation:** Store-level computation using `list_files(path,
max_depth=max_depth)`. No Backend ABC change. The aggregation builds a
`FolderInfo` from the yielded `FileInfo` objects (count, total size, latest
`modified_at`).

**Depth examples:**

```
store.get_folder_info("data", max_depth=0)
# Aggregates: data/file_a.csv, data/file_b.csv
# Excludes:   data/raw/file_c.csv

store.get_folder_info("data", max_depth=1)
# Aggregates: data/file_a.csv, data/raw/file_c.csv
# Excludes:   data/raw/2026/file_d.csv
```

---

## FOLDERINFO-002: Proxy / extension pass-through

**Invariant:** `ProxyStore`, `CachedStore`, and `ObservedStore` forward the
`max_depth` parameter to the inner store's `get_folder_info()`.

`CachedStore` includes `max_depth` in its cache key so that
`get_folder_info("x")` and `get_folder_info("x", max_depth=0)` are cached
independently.
