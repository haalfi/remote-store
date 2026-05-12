# SFTP Backend

The SFTP backend stores files on any SSH/SFTP server using [paramiko](https://www.paramiko.org/). Unlike fsspec's `SFTPFileSystem`, it gives you explicit control over host key verification and handles Azure Key Vault PEM quirks out of the box.

## Installation

```bash
pip install "remote-store[sftp]"
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
from remote_store.backends import SFTPBackend, SFTPUtils

pkey = SFTPUtils.load_private_key("/path/to/id_rsa", from_file=True)

backend = SFTPBackend(
    host="files.example.com",
    username="deploy",
    pkey=pkey,
)
```

Or load a PEM string directly (useful for secrets managers like Azure Key Vault):

```python
pkey = SFTPUtils.load_private_key(pem_string)
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

## Preflight host-key discovery

To populate a committed `host.keys` file without going through a TOFU connect
first, use [`SFTPUtils.scan_host_keys(host, port=22)`](../../reference/api/sftp-utils.md).
It opens a transport, captures the server's *negotiated* host key (no
authentication), and returns a single `known_hosts`-formatted line ready to
commit:

<!-- Rule 6 exemption: requires a live SFTP server; cannot execute in CI. -->
```python
from pathlib import Path
from remote_store.backends import SFTPUtils

entry = SFTPUtils.scan_host_keys("sftp.example.com")
Path("host.keys").write_text(entry + "\n")
```

For non-default ports the entry uses the OpenSSH `[host]:port` form.
Network failures (host unreachable, port refused, DNS error) raise `OSError`;
KEX failures (legacy server offering only `ssh-rsa`) raise
`paramiko.SSHException` — call `enable_ssh_rsa_compat()` first in that case.

`scan_host_keys()` returns the **negotiated** key for one handshake, not
every key type the server offers. If the server publishes multiple key types
and paramiko later negotiates a type other than the pinned line, the
connection fails with `BadHostKeyException`. Call the helper multiple times
under different `disabled_algorithms` settings if you need full-type
coverage.

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

Paramiko has deprecated `ssh-rsa` (SHA-1) and reserves removal for a future
major release. Empirically (verified against paramiko 2.12, 3.0, 3.5, 4.0
in `sandbox/bk-198-empirical-verification.md`), a freshly-imported paramiko
of any of those versions already negotiates against an `ssh-rsa`-only
server out of the box — including against a server that also restricts KEX
to legacy SHA-1 variants. `ssh-rsa` is therefore not the root cause of
most legacy-SFTP connection failures today; it becomes one only when
something has cleared `ssh-rsa` from paramiko's defaults. Concretely you
will see one of these errors when that state is reached:

| Error | Stage that failed |
|-------|-------------------|
| `IncompatiblePeer: no acceptable host key` | KEX host-key-algorithm negotiation |
| `KeyError: 'ssh-rsa'` (during connect) | Host-key parsing dispatch |
| `SSHException: Signature verification (ssh-rsa) failed.` | Signature verification |

`disabled_algorithms` cannot re-add a default-removed algorithm.
[`SFTPUtils.enable_ssh_rsa_compat()`](../../reference/api/sftp-utils.md)
ensures `ssh-rsa` is present at all four sites in one call — a no-op on
freshly-imported paramiko, and a recovery / forward-compatibility shim
otherwise:

```python
--8<-- "examples/snippets/sftp_legacy_servers.py:enable-ssh-rsa-compat"
```

!!! note "If you observe `IncompatiblePeer: no acceptable kex algorithm`"
    KEX / cipher / MAC negotiation failures are a separate problem;
    `enable_ssh_rsa_compat()` does not help. Widen the relevant
    algorithm list via the `connect_kwargs={"disabled_algorithms": ...}`
    SFTP constructor argument instead.

!!! warning "Security tradeoff"
    This is **process-global**: every paramiko transport in the process
    will then accept SHA-1 host keys. Only enable this if every server
    your process connects to is under your operational control, and push
    server operators to upgrade to `rsa-sha2-256`/`rsa-sha2-512` so the
    shim can be removed.

### Alternative: pin `paramiko<3`

Paramiko 2.x and 3.x both ship `ssh-rsa` in defaults natively (verified).
Pinning paramiko 2.x is a legitimate alternative when the consumer runs
in an isolated environment (e.g. a build-agent task connecting only to
one legacy server). The tradeoffs:

| Approach | Loses |
|----------|-------|
| `paramiko<3` pin | Terrapin (CVE-2023-48795) mitigation; caps `cryptography<40`; paramiko 2.x is EOL with no CVE backports |
| `enable_ssh_rsa_compat()` | Process-wide SHA-1 host-key acceptance only |

The library's `[sftp]` extra requires `paramiko>=3.0` (paramiko 2.x
lacks `channel_timeout=` on `SSHClient.connect`); to pin paramiko 2.x
the consumer must override at their own dependency layer.

## Connection Behaviour

- **Lazy connect** — no network call happens during construction. The SSH/SFTP connection is established on the first operation.
- **Auto-reconnect** — if the connection goes stale between operations, the backend reconnects transparently.
- **Retry** — transient SSH errors (`SSHException`, `OSError`, `EOFError`) are retried up to 3 times with exponential backoff (2 s min, 10 s max).
- **Single connection, not thread-safe** — each `SFTPBackend` instance holds one paramiko `SFTPClient`. Calling it from multiple threads simultaneously (e.g. via `SyncBackendAdapter` + `asyncio.gather`) races on the shared socket. Create one `SFTPBackend` per thread for parallel workloads.

## Capabilities

The SFTP backend supports all capabilities except `GLOB` and `ATOMIC_MOVE`.
See the [capabilities matrix](../../reference/capabilities-matrix.md) for full details.

!!! warning "Atomic write caveat"
    Atomic writes use a temp file (`.~tmp.<name>.<uuid>`) and rename. If the
    connection drops between write and rename, the orphan temp file will remain
    on the server.

!!! note "Move fallback"
    `move()` tries `posix_rename` (atomic), then standard `rename()`, then
    copy + delete as a last resort. Most servers support at least `rename()`.

!!! note "TOCTOU on `overwrite=False`"
    Like all backends, the exists-check and write are separate operations.
    Concurrent writers can both pass the check.

See the [Concurrency and Atomicity Guarantees](../../explanation/concurrency.md) guide for details and workarounds.

## Escape Hatch

Access the underlying `paramiko.SFTPClient` when you need protocol-level features:

```python
import paramiko

sftp_client = backend.unwrap(paramiko.SFTPClient)
sftp_client.listdir_attr("/custom/path")
```

## See also

- [Capabilities matrix](../../reference/capabilities-matrix.md)
- [API reference](../../reference/api/store.md)
- [SFTP utilities reference](../../reference/api/sftp-utils.md) — `scan_host_keys`, `enable_ssh_rsa_compat`, `HostKeyPolicy`
- [Example script](../../../examples/backends/sftp_backend.py)

## API Reference

::: remote_store.backends.SFTPBackend
