# SFTP Backend

The SFTP backend stores files on any SSH/SFTP server using [paramiko](https://www.paramiko.org/). Unlike fsspec's `SFTPFileSystem`, it gives you explicit control over host key verification and handles Azure Key Vault PEM quirks out of the box.

## Installation

```bash
pip install remote-store[sftp]
```

This pulls in `paramiko` and `tenacity` (for automatic retry on transient SSH errors).

## Usage

```python
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

```python
from remote_store.backends import SFTPBackend
from remote_store.backends._sftp import load_private_key

pkey = load_private_key("/path/to/id_rsa", from_file=True)

backend = SFTPBackend(
    host="files.example.com",
    username="deploy",
    pkey=pkey,
)
```

Or load a PEM string directly (useful for secrets managers like Azure Key Vault):

```python
pkey = load_private_key(pem_string)
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | `str` | *(required)* | SFTP server hostname |
| `port` | `int` | `22` | SSH port |
| `username` | `str` | `None` | SSH username |
| `password` | `str` | `None` | SSH password |
| `pkey` | `paramiko.PKey` | `None` | Private key for key-based auth |
| `base_path` | `str` | `"/"` | Root path on the remote server |
| `host_key_policy` | `HostKeyPolicy` | `STRICT` | Host key verification mode (see below) |
| `known_host_keys` | `str` | `None` | Known-hosts string (code-level override) |
| `host_keys_path` | `str` | `~/.ssh/known_hosts` | Path to known_hosts file |
| `config` | `dict` | `None` | Config dict (may contain `known_host_keys`) |
| `timeout` | `int` | `10` | SSH connection timeout in seconds |
| `connect_kwargs` | `dict` | `None` | Extra kwargs passed to `SSHClient.connect()` |

## Host Key Verification

The `HostKeyPolicy` enum controls how unknown host keys are handled:

| Policy | Behaviour | Use case |
|--------|-----------|----------|
| `STRICT` | Reject unknown hosts. Key must be in known_hosts. | Production (default) |
| `TRUST_ON_FIRST_USE` | Accept and save on first connect, verify after. | First-time server setup |
| `AUTO_ADD` | Accept any key silently. | Dev / testing only |

Known host keys are resolved in order (first match wins):

1. `known_host_keys` constructor parameter
2. `config["known_host_keys"]` dict value
3. `SFTP_KNOWN_HOST_KEYS` environment variable
4. `host_keys_path` file on disk (default: `~/.ssh/known_hosts`)

```python
from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

# Development / testing
backend = SFTPBackend(
    host="localhost",
    port=2222,
    username="test",
    password="test",
    host_key_policy=HostKeyPolicy.AUTO_ADD,
)
```

## Connection Behaviour

- **Lazy connect** — no network call happens during construction. The SSH/SFTP connection is established on the first operation.
- **Auto-reconnect** — if the connection goes stale between operations, the backend reconnects transparently.
- **Retry** — transient SSH errors (`SSHException`, `OSError`, `EOFError`) are retried up to 3 times with exponential backoff (2 s min, 10 s max).

## Capabilities

The SFTP backend supports all capabilities **except** `GLOB`:

| Capability | Supported | Notes |
|------------|-----------|-------|
| `READ` | Yes | |
| `WRITE` | Yes | Creates intermediate directories automatically |
| `DELETE` | Yes | |
| `LIST` | Yes | |
| `RECURSIVE_LIST` | Yes | |
| `MOVE` | Yes | Uses `posix_rename` with fallback |
| `COPY` | Yes | Read + write (no server-side copy in SFTP) |
| `ATOMIC_WRITE` | Yes | Temp file + rename (see caveat below) |
| `METADATA` | Yes | |
| `GLOB` | No | No server-side glob; not offered to avoid misleading perf |

!!! warning "Atomic write caveat"
    Atomic writes use a temp file (`.~tmp.<name>.<uuid>`) and rename. If the connection drops between write and rename, the orphan temp file will remain on the server.

## Escape Hatch

Access the underlying `paramiko.SFTPClient` when you need protocol-level features:

```python
import paramiko

sftp_client = backend.unwrap(paramiko.SFTPClient)
sftp_client.listdir_attr("/custom/path")
```

## API Reference

::: remote_store.backends.SFTPBackend
