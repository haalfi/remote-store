# ADR-0014: Middleware Architecture — Path 1 (ProxyStore + Stream Wrappers)

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ID-006 (progress tracking) and ID-008 (checksum verification) are
cross-cutting concerns that overlap with existing proxy-based extensions
(ObservedStore, CachedStore). The middleware architecture research
(`sdd/research/research-store-middleware-architecture.md`) evaluated eight
design options (A through H) and identified two viable paths:

- **Path 1 (G+E):** Extract a shared `ProxyStore` base class from
  ObservedStore/CachedStore, and implement progress/checksums as
  stream-level wrappers (`ext.streams`) and pure functions
  (`ext.integrity`). No new dispatch model.
- **Path 2 (H):** Build an internal `_MiddlewareProxy` with
  category-scoped dispatch and middleware merging. Eliminates proxy
  nesting entirely, but adds ~150 lines of framework code.

The decision depends on the extension roadmap: how many proxy-based
concerns need to compose?

## Decision

**We choose Path 1 (ProxyStore base + stream wrappers).**

ProxyStore is a delegation base class, not a middleware framework. It
centralizes the private-attribute coupling (`_backend`, `_root`,
`_owns_backend`) and provides default delegation for all Store methods.
Subclasses override only the methods they intercept.

### Rationale

1. **Only observe + cache compose today.** Retry is already shipped as
   per-backend native configuration (ADR-0011, `RetryPolicy`). Circuit
   breaker, rate limiting, and fault injection are post-v1 ideas with
   no committed timeline. Two proxy wrappers do not justify a dispatch
   framework.

2. **Progress and checksums are stream concerns, not Store concerns.**
   `ProgressReader(store.read("file.bin"), callback)` is the right
   abstraction — it composes with any `BinaryIO`, requires no Store
   wrapping, and correctly skips cache hits (no stream to wrap).

3. **No breaking changes.** `observe()` and `cached_store()` factories
   keep their existing signatures and return types. ProxyStore is an
   internal base class, not a public API.

4. **The refactor from Path 1 to Path 2 is internal-only.** If a third
   policy-like proxy becomes necessary, migrating from ProxyStore to
   `_MiddlewareProxy` does not break public API. But we do not build
   that infrastructure speculatively.

### What we build

| Module | Contents |
|--------|----------|
| `_proxy.py` (internal) | `ProxyStore` base class with `_wrap_child()` hook |
| `ext.streams` (new) | `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter` |
| `ext.integrity` (new) | `checksum()`, `verify()` — pure functions returning strings |

### What we do NOT build

- No `ProgressStore` or `ChecksumStore` proxy wrappers.
- No `_before_*` / `_after_*` / `_short_circuit_*` hooks on ProxyStore.
- No category dispatch, no middleware merging, no public middleware API.
- No changes to `Store.read()` or `Store.write()` signatures for
  progress or checksums.
- No data model changes (`ContentDigest`, `FileInfo.digest`/`etag`) —
  those ship separately under ID-008 when backends populate them.

### ProxyStore contract

`ProxyStore(Store)` is an internal abstract base class. It is not part
of the public API and must not be subclassed by user code.

**Construction:** `__init__(self, inner: Store)` copies `_backend`,
`_root`, and `_owns_backend` from the inner store. Exposes
`inner: Store` as a read-only property.

**Delegation:** Every public `Store` method has a default implementation
that delegates to `self._inner.<method>(...)`. Subclasses override only
the methods they intercept. Drift-protection tests (from ADR-0010)
verify that ProxyStore covers the full Store API surface.

**`_wrap_child()` hook:** `ProxyStore.child(subpath)` calls
`self._inner.child(subpath)` to create the inner child, then calls
`self._wrap_child(inner_child) -> Store` to let the subclass wrap it.

- The base `_wrap_child()` raises `NotImplementedError` — subclasses
  must provide an implementation.
- `CachedStore._wrap_child()` returns a new `CachedStore` with the same
  TTL, max_entries, and backend config.
- `ObservedStore._wrap_child()` returns a new `ObservedStore` with the
  same hooks.
- Subclasses must not return `None`. The return value must be a `Store`.

This fixes BUG-003: `cached_store(s).child("sub")` now returns a
`CachedStore`, not a plain `Store`.

### Migration trigger for Path 2

Move to merged middleware only when one of these becomes true:

- Three or more store-level concerns must compose on the same operation path.
- Ordering between wrappers becomes product-significant, not just internal.
- One concern must short-circuit another in a general way.
- Adding a new concern would require broad override duplication again.

## Consequences

- **ProxyStore reduces CachedStore by ~100 lines** (pass-through methods
  eliminated, init coupling centralized).
- **ObservedStore still overrides everything** (it observes all ops), so
  its line count shrinks only moderately. The win is in coupling
  centralization and `child()` propagation.
- **Two-level inheritance** (`Store -> ProxyStore -> CachedStore`) adds
  one layer of indirection. Acceptable for two consumers.
- **`child()` propagation ships with ProxyStore.** Default: child stores
  inherit wrapper behavior via `_wrap_child()`.
- **Two proxy layers remain** when composing `observe(cached_store(store))`.
  The performance cost is two Python function calls per operation (<1us),
  negligible against real I/O.
- **Stream wrappers** (`ext.streams`) are independently useful: they work
  with any `BinaryIO`, including from `open_atomic()` or third-party code.

## Related work

- **ID-008 (ContentDigest / FileInfo model change):** The research
  document (§5) proposes replacing `FileInfo.checksum` with
  `ContentDigest` (digest + etag). That model change is deferred to a
  separate PR — it has its own ripple radius (backends, tests, docs) and
  is not required for stream wrappers or integrity functions to ship.

## References

- Research: `sdd/research/research-store-middleware-architecture.md`
- Extends: ADR-0010 (proxy-subclass pattern stays; ProxyStore becomes
  the shared base; ADR-0010's drift-protection approach is preserved)
- Backlog: ID-092, ID-093, ID-094, ID-091, BUG-003
