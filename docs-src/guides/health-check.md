# Health Check

Verify backend connectivity and credentials before your application starts
processing requests.

## Quick start

```python
from remote_store import Store
from remote_store.backends import LocalBackend

store = Store(LocalBackend(root="/data/inbox"))
store.ping()  # raises on failure, silent on success
```

## Use cases

- **Startup gates** — fail fast before accepting traffic if the backend is
  unreachable or credentials are invalid.
- **Liveness probes** — Kubernetes `livenessProbe` or similar health endpoints.
- **Connection validation** — verify config after loading from TOML/YAML.

## Error handling

`ping()` raises the same exceptions as other Store operations:

| Exception | Meaning |
|-----------|---------|
| `PermissionDenied` | Invalid credentials or insufficient permissions |
| `NotFound` | Bucket, container, or root directory does not exist |
| `BackendUnavailable` | Network error, DNS failure, or timeout |

```python
from remote_store import BackendUnavailable, NotFound, PermissionDenied

try:
    store.ping()
except PermissionDenied:
    log.error("Bad credentials for %s", store)
except NotFound:
    log.error("Missing bucket/container for %s", store)
except BackendUnavailable:
    log.error("Backend unreachable for %s", store)
```

## Per-backend strategies

Each backend uses the cheapest possible read-only operation:

| Backend | Operation | What it validates |
|---------|-----------|-------------------|
| [Local](backends/local.md) | `root.exists()` + `os.access(R_OK)` | Directory exists and is readable |
| [Memory](backends/memory.md) | No-op | Always healthy |
| [S3](backends/s3.md) | `head_bucket` | Bucket exists, credentials valid |
| [S3-PyArrow](backends/s3-pyarrow.md) | `get_file_info(bucket)` | Bucket accessible via PyArrow |
| [Azure](backends/azure.md) | `get_container_properties()` | Container exists, credentials valid |
| [Graph](backends/graph.md) | No-op ¹ | Nothing — see below |
| [SFTP](backends/sftp.md) | `stat(base_path)` | SSH connection, path exists |
| [HTTP](backends/http.md) | `HEAD` to `base_url` (falls back to `GET`) | Server reachable |
| [SQLBlob](backends/sql-blob.md) | `SELECT 1` | Database connection valid |
| [SQLQuery](backends/sql-query.md) | `SELECT 1` | Database connection valid |

¹ Graph does not override the default health check, so `ping()` succeeds
without contacting Microsoft Graph. Unlike Memory — where "always healthy" is
the truth — a successful `ping()` on Graph carries no information about
reachability or credential validity. Issue a real read if you need to know.

## Observability

`ping()` integrates with `ext.observe`:

```python
from remote_store.ext.observe import observe

def on_ping(event):
    print(f"Ping took {event.duration_ms:.1f}ms")

observed = observe(store, on_ping=on_ping)
observed.ping()
```

## Design notes

- **No return value** — success is silent (`None`), failure raises. This
  matches the Go convention of `Ping() error` and keeps the API minimal.
- **No caching** — every call performs a real connectivity check.
- **No timeout parameter** — use backend-level timeouts (e.g. `RetryPolicy`).
- **Not capability-gated** — all backends support health checks.

## See also

- [API reference](../reference/api/store.md) — `Store.ping()` method
- [Backends guide](backends/index.md) — per-backend configuration and timeouts
