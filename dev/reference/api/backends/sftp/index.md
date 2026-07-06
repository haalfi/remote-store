# SFTPBackend

API reference for `SFTPBackend` — stores files on any SSH/SFTP server using paramiko. Explicit host key verification and Azure Key Vault PEM support.

## SFTPBackend

```
SFTPBackend(
    host: str,
    *,
    port: int = 22,
    username: str | None = None,
    password: str | Secret | None = None,
    pkey: Any = None,
    base_path: str = "/",
    host_key_policy: HostKeyPolicy | str = STRICT,
    known_host_keys: str | None = None,
    host_keys_path: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: int = 10,
    connect_kwargs: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,
)
```

SFTP backend using pure paramiko.

`move()` attempts `posix_rename` (atomic on POSIX-compliant servers), then falls back to `rename`, and finally to a stream copy followed by a delete. Because atomicity cannot be guaranteed across all servers, `ATOMIC_MOVE` is not declared.

Warning

**Not thread-safe for concurrent access.** This backend maintains a single SSH/SFTP connection (paramiko `SFTPClient`), which is not safe to call from multiple threads simultaneously. Concurrent calls via `SyncBackendAdapter` and `asyncio.gather` will race on the shared socket and may hang or corrupt responses. Create one `SFTPBackend` instance per thread if you need parallel operations.

Parameters:

- **`host`** (`str`) – SFTP server hostname (required, non-empty).
- **`port`** (`int`, default: `22` ) – SSH port (default: 22).
- **`username`** (`str | None`, default: `None` ) – SSH username.
- **`password`** (`str | Secret | None`, default: `None` ) – SSH password.
- **`pkey`** (`Any`, default: `None` ) – paramiko.PKey instance for key-based auth.
- **`base_path`** (`str`, default: `'/'` ) – Root path on the remote server (default: /).
- **`host_key_policy`** (`HostKeyPolicy | str`, default: `STRICT` ) – Host key verification policy (see SFTPUtils.HostKeyPolicy). Accepts enum value or string.
- **`known_host_keys`** (`str | None`, default: `None` ) – Known hosts string (code-level override).
- **`host_keys_path`** (`str | None`, default: `None` ) – Path to known_hosts file (default: ~/.ssh/known_hosts).
- **`config`** (`dict[str, Any] | None`, default: `None` ) – Optional config dict (may contain known_host_keys).
- **`timeout`** (`int`, default: `10` ) – SSH connection timeout in seconds.
- **`connect_kwargs`** (`dict[str, Any] | None`, default: `None` ) – Extra kwargs passed to SSHClient.connect().

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with SFTP-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="sftp" and details containing
- `ResolutionPlan` – host, port, and base_path.

## See also

- [SFTP Backend Guide](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) — usage patterns, configuration, and examples
- [SFTP Backend example](https://docs.remotestore.dev/stable/tutorial/examples/sftp-backend/index.md) — SFTP backend in action
