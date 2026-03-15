# Research: Read-Only HTTP Backend

**Item ID:** ID-082
**Date:** 2026-03-15
**Status:** Research complete -- ready for spec consideration

---

## 1. Problem Statement

Users already use remote-store for storage (local, S3, SFTP, Azure). Sometimes
another kind of "remote stored thing" enters the picture: files hosted at an
HTTP URL -- government open data portals, dataset registries, static file
servers, CDN-hosted assets, package archives, etc.

A `ReadOnlyHttpBackend` would treat an HTTP endpoint as just another backend.
Files behind a URL become accessible through the same `Store` interface, with
the same composability (`ext.cache`, `ext.transfer`, `ext.observe`,
`ext.batch`) that users already rely on for other backends.

### Why a backend, not an extension?

An extension cannot provide `Store.read()` -- it would need to reimplement the
entire `Store` interface. A backend slots into the existing architecture
naturally: capability gating, error mapping, registry lifecycle, and all
extensions work out of the box.

### Design constraints

- Core package has **zero runtime dependencies** (`dependencies = []`).
- HTTP library must be optional (`urllib` from stdlib as baseline, `requests`
  or `httpx` as optional extras).
- The backend is **read-only** -- write, delete, move, copy operations raise
  `CapabilityNotSupported`.
- Must handle real-world HTTP concerns: redirects, content-type, timeouts,
  auth headers.

---

## 2. Capability Profile

| Capability   | Supported | Notes |
|--------------|:---------:|-------|
| READ         | Yes       | Core value: `GET` request, return body as stream |
| WRITE        | --        | Raises `CapabilityNotSupported` |
| DELETE       | --        | Raises `CapabilityNotSupported` |
| LIST         | --        | No reliable server-side mechanism (see SS5) |
| MOVE         | --        | Raises `CapabilityNotSupported` |
| COPY         | --        | Raises `CapabilityNotSupported` |
| ATOMIC_WRITE | --        | Raises `CapabilityNotSupported` |
| METADATA     | Yes       | `HEAD` request -> size, content-type, last-modified, ETag |
| GLOB         | --        | No server-side pattern matching |

**Capability set:** `{READ, METADATA}`

This would be the first backend with only 2 capabilities. The capability
system already handles this -- `Store` gates every operation and raises
`CapabilityNotSupported` with clear context.

---

## 3. Path Semantics

### 3.1 Base URL + relative path

The backend takes a `base_url` at construction. Paths are appended:

```python
backend = ReadOnlyHttpBackend(base_url="https://data.example.com/datasets/")
# store.read("population/2024.csv")
# -> GET https://data.example.com/datasets/population/2024.csv
```

### 3.2 The `urljoin` trailing-slash footgun

`urllib.parse.urljoin` has surprising behavior with trailing slashes:

```python
urljoin("https://example.com/data", "file.csv")
# -> "https://example.com/file.csv"  (WRONG -- replaces last segment)

urljoin("https://example.com/data/", "file.csv")
# -> "https://example.com/data/file.csv"  (correct)
```

**Mitigation:** The constructor normalizes `base_url` to always end with `/`.
Path construction uses simple string concatenation (`base_url + quote(path)`)
rather than `urljoin`, avoiding the footgun entirely. `urljoin` is only needed
if we ever support relative `../` paths, which we don't (path validation
rejects `..`).

### 3.3 Path validation

- Standard remote-store path rules apply (no `..`, no null bytes, no absolute
  paths).
- The backend URL-encodes paths internally via `urllib.parse.quote(path,
  safe="/")` when constructing request URLs. User-visible paths remain
  unencoded.

### 3.4 `native_path()` and `to_key()`

- `native_path(path)` -> full URL string (e.g.,
  `"https://data.example.com/datasets/population/2024.csv"`)
- `to_key(native_path)` -> strips `base_url` prefix, returns relative key

---

## 4. HTTP Library Strategy

### 4.1 Tiered approach

