# HTTP Backend (Read-Only)

The HTTP backend reads files from HTTP/HTTPS URLs. Capabilities: `{READ, METADATA, LAZY_READ}` only -- write, delete, list, move, and copy operations are not supported.

**Primary use cases:** government open data portals, dataset registries, static file servers, CDN-hosted assets, package archives, public APIs serving files.

## Usage

```python
from remote_store import Store
from remote_store.backends import ReadOnlyHttpBackend

backend = ReadOnlyHttpBackend(
    base_url="https://data.example.com/datasets/",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)
store = Store(backend=backend)

content = store.read_bytes("population/2024.csv")
info = store.get_file_info("population/2024.csv")
print(f"Size: {info.size}, Modified: {info.modified_at}")
```

### Via Registry

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "opendata": BackendConfig(
            type="http",
            options={
                "base_url": "https://data.example.com/datasets/",
                "timeout": 60,
                "headers": {"X-API-Key": "YOUR_KEY"},
            },
        ),
    },
    stores={"data": StoreProfile(backend="opendata")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    content = store.read_bytes("population/2024.csv")
```

## Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | *(required)* | Root URL. Trailing `/` is appended if missing. |
| `headers` | `dict[str, str]` | `None` | Custom headers sent with every request (API keys, auth tokens). |
| `timeout` | `float` | `30.0` | Request timeout in seconds. |
| `retry` | `RetryPolicy` | `None` | Retry policy for transient errors (429, 5xx). |
| `http_client` | `str` | `None` | Force transport: `"urllib"`, `"requests"`, or `"httpx"`. Auto-detected if `None`. |
| `verify_ssl` | `bool` | `True` | Whether to verify TLS certificates. |
| `max_redirects` | `int` | `5` | Maximum number of HTTP redirects to follow. |

## Capabilities

This is a read-only backend. Only read-related capabilities are supported.
See the [capabilities matrix](../capabilities-matrix.md) for full details.

## HTTP Library

The backend auto-detects the best available HTTP library:

1. **httpx** (if installed) -- connection pooling, HTTP/2. Install: `pip install "remote-store[httpx]"`
2. **requests** (if installed) -- connection pooling, sessions. Install: `pip install "remote-store[requests]"`
3. **urllib** (always available) -- stdlib, zero dependencies.

Override with `http_client="urllib"` (or `"requests"`, `"httpx"`).

## Folder Semantics

HTTP has no folder concept. `is_folder()` always returns `False`. `get_folder_info()` always raises `NotFound`.

## Metadata Mapping

`get_file_info()` maps HTTP response headers to `FileInfo` fields:

| FileInfo field | HTTP header | Fallback |
|---|---|---|
| `size` | `Content-Range` total, then `Content-Length` | `0` |
| `modified_at` | `Last-Modified` | `datetime.min` (UTC) |
| `etag` | `ETag` | `None` |
| `content_type` | `Content-Type` | `None` |
| `extra` | All headers | `{"headers": {...}}` |

## CDN Compatibility

Some CDN-fronted servers (e.g. Cloudflare) return 403 on `HEAD` requests while
allowing `GET`. The backend handles this transparently: when `HEAD` returns
401 or 403, it retries with `GET` + `Range: bytes=0-0` (downloading at most
1 byte). If the ranged `GET` succeeds, the backend remembers that HEAD is
blocked and skips it for subsequent calls. This applies to `exists()`,
`get_file_info()`, and `check_health()`.

If both `HEAD` and `GET` fail, the original error is raised.

Note that `check_health()` probes `base_url` (the root), not a specific file.
Many HTTP servers and CDNs return 403 or 404 for directory URLs while serving
individual files normally. A failing health check does not necessarily mean
`read()` or `exists()` will fail on actual file paths.

## Composability

The primary value of making HTTP a backend (vs. standalone code):

- **`ext.cache`** -- TTL-based caching of `read()` results. Avoids repeated downloads.
- **`ext.transfer`** -- `download(store, "file.csv", local_path)` works out of the box.
- **`ext.observe`** -- instrument HTTP reads with callbacks (timing, logging).
- **`ext.batch`** -- `batch_exists(store, paths)` to check multiple resources.

## See also

- [Example script](../examples/http-backend.md)
- [Capabilities matrix](../capabilities-matrix.md)
- [API reference](../api/store.md)
