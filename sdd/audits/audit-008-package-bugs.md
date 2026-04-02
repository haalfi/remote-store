# Audit 008 -- Package Bugs (User-Facing)

**Date:** 2026-04-02
**Scope:** All source code under `src/remote_store/` — core store, backends,
extensions, async API, configuration.
**Method:** Systematic code review of all 52 source files, followed by
executable reproduction scripts for each candidate bug. Only findings
with confirmed failing reproductions are included.

---

## Summary

| ID | Component | Severity | Title |
|---|---|---|---|
| B-1 | `ext/cache` | **High** | CachedStore: write doesn't invalidate parent directory metadata |
| B-2 | `ext/cache` | **High** | CachedStore.child() creates isolated cache — cross-store coherence lost |
| B-3 | `_config` | **Medium** | `RegistryConfig.from_dict` crashes on YAML/TOML `null` options |
| B-4 | `_config` | **Medium** | `RegistryConfig.from_dict` silently converts `null` to string `"None"` |
| B-5 | `ext/partition` | **Low** | `partition_path` allows `=` in key — round-trip with `parse_partition` fails |

---

<a id="b-1"></a>

## B-1 — CachedStore: write doesn't invalidate parent directory metadata

**File:** `src/remote_store/ext/cache.py` lines 288–292 (`_invalidate_path`)
**Severity:** High

### Description

When writing a file at a nested path (e.g. `dir/file.txt`), the backend
implicitly creates intermediate directories. `CachedStore._invalidate_path`
only invalidates cache entries for the **exact path** written, not for any
parent directories. This leaves `exists()`, `is_file()`, and `is_folder()`
cache entries for parent paths stale.

### Reproduction

```python
from remote_store.backends._memory import MemoryBackend
from remote_store._store import Store
from remote_store.ext.cache import cache

store = Store(MemoryBackend())
cached = cache(store, ttl=300)

# Cache "newdir" as non-existent
assert cached.exists("newdir") == False       # cached

# Write creates "newdir" implicitly
cached.write("newdir/file.txt", b"hello", overwrite=True)

# BUG: returns stale False — should be True
assert cached.exists("newdir") == False        # stale!
assert store.exists("newdir") == True          # actual truth
```

### Execution result

```
exists("newdir") before write: False
exists("newdir") after write:  False    ← stale
is_folder("newdir") after write: False  ← stale
```

### Root cause

`_invalidate_path(path)` at line 288 iterates `_PATH_PREFIXES` and deletes
`(prefix, path)` — only the **leaf** path — then calls `_invalidate_listings()`
(line 292), which clears all listing/glob cache entries. Listing operations
like `list_files("newdir")` therefore return fresh results. However, per-path
metadata (`exists`, `is_folder`, `is_file`) for **parent** segments (e.g.
`"newdir"` when writing `"newdir/file.txt"`) is not invalidated.

---

<a id="b-2"></a>

## B-2 — CachedStore.child() creates isolated cache

**File:** `src/remote_store/ext/cache.py` lines 443–451 (`_wrap_child`)
**Severity:** High

### Description

`CachedStore._wrap_child()` creates a **new** `CachedStore` with
`cache_backend=None`, meaning a fresh `MemoryCache`. The child and parent
have completely independent caches. Writing through the child does not
invalidate the parent's cached entries, so the parent returns stale data.

### Reproduction

```python
from remote_store.backends._memory import MemoryBackend
from remote_store._store import Store
from remote_store.ext.cache import cache

store = Store(MemoryBackend())
cached_store = cache(store, ttl=300)

cached_store.write("sub/file.txt", b"version1", overwrite=True)
content1 = cached_store.read_bytes("sub/file.txt")  # cached

child = cached_store.child("sub")
child.write("file.txt", b"version2", overwrite=True)  # child cache only

# BUG: parent returns stale cached content
content2 = cached_store.read_bytes("sub/file.txt")
assert content2 == b"version1"                  # stale!
assert store.read_bytes("sub/file.txt") == b"version2"  # truth
```

### Execution result

```
Parent reads:                   b'version1'
Parent reads after child write: b'version1'   ← stale
Actual value in store:          b'version2'
```

### Root cause

`_wrap_child` at line 444 passes `cache_backend=None`, which triggers
`MemoryCache()` construction at line 240. The parent's cache instance is
never shared or linked.

---

<a id="b-3"></a>

## B-3 — RegistryConfig.from_dict crashes on YAML/TOML null options

