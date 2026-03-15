# Research: Read-Only HTTP Backend

**Item ID:** ID-082
**Date:** 2026-03-15
**Status:** Research draft — open for discussion

---

## 1. Problem Statement

Many useful data sources are exposed as static files or simple HTTP APIs:
government open data portals (opendata.swiss, data.gov), dataset registries,
static file servers, CDN-hosted assets, package registries, etc.

Today, consuming these in remote-store requires downloading files first and
pointing a `LocalBackend` at them — or writing ad-hoc `requests` code outside
the store abstraction entirely. This means users lose composability with
extensions like `ext.cache`, `ext.transfer`, `ext.observe`, and `ext.batch`.

A `ReadOnlyHttpBackend` would bring HTTP-hosted content into the store
abstraction with minimal capabilities: **READ** and **METADATA**, and
optionally **LIST** where the server supports directory-style listings.

### Why a backend, not an extension?

An extension cannot provide `Store.read()` — it would need to reimplement the
entire `Store` interface. A backend slots into the existing architecture
naturally: capability gating, error mapping, registry lifecycle, and all
extensions work out of the box.

### Design constraints

- Core package has **zero runtime dependencies** (`dependencies = []`).
- HTTP library must be optional (`urllib` from stdlib as baseline, `requests`
  or `httpx` as optional extras).
- The backend is **read-only** — write, delete, move, copy operations raise
  `CapabilityNotSupported`.
- Must handle real-world HTTP concerns: redirects, content-type, timeouts,
  retries, auth headers.

---

## 2. Capability Profile

| Capability     | Supported | Notes |
|----------------|:---------:|-------|
| READ           | Yes       | Core value: `GET` request, return body as stream |
| WRITE          | No        | Raises `CapabilityNotSupported` |
| DELETE         | No        | Raises `CapabilityNotSupported` |
| LIST           | Maybe     | Only if server exposes an index (see §5) |
| MOVE           | No        | Raises `CapabilityNotSupported` |
| COPY           | No        | Raises `CapabilityNotSupported` |
| ATOMIC_WRITE   | No        | Raises `CapabilityNotSupported` |
| METADATA       | Yes       | `HEAD` request → size, content-type, last-modified, ETag |
| GLOB           | No        | No server-side pattern matching |

**Minimum capability set:** `{READ, METADATA}`
**Extended capability set:** `{READ, METADATA, LIST}` (when listing is available)

This would be the first backend with fewer than 8 capabilities. The capability
system already handles this — `Store` gates every operation and raises
`CapabilityNotSupported` with clear context.

---

## 3. Path Semantics

### 3.1 Base URL + relative path

The backend takes a `base_url` at construction. Paths are appended:

```python
backend = ReadOnlyHttpBackend(base_url="https://data.example.com/datasets/")
# store.read("population/2024.csv")
# → GET https://data.example.com/datasets/population/2024.csv
```

Path joining uses `urllib.parse.urljoin` with care for trailing slashes.

### 3.2 Path validation

- Standard remote-store path rules apply (no `..`, no null bytes, no absolute
  paths).
- The backend does **not** URL-encode user-visible paths — encoding happens
  internally when constructing the request URL.

### 3.3 `native_path()` and `to_key()`

- `native_path(path)` → full URL string (e.g.,
  `"https://data.example.com/datasets/population/2024.csv"`)
- `to_key(native_path)` → strips `base_url` prefix, returns relative key

---

## 4. HTTP Library Strategy

### 4.1 Tiered approach (like S3 vs S3-PyArrow)

| Tier | Library | Dependency | Pros | Cons |
|------|---------|------------|------|------|
| **Baseline** | `urllib.request` | stdlib | Zero deps, always available | No connection pooling, clunky API, no async |
| **Standard** | `requests` | optional extra | Industry standard, sessions, auth adapters | Sync only, heavy dep tree |
| **Advanced** | `httpx` | optional extra | Sync + async, HTTP/2, modern API | Newer, smaller ecosystem |

### 4.2 Recommendation

**Single backend, pluggable transport.** Rather than separate backends per HTTP
library (the S3 vs S3-PyArrow model), use a single `ReadOnlyHttpBackend` that
auto-detects the best available library at init:

1. If `httpx` is installed → use it (best feature set)
2. Else if `requests` is installed → use it (most common)
3. Else → fall back to `urllib.request` (always available)

User can override: `ReadOnlyHttpBackend(base_url=..., http_client="urllib")`.

**Rationale:** Unlike S3 vs S3-PyArrow (which have fundamentally different I/O
models and performance profiles), the HTTP libraries are functionally
interchangeable for our needs. One backend with swappable transport is simpler
than three backends.

### 4.3 Transport abstraction

Internal protocol (not user-facing):

```python
class HttpTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse: ...
    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse: ...

@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: BinaryIO  # streaming body
```

