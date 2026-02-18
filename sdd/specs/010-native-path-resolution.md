# Native Path Resolution Specification

## Overview

This spec defines bidirectional path resolution between backend-native paths and
store-relative keys. The primary motivation is **round-trip safety**: paths
returned by the Store API must be directly usable as input to other Store
methods. A secondary motivation is a **public helper** for users who receive
absolute or backend-native paths from external sources and need to convert them
to store-relative keys.

The solution is `to_key` — a method at both the Backend and Store levels that
converts native paths to relative keys.

**Relationship to existing specs:**
- Extends `003-backend-adapter-contract.md` (new method on Backend ABC)
- Complements `004-path-model.md` (RemotePath validation is unchanged)
- See also: [ADR-0005](../adrs/0005-native-path-resolution.md)

---

## The Problem

### NPR-001: Round-Trip Invariant

**Invariant:** Any path returned by a Store method (in `FileInfo.path`,
`FolderInfo.path`, or `list_folders` results) must be directly usable as input
to other Store methods without modification.

**Example:**
```python
store = Store(backend=local, root_path="data")
store.write("reports/q1.csv", content)

for f in store.list_files(""):
    data = store.read_bytes(str(f.path))  # must work — no manual stripping
```

**Current violation:** `FileInfo.path` includes the store's `root_path` prefix
(e.g. `"data/reports/q1.csv"` instead of `"reports/q1.csv"`), causing double-
prefixing when fed back into Store methods.

### NPR-002: External Path Conversion

**Invariant:** `Store.to_key(path)` converts an absolute or backend-native path
to a store-relative key that can be used with any Store method.

**Example:**
```python
store = Store(backend=sftp, root_path="data")

# Path from an SFTP server log
key = store.to_key("/srv/sftp/data/reports/q1.csv")
assert key == "reports/q1.csv"

content = store.read_bytes(key)  # works
```

---

## Backend: `to_key`

### NPR-003: Backend.to_key Method

**Invariant:** The Backend ABC gains a concrete (non-abstract) method:
```python
def to_key(self, native_path: str) -> str:
    """Convert a backend-native path to a backend-relative key.

    :param native_path: Absolute or backend-native path string.
    :returns: Path relative to the backend's root.
    """
    return native_path  # default: identity
```
**Postconditions:** The default implementation is the identity function.
Backends that have no concept of a native root (or whose I/O already operates
on relative keys) inherit the default unchanged.

### NPR-004: Backend.to_key Contract

**Invariant:** Implementations of `to_key` must satisfy:
1. **Deterministic** — same input always produces the same output.
2. **Pure** — no side effects, no I/O, no network calls.
3. **Total** — must return a string for every input; must not raise.

### NPR-005: Backend.to_key Is Stripping, Not Validation

**Invariant:** `to_key` strips the backend's own root/prefix from the path.
It does not validate path safety — that is `RemotePath`'s responsibility. If
the input path does not start with the backend's root, the backend returns the
input unchanged (best-effort).

### NPR-006: LocalBackend.to_key

**Invariant:** `LocalBackend.to_key(native_path)` strips the backend's
filesystem root directory.
**Example:**
```python
backend = LocalBackend("/tmp/store")
backend.to_key("/tmp/store/data/file.txt")  # → "data/file.txt"
backend.to_key("data/file.txt")             # → "data/file.txt" (no prefix, unchanged)
```
**Postconditions:** Replaces the inline `Path.relative_to(self._root)` calls
currently scattered across listing methods.

### NPR-007: S3Backend.to_key

**Invariant:** `S3Backend.to_key(native_path)` strips the bucket prefix.
**Example:**
```python
backend = S3Backend(bucket="my-bucket")
backend.to_key("my-bucket/data/file.txt")   # → "data/file.txt"
backend.to_key("data/file.txt")             # → "data/file.txt" (no prefix, unchanged)
```
**Postconditions:** Replaces the existing `_rel_path()` helper with a public,
contract-backed method.

### NPR-008: SFTPBackend.to_key

