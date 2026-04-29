# Glob Pattern Matching

The `ext.glob` module provides portable pattern matching for file listing
across all backends. For simple name-based filtering, use
`Store.list_files(pattern=...)` directly — it works with every backend.

Three tiers of pattern matching are available (ADR-0009):

1. **`list_files(pattern=...)`** — `fnmatch` name filtering at the Store level
2. **`Store.glob(pattern)`** — native backend glob, capability-gated
3. **`ext.glob.glob_files()`** — portable full glob with recursive patterns

No extra dependencies are required — the module is pure Python and always
available.

## Quick Start

```python
from remote_store import Store, glob_files
from remote_store.backends import MemoryBackend

store = Store(backend=MemoryBackend())
store.write("data/report.csv", b"r1")
store.write("data/summary.csv", b"r2")
store.write("data/readme.txt", b"r3")
store.write("logs/app.log", b"l1")

# Tier 1: simple name filtering (works with every backend)
csvs = list(store.list_files("data", pattern="*.csv"))
# [FileInfo("data/report.csv", ...), FileInfo("data/summary.csv", ...)]

# Tier 3: full recursive glob (works with every backend)
all_csvs = list(glob_files(store, "**/*.csv"))
# [FileInfo("data/report.csv", ...), FileInfo("data/summary.csv", ...)]
```

## Tier 1: list_files(pattern=...)

The simplest and most common option. The `pattern` parameter on
`list_files` filters results by **file name** using `fnmatch`:

```python
# All CSVs in the data folder
store.list_files("data", pattern="*.csv")

# All files starting with "report"
store.list_files("", pattern="report.*")

# Single-character wildcard
store.list_files("", pattern="file?.txt")  # file1.txt, fileA.txt

# Character class
store.list_files("", pattern="*.[ct]sv")  # matches .csv and .tsv
```

This works with every backend (needs only `LIST` capability). The
filtering is applied at the Store level after path rebasing.

**Composing with `max_depth`:** `pattern` and `max_depth` compose naturally ---
depth filtering applies first (which files to consider), then pattern filtering
(which names to keep):

```python
# CSVs in data/ and its immediate subfolders only
store.list_files("data", max_depth=1, pattern="*.csv")
```

**Limitation:** `pattern` matches against the file's **name** (basename),
not the full path. For path-based patterns like `data/**/*.csv`, use
`glob_files()` (Tier 3).

## Tier 2: Store.glob() — native backend glob

For backends with native pattern matching, `Store.glob()` provides direct
access. It is capability-gated on `Capability.GLOB` — like `Store.unwrap()`,
it is an opt-in feature for users who know their backend:

```python
from remote_store import Capability

if store.supports(Capability.GLOB):
    for info in store.glob("**/*.csv"):
        print(info.path)
```

`LocalBackend`, `S3Backend`, `S3PyArrowBackend`, and `AzureBackend` implement
native glob. `LocalBackend` uses `pathlib.Path.glob()`; the cloud backends use
prefix-optimized listing with client-side regex filtering.

## Tier 3: glob_files() — portable full glob

`glob_files()` is the recommended API when `list_files(pattern=)` isn't
enough and you want code that works across all backends:

```python
from remote_store.ext.glob import glob_files

# Recursive: find all logs at any depth
for info in glob_files(store, "**/*.log"):
    print(info.path, info.size)

# Subdirectory wildcard
for info in glob_files(store, "data/2024/*.csv"):
    print(info.path)

# Match everything
for info in glob_files(store, "**/*"):
    print(info.path)
```

When the backend supports `Capability.GLOB`, `glob_files` delegates to
the native `store.glob()`. Otherwise it extracts the longest non-wildcard
prefix, calls `store.list_files()` with that prefix, and filters
client-side using a regex compiled from the pattern.

## Pattern Syntax

| Pattern   | Matches |
|-----------|---------|
| `*`       | Any characters except `/` |
| `**`      | Zero or more path segments (recursive) |
| `?`       | Single non-separator character |
| `[abc]`   | Character class |
| `[!abc]`  | Negated character class |

`**` must be a complete path segment (`**/`, `/**`, or the entire pattern).
Patterns like `**error` where `**` is embedded within a segment raise
`ValueError`.

## Works with Store.child()

All glob operations work correctly through `Store.child()` path scoping:

```python
store = Store(backend=MemoryBackend())
store.write("reports/q1.csv", b"data")
store.write("reports/q2.csv", b"data")
store.write("reports/archive/old.csv", b"data")

reports = store.child("reports")

# Tier 1: name filter within child scope
list(reports.list_files("", pattern="*.csv"))
# [FileInfo("q1.csv"), FileInfo("q2.csv")]

# Tier 3: recursive glob within child scope
list(glob_files(reports, "**/*.csv"))
# [FileInfo("q1.csv"), FileInfo("q2.csv"), FileInfo("archive/old.csv")]
```

## Choosing the Right Tier

| Need | Use |
|------|-----|
| Filter files in one folder by name | `list_files(pattern="*.csv")` |
| Recursive search across directories | `glob_files(store, "**/*.csv")` |
| Native backend glob (Local, S3, S3-PyArrow, Azure) | `store.glob("**/*.csv")` |
| Works with every backend | `list_files(pattern=)` or `glob_files()` |

## See also

- [API reference](../api/extensions/glob.md)
- [Example script](https://github.com/haalfi/remote-store/blob/master/examples/extensions/glob_pattern_matching.py)
