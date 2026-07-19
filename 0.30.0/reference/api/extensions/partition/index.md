# ext.partition

## partition

Partition helpers -- Hive-style partition path building and parsing.

Utilities for constructing and deconstructing partition paths like `year=2026/month=03/day=01/data.parquet`, commonly used in Parquet data lake workflows.

Example

```
from remote_store.ext.partition import partition_path, parse_partition

path = partition_path("data.parquet", year=2026, month="03")
# -> "year=2026/month=03/data.parquet"

parsed = parse_partition(path)
# -> ParsedPartition(partitions={"year": "2026", "month": "03"},
#                     filename="data.parquet")
```

### ParsedPartition

```
ParsedPartition(partitions: dict[str, str], filename: str)
```

Result of parsing a Hive-style partition path.

Attributes:

- **`partitions`** (`dict[str, str]`) – Ordered mapping of partition column names to values.
- **`filename`** (`str`) – The trailing non-partition portion of the path.

### partition_path

```
partition_path(
    filename: str, /, **partitions: str | int
) -> str
```

Build a Hive-style partition path.

Parameters:

- **`filename`** (`str`) – Leaf file name (e.g., "data.parquet"). Must be non-empty and must not contain /.
- **`partitions`** (`str | int`, default: `{}` ) – Partition key-value pairs. Values are coerced to str. Keys and coerced values must be non-empty and must not contain =.

Returns:

- `str` – Forward-slash-joined path like "year=2026/month=03/data.parquet".

Raises:

- `ValueError` – If filename is empty or contains /, if any partition key or coerced value is empty, or if any key or value contains =.

### parse_partition

```
parse_partition(path: str) -> ParsedPartition
```

Parse a Hive-style partition path into its components.

A segment is treated as a partition if it contains exactly one `=` and the key portion is non-empty. Once a non-partition segment is encountered, all remaining segments (including any later `key=value` segments) become part of the filename.

Parameters:

- **`path`** (`str`) – The partition path to parse (e.g., "year=2026/month=03/data.parquet").

Returns:

- `ParsedPartition` – A ParsedPartition with extracted partitions and filename.

Raises:

- `ValueError` – If path is empty.

## See also

- [Data Lake Patterns](https://docs.remotestore.dev/stable/guides/data-lake-patterns/index.md) — guide to Hive-style partitioning and data lake layouts
