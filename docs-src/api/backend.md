# Backend

::: remote_store.Backend
    options:
      members: false

!!! info "Implementing a backend"
    Subclass `Backend` and implement all abstract methods. Map every
    backend-native exception to a `remote_store` error — native exceptions
    must never leak to callers.

---

## Identity

::: remote_store.Backend.name
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.capabilities
    options:
      show_root_heading: true
      heading_level: 3

---

## Checking Existence

::: remote_store.Backend.exists
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.is_file
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.is_folder
    options:
      show_root_heading: true
      heading_level: 3

---

## Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.Backend.read
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.read_bytes
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.read_seekable
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Default implementation"
    The default spools the stream into a `SpooledTemporaryFile` (up to 8 MB
    in RAM, beyond that on disk) when the backend stream is not already
    seekable. Override for efficiency when the backend supports range reads.

---

## Writing

!!! note "Requires `Capability.WRITE`"
    `write()` raises `CapabilityNotSupported` on backends that do not declare
    this capability. Most backends declare it.

::: remote_store.Backend.write
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.Backend.write_atomic
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.Backend.open_atomic
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

---

## Deleting

!!! note "Requires `Capability.DELETE`"
    All delete methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.Backend.delete
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.delete_folder
    options:
      show_root_heading: true
      heading_level: 3

---

## Listing and Iteration

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.Backend.list_files
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.Backend.list_folders
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.iter_children
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Default implementation"
    Chains `list_files()` then `list_folders()`. Override when the backend
    can fetch both in a single I/O call.

::: remote_store.Backend.glob
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.GLOB`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Non-abstract"
    The default raises `CapabilityNotSupported`. Backends that provide native
    glob support override this and declare `Capability.GLOB`.

---

## Metadata

::: remote_store.Backend.get_file_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.Backend.get_folder_info
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

---

## File Operations

::: remote_store.Backend.move
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.MOVE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.Backend.copy
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

---

## Introspection

::: remote_store.Backend.resolve
    options:
      show_root_heading: true
      heading_level: 3

---

## Lifecycle

::: remote_store.Backend.check_health
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.close
    options:
      show_root_heading: true
      heading_level: 3

---

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.

::: remote_store.Backend.unwrap
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.native_path
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.to_key
    options:
      show_root_heading: true
      heading_level: 3

**Related types:** [`CapabilitySet`](capabilities.md),
[`FileInfo`](models.md), [`FolderInfo`](models.md),
[`FolderEntry`](models.md), [`ResolutionPlan`](models.md).

## See also

- [Build Your Own Backend](../how-to/custom-backend-guide.md) — step-by-step guide to implementing a custom backend
- [Capabilities Matrix](../reference/capabilities-matrix.md) — per-backend capability comparison
- [Errors](errors.md) — error types backends must raise
