# AsyncBackend

`AsyncBackend` is the abstract base class for native async backends — the
async counterpart of [`Backend`](../backend.md). Subclass it to implement a
backend that talks to its store with `async`/`await`. It lives in
`remote_store.aio`.

::: remote_store.aio.AsyncBackend
    options:
      members: false

!!! info "Implementing an async backend"
    Subclass `AsyncBackend` and implement all abstract methods. Map every
    backend-native exception to a `remote_store` error — native exceptions
    must never leak to callers.

## Identity

::: remote_store.aio.AsyncBackend.name
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.capabilities
    options:
      show_root_heading: true
      heading_level: 3

## Existence

::: remote_store.aio.AsyncBackend.exists
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.is_file
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.is_folder
    options:
      show_root_heading: true
      heading_level: 3

## Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.aio.AsyncBackend.read
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Quality flag: `Capability.LAZY_READ`"
    When declared, data is fetched lazily — partial reads avoid loading the whole
    file. Without it, the backend may buffer content before returning the stream.

::: remote_store.aio.AsyncBackend.read_bytes
    options:
      show_root_heading: true
      heading_level: 3

## Writing

!!! note "Requires `Capability.WRITE`"
    `write()` raises `CapabilityNotSupported` on backends that do not declare
    this capability. Most backends declare it.
    `write_atomic()` additionally requires `Capability.ATOMIC_WRITE`.

!!! info "Quality flag: `Capability.WRITE_RESULT_NATIVE`"
    When declared, the returned `WriteResult` rich fields (`etag`, `version_id`,
    `last_modified`, `digest`) are populated from the backend's write response —
    each only when that response carries it, so a native backend may leave some,
    or even all, of them `None`. SFTP, for instance, declares the flag but its
    write response carries no metadata, so it returns every rich field `None`
    (call `get_file_info()` for the metadata). Without the flag, only locally
    computable fields are set.

::: remote_store.aio.AsyncBackend.write
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncBackend.write_atomic
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

## Deleting

!!! note "Requires `Capability.DELETE`"
    All delete methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncBackend.delete
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.delete_folder
    options:
      show_root_heading: true
      heading_level: 3

## Listing and Iteration

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncBackend.list_files
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncBackend.list_folders
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.iter_children
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.glob
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.GLOB`"
    `glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.

## Metadata

!!! note "Requires `Capability.METADATA`"
    `get_file_info()` requires `Capability.METADATA`.
    `get_folder_info()` requires `Capability.METADATA` without `max_depth`,
    or `Capability.LIST` when `max_depth` is set.

::: remote_store.aio.AsyncBackend.get_file_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncBackend.get_folder_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Capability depends on `max_depth`"
    Without `max_depth`: requires `Capability.METADATA`.
    With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

## File Operations

!!! note "Requires `Capability.MOVE` / `Capability.COPY`"
    `move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`.
    Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

::: remote_store.aio.AsyncBackend.move
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.MOVE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Quality flag: `Capability.ATOMIC_MOVE`"
    When declared, `move()` is guaranteed atomic under concurrent access.
    Check `store.supports(Capability.ATOMIC_MOVE)` to query at runtime.

::: remote_store.aio.AsyncBackend.copy
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

## Lifecycle

::: remote_store.aio.AsyncBackend.aclose
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.check_health
    options:
      show_root_heading: true
      heading_level: 3

## Introspection

::: remote_store.aio.AsyncBackend.resolve
    options:
      show_root_heading: true
      heading_level: 3

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.

::: remote_store.aio.AsyncBackend.unwrap
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.native_path
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncBackend.to_key
    options:
      show_root_heading: true
      heading_level: 3

## See also

- [Backend](../backend.md) — synchronous counterpart
- [AsyncStore](store.md) — the async Store that drives an `AsyncBackend`
- [Adapters](adapters.md) — bridge sync ↔ async backend implementations
- [Async Store Guide](../../../guides/async.md) — usage patterns and FastAPI integration
