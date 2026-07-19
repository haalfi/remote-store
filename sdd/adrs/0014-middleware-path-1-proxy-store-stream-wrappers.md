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

**Choose Path 1: a `ProxyStore` delegation base plus stream-level wrappers,
not a middleware framework (Path 2).** `ProxyStore` centralizes the
private-attribute coupling (`_backend`, `_root`, `_owns_backend`) and default
delegation shared by `ObservedStore` and `CachedStore`; subclasses override
only the methods they intercept. Progress and checksums ship as `BinaryIO`
wrappers (`ext.streams`) and pure functions (`ext.integrity`), never as Store
proxies. *Reverse when* a third policy-like proxy must compose (see the
migration triggers below); the Path 1 → Path 2 refactor is internal-only and
breaks no public API, so it is safe to defer rather than build speculatively.

**Why Path 1, not a dispatch framework**

- **Only observe + cache compose today.** Retry already ships as per-backend
  native config (ADR-0011, `RetryPolicy`); circuit-breaker, rate-limiting, and
  fault-injection are post-v1 with no committed timeline. Two wrappers do not
  justify dispatch machinery.
- **Progress and checksums are stream concerns, not Store concerns.** A
  `BinaryIO` wrapper composes with any stream, needs no Store wrapping, and
  correctly skips cache hits (no stream to wrap).
- **No breaking changes.** `observe()` and `cached_store()` keep their
  signatures and return types; `ProxyStore` is a base class, not a new public
  surface.

**Scope: what Path 1 delivers**

- `ProxyStore` internal base (`_proxy.py`) with a `_wrap_child()` hook.
- New `ext.streams` (progress + checksum `BinaryIO` wrappers) and `ext.integrity`
  (pure checksum/verify functions). The exact class list and per-symbol
  contracts are owned by specs `033-ext-streams` and `034-ext-integrity`.

**Scope: what Path 1 excludes (the boundary against Path 2)**

- No `ProgressStore`/`ChecksumStore` proxies; no before/after/short-circuit
  hooks; no category dispatch, middleware merging, or public middleware API.
- No `Store.read()`/`write()` signature changes for progress or checksums.
- No data-model change (`ContentDigest`, `FileInfo.digest`/`etag`), deferred
  to ID-008.

**ProxyStore contract**

`ProxyStore(Store)` is a delegation base: it adopts the inner store's backend
coupling, delegates every public `Store` method to its inner store by default,
and propagates `child()` through `_wrap_child()`, which subclasses must
implement (the base raises). Construction, delegation, and `_wrap_child()`
mechanics are owned by `src/remote_store/_proxy.py`; the ADR-0010
drift-protection tests hold delegation to the full `Store` surface. *Amended by
ADR-0015:* the original "internal, must not be subclassed by user code" clause
is superseded; `ProxyStore` is now exported and documented so extension
authors can subclass it.

**Migration trigger for Path 2 (reverse this decision when any becomes true)**

- three or more store-level concerns must compose on one operation path;
- wrapper ordering becomes product-significant, not merely internal;
- one concern must short-circuit another in a general way;
- adding a concern would again require broad override duplication.

## Consequences

- **ProxyStore reduces CachedStore by ~100 lines** (pass-through methods
  eliminated, init coupling centralized).
- **ObservedStore still overrides everything** (it observes all ops), so
  its line count shrinks only moderately. The win is in coupling
  centralization and `child()` propagation.
- **Two-level inheritance** (`Store -> ProxyStore -> CachedStore`) adds
  one layer of indirection. Acceptable for two consumers.
- **`child()` propagation ships with ProxyStore.** Default: child stores
  inherit wrapper behavior via `_wrap_child()`. This fixes BUG-003:
  `cached_store(s).child("sub")` returns a `CachedStore`, not a plain `Store`.
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
