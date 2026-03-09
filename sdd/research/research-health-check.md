# Research: Backend Health Check (`store.ping()` / `backend.check_health()`)

**Item ID:** ID-054
**Date:** 2026-03-09
**Context:** Lightweight, non-destructive health verification for backends; startup gates and liveness probes.

---

## 1. Overview and Motivation

A **health check** method verifies that a backend is reachable and credentials are valid without performing any data operations. This enables:

- **Startup gates:** Fail fast if credentials are invalid before accepting traffic
- **Liveness probes:** Kubernetes, container orchestrators, monitoring systems
- **Connection validation:** Application initialization / bootstrap logic
- **Operational hygiene:** Verify before critical operations

The operation must be **non-destructive** (no side effects), **lightweight** (minimal I/O), and **portable** across all backends.

---

## 2. Design Constraints and Principles

### 2.1 Non-Destructive
- Must not create, modify, or delete any data
- Must not have observable side effects on the backend
- Read-only or pure metadata operations only

### 2.2 Lightweight
- Should complete in under 1–2 seconds on a healthy backend
- Minimal network round-trips (preferably a single call)
- No listing, streaming, or enumeration

### 2.3 Portable Semantics
- Uniform API across all backends (Store + all 6 backends)
- Failure modes standardized: success (healthy), exception (unhealthy)
- Credential validation implicit (failures = bad credentials or connectivity)

### 2.4 Clear Failure Semantics
- Success = backend is reachable and credentials work
- Raises exception on any connectivity or credential issue
- **Does not** return a `bool` or status enum — follows remote-store convention of raising exceptions for error conditions

---

## 3. Backend-Specific Strategies

### 3.1 Local Backend
**Method:** `os.access(root_path, os.R_OK)`

- Verifies the root path exists and is readable
- Non-destructive, instant
- Raises `PermissionDenied` if path not readable, `NotFound` if path missing

**Implementation Notes:**
- Works for any root path (file or folder)
- Natural fit for how Local backend validates paths

---

### 3.2 S3 Backend
**Method:** `s3.head_bucket()` or equivalent

- Lightweight metadata call, no data transfer
- Validates bucket exists and credentials have permission
- AWS API: `HeadBucket` operation
- Returns 200 OK on success, 403 on permission denied, 404 on missing bucket

**Implementation Notes:**
- s3fs may use `s3.meta.client.head_bucket()`
- boto3: `s3_client.head_bucket(Bucket=bucket_name)`
- Preferred over checking for root path existence (which would require listing)

**Error Mapping:**
- 403 / AccessDenied → `PermissionDenied`
- 404 / NoSuchBucket → `NotFound`
- Timeout / connection → `BackendUnavailable`

---

### 3.3 S3-PyArrow Backend
**Method:** Same as S3 or PyArrow FS stat on bucket root

- If using boto3 client underneath: `head_bucket()`
- If using PyArrow FS: `fs.get_file_info()` on bucket root path
- Both should be lightweight

**Implementation Notes:**
- Consistency with S3 Backend preferred for maintainability
- May need to unwrap underlying boto3 client for `head_bucket()` call

---

### 3.4 SFTP Backend
**Method:** `stat(root_path)` or equivalent

- Checks if root path exists via `os.stat()`-like call
- Paramiko provides `sftp.stat(path)` — returns stat info
- Also validates SSH connectivity and credentials

**Implementation Notes:**
- `sftp.stat(root_path)` already used in existence checks
- Non-destructive: just metadata lookup
- Error mapping: EIO / connection → `BackendUnavailable`, EACCES → `PermissionDenied`, ENOENT → `NotFound`

---

### 3.5 Azure Blob Storage
**Method:** Container properties lookup

- `get_container_properties()` or equivalent
- Non-destructive metadata call
- Validates container exists and credentials work

**Implementation Notes:**
- `ContainerClient.get_container_properties()` is lightweight
- Or use `BlobServiceClient.get_container_client().exists()`
- Error mapping: 403 → `PermissionDenied`, 404 → `NotFound`, connection → `BackendUnavailable`

---

### 3.6 Azure Data Lake Storage (HNS)
**Method:** File system properties or root directory stat

- Similar to non-HNS but may use `DataLakeFileSystemClient.get_file_system_properties()`
- Or `DataLakeFileSystemClient.exists()` check on filesystem
- Validates filesystem exists and credentials work

**Implementation Notes:**
- May reuse `get_file_system_properties()` already used for folder stats
- Or parallel to container check in non-HNS mode

---

### 3.7 Memory Backend
**Method:** Always succeeds

- In-memory backend is always "healthy" by definition
- Return immediately without any checks
- Could optionally verify that root path exists in the tree, but not required

**Implementation Notes:**
- Safe to always return success — no external resources to validate

