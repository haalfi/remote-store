# Path Model Specification

## Overview

`RemotePath` is an immutable value object holding one Key of a store, with path manipulation utilities. `RemotePath(s)` holds [spec 054](054-store-key.md)'s store key K(s) of the input `s` where that is not the root, and raises `InvalidPath` where spec 054 refuses `s` or K(s) is the root (PATH-008); `RemotePath.ROOT` holds the root (PATH-015); which inputs map to which Key, and in what precedence, is spec 054's (PATH-002 to PATH-007 are its sections). This spec states the value object.

## PATH-001: Immutability

**Invariant:** A `RemotePath` instance cannot be modified after construction.
**Postconditions:** All attributes are read-only. Attempting to set attributes raises `AttributeError`.

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

## PATH-016: `as_posix` Method

**Invariant:** `as_posix()` is a method (called with parentheses, matching
`pathlib.PurePath.as_posix`) that returns the forward-slash path string.
Because `RemotePath` always stores forward slashes, the result equals
`str(self)` on every platform.
**Postconditions:** `RemotePath("a/b").as_posix() == "a/b"`;
`RemotePath.ROOT.as_posix() == "."`.
**Example:**
```python
assert RemotePath("a\\b").as_posix() == "a/b"
assert RemotePath.ROOT.as_posix() == "."
```

## PATH-017: Not `os.PathLike`

**Invariant:** `RemotePath` deliberately does **not** implement `__fspath__`
and is therefore not an `os.PathLike`. `RemotePath` is a *remote-store key*,
not a local filesystem path; implementing `__fspath__` would let it be passed
silently to `open()`, `os.path.*`, and similar APIs that operate on the local
filesystem, masking a category error. Callers that need a string use
`as_posix()` (PATH-016) or `str()`.
**Postconditions:** `isinstance(RemotePath("a"), os.PathLike)` is `False`;
`os.fspath(RemotePath("a"))` raises `TypeError`.
**Example:**
```python
import os
with pytest.raises(TypeError):
    os.fspath(RemotePath("a"))
```

### pathlib parity scope (informative)

`RemotePath` is a deliberately minimal subset of `pathlib.PurePath`, not a
drop-in replacement. Beyond `as_posix()` (PATH-016), the following `PurePath`
members are intentionally absent:
`stem`, `suffixes`, `with_name`, `with_suffix`, `with_stem`, `joinpath`,
`parents`, `match`, `relative_to` / `is_relative_to`, and `is_absolute`. The
`as_uri` and `drive` / `root` / `anchor` accessors are out of scope entirely
(meaningless for a rootless remote key). The follow-up that once tracked them
was retired for want of demand, so **this list is the durable record** rather
than a pointer into the backlog. Each member would need its own `PATH-NNN`
clause and spec-tagged test; file one per member if a concrete need appears.