**Invariant:** `SFTPBackend.to_key(native_path)` strips the configured
`base_path`.
**Example:**
```python
backend = SFTPBackend(host="srv", base_path="/srv/sftp")
backend.to_key("/srv/sftp/data/file.txt")   # → "data/file.txt"
backend.to_key("data/file.txt")             # → "data/file.txt" (no prefix, unchanged)
```

### NPR-009: Future Backends

**Invariant:** New backends (Azure Blob, GCS, etc.) implement `to_key` to strip
their native root/prefix. The method is the single extension point for
backend-specific reverse path resolution.

---

## Store: `to_key`

### NPR-010: Store.to_key Method

**Invariant:** `Store.to_key(path)` is a public method that composes backend
conversion with store-root stripping:

```python
def to_key(self, path: str) -> str:
    """Convert an absolute or backend-native path to a store-relative key.

    :param path: Absolute, backend-native, or backend-relative path.
    :returns: Key relative to this store's root_path.
    """
```

**Sequence:**
```
native_path  →  backend.to_key()  →  strip root_path prefix  →  store-relative key
```

### NPR-011: Store.to_key Composition

**Invariant:** `Store.to_key` calls `backend.to_key(path)` first, then strips
its own `root_path` prefix from the result. The two levels are independent and
composable.

**Example:**
```python
# SFTP backend with base_path="/srv/sftp", store with root_path="data"
store = Store(backend=sftp, root_path="data")

# Full chain: "/srv/sftp/data/reports/q1.csv"
#   → backend.to_key → "data/reports/q1.csv"
#   → strip root_path → "reports/q1.csv"
store.to_key("/srv/sftp/data/reports/q1.csv")  # → "reports/q1.csv"
```

### NPR-012: Store.to_key With No root_path

**Invariant:** When `root_path` is empty, `Store.to_key` returns the result of
`backend.to_key` directly (nothing to strip).

### NPR-013: Store.to_key With Unrelated Path

**Invariant:** If the path (after backend stripping) does not start with
`root_path`, `Store.to_key` raises `InvalidPath`. The path does not belong to
this store.

**Example:**
```python
store = Store(backend=local, root_path="data")
store.to_key("/tmp/store/other/file.txt")  # → InvalidPath (not under "data/")
```

---

## Round-Trip Fix

### NPR-014: Store Listing Methods Return Store-Relative Paths

**Invariant:** `list_files`, `get_file_info`, and `get_folder_info` strip
`root_path` from the paths in returned `FileInfo` / `FolderInfo` objects.
The returned `path` attribute contains a store-relative key.

**Example:**
```python
store = Store(backend=local, root_path="data")
store.write("reports/q1.csv", content)

files = list(store.list_files(""))
assert str(files[0].path) == "reports/q1.csv"  # NOT "data/reports/q1.csv"
```

### NPR-015: list_folders Returns Store-Relative Names

**Invariant:** `list_folders` returns immediate subfolder **names** (not full
paths). This is already the current behavior and is unaffected by this spec.

### NPR-016: Round-Trip With Nested Paths

**Invariant:** Round-trip works at any nesting depth:
```python
store = Store(backend=local, root_path="project/data")
store.write("2024/q1/report.csv", content)

for f in store.list_files("", recursive=True):
    assert store.read_bytes(str(f.path))  # works for all depths
```

---

## Validation and Safety

### NPR-017: RemotePath Invariants Are Preserved

**Invariant:** All existing `RemotePath` validation rules (PATH-001 through
PATH-014) remain in force. `to_key` output is validated through `RemotePath`
before use in Store methods — the same as any user-provided path.

### NPR-018: No New Capability Required

**Invariant:** `to_key` is not gated by a `Capability`. All backends have it
(with the identity default). There is no `Capability.NATIVE_PATH_RESOLUTION`.

### NPR-019: Backward Compatibility

**Invariant:** Existing backends that do not override `to_key` behave
identically to the current system for forward operations (rel→abs via
`_full_path`). The listing round-trip fix is a **bug fix**, not a behavioral
change — current behavior (leaking `root_path` in returned paths) is incorrect
per NPR-001.
