# ADR-0004: Empty Path Semantics in Store

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

`RemotePath` rejects empty strings (PATH-008), and `Store._full_path` validated all paths through `RemotePath`. This meant `store.list_files("")` and `store.list_folders("")` raised `InvalidPath` — users had no way to query the store root.

This surfaced when writing example scripts: every natural usage pattern for "list everything in the store" required passing `""` as the path argument.

## Decision

Split path resolution in `Store` into two tiers:

- **`_full_path(path)` accepts `""` (and `"."`) as the store root.** Folder and
  query operations resolve an empty path to the store root instead of raising;
  non-empty paths still validate through `RemotePath`, so PATH-008 is untouched.
  *Reverse if* `RemotePath` is changed to accept `""` directly, making the
  second tier redundant.
- **`_require_file_path(path)` rejects `""` for file-targeted operations.** An
  empty path to a file operation is nonsensical, so it fails early with
  `InvalidPath` rather than reaching a backend. *Reverse if* any file operation
  gains meaningful root semantics (none exists today).
- **`delete_folder("")` is rejected even though it is a folder operation.**
  Deleting the store root is destructive and almost certainly unintended, so it
  is the deliberate exception to the folder-op accept rule and raises
  `InvalidPath`. *Reverse if* an explicit "empty the store" workflow is ever
  needed; that must be a distinct, guarded entry point, never a bare empty path.

The authoritative, per-method roster of which operations accept vs. reject the
root is spec-rate and lives in spec 001 § STORE-002, which tracks method
additions as the API grows.

## Consequences

- `RemotePath` is unchanged — still rejects empty strings (PATH-008 intact)
- STORE-002 is updated to reflect the two-tier resolution
- Users can now naturally query the store root with `""`
- File-targeted operations fail early with a clear error on empty path
- `delete_folder("")` is explicitly guarded as a safety measure
