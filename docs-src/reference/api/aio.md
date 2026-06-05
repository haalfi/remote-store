# Async API

<!-- Capability admonition placement rules (applies to this file and store.md):
     - Section-level (capability applies to ALL methods in the section):
       place the admonition directly after the section heading, before the first ::: directive.
     - Method-level (capability applies to ONE method only):
       place the admonition after that method's ::: directive block (end of method section).
-->

The `remote_store.aio` module provides native `async`/`await` support
for store operations. See [Store](store.md) for the synchronous
counterpart.

---

## AsyncStore

::: remote_store.aio.AsyncStore
    options:
      members: false

!!! info "Async counterpart to `Store`"
    Same methods, same errors, same capability model.  See the
    [Async Store Guide](../../guides/async.md) for usage patterns and
    [Store](store.md) for the synchronous counterpart.

!!! info "Thread safety"
    `AsyncStore` is immutable after construction and can be shared across
    tasks on the same event loop.  Backend thread safety depends on the
    backend implementation.

### Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.aio.AsyncStore.read
    options:
      show_root_heading: true
      heading_level: 4

!!! info "Quality flag: `Capability.LAZY_READ`"
    When declared, data is fetched lazily — partial reads avoid loading the whole
    file. Without it, the backend may buffer content before returning the stream.

::: remote_store.aio.AsyncStore.read_bytes
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.read_text
    options:
      show_root_heading: true
      heading_level: 4

### Writing

!!! note "Requires `Capability.WRITE`"
    `write()` and `write_text()` raise `CapabilityNotSupported` on backends that
    do not declare this capability. Most backends declare it.
    `write_atomic()` additionally requires `Capability.ATOMIC_WRITE`.

!!! info "Quality flag: `Capability.WRITE_RESULT_NATIVE`"
    When declared, the returned `WriteResult` fields (`etag`, `version_id`,
    `last_modified`, `digest`) are populated from the backend's write response.
    Without it, only locally computable fields are set.

::: remote_store.aio.AsyncStore.write
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncStore.write_text
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.aio.AsyncStore.write_atomic
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

::: remote_store.aio.AsyncStore.delete
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.delete_folder
    options:
      show_root_heading: true
      heading_level: 4

### Listing and Iteration

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.aio.AsyncStore.list_files
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncStore.list_folders
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.aio.AsyncStore.iter_children
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.glob
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.GLOB`"
    `glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.
    Check `store.supports(Capability.GLOB)` before calling.

!!! info "Ordering and laziness"
    **Ordering is backend-defined** and may vary between backends (e.g.
    lexicographic on S3, OS-dependent on local filesystems). Callers must
    not depend on any particular order.

    **Results are yielded lazily.** Backends may use pagination internally.
    Memory usage stays bounded for large directories.

### File Operations

!!! note "Requires `Capability.MOVE` / `Capability.COPY`"
    `move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`.
    Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

::: remote_store.aio.AsyncStore.move
    options:
      show_root_heading: true
      heading_level: 4

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
      heading_level: 4

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Metadata preservation"
    Metadata preservation is backend-dependent. S3 copies metadata;
    local preserves metadata (`copy2`); SFTP does not (stream copy).

### Metadata

!!! note "Partially requires `Capability.METADATA`"
    `head()` and `get_file_info()` require `Capability.METADATA`.
    `get_folder_info()` requires `Capability.METADATA` without `max_depth`,
    or `Capability.LIST` when `max_depth` is set.
    `exists()`, `is_file()`, and `is_folder()` are always available.

::: remote_store.aio.AsyncStore.head
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncStore.exists
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.is_file
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.is_folder
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.get_file_info
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.aio.AsyncStore.get_folder_info
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Capability depends on `max_depth`"
    Without `max_depth`: requires `Capability.METADATA`.
    With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

### Introspection

::: remote_store.aio.AsyncStore.resolve
    options:
      show_root_heading: true
      heading_level: 4

!!! info
    `resolve()` is a pure introspection method — it performs no I/O and is
    never called implicitly by other Store methods. The returned
    [`ResolutionPlan`](models.md) describes how a key maps to its storage
    location.

### Lifecycle

::: remote_store.aio.AsyncStore.ping
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.aclose
    options:
      show_root_heading: true
      heading_level: 4

