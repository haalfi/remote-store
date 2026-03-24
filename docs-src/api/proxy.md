# ProxyStore

Base class for building Store middleware. Subclass it to intercept
specific operations while delegating the rest to the inner Store.

ProxyStore is an internal delegation base by design
([ADR-0014](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0014-middleware-path-1-proxy-store-stream-wrappers.md)) —
it centralises the private-attribute coupling that `ObservedStore` and
`CachedStore` share. It is documented here because it is visible in
their inheritance chain and useful for anyone building custom Store
extensions ([ADR-0015](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0015-proxystore-publicly-documented.md)).

::: remote_store.ProxyStore

## See also

- [ext.observe](extensions/observe.md) — ObservedStore, built on ProxyStore
- [ext.cache](extensions/cache.md) — CachedStore, built on ProxyStore
- [ext.streams](extensions/streams.md) — composable stream wrappers (an alternative to Store-level proxying)
