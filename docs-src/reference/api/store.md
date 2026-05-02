# Store

<!-- Capability admonition placement rules (applies to this file and aio.md):
     - Section-level (capability applies to ALL methods in the section):
       place the admonition directly after the section heading, before the first ::: directive.
     - Method-level (capability applies to ONE method only):
       place the admonition after that method's ::: directive block (end of method section).
-->

::: remote_store.Store
    options:
      members: false

!!! info "Root path creation"
    The root path does not need to exist before constructing the store.
    `write()` creates intermediate folders implicitly on all backends:

    ```python
    store = Store(backend, root_path="brand-new-folder")
    store.write("hello.txt", b"works")  # folder created automatically
    ```

!!! info "Thread safety"
    `Store` is immutable after construction and can be shared across threads.
    Backend thread safety depends on the backend implementation.

---

## Reading

!!! note "Requires `Capability.READ`"
    All read methods raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.

::: remote_store.Store.read
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Quality flag: `Capability.LAZY_READ`"
    When declared, data is fetched lazily — partial reads avoid loading the whole
    file. Without it, the backend may buffer content before returning the stream.

::: remote_store.Store.read_bytes
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.read_seekable
    options:
      show_root_heading: true
      heading_level: 3

!!! info "Quality flag: `Capability.SEEKABLE_READ`"
    When declared, the stream is natively seekable. Without it, the Store falls
    back to a `SpooledTemporaryFile` (RAM-first, spilling to disk beyond the
    threshold). Backends may provide a more efficient implementation — for
    example, Azure issues HTTP Range requests instead of spooling.

::: remote_store.Store.read_text
    options:
      show_root_heading: true
      heading_level: 3

---

## Writing

!!! note "Requires `Capability.WRITE`"
    `write()` and `write_text()` raise `CapabilityNotSupported` on backends that do not
    declare this capability. Most backends declare it.
    `write_atomic()` and `open_atomic()` additionally require `Capability.ATOMIC_WRITE`.

!!! info "Quality flag: `Capability.WRITE_RESULT_NATIVE`"
    When declared, the returned `WriteResult` fields (`etag`, `version_id`,
    `last_modified`, `digest`) are populated from the backend's write response.
    Without it, only locally computable fields are set.

::: remote_store.Store.write
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.Store.write_text
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

::: remote_store.Store.write_atomic
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! note "Backend-conditional argument: `metadata=`"
    Passing `metadata` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

!!! info
    Most backends implement this as temp-file + rename. See the
    [Backend Behavior Matrix](#backend-behavior-matrix) for details.

::: remote_store.Store.open_atomic
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

!!! note "Requires `Capability.LIST`"
    All listing methods raise `CapabilityNotSupported` on backends that do not
    declare this capability.

::: remote_store.Store.list_files
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.Store.list_folders
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Backend-conditional argument: `max_depth=`"
    Backends with native depth limiting prune traversal early. Backends that do not
    support it still return correct results — the Store applies client-side filtering
    as a safety net.

::: remote_store.Store.iter_children
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.Store.glob
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

---

## File Operations

!!! note "Requires `Capability.MOVE` / `Capability.COPY`"
    `move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`.
    Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

::: remote_store.Store.move
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

::: remote_store.Store.copy
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.COPY`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

!!! info "Metadata preservation"
    Metadata preservation is backend-dependent. S3 copies metadata;
    local preserves metadata (`copy2`); SFTP does not (stream copy).

---

## Metadata

!!! note "Partially requires `Capability.METADATA`"
    `head()` and `get_file_info()` require `Capability.METADATA`.
    `get_folder_info()` requires `Capability.METADATA` without `max_depth`,
    or `Capability.LIST` when `max_depth` is set.
    `exists()`, `is_file()`, and `is_folder()` are always available.

::: remote_store.Store.head
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

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

!!! note "Requires `Capability.METADATA`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.Store.get_folder_info
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

---

## Introspection

::: remote_store.Store.resolve
    options:
      show_root_heading: true
      heading_level: 3

!!! info
    `resolve()` is a pure introspection method — it performs no I/O and is
    never called implicitly by other Store methods. The returned
    [`ResolutionPlan`](models.md) describes how a key maps to its storage
    location.

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

!!! info
    `supports()` itself is portable — it works on all backends. Only the
    capability-gated methods it guards are backend-specific.

---

## Backend Behavior Matrix

How key operations behave across backends. Verify against actual code before
relying on these in production.

| Behavior | [Local](../../guides/backends/local.md) | [S3](../../guides/backends/s3.md) | [S3-PyArrow](../../guides/backends/s3-pyarrow.md) | [SFTP](../../guides/backends/sftp.md) | [Azure](../../guides/backends/azure.md) | [Memory](../../guides/backends/memory.md) | [HTTP](../../guides/backends/http.md) | [SQLBlob](../../guides/backends/sql-blob.md) | [SQLQuery](../../guides/backends/sql-query.md) |
|----------|-------|----|------------|------|-------|--------|------|---------|-----------|
| `move()` atomicity | Atomic (same FS) | Copy+delete | Copy+delete | Server-dependent | Copy+delete | Atomic | — | Atomic (SQL transaction) | — |
| `copy()` preserves metadata | Yes (`copy2`) | Yes | Yes | — | Yes | — | — | Yes | — |
| `write_atomic()` mechanism | temp+rename | Direct PUT (atomic) | Direct PUT (atomic) | temp+rename | Direct PUT or temp+rename | Direct (atomic) | — | Direct (atomic) | — |
| Native `glob()` | Yes | Yes | Yes | — | Yes | — | — | Yes (SQL GLOB/LIKE) | Yes (in-memory) |
| `list_files()` ordering | OS-dependent | Lexicographic | Lexicographic | OS-dependent | Lexicographic | Insertion order | — | DB-dependent | Lexicographic |

## See also

- [Getting Started](../../tutorial/getting-started.md) — step-by-step guide to reading and writing files
- [Concurrency](../../explanation/concurrency.md) — thread safety, atomic writes, and move semantics
- [Quickstart example](../../tutorial/examples/quickstart.md) — minimal config, write, and read
