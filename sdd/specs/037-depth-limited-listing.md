# Depth-Limited Listing

Adds `max_depth` parameter to `Store.list_files()` and `Store.list_folders()`
for controlling traversal depth without fetching the full recursive tree.

**Related:** [Research](../research/research-depth-limited-listing.md),
ID-107, ID-108.

---

## DEPTH-001: list_files(max_depth=N)

**Invariant:** `list_files(path, *, recursive=False, pattern=None, max_depth=None)`
accepts an optional `max_depth` keyword. Depth is the number of folder levels
between the listing root and the file's parent directory:

- `max_depth=None` (default): defers to `recursive`.
- `max_depth=0`: files directly in `path` only (equivalent to `recursive=False`).
- `max_depth=N` (N > 0): files up to N folder levels below `path`.

When `max_depth` is set, `recursive` is ignored -- depth takes full control of
traversal.

**Validation:** `max_depth < 0` raises `ValueError`.

**Filtering order:** depth filtering applies first, then `pattern` filtering.
The two compose naturally.

**Implementation (Phase 1):** Client-side filtering at the Store level.
`max_depth=0` delegates with `recursive=False`; `max_depth > 0` delegates with
`recursive=True` and filters results by path component count. No Backend ABC
change.

**Depth examples:**

```
store.list_files("data", max_depth=1)

data/file_a.csv          -> depth 0  included
data/raw/file_b.csv      -> depth 1  included
data/raw/2026/file_c.csv -> depth 2  excluded
```

---

## DEPTH-002: list_folders(max_depth=N)

**Invariant:** `list_folders(path, *, max_depth=None)` accepts an optional
`max_depth` keyword controlling how many levels of subfolders to return:

- `max_depth=None` or `max_depth=0`: immediate children only (current behavior).
- `max_depth=N` (N > 0): subfolders up to N levels deep via BFS traversal using
  `Backend.list_folders()` at each level.

**Validation:** `max_depth < 0` raises `ValueError`.

**Implementation (Phase 1):** BFS at the Store level. Each BFS step calls the
existing `Backend.list_folders()` for one level. Cost is O(total folders within
depth), not O(depth). No Backend ABC change.
