# MemoryBackend

API reference for `MemoryBackend`: stores files in an in-process tree. No
filesystem access, no network. Ideal for testing and prototyping.

`MemoryBackend` is a [`DriverBackend`](../drivers.md#remote_store.drivers.DriverBackend)
built over `MemoryDriver`: the driver reads and changes the tree, and the
contract kernel validates keys, guards the root and types every refusal.
`MemoryDriver` is public as a complete, dependency-free example of a driver.

::: remote_store.backends.MemoryBackend
    options:
      show_bases: false

::: remote_store.backends.MemoryDriver
    options:
      show_bases: false

## See also

- [Memory Backend Guide](../../../guides/backends/memory.md) — usage patterns, configuration, and examples
- [Memory Backend example](../../../../examples/advanced/memory_backend.py) — in-memory backend in action
- [Drivers](../drivers.md) — the protocols `MemoryDriver` implements
- [Build Your Own Backend](../../../guides/custom-backend-guide.md) — writing a driver of your own
