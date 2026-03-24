# ProxyStore

Base class for building Store middleware. Subclass it to intercept
specific operations while delegating the rest to the inner Store.

See [ADR-0014](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0014-middleware-path-1-proxy-store-stream-wrappers.md) for the design rationale.

::: remote_store.ProxyStore

## See also

- [ext.observe](extensions/observe.md) --- ObservedStore, built on ProxyStore
- [ext.cache](extensions/cache.md) --- CachedStore, built on ProxyStore
- [ext.streams](extensions/streams.md) --- composable stream wrappers (an alternative to Store-level proxying)
