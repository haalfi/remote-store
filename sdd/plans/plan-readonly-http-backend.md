# Implementation Plan: ID-082 — Read-Only HTTP Backend

**Date:** 2026-03-15
**Research:** [research-readonly-http-backend.md](../research/research-readonly-http-backend.md)
**Branch:** `claude/plan-readonly-http-backend-YhBCx`

---

## Summary

Add a `ReadOnlyHttpBackend` with capabilities `{READ, METADATA}` using stdlib
`urllib.request` as the baseline transport (zero new runtime dependencies).
Optional `requests` and `httpx` transports via extras. This is the first
backend with only 2 capabilities, requiring conformance-suite capability gates
as a prerequisite.

---

## Steps

### Phase 0: Prerequisite — Conformance Suite Capability Gates

**Goal:** Make the conformance suite safe for any partial-capability backend.

**File:** `tests/backends/test_conformance.py`

Add `if not backend.capabilities.supports(Capability.X): pytest.skip(...)` to
every test class/method that exercises a capability beyond `{READ, METADATA}`.
Follow the existing `ATOMIC_WRITE` / `GLOB` gating pattern.

| Test class | Gate on |
|---|---|
| `TestBackendExists.test_true_after_write` | WRITE |
| `TestBackendFileFolder.test_is_file` | WRITE |
| `TestBackendFileFolder.test_is_folder` | WRITE |
| `TestBackendRead.test_read_returns_binary_stream` | WRITE |
| `TestBackendRead.test_read_bytes` | WRITE |
| `TestBackendRead.test_read_bytes_not_found` | — (already tests NotFound, no write needed) |
| `TestBackendWrite` (whole class, 4 methods) | WRITE |
| `TestBackendDelete` (whole class, 4 methods) | DELETE |
| `TestBackendListing` (whole class, 7 methods) | LIST |
| `TestBackendIterChildren` (whole class, all methods) | LIST |
| `TestBackendMetadata.test_get_file_info` | WRITE |
| `TestBackendMetadata.test_get_folder_info` | WRITE |
| `TestBackendMetadata.test_get_file_info_not_found` | — (no write needed) |
| `TestBackendMetadata.test_get_folder_info_not_found` | — (no write needed) |
| `TestBackendMove` (whole class) | MOVE |
| `TestBackendCopy` (whole class) | COPY |
| `TestStreamingConformance` read tests (SIO-001) | WRITE (setup) |
| `TestStreamingConformance` write tests (SIO-003) | WRITE |
| `TestBackendToKey.test_to_key_round_trip_with_listing` | WRITE + LIST |

**Validation:** Run `hatch run test` — all existing backends must still pass
with identical pass/skip/fail counts.

---

### Phase 1: Spec

**Goal:** Formalize the design as a testable specification.

**File:** `sdd/specs/032-http-backend.md`

Sections (following the memory-backend spec template):

1. **Overview** — purpose, capability set `{READ, METADATA}`, use cases.
2. **Dependencies** — stdlib urllib baseline; optional `requests`/`httpx`.
3. **Construction** — `ReadOnlyHttpBackend(base_url, *, headers, timeout, retry,
   http_client, verify_ssl, max_redirects)`. Trailing-slash normalization.
4. **Transport abstraction** — `HttpTransport` protocol, `HttpResponse`
   dataclass, auto-detection order (httpx → requests → urllib).
5. **Path semantics** — `base_url + quote(path, safe="/")`, `native_path()`,
   `to_key()`.
6. **Read operations** — `read()` returns `_ErrorMappingStream(response.body)`,
   non-seekable. `read_bytes()` returns buffered content.
7. **Existence checks** — `exists()`/`is_file()` via HEAD→200/404.
   `is_folder()` always False.
8. **Metadata** — `get_file_info()` maps HTTP headers to `FileInfo` fields
   (Content-Length→size, Last-Modified→modified_at, ETag→checksum,
   Content-Type→content_type, all headers→extra).
   `get_folder_info()` raises `NotFound`.
9. **Unsupported operations** — WRITE, DELETE, LIST, MOVE, COPY, ATOMIC_WRITE,
   GLOB all raise `CapabilityNotSupported`.
10. **Error mapping** — HTTP status → remote-store error table.
11. **Health check** — `HEAD base_url`, raise `BackendUnavailable` on failure.
12. **Lifecycle** — `close()` closes transport; `unwrap()` returns transport if
    type matches.
13. **Known limitations** — `size=0` when Content-Length missing,
    `modified_at=datetime.min(UTC)` when Last-Modified missing.

Spec IDs: `HTTP-001` through `HTTP-017` (matching research §16.1 test IDs).

---

### Phase 2: Implementation — Backend + urllib Transport

**Goal:** Working `ReadOnlyHttpBackend` with zero new runtime dependencies.

**File:** `src/remote_store/backends/_http.py` (~250 lines)

Components:

1. **`HttpResponse` dataclass** — `status: int`, `headers: dict[str, str]`,
   `body: BinaryIO`.

