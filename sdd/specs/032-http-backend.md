# HTTP Backend Specification

## Overview

`ReadOnlyHttpBackend` implements the `Backend` ABC for reading files from
HTTP/HTTPS URLs. It treats an HTTP endpoint as a read-only file store,
enabling the same `Store` interface and extension composability (`ext.cache`,
`ext.transfer`, `ext.observe`, `ext.batch`) as other backends.

**Capability set:** `{READ, METADATA, LAZY_READ}`

**Primary use cases:** government open data portals, dataset registries,
static file servers, CDN-hosted assets, package archives, public APIs
serving files.

**Dependencies:** None (stdlib `urllib.request` as baseline).
**Optional extras:** `pip install "remote-store[requests]"` or
`pip install "remote-store[httpx]"` for connection pooling and advanced
features.

---

## Construction

### HTTP-CON-001: Constructor Parameters

**Invariant:** `ReadOnlyHttpBackend` is constructed with a required `base_url`
and optional configuration parameters.
**Signature:**
```python
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
**Postconditions:**
- `base_url` is normalized to always end with `/`.
- Transport is selected based on `http_client` or auto-detected
  (httpx -> requests -> urllib).
- No network call occurs during `__init__`.

### HTTP-CON-002: Base URL Trailing-Slash Normalization

**Invariant:** The constructor appends `/` to `base_url` if not already
present.
**Rationale:** Avoids the `urljoin` footgun where
`urljoin("https://example.com/data", "file.csv")` replaces the last segment
instead of appending.

### HTTP-CON-003: Backend Name

**Invariant:** `name` property returns `"http"`.

### HTTP-CON-004: Capability Declaration

**Invariant:** `capabilities` returns `CapabilitySet({Capability.READ,
Capability.METADATA, Capability.LAZY_READ})`.
**Rationale:** HTTP endpoints are read-only. No reliable server-side
mechanism exists for LIST, MOVE, COPY, DELETE, or WRITE operations across
arbitrary HTTP servers. `LAZY_READ` is declared because `read()` returns a
live streamed response body (urllib's response, or `requests`/`httpx` with
`stream=True`) rather than pre-loading the full file into memory.

---

## Transport Abstraction

### HTTP-TR-001: Transport Protocol

**Invariant:** The backend delegates HTTP operations to an internal transport
conforming to the `HttpTransport` protocol:
```python
class HttpTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse: ...
    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse: ...
    def close(self) -> None: ...
