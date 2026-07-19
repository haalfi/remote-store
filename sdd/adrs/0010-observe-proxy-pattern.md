# ADR-0010: Observe - Proxy Subclass Pattern

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ID-024 (`ext.observe`) needs a mechanism to intercept every public
`Store` method so that user-defined callbacks fire before and after each
operation. Two implementation strategies were evaluated during research
(`sdd/research/research-logging-monitoring-tracing.md`, section 5):

**Option A — Proxy subclass.** `ObservedStore(Store)` explicitly
overrides every public method. Each override wraps the delegation in
timing, hook dispatch, and error capture. The proxy is a real `Store`
subclass, so `isinstance(observed, Store)` is `True`, type checkers see
the full API, and IDE autocomplete works out of the box.

**Option B — `__getattr__` proxy.** A thin wrapper intercepts attribute
access at runtime and wraps each call dynamically. This automatically
picks up new methods without code changes, but loses static type safety,
breaks IDE navigation, and makes the instrumentation logic opaque.

The key maintenance hazard with Option A: when a new public method is
added to `Store`, the proxy silently inherits the un-instrumented base
implementation — calls bypass hooks with no warning.

## Decision

Use **Option A (proxy subclass)**: `ObservedStore(Store)` explicitly overrides
every public method, guarded by a **mandatory drift-protection test** (OBS-007)
that fails CI if any public `Store` method lacks an override.

- **Why a real subclass, not a `__getattr__` proxy (Option B).** An explicit
  subclass keeps `isinstance(observed, Store)` true, preserves static typing and
  IDE navigation, and keeps the instrumentation legible; a `__getattr__` wrapper
  auto-picks-up new methods but loses all three. *Reverse if* the maintenance cost
  of explicit overrides ever outweighs that benefit (for example, if `Store`
  grows large and volatile).
- **The drift test is what makes Option A viable.** Option A's one hazard is that
  a newly added `Store` method silently inherits the un-instrumented base and
  bypasses hooks; OBS-007 catches that at CI. The test is a hard requirement for
  any proxy subclass of `Store`, not an optional extra.
- **Named `ext.observe`, not `ext.notify`.** "Observe" describes the read-only,
  side-effect-free nature of the hooks; the factory is `observe()`. *Reverse if*
  the hooks ever gain interception or mutation semantics, at which point
  "notify"/"intercept" naming fits.

The `__dict__`-introspection mechanism of the drift test and the `observe()`
signature are spec-rate and live in [spec 019](../specs/019-ext-observe.md)
(OBS-002, OBS-007).

## Consequences

- **Type safety preserved.** `ObservedStore` is a `Store` subclass
  with explicit signatures. `mypy --strict` checks all overrides.
- **IDE-friendly.** Autocomplete, go-to-definition, and hover docs
  work as expected because every method is explicitly defined.
- **Drift caught at CI.** The drift-protection test prevents silent
  bypass when `Store` gains new public methods. This is the primary
  safety net that makes Option A viable.
- **More code to maintain.** Each new `Store` method requires a
  corresponding override in `ObservedStore`. The drift-protection
  test ensures this is not forgotten.
- **Pattern reusable.** Future wrappers (cache, retry, circuit breaker)
  can follow the same proxy + drift-protection approach.
