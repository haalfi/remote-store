# RemotePath Specification

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

**Invariant:** Path segments containing `..` are rejected.
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
