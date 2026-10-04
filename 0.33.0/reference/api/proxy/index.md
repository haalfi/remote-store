# ProxyStore

Base class for building Store middleware. Subclass it to intercept specific operations while delegating the rest to the inner Store.

ProxyStore is an [internal delegation base by design](https://docs.remotestore.dev/stable/explanation/design/adrs/0014-middleware-path-1-proxy-store-stream-wrappers/index.md) — it centralises the private-attribute coupling that `ObservedStore` and `CachedStore` share. It is [documented publicly](https://docs.remotestore.dev/stable/explanation/design/adrs/0015-proxystore-publicly-documented/index.md) because it is visible in their inheritance chain and useful for anyone building custom Store extensions.

## ProxyStore

```
ProxyStore(inner: Store)
```

Bases: `Store`

Base class for Store proxies that delegate to an inner Store.

All public `Store` methods delegate to `self._inner` by default. Subclasses override only the methods they intercept and must implement `_wrap_child()` to control how `child()` propagates wrapper behavior.

`ObservedStore` and `CachedStore` are built on this base. Subclass it to build your own Store middleware.

Parameters:

- **`inner`** (`Store`) – The Store instance to wrap.

Example

```
from remote_store import ProxyStore, Store

class LoggingStore(ProxyStore):
    def read_bytes(self, path: str) -> bytes:
        print(f"Reading {path}")
        return self.inner.read_bytes(path)

    def _wrap_child(self, inner_child: Store) -> "LoggingStore":
        return LoggingStore(inner_child)
```

### inner

```
inner: Store
```

The wrapped Store instance.

### child

```
child(subpath: str) -> Store
```

Return a child store wrapped with the same proxy behavior.

Delegates to `_wrap_child()` which subclasses must implement.

## Interop (Backend-Specific)

Backend-specific methods

`unwrap`, `native_path`, and `to_key` delegate directly to the inner Store and expose backend internals. Using them ties your code to a specific backend. `supports()` is portable — it works on all backends. See [Store — Interop](https://docs.remotestore.dev/stable/reference/api/store/#interop-backend-specific) for the full contract.

## See also

- [ext.observe](https://docs.remotestore.dev/stable/reference/api/extensions/observe/index.md) — ObservedStore, built on ProxyStore
- [ext.cache](https://docs.remotestore.dev/stable/reference/api/extensions/cache/index.md) — CachedStore, built on ProxyStore
- [ext.streams](https://docs.remotestore.dev/stable/reference/api/extensions/streams/index.md) — composable stream wrappers (an alternative to Store-level proxying)
