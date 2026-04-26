# Async API

The `remote_store.aio` module provides native `async`/`await` support
for store operations. See [Store](store.md) for the synchronous
counterpart.

---

## AsyncStore

::: remote_store.aio.AsyncStore
    options:
      members: false

### Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, see
    [Store](store.md) or the [Async Store Guide](../async.md).

::: remote_store.aio.AsyncStore.unwrap
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.native_path
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.to_key
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.supports
    options:
      show_root_heading: true
      heading_level: 4

!!! info
    `supports()` itself is portable — it works on all backends. Only the
    capability-gated methods it guards are backend-specific.

---

## AsyncBackend

::: remote_store.aio.AsyncBackend
    options:
      members: false

!!! info "Implementing an async backend"
    Subclass `AsyncBackend` and implement all abstract methods. Map every
    backend-native exception to a `remote_store` error — native exceptions
    must never leak to callers.

### Identity

::: remote_store.aio.AsyncBackend.name
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.capabilities
    options:
      show_root_heading: true
      heading_level: 4

### Existence

::: remote_store.aio.AsyncBackend.exists
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.is_file
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.is_folder
    options:
      show_root_heading: true
      heading_level: 4

### Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.aio.AsyncBackend.read
    options:
      show_root_heading: true
      heading_level: 4

!!! info "Quality flag: `Capability.LAZY_READ`"
    When declared, data is fetched lazily — partial reads avoid loading the whole
    file. Without it, the backend may buffer content before returning the stream.

::: remote_store.aio.AsyncBackend.read_bytes
    options:
      show_root_heading: true
      heading_level: 4

### Writing

!!! note "Requires `Capability.WRITE`"
    `write()` raises `CapabilityNotSupported` on backends that do not declare
    this capability. Most backends declare it.
    `write_atomic()` additionally requires `Capability.ATOMIC_WRITE`.

!!! info "Quality flag: `Capability.WRITE_RESULT_NATIVE`"
    When declared, the returned `WriteResult` fields (`etag`, `version_id`,
    `last_modified`, `digest`) are populated from the backend's write response.
    Without it, only locally computable fields are set.

::: remote_store.aio.AsyncBackend.write
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncBackend.write_atomic
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

### Deleting

!!! note "Requires `Capability.DELETE`"
    All delete methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncBackend.delete
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.delete_folder
    options:
      show_root_heading: true
      heading_level: 4

### Listing and Iteration

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncBackend.list_files
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncBackend.list_folders
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.iter_children
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.GLOB`"
    `glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncBackend.glob
    options:
      show_root_heading: true
      heading_level: 4

### Metadata

!!! note "Requires `Capability.METADATA`"
    Both methods raise `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncBackend.get_file_info
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncBackend.get_folder_info
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

### File Operations

!!! note "Requires `Capability.MOVE` / `Capability.COPY`"
    `move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`.
    Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

::: remote_store.aio.AsyncBackend.move
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.MOVE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Quality flag: `Capability.ATOMIC_MOVE`"
    When declared, `move()` is guaranteed atomic under concurrent access.
    Check `store.supports(Capability.ATOMIC_MOVE)` to query at runtime.

::: remote_store.aio.AsyncBackend.copy
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

### Lifecycle

::: remote_store.aio.AsyncBackend.aclose
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.check_health
    options:
      show_root_heading: true
      heading_level: 4

### Introspection

::: remote_store.aio.AsyncBackend.resolve
    options:
      show_root_heading: true
      heading_level: 4

### Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.

::: remote_store.aio.AsyncBackend.unwrap
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.native_path
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncBackend.to_key
    options:
      show_root_heading: true
      heading_level: 4

---

## SyncBackendAdapter

::: remote_store.aio.SyncBackendAdapter
    options:
      members: false

---

## AsyncBackendSyncAdapter

::: remote_store.AsyncBackendSyncAdapter
    options:
      members: false

---

## AsyncMemoryBackend

::: remote_store.aio.AsyncMemoryBackend
    options:
      members: false

---

## AsyncAzureBackend

::: remote_store.aio.AsyncAzureBackend
    options:
      members: false

---

## AsyncWritableContent

::: remote_store.aio.AsyncWritableContent

---

## See also

- [Async Store Guide](../async.md) — usage patterns, streaming, FastAPI integration
- [Example: Async Store](../examples/async-store.md) — runnable demo script
- [Store](store.md) — synchronous counterpart
- [Concurrency](../concurrency.md) — thread safety and atomicity semantics
- [aio.ext.write](extensions/aio-write.md) — async write helpers with client-side hashing
- [Write Integrity guide](../write-integrity.md) — hashing workflows for sync and async
