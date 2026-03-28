# Audit 005 — Laziness & Memory Efficiency

**Date:** 2026-03-28
**Scope:** `src/remote_store/` — all Python source files
**Branch:** `claude/audit-laziness-memory-cIPJr`
**Method:** Full line-by-line read of all 40 source files. Two focus areas:
(1) missed opportunities for lazy evaluation/loading where it would genuinely help,
(2) memory hygiene — unnecessary buffering, patterns that should stream but don't,
objects holding more data than needed.

**Verification:** All findings verified against actual code. Line references are
point-in-time for branch `claude/audit-laziness-memory-cIPJr`.

---

## Summary

| Severity | Count |
|----------|-------|
| High     | 2     |
| Medium   | 6     |
| Low      | 3     |
| **Total**| **11**|

---

## Findings

### H-1 — `_s3_base.py:118` — `list_files(recursive=True)` materialises entire listing into a dict

**File:** `backends/_s3_base.py`, line 118
**Category:** Memory Bloat

```python
results: dict[str, Any] = self._s3fs.find(s3_path, detail=True)
for s3_key, info in results.items():
    ...
    yield self._info_to_fileinfo(info, rel)
```

`s3fs.find()` returns a single `dict` containing every matching object. For a
large S3 prefix (100k+ objects) this dict can consume hundreds of MBs — each
entry carries ETag, size, mtime, storage class, ACL metadata, etc. The
subsequent `yield` is lazy, but the full result is already in memory before the
first item is returned to the caller. s3fs does not offer a streaming variant of
`find()`; the practical fix is to replace recursive `find()` with a paginated
`ls()` loop or `s3fs.walk()`.

---

### H-2 — `_s3_base.py:199` — `get_folder_info` loads all object metadata to compute 3 scalars

**File:** `backends/_s3_base.py`, line 199
**Category:** Memory Bloat

```python
results: dict[str, Any] = self._s3fs.find(s3_path, detail=True)
file_count = 0
total_size = 0
latest_modified: datetime | None = None
for _key, info in results.items():
    if info.get("type") == "file":
        file_count += 1
        total_size += info.get("size", 0) or 0
        ...
```

Identical root cause to H-1. The entire recursive listing is loaded into a dict
while only three scalars are needed (count, size, latest modification time).
For a 1M-object prefix this allocates the same large dict and then discards it
after aggregation.

---

### M-1 — `ext/cache.py:375,395,405,414` — listing caches have no size guard

**File:** `ext/cache.py`, lines 375, 395, 405, 414
**Category:** Memory Bloat

```python
# iter_children (375), list_files (395), list_folders (405), glob (414)
result = tuple(self._inner.list_files(path, recursive=recursive, ...))
self._cache.set(key, result, self._ttl)
return iter(result)
```

`read_bytes` has `max_content_size` to skip caching large files. No equivalent
`max_listing_size` guard exists for listing operations. Materialising to `tuple`
is unavoidable for caching, but a `list_files(recursive=True)` on a store with
100k files caches 100k `FileInfo` objects with no upper bound. `MemoryCache`'s
`max_entries` limits the *number of cache entries*, not the *size of each entry*.

---

### M-2 — `ext/cache.py:347–348` — `read_bytes` reads full content before size check

**File:** `ext/cache.py`, lines 347–348
**Category:** Memory Bloat

```python
result = self._inner.read_bytes(path)          # full read — allocates
if self._max_content_size is None or len(result) <= self._max_content_size:
    self._cache.set(key, result, self._ttl)    # might not cache after all
return result
```

The full byte content is already in memory at the point of the size check. For
files that exceed `max_content_size`, the bytes are loaded, the cache-set is
skipped, and the transient double-reference (caller + cache candidate) is
discarded — but the read itself cannot be avoided because `read_bytes` must
return the content regardless. A pre-flight `get_file_info` size check would
skip the wasted cache-set attempt and avoid the transient double-reference, but
not the read itself.

---

### M-3 — `backends/_memory.py:225–231` — `list_files` holds lock while building full result list

**File:** `backends/_memory.py`, lines 225–231
**Category:** Memory Bloat + Lock Contention

```python
with self._lock:
    node = self._traverse(segments)
    ...
    results = self._collect_files(node, prefix, recursive=recursive, ...)
yield from results  # lock already released here
```

`_collect_files` (line 491) builds a full `list[FileInfo]` under the lock, then
releases it before yielding. Two problems:
(1) the lock is held for the entire traversal — all concurrent writes block;
(2) the full list is allocated in memory before the first item is returned,
so callers that only need the first few items still pay the full traversal cost.

