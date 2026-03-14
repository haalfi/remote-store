"""Partition helpers -- Hive-style partition path building and parsing.

Utilities for constructing and deconstructing partition paths like
``year=2026/month=03/day=01/data.parquet``, commonly used in Parquet
data lake workflows.

Usage:

```python
from remote_store.ext.partition import partition_path, parse_partition

path = partition_path("data.parquet", year=2026, month="03")
# -> "year=2026/month=03/data.parquet"

parsed = parse_partition(path)
# -> ParsedPartition(partitions={"year": "2026", "month": "03"},
#                     filename="data.parquet")
```
"""

from __future__ import annotations

import dataclasses

__all__ = ["ParsedPartition", "parse_partition", "partition_path"]


@dataclasses.dataclass(frozen=True)
class ParsedPartition:
    """Result of parsing a Hive-style partition path.

    Attributes:
        partitions: Ordered mapping of partition column names to values.
        filename: The trailing non-partition portion of the path.
    """

    partitions: dict[str, str]
    filename: str


def partition_path(filename: str, /, **partitions: str | int) -> str:
    """Build a Hive-style partition path.

    Args:
        filename: Leaf file name (e.g., ``"data.parquet"``).
            Must be non-empty and must not contain ``/``.
        partitions: Partition key-value pairs. Values are coerced to
            ``str``. Keys and coerced values must be non-empty.

    Returns:
        Forward-slash-joined path like ``"year=2026/month=03/data.parquet"``.

    Raises:
        ValueError: If *filename* is empty or contains ``/``, or if
            any partition key or coerced value is empty.
    """
    if not filename:
        msg = "filename must be non-empty"
        raise ValueError(msg)
    if "/" in filename:
        msg = f"filename must not contain '/': {filename!r}"
        raise ValueError(msg)

    segments: list[str] = []
    for key, value in partitions.items():
        if not key:
            msg = "partition key must be non-empty"
            raise ValueError(msg)
        str_value = str(value)
        if not str_value:
            msg = f"partition value for {key!r} must be non-empty"
            raise ValueError(msg)
        if "=" in str_value:
            msg = f"partition value for {key!r} must not contain '=': {str_value!r}"
            raise ValueError(msg)
        segments.append(f"{key}={str_value}")

    segments.append(filename)
    return "/".join(segments)


def parse_partition(path: str) -> ParsedPartition:
    """Parse a Hive-style partition path into its components.

    A segment is treated as a partition if it contains exactly one ``=``
    and the key portion is non-empty.  Once a non-partition segment is
    encountered, all remaining segments (including any later ``key=value``
    segments) become part of the filename.

    Args:
        path: The partition path to parse (e.g.,
            ``"year=2026/month=03/data.parquet"``).

    Returns:
        A ``ParsedPartition`` with extracted partitions and filename.

    Raises:
        ValueError: If *path* is empty.
    """
    if not path:
        msg = "path must be non-empty"
        raise ValueError(msg)

    segments = path.split("/")
    partitions: dict[str, str] = {}
    filename_start = len(segments)

    for i, segment in enumerate(segments):
        if _is_partition_segment(segment):
            key, _, value = segment.partition("=")
            partitions[key] = value
        else:
            filename_start = i
            break

    filename = "/".join(segments[filename_start:])
    return ParsedPartition(partitions=dict(partitions), filename=filename)


def _is_partition_segment(segment: str) -> bool:
    """Return True if *segment* looks like ``key=value``."""
    eq_idx = segment.find("=")
    # Exactly one '=' with non-empty key portion
    return eq_idx > 0 and segment.count("=") == 1
