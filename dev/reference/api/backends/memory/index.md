# MemoryBackend

API reference for `MemoryBackend` — stores files in an in-process data structure. No filesystem access, no network. Ideal for testing and prototyping.

## MemoryBackend

```
MemoryBackend()
```

In-memory backend using a tree-indexed data structure.

Zero dependencies, no filesystem access, no network. Designed as a drop-in backend for unit testing, interactive exploration, and documentation examples.

All capabilities except `GLOB` are supported. The full conformance suite passes with zero skips.

## See also

- [Memory Backend Guide](https://docs.remotestore.dev/stable/guides/backends/memory/index.md) — usage patterns, configuration, and examples
- [Memory Backend example](https://docs.remotestore.dev/stable/tutorial/examples/memory-backend/index.md) — in-memory backend in action
