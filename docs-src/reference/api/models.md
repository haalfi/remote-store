# Models

::: remote_store.RemotePath

::: remote_store.PathEntry

::: remote_store.ContentDigest

::: remote_store.FileInfo

!!! note "Backend-conditional fields"
    `etag` varies by backend — whether it is populated and what it means
    depends on the backend. `metadata` requires `Capability.USER_METADATA`
    and is only present when metadata was stored with the file. `extra`
    contains backend-specific key/value pairs whose keys depend on the
    backend implementation.

::: remote_store.WriteResult

!!! note "Backend-conditional fields"
    Only `path` and `size` are guaranteed to be populated on every write.
    All other fields depend on the `source` discriminator:

    - `source="native"` — rich fields populated; requires `Capability.WRITE_RESULT_NATIVE`.
    - `source="basic"` — only `path` and `size` are reliable.
    - `source="sidecar"` — fields sourced from a `get_file_info()` enrichment call.

    Always check `source` before reading any optional field.

::: remote_store.FolderEntry

::: remote_store.FolderInfo

!!! note "Backend-conditional fields"
    `extra` contains backend-specific metadata. `modified_at` is `None` on
    backends that do not track folder modification times.

::: remote_store.ResolutionPlan

!!! note "Backend-conditional field: `details`"
    The `details` mapping contains backend-specific context. Keys and values
    depend on the backend implementation.

## See also

- [Getting Started](../../tutorial/getting-started.md) — using FileInfo and metadata in Store operations
- [File Operations example](../../tutorial/examples/file-operations.md) — reading, writing, and inspecting files
- [Store.resolve()](store.md#introspection) — returns a ResolutionPlan for key introspection
