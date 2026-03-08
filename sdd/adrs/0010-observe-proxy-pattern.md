# ADR-0010: Observe - Proxy Subclass Pattern

## Status

Accepted

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

Use **Option A (proxy subclass)** with a mandatory **drift-protection
test** that asserts `ObservedStore` overrides every public method of
`Store`. This catches missing overrides at CI time.

The drift-protection test inspects `Store.__dict__` for public callable
members and verifies that `ObservedStore.__dict__` contains an override
for each one. This is specified as OBS-007 in the spec.

### Reusability

The proxy subclass pattern established here is reusable for future
wrappers such as `ext.cache` (ID-025). The drift-protection test
technique generalises: any proxy subclass of `Store` can include an
analogous assertion.

### Naming

The extension is named `ext.observe` (not `ext.notify` from the
original backlog). "Observe" better describes the read-only,
side-effect-free nature of the hooks — they observe operations but do
not intercept or modify them. The factory function is `observe()`.

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
