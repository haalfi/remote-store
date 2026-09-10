# Capabilities

## Capability

Bases: `Enum`

Operations a backend may support.

Most values gate one or more `Store` methods; some are quality flags that inform callers about backend behaviour without gating a specific method (see `ATOMIC_MOVE`, `SEEKABLE_READ`, `LAZY_READ`). Use `Store.supports()` to query at runtime.

Values:

*Core I/O*

- `READ` -- Stream or bulk-read file content. Gates `Store.read()` and `Store.read_bytes()`.
- `WRITE` -- Create or overwrite files. Gates `Store.write()`.
- `DELETE` -- Remove files and folders. Gates `Store.delete()` and `Store.delete_folder()`.

*Navigation*

- `LIST` -- Enumerate files and subfolders. Gates `Store.list_files()` and `Store.list_folders()`.
- `GLOB` -- Native pattern matching against file paths. Gates `Store.glob()`. Not all backends support this — use `ext.glob.glob_files()` as a portable fallback.

*File operations*

- `MOVE` -- Rename or relocate a file within the same backend. Gates `Store.move()`.
- `COPY` -- Duplicate a file within the same backend. Gates `Store.copy()`.

*Atomic variants*

- `ATOMIC_WRITE` -- Write via temp-file-and-rename so readers never see partial content. Gates `Store.write_atomic()` and `Store.open_atomic()`.
- `ATOMIC_MOVE` -- Quality flag: `move()` is guaranteed atomic under concurrent access (e.g. Local via `os.rename`, Memory under lock, SQL in a transaction). Does **not** gate a method — call `store.supports(Capability.ATOMIC_MOVE)` before relying on atomic rename semantics. Backends that implement move as copy-then-delete (e.g. S3, Azure non-HNS) do not declare this capability.

*Metadata*

- `METADATA` -- Retrieve file or folder metadata. Gates `Store.get_file_info()` and `Store.get_folder_info()`.
- `USER_METADATA` -- Store user-supplied key/value pairs alongside a file. Strict gate on the `metadata=` kwarg in `Store.write()`, `Store.write_text()`, and `Store.write_atomic()`: passing a non-empty mapping to a backend that does not declare this capability raises `CapabilityNotSupported` before any I/O. `metadata=None` and `metadata={}` are always allowed.

*Quality flags*

- `SEEKABLE_READ` -- `Store.read()` always returns a seekable stream (`stream.seekable()` is `True`). Backends that declare this capability return seekable streams from both `read()` and `read_seekable()` with zero overhead. Absence of the flag means only that `read()` is forward-only -- not that seekable reads are unavailable. On the sync `Store`, `read_seekable()` is gated on `READ` alone, so it is served on every backend: a backend without the flag serves it either through a native override as cheap as the passthrough (the sync Azure backend issues one ranged download per `read()`, with no temp-file spill) or through a `SpooledTemporaryFile` that copies the object first (HTTP, and any async backend bridged to sync). The async API has no `read_seekable()` -- an async-native backend that omits the flag (`AsyncAzureBackend`, `GraphBackend`) has no seekable read until bridged to sync. The flag does not distinguish the native and spooled costs; the Azure backend guide's "Streaming and seekable reads" section documents the sync Azure range reader in full.
- `LAZY_READ` -- `read()` fetches data lazily on demand from the native source rather than loading the entire file into memory before returning. Backends that pre-load the full file contents (e.g. in-memory backends, SQL blob stores) do **not** declare this flag. Callers can use `store.supports(Capability.LAZY_READ)` to know whether partial reads avoid loading the entire file.
- `WRITE_RESULT_NATIVE` -- Quality flag: the backend fills each rich field of the returned `WriteResult` (`etag`, `version_id`, `last_modified`, `digest`) directly from its write response, but only when that response carries the field — which fields are filled depends on the backend. Some native backends fill none: SFTP's write response has no metadata at all, so it returns only `path` / `size` / `source` and leaves every rich field `None` (call `get_file_info()` for the metadata). Does **not** gate any method — `Store.write*()` works on every backend. Backends without this flag return a `WriteResult` with only `path` and `size` populated (`source == "basic"`); `metadata` is governed independently by the `USER_METADATA` capability and is not subject to this flag. `store.supports(Capability.WRITE_RESULT_NATIVE)` tells you whether the rich fields *may* be populated, not that any given one is: a native backend can still leave an individual field `None` (SFTP leaves all of them). Check the specific field you need, or call `store.get_file_info()` when you must have it.

Quality flags vs. method gates

Two kinds of capabilities exist. **Method gates** (e.g. `READ`, `WRITE`, `DELETE`) guard specific Store or Backend methods — calling a gated method on a backend that does not declare the capability raises `CapabilityNotSupported`. **Quality flags** (e.g. `SEEKABLE_READ`, `WRITE_RESULT_NATIVE`) are informational only — they describe behaviour the backend provides but do not guard any method call. For example, a backend that omits `SEEKABLE_READ` is still served by the sync `Store.read_seekable()` — the flag reports only whether `read()` itself is seekable, not whether `read_seekable()` is native or spooled (the async API has no `read_seekable()`). Check the class docstring for the full categorisation.

## CapabilitySet

```
CapabilitySet(capabilities: set[Capability])
```

Immutable set of capabilities declared by a backend.

Parameters:

- **`capabilities`** (`set[Capability]`) – The set of supported capabilities.

### supports

```
supports(cap: Capability) -> bool
```

Check whether a capability is supported.

### require

```
require(cap: Capability, *, backend: str = '') -> None
```

Raise if a capability is not supported.

Raises:

- `CapabilityNotSupported` – If the capability is missing.

## See also

- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — per-backend capability comparison
- [Capabilities & Errors example](https://docs.remotestore.dev/stable/tutorial/examples/capabilities-and-errors/index.md) — checking capabilities at runtime