---

### M-4 — `backends/_memory.py:233–248` — `list_folders` builds list comprehension under lock

**File:** `backends/_memory.py`, lines 233–248
**Category:** Memory Bloat + Lock Contention

```python
with self._lock:
    ...
    results = [
        FolderEntry(...)
        for name, child in node.children.items()
        if isinstance(child, _DirNode)
    ]
yield from results
```

Same pattern as M-3: full list assembled under lock, then yielded outside it.

---

### M-5 — `backends/_memory.py:250–273` — `iter_children` builds full list under lock

**File:** `backends/_memory.py`, lines 250–273
**Category:** Memory Bloat + Lock Contention

```python
with self._lock:
    ...
    results: list[FileInfo | FolderEntry] = []
    for name, child in node.children.items():
        ...
        results.append(...)
yield from results
```

Same pattern as M-3 and M-4.

---

### M-6 — `backends/_memory.py:120` — stream write allocates two full copies

**File:** `backends/_memory.py`, line 120
**Category:** Memory Bloat

```python
raw = content if isinstance(content, bytes) else content.read()
...
parent.children[leaf] = _FileEntry(data=bytearray(raw), ...)
```

When `content` is a stream, `content.read()` creates a `bytes` object (first
copy), then `bytearray(raw)` creates a second copy. Peak memory during write is
2× the file size. Accumulating directly into a `bytearray` via chunked reads
would halve the peak.

---

### L-1 — `ext/cache.py:185–206` — `MemoryCache` dict rebuild creates transient 2× memory

**File:** `ext/cache.py`, lines 185–206
**Category:** Memory Bloat (transient)

`clear_prefix()`, `clear_prefixes()`, and `size()` all rebuild `_data` via a dict
comprehension while holding `_lock`. For the duration of the comprehension, both
the old and new dicts coexist. For large caches this is a transient O(n) memory
spike. The `size()` method in particular rebuilds the dict on every call, making
it non-trivial to call frequently (e.g. in monitoring loops).

---

### L-2 — `ext/batch.py:136,282` — concurrent batch materialises full iterable

**File:** `ext/batch.py`, lines 136 and 282
**Category:** Laziness

```python
# _run_batch_concurrent (136)
items_list = list(items)
# _batch_exists_concurrent (282)
paths_list = list(paths)
```

Both concurrent batch helpers materialise the full iterable before submitting
futures. This is necessary because `future_to_key` is a dict comprehension that
requires iterating `items_list` — the iterable must be repeatable. For iterables
that yield 100k+ items this holds all items in memory simultaneously. Sequential
variants (`_run_batch_sequential`, the `{path: store.exists(path) for path in
paths}` dict comprehension) consume items lazily. The difference is undocumented.

---

### L-3 — `backends/_sqlalchemy.py:32–38` — `sqlalchemy` imported at module level

**File:** `backends/_sqlalchemy.py`, lines 32–38
**Category:** Laziness

```python
try:
    import sqlalchemy as sa
    from sqlalchemy import Engine, event
except ImportError as _imp_err:
    raise ImportError(...) from _imp_err
```

`sqlalchemy` is imported at module level. `backends/__init__.py` guards the
import of this module in a `try/except ImportError`, so the library is not loaded
if unavailable. However, when it *is* installed, any import of
`remote_store.backends._sqlalchemy` immediately loads the full `sqlalchemy`
package. Contrast with `_sftp.py` (paramiko deferred to `_connect()`), `_s3.py`
(s3fs deferred to `__init__`), and `_azure.py` (azure SDK deferred to method
bodies). Minor inconsistency; the cost is small since sqlalchemy is explicitly
opt-in.

---

## What is already good

- **Azure `list_files` / `list_folders` / `iter_children` / `get_folder_info`** —
  all use SDK iterators; results are streamed lazily, only scalars accumulated.
- **`ext/transfer.py`** — downloads chunked at 1 MiB; full file never in memory.
- **`_stream.py`** — `_ErrorMappingStream` is a thin zero-copy wrapper.
- **`backends/__init__.py`** — heavy backends guarded with `try/except ImportError`.
- **SFTP / Azure / s3fs SDK imports** — deferred to `__init__` or method bodies.
- **`ext/` optional modules** (arrow, otel, pydantic, yaml, dagster) — not
  imported in top-level `__init__.py` (ADR-0013).
- **`_store.py` `get_folder_info` with `max_depth`** — iterates `list_files`
  lazily, accumulating only 3 scalars.

---

## Follow-up

See backlog item **ID-123** for tracked remediation work.