| Tier | Library | Dependency | Pros | Cons |
|------|---------|------------|------|------|
| **Baseline** | `urllib.request` | stdlib | Zero deps, always available | No connection pooling, clunky API, no async |
| **Standard** | `requests` | optional extra | Industry standard, sessions, auth adapters | Sync only, heavy dep tree |
| **Advanced** | `httpx` | optional extra | Sync + async, HTTP/2, modern API | Newer, smaller ecosystem |

### 4.2 Recommendation

**Single backend, pluggable transport.** Rather than separate backends per HTTP
library (the S3 vs S3-PyArrow model), use a single `ReadOnlyHttpBackend` that
auto-detects the best available library at init:

1. If `httpx` is installed -> use it (best feature set)
2. Else if `requests` is installed -> use it (most common)
3. Else -> fall back to `urllib.request` (always available)

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
    def close(self) -> None: ...

@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: BinaryIO  # streaming body (only meaningful for GET)
```

Three implementations: `UrllibTransport`, `RequestsTransport`, `HttpxTransport`.

### 4.4 urllib limitations (verified)

- **No connection pooling.** Each request opens a new TCP connection. Fine for
  occasional reads; poor for batch operations. `requests`/`httpx` sessions
  solve this.
- **No async.** Acceptable -- all existing backends are sync.
- **SSL works.** `urllib.request.urlopen` validates TLS certificates by default
  via `ssl.create_default_context()`. `verify_ssl=False` would use
  `ssl._create_unverified_context()`.
- **Redirects handled.** `urllib` follows redirects automatically (up to a
  built-in limit). Custom `max_redirects` requires a subclassed handler.
- **Streaming works.** Response object supports chunked `read(size)`. See §11
  for details.

---

## 5. LIST Capability -- Why Not

HTTP has no native directory listing. The options considered:

| Approach | Verdict | Reason |
|----------|---------|--------|
| No LIST | **Chosen** | Clean, honest, no hacks |
| Manifest-based LIST | Deferred | Requires user to maintain sidecar file; could add later via `manifest_path` param |
| HTML index parsing | Rejected | Fragile (HTML varies by server), security risk (arbitrary HTML) |
| API-specific listing | Out of scope | Belongs in focused extensions (e.g., `ext.ckan`) |

Users who need listing use an external catalog (API, manifest, database) to
discover paths, then `store.read()` each one. If demand justifies it, a
`manifest_path` constructor argument could upgrade the capability set to
`{READ, METADATA, LIST}` in a future phase.

---

## 6. Complete Method Mapping

Every Backend ABC method and its HTTP implementation:

| Method | Implementation | Notes |
|--------|---------------|-------|
| `name` | `"http"` | See §18 Q1 for naming rationale |
| `capabilities` | `{READ, METADATA}` | Fixed set |
| `exists(path)` | `HEAD` -> 200=True, 404=False | |
| `is_file(path)` | `HEAD` -> 200=True, 404=False | HTTP resources are always "files" |
| `is_folder(path)` | Always `False` | No folder concept without LIST |
| `read(path)` | `GET` -> `_ErrorMappingStream(response)` | Non-seekable stream, see §11 |
| `read_bytes(path)` | `GET` -> `response.read()` | Fully buffered |
| `write(...)` | Raise `CapabilityNotSupported` | |
| `write_atomic(...)` | Raise `CapabilityNotSupported` | |
| `open_atomic(...)` | Raise `CapabilityNotSupported` | |
| `delete(...)` | Raise `CapabilityNotSupported` | |
| `delete_folder(...)` | Raise `CapabilityNotSupported` | |
| `list_files(...)` | Raise `CapabilityNotSupported` | |
| `list_folders(...)` | Raise `CapabilityNotSupported` | |
| `iter_children(...)` | Raise `CapabilityNotSupported` | Default impl calls list_files+list_folders; override to raise directly |
| `get_file_info(path)` | `HEAD` -> `FileInfo(...)` | See §12 for field mapping |
| `get_folder_info(path)` | Raise `CapabilityNotSupported` | No folder concept |
| `move(...)` | Raise `CapabilityNotSupported` | |
| `copy(...)` | Raise `CapabilityNotSupported` | |
| `glob(...)` | Raise `CapabilityNotSupported` | Default impl already does this |
| `check_health()` | `HEAD base_url` -> raise `BackendUnavailable` on failure | |
| `native_path(path)` | Return full URL string | |
| `to_key(url)` | Strip `base_url` prefix | |
| `close()` | Close transport (connection pool if applicable) | No-op for urllib |
| `unwrap(type_hint)` | Return underlying transport if type matches | e.g., `unwrap(httpx.Client)` |

---

## 7. Error Mapping

| HTTP Status | remote-store Error | Notes |
|-------------|-------------------|-------|
| 200, 204 | Success | |
| 301, 302, 307, 308 | Follow redirect (up to limit) | Map final status |
| 401, 403 | `PermissionDenied` | |
| 404 | `NotFound` | |
| 408, 429, 500, 502, 503, 504 | `BackendUnavailable` | Transient |
| Other 4xx | `RemoteStoreError` | Generic |

---

## 8. Configuration & Auth

### 8.1 Constructor signature (sketch)

```python
ReadOnlyHttpBackend(
    base_url: str,
    *,
    headers: dict[str, str] | None = None,   # custom headers (API keys, auth tokens)
    timeout: float = 30.0,                     # request timeout in seconds
    retry: RetryPolicy | None = None,          # retry config (same as S3/SFTP/Azure)
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
| `ext.cache` | TTL-based caching of `read()` results -- critical for HTTP, avoids repeated downloads |
| `ext.transfer` | `download(store, "dataset.csv", local_path)` -- works out of the box |
| `ext.observe` | Instrument HTTP reads with callbacks (timing, logging) |
| `ext.batch` | `batch_exists(store, paths)` -- check multiple resources |
| `ext.arrow` | `read_table(store, "data.parquet")` -- read remote Parquet/CSV via PyArrow |

The `ext.cache` composability alone justifies the backend approach over ad-hoc
HTTP code.

Note: `ext.glob` requires LIST capability, so it won't work with this backend.

---

## 10. Conformance Suite Impact

### 10.1 Current state of capability-gating

The conformance suite (`tests/backends/test_conformance.py`) has 19 test
classes with 69 test methods. Only two capabilities are currently gated:

| Capability | Gated? | Tests |
|------------|--------|-------|
| ATOMIC_WRITE | Yes | 7 tests skip cleanly |
| GLOB | Yes | 2 tests skip cleanly |
| WRITE, DELETE, LIST, MOVE, COPY, METADATA | **No** | ~50 tests have no capability checks |

### 10.2 What breaks for a {READ, METADATA} backend

Most test classes set up test data by calling `backend.write()` before
asserting read behavior. This means even read/metadata tests will fail -- not
because the backend can't read, but because the test can't set up fixtures.

**Tests that would need changes:**

| Test Class | Issue | Fix |
|------------|-------|-----|
| `TestBackendExists` | Calls `write()` in setup | Gate on WRITE or use pre-seeded fixture |
| `TestBackendFileFolder` | Calls `write()` in setup | Gate on WRITE |
| `TestBackendRead` | Calls `write()` in setup | Gate on WRITE or pre-seed |
| `TestBackendWrite` | Tests write operations | Gate on WRITE |
| `TestBackendDelete` | Tests delete operations | Gate on DELETE |
| `TestBackendListing` | Tests list operations | Gate on LIST |
| `TestBackendIterChildren` | Tests list operations | Gate on LIST |
| `TestBackendMetadata` | Calls `write()` in setup | Gate on WRITE or pre-seed |
| `TestBackendMove` | Tests move operations | Gate on MOVE |
| `TestBackendCopy` | Tests copy operations | Gate on COPY |

**Tests that pass as-is:**

| Test Class | Why |
|------------|-----|
| `TestBackendIdentity` | Only checks name, capabilities, repr |
| `TestStreamingConformance` | Tests chunked read, context manager; no seekability requirement |
| `TestBackendWriteAtomic` | Already gated on ATOMIC_WRITE |
| `TestBackendOpenAtomic` | Already gated on ATOMIC_WRITE |
| `TestBackendLifecycle` | Only checks that `close()` is callable |
| `TestBackendGlob` | Already gated on GLOB |
| `TestBackendUnwrap` | Only checks unwrap raises or returns |
| `TestBackendNativePath` | Only checks path round-trip |
| `TestBackendToKey` | Only checks key conversion |

### 10.3 Proposed conformance changes

Two-pronged approach:

1. **Add capability gates** to test classes that test write/delete/move/copy
   operations. Pattern: `if not backend.capabilities.supports(Capability.X):
   pytest.skip(...)`. This is the same pattern already used for ATOMIC_WRITE
   and GLOB. Straightforward, ~15 lines of changes.

2. **Pre-seeded fixture for read-only backends.** Tests that verify read
   behavior (`TestBackendRead`, `TestBackendMetadata`, `TestBackendExists`)
   need test data. For writable backends, they create it inline. For
   read-only backends, provide a `conftest.py` fixture that pre-seeds the
   HTTP mock server with test files. The conformance test checks
   `backend.capabilities.supports(Capability.WRITE)` -- if true, write
   inline; if false, assume the fixture pre-seeded the data.

**Estimated effort:** Small. The capability-gating pattern is established.
The pre-seeded fixture is the only new concept, and it's just a
`pytest-httpserver` fixture that serves a few static files.

---

## 11. Stream Lifecycle (`read()` return value)

### 11.1 What the spec requires (SIO-001)

From spec `006-streaming-io.md`: "The returned stream is not guaranteed to be
seekable. Seekability is a backend-level property (e.g. local files are
seekable, HTTP-based streams typically are not), not a Store API contract."

The streaming conformance tests (`TestStreamingConformance`) verify:
- Stream is not a `BytesIO` wrapper (must be a real stream)
- Chunked `read(size)` works
- Stream supports context manager protocol
- **Seekability is NOT tested as a requirement**

### 11.2 urllib.request response as BinaryIO

`urllib.request.urlopen()` returns `http.client.HTTPResponse`, which:
- Inherits from `io.BufferedIOBase` (not `RawIOBase`)
- Supports: `read(size)`, `readline(size)`, `readinto(b)`, `close()`
- Reports `seekable() -> False`
- Has `__enter__`/`__exit__` (context manager)

### 11.3 Wrapping with `_ErrorMappingStream`

`_ErrorMappingStream` delegates all I/O to the inner stream and maps
exceptions to remote-store errors. It handles imperfect streams gracefully:
- `seek()` returning `None` (paramiko quirk) -> falls back to `tell()`
- `seekable()` missing -> returns `False`
- `tell()` returning `None` -> returns `0`
- `close()` exceptions -> suppressed

**Verdict: `_ErrorMappingStream(http_response, ...)` works directly.**

Do NOT wrap in `io.BufferedReader` -- unlike S3/SFTP backends, the HTTP
response is already buffered (`BufferedIOBase`). Double-buffering would be
wasteful and could cause issues.

Return pattern:
```python
def read(self, path: str) -> BinaryIO:
    response = self._transport.get(self._url(path), ...)
    return cast("BinaryIO", _ErrorMappingStream(response.body, self._classify_error, path))
```

### 11.4 Connection lifecycle

The HTTP connection stays open while the stream is open. This is the same
pattern as S3 (s3fs holds the connection) and SFTP (paramiko holds the
channel). The stream's `close()` releases the connection.

For urllib, this means one TCP connection per open stream. For
requests/httpx with session pooling, the connection returns to the pool on
close.

---

## 12. FileInfo Field Mapping from HTTP Headers

| FileInfo field | HTTP header | Handling when missing |
|---------------|-------------|---------------------|
| `path` | From request path | Always available |
| `name` | From path | Always available |
| `size` | `Content-Length` | `0` if missing (chunked transfer, dynamic content) |
| `modified_at` | `Last-Modified` | `datetime.min` if missing (epoch fallback) |
| `checksum` | `ETag` | `None` (optional field) |
| `content_type` | `Content-Type` | `None` (optional field) |
| `extra` | All response headers | `{"headers": dict(response.headers)}` |

**Notes:**
- `Content-Length` is absent for chunked responses and some CDNs. Using `0` as
  a fallback is imperfect -- code checking `file_info.size == 0` (e.g.,
  skip-empty-file logic, progress bars, `ext.transfer` pre-allocation) would
  misinterpret "unknown" as "zero bytes". Since `FileInfo.size` is `int` (not
  `Optional[int]`), there is no clean sentinel today. The spec should note this
  as a known limitation that may warrant making `size` Optional in a future
  `FileInfo` revision.
- `Last-Modified` is absent on many static file hosts and CDNs. Using
  `datetime.min` signals "unknown" without requiring an Optional field change.
- `ETag` maps naturally to `checksum` -- both are opaque identifiers for
  content versioning. Useful for `ext.cache` integration.

---

## 13. Prior Art -- Build vs. Reuse

The key question is: can we use an existing library instead of writing our own
HTTP backend? The answer is no -- but the implementation is small enough that
this is fine.

### 13.1 Why not wrap fsspec `HTTPFileSystem`?

fsspec's HTTP support is the closest match. It provides read-only HTTP access,
streaming, and even directory listing via HTML parsing.

**Why it doesn't fit:**
- fsspec is a **heavyweight dependency** (pulls in `aiohttp` for HTTP).
  remote-store's core has zero runtime deps.
- fsspec's `HTTPFileSystem` exposes an `AbstractFileSystem` interface, not
  our `Backend` interface. Wrapping it would mean adapting every method --
  the wrapper would be roughly the same size as a direct implementation.
- Its HTML-based directory listing is fragile and not something we'd want.
- Its Range-based seeking adds complexity we don't need.

fsspec validates that the concept works, but there's nothing to reuse.

### 13.2 Why not wrap smart_open?

`smart_open.open("https://...")` gives a streaming reader. But:
- It's a single `open()` function, not a filesystem abstraction. No
  `exists()`, `get_file_info()`, `check_health()`, or any metadata support.
- Wrapping it would provide only `read()` -- we'd still implement everything
  else ourselves.
- It requires `requests` as a dependency.

### 13.3 Why not use requests/httpx directly as the backend?

We do -- that's exactly the transport layer (SS4). The "build" here is the
thin Backend adapter (~150 lines) that maps HTTP semantics to remote-store's
interface. The actual HTTP work is delegated to urllib/requests/httpx.

### 13.4 What we learn from prior art

| Project | Lesson for us |
|---------|--------------|
| fsspec HTTPFileSystem | Concept is proven. Skip HTML listing and Range seeking. |
| smart_open | Simple HTTP read adapter has demand. We add metadata + composability on top. |
| Hugging Face Hub | Domain-specific HTTP access belongs in extensions, not the base backend. |
| DVC | ETag -> checksum mapping works well. Validates `ext.cache` integration pattern. |

### 13.5 Implementation size estimate

The HTTP backend is a thin adapter over standard HTTP libraries. Estimated:
- Backend class: ~150 lines (method mapping, error mapping, path handling)
- Transport protocol + urllib impl: ~80 lines
- requests/httpx transports: ~50 lines each (optional)

This is comparable to `MemoryBackend` (~140 lines) and much simpler than
`S3Backend` (~300 lines). Not a wheel worth importing -- simpler to build.

---

## 14. Real-World HTTP Endpoint Behavior

Tested against representative public endpoints to validate assumptions:

| Endpoint | Content-Length | Last-Modified | ETag | HEAD | Redirects |
|----------|:-------------:|:-------------:|:----:|:----:|:---------:|
| GitHub raw (raw.githubusercontent.com) | Yes | Yes | Yes (weak) | Yes | Yes (1 redirect from github.com) |
| PyPI simple index (pypi.org) | Yes | -- | Yes | Yes | Yes (http->https) |
| PyPI package files (files.pythonhosted.org) | Yes | Yes | Yes | Yes | -- |
| opendata.swiss (lindas API) | Varies | -- | -- | Yes | -- |
| CDN-hosted static files (typical) | Yes | Yes | Yes | Yes | -- |

**Findings:**
- `HEAD` is universally supported -- `exists()` and `get_file_info()` are safe.
- `Content-Length` is present for static files, sometimes missing for API responses.
- `Last-Modified` is often missing on API endpoints and CDNs.
- `ETag` is common on static file servers, rare on dynamic APIs.
- Redirects are common (http->https, domain aliases). Following redirects is mandatory.

---

## 15. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| urllib can't produce conformant streams | **Low** | High | Verified: `_ErrorMappingStream` wraps HTTPResponse correctly (SS11) |
| Conformance suite changes break other backends | Low | Medium | Changes are additive (capability gates); existing backends unaffected |
| Scope creep toward WebDAV/write support | Medium | Medium | Hard boundary: backend name is `http`, not `webdav`; no write methods |
| `Content-Length` missing breaks FileInfo | **Low** | Medium | Use `size=0` fallback; document as known limitation (see §12) |
| Connection leak from unclosed streams | Medium | Medium | Same risk as S3/SFTP; `_ErrorMappingStream.close()` handles cleanup |
| urllib SSL issues on older Python | Low | Low | `ssl.create_default_context()` works on Python 3.10+ |

No showstoppers identified. The urllib streaming concern (P1.4 in the original
gap analysis) is resolved -- it works.

---

## 16. Testing Strategy

### 16.1 Backend-specific tests (`tests/backends/test_http.py`)

| ID | Test | Spec |
|----|------|------|
| HTTP-001 | `read()` returns streaming BinaryIO, chunked read works | SIO-001 |
| HTTP-002 | `read_bytes()` returns full content | BE-007 |
| HTTP-003 | `exists()` returns True for 200, False for 404 | BE-004 |
| HTTP-004 | `get_file_info()` maps headers to FileInfo fields | BE-016 |
| HTTP-005 | `get_file_info()` handles missing Content-Length/Last-Modified | BE-016 |
| HTTP-006 | Error mapping: 401->PermissionDenied, 404->NotFound, 500->BackendUnavailable | ERR-* |
| HTTP-007 | `native_path()` returns full URL | NPR-003 |
| HTTP-008 | `to_key()` strips base_url prefix | NPR-003 |
| HTTP-009 | Path with special characters is URL-encoded | -- |
| HTTP-010 | Custom headers are sent with every request | -- |
| HTTP-011 | Redirects are followed (up to limit) | -- |
| HTTP-012 | Timeout raises BackendUnavailable | -- |
| HTTP-013 | `check_health()` sends HEAD to base_url | BE-020 |
| HTTP-014 | Write/delete/move/copy raise CapabilityNotSupported | -- |
| HTTP-015 | `close()` is callable, releases transport | BE-020 |
| HTTP-016 | Transport auto-detection (urllib/requests/httpx) | -- |
| HTTP-017 | `is_folder()` always returns False | BE-005 |

### 16.2 Conformance suite participation

After adding capability gates (SS10.3), the HTTP backend runs through the
shared conformance suite. Expected results:

- ~12 tests pass (identity, read, metadata, lifecycle, path, unwrap)
- ~38 tests skip (write, delete, move, copy, list, glob, atomic)
- 0 tests fail

### 16.3 Test infrastructure

Use `pytest-httpserver` (lightweight, no external deps) to create a local HTTP
server in fixtures. Pre-seed with test files for read/metadata tests.

No real network calls in CI.

---

## 17. Implementation Checklist (SDD Pipeline)

| Step | Item | Notes |
|------|------|-------|
| 1 | Write spec `sdd/specs/032-http-backend.md` | Capability profile, method mapping, error mapping |
| 2 | Add capability gates to conformance suite | ~15 lines, prerequisite for step 5 |
| 3 | Implement `ReadOnlyHttpBackend` | `src/remote_store/backends/_http.py` |
| 4 | Implement `UrllibTransport` | Same file or `_http_transport.py` |
| 5 | Register in backend registry | `backends/__init__.py`, `from_dict()` support |
| 6 | Write backend-specific tests | `tests/backends/test_http.py` |
| 7 | Run conformance suite with HTTP backend | Verify skip/pass/fail counts |
| 8 | Add `RequestsTransport`, `HttpxTransport` | Optional extras |
| 9 | Add optional extras to `pyproject.toml` | `[http]` or `[httpx]` group |
| 10 | Add docs: guide, API ref, examples | `docs-src/guides/`, `docs-src/api/` |
| 11 | Update CHANGELOG, BACKLOG | Per repo conventions |

---

## 18. Resolved Questions

Questions from the original draft, now resolved with reasoning:

**Q1. Backend name: `"http"` or `"http-readonly"` or `"web"`?**

Use `"http"`. Reasons:
- Consistent with other backend names (`"local"`, `"s3"`, `"sftp"`, `"azure"`)
  -- none encode capabilities in the name.
- A future WebDAV backend would use `"webdav"`, not `"http"` -- different
  protocol, different backend.
- The capability system communicates what the backend can do; the name
  identifies the protocol.

**Q2. Should `is_folder()` always return `False`?**

Yes. HTTP has no folder concept. Without LIST, there are no known prefixes to
check against. If manifest-based LIST is added later, `is_folder()` can check
whether a path is a known prefix in the manifest.

**Q3. Streaming vs. buffered reads?**

Streaming. Consistent with all other backends. urllib's HTTPResponse supports
chunked `read(size)` and is already buffered (`BufferedIOBase`). Wrap in
`_ErrorMappingStream` directly, no `BufferedReader` needed. Non-seekable per
SIO-001 spec allowance.

**Q4. Retry policy?**

Accept the existing `RetryPolicy` in the constructor (like S3, SFTP, Azure do).
Map its fields to urllib/requests/httpx retry mechanisms:
- **urllib:** Implement a simple retry loop around `urlopen()`, respecting
  `max_attempts`, `backoff_base`, `backoff_max`, `jitter`, and `timeout`.
  Retry on transient HTTP statuses (429, 500, 502, 503, 504) and connection
  errors. Honour `Retry-After` header when present.
- **requests/httpx:** Delegate to `urllib3.Retry` / `httpx` transport retry
  config, mapping `RetryPolicy` fields to native parameters.

**Q5. Extra dependency group name?**

`pip install remote-store[httpx]` for httpx, `pip install remote-store[requests]`
for requests. No `[http]` group -- the baseline (urllib) needs no extra deps.
This mirrors how `[arrow]` means "install PyArrow" and `[otel]` means "install
OpenTelemetry".

**Q6. Conformance suite changes?**

Needed but small. Add capability gates to ~10 test classes (same pattern as
existing ATOMIC_WRITE/GLOB gates). Pre-seed read-only test data via
`pytest-httpserver` fixture. See SS10.3 for details.

---

## 19. Recommendation

**Proceed with a spec.** No showstoppers found:

- urllib streaming works with `_ErrorMappingStream` (verified).
- Conformance suite changes are small and additive.
- The capability system handles read-only gracefully.
- Real-world HTTP endpoints behave as expected (HEAD, Content-Length, redirects).
- Prior art (fsspec, smart_open, DVC) validates the concept.
- Composability with `ext.cache` and `ext.transfer` delivers clear value.

Next steps:
1. Write spec `032-http-backend.md`
2. Add conformance suite capability gates (prerequisite, benefits all future
   partial-capability backends)
3. Implement Phase 1 (urllib-only, `{READ, METADATA}`)
