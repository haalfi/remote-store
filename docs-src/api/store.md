# Store

!!! tip "See also"
    The [Store API Reference](store-api.md) documents behavioral guarantees,
    backend differences, and the target v1 API surface.

::: remote_store.Store
    options:
      members: false

!!! note "Thread safety"
    `Store` is immutable after construction and can be shared across threads.
    Backend thread safety depends on the backend implementation.

---

## Reading

::: remote_store.Store.read
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.read_bytes
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.read_text
    options:
      show_root_heading: true
      heading_level: 3

---

## Writing

::: remote_store.Store.write
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.write_text
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.write_atomic
    options:
      show_root_heading: true
      heading_level: 3

!!! note
    Most backends implement this as temp-file + rename. See the
    [Backend Behavior Matrix](#backend-behavior-matrix) for details.

::: remote_store.Store.open_atomic
    options:
      show_root_heading: true
      heading_level: 3

---

## Deleting

::: remote_store.Store.delete
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.delete_folder
    options:
      show_root_heading: true
      heading_level: 3

---

## Listing and Iteration

::: remote_store.Store.list_files
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.list_folders
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.iter_children
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.glob
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Ordering and laziness"
    **Ordering is backend-defined** and may vary between backends (e.g.
    lexicographic on S3, OS-dependent on local filesystems). Callers must
    not depend on any particular order.

    **Results are yielded lazily.** Backends may use pagination internally.
    Memory usage stays bounded for large directories.

---

## File Operations

::: remote_store.Store.move
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Atomicity"
    Atomicity is backend-dependent. Local uses `os.replace` (atomic on same
    filesystem). S3 and Azure use copy-then-delete (not atomic). SFTP
    atomicity depends on the server.

::: remote_store.Store.copy
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Metadata preservation"
    Metadata preservation is backend-dependent. S3 copies metadata; local
    and SFTP may not preserve modification time or content type.

---

## Metadata

::: remote_store.Store.exists
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.is_file
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.is_folder
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.get_file_info
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.get_folder_info
    options:
      show_root_heading: true
      heading_level: 3

---

## Lifecycle

::: remote_store.Store.ping
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.close
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.child
    options:
      show_root_heading: true
      heading_level: 3

---

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.

::: remote_store.Store.unwrap
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.native_path
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.to_key
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.supports
    options:
      show_root_heading: true
      heading_level: 3

!!! note
    `supports()` itself is portable -- it works on all backends. Only the
    capability-gated methods it guards are backend-specific.

---

## Backend Behavior Matrix

How key operations behave across backends. Verify against actual code before
relying on these in production.

| Behavior | Local | S3 | S3-PyArrow | SFTP | Azure | Memory |
|----------|-------|----|------------|------|-------|--------|
| `move()` atomicity | Atomic (same FS) | Copy+delete | Copy+delete | Server-dependent | Copy+delete | Atomic |
| `copy()` preserves metadata | Yes (`copy2`) | Yes | Yes | No | Yes | No |
| `write_atomic()` mechanism | temp+rename | Direct PUT (atomic) | Direct PUT (atomic) | temp+rename | Direct PUT or temp+rename | Direct (atomic) |
| Native `glob()` | Yes | Yes | Yes | No | Yes | No |
| `list_files()` ordering | OS-dependent | Lexicographic | Lexicographic | OS-dependent | Lexicographic | Insertion order |

**Related types:** `WritableContent = BinaryIO | bytes`,
[`FileInfo`](models.md), [`FolderInfo`](models.md),
[`RemotePath`](path.md), [`Capability`](capabilities.md).
