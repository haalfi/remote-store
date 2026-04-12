# Backend

::: remote_store.Backend
    options:
      members: false

!!! note "Implementing a backend"
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

!!! note "Default implementation"
    The default spools the stream into a `SpooledTemporaryFile` (up to 8 MB
    in RAM, beyond that on disk) when the backend stream is not already
    seekable. Override for efficiency when the backend supports range reads.

---

## Writing

::: remote_store.Backend.write
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.write_atomic
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.open_atomic
    options:
      show_root_heading: true
      heading_level: 3

---

## Deleting

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

::: remote_store.Backend.list_files
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.list_folders
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.iter_children
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Default implementation"
    Chains `list_files()` then `list_folders()`. Override when the backend
    can fetch both in a single I/O call.

::: remote_store.Backend.glob
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Non-abstract"
    The default raises `CapabilityNotSupported`. Backends that provide native
    glob support override this and declare `Capability.GLOB`.

---

## Metadata

::: remote_store.Backend.get_file_info
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.get_folder_info
    options:
      show_root_heading: true
      heading_level: 3

---

## File Operations

::: remote_store.Backend.move
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.copy
    options:
      show_root_heading: true
      heading_level: 3

---

## Introspection

::: remote_store.Backend.resolve
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.to_key
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Backend.native_path
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

::: remote_store.Backend.unwrap
    options:
      show_root_heading: true
      heading_level: 3

**Related types:** [`CapabilitySet`](capabilities.md),
[`FileInfo`](models.md), [`FolderInfo`](models.md),
[`FolderEntry`](models.md), [`ResolutionPlan`](models.md).

## See also

- [Build Your Own Backend](../custom-backend-guide.md) — step-by-step guide to implementing a custom backend
- [Capabilities Matrix](../capabilities-matrix.md) — per-backend capability comparison
- [Errors](errors.md) — error types backends must raise