```
The `HttpResponse` dataclass carries `status: int`, `headers: dict[str, str]`,
and `body: BinaryIO`.

### HTTP-TR-002: Transport Auto-Detection

**Invariant:** When `http_client` is `None`, the backend selects the best
available transport: httpx (if installed) -> requests (if installed) -> urllib
(always available).
**Rationale:** Users get the best available HTTP library without explicit
configuration. Connection pooling and HTTP/2 are automatic when httpx or
requests are installed.

### HTTP-TR-003: Explicit Transport Override

**Invariant:** When `http_client` is `"urllib"`, `"requests"`, or `"httpx"`,
the backend uses that transport exclusively. Raises `ImportError` if the
requested library is not installed.

---

## Path Semantics

### HTTP-PATH-001: URL Construction

**Invariant:** Request URLs are constructed as
`base_url + urllib.parse.quote(path, safe="/")`.
**Rationale:** Simple concatenation (not `urljoin`) avoids the trailing-slash
footgun. `quote(path, safe="/")` encodes special characters while preserving
path separators.

### HTTP-PATH-002: `native_path()`

**Invariant:** `native_path(path)` returns the full URL string
(e.g., `"https://data.example.com/datasets/population/2024.csv"`).

### HTTP-PATH-003: `to_key()`

**Invariant:** `to_key(native_path)` strips the `base_url` prefix and returns
the relative key. If `native_path` does not start with `base_url`, it is
returned unchanged.

### HTTP-PATH-004: Round-Trip

**Invariant:** `to_key(native_path(key)) == key` for all valid keys.

---

## Read Operations

### HTTP-READ-001: `read(path)` — Streaming Read

**Invariant:** Sends `GET base_url + path`. Returns the response body wrapped
in `_ErrorMappingStream`. The stream is non-seekable. Raises `NotFound` for
404, `PermissionDenied` for 401/403, `BackendUnavailable` for transient
errors.
**Rationale:** HTTP response streams are inherently non-seekable (SIO-001
allows this). Wrapping in `_ErrorMappingStream` maps transport exceptions to
remote-store errors during stream reads.

### HTTP-READ-002: `read_bytes(path)` — Buffered Read

**Invariant:** Sends `GET base_url + path`. Returns `response.body.read()` as
`bytes`. Same error mapping as `read()`.

---

## Existence Checks

### HTTP-EXIST-001: `exists(path)`

**Invariant:** Sends `HEAD base_url + path`. Returns `True` for HTTP 200,
`False` for 404. On 401/403, falls back per HTTP-FALLBACK-001 before raising.
Other errors raise the mapped exception.

### HTTP-EXIST-002: `is_file(path)`

**Invariant:** Same as `exists(path)`. HTTP resources are always "files".

### HTTP-EXIST-003: `is_folder(path)`

**Invariant:** Always returns `False`.
**Rationale:** HTTP has no folder concept. Without LIST capability, there are
no known prefixes to check against.

---

## Metadata

### HTTP-META-001: `get_file_info(path)`

**Invariant:** Sends `HEAD base_url + path` (falls back per HTTP-FALLBACK-001
on 401/403). Maps response headers to `FileInfo`:

| FileInfo field | HTTP header | Fallback when missing |
|---|---|---|
| `path` | From request path | Always available |
| `name` | From path | Always available |
| `size` | `Content-Range` total, then `Content-Length` | `0` |
| `modified_at` | `Last-Modified` | `datetime.min.replace(tzinfo=timezone.utc)` |
| `etag` | `ETag` | `None` |
| `content_type` | `Content-Type` | `None` |
| `extra` | All response headers | `{"headers": dict(response.headers)}` |

Raises `NotFound` for 404.

### HTTP-META-002: `get_folder_info(path)`

**Invariant:** Always raises `NotFound`.
**Rationale:** Consistent with `is_folder()` returning `False`. No folder
metadata can be computed without LIST capability.

### HTTP-META-003: Known Limitations — Missing Headers

**Invariant:** When `Content-Length` is absent (chunked transfer, dynamic
content), `size` is `0`. When `Last-Modified` is absent, `modified_at` is
`datetime.min` (UTC). Both are documented known limitations.
**Rationale:** `FileInfo.size` and `modified_at` are non-optional `int` and
`datetime` respectively. A future `FileInfo` revision may make these optional.

---

## Unsupported Operations

### HTTP-UNSUP-001: Write, Delete, List, Move, Copy

**Invariant:** The following methods raise `CapabilityNotSupported`:
`write()`, `write_atomic()`, `open_atomic()`, `delete()`, `delete_folder()`,
`list_files()`, `list_folders()`, `iter_children()`, `move()`, `copy()`.
**Rationale:** The backend is read-only. `iter_children()` overrides the
default implementation (which calls `list_files` + `list_folders`) to raise
directly, avoiding confusing intermediate errors.

---

## Error Mapping

### HTTP-ERR-001: HTTP Status to Remote-Store Error

**Invariant:**

| HTTP Status | remote-store Error |
|---|---|
| 200, 204 | Success |
| 301, 302, 307, 308 | Follow redirect (up to `max_redirects` limit) |
| 401, 403 | `PermissionDenied(path=..., backend="http")` |
| 404 | `NotFound(path=..., backend="http")` |
| 408, 429, 500, 502, 503, 504 | `BackendUnavailable(backend="http")` |
| Other 4xx/5xx | `RemoteStoreError(path=..., backend="http")` |

### HTTP-ERR-002: Connection Errors

**Invariant:** Network-level failures (DNS resolution, connection refused,
timeout) raise `BackendUnavailable`.

---

## HEAD Fallback

### HTTP-FALLBACK-001: Ranged GET Fallback for HEAD-Blocked Servers

**Invariant:** When `HEAD` returns 401 or 403, `exists()`, `get_file_info()`,
and `check_health()` retry with `GET` + `Range: bytes=0-0` (single byte).
If the `GET` succeeds (2xx) or returns 404, the result is used and the backend
caches the fact that HEAD is blocked for its remaining lifetime. If `GET` also
returns 401/403, the original `PermissionDenied` (or `BackendUnavailable` for
health checks) is raised.

**Rationale:** Some CDN-fronted servers (e.g. Cloudflare) return 403 on HEAD
while allowing GET. A ranged GET downloads at most 1 byte, making it a cheap
probe. Caching avoids redundant HEAD requests on subsequent calls.

For ranged GET responses (HTTP 206), `Content-Range` total takes precedence
over `Content-Length` when building `FileInfo.size` (the latter reflects the
byte range, not the full file).

---

## Health Check

### HTTP-HEALTH-001: `check_health()`

**Invariant:** Sends `HEAD base_url` (falls back per HTTP-FALLBACK-001 on
401/403). Raises `BackendUnavailable` if the request fails (network error or
non-2xx status).

---

## Lifecycle

### HTTP-LIFE-001: `close()`

**Invariant:** Closes the underlying transport (connection pool for
requests/httpx, no-op for urllib). Safe to call multiple times.

### HTTP-LIFE-002: `unwrap(type_hint)`

**Invariant:** Returns the underlying transport object if `type_hint` matches
the transport type (e.g., `unwrap(httpx.Client)`). Raises
`CapabilityNotSupported` otherwise.

---

## Credential Hygiene

### HTTP-CRED-001: `__repr__` Masks Secrets

**Invariant:** `repr()` output never includes header values. Header keys are
shown but values are masked as `"***"`.
**Rationale:** AF-008 conformance. Headers commonly contain API keys and auth
tokens.

---

## Retry Policy

### HTTP-RETRY-001: Retry Integration

**Invariant:** When `retry` is provided, transient errors (HTTP 429, 500, 502,
503, 504 and connection errors) are retried according to `RetryPolicy` fields:
`max_attempts`, `backoff_base`, `backoff_max`, `jitter`, `timeout`. The
`Retry-After` header is honoured when present.
