# ext.glob

## glob

Glob — portable pattern matching for file listing.

Delegates to native backend glob when `Capability.GLOB` is available, otherwise falls back to `Store.list_files()` + client-side filtering.

For simple name-based filtering, prefer `Store.list_files(pattern=...)`. Use `glob_files` when you need full recursive glob patterns (`**`, wildcards in directory segments) and want portable behavior across all backends.

Example

```
from remote_store.ext.glob import glob_files

# Works with any backend — uses native glob or list+filter fallback
for info in glob_files(store, "data/**/*.csv"):
    print(info.path, info.size)
```

### glob_files

```
glob_files(
    store: Store, pattern: str
) -> Iterator[FileInfo]
```

Match files against a glob pattern.

When the backend supports `Capability.GLOB`, delegates to `store.glob()` for native pattern matching. Otherwise extracts the longest non-wildcard prefix, lists files under that prefix, and filters client-side.

Parameters:

- **`store`** (`Store`) – The Store to search.
- **`pattern`** (`str`) – Glob pattern relative to the store root (e.g., "data/\*.csv", "\*\*/\*.txt").

Returns:

- `Iterator[FileInfo]` – Iterator of matching FileInfo objects.

## See also

- [Glob Pattern Matching](https://docs.remotestore.dev/stable/guides/glob-pattern-matching/index.md) — guide to portable glob patterns
- [Glob Pattern Matching example](https://docs.remotestore.dev/stable/tutorial/examples/glob-pattern-matching/index.md) — glob usage in action
