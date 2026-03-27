# TLS CA Bundle Specification

## Overview

Dedicated `tls_ca_bundle` parameter for S3 backends, replacing nested `client_options` workarounds for custom CA certificates. Supports explicit paths and environment variable fallback chains. Early path validation at construction time.

Phase 1 covers `S3Backend` and `S3PyArrowBackend`. Phase 2 (Azure) is deferred.

---

## Parameter

### TLS-001: `tls_ca_bundle` on `S3Backend`

**Invariant:** `S3Backend` accepts an optional `tls_ca_bundle: str | None` keyword argument after `region_name` and before `client_options`.
**Default:** `None` (use SDK defaults).
**Value:** Filesystem path to a PEM-format CA bundle file.

### TLS-002: `tls_ca_bundle` on `S3PyArrowBackend`

**Invariant:** `S3PyArrowBackend` accepts the same `tls_ca_bundle: str | None` keyword argument with identical semantics.

---

## Environment Variable Fallback

### TLS-003: Env var fallback chain for S3 backends

**Invariant:** When `tls_ca_bundle` is `None`, the following environment variables are checked in order. The first non-empty value wins:

| Priority | Env var | Rationale |
|----------|---------|-----------|
| 1 | `AWS_CA_BUNDLE` | boto3 standard |
| 2 | `REQUESTS_CA_BUNDLE` | requests (underlies botocore) |
| 3 | `SSL_CERT_FILE` | OpenSSL standard, broadest fallback |

**Postconditions:**
- Resolution happens once at construction time (not per-request).
- Empty string env vars are treated as unset.
- If all sources are unset/empty, the resolved value is `None` (SDK defaults apply).

---

## Validation

### TLS-004: Early path validation at construction time

**Invariant:** If the resolved CA bundle path (from explicit param or env var) is not `None`, the path is validated at construction time.
**Postconditions:**
- `Path.is_file()` must return `True` (directories are rejected).
- A `ValueError` is raised with a message that includes the path if validation fails.
- Validation is eager: a missing cert is a config error, not a transient network issue.

---

## Injection

### TLS-005: S3Backend `verify` injection into s3fs `client_kwargs`

**Invariant:** When `_tls_ca_bundle` is not `None`, `S3Backend` injects `verify` into `client_kwargs` via `setdefault`.
**Postconditions:**
- An explicit `client_options.client_kwargs.verify` is NOT overridden (backward compat).
- The value is the resolved filesystem path string.

### TLS-006: S3PyArrowBackend `tls_ca_file_path` injection into PyArrow S3FileSystem

**Invariant:** When `_tls_ca_bundle` is not `None`, `S3PyArrowBackend` injects `tls_ca_file_path` into the PyArrow `S3FileSystem` constructor kwargs via `setdefault`.

### TLS-007: S3PyArrowBackend `verify` injection into s3fs side

**Invariant:** When `_tls_ca_bundle` is not `None`, `S3PyArrowBackend` injects `verify` into the s3fs `client_kwargs` via `setdefault`, same as TLS-005.

---

## Phase 2 (Deferred)

### TLS-008: `tls_ca_bundle` on `AzureBackend`

Deferred until demand materializes. Same parameter design, different env var chain.

### TLS-009: Env var fallback chain for Azure

| Priority | Env var |
|----------|---------|
| 1 | `AZURE_CA_CERTIFICATE_PATH` |
| 2 | `REQUESTS_CA_BUNDLE` |
| 3 | `SSL_CERT_FILE` |

### TLS-010: Azure `connection_verify` injection

Inject into `BlobServiceClient` / `DataLakeServiceClient` constructor options.

---

## Manual Testing Note

Integration testing actual TLS with custom CA is impractical with moto. For real verification, use MinIO with a self-signed certificate and a custom CA bundle file.