Three implementations: `UrllibTransport`, `RequestsTransport`, `HttpxTransport`.

---

## 5. LIST Capability — The Hard Question

HTTP has no native directory listing. Options:

### 5.1 No LIST at all

Simplest. The backend declares `{READ, METADATA}` only. Users who need listing
use an external catalog (API, manifest file, database) to discover paths, then
`store.read()` each one.

**Pro:** Clean, honest, no hacks.
**Con:** Many real use cases need "give me all CSVs in this folder."

### 5.2 Manifest-based LIST

The backend reads a sidecar file (e.g., `_manifest.json`, `_index.txt`) that
lists available paths. The manifest is fetched on first `list_files()` call and
cached.

```json
// _manifest.json at base_url root
{
  "files": [
    {"path": "population/2024.csv", "size": 14200, "modified": "2024-01-15T10:00:00Z"},
    {"path": "population/2023.csv", "size": 13800, "modified": "2023-01-10T08:00:00Z"}
  ]
}
```

**Pro:** Works with any static file host. Users control the manifest.
**Con:** Requires manifest maintenance. Stale manifest = stale listing.

### 5.3 HTML index parsing

Some HTTP servers (Apache, nginx) serve directory listings as HTML. The backend
could parse `<a href="...">` links from `GET base_url/path/`.

**Pro:** Works with many static servers out of the box.
**Con:** Fragile (HTML parsing), unreliable (servers differ), security risk
(arbitrary HTML).

### 5.4 API-specific listing

For known APIs (CKAN, OData, S3-compatible), implement listing via the API's
native mechanism. This belongs in **extensions**, not the core backend.

### 5.5 Recommendation

**Start with no LIST.** The backend declares `{READ, METADATA}`. Add
manifest-based LIST later if demand justifies it, via an optional
`manifest_path` constructor argument that upgrades the capability set to
`{READ, METADATA, LIST}`.

HTML parsing is too fragile for a library. API-specific listing belongs in
focused extensions (e.g., `ext.opendata`, `ext.ckan`).

---

## 6. Abstract Method Implementation Plan

How each Backend ABC method maps to HTTP:

| Method | Implementation |
|--------|---------------|
| `name` | `"http"` |
| `capabilities` | `{READ, METADATA}` (or `+LIST` with manifest) |
| `exists(path)` | `HEAD` request → `True` if 200, `False` if 404 |
| `is_file(path)` | `HEAD` request → `True` if 200, `False` if 404 (HTTP resources are always "files") |
| `is_folder(path)` | `False` unless LIST is enabled and path is a known prefix |
| `read(path)` | `GET` → return response body as `BinaryIO` stream |
| `read_bytes(path)` | `GET` → return response body as `bytes` |
| `write(...)` | Raise `CapabilityNotSupported` |
| `write_atomic(...)` | Raise `CapabilityNotSupported` |
| `open_atomic(...)` | Raise `CapabilityNotSupported` |
| `delete(...)` | Raise `CapabilityNotSupported` |
| `delete_folder(...)` | Raise `CapabilityNotSupported` |
| `list_files(...)` | Raise `CapabilityNotSupported` (or manifest-based) |
| `list_folders(...)` | Raise `CapabilityNotSupported` (or manifest-based) |
| `get_file_info(path)` | `HEAD` → `FileInfo(size=Content-Length, modified_at=Last-Modified, content_type=Content-Type, checksum=ETag)` |
| `get_folder_info(path)` | Raise `CapabilityNotSupported` (or manifest-based) |
| `move(...)` | Raise `CapabilityNotSupported` |
| `copy(...)` | Raise `CapabilityNotSupported` |
| `check_health()` | `HEAD base_url` → raise `BackendUnavailable` on failure |
| `native_path(path)` | Return full URL |
| `to_key(url)` | Strip `base_url` prefix |

---

## 7. Error Mapping

| HTTP Status | remote-store Error |
|-------------|-------------------|
| 200, 204    | Success |
| 301, 302, 307, 308 | Follow redirect (up to limit), then map final status |
| 401, 403    | `PermissionDenied` |
| 404         | `NotFound` |
| 408, 429, 500, 502, 503, 504 | `BackendUnavailable` (transient, retryable) |
| Other 4xx   | `RemoteStoreError` (generic) |

---

## 8. Configuration & Auth

### 8.1 Constructor signature (sketch)

```python
ReadOnlyHttpBackend(
    base_url: str,
    *,
    headers: dict[str, str] | None = None,   # custom headers (API keys, auth tokens)
    timeout: float = 30.0,                     # request timeout in seconds
    http_client: str | None = None,            # force "urllib", "requests", or "httpx"
    verify_ssl: bool = True,                   # TLS verification
    max_redirects: int = 5,                    # redirect follow limit
)
```

### 8.2 Auth patterns

- **API key in header:** `headers={"Authorization": "Bearer <token>"}` or
  `headers={"X-API-Key": "<key>"}`
