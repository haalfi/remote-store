# ADR-0030: Azure HNS Is an Explicit Declaration, Not Auto-Detected

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ADLS Gen2 (Hierarchical Namespace, HNS) accounts and plain Blob Storage
accounts differ in semantics the Azure backend must adapt to: atomic
`rename_file` vs copy+delete `move`, real directories vs virtual prefixes,
single-call recursive delete vs iterate-and-delete. The backend originally
discovered which mode an account was in by probing `GetAccountInfo`
(`get_account_information() -> is_hns_enabled`) on first use and caching the
result for the instance lifetime.

That implicit probe was the root cause of a family of failure modes:

- **Sticky misdetection.** A wrong cached result (e.g. an RBAC-propagation
  `403` on the account-level call right after provisioning) degraded an HNS
  account to flat semantics for the entire instance lifetime.
- **Per-operation re-probe storm.** The interim mitigation (do not cache a
  *failed* probe) meant a *persistently* failing probe re-ran on every
  operation.
- **Torn reads within one operation.** Because an uncached probe could
  re-evaluate mid-operation, `move` / `copy` had to snapshot the HNS state at
  entry so a single logical operation could not straddle the HNS and non-HNS
  code paths.

Each mitigation bounded the damage without removing the cause: the account's
nature was being *guessed* at runtime from a network call that can fail,
return stale authorization state, or be denied by least-privilege credentials.

The account's HNS status is a fixed, deployment-time fact. Treating a fixed
fact as a runtime discovery is the design error.

## Decision

The Azure backend no longer auto-detects HNS. The account's nature is a
**mandatory, explicit** constructor and config input, declared as a required
`hns: bool` on both `AzureBackend` and `AsyncAzureBackend` (no default; a
missing or non-`bool` value raises at construction).

- `AzureBackend(..., hns: bool)` and `AsyncAzureBackend(..., hns: bool)` —
  there is no default. A backend constructed without `hns`, or with a
  non-`bool` value, raises `ValueError` at construction time (fail loud, never
  silently infer). The declaration must be a real boolean, not a truthy/falsy
  proxy: config env-var resolution yields strings, so a `${VAR}` placeholder
  resolving to `"false"` would otherwise coerce to `True` via `bool(...)` and
  silently re-enable HNS — the very misdetection class this decision removes.
- `_hns` becomes an immutable attribute set from the declared value. No probe,
  no cache, no warn-once state, no per-operation snapshot.

For users who do not know an account's HNS status, a public one-shot helper
discovers it explicitly:

- `AzureUtils.detect_hns(...)` (sync) and `AzureUtils.adetect_hns(...)` (async)
  issue a single `GetAccountInfo` call and return a `bool`. Unlike the former
  implicit probe, these are **fail-loud**: a probe error is mapped to a
  `remote_store` error and raised, not swallowed and degraded to flat
  semantics.

This mirrors the established helper pattern for connection facts that are
discoverable but should not be silently inferred: `SFTPUtils.scan_host_keys`
and `GraphUtils.resolve_drive_id`.

### Why mandatory rather than a detected default

A detected default reintroduces every failure mode above: the probe can fail,
return stale authorization state, or be denied. A declared value cannot. The
small one-time cost — the user must state a fact they already know, or call
`detect_hns()` once — buys the removal of an entire failure class and makes the
backend's behaviour deterministic from construction.

### Migration

This is a breaking change: every existing Azure call site must add `hns=`.
Pre-v1 semver permits the change in a minor bump. The migration guide documents
the before/after and the `detect_hns()` discovery recipe.

## Consequences

- The backend is deterministic from construction: no network call decides which
  semantics apply, and no operation can observe a different HNS state than the
  one declared.
- The sticky-misdetection, re-probe-storm, and torn-read failure modes are
  removed by construction, not bounded.
- `AzureUtils.detect_hns()` / `adetect_hns()` join the public API as the
  sanctioned discovery path, fail-loud by contract.
- Existing users must declare `hns=`; the change is breaking and documented in
  the migration guide.
- The `GetAccountInfo` probe logic is relocated (into `detect_hns`), not
  deleted — discovery remains available, but only when the user explicitly asks
  for it.
