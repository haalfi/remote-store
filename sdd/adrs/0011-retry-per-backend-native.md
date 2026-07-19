# ADR-0011: Retry - Per-Backend Native Configuration

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

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

Use **Option B: per-backend native retry configuration**, a `RetryPolicy` that
maps to each backend's own retry mechanism.

- **Retry is a transport concern, so backends own it.** Each backend translates
  one `RetryPolicy` into its native mechanism (SFTP tenacity, S3 botocore, Azure
  `ExponentialRetry`, S3-PyArrow both sides); Local and Memory reject `retry`
  because it is meaningless for local I/O. *Reverse if* a cross-cutting retry
  concern emerges that no single backend can own (e.g. mid-operation reconnect
  spanning backends).
- **The policy replaces SDK defaults rather than stacking on them,** so retries
  do not multiply. That was the flaw in Option A (a Store-level tenacity wrapper)
  and Option C (an `ext/` retry proxy), both of which compose on top of SDK
  retry. *Reverse if* a use case genuinely needs layered retry at two levels.
- **One configuration point: a single frozen dataclass and one constructor
  parameter.** `BackendConfig` carries it and the Registry merges it in, keeping
  the surface minimal and discoverable. *Reverse if* the single knob cannot
  express a required policy and users are pushed back to `client_options`.
- **No new core dependency.** `tenacity` stays confined to the `sftp` extra, not
  the zero-dependency core. *Reverse if* a core-level retry mechanism becomes
  unavoidable.

Application-level retry (mid-operation reconnect, idempotency checks) is out of
scope, and could later be a composing `ext/retry.py` middleware.

The `RetryPolicy` fields and defaults, the `disabled()` factory, the per-backend
SDK mappings, the Local/Memory `TypeError`, and the `BackendConfig`/`from_dict`
wiring are spec-rate and live in [spec 025](../specs/025-retry-policy.md)
(RET-001, RET-003, RET-004 through RET-006, RET-010 through RET-014).

## Consequences

- Users get a single, discoverable retry knob across all cloud backends.
- SFTP retry is no longer hardcoded — users can tune or disable it.
- S3/Azure retry is no longer buried in `client_options`.
- Local/Memory constructors reject `retry` with clear TypeError.
- Lossy mapping: the dataclass cannot express every SDK-specific knob.
  Users who need full control still use `client_options`.
- Future `ext/retry.py` middleware is orthogonal and can compose with
  backend-level retry.
