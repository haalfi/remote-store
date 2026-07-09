# ReadOnlyHttpBackend

API reference for `ReadOnlyHttpBackend` — read-only access to files over HTTP/HTTPS. Supports `READ`, `METADATA`, and `LAZY_READ` capabilities only (`read()` streams lazily; write, delete, list, move, and copy are unsupported).

## ReadOnlyHttpBackend

```
ReadOnlyHttpBackend(
    base_url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    retry: RetryPolicy | None = None,
    http_client: str | None = None,
    verify_ssl: bool = True,
    max_redirects: int = 5,
)
```

Read-only backend for HTTP/HTTPS URLs.

Treats an HTTP endpoint as a file store with `{READ, METADATA, LAZY_READ}` capabilities (`read()` streams the response body lazily rather than buffering the whole file). Write, delete, list, move, and copy operations raise `CapabilityNotSupported`.

Parameters:

- **`base_url`** (`str`) – Root URL. A trailing / is appended if missing.
- **`headers`** (`dict[str, str] | None`, default: `None` ) – Custom headers sent with every request (e.g. API keys).
- **`timeout`** (`float`, default: `30.0` ) – Request timeout in seconds.
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Retry policy for transient errors.
- **`http_client`** (`str | None`, default: `None` ) – Force a specific transport ("urllib", "requests", or "httpx"). Auto-detected if None.
- **`verify_ssl`** (`bool`, default: `True` ) – Whether to verify TLS certificates.
- **`max_redirects`** (`int`, default: `5` ) – Maximum number of redirects to follow.

### exists

```
exists(path: str) -> bool
```

Check existence via HEAD request (falls back to ranged GET).

### is_file

```
is_file(path: str) -> bool
```

HTTP resources are always files.

### is_folder

```
is_folder(path: str) -> bool
```

HTTP has no folder concept — always returns False.

### read

```
read(path: str) -> BinaryIO
```

Stream-read a file via GET.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Buffered-read a file via GET.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Get file metadata via HEAD request (falls back to ranged GET).

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

HTTP has no folder concept — always raises NotFound.

### check_health

```
check_health() -> None
```

Verify connectivity by sending HEAD to base_url (or GET if HEAD is blocked).

Note

The health check probes `base_url` (the root), not a specific file. Many HTTP servers and CDNs return 403 or 404 for directory URLs while serving individual files normally. A failing health check therefore does not necessarily mean `read()` or `exists()` will fail on actual file paths.

### close

```
close() -> None
```

Close the underlying transport.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the transport if it matches the requested type.

### native_path

```
native_path(path: str) -> str
```

Return the full URL for a backend-relative key.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with HTTP-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="http" and details containing
- `ResolutionPlan` – url and method.

### to_key

```
to_key(native_path: str) -> str
```

Strip base_url prefix to get a backend-relative key.

## Interop (Backend-Specific)

Backend-specific methods

`unwrap`, `native_path`, and `to_key` expose backend internals. Using them ties your code to `ReadOnlyHttpBackend`. For portable alternatives, use the methods from [Backend](https://docs.remotestore.dev/stable/reference/api/backend/index.md).

## See also

- [HTTP Backend Guide](https://docs.remotestore.dev/stable/guides/backends/http/index.md) — usage patterns, configuration, and examples
- [HTTP Backend example](https://docs.remotestore.dev/stable/tutorial/examples/http-backend/index.md) — read-only HTTP access in action
