# Path Model Specification

## Overview

`RemotePath` is an immutable value object representing a normalized, validated path within a remote store. It enforces safety invariants and provides path manipulation utilities.

## PATH-001: Immutability

**Invariant:** A `RemotePath` instance cannot be modified after construction.
**Postconditions:** All attributes are read-only. Attempting to set attributes raises `AttributeError`.

## PATH-002: Backslash Normalization

**Invariant:** Backslash characters (`\`) are converted to forward slashes (`/`) during normalization.
**Example:**
```python
assert str(RemotePath("a\\b\\c")) == "a/b/c"
```

## PATH-003: Double-Dot Rejection

**Invariant:** A path segment exactly equal to `..` is rejected. A segment that merely contains `..` as a substring (e.g. a filename like `a..b`) is allowed.
**Raises:** `InvalidPath`
**Example:**
```python
with pytest.raises(InvalidPath):
    RemotePath("foo/../bar")
```

## PATH-004: Leading and Trailing Slash Stripping

**Invariant:** Leading and trailing `/` characters are stripped from the normalized path.
**Example:**
```python
assert str(RemotePath("/a/b/")) == "a/b"
```

## PATH-005: Consecutive Slash Collapsing

**Invariant:** Consecutive `/` characters are collapsed to a single `/`.
**Example:**
```python
assert str(RemotePath("a///b")) == "a/b"
```

## PATH-006: Dot Segment Removal

**Invariant:** Single-dot (`.`) segments are removed during normalization.
**Example:**
```python
assert str(RemotePath("a/./b")) == "a/b"
```

## PATH-007: Null Byte Rejection

**Invariant:** Paths containing null bytes (`\0`) are rejected.
**Raises:** `InvalidPath`

## PATH-008: Empty Path Rejection

**Invariant:** A path that normalizes to an empty string is rejected.
**Raises:** `InvalidPath`
**Example:**
```python
with pytest.raises(InvalidPath):
    RemotePath("")
with pytest.raises(InvalidPath):
    RemotePath("/")
with pytest.raises(InvalidPath):
    RemotePath(".")
```

## PATH-009: Name Property

**Invariant:** `name` returns the final component of the path.
**Example:**
```python
assert RemotePath("a/b/c.txt").name == "c.txt"
```

## PATH-010: Parent Property

**Invariant:** `parent` returns the parent `RemotePath`, or `None` for a single-component path.
**Example:**
```python
assert RemotePath("a/b/c").parent == RemotePath("a/b")
assert RemotePath("file.txt").parent is None
```

## PATH-011: Parts Property

**Invariant:** `parts` returns a tuple of path components.
**Example:**
```python
assert RemotePath("a/b/c").parts == ("a", "b", "c")
```

## PATH-012: Join Operator

**Invariant:** The `/` operator joins a `RemotePath` with a string to produce a new `RemotePath`.
**Example:**
```python
assert RemotePath("a") / "b" == RemotePath("a/b")
```

## PATH-013: Equality and Hashing

**Invariant:** Equality and hashing are based on the normalized path string.
**Example:**
```python
assert RemotePath("a/b") == RemotePath("a//b")
assert hash(RemotePath("a/b")) == hash(RemotePath("a//b"))
```

## PATH-014: Suffix Property

**Invariant:** `suffix` returns the file extension (including the dot), or empty string if none.
**Example:**
```python
assert RemotePath("file.tar.gz").suffix == ".gz"
assert RemotePath("noext").suffix == ""
```

## PATH-015: Root Sentinel

**Invariant:** `RemotePath.ROOT` is a class-level singleton sentinel representing the root folder.
It bypasses `__init__` validation (PATH-008 still rejects `RemotePath("")` and `RemotePath(".")`).

**Properties:**
- `str(ROOT)` returns `"."`.
- `ROOT.name` returns `"."`.
- `ROOT.parent` returns `None`.
- `ROOT.parts` returns `(".",)`.
- `ROOT.suffix` returns `""`.
- `ROOT / "a"` produces `RemotePath("a")` (join strips the dot prefix).
- `ROOT` is immutable: `__setattr__` and `__delattr__` raise `AttributeError`.
- `ROOT` is a singleton: `RemotePath.ROOT is RemotePath.ROOT`.

**Round-trip:** Store methods that accept a folder path (`get_folder_info`, `list_files`, etc.)
accept `"."` as a root alias, so `str(folder_info.path)` can be fed back into Store methods.

**Example:**
```python
fi = store.get_folder_info("")
assert fi.path is RemotePath.ROOT
assert str(fi.path) == "."
# Round-trip: "." works as input
fi2 = store.get_folder_info(str(fi.path))
assert fi2.path is RemotePath.ROOT
```
