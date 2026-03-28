# SQL Query Backend

The SQL query backend is a read-only materializer that maps path keys to SQL queries. On `read()`, it executes the query and serializes the result set to Parquet, CSV, or Arrow IPC based on the key's file extension.

**Primary use cases:** exposing SQL query results as portable data products, on-demand materialization of views and reports, bridging SQL databases into the Store abstraction for consumers who don't need to know the source is a database.

## Installation

```bash
pip install remote-store[sql-query]
```

Requires `sqlalchemy>=2.0` and `pyarrow>=12.0.0`.

## Usage

```python
from remote_store import Store
from remote_store.backends import SQLQueryBackend

backend = SQLQueryBackend(
    url="sqlite:///analytics.db",
    queries={
        "reports/daily_sales.parquet": "SELECT date, SUM(amount) FROM orders GROUP BY date",
        "reports/user_summary.csv": "SELECT * FROM user_summary_mv",
    },
)
store = Store(backend=backend)

# Read executes the query and serializes to the format implied by the extension
data = store.read_bytes("reports/daily_sales.parquet")  # Parquet bytes
```

## Key-to-query resolution

Keys are resolved by exact lookup in the `queries` dict. The serialization format is determined by the file extension:

| Extension | Format |
|-----------|--------|
| `.parquet` | Apache Parquet |
| `.csv` | CSV |
| `.arrow`, `.ipc` | Arrow IPC |

## Strict mode

`strict=True` (default) restricts resolution to the explicit `queries` dict only. View-based and convention-based discovery (`strict=False`) are planned for a future release.

## Capabilities

`READ`, `LIST`, `METADATA`, `GLOB`, `SEEKABLE_READ`. All write operations raise `CapabilityNotSupported`.

## Custom serializers

The `ResultSerializer` protocol allows custom serialization:

```python
from remote_store.backends import ArrowSerializer, SQLQueryBackend

# Use the built-in ArrowSerializer (default)
backend = SQLQueryBackend(url="sqlite:///db.sqlite", queries={...})

# Or provide a custom serializer
backend = SQLQueryBackend(url="sqlite:///db.sqlite", queries={...}, serializer=my_serializer)
```

## Engine lifecycle

Same as SQL Blob backend --- accepts either a URL string (creates and owns the engine) or a pre-existing `sqlalchemy.Engine` (borrows it). See [SQL Blob Backend](sql-blob.md#engine-lifecycle) for details.