**File:** `src/remote_store/_config.py` line 246 and 270
**Severity:** Medium

### Description

When a YAML or TOML config file specifies `options:` with no value (producing
Python `None`), `from_dict` calls `dict(None)` or `dict(prof.get("options", {}))`
where the `get` returns `None` (key exists with null value). This raises an
unhelpful `TypeError`.

### Reproduction

```python
from remote_store._config import RegistryConfig

config_data = {
    "backends": {
        "mybackend": {
            "type": "memory",
            "options": None,    # YAML "options:" with no value
        }
    },
    "stores": {},
}

RegistryConfig.from_dict(config_data)
# TypeError: 'NoneType' object is not iterable
```

### Execution result

```
TypeError: 'NoneType' object is not iterable
```

### Root cause

Line 246: `options = dict(cfg.get("options", {}))`. When the key `"options"`
exists with value `None`, `.get("options", {})` returns `None` (the key is
present), and `dict(None)` raises `TypeError`. The same pattern exists at
line 270 for store profiles.

---

<a id="b-4"></a>

## B-4 — RegistryConfig.from_dict silently converts null to string "None"

**File:** `src/remote_store/_config.py` lines 257, 268–269
**Severity:** Medium

### Description

`str(None)` produces the string `"None"` in Python. When YAML/TOML config
files contain null values for `type`, `backend`, or `root_path`, `from_dict`
silently converts them to the literal string `"None"` instead of raising a
validation error. This causes files to be stored under a `None/` prefix or
backend lookups to fail with a confusing "unknown backend type 'None'" error.

### Reproduction

```python
from remote_store._config import RegistryConfig
from remote_store.backends._memory import MemoryBackend
from remote_store._store import Store

config = RegistryConfig.from_dict({
    "backends": {"b": {"type": "memory"}},
    "stores": {"s": {"backend": "b", "root_path": None}},
})

print(repr(config.stores["s"].root_path))  # 'None'

# Using this profile corrupts paths:
store = Store(MemoryBackend(), root_path=config.stores["s"].root_path)
store.write("file.txt", b"data", overwrite=True)
# File stored at "None/file.txt" instead of "file.txt"
```

### Execution result

```
root_path repr: 'None'
File at None/file.txt: True
File at file.txt:      False
```

### Root cause

`str()` coercion at lines 257 (`str(cfg["type"])`), 268 (`str(prof["backend"])`),
and 269 (`str(prof.get("root_path", ""))`) treats `None` as a valid input
instead of validating that required fields are strings.

---

<a id="b-5"></a>

## B-5 — partition_path allows `=` in key — round-trip fails

**File:** `src/remote_store/ext/partition.py` lines 65–76
**Severity:** Low

### Description

`partition_path` validates that `=` is not in the partition **value** (line
73–74) but does not validate the partition **key**. A key containing `=`
produces a segment like `col=x=val` with two `=` signs, which
`parse_partition` cannot parse (it requires exactly one `=` per segment).

### Reproduction

```python
from remote_store.ext.partition import partition_path, parse_partition

path = partition_path("data.parquet", **{"col=x": "val"})
# 'col=x=val/data.parquet'

parsed = parse_partition(path)
print(parsed.partitions)   # {} — key lost
print(parsed.filename)     # 'col=x=val/data.parquet' — entire path is filename
```

### Execution result

```
partition_path output: 'col=x=val/data.parquet'
Partitions recovered:  {}
Filename recovered:    'col=x=val/data.parquet'
Round-trip: FAILED
```

### Root cause

Line 73 checks `if "=" in str_value` for values but there is no corresponding
check for keys. `_is_partition_segment` at line 122–124 requires
`segment.count("=") == 1`, so any key with `=` produces unparseable output.

---

## Notes

- **Azure `start_copy_from_url` race condition:** The non-HNS code paths in
  `backends/_azure.py` lines 661–662 (move) and 681 (copy) call
  `start_copy_from_url()` without waiting for the async server-side copy to
  complete before deleting the source (move) or returning (copy). This is a
  real data-loss risk for large blobs or cross-account copies but cannot be
  reproduced without an Azure environment.

- **ChecksumWriter / ProgressWriter partial-write semantics:** Both wrappers
  in `ext/streams.py` update hash/callback based on input data length rather
  than actual bytes written. This is explicitly documented as a known
  limitation ("Assumes buffered I/O semantics"). Users wrapping `RawIOBase`
  streams will get incorrect checksums/progress. Noted here for completeness.