- **No auth:** Most open data portals need nothing
- **Advanced auth** (OAuth, mutual TLS): Out of scope for v1. Users can
  pre-configure an `httpx.Client` and pass it via a future `client` parameter.

### 8.3 Registry integration

```yaml
# store config
stores:
  opendata:
    backend: http
    base_url: "https://data.example.com/datasets/"
    options:
      timeout: 60
      headers:
        X-API-Key: "${OPENDATA_API_KEY}"
```

---

## 9. Composability with Existing Extensions

This is the primary value of making it a backend vs. standalone code:

| Extension | Benefit |
|-----------|---------|
| `ext.cache` | TTL-based caching of `read()` results — critical for HTTP, avoids repeated downloads |
| `ext.transfer` | `download(store, "dataset.csv", local_path)` — works out of the box |
| `ext.observe` | Instrument HTTP reads with callbacks (timing, logging) |
| `ext.batch` | `batch_exists(store, paths)` — check multiple resources |
| `ext.glob` | `glob_files(store, "*.csv")` — works if LIST is available |

The `ext.cache` composability alone justifies the backend approach over ad-hoc
HTTP code.

---

## 10. Testing Strategy

### 10.1 Unit tests (no network)

- Mock the `HttpTransport` protocol
- Verify path construction, error mapping, capability gating
- Test all three transport implementations against a mock server

### 10.2 Integration tests

- Use `pytest-httpserver` or `responses` / `respx` for deterministic HTTP
  mocking
- Test redirects, auth headers, timeouts, error codes
- No real network calls in CI

### 10.3 Conformance tests

- Run the shared backend conformance suite
- Expected: all read/metadata tests pass, all write/delete tests raise
  `CapabilityNotSupported`
- This will be the first backend where the conformance suite has a significant
  number of expected `CapabilityNotSupported` results — may need conformance
  suite adjustments

---

## 11. Open Questions

1. **Backend name:** `"http"` or `"http-readonly"` or `"web"`?
   `"http"` is cleanest but could be confused with a future read-write
   WebDAV backend.

2. **Should `is_folder()` always return `False`?** HTTP doesn't have folders.
   But if we add manifest-based LIST, folder prefixes become meaningful.
   Starting with `False` and evolving seems safest.

3. **Streaming vs. buffered reads:** Should `read()` return a streaming
   response (memory-efficient for large files) or buffer the full response?
   Other backends stream, so streaming is consistent — but HTTP streaming
   requires keeping the connection open, which has lifecycle implications.

4. **Retry policy:** Should the backend have its own retry logic, or defer to
   the future `RetryPolicy` from ID-010? Deferring is cleaner but means no
   retries until ID-010 lands. A simple 1-retry for 429/503 with
   `Retry-After` header respect might be pragmatic.

5. **Extra dependency group name:** `pip install remote-store[http]`? The
   baseline works with zero deps (urllib), so the extra is truly optional.
   Maybe `pip install remote-store[httpx]` to align with the library name.

6. **Conformance suite changes:** The current conformance tests likely assume
   all backends support write. Need to check whether the suite handles
   partial capabilities or needs gating.

---

## 12. Phased Approach

### Phase 1 — Minimal viable backend
- `ReadOnlyHttpBackend` with `{READ, METADATA}` capabilities
- `urllib.request` transport only (zero deps)
- Basic error mapping, timeout, custom headers
- Unit tests with mocked HTTP

### Phase 2 — Transport options
- `RequestsTransport` and `HttpxTransport`
- Optional extras: `remote-store[requests]`, `remote-store[httpx]`
- Connection pooling, session reuse

### Phase 3 — LIST support
- Optional manifest-based listing (`manifest_path` parameter)
- Capability set upgrades to `{READ, METADATA, LIST}` when manifest is
  configured

### Phase 4 — Ecosystem extensions (separate items)
- `ext.opendata` — CKAN/DCAT API wrapper (opendata.swiss, data.gov)
- `ext.webdav` — read-write HTTP backend (different backend entirely)

---

## 13. Prior Art & References

- **fsspec `HTTPFileSystem`:** Read-only HTTP filesystem in the fsspec
  ecosystem. Supports directory listing via HTML parsing. Good validation
  that the concept works, but we'd avoid HTML parsing.
- **smart_open:** Supports HTTP URLs for reading. Streaming-focused.
- **CKAN API:** `/api/3/action/package_show`, `/api/3/action/resource_show` —
  structured JSON endpoints for dataset discovery.

---

## 14. Recommendation

**Proceed with a spec.** The backend fits naturally into the existing
architecture, the capability system handles read-only gracefully, and the
composability with `ext.cache` and `ext.transfer` delivers real value. The
phased approach keeps scope manageable.

Suggested next steps:
1. Add **ID-082** to `BACKLOG.md` (Parking Lot)
2. Write spec when ready to prioritize
