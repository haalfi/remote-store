# ProxyStore

Base class for building Store middleware. Subclass it to intercept
specific operations while delegating the rest to the inner Store.

ProxyStore is an [internal delegation base by
design](../../../sdd/adrs/0014-middleware-path-1-proxy-store-stream-wrappers.md) —
it centralises the private-attribute coupling that `ObservedStore` and
`CachedStore` share. It is [documented publicly](../../../sdd/adrs/0015-proxystore-publicly-documented.md)
because it is visible in their inheritance chain and useful for anyone
building custom Store extensions.

::: remote_store.ProxyStore

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    `unwrap`, `native_path`, and `to_key` delegate directly to the inner
    Store and expose backend internals. Using them ties your code to a
    specific backend. `supports()` is portable — it works on all backends.
    See [Store — Interop](store.md#interop-backend-specific) for the full
    contract.

## See also

- [ext.observe](extensions/observe.md) — ObservedStore, built on ProxyStore
- [ext.cache](extensions/cache.md) — CachedStore, built on ProxyStore
- [ext.streams](extensions/streams.md) — composable stream wrappers (an alternative to Store-level proxying)