---

## 4. API Design

### Option A: `store.ping()` (Recommended)

```python
# Store level
def ping(self) -> None:
    """
    Verify the backend is reachable and credentials are valid.

    Non-destructive: performs no data operations, creates no side effects.
    Lightweight: single metadata call per backend.

    Raises
    ------
    PermissionDenied
        If credentials are invalid or insufficient.
    NotFound
        If the backend root path / container / filesystem does not exist.
    BackendUnavailable
        If the backend is unreachable (network, timeout, etc.).

    Examples
    --------
    >>> store = Store(s3_backend, root_path="data")
    >>> store.ping()  # Raises on error, succeeds silently

    >>> try:
    ...     store.ping()
    ... except (PermissionDenied, NotFound, BackendUnavailable) as e:
    ...     print(f"Backend unhealthy: {e}")
    """
```

**Rationale:**
- Familiar terminology from web/API health checks
- Short, memorable method name
- Consistent with Unix/network convention

### Option B: `backend.check_health()` (Alternative)

```python
# Backend ABC level
def check_health(self) -> None:
    """
    Verify the backend is healthy (reachable, credentials valid).
    """
```

**Tradeoff:**
- More explicit about intent
- Longer name
- Less standard in Python ecosystem

### Design Decision: Both
- Expose at **Store level** as `ping()` (user-facing)
- Implement at **Backend ABC level** as `check_health()` (backend contract)
- Store delegates to backend

---

## 5. Error Mapping

Health checks should raise existing error types from the error model (`005-error-model.md`):

| Condition | Exception Type | Details |
|-----------|---|---|
| Credentials invalid | `PermissionDenied` | Backend explicitly rejects credentials |
| Root path missing | `NotFound` | Bucket, container, FS, or directory does not exist |
| Network unreachable | `BackendUnavailable` | Timeout, connection refused, DNS failure |
| Other backend error | `BackendUnavailable` | Generic fallback for unmapped errors |

**No new error types needed** — existing error model covers all scenarios.

---

## 6. Integration Points

### 6.1 Store Lifecycle
- Optional in `__init__()` or shortly after for fail-fast bootstrap
- Separate call — not automatic (user controls when to verify)
- No dependency on Registry — Store can call `ping()` independently

### 6.2 Registry Health
- Could add `Registry.ping()` to verify all registered backends
- Iterates all backends, calls `store.ping()` on each
- Returns first error or succeeds silently

### 6.3 Observability Integration
- `ext.observe` hooks can wrap health checks for monitoring
- OpenTelemetry span for `ping()` call
- Metrics: health check latency, failure rate
- Logging: debug-level entry/exit, info-level on failure

### 6.4 No Tight Coupling
- Health check is independent of existing Store/Backend methods
- Does not affect caching (`ext.cache`)
- Does not interact with batch operations
- Does not require capabilities (not capability-gated)

---

## 7. Testing Strategy

### 7.1 Unit Tests per Backend

For each backend, test:
- **Success case:** Healthy backend → no exception
- **PermissionDenied:** Invalid credentials → raises `PermissionDenied`
- **NotFound:** Missing bucket/path → raises `NotFound`
- **BackendUnavailable:** Mock network failure → raises `BackendUnavailable`

### 7.2 Conformance Tests

In `test_conformance.py`, add:
- `test_check_health_success()` — all backends pass when healthy
- `test_check_health_missing_root()` — NotFound when root missing (skip Memory)
- Error injection tests per backend via mock

### 7.3 Integration Tests

- DockerBackend fixtures: real MinIO, Azurite, SFTP
- Verify actual latency / performance (should be < 1 second)

### 7.4 Examples

- Simple script: `examples/health_check.py` or section in existing example
- Shows Store + health check pattern for startup validation

---

## 8. Specification Outline (for ADR / Spec)

### Spec Structure

**Spec:** `sdd/specs/025-health-check.md` (tentative number)

**Sections:**

1. Overview — use cases and design constraints
2. Store API — `store.ping()` signature and semantics
3. Backend ABC — `Backend.check_health()` contract
4. Per-backend implementation — strategies and error mapping
5. Error Handling — detailed error types and conditions
6. Integration — observability, Registry, lifecycle
7. Non-requirements — what health checks do NOT do
8. Testing — unit, conformance, integration, examples

**Traceability Markers:**
- PING-001 through PING-NNN for spec requirements
- Store method: STORE-016 (tentative)
- Backend method: BE-023 (tentative)

---

## 9. Implementation Roadmap

### Phase 1: Core
1. Add `Backend.check_health()` ABC method (all 6 backends implement)
2. Implement per-backend logic (Local, S3, S3-PyArrow, SFTP, Azure)
3. Add `Store.ping()` delegation
4. Unit tests per backend + conformance suite
5. Spec + ADR

