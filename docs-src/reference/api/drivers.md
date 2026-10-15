# Drivers

`remote_store.drivers` holds the contract kernel and the protocols a backend is
written against. A driver implements the wire primitives of one storage system;
[`DriverBackend`](#remote_store.drivers.DriverBackend) (sync) or
[`AsyncDriverBackend`](#remote_store.drivers.AsyncDriverBackend) (async) wraps
it into a complete [`Backend`](backend.md) or [`AsyncBackend`](aio/backend.md).
Each protocol method's docstring states what the kernel relies on that method
to do. The [Build Your Own Backend](../../guides/custom-backend-guide.md) guide
walks through writing one.

!!! info "Construction checks the declarations"
    Building a `DriverBackend` or `AsyncDriverBackend` raises `ValueError` when
    a declared capability has no protocol to back it, when a flat driver has
    folder objects, when folder objects come without `remove_folder` or
    explicit parents without `ensure_parents`, or when the class's
    `close_is_terminal` differs from the driver's.

---

## Kernel

::: remote_store.drivers.DriverBackend
    options:
      show_root_heading: true
      heading_level: 3
      members: false

::: remote_store.drivers.AsyncDriverBackend
    options:
      show_root_heading: true
      heading_level: 3
      members: false

---

## Driver protocols

::: remote_store.drivers.Driver
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncDriver
    options:
      show_root_heading: true
      heading_level: 3

---

## Records

::: remote_store.drivers.Entry
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.Page
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.PutResult
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.Op
    options:
      show_root_heading: true
      heading_level: 3

---

## Optional protocols

Each is detected on the driver instance when the kernel is constructed.

::: remote_store.drivers.SupportsRangeRead
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsOpenWrite
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.WriteHandle
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsAtomicMove
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsRename
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsCopy
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsDeleteTree
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsRemoveFolder
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsEnsureParents
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsFolderStats
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.SupportsGlob
    options:
      show_root_heading: true
      heading_level: 3

---

## Async optional protocols

The async mirrors of the protocols above: the same members, as coroutines
(`glob` returns an async iterator).

::: remote_store.drivers.AsyncSupportsRangeRead
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsOpenWrite
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncWriteHandle
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsAtomicMove
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsRename
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsCopy
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsDeleteTree
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsRemoveFolder
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsEnsureParents
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsFolderStats
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.drivers.AsyncSupportsGlob
    options:
      show_root_heading: true
      heading_level: 3

**Related types:** [`Capability`](capabilities.md), [`CapabilitySet`](capabilities.md), [`ResolutionPlan`](models.md#remote_store.ResolutionPlan), [`RemoteStoreError`](errors.md#remote_store.RemoteStoreError).

## See also

- [Build Your Own Backend](../../guides/custom-backend-guide.md) — writing a driver, step by step
- [MemoryBackend](backends/memory.md) — a shipped backend built on a driver (`MemoryDriver`)
- [AsyncMemoryBackend](aio/backends/memory.md) — its async twin (`AsyncMemoryDriver`)
- [Backend](backend.md) — the interface the kernel implements
