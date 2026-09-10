# HTTP Backend (Read-Only)

The HTTP backend reads files from HTTP/HTTPS URLs. Capabilities: `{READ, METADATA, LAZY_READ}` only — write, delete, list, move, and copy operations are not supported.

**Primary use cases:** government open data portals, dataset registries, static file servers, CDN-hosted assets, package archives, public APIs serving files.

## Usage

```
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

```
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

| Parameter       | Type             | Default      | Description                                                                       |
| --------------- | ---------------- | ------------ | --------------------------------------------------------------------------------- |
| `base_url`      | `str`            | *(required)* | Root URL. Trailing `/` is appended if missing.                                    |
| `headers`       | `dict[str, str]` | `None`       | Custom headers sent with every request (API keys, auth tokens).                   |
| `timeout`       | `float`          | `30.0`       | Request timeout in seconds.                                                       |
| `retry`         | `RetryPolicy`    | `None`       | Retry policy for transient errors (429, 5xx).                                     |
| `http_client`   | `str`            | `None`       | Force transport: `"urllib"`, `"requests"`, or `"httpx"`. Auto-detected if `None`. |
| `verify_ssl`    | `bool`           | `True`       | Whether to verify TLS certificates.                                               |
| `max_redirects` | `int`            | `5`          | Maximum number of HTTP redirects to follow.                                       |

## Capabilities

This is a read-only backend. Only read-related capabilities are supported. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

## HTTP Library

The backend auto-detects the best available HTTP library:

1. **httpx** (if installed) — connection pooling, HTTP/2. Install: `pip install "remote-store[httpx]"`
1. **requests** (if installed) — connection pooling, sessions. Install: `pip install "remote-store[requests]"`
1. **urllib** (always available) — stdlib, zero dependencies.

Override with `http_client="urllib"` (or `"requests"`, `"httpx"`).

## Folder Semantics

HTTP has no folder concept. `is_folder()` always returns `False`. `get_folder_info()` always raises `NotFound`.

## Metadata Mapping

`get_file_info()` maps HTTP response headers to `FileInfo` fields:

| FileInfo field | HTTP header                                  | Fallback             |
| -------------- | -------------------------------------------- | -------------------- |
| `size`         | `Content-Range` total, then `Content-Length` | `0`                  |
| `modified_at`  | `Last-Modified`                              | `datetime.min` (UTC) |
| `etag`         | `ETag`                                       | `None`               |
| `content_type` | `Content-Type`                               | `None`               |
| `extra`        | All headers                                  | `{"headers": {...}}` |

## CDN Compatibility

Some CDN-fronted servers (e.g. Cloudflare) return 403 on `HEAD` requests while allowing `GET`. The backend handles this transparently: when `HEAD` returns 401 or 403, it retries with `GET` + `Range: bytes=0-0` (downloading at most 1 byte). If the ranged `GET` succeeds, the backend remembers that HEAD is blocked and skips it for subsequent calls. This applies to `exists()`, `get_file_info()`, and `check_health()`.

If both `HEAD` and `GET` fail, the original error is raised.

Note that `check_health()` probes `base_url` (the root), not a specific file. Many HTTP servers and CDNs return 403 or 404 for directory URLs while serving individual files normally. A failing health check does not necessarily mean `read()` or `exists()` will fail on actual file paths.

## Composability

The primary value of making HTTP a backend (vs. standalone code):

- **`ext.cache`** — TTL-based caching of `read()` results. Avoids repeated downloads.
- **`ext.transfer`** — `download(store, "file.csv", local_path)` works out of the box.
- **`ext.observe`** — instrument HTTP reads with callbacks (timing, logging).
- **`ext.batch`** — `batch_exists(store, paths)` to check multiple resources.

## See also

- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/http-backend/index.md)
- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)

## API Reference

## ReadOnlyHttpBackend

```
ReadOnlyHttpBackend(
    base_url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    retry: RetryPolicy | None = None,
    http_client: str | None = None,
    verify_ssl: bool = True,
    max_redirects: int = 5,
)
```

Bases: `Backend`

Read-only backend for HTTP/HTTPS URLs.

Treats an HTTP endpoint as a file store with `{READ, METADATA, LAZY_READ}` capabilities (`read()` streams the response body lazily rather than buffering the whole file). Write, delete, list, move, and copy operations raise `CapabilityNotSupported`.

Parameters:

- **`base_url`** (`str`) – Root URL. A trailing / is appended if missing.
- **`headers`** (`dict[str, str] | None`, default: `None` ) – Custom headers sent with every request (e.g. API keys).
- **`timeout`** (`float`, default: `30.0` ) – Request timeout in seconds.
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Retry policy for transient errors.
- **`http_client`** (`str | None`, default: `None` ) – Force a specific transport ("urllib", "requests", or "httpx"). Auto-detected if None.
- **`verify_ssl`** (`bool`, default: `True` ) – Whether to verify TLS certificates.
- **`max_redirects`** (`int`, default: `5` ) – Maximum number of redirects to follow.

### exists

```
exists(path: str) -> bool
```

Check existence via HEAD request (falls back to ranged GET).

### is_file

```
is_file(path: str) -> bool
```

HTTP resources are always files.

### is_folder

```
is_folder(path: str) -> bool
```

HTTP has no folder concept — always returns False.

### read

```
read(path: str) -> BinaryIO
```

Stream-read a file via GET.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Buffered-read a file via GET.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Get file metadata via HEAD request (falls back to ranged GET).

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

HTTP has no folder concept — always raises NotFound.

### check_health

```
check_health() -> None
```

Verify connectivity by sending HEAD to base_url (or GET if HEAD is blocked).

Note

The health check probes `base_url` (the root), not a specific file. Many HTTP servers and CDNs return 403 or 404 for directory URLs while serving individual files normally. A failing health check therefore does not necessarily mean `read()` or `exists()` will fail on actual file paths.

### close

```
close() -> None
```

Close the underlying transport.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the transport if it matches the requested type.

### native_path

```
native_path(path: str) -> str
```

Return the full URL for a backend-relative key.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with HTTP-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="http" and details containing
- `ResolutionPlan` – url and method.

### to_key

```
to_key(native_path: str) -> str
```

Strip base_url prefix to get a backend-relative key.
