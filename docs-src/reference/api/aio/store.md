# AsyncStore

<!-- Capability admonition placement rules (applies to this file and ../store.md):
     - Section-level (capability applies to ALL methods in the section):
       place the admonition directly after the section heading, before the first ::: directive.
     - Method-level (capability applies to ONE method only):
       place the admonition after that method's ::: directive block (end of method section).
-->

`AsyncStore` is the async counterpart of [`Store`](../store.md): the same
methods, the same errors, the same capability model, exposed as coroutines.
It lives in `remote_store.aio`.

::: remote_store.aio.AsyncStore
    options:
      members: false

!!! info "Async counterpart to `Store`"
    Same methods, same errors, same capability model. See the
    [Async Store Guide](../../../guides/async.md) for usage patterns and
    [Store](../store.md) for the synchronous counterpart.

!!! info "Thread safety"
    `AsyncStore` is immutable after construction and can be shared across
    tasks on the same event loop. Backend thread safety depends on the
    backend implementation.

## Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.aio.AsyncStore.read
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Quality flag: `Capability.LAZY_READ`"
    When declared, data is fetched lazily — partial reads avoid loading the whole
    file. Without it, the backend may buffer content before returning the stream.

::: remote_store.aio.AsyncStore.read_bytes
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.read_text
    options:
      show_root_heading: true
      heading_level: 3

## Writing

!!! note "Requires `Capability.WRITE`"
    `write()` and `write_text()` raise `CapabilityNotSupported` on backends that
    do not declare this capability. Most backends declare it.
    `write_atomic()` additionally requires `Capability.ATOMIC_WRITE`.

!!! info "Quality flag: `Capability.WRITE_RESULT_NATIVE`"
    When declared, the returned `WriteResult` rich fields (`etag`, `version_id`,
    `last_modified`, `digest`) are populated from the backend's write response —
    each only when that response carries it. SFTP, for instance, declares the
    flag but returns `last_modified=None` (its write response has no timestamp;
    call `get_file_info()` for the mtime). Without the flag, only locally
    computable fields are set.

::: remote_store.aio.AsyncStore.write
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncStore.write_text
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncStore.write_atomic
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

::: remote_store.aio.AsyncStore.delete
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.delete_folder
    options:
      show_root_heading: true
      heading_level: 3

## Listing and Iteration

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncStore.list_files
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncStore.list_folders
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncStore.iter_children
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.glob
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.GLOB`"
    `glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.
    Check `store.supports(Capability.GLOB)` before calling.

!!! info "Ordering and laziness"
    **Ordering is backend-defined** and may vary between backends (e.g.
    lexicographic on S3, OS-dependent on local filesystems). Callers must
    not depend on any particular order.

    **Results are yielded lazily.** Backends may use pagination internally.
    Memory usage stays bounded for large directories.

## File Operations

!!! note "Requires `Capability.MOVE` / `Capability.COPY`"
    `move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`.
    Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

::: remote_store.aio.AsyncStore.move
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.MOVE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Atomicity"
    Atomicity is backend-dependent. Local uses `os.replace` (atomic on same
    filesystem). S3 and Azure use copy-then-delete (not atomic). SFTP
    atomicity depends on the server.
    Check `store.supports(Capability.ATOMIC_MOVE)` to query this at runtime.

::: remote_store.aio.AsyncStore.copy
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Metadata preservation"
    Metadata preservation is backend-dependent. S3 copies metadata;
    local preserves metadata (`copy2`); SFTP does not (stream copy).

## Metadata

!!! note "Partially requires `Capability.METADATA`"
    `head()` and `get_file_info()` require `Capability.METADATA`.
    `get_folder_info()` requires `Capability.METADATA` without `max_depth`,
    or `Capability.LIST` when `max_depth` is set.
    `exists()`, `is_file()`, and `is_folder()` are always available.

::: remote_store.aio.AsyncStore.head
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncStore.exists
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.is_file
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.is_folder
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.get_file_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncStore.get_folder_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Capability depends on `max_depth`"
    Without `max_depth`: requires `Capability.METADATA`.
    With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

## Introspection

::: remote_store.aio.AsyncStore.resolve
    options:
      show_root_heading: true
      heading_level: 3

!!! info
    `resolve()` is a pure introspection method — it performs no I/O and is
    never called implicitly by other Store methods. The returned
    [`ResolutionPlan`](../models.md) describes how a key maps to its storage
    location.

## Lifecycle

::: remote_store.aio.AsyncStore.ping
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.aclose
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.child
    options:
      show_root_heading: true
      heading_level: 3

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, see
    [Store](../store.md) or the [Async Store Guide](../../../guides/async.md).

::: remote_store.aio.AsyncStore.unwrap
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.native_path
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.to_key
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.AsyncStore.supports
    options:
      show_root_heading: true
      heading_level: 3

!!! info
    `supports()` itself is portable — it works on all backends. Only the
    capability-gated methods it guards are backend-specific.

## See also

- [Async Store Guide](../../../guides/async.md) — usage patterns, streaming, FastAPI integration
- [Example: Async Store](../../../../examples/advanced/async_store.py) — runnable demo script
- [Store](../store.md) — synchronous counterpart
- [AsyncBackend](backend.md) — the backend protocol `AsyncStore` drives
- [Concurrency](../../../explanation/concurrency.md) — thread safety and atomicity semantics
