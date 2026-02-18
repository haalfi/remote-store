# Native Path Resolution Specification

## Overview

Native path resolution allows backends to transform validated paths into their
canonical, backend-specific form before every I/O operation. Today `RemotePath`
applies a single set of normalization rules (PATH-002 through PATH-006) that
work for most backends, but some storage systems have additional or different
canonicalization needs (S3 key encoding, SFTP chroot-relative paths, Azure
container/blob separation, case-insensitive filesystems). This spec introduces
a `resolve_path` hook on the Backend ABC and defines how the Store integrates it.

**Relationship to existing specs:**
- Extends `003-backend-adapter-contract.md` (new abstract method on Backend)
- Complements `004-path-model.md` (RemotePath validation is unchanged)
- See also: [ADR-0005](../adrs/0005-native-path-resolution.md)

---

## Design Principles

### NPR-001: Two-Phase Path Pipeline

**Invariant:** Path handling is split into two sequential phases:

1. **Validation** — `RemotePath` rejects unsafe paths (null bytes, `..` segments,
   empty strings). This phase is backend-agnostic and cannot be bypassed.
2. **Resolution** — The backend's `resolve_path()` transforms the validated path
   string into its native canonical form.

**Postconditions:** Phase 1 always runs before phase 2. A backend never receives
an unvalidated path.

### NPR-002: RemotePath Invariants Are Preserved

**Invariant:** All existing `RemotePath` validation rules (PATH-001 through
PATH-014) remain in force. `resolve_path` receives the output of `RemotePath`
normalization and may further transform it, but cannot relax safety invariants.

---

## Backend Hook

### NPR-003: resolve_path Method

**Invariant:** The Backend ABC gains a concrete (non-abstract) method:
```python
def resolve_path(self, path: str) -> str:
    """Transform a validated path into the backend's canonical form.

    :param path: Normalized path string (output of RemotePath).
    :returns: Backend-canonical path string.
    """
    return path  # default: identity
```
**Postconditions:** The default implementation is the identity function.
Backends that do not need custom resolution inherit the default and are
unaffected.

### NPR-004: resolve_path Contract

**Invariant:** Implementations of `resolve_path` must satisfy:
1. **Deterministic** — same input always produces the same output.
2. **Pure** — no side effects, no I/O, no network calls.
3. **Total** — must return a string for every valid input; must not raise.
4. **Non-empty** — must not return an empty string for a non-empty input.

**Raises:** If a backend violates rule 4, the Store raises `InvalidPath`.

### NPR-005: resolve_path Is Not Validation

**Invariant:** `resolve_path` must not reject paths. Path rejection is the
exclusive responsibility of `RemotePath` (phase 1). If a backend cannot
represent a particular path, the operation will fail naturally at the I/O level
with the appropriate error (e.g. `NotFound`, `PermissionDenied`).

---

## Store Integration

### NPR-006: Store Calls resolve_path

**Invariant:** `Store._full_path()` calls `backend.resolve_path()` after
`RemotePath` validation and root-path joining. The resolved path is what the
backend receives for all subsequent I/O.

**Sequence:**
```
user path  →  RemotePath(path)  →  join with root_path  →  backend.resolve_path()  →  backend I/O
```

### NPR-007: Empty Path Bypass

**Invariant:** When `_full_path("")` resolves to the store root (per ADR-0004),
`resolve_path` is still called on the root path string. This ensures the root
path itself is canonicalized by the backend.

### NPR-008: resolve_path Called Once Per Operation

**Invariant:** For any single Store operation, `resolve_path` is called exactly
once per path argument. Multi-path operations (e.g. `move(src, dst)`) call it
once per path.

---

## Backend-Specific Behaviors

### NPR-009: Local Backend

**Invariant:** `LocalBackend.resolve_path()` is the identity (inherits default).
Local paths are already handled by `RemotePath` normalization and Python's
`pathlib`.

### NPR-010: S3 Backend

**Invariant:** `S3Backend.resolve_path()` may apply:
- Stripping a leading `/` (S3 keys are never slash-prefixed).
- Encoding rules for special characters if needed.

**Postconditions:** The returned string is a valid S3 object key.

### NPR-011: SFTP Backend

**Invariant:** `SFTPBackend.resolve_path()` may prepend the configured
`base_path` or apply chroot-relative resolution.
**Postconditions:** The returned string is an absolute POSIX path on the remote
server.

### NPR-012: Future Backends

**Invariant:** New backends (Azure Blob, GCS, etc.) implement `resolve_path` to
handle their native path conventions. The hook is the single extension point for
backend-specific path logic.

---

## Error Handling

### NPR-013: Post-Resolution Empty Path Guard

**Invariant:** If `resolve_path` returns an empty string, the Store raises
`InvalidPath` before calling any backend I/O method.

### NPR-014: No Exception Leakage from resolve_path

**Invariant:** If a backend's `resolve_path` raises an unexpected exception, the
Store catches it and raises `RemoteStoreError` with the original exception as
cause. This maintains the no-native-exception-leakage guarantee (BE-021).

---

## Capability and Backward Compatibility

### NPR-015: No New Capability Required

**Invariant:** `resolve_path` is not gated by a `Capability`. All backends have
it (with the identity default). There is no `Capability.NATIVE_PATH_RESOLUTION`.

### NPR-016: Backward Compatibility

**Invariant:** Existing backends that do not override `resolve_path` behave
identically to the current system. The default identity implementation ensures
zero behavioral change for backends that do not opt in.