2. **`HttpTransport` Protocol** — `get()`, `head()`, `close()`.

3. **`UrllibTransport`** — implements `HttpTransport` using
   `urllib.request.urlopen`. Handles:
   - Custom headers via `Request(url, headers=...)`.
   - Timeout via `urlopen(timeout=...)`.
   - SSL via `ssl.create_default_context()` or `_create_unverified_context()`.
   - Redirect limit via custom `HTTPRedirectHandler`.
   - Error mapping: `urllib.error.HTTPError` → `HttpResponse(status, headers, body)`.
   - Connection errors → `BackendUnavailable`.

4. **`ReadOnlyHttpBackend(Backend)`** — constructor, properties, all ABC methods:
   - `name` → `"http"`
   - `capabilities` → `CapabilitySet({Capability.READ, Capability.METADATA})`
   - `read(path)` → GET → `_ErrorMappingStream(response.body, ...)`
   - `read_bytes(path)` → GET → `response.body.read()`
   - `exists(path)` → HEAD → 200=True, 404=False
   - `is_file(path)` → HEAD → 200=True, 404=False
   - `is_folder(path)` → always `False`
   - `get_file_info(path)` → HEAD → parse headers into `FileInfo`
   - `get_folder_info(path)` → raise `NotFound`
   - Write/delete/list/move/copy → raise `CapabilityNotSupported`
   - `check_health()` → HEAD base_url
   - `native_path(path)` → full URL string
   - `to_key(native_path)` → strip base_url prefix
   - `close()` → close transport
   - `unwrap(type_hint)` → return transport if type matches
   - `__repr__` → mask headers (credential hygiene, AF-008)

5. **`_classify_error(status, path)`** — HTTP status → remote-store error.

6. **`_build_file_info(path, headers)`** — HTTP headers → `FileInfo`.

7. **Transport auto-detection** — `_resolve_transport(http_client, ...)`:
   try httpx → requests → urllib; respect explicit `http_client` override.

---

### Phase 3: Registration

**Goal:** Make `"http"` usable via the backend registry.

**Files:**
- `src/remote_store/backends/__init__.py` — add import + `__all__` entry for
  `ReadOnlyHttpBackend`. Since urllib is stdlib, no `try/except ImportError`
  needed.
- `src/remote_store/_registry.py` — add `register_backend("http",
  ReadOnlyHttpBackend)` in `_register_builtin_backends()`.

---

### Phase 4: Backend-Specific Tests

**Goal:** 17 HTTP-specific test scenarios covering behavior not in the
conformance suite.

**File:** `tests/backends/test_http.py` (~250 lines)

**Test infrastructure:** `pytest-httpserver` fixture serving pre-seeded files.

**Dependency:** Add `pytest-httpserver` to `pyproject.toml`
`[tool.hatch.envs.default.dependencies]` (test-only dep).

Tests (from research §16.1):

| ID | Test | Spec |
|----|------|------|
| HTTP-001 | `read()` returns streaming BinaryIO, chunked read works | SIO-001 |
| HTTP-002 | `read_bytes()` returns full content | BE-007 |
| HTTP-003 | `exists()` → True for 200, False for 404 | BE-004 |
| HTTP-004 | `get_file_info()` maps headers to FileInfo fields | BE-016 |
| HTTP-005 | `get_file_info()` handles missing Content-Length/Last-Modified | BE-016 |
| HTTP-006 | Error mapping: 401→PermissionDenied, 404→NotFound, 500→BackendUnavailable | ERR-* |
| HTTP-007 | `native_path()` returns full URL | NPR-003 |
| HTTP-008 | `to_key()` strips base_url prefix | NPR-003 |
| HTTP-009 | Path with special chars is URL-encoded | — |
| HTTP-010 | Custom headers sent with every request | — |
| HTTP-011 | Redirects are followed (up to limit) | — |
| HTTP-012 | Timeout raises BackendUnavailable | — |
| HTTP-013 | `check_health()` sends HEAD to base_url | BE-020 |
| HTTP-014 | Write/delete/move/copy raise CapabilityNotSupported | — |
| HTTP-015 | `close()` is callable, releases transport | BE-020 |
| HTTP-016 | Transport auto-detection (urllib fallback) | — |
| HTTP-017 | `is_folder()` always returns False | BE-005 |

---

### Phase 5: Conformance Suite Integration

**Goal:** HTTP backend participates in the shared conformance suite.

**File:** `tests/backends/conftest.py`

1. Add `"http"` to the `backend` fixture `params` list.
2. Create a session-scoped `http_server` fixture using `pytest-httpserver` that
   pre-seeds test files (`hello.txt`, `data.bin`, `dir/a.txt`, etc.) matching
   the data patterns the conformance suite expects.
3. In the `backend` fixture, for `request.param == "http"`: create
   `ReadOnlyHttpBackend(base_url=http_server.url_for("/"))`.

**Expected conformance results:**
- ~12 tests pass (identity, lifecycle, native_path, to_key non-write, unwrap)
- ~48 tests skip (gated on WRITE/DELETE/LIST/MOVE/COPY)
- ~9 tests skip (existing ATOMIC_WRITE/GLOB gates)
- 0 tests fail

