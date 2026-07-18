# ADR-0015: Document ProxyStore in the Public API Reference

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0014 |

Amends only the "ProxyStore contract" visibility clause of
[ADR-0014](0014-middleware-path-1-proxy-store-stream-wrappers.md).

## Context

ADR-0014 established `ProxyStore` as "an internal abstract base class …
not part of the public API and must not be subclassed by user code."
That restriction made sense at the time: only two consumers existed
(`ObservedStore`, `CachedStore`) and speculative framework surface was
explicitly avoided.

In practice, `ProxyStore` is already visible to users:

- **Inheritance chain.** The rendered API docs for `ObservedStore` and
  `CachedStore` show `ProxyStore(Store)` in their class hierarchy.
  Users see the name but have no documentation to follow.

- **Extension authors need it.** Anyone building a custom Store wrapper
  (logging, retry, metrics, access control) must either subclass
  `ProxyStore` or re-implement the same private-attribute coupling and
  delegation boilerplate. Hiding the base class forces duplication.

- **No stability cost.** `ProxyStore`'s contract is already implicitly
  stable — changing it would break `ObservedStore` and `CachedStore`,
  which are public. Documenting it adds no new compatibility burden.

## Decision

Export `ProxyStore` from `remote_store` and document it in the API
reference. The class remains an internal delegation base by design:
it centralises private-attribute coupling (`_backend`, `_root`,
`_owns_backend`) and default delegation. It is not a middleware
framework and gains no new hooks or dispatch machinery.

The rest of ADR-0014 (delegation model, `_wrap_child()` hook, stream
wrappers, integrity functions, migration trigger for Path 2) remains
in effect.

## Consequences

- **Documented.** `ProxyStore` has an API reference page, appears in
  `__all__`, and includes a usage example for custom middleware.
- **No new API surface.** No methods, hooks, or configuration are added
  to `ProxyStore`. The class is unchanged.
- **Extension authors unblocked.** Custom Store wrappers can subclass
  `ProxyStore` instead of duplicating its boilerplate.
- **ADR-0014 contract intact.** Construction, delegation, `_wrap_child()`,
  and drift-protection tests all continue as specified.

## References

- Supersedes: ADR-0014 § "ProxyStore contract", first paragraph only
- Backlog: ID-101