### Phase 2: Observability
1. `ext.observe` wiring (hooks for health checks)
2. OpenTelemetry span support
3. Example: `examples/health_check.py`

### Phase 3: Registry Integration
1. `Registry.ping_all()` or similar (optional convenience method)
2. Docs integration

---

## 10. Known Considerations and Open Questions

### 10.1 Should health checks be capability-gated?

**Decision:** No.

**Rationale:**
- Health checks are orthogonal to data operations
- All backends can provide some form of health verification
- Failure should never be due to missing capability, only backend unavailability

### 10.2 Should health checks cache results?

**Decision:** No, always make a live call.

**Rationale:**
- Health checks are meant to detect transient failures
- Caching would defeat the purpose
- Caller can implement their own caching if needed
- `ext.cache` applies to data operations, not health checks

### 10.3 What about timeout configuration?

**Decision:** Deferred; use backend's default timeout.

**Rationale:**
- Adding timeout parameters complicates the API
- Backends already have timeout configuration
- Can revisit if customers need tunable timeouts

### 10.4 Should health checks verify read or write capability?

**Decision:** Read only (minimal verification).

**Rationale:**
- Write verification would require creating/deleting test files (side effects)
- Read (existence, permissions) is sufficient for startup gates and liveness probes
- Users can test write capability separately if needed

### 10.5 Return type: void (None) vs. bool vs. object?

**Decision:** `None` (void).

**Rationale:**
- Consistent with remote-store error convention: success = return silently, failure = raise
- Boolean return would require catch-all exception for unhealthy state
- `None` is idiomatic Python for "operation succeeded"

---

## 11. Comparison with Other Libraries

### AWS SDK (`boto3`)
- `s3_client.head_bucket()` — validates bucket access
- Returns response metadata; no exception = success
- remote-store aligns with this pattern

### Google Cloud (`google-cloud-storage`)
- `bucket.exists()` — checks bucket existence
- Similar lightweight metadata call

### Azure SDK
- `ContainerClient.exists()` / `get_container_properties()`
- Both lightweight, non-destructive

### fsspec (via s3fs, adlfs, paramiko)
- No standard health check interface
- Each provider has its own validation mechanism
- remote-store standardizing across backends is an improvement

---

## 12. Summary and Recommendations

1. **Method names:** `Store.ping()` (user-facing), `Backend.check_health()` (implementation)
2. **Error types:** Use existing `PermissionDenied`, `NotFound`, `BackendUnavailable`
3. **Implementation:** Per-backend lightweight checks (HeadBucket, stat, exists calls)
4. **No new capabilities:** Health checks are always available
5. **Non-destructive:** Verify without side effects
6. **Testing:** Unit + conformance + integration against real backends
7. **Spec:** Separate spec document (025-health-check.md)
8. **Integration:** Optional observability hooks via `ext.observe`
9. **No caching, no timeouts, no return value** — keep API minimal and idiomatic

---

## Appendix: Pseudocode

### Store.ping()

```python
def ping(self) -> None:
    """Verify backend is reachable and credentials work."""
    return self._backend.check_health()
```

### Backend.check_health() (ABC)

```python
@abstractmethod
def check_health(self) -> None:
    """
    Verify the backend is healthy (reachable, credentials valid).

    Raises
    ------
    PermissionDenied
        Credentials invalid or insufficient.
    NotFound
        Root path / container / filesystem does not exist.
    BackendUnavailable
        Backend unreachable (network, timeout, etc.).
    """
```

### LocalBackend.check_health()

```python
def check_health(self) -> None:
    """Verify root path exists and is readable."""
    try:
        if not os.access(self.root_path, os.R_OK):
            raise PermissionDenied(f"No read access to {self.root_path}")
        if not os.path.exists(self.root_path):
            raise NotFound(f"Root path does not exist: {self.root_path}")
    except OSError as e:
        # Refine based on errno or re-raise as BackendUnavailable
```

### S3Backend.check_health()

```python
def check_health(self) -> None:
    """Verify bucket exists and credentials work via HeadBucket."""
    try:
        self._client.head_bucket(Bucket=self._bucket_name)
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == '403':
            raise PermissionDenied(f"S3 access denied: {e}")
        elif code == '404':
            raise NotFound(f"S3 bucket not found: {self._bucket_name}")
        else:
            raise BackendUnavailable(f"S3 unavailable: {e}")
    except Exception as e:
        # Timeout, connection, etc.
        raise BackendUnavailable(f"S3 unavailable: {e}")
```

---

**Author notes:** This research provides a complete blueprint for implementing health checks. The design is minimal, portable, and consistent with the existing architecture. No blocking issues identified.
