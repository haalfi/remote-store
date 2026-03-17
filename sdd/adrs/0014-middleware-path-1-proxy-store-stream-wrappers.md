# ADR-0014: Middleware Architecture — Path 1 (ProxyStore + Stream Wrappers)

## Status

Accepted

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
| `_proxy.py` (internal) | `ProxyStore` base class |
| `ext.streams` (new) | `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter` |
| `ext.integrity` (new) | `verify()`, `checksum()`, `ContentDigest` |
| `_models.py` (amended) | `ContentDigest` dataclass, `FileInfo.digest` / `FileInfo.etag` fields |

### What we do NOT build

- No `ProgressStore` or `ChecksumStore` proxy wrappers.
- No `_before_*` / `_after_*` / `_short_circuit_*` hooks on ProxyStore.
- No category dispatch, no middleware merging, no public middleware API.
- No changes to `Store.read()` or `Store.write()` signatures for
  progress or checksums.

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
  inherit wrapper behavior. Each subclass implements `_wrap_child()`.
- **Two proxy layers remain** when composing `observe(cached_store(store))`.
  The performance cost is two Python function calls per operation (<1us),
  negligible against real I/O.
- **Stream wrappers** (`ext.streams`) are independently useful: they work
  with any `BinaryIO`, including from `open_atomic()` or third-party code.

## References

- Research: `sdd/research/research-store-middleware-architecture.md`
- Supersedes: ADR-0010 (proxy pattern stays, but ProxyStore becomes the
  shared base; ADR-0010's drift-protection approach is preserved)
- Backlog: ID-092, ID-093, ID-094, ID-091, BUG-003
