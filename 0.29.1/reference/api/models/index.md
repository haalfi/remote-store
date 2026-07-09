# Models

## RemotePath

```
RemotePath(raw: str)
```

An immutable, normalized path within a remote store.

Parameters:

- **`raw`** (`str`) – The raw path string to normalize and validate.

Raises:

- `InvalidPath` – If the path is malformed or unsafe.

### name

```
name: str
```

Final component of the path.

### parent

```
parent: RemotePath | None
```

Parent path, or `None` if the path has only one component.

Example: `RemotePath("a/b").parent` returns `RemotePath("a")`, but `RemotePath("a").parent` returns `None`.

### parts

```
parts: tuple[str, ...]
```

Tuple of path components.

### suffix

```
suffix: str
```

File extension including the dot, or empty string.

### as_posix

```
as_posix() -> str
```

Return the path as a forward-slash string.

Mirrors `pathlib.PurePath.as_posix`. The path is always stored with forward slashes, so the result is identical to `str(self)` on every platform. `RemotePath.ROOT.as_posix()` returns `"."`.

### from_backend_path

```
from_backend_path(path: str) -> RemotePath
```

Create a RemotePath, using ROOT for empty paths.

Backends use this in `get_folder_info` to avoid duplicating the `RemotePath(path) if path else RemotePath.ROOT` pattern.

## PathEntry

Bases: `Protocol`

Shared interface for listing results -- every entry has a name and path.

### name

```
name: str
```

Entry name (final path component).

### path

```
path: RemotePath
```

Normalized remote path.

## ContentDigest

```
ContentDigest(algorithm: str, value: str)
```

Verified content digest with known algorithm.

Both `algorithm` and `value` are normalized to lowercase on construction.

Attributes:

- **`algorithm`** (`str`) – Hash algorithm name, always lowercase (e.g., "sha256").
- **`value`** (`str`) – Lowercase hex-encoded digest, no prefix, no separators.

## FileInfo

```
FileInfo(
    path: RemotePath,
    name: str,
    size: int,
    modified_at: datetime,
    digest: ContentDigest | None = None,
    etag: str | None = None,
    content_type: str | None = None,
    metadata: Mapping[str, str] | None = None,
    extra: dict[str, object] = dict(),
)
```

Immutable snapshot of file metadata.

Satisfies the `PathEntry` protocol.

Attributes:

- **`path`** (`RemotePath`) – Normalized remote path.
- **`name`** (`str`) – File name (final path component).
- **`size`** (`int`) – File size in bytes.
- **`modified_at`** (`datetime`) – Last modification time.
- **`digest`** (`ContentDigest | None`) – Verified content digest with known algorithm.
- **`etag`** (`str | None`) – Opaque backend-provided tag for change detection.
- **`content_type`** (`str | None`) – Optional MIME type.
- **`metadata`** (`Mapping[str, str] | None`) – User-supplied key/value metadata echoed from the backend.
- **`extra`** (`dict[str, object]`) – Backend-specific metadata.

Backend-conditional fields

`etag` varies by backend — whether it is populated and what it means depends on the backend. `metadata` requires `Capability.USER_METADATA` and is only present when metadata was stored with the file. `extra` contains backend-specific key/value pairs whose keys depend on the backend implementation.

## WriteResult

```
WriteResult(
    path: RemotePath,
    size: int,
    source: Literal["native", "basic", "sidecar"] = "basic",
    digest: ContentDigest | None = None,
    etag: str | None = None,
    version_id: str | None = None,
    last_modified: datetime | None = None,
    metadata: Mapping[str, str] | None = None,
)
```

Immutable snapshot of a completed write operation.

Returned by `Store.write()`, `Store.write_text()`, and `Store.write_atomic()`.

Attributes:

