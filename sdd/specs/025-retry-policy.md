# Retry Policy Specification

## Overview

A `RetryPolicy` frozen dataclass provides unified retry configuration across
backends. Each backend maps the policy to its native retry mechanism, avoiding
retry multiplication.

**ADR:** `sdd/adrs/0011-retry-per-backend-native.md`
**Research:** `sdd/research/research-retry-policy.md`

---

## RetryPolicy dataclass

### RET-001: Construction and Defaults

**Invariant:** `RetryPolicy` is a frozen dataclass with five fields.
**Signature:**
```python
@dataclasses.dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    jitter: float = 1.0
    timeout: float | None = None
```
**Postconditions:**
- All fields are immutable (frozen).
- Default `RetryPolicy()` configures 3 attempts with 1-60 s exponential
  backoff and 1 s jitter.

### RET-002: Validation

**Invariant:** `RetryPolicy.__post_init__` validates field constraints.
**Rules:**
- `max_attempts >= 1` (at least one attempt). Raises `ValueError` otherwise.
- `backoff_base >= 0`. Raises `ValueError` otherwise.
- `backoff_max >= 0`. Raises `ValueError` otherwise.
- `jitter >= 0`. Raises `ValueError` otherwise.
- `timeout` must be `> 0` or `None`. Raises `ValueError` otherwise.

### RET-003: `disabled()` Factory

**Invariant:** `RetryPolicy.disabled()` returns a policy with `max_attempts=1`.
**Postconditions:** Equivalent to `RetryPolicy(max_attempts=1)`.

---

## BackendConfig integration

### RET-004: BackendConfig.retry Field

**Invariant:** `BackendConfig` has an optional `retry: RetryPolicy | None`
field (default `None`).
**Postconditions:**
- `None` means "use backend default retry behavior."
- A `RetryPolicy` instance overrides the backend's default retry.

### RET-005: Registry Backend Construction

**Invariant:** `Registry._get_backend()` passes `retry` from
`BackendConfig.retry` into the backend constructor via `options`.
**Postconditions:**
- When `cfg.retry is not None`, `retry=cfg.retry` is included in the
  kwargs passed to the backend factory.
- When `cfg.retry is None`, no `retry` kwarg is passed (backend uses
  its own defaults).

### RET-006: Config Parsing

**Invariant:** `RegistryConfig._from_dict()` parses a nested `retry` dict
in backend config sections into a `RetryPolicy` instance.
**Example:**
```python
{"type": "sftp", "options": {...}, "retry": {"max_attempts": 5}}
```
**Postconditions:**
- `retry` key is parsed into `BackendConfig(retry=RetryPolicy(...))`.
- Unknown keys within `retry` raise `TypeError`.
- Missing `retry` key results in `BackendConfig(retry=None)`.

---

## Per-backend mapping

### RET-010: SFTP Retry Mapping

**Invariant:** `SFTPBackend` accepts `retry: RetryPolicy | None = None`.
**Mapping:**
- `max_attempts` -> `stop_after_attempt(max_attempts)`
- `backoff_base` -> `wait_exponential(min=backoff_base)`
- `backoff_max` -> `wait_exponential(max=backoff_max)`
- `jitter` -> `+ wait_random(0, jitter)` (additive)
- `timeout` -> `| stop_after_delay(timeout)` (combined with attempt limit)
**Postconditions:**
- When `retry is None`, uses current defaults (3 attempts, 2-10 s backoff).
- When `retry` is provided, replaces the hardcoded tenacity parameters.
- Retry scope remains **connection only** (same as SFTP-009).

### RET-011: S3 Retry Mapping

**Invariant:** `S3Backend` accepts `retry: RetryPolicy | None = None`.
**Mapping:**
- `max_attempts` -> `botocore.config.Config(retries={"max_attempts": N,
  "mode": "standard"})` merged into s3fs `client_kwargs.config`.
**Postconditions:**
- When `retry is None`, uses botocore defaults (5 attempts, legacy mode).
- When `retry` is provided, overrides botocore retry config.
- `backoff_base`, `backoff_max`, `jitter`, `timeout` are not directly
  mappable to botocore -- logged as debug-level info if set.

### RET-012: Azure Retry Mapping

**Invariant:** `AzureBackend` accepts `retry: RetryPolicy | None = None`.
**Mapping:**
- `max_attempts` -> `ExponentialRetry(retry_total=max_attempts - 1)`
- `backoff_base` -> `ExponentialRetry(initial_backoff=backoff_base)`
- `jitter` -> `ExponentialRetry(random_jitter_range=jitter)`
**Postconditions:**
- When `retry is None`, uses Azure SDK defaults.
- When `retry` is provided, creates an `ExponentialRetry` policy and
  sets it as `retry_policy` in client options.
- `backoff_max` and `timeout` are not directly mappable -- logged as
  debug-level info if set.

### RET-013: S3-PyArrow Retry Mapping

**Invariant:** `S3PyArrowBackend` accepts `retry: RetryPolicy | None = None`.
**Mapping:**
- `max_attempts` -> `AwsStandardS3RetryStrategy(max_attempts=N)` on
  the PyArrow C++ `S3FileSystem`.
- s3fs side: same as RET-011.
**Postconditions:**
- When `retry is None`, uses PyArrow and botocore defaults.
- When `retry` is provided, configures both PyArrow and s3fs sides.

### RET-014: Local and Memory

**Invariant:** `LocalBackend` and `MemoryBackend` do not accept a `retry`
parameter.
**Postconditions:** Passing `retry` raises `TypeError` from the constructor.

---

## Public API

### RET-020: Top-level Export

**Invariant:** `RetryPolicy` is exported from `remote_store.__init__.__all__`.
**Postconditions:** `from remote_store import RetryPolicy` works.

### RET-021: Repr and Equality

**Invariant:** `RetryPolicy` uses standard frozen dataclass `__repr__`,
`__eq__`, and `__hash__`.
**Postconditions:** Instances are printable, comparable, and usable as
dict keys.
