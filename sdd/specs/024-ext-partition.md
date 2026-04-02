# ext.partition - Hive-Style Partition Path Helpers Specification

## Overview

`ext.partition` provides utilities for building and parsing Hive-style partition
paths (e.g., `year=2026/month=03/day=01/data.parquet`), commonly used in
Parquet data lake workflows alongside PyArrow datasets.

Two functions: `partition_path()` builds a full path from a filename and
partition key-value pairs, `parse_partition()` extracts partition pairs from
a path string.

**Module:** `src/remote_store/ext/partition.py`
**Dependencies:** None (pure Python, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API),
[014-pyarrow-filesystem-adapter.md](014-pyarrow-filesystem-adapter.md) (PyArrow adapter),
ID-036, data-lake patterns guide.

---

## Requirements

### PART-001: partition_path() Signature

**Invariant:** `partition_path(filename: str, /, **partitions: str | int) -> str`.

- `filename`: The leaf file name (e.g., `"data.parquet"`).
- `**partitions`: Keyword arguments for partition columns. Values are
  coerced to `str`.
- Returns a forward-slash-joined path: `col1=val1/col2=val2/.../filename`.

### PART-002: partition_path() Column Ordering

**Invariant:** Partition columns appear in `**kwargs` insertion order (Python
3.7+ dict ordering guarantee). The same keyword arguments always produce the
same path.

### PART-003: partition_path() Value Coercion

**Invariant:** Integer values are converted via `str()`. The resulting segment
is `key=str(value)`. No padding, quoting, or escaping is applied.

### PART-004: partition_path() Empty Partitions

**Invariant:** When no `**partitions` are given, `partition_path(filename)`
returns `filename` unchanged.

### PART-005: partition_path() Validation — filename

**Invariant:** `filename` must be a non-empty string containing no `/`
characters. Raises `ValueError` if empty or contains `/`.

### PART-006: partition_path() Validation — keys

**Invariant:** Partition keys must be non-empty strings and must not
contain `=`. Partition values must be non-empty after `str()` coercion
and must not contain `=` (breaks round-trip parsing per PART-011 /
PART-008). Raises `ValueError` on empty key, key containing `=`, empty
value, or value containing `=`.

### PART-007: parse_partition() Signature

**Invariant:** `parse_partition(path: str) -> ParsedPartition`.

`ParsedPartition` is a frozen dataclass with:
- `partitions: dict[str, str]` — ordered mapping of column names to values.
- `filename: str` — the trailing non-partition segment (may be empty if the
  path consists only of partition segments).

### PART-008: parse_partition() Segment Matching

**Invariant:** A path segment is a partition segment if and only if it
contains exactly one `=` character and the portion before `=` is non-empty.
Segments not matching this pattern are treated as the filename.

### PART-009: parse_partition() Multiple Non-Partition Segments

**Invariant:** Only the final contiguous group of non-partition segments
is treated as the filename (joined with `/`). All `key=value` segments
preceding the filename are treated as partitions. If a `key=value` segment
appears after a non-partition segment, it is part of the filename, not a
partition.

### PART-010: parse_partition() Empty Path

**Invariant:** Raises `ValueError` when `path` is empty.

### PART-011: parse_partition() Round-Trip

**Invariant:** For a path built by `partition_path()`, `parse_partition()`
recovers the same partitions and filename:

```python
path = partition_path("data.parquet", year="2026", month="03")
parsed = parse_partition(path)
assert parsed.partitions == {"year": "2026", "month": "03"}
assert parsed.filename == "data.parquet"
```

### PART-012: ParsedPartition Dataclass

**Invariant:** `ParsedPartition` is a frozen dataclass. `partitions` is a
plain `dict` (not a view or proxy). Mutation of the returned dict does not
affect the original.

### PART-013: Module Exports

**Invariant:** `__all__ = ["ParsedPartition", "parse_partition", "partition_path"]`.
All three symbols are re-exported unconditionally from `remote_store.__init__`.
