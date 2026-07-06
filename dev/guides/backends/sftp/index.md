# SFTP Backend

The SFTP backend stores files on any SSH/SFTP server using [paramiko](https://www.paramiko.org/). Unlike fsspec's `SFTPFileSystem`, it gives you explicit control over host key verification and handles Azure Key Vault PEM quirks out of the box.

## Installation

```
pip install "remote-store[sftp]"
```

This pulls in `paramiko` and `tenacity` (for automatic retry on transient SSH errors).

## Usage

```
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "my-sftp": BackendConfig(
            type="sftp",
            options={
                "host": "files.example.com",
                "username": "deploy",
                "password": "secret",
                "base_path": "/srv/data",
            },
        ),
    },
    stores={"uploads": StoreProfile(backend="my-sftp", root_path="uploads")},
)

with Registry(config) as registry:
    store = registry.get_store("uploads")
    store.write("report.csv", b"col1,col2\n1,2\n")
    data = store.read_bytes("report.csv")
```

### Key-based authentication

```
from remote_store.backends import SFTPBackend, SFTPUtils

pkey = SFTPUtils.load_private_key("/path/to/id_rsa", from_file=True)

backend = SFTPBackend(
    host="files.example.com",
    username="deploy",
    pkey=pkey,
)
```

Or load a PEM string directly (useful for secrets managers like Azure Key Vault):

```
pkey = SFTPUtils.load_private_key(pem_string)
```

## Options

| Option            | Type            | Default              | Description                                  |
| ----------------- | --------------- | -------------------- | -------------------------------------------- |
| `host`            | `str`           | *(required)*         | SFTP server hostname                         |
| `port`            | `int`           | `22`                 | SSH port                                     |
| `username`        | `str`           | `None`               | SSH username                                 |
| `password`        | `str`           | `None`               | SSH password                                 |
| `pkey`            | `paramiko.PKey` | `None`               | Private key for key-based auth               |
| `base_path`       | `str`           | `"/"`                | Root path on the remote server               |
| `host_key_policy` | `HostKeyPolicy` | `STRICT`             | Host key verification mode (see below)       |
| `known_host_keys` | `str`           | `None`               | Known-hosts string (code-level override)     |
| `host_keys_path`  | `str`           | `~/.ssh/known_hosts` | Path to known_hosts file                     |
| `config`          | `dict`          | `None`               | Config dict (may contain `known_host_keys`)  |
| `timeout`         | `int`           | `10`                 | SSH connection timeout in seconds            |
| `connect_kwargs`  | `dict`          | `None`               | Extra kwargs passed to `SSHClient.connect()` |

## Preflight host-key discovery

To populate a committed `host.keys` file without going through a TOFU connect first, use [`SFTPUtils.scan_host_keys(host, port=22)`](https://docs.remotestore.dev/stable/reference/api/sftp-utils/index.md). It opens a transport, captures the server's *negotiated* host key (no authentication), and returns a single `known_hosts`-formatted line ready to commit:

```
from pathlib import Path
from remote_store.backends import SFTPUtils

entry = SFTPUtils.scan_host_keys("sftp.example.com")
Path("host.keys").write_text(entry + "\n")
```

For non-default ports the entry uses the OpenSSH `[host]:port` form. Network failures (host unreachable, port refused, DNS error) raise `OSError`; KEX failures (legacy server offering only `ssh-rsa`) raise `paramiko.SSHException` — call `enable_ssh_rsa_compat()` first in that case.

`scan_host_keys()` returns the **negotiated** key for one handshake, not every key type the server offers. If the server publishes multiple key types and paramiko later negotiates a type other than the pinned line, the connection fails with `BadHostKeyException`. Call the helper multiple times under different `disabled_algorithms` settings if you need full-type coverage.

## Host Key Verification

The `HostKeyPolicy` enum controls how unknown host keys are handled:

| Policy               | Behaviour                                         | Use case                |
| -------------------- | ------------------------------------------------- | ----------------------- |
| `STRICT`             | Reject unknown hosts. Key must be in known_hosts. | Production (default)    |
| `TRUST_ON_FIRST_USE` | Accept and save on first connect, verify after.   | First-time server setup |
| `AUTO_ADD`           | Accept any key silently.                          | Dev / testing only      |

Known host keys are resolved in order (first match wins):

1. `known_host_keys` constructor parameter
1. `config["known_host_keys"]` dict value
1. `SFTP_KNOWN_HOST_KEYS` environment variable
1. `host_keys_path` file on disk (default: `~/.ssh/known_hosts`)

```
from remote_store.backends import SFTPBackend, SFTPUtils

# Development / testing
backend = SFTPBackend(
    host="localhost",
    port=2222,
    username="test",
    password="test",
    host_key_policy=SFTPUtils.HostKeyPolicy.AUTO_ADD,
)
```

## Legacy Servers (`ssh-rsa` / SHA-1)

**What changed.** Paramiko 5.0 removed `ssh-rsa` from its host-key defaults — empirically verified, see the [research note](https://github.com/haalfi/remote-store/blob/master/sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md) for the version matrix.

- **paramiko `< 5`** ships `ssh-rsa` in defaults at all four negotiation sites. A freshly-imported paramiko already negotiates against an `ssh-rsa`-only server out of the box.
- **paramiko `>= 5`** has `ssh-rsa` removed from all four sites. Connecting to an `ssh-rsa`-only server raises `IncompatiblePeer: Incompatible ssh peer (no acceptable host key)` during KEX, before authentication is attempted.

The `[sftp]` extra has no upper bound on paramiko, so current resolvers pick paramiko 5+ by default. New installs hit the failure unless they call the helper described below.

### Diagnose first

Before mutating paramiko's defaults, confirm the failure shape. An `IncompatiblePeer` error from paramiko wraps four distinct negotiation failures — host key, KEX, cipher, or MAC — and only the first is fixed by `enable_ssh_rsa_compat()`. The other three need `connect_kwargs={"disabled_algorithms": ...}` instead. [`SFTPUtils.scan_host_algorithms()`](https://docs.remotestore.dev/stable/reference/api/sftp-utils/#remote_store.backends.SFTPUtils.scan_host_algorithms) parses the server's `SSH_MSG_KEXINIT` advertisement (RFC 4253 § 7.1) over a raw socket — no paramiko, no authentication, so the result reflects exactly what the server advertises:

```
from remote_store.backends import SFTPUtils

info = SFTPUtils.scan_host_algorithms("legacy.example.com")
print("host-key algos:", info["server_host_key_algorithms"])
print("kex algos:     ", info["kex_algorithms"])
```

If `server_host_key_algorithms == ["ssh-rsa"]`, this guide applies and the next subsection is the fix. If it's `kex_algorithms` that's narrow (e.g. only `diffie-hellman-group14-sha1`), `enable_ssh_rsa_compat()` will not help; widen the relevant list via `SFTPBackend(connect_kwargs={"disabled_algorithms": ...})`.

### Fix: re-enable `ssh-rsa` at process startup

[`SFTPUtils.enable_ssh_rsa_compat()`](https://docs.remotestore.dev/stable/reference/api/sftp-utils/index.md) adds `ssh-rsa` to all four paramiko host-key sites in one call. It is a no-op on paramiko `< 5` (all four guards short-circuit) and the required recovery path on paramiko `>= 5`:

```
from remote_store.backends import SFTPUtils

# Call once, before any SFTPBackend connect to a legacy server.
SFTPUtils.enable_ssh_rsa_compat()
```

If you observe `IncompatiblePeer: no acceptable kex algorithm`

KEX / cipher / MAC negotiation failures are a separate problem; `enable_ssh_rsa_compat()` does not help. Widen the relevant algorithm list via the `connect_kwargs={"disabled_algorithms": ...}` SFTP constructor argument instead.

Security tradeoff

This is **process-global**: every paramiko transport in the process will then accept SHA-1 host keys. Only enable this if every server your process connects to is under your operational control, and push server operators to upgrade to `rsa-sha2-256`/`rsa-sha2-512` so the shim can be removed.

### Alternative: pin `paramiko<5`

Pinning `paramiko<5` keeps the consumer on the empirically-verified compatible range (`>= 3.0,< 5`) and avoids the helper entirely. The tradeoff is freezing on paramiko 4.x while upstream moves on:

| Approach                  | Loses                                                                              |
| ------------------------- | ---------------------------------------------------------------------------------- |
| `paramiko<5` pin          | Future paramiko 5+ improvements (perf, protocol features, CVE fixes once 4.x EOLs) |
| `enable_ssh_rsa_compat()` | Process-wide SHA-1 host-key acceptance only                                        |

Either composes cleanly with the library's `[sftp]` floor of `paramiko>=3.0`. To pin the consumer must override at their own dependency layer (e.g. `requirements.txt` line `paramiko>=3.0,<5`).

## Connection Behaviour

- **Lazy connect** — no network call happens during construction. The SSH/SFTP connection is established on the first operation.
- **Auto-reconnect** — if the connection goes stale between operations, the backend reconnects transparently.
- **Retry** — transient SSH errors (`SSHException`, `OSError`, `EOFError`) are retried up to 3 times with exponential backoff (2 s min, 10 s max).
- **Single connection, not thread-safe** — each `SFTPBackend` instance holds one paramiko `SFTPClient`. Calling it from multiple threads simultaneously (e.g. via `SyncBackendAdapter` + `asyncio.gather`) races on the shared socket. Create one `SFTPBackend` per thread for parallel workloads.

## Capabilities

The SFTP backend supports all capabilities except `GLOB` and `ATOMIC_MOVE`. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

Atomic write caveat

Atomic writes use a temp file (`.~tmp.<name>.<uuid>`) and rename. If the connection drops between write and rename, the orphan temp file will remain on the server.

Move fallback

`move()` tries `posix_rename` (atomic), then standard `rename()`, then copy + delete as a last resort. Most servers support at least `rename()`.

TOCTOU on `overwrite=False`

Like most backends, the exists-check and write are separate operations. Concurrent writers can both pass the check.

See the [Concurrency and Atomicity Guarantees](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) guide for details and workarounds.

## Escape Hatch

Access the underlying `paramiko.SFTPClient` when you need protocol-level features:

```
import paramiko

sftp_client = backend.unwrap(paramiko.SFTPClient)
sftp_client.listdir_attr("/custom/path")
```

## See also

- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)
- [SFTP utilities reference](https://docs.remotestore.dev/stable/reference/api/sftp-utils/index.md) — `scan_host_keys`, `enable_ssh_rsa_compat`, `HostKeyPolicy`
- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/sftp-backend/index.md)

## API Reference

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

Bases: `Backend`

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
