# Glob — Pattern Matching Specification

## Overview

Glob adds file pattern matching to remote-store at two levels:

1. **Core**: `Capability.GLOB`, `Backend.glob()`, and `Store.glob()` — for
   backends with native glob support (e.g., Local via pathlib).
2. **Extension**: `ext.glob.glob_files()` — universal function that delegates
   to `Store.glob()` when the backend supports GLOB, otherwise falls back to
   `Store.list_files()` + client-side pattern matching.

Patterns follow Unix glob conventions: `*` matches any non-separator characters,
`**` matches zero or more path segments (recursive), `?` matches a single
non-separator character.

**Module (extension):** `src/remote_store/ext/glob.py`
**Dependencies:** None (pure Python, always available)
**Related:** [003-backend-adapter-contract.md](003-backend-adapter-contract.md)
(CAP-001, BE-024), [001-store-api.md](001-store-api.md) (STORE-014), BK-002,
ID-007.

---

## Capability

### GLOB-001: Capability.GLOB Enum Member

**Invariant:** `Capability.GLOB` is a member of the `Capability` enum with
value `"glob"`.
**Rationale:** Backends that implement native pattern matching declare this
capability. Backends without native glob omit it — the extension provides a
universal fallback via `list_files` + client-side filtering.

---

## Backend Contract

### GLOB-002: Backend.glob() Default Method

**Invariant:** `Backend.glob(pattern)` is a non-abstract method with a default
implementation that raises `CapabilityNotSupported`.
**Signature:**
```python
def glob(self, pattern: str) -> Iterator[FileInfo]:
```
**Parameters:** `pattern` is a glob pattern relative to the backend root (or to
whatever path prefix the Store prepends). Supports `*`, `**`, and `?`
wildcards.
**Raises:** `CapabilityNotSupported` if the backend does not declare
`Capability.GLOB`.
**Rationale:** Non-abstract so existing backends compile without changes.
Backends that add native glob override this method and add `GLOB` to their
capability set.

### GLOB-003: Backend.glob() Postconditions

**Invariant:** Returns only files (not folders). Paths in returned `FileInfo`
objects are backend-relative (same convention as `list_files`). Results are
yielded lazily via iterator.

### GLOB-004: LocalBackend Native Glob

**Invariant:** `LocalBackend` overrides `glob()` using `pathlib.Path.glob()`.
`LocalBackend` declares `Capability.GLOB` in its capability set.
**Postconditions:** Leverages the OS filesystem's native pattern matching.
`FileInfo` paths are converted via `to_key()` (same as `list_files`).

---

## Store API

### GLOB-005: Store.glob() Signature

**Invariant:** `Store.glob(pattern) -> Iterator[FileInfo]`.
**Parameters:** `pattern` is a glob pattern relative to the store root.
**Raises:** `CapabilityNotSupported` if the backend lacks `Capability.GLOB`.

### GLOB-006: Store.glob() Path Scoping

**Invariant:** Store prepends `root_path` to the pattern before delegating to
`Backend.glob()`. Returned `FileInfo.path` values are rebased to store-relative
(same as `list_files`).

### GLOB-007: Store.glob() Capability Gating

**Invariant:** `Store.glob()` calls `capabilities.require(Capability.GLOB)`
before delegating. If the backend lacks GLOB, the caller should use
`ext.glob.glob_files()` instead.

---

## Extension: ext.glob

### GLOB-008: glob_files Signature

**Invariant:** `glob_files(store, pattern) -> Iterator[FileInfo]`.
**Parameters:** `store` is a `Store` instance. `pattern` is a glob pattern
relative to the store root.

### GLOB-009: Native Delegation

**Invariant:** When `store.supports(Capability.GLOB)` is `True`,
`glob_files` delegates entirely to `store.glob(pattern)`.

### GLOB-010: Client-Side Fallback

**Invariant:** When `store.supports(Capability.GLOB)` is `False`,
`glob_files` extracts the longest non-wildcard directory prefix from the
pattern, calls `store.list_files(prefix, recursive=...)`, and filters
results client-side against the compiled pattern.

### GLOB-011: Prefix Extraction

**Invariant:** The prefix is the longest sequence of leading path segments
that contain no wildcard characters (`*`, `?`, `[`). For `data/2024/*.csv`
the prefix is `"data/2024"`. For `**/*.csv` the prefix is `""`.
**Rationale:** Minimizes the listing scope — the backend only returns files
under the prefix directory, reducing network traffic and memory usage.

### GLOB-012: Recursive Detection

**Invariant:** The fallback uses `recursive=True` if the pattern contains
`**` or if any non-final path segment contains wildcards. Otherwise uses
`recursive=False`.
**Rationale:** `**` explicitly requests recursive descent. Wildcards in
non-final segments (e.g., `*/sub/*.csv`) require traversing multiple
directory levels.

### GLOB-013: Pattern Matching

**Invariant:** Client-side filtering converts the glob pattern to a regex:
- `*` → `[^/]*` (any characters except separator)
- `**/` → `(?:.+/)?` (zero or more path segments)
- `**` (at end) → `.*` (match everything)
- `?` → `[^/]` (single non-separator character)
- All other characters are regex-escaped.

The regex is anchored (`^...$`) and matched against the full store-relative
path of each `FileInfo`.

### GLOB-014: No Backend Coupling

**Invariant:** `glob_files` operates exclusively through the public `Store`
API (`supports`, `glob`, `list_files`). It never accesses `store._backend`
or any backend internals.

### GLOB-015: Capability Gating Propagation

**Invariant:** `CapabilityNotSupported` raised by `Store.glob()` or
`Store.list_files()` propagates immediately. `glob_files` does not catch
or wrap these errors.

### GLOB-016: Empty Results

**Invariant:** When no files match the pattern, `glob_files` yields nothing
(empty iterator). This is not an error.
