# Glob — Pattern Matching Specification

## Overview

Three-tier pattern matching for remote-store (ADR-0009):

1. **`list_files(pattern=…)`**: `fnmatch` name filtering on `Store.list_files()`.
   Works with every backend (needs `LIST` only).
2. **`Store.glob(pattern)`**: native backend glob, capability-gated on
   `Capability.GLOB`. Like `unwrap()` — opt-in native access.
3. **`ext.glob.glob_files()`**: portable full glob. Delegates to `Store.glob()`
   when available, otherwise `list_files()` + client-side regex.

Patterns follow Unix glob conventions: `*` matches any non-separator characters,
`**` matches zero or more path segments (recursive), `?` matches a single
non-separator character, `[abc]` matches a character class, `[!abc]` matches
a negated character class.

**Module (extension):** `src/remote_store/ext/glob.py`
**Dependencies:** None (pure Python, always available)
**Related:** [003-backend-adapter-contract.md](003-backend-adapter-contract.md)
(CAP-001, BE-024), [001-store-api.md](001-store-api.md) (STORE-014, STORE-015),
BK-002, ID-007, [ADR-0009](../adrs/0009-glob-three-tier-design.md).

---

## Tier 1: list_files(pattern=…)

### GLOB-001: list_files pattern Parameter

**Invariant:** `Store.list_files(path, *, recursive=False, pattern=None)`.
When `pattern` is not `None`, only files whose **name** matches the pattern
(via `fnmatch.fnmatch`) are yielded.
**Postconditions:** Filtering is applied at the Store level after
rebasing paths. Backend `list_files` signature is unchanged.
**Rationale:** Covers the common case ("give me the CSVs") without new
capabilities, new methods, or extensions.

---

## Tier 2: Native Glob Capability

### GLOB-002: Capability.GLOB Enum Member

**Invariant:** `Capability.GLOB` is a member of the `Capability` enum with
value `"glob"`.
**Rationale:** Backends that implement native pattern matching declare this
capability. Backends without native glob omit it — Tier 1 and Tier 3
provide universal alternatives.

### GLOB-003: Backend.glob() Default Method

**Invariant:** `Backend.glob(pattern)` is a non-abstract method with a default
implementation that raises `CapabilityNotSupported`.
**Signature:**
```python
def glob(self, pattern: str) -> Iterator[FileInfo]:
```
**Parameters:** `pattern` is a glob pattern relative to the backend root.
Supports `*`, `**`, `?`, `[abc]`, and `[!abc]`.
**Raises:** `CapabilityNotSupported` if the backend does not declare
`Capability.GLOB`.
**Rationale:** Non-abstract so existing backends compile without changes.
Backends that add native glob override this method and add `GLOB` to their
capability set.

### GLOB-004: Backend.glob() Postconditions

**Invariant:** Returns only files (not folders). Paths in returned `FileInfo`
objects are backend-relative (same convention as `list_files`). Results are
yielded lazily via iterator.

### GLOB-005: LocalBackend Native Glob

**Invariant:** `LocalBackend` overrides `glob()` using `pathlib.Path.glob()`.
`LocalBackend` declares `Capability.GLOB` in its capability set (via
`set(Capability)` which includes all members).
**Postconditions:** Leverages the OS filesystem's native pattern matching.
`FileInfo` paths are converted via `to_key()` (same as `list_files`).

---

## Tier 2: Store API

### GLOB-006: Store.glob() Signature

**Invariant:** `Store.glob(pattern) -> Iterator[FileInfo]`.
**Parameters:** `pattern` is a glob pattern relative to the store root.
**Raises:** `CapabilityNotSupported` if the backend lacks `Capability.GLOB`.

### GLOB-007: Store.glob() Path Scoping

**Invariant:** Store prepends `root_path` to the pattern before delegating to
`Backend.glob()`. Returned `FileInfo.path` values are rebased to store-relative
(same as `list_files`).

### GLOB-008: Store.glob() Capability Gating

**Invariant:** `Store.glob()` calls `capabilities.require(Capability.GLOB)`
before delegating. If the backend lacks GLOB, the caller should use
`list_files(pattern=...)` or `ext.glob.glob_files()` instead.

---

## Tier 3: Extension — ext.glob

### GLOB-009: glob_files Signature

**Invariant:** `glob_files(store, pattern) -> Iterator[FileInfo]`.
**Parameters:** `store` is a `Store` instance. `pattern` is a glob pattern
relative to the store root.

### GLOB-010: Native Delegation

**Invariant:** When `store.supports(Capability.GLOB)` is `True`,
`glob_files` delegates entirely to `store.glob(pattern)`.

### GLOB-011: Client-Side Fallback

**Invariant:** When `store.supports(Capability.GLOB)` is `False`,
`glob_files` extracts the longest non-wildcard directory prefix from the
pattern, calls `store.list_files(prefix, recursive=...)`, and filters
results client-side against the compiled pattern.

### GLOB-012: Prefix Extraction

**Invariant:** The prefix is the longest sequence of leading path segments
that contain no wildcard characters (`*`, `?`, `[`). For `data/2024/*.csv`
the prefix is `"data/2024"`. For `**/*.csv` the prefix is `""`.
**Rationale:** Minimizes the listing scope — the backend only returns files
under the prefix directory, reducing network traffic and memory usage.

### GLOB-013: Recursive Detection

**Invariant:** The fallback uses `recursive=True` if the pattern contains
`**` or if any non-final path segment contains wildcards. Otherwise uses
`recursive=False`.
**Rationale:** `**` explicitly requests recursive descent. Wildcards in
non-final segments (e.g., `*/sub/*.csv`) require traversing multiple
directory levels.

### GLOB-014: Pattern Matching

**Invariant:** Client-side filtering converts the glob pattern to a regex:
- `*` → `[^/]*` (any characters except separator)
- `**/` → `(?:.+/)?` (zero or more path segments)
- `**` (at end) → `.*` (match everything)
- `?` → `[^/]` (single non-separator character)
- `[abc]` → `[abc]` (character class, passed through)
- `[!abc]` → `[^abc]` (negated character class)
- All other characters are regex-escaped.

The regex is anchored (`^...$`) and matched against the full store-relative
path of each `FileInfo`.

### GLOB-015: No Backend Coupling

**Invariant:** `glob_files` operates exclusively through the public `Store`
API (`supports`, `glob`, `list_files`). It never accesses `store._backend`
or any backend internals.

### GLOB-016: Capability Gating Propagation

**Invariant:** `CapabilityNotSupported` raised by `Store.glob()` or
`Store.list_files()` propagates immediately. `glob_files` does not catch
or wrap these errors.

### GLOB-017: Empty Results

**Invariant:** When no files match the pattern, both `list_files(pattern=...)`
and `glob_files` yield nothing (empty iterator). This is not an error.
