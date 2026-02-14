# ADR-0004: Empty Path Semantics in Store

## Status

Accepted

## Context

`RemotePath` rejects empty strings (PATH-008), and `Store._full_path` validated all paths through `RemotePath`. This meant `store.list_files("")` and `store.list_folders("")` raised `InvalidPath` — users had no way to query the store root.

This surfaced when writing example scripts: every natural usage pattern for "list everything in the store" required passing `""` as the path argument.

## Decision

Split path resolution in `Store` into two tiers:

1. **`_full_path(path)`** — accepts empty string `""` to mean "the store root." If `root_path` is set, returns `root_path`; otherwise returns `""`. Non-empty paths still validate through `RemotePath`.

2. **`_require_file_path(path)`** — rejects empty strings with `InvalidPath`. Used by file-targeted operations where an empty path is nonsensical.

### Method classification

| Accepts `""` (folder/query ops) | Rejects `""` (file-targeted ops) |
|--------------------------------|----------------------------------|
| `exists` | `read`, `read_bytes` |
| `is_file`, `is_folder` | `write`, `write_atomic` |
| `list_files`, `list_folders` | `delete` |
| `get_folder_info` | `delete_folder` |
| | `get_file_info` |
| | `move`, `copy` |

### Rationale for `delete_folder("")` rejection

Even though `delete_folder` is a folder operation, deleting the store root is destructive and almost certainly unintended. It is rejected with `InvalidPath("Cannot delete the store root")`.

## Consequences

- `RemotePath` is unchanged — still rejects empty strings (PATH-008 intact)
- STORE-002 is updated to reflect the two-tier resolution
- Users can now naturally query the store root with `""`
- File-targeted operations fail early with a clear error on empty path
- `delete_folder("")` is explicitly guarded as a safety measure