- **`path`** (`RemotePath`) – Normalized written path, store-relative.
- **`size`** (`int`) – Bytes written.
- **`source`** (`Literal['native', 'basic', 'sidecar']`) – Provenance of the optional fields. "native" — the backend populated them from its write response; trust digest, etag, and last_modified. "basic" — only path and size are reliable; call Store.head() or use ext.write helpers if you need more. "sidecar" — constructed by Store.head() from a subsequent get_file_info() call.
- **`digest`** (`ContentDigest | None`) – Content digest from the write — either a client-computed hash from ext.write helpers, or a hash echoed by the backend from its write response (e.g., Azure echoes the client-supplied MD5 as ContentDigest("md5", …)). None when neither source applies.
- **`etag`** (`str | None`) – Opaque backend change tag; semantics vary by backend.
- **`version_id`** (`str | None`) – Immutable backend version identifier; None when the backend does not version objects.
- **`last_modified`** (`datetime | None`) – Server timestamp from the write response; None when the backend's write response omits it.
- **`metadata`** (`Mapping[str, str] | None`) – Echo of user metadata stored with the object.

Backend-conditional fields

Only `path` and `size` are guaranteed to be populated on every write. All other fields depend on the `source` discriminator:

- `source="native"` — rich fields populated; requires `Capability.WRITE_RESULT_NATIVE`.
- `source="basic"` — only `path` and `size` are reliable.
- `source="sidecar"` — fields sourced from a `get_file_info()` enrichment call.

Always check `source` before reading any optional field.

## FolderEntry

```
FolderEntry(path: RemotePath, name: str)
```

Immutable folder identity returned by listing operations.

Satisfies the `PathEntry` protocol.

Attributes:

- **`path`** (`RemotePath`) – Normalized remote path.
- **`name`** (`str`) – Folder name (final path component).

## FolderInfo

```
FolderInfo(
    path: RemotePath,
    file_count: int,
    total_size: int,
    modified_at: datetime | None = None,
    extra: dict[str, object] = dict(),
)
```

Aggregated folder metadata.

Satisfies the `PathEntry` protocol.

Attributes:

- **`path`** (`RemotePath`) – Normalized remote path.
- **`file_count`** (`int`) – Number of files in the folder.
- **`total_size`** (`int`) – Total size of all files in bytes.
- **`modified_at`** (`datetime | None`) – Optional last modification time.
- **`extra`** (`dict[str, object]`) – Backend-specific metadata.

### name

```
name: str
```

Folder name (final path component).

Unlike `FileInfo` and `FolderEntry`, which store `name` as a constructor field, this is a derived property (`self.path.name`) to avoid redundancy and keep `name` in sync with `path`.

Backend-conditional fields

`extra` contains backend-specific metadata. `modified_at` is `None` on backends that do not track folder modification times.

## ResolutionPlan

```
ResolutionPlan(
    kind: str,
    backend: str,
    key: str,
    native_path: str,
    details: dict[str, Any],
)
```

Describes how a key maps to its storage location.

Returned by `Backend.resolve()` and `Store.resolve()`. The plan captures the resolution strategy, backend identity, resolved key, native path, and backend-specific context -- all without performing any I/O.

`details` is wrapped in `types.MappingProxyType` via `__post_init__` to prevent accidental mutation at runtime.

Parameters:

- **`kind`** (`str`) – Resolution strategy identifier (e.g. "local", "s3", "azure").
- **`backend`** (`str`) – Human-readable backend identifier (typically Backend.name).
- **`key`** (`str`) – The resolved key (store-relative after Store.resolve(), backend-relative after Backend.resolve()).
- **`native_path`** (`str`) – Backend-native location string (same as Backend.native_path() output).
- **`details`** (`dict[str, Any]`) – Backend-specific resolution context. Immutable at runtime. Values should be JSON-serializable primitives.

Backend-conditional field: `details`

The `details` mapping contains backend-specific context. Keys and values depend on the backend implementation.

## See also

- [Getting Started](https://docs.remotestore.dev/stable/tutorial/getting-started/index.md) — using FileInfo and metadata in Store operations
- [File Operations example](https://docs.remotestore.dev/stable/tutorial/examples/file-operations/index.md) — reading, writing, and inspecting files
- [Store.resolve()](https://docs.remotestore.dev/stable/reference/api/store/#introspection) — returns a ResolutionPlan for key introspection
