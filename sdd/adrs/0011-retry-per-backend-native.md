# ADR-0011: Retry - Per-Backend Native Configuration

## Status

Accepted

## Context

ID-010 requires a unified retry policy for transient backend errors.
The SFTP backend has hardcoded tenacity retry on `_connect()` (3 attempts,
2-10 s exponential). S3 and Azure rely on their SDK's built-in retry.
There is no unified user-facing retry surface.

Four options were evaluated in the research
(`sdd/research/research-retry-policy.md`, section 4):

**Option A - Unified tenacity at Store level.** Wraps every Store method
with tenacity retry. Causes retry multiplication (SDK retries x Store
retries = excessive attempts). Wrong abstraction level.

**Option B - Per-backend native retry configuration.** A `RetryPolicy`
dataclass maps to each backend's native retry mechanism. Replaces SDK
defaults, no multiplication.

**Option C - Store-level retry middleware (`ext/`).** A retry proxy in
`ext/retry.py`, similar to `ext.observe`. Additive, but stacks on top
of SDK retry and is harder to reason about.

**Option D - Hybrid B + C.** Most complex, two configuration points.

## Decision

Use **Option B (per-backend native configuration)**.

1. Backends own their transport — retry is a transport concern.
2. The policy replaces SDK defaults, avoiding retry multiplication.
3. Minimal API surface: one frozen dataclass, one constructor parameter.
4. No new core dependencies — `tenacity` stays in the SFTP `sftp` extra.

### RetryPolicy dataclass

A frozen dataclass in `_config.py` with five fields:

- `max_attempts` (int, default 3): Total attempts including initial.
  Set to 1 to disable retry.
- `backoff_base` (float, default 1.0): Base delay in seconds.
- `backoff_max` (float, default 60.0): Ceiling for exponential backoff.
- `jitter` (float, default 1.0): Max random jitter per delay.
- `timeout` (float | None, default None): Total wall-clock limit.

A `RetryPolicy.disabled()` classmethod returns `RetryPolicy(max_attempts=1)`.

### Backend mapping

Each backend translates the policy into its native retry mechanism:

- **SFTP:** Replaces hardcoded tenacity decorator with policy-driven
  `stop_after_attempt`, `wait_exponential`, `wait_random`, optionally
  `stop_after_delay`.
- **S3:** Maps to `botocore.config.Config(retries={"max_attempts": N,
  "mode": "standard"})` merged into `client_options`.
- **Azure:** Maps to `ExponentialRetry(retry_total=N-1,
  initial_backoff=base, random_jitter_range=jitter)` set as
  `retry_policy` in client options.
- **S3-PyArrow:** Maps to both PyArrow C++ side (`max_attempts`) and
  s3fs side (same as S3).
- **Local/Memory:** Do not accept `retry` parameter — TypeError if
  provided (correct: retry is meaningless for local I/O).

### BackendConfig integration

`BackendConfig` gains a `retry: RetryPolicy | None = None` field.
`Registry._get_backend()` merges `retry` into `options` before
constructing the backend. `from_dict()` parses `retry` from nested
dicts in the config.

### Scope

The policy controls **connection retry** (SFTP) and **SDK-level
operation retry** (S3, Azure). Application-level retry (reconnect
mid-operation, idempotency checks) is out of scope and could be
addressed by a future `ext/retry.py` middleware.

## Consequences

- Users get a single, discoverable retry knob across all cloud backends.
- SFTP retry is no longer hardcoded — users can tune or disable it.
- S3/Azure retry is no longer buried in `client_options`.
- Local/Memory constructors reject `retry` with clear TypeError.
- Lossy mapping: the dataclass cannot express every SDK-specific knob.
  Users who need full control still use `client_options`.
- Future `ext/retry.py` middleware is orthogonal and can compose with
  backend-level retry.