::: remote_store.aio.AsyncStore.child
    options:
      show_root_heading: true
      heading_level: 4

### Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, see
    [Store](store.md) or the [Async Store Guide](../../guides/async.md).

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

::: remote_store.aio.AsyncBackend.glob
    options:
      show_root_heading: true
      heading_level: 4

!!! note "Requires `Capability.GLOB`"
    `glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.

### Metadata

!!! note "Requires `Capability.METADATA`"
    `get_file_info()` requires `Capability.METADATA`.
    `get_folder_info()` requires `Capability.METADATA` without `max_depth`,
    or `Capability.LIST` when `max_depth` is set.

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

!!! note "Capability depends on `max_depth`"
    Without `max_depth`: requires `Capability.METADATA`.
    With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

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

Wraps any synchronous `Backend` as an `AsyncBackend` by dispatching each
blocking call to the default executor via `asyncio.to_thread`.  `AsyncStore`
auto-wraps sync backends on construction; explicit construction is only
required when you want to introspect the adapter.

::: remote_store.aio.SyncBackendAdapter
    options:
      show_bases: false

---

## AsyncBackendSyncAdapter

Wraps any `AsyncBackend` as a synchronous `Backend` by running a private
event loop on a dedicated daemon thread for the adapter's lifetime.  See
[Async-sync bridges](../../guides/async-sync-bridges.md) for the full
behaviour contract and the [async-to-sync adapter decision record](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0025-async-to-sync-backend-adapter.md)
for the design rationale.

::: remote_store.AsyncBackendSyncAdapter
    options:
      show_bases: false

---

## AsyncMemoryBackend

In-memory async backend using a tree-indexed data structure.  Zero
dependencies, no filesystem access, no network.  Designed as a drop-in
async backend for unit testing, interactive exploration, and documentation
examples.  Supports all capabilities except `GLOB`.

::: remote_store.aio.AsyncMemoryBackend
    options:
      show_bases: false

---

## AsyncAzureBackend

Native async Azure Storage backend.  Uses the async Blob SDK for non-HNS
accounts (plain Blob Storage, Azurite) and the async DataLake SDK for HNS
accounts (ADLS Gen2) to get atomic rename and real directory support.

::: remote_store.aio.AsyncAzureBackend
    options:
      show_bases: false

---

## GraphBackend

Native async Microsoft Graph backend over OneDrive, SharePoint document
libraries, and Teams files.  A single instance targets one drive
(`drive_id`); transport is `httpx` and auth is a token-provider callable
(the built-in `GraphAuth` helper, or any user-supplied callable).  Requires
the `graph` extra.  See the [Graph setup guide](../../guides/backends/graph-setup.md)
for provisioning credentials and resolving a `drive_id`.

::: remote_store.aio.GraphBackend
    options:
      members: false
      show_bases: false

---

## GraphAuth

MSAL-backed token provider for `GraphBackend`.  Wraps the client-credentials
(app-only) and device-code (interactive) flows and exposes the bearer token
through the token-provider protocol — a `GraphAuth` instance is itself a
`Callable[[], str]`.

::: remote_store.aio.GraphAuth
    options:
      show_bases: false

---

## GraphUtils

Namespace helpers for Graph configuration.  `resolve_drive_id` turns "my
OneDrive" (`"me"`), a SharePoint site URL, or a Teams channel mapping into the
opaque `drive_id` the backend requires.

::: remote_store.aio.GraphUtils.resolve_drive_id
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.GraphUtils.aresolve_drive_id
    options:
      show_root_heading: true
      heading_level: 3

---

## AsyncWritableContent

::: remote_store.aio.AsyncWritableContent

---

## See also

- [Async Store Guide](../../guides/async.md) — usage patterns, streaming, FastAPI integration
- [Example: Async Store](../../../examples/advanced/async_store.py) — runnable demo script
- [Store](store.md) — synchronous counterpart
- [Concurrency](../../explanation/concurrency.md) — thread safety and atomicity semantics
- [aio.ext.write](extensions/aio-write.md) — async write helpers with client-side hashing
- [Write Integrity guide](../../guides/write-integrity.md) — hashing workflows for sync and async
