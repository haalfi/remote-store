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

**HNS status is a mandatory, explicit declaration, never auto-detected.** Both
`AzureBackend` and `AsyncAzureBackend` take a required `hns: bool` (no default);
`_hns` is set once from it, with no probe, cache, warn-once state, or
per-operation snapshot.

- **Why mandatory rather than a detected default.** The account's HNS status is a
  fixed, deployment-time fact, but the old `GetAccountInfo` probe *guessed* it at
  runtime from a network call that can fail, return stale authorization state
  (e.g. an RBAC-propagation `403`), or be denied by least-privilege credentials.
  That produced sticky misdetection, per-operation re-probe storms, and torn
  reads mid-operation. A declared value cannot fail, so the one-time cost of
  stating a known fact buys removal of the entire failure class and determinism
  from construction. The value must be a real `bool`, not a truthy/falsy proxy,
  because config env-var resolution yields strings and a `"false"` placeholder
  would otherwise coerce to `True` and silently re-enable HNS. *Reverse if* a
  deployment-time-reliable, authorization-independent way to detect HNS emerges.
- **Discovery stays available, but only when asked, and fail-loud.**
  `AzureUtils.detect_hns()` / `adetect_hns()` issue a single `GetAccountInfo`
  call and return a `bool`; unlike the former implicit probe, a probe error is
  raised rather than swallowed and degraded to flat semantics. This mirrors the
  established pattern for connection facts that are discoverable but must not be
  silently inferred (`SFTPUtils.scan_host_keys`, `GraphUtils.resolve_drive_id`).
  *Reverse if* discovery becomes reliable enough to fold back into construction.

The exact constructor signatures, the `ValueError` validation, the real-`bool`
coercion rule, `_hns` immutability, and the `detect_hns`/`adetect_hns` contract
are spec-rate and live in [spec 012](../specs/012-azure-backend.md) (AZ-001,
AZ-005, AZ-006). The breaking migration (every call site adds `hns=`) is in
Consequences.

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
