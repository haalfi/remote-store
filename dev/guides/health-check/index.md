# Health Check

Verify backend connectivity and credentials before your application starts processing requests.

## Quick start

```
from remote_store import Store
from remote_store.backends import LocalBackend

store = Store(LocalBackend(root="/data/inbox"))
store.ping()  # raises on failure, silent on success
```

## Use cases

- **Startup gates** — fail fast before accepting traffic if the backend is unreachable or credentials are invalid.
- **Liveness probes** — Kubernetes `livenessProbe` or similar health endpoints.
- **Connection validation** — verify config after loading from TOML/YAML.

## Error handling

`ping()` raises the same exceptions as other Store operations:

| Exception            | Meaning                                             |
| -------------------- | --------------------------------------------------- |
| `PermissionDenied`   | Invalid credentials or insufficient permissions     |
| `NotFound`           | Bucket, container, or root directory does not exist |
| `BackendUnavailable` | Network error, DNS failure, or timeout              |

```
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

| Backend                                                                               | Operation                                  | What it validates                   |
| ------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------------- |
| [Local](https://docs.remotestore.dev/stable/guides/backends/local/index.md)           | `root.exists()` + `os.access(R_OK)`        | Directory exists and is readable    |
| [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md)         | No-op                                      | Always healthy                      |
| [S3](https://docs.remotestore.dev/stable/guides/backends/s3/index.md)                 | `head_bucket`                              | Bucket exists, credentials valid    |
| [S3-PyArrow](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) | `get_file_info(bucket)`                    | Bucket accessible via PyArrow       |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md)           | `get_container_properties()`               | Container exists, credentials valid |
| [Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)           | `GET /drives/{id}/root`                    | Drive reachable, credentials valid  |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md)             | `stat(base_path)`                          | SSH connection, path exists         |
| [HTTP](https://docs.remotestore.dev/stable/guides/backends/http/index.md)             | `HEAD` to `base_url` (falls back to `GET`) | Server reachable                    |
| [SQLBlob](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md)      | `SELECT 1`                                 | Database connection valid           |
| [SQLQuery](https://docs.remotestore.dev/stable/guides/backends/sql-query/index.md)    | `SELECT 1`                                 | Database connection valid           |

Graph probes the effective root: `GET /drives/{id}/root` when no `base_path` is configured, or the `base_path` folder item when one is pinned. A missing/unreachable drive raises `BackendUnavailable`; a missing `base_path` root raises `NotFound`.

## Observability

`ping()` integrates with `ext.observe`:

```
from remote_store.ext.observe import observe

def on_ping(event):
    print(f"Ping took {event.duration_ms:.1f}ms")

observed = observe(store, on_ping=on_ping)
observed.ping()
```

## Design notes

- **No return value** — success is silent (`None`), failure raises. This matches the Go convention of `Ping() error` and keeps the API minimal.
- **No caching** — every call performs a real connectivity check.
- **No timeout parameter** — use backend-level timeouts (e.g. `RetryPolicy`).
- **Not capability-gated** — all backends support health checks.

## See also

- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md) — `Store.ping()` method
- [Backends guide](https://docs.remotestore.dev/stable/guides/backends/index.md) — per-backend configuration and timeouts
