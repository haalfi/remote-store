# iter_children Specification

## Overview

`iter_children()` returns both files and subfolders under a path in a single
pass, avoiding the two round-trips required by calling `list_files()` and
`list_folders()` separately. Most backends (S3 `ls`, local `iterdir`, SFTP
`listdir_attr`) already fetch both in a single response — this API exposes
that efficiency to callers.

Non-recursive only (immediate children). For recursive file listing, use
`list_files(recursive=True)`. For pattern filtering, use
`list_files(pattern=...)` or `ext.glob.glob_files()`.

---

## Store API

### ITER-001: `Store.iter_children()`

**Invariant:** `Store.iter_children(path)` delegates to
`Backend.iter_children()` and yields both files and folders under `path`.

**Signature:**
```python
def iter_children(self, path: str) -> Iterator[FileInfo | str]:
    ...
```

**Postconditions:**
- Files are yielded as `FileInfo` with store-relative paths (same rebasing as
  `list_files` — see STORE-012).
- Folders are yielded as `str` folder names (same format as `list_folders`).
- Ordering within a single type is backend-defined. Files and folders may be
  interleaved or grouped — callers must not depend on ordering.
- Empty directories yield nothing.
- Non-existent paths yield nothing (no exception).
- `path` accepts `""` and `"."` as root aliases (same as `list_files`).

### ITER-002: Capability Gating

**Invariant:** `iter_children()` is gated on `Capability.LIST`. Raises
`CapabilityNotSupported` if the backend lacks `LIST`.

### ITER-003: STORE-008 Update

**Invariant:** `iter_children` is added to the Store API surface in STORE-008.

---

## Backend API

### ITER-004: `Backend.iter_children()`

**Invariant:** `Backend.iter_children(path)` is a concrete (non-abstract)
method with a default implementation that chains `list_files()` and
`list_folders()`.

**Signature:**
```python
def iter_children(self, path: str) -> Iterator[FileInfo | str]:
    ...
```

**Default implementation:**
```python
def iter_children(self, path: str) -> Iterator[FileInfo | str]:
    yield from self.list_files(path)
    yield from self.list_folders(path)
```

**Postconditions:**
- Returns an iterator of `FileInfo` (for files) and `str` (for folder names).
- Backends may override to perform a single I/O call instead of two.
- Non-existent paths yield nothing.

### ITER-005: Backend Overrides

**Invariant:** Backends that can fetch files and folders in a single I/O
operation override `iter_children()` for efficiency.

| Backend      | Override strategy                                         |
|------------- |-----------------------------------------------------------|
| Local        | Single `iterdir()`, yield `FileInfo` or folder name       |
| S3           | Single `ls(detail=True)`, partition by `type`             |
| S3-PyArrow   | Single `ls(detail=True)`, partition by `type`             |
| SFTP         | Single `listdir_attr()`, partition by `st_mode`           |
| Azure non-HNS | Single `walk_blobs()`, partition by `prefix` attribute  |
| Azure HNS    | Single `get_paths(recursive=False)`, partition by `is_directory` |
| Memory       | Single tree traversal under lock                          |

---

## Extension Integration

### ITER-006: ext.observe

**Invariant:** `iter_children()` fires the `on_list` hook (same as
`list_files` and `list_folders`). The operation name in the hook context is
`"iter_children"`.

**ObservedStore implementation:** Materializes results into a list (same
pattern as `list_files` / `list_folders`) to ensure timing covers actual I/O.

### ITER-007: ext.cache

**Invariant:** `CachedStore` caches `iter_children()` results under the key
`("iter_children", path)`. Invalidated by the same mutation operations that
invalidate `list_files` and `list_folders` (writes, deletes, moves, copies).

The `"iter_children"` prefix is added to `_LISTING_PREFIXES`.

---

## Spec Cross-References

### ITER-008: Spec Updates

The following specs are updated to reflect `iter_children`:

- **001-store-api.md**: Add `iter_children` to STORE-008 surface list.
- **003-backend-adapter-contract.md**: Add `iter_children` to backend method
  table (concrete with default, not abstract).
- **019-ext-observe.md**: Add `iter_children` to `on_list` hook table.
- **023-ext-cache.md**: Add `iter_children` to cached operations table and
  `_LISTING_PREFIXES`.
