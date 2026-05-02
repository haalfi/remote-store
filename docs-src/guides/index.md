# Guides

Guides are task-oriented. They answer "how do I do X with `remote-store`?" and
assume you are already familiar with the basics from the
[Tutorial](../tutorial/). Pick the guide that matches your task.

## Backends

`remote-store` connects to different storage systems through pluggable backends.
Each backend implements the same `Store` API — switching storage takes a config
change, not a code rewrite.

- [Choosing a Backend](choosing-a-backend.md) — compare backends by capability and use case
- [Backends](backends/) — per-backend guides: Local filesystem, Memory, HTTP/HTTPS, S3, S3 (PyArrow), SFTP, Azure Blob / ADLS, SQL Blob, SQL Query

## Extensions

Extensions add optional capabilities to `Store`. Install the relevant extra,
wrap your store, and the new capability becomes available through the same API.

- [Extensions overview](extensions.md) — what is available and when to use each
- [Batch Operations](batch-operations.md) — read or write many files in one call
- [Caching](cache.md) — transparent read cache with a pluggable backing store
- [Write Integrity](write-integrity.md) — hash verification on upload
- [Glob Pattern Matching](glob-pattern-matching.md) — `**` pattern listing across backends
- [Transfer Operations](transfer-operations.md) — copy files between two backends
- [Observability](observe.md) — hook into reads, writes, and deletes for metrics or logging
- [Retry Policy](retry.md) — automatic retry with backoff
- [Health Check](health-check.md) — liveness probes for any backend

## Async and Data Formats

- [Async Store](async.md) — `AsyncStore`, task batching, and async context managers
- [Async/Sync Bridges](async-sync-bridges.md) — mix async and sync code safely
- [PyArrow Adapter](pyarrow-adapter.md) — use `Store` as a PyArrow filesystem
- [Parquet Datasets](parquet-datasets.md) — read and write partitioned Parquet datasets
- [Dagster IO Manager](dagster.md) — I/O managers for Dagster pipelines
- [Data Lake Patterns](data-lake-patterns.md) — partitioning, manifests, and Delta patterns

## Reference and Troubleshooting

- [Troubleshooting](troubleshooting.md) — common errors, causes, and fixes
- [Build Your Own Backend](custom-backend-guide.md) — implement a custom storage backend