**Validation:** `hatch run test` — all backends green, HTTP shows expected
skip count.

---

### Phase 6: Optional Transports (requests, httpx)

**Goal:** Higher-quality HTTP experience for users who have requests or httpx
installed.

**Files:**
- `src/remote_store/backends/_http.py` — add `RequestsTransport` and
  `HttpxTransport` classes (~50 lines each). Benefits: connection pooling,
  sessions, HTTP/2 (httpx).
- `pyproject.toml` — add optional extras:
  ```toml
  requests = ["requests>=2.25.0"]
  httpx = ["httpx>=0.24.0"]
  ```

**Validation:** Tests pass with urllib (default), `pip install requests` and
`pip install httpx` both work.

---

### Phase 7: Documentation

**Goal:** User-facing docs for the HTTP backend.

**Files:**

1. **`guides/backends/http.md`** — user guide (following memory.md template):
   - One-line description + use cases
   - Usage examples (direct constructor + registry config)
   - Constructor parameters table
   - Capabilities table
   - HTTP-specific semantics (no folders, read-only, header mapping)
   - Composability with ext.cache, ext.transfer
   - Error mapping reference

2. **`examples/http_backend.py`** — runnable example script:
   - Construct backend with base_url
   - Read a file, get metadata
   - Show ext.cache composability
   - Use `pytest-httpserver` in a `if __name__ == "__main__"` guard so it's
     self-contained (or use a public URL that's stable)

3. **`examples/configuration.py`** — add HTTP backend configuration entry.

4. **`guides/backends/index.md`** — add HTTP row to Supported Backends table.

5. **`README.md`** — add HTTP row to backends table + installation section.

6. **Docs nav** — add `http.md` to `docs-src/guides/backends/_nav.yml`
   (or equivalent).

7. **API reference** — if not auto-generated, add `docs-src/api/` entry for
   `ReadOnlyHttpBackend`.

---

### Phase 8: Bookkeeping

**Goal:** Keep the repo consistent per CLAUDE.md principles.

**Files:**

1. **`CHANGELOG.md`** — add entry under `[Unreleased]`:
   ```
   ### Added
   - Read-only HTTP backend (`ReadOnlyHttpBackend`) for reading files from
     HTTP/HTTPS URLs. Capabilities: `{READ, METADATA}`. Zero runtime
     dependencies (uses stdlib `urllib`); optional `requests` and `httpx`
     transports via extras. (ID-082)
   - Optional extras: `remote-store[requests]`, `remote-store[httpx]`.
   - Conformance suite capability gates for WRITE, DELETE, LIST, MOVE, COPY
     (enables testing partial-capability backends).
   ```

2. **`sdd/BACKLOG.md`** — update ID-082 status. Move completed parts to
   `BACKLOG-DONE.md`.

3. **`CONTRIBUTING.md`** — verify the "Adding a New Backend" checklist is still
   accurate (no structural changes expected).

---

## Commit Strategy

| Commit | Content | ID |
|--------|---------|-----|
| 1 | Conformance suite capability gates | ID-082 |
| 2 | Spec `032-http-backend.md` | ID-082 |
| 3 | `ReadOnlyHttpBackend` + `UrllibTransport` + registration | ID-082 |
| 4 | Backend-specific tests + conformance fixture | ID-082 |
| 5 | Optional transports (requests, httpx) + extras | ID-082 |
| 6 | Docs: guide, example, README, nav, CHANGELOG, BACKLOG | ID-082 |

Each commit should pass `hatch run all` independently.

---

## Dependencies & Test Infrastructure

| Dependency | Type | Purpose |
|---|---|---|
| `pytest-httpserver` | test-only | Mock HTTP server for backend tests + conformance fixture |
| `requests>=2.25.0` | optional extra | `RequestsTransport` |
| `httpx>=0.24.0` | optional extra | `HttpxTransport` |

No new runtime dependencies for the baseline backend.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Conformance gate changes affect other backends | Additive only (skip where unsupported); run full suite |
| urllib streaming edge cases | Research verified `_ErrorMappingStream` wraps `HTTPResponse` correctly |
| `pytest-httpserver` not installed | Add to test dependencies in `pyproject.toml` |
| `size=0` when Content-Length missing | Document as known limitation in spec and guide |

---

## Open Questions (for implementation, not blockers)

1. **Retry integration:** Should the urllib transport implement retry inline, or
   delegate to the existing `RetryPolicy` helper used by other backends? →
   Check how S3/SFTP backends use `RetryPolicy` and follow the same pattern.

2. **`get_folder_info()` behavior:** Research says raise `NotFound` (consistent
   with `is_folder()` returning False). Alternative: raise
   `CapabilityNotSupported`. → `NotFound` is correct per the research rationale.

3. **Spec number:** Next available is 032. Verify no conflicts before creating.
   → Confirmed: `sdd/specs/032-*.md` does not exist.
