# ADR-0005: Bidirectional Path Resolution via `to_key`

## Status

Accepted

## Context

The Store API has a round-trip problem. Users pass **store-relative keys**
(e.g. `"reports/q1.csv"`) into Store methods, and the Store joins them with
`root_path` before delegating to the backend. But the **return path** is broken:

- `list_files` and `get_file_info` delegate to the backend, which returns
  `FileInfo` with paths relative to the **backend root** — these include the
  store's `root_path` prefix. A `Store(root_path="data")` listing returns
  `FileInfo.path = "data/reports/q1.csv"`, not `"reports/q1.csv"`.
- If the user feeds that path back into `store.read(str(info.path))`, the Store
  prepends `root_path` again → `"data/data/reports/q1.csv"` → `NotFound`.

A second, related problem: users receive **absolute or backend-native paths**
from external sources (SFTP server logs, S3 event notifications, filesystem
watchers) and need to convert them to store-relative keys. No public helper
exists for this.

Both problems reduce to the same missing primitive: **convert a
backend-native/absolute path to a store-relative key**.

### Current ad-hoc handling

Each backend strips its own root differently:
- **Local:** `Path.relative_to(self._root)` inline in listing methods.
- **S3:** `_rel_path()` helper strips the bucket prefix.
- **SFTP:** String concatenation from input path + filename (no dedicated helper).

None of them strip the **store root** — that responsibility belongs to the Store
layer, which currently doesn't do it at all.

## Decision

Introduce `to_key` at two levels:

### 1. `Backend.to_key(native_path: str) -> str`

Concrete method on the Backend ABC (identity default). Converts a
backend-native path to a backend-relative key by stripping the backend's own
root/prefix.

- **Local:** strips filesystem root → `"/tmp/store/data/file.txt"` → `"data/file.txt"`
- **S3:** strips bucket prefix → `"my-bucket/data/file.txt"` → `"data/file.txt"`
- **SFTP:** strips base_path → `"/srv/sftp/data/file.txt"` → `"data/file.txt"`

Replaces the existing scattered `_rel_path` / `relative_to` patterns with a
single, consistent hook.

### 2. `Store.to_key(path: str) -> str`

Public method. Composes backend conversion with store-root stripping:

```
backend.to_key(native_path)  →  strip root_path prefix  →  store-relative key
```

Example:
```python
store = Store(backend=sftp, root_path="data")
store.to_key("/srv/sftp/data/reports/q1.csv")  # → "reports/q1.csv"
```

### 3. Round-trip fix

Store listing methods (`list_files`, `list_folders`, `get_file_info`,
`get_folder_info`) strip `root_path` from returned paths so that `FileInfo.path`
is directly usable as input to other Store methods.

### Key design choices

1. **Same name at both levels** — `to_key` at Backend and Store. Clear intent,
   composable.

2. **Concrete method, not abstract** — existing backends inherit the identity
   default. Only backends with custom roots override.

3. **Pure and deterministic** — no I/O, no side effects. Testable in isolation.

4. **Store owns the round-trip guarantee** — the Store layer strips `root_path`,
   not the backend. Backends only know about their own root.

## Consequences

- **Round-trip works** — `FileInfo.path` from listing is directly usable as
  input to `read`, `write`, `delete`, etc.
- **External paths are supported** — users can convert absolute paths from logs,
  events, and other systems to store keys via a public API.
- **Backend path logic is centralized** — each backend defines its
  native→relative conversion in one place instead of scattering it.
- **RemotePath is untouched** — all PATH-* spec invariants remain in force.
- **Backward compatible** — identity default means zero behavioral change for
  backends that don't override.
