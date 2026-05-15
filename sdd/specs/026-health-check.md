# Health Check Specification

## Overview

A lightweight, non-destructive health check verifies that a backend is reachable
and credentials are valid. Enables startup gates ("fail before accepting
traffic"), liveness probes (Kubernetes), and connection validation.

**Research:** `sdd/research/research-health-check.md`

---

## Store API

### PING-001: `Store.ping()`

**Invariant:** `Store.ping()` delegates to `Backend.check_health()`.
**Signature:**
```python
def ping(self) -> None: ...
```
**Postconditions:**
- Returns `None` on success (backend is reachable and credentials are valid).
- Raises on failure — exception type depends on the failure mode:
  - `PermissionDenied` for invalid credentials.
  - `NotFound` for missing bucket/container/path.
  - `BackendUnavailable` for network/DNS/timeout errors.
- Not capability-gated (all backends support health checks).
- Logs `DEBUG` on entry, `INFO` on success.

---

## Backend API

### PING-002: `Backend.check_health()`

**Invariant:** `Backend.check_health()` is a concrete (non-abstract) method
with a default no-op implementation. Backends override it to perform a
lightweight connectivity check.
**Signature:**
```python
def check_health(self) -> None: ...
```
**Postconditions:**
- Default implementation is a no-op (always succeeds).
- Backends that override it perform the cheapest possible read-only operation
  to verify reachability and credential validity.
- Must not modify backend state (no writes, no deletes).
- Must map native exceptions through the backend's error mapper.

---

## Per-Backend Health Checks

### PING-003: LocalBackend

**Strategy:** Verify root directory exists and is readable.
```python
if not self._root.exists():
    raise NotFound(...)
if not os.access(self._root, os.R_OK):
    raise PermissionDenied(...)
```

### PING-004: S3Backend

**Strategy:** `head_bucket` via s3fs's synchronous `call_s3` wrapper, inside `_s3fs_errors()`.
```python
with self._s3fs_errors():
    self._fs.call_s3("head_bucket", Bucket=self._bucket)
```
`self._fs.s3` is the raw `aiobotocore` client — its methods return
coroutines, so calling `self._fs.s3.head_bucket(...)` directly never
issues the request. `call_s3` is the synchronous wrapper that awaits the
call on the s3fs event loop (the same path `head_object` already uses).

### PING-005: S3PyArrowBackend

**Strategy:** `get_file_info` on the bucket path, inside `_pyarrow_errors()`.
```python
with self._pyarrow_errors():
    self._pa_fs.get_file_info(self._bucket)
```

### PING-006: SFTPBackend

**Strategy:** `stat` on `base_path`, inside `_errors()`.
```python
with self._errors():
    self._sftp.stat(self._base_path)
```

### PING-007: AzureBackend

**Strategy:** `get_container_properties()` (non-HNS) or
`get_file_system_properties()` (HNS), inside `_errors()`.
```python
with self._errors():
    if self._hns:
        self._fs.get_file_system_properties()
    else:
        self._cc.get_container_properties()
```

### PING-008: MemoryBackend

**Strategy:** No-op. In-memory backend is always healthy. Uses the default
`Backend.check_health()` implementation (no override needed).

---

## Error Mapping

### PING-009: Error Classification

**Invariant:** Health check failures are mapped through each backend's existing
error mapper (`_errors()`, `_pyarrow_errors()`, `_classify()`).
**Rules:**
- Invalid credentials -> `PermissionDenied`
- Missing bucket/container/path -> `NotFound`
- Network/DNS/timeout -> `BackendUnavailable`
- Other failures -> `RemoteStoreError`

---

## Observe Integration

### PING-010: `on_ping` Hook

**Invariant:** `ext.observe` fires `on_ping` after `Store.ping()`.
**Rules:**
- `_OP_HOOK_MAP["ping"] = "on_ping"`
- `observe()` accepts `on_ping` keyword argument.
- `ObservedStore.ping()` wraps `inner.ping()` with `_observe_op("ping", "", {})`.
