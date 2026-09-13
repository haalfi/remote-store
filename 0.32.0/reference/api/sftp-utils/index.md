# SFTPUtils

Backend-specific module

The helpers and enums in this module are exclusive to the SFTP backend. Using them ties your code to `SFTPBackend`.

## SFTPUtils

SFTP setup utilities for key loading and host verification.

Groups helpers that assist with SFTP backend configuration:

- `SFTPUtils.load_private_key(...)` -- load RSA keys from file or PEM string
- `SFTPUtils.HostKeyPolicy` -- enum controlling unknown host key behavior
- `SFTPUtils.scan_host_keys(host, port=22)` -- preflight host-key discovery; returns a `known_hosts`-formatted line for committing into a `host.keys` file
- `SFTPUtils.scan_host_algorithms(host, port=22)` -- raw-socket SSH KEXINIT probe; returns the server's algorithm advertisement (kex / host-key / cipher / MAC / compression name-lists) for diagnosing `IncompatiblePeer` failures
- `SFTPUtils.enable_ssh_rsa_compat()` -- restore `ssh-rsa` (SHA-1) acceptance for legacy SFTP servers (see method docstring for the security tradeoff)

Example

```
from remote_store.backends import SFTPUtils, SFTPBackend

key = SFTPUtils.load_private_key("~/.ssh/id_rsa", from_file=True)
backend = SFTPBackend(
    host="sftp.example.com",
    pkey=key,
    host_key_policy=SFTPUtils.HostKeyPolicy.AUTO_ADD,
)
```

## Methods

### load_private_key

```
load_private_key(
    source: str, *, from_file: bool = False
) -> Any
```

Load an RSA private key from a file path or a PEM string.

Parameters:

- **`source`** (`str`) – File path (if from_file=True) or PEM-encoded string.
- **`from_file`** (`bool`, default: `False` ) – If True, treat source as a file path.

Returns:

- `Any` – paramiko.RSAKey

### enable_ssh_rsa_compat

```
enable_ssh_rsa_compat() -> None
```

Guarantee `ssh-rsa` (SHA-1) acceptance across paramiko's four host-key sites.

Appends `ssh-rsa` to four paramiko class attributes if it is missing — future-proofing the consumer against eventual removal, and restoring state if downstream code has cleared it:

1. `paramiko.Transport._preferred_keys` -- KEX host-key-algorithm negotiation.
1. `paramiko.Transport._key_info` -- host-key parsing dispatch.
1. `paramiko.rsakey.RSAKey.HASHES` -- signature-verification hash dispatch.
1. `paramiko.Transport._preferred_pubkeys` -- client RSA public-key authentication signatures.

Empirically verified across paramiko 2.12 / 3.0 / 3.5 / 4.0 / 5.0 (see `sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md`):

- On paramiko **< 5.0** all four sites contain `ssh-rsa` by default, so a freshly-imported paramiko already negotiates against an `ssh-rsa`-only server. The helper is a no-op (all four guards short-circuit) and is safe to call eagerly for forward compatibility.
- On paramiko **>= 5.0** all four sites have `ssh-rsa` removed. Bare connect to an `ssh-rsa`-only server fails immediately in `Transport._parse_kex_init` with `IncompatiblePeer: no acceptable host key`. Calling this helper at process startup is the only way to restore the connection without monkey-patching `connect_kwargs["disabled_algorithms"]` on every connect.

For KEX / cipher / MAC negotiation failures (e.g. `IncompatiblePeer: no acceptable kex algorithm`), this helper is not the right tool — use `connect_kwargs={"disabled_algorithms": ...}` to widen those instead.

`disabled_algorithms` cannot re-add a default-removed algorithm, so class-level patching is the only forward-compatible path. The patches are idempotent; calling this multiple times in the same process is safe.

Process-global side effect

Every paramiko transport in this process will accept SHA-1 host keys for the lifetime of the process. Only call this if the consumer connects exclusively to servers under your operational control, or if you have explicitly evaluated the tradeoff for every server in the process.

`ssh-rsa` is appended (not prepended) to the preferred lists, so modern algorithms are still negotiated first when the server offers them.

Single-threaded startup only

The four read-then-write patches are not atomic; if two threads enter the helper at the same time they race on the rebind. Call once at process startup before any backend connect, not from a request-handling code path.

Example

```
from remote_store.backends import SFTPUtils

# Call once at process startup, before any SFTPBackend connect.
SFTPUtils.enable_ssh_rsa_compat()
```

### scan_host_keys

```
scan_host_keys(
    host: str, port: int = 22, *, timeout: float = 10.0
) -> str
```

Discover an SFTP server's host key without authenticating.

Opens a `paramiko.Transport` to *host*:*port*, performs key exchange, captures the server's offered host key, closes the connection, and returns the key as a single `known_hosts`-formatted line. No authentication is attempted; only the SSH key-exchange handshake runs.

Use this to populate a committed `host.keys` file for production `STRICT` policy use, without going through a TOFU connect first.

Parameters:

- **`host`** (`str`) – Hostname or IP address of the SFTP server.
- **`port`** (`int`, default: `22` ) – SSH port (default: 22).
- **`timeout`** (`float`, default: `10.0` ) – Socket and KEX timeout in seconds (default: 10).

Returns:

- `str` – A single known_hosts-format line:
- `str` – "\<host_label> \<key_type> \<base64_key>". Per OpenSSH convention,
- `str` – host_label is "\[host\]:port" when port is not 22, and the
- `str` – bare hostname otherwise. The trailing newline is not included.
- `str` – Returns only the negotiated key for one handshake (whichever
- `str` – key type paramiko picked: usually one of ed25519, ecdsa, rsa),
- `str` – not every key the server offers. ssh-keyscan returns one line
- `str` – per offered type by default; this helper does not. If the server
- `str` – offers multiple key types and paramiko later negotiates a
- `str` – different one than the pinned line, the connection fails with
- `str` – BadHostKeyException. Callers that need full-type coverage
- `str` – must call this helper multiple times under different
- `str` – disabled_algorithms settings to force each type in turn.

Raises:

- `SSHException` – Negotiation failed (e.g. legacy server offering only ssh-rsa; call enable_ssh_rsa_compat() first if so).
- `OSError` – Socket-level failure (host unreachable, port refused, DNS error, timeout).

Example

```
from pathlib import Path

from remote_store.backends import SFTPUtils

entry = SFTPUtils.scan_host_keys("sftp.example.com")
Path("host.keys").write_text(entry + "\n")
```

### scan_host_algorithms

```
scan_host_algorithms(
    host: str, port: int = 22, *, timeout: float = 10.0
) -> dict[str, list[str] | str]
```

Discover an SFTP server's algorithm advertisement without authenticating.

Opens a raw TCP socket, exchanges SSH banners, reads the server's first `SSH_MSG_KEXINIT` packet (RFC 4253 § 7.1), parses the ten name-lists it carries, and returns them as a dictionary. No paramiko, no key exchange completes, no authentication is attempted.

Use this to identify the failure shape behind an `IncompatiblePeer` error. `IncompatiblePeer` wraps four distinct negotiation failures (host key / KEX / cipher / MAC), and only the first is addressable by `enable_ssh_rsa_compat()`. Inspecting the four corresponding name-lists in the result tells you which list the server narrowed and to what.

Pure-socket parsing (rather than driving `paramiko.Transport`) is deliberate: the result reflects what the *server* advertises, independent of any process-global paramiko state mutated by `enable_ssh_rsa_compat()` or downstream code.

Parameters:

- **`host`** (`str`) – Hostname or IP address of the SFTP server.
- **`port`** (`int`, default: `22` ) – SSH port (default: 22).
- **`timeout`** (`float`, default: `10.0` ) – Socket timeout in seconds (default: 10).

Returns:

- `dict[str, list[str] | str]` – A dictionary with eleven entries:
- `dict[str, list[str] | str]` – "banner" -- the server's identification string (e.g. "SSH-2.0-OpenSSH_8.9p1").
- `dict[str, list[str] | str]` – The ten RFC 4253 § 7.1 name-lists, each as a Python list\[str\]: kex_algorithms, server_host_key_algorithms, encryption_algorithms_ctos, encryption_algorithms_stoc, mac_algorithms_ctos, mac_algorithms_stoc, compression_algorithms_ctos, compression_algorithms_stoc, languages_ctos, languages_stoc.

Raises:

- `OSError` – Socket-level failure (host unreachable, port refused, timeout, connection reset, unexpected EOF, or the server's first packet was not SSH_MSG_KEXINIT).

Diagnose an `ssh-rsa`-only legacy server

```
from remote_store.backends import SFTPUtils

info = SFTPUtils.scan_host_algorithms("legacy.example.com")
print(info["server_host_key_algorithms"])
# ['ssh-rsa']  -> classic legacy server; on paramiko 5+,
# call SFTPUtils.enable_ssh_rsa_compat() at process startup.
```

Diagnose a narrow-KEX server

```
info = SFTPUtils.scan_host_algorithms("legacy.example.com")
print(info["kex_algorithms"])
# ['diffie-hellman-group14-sha1']  -> KEX narrowing;
# widen via SFTPBackend(connect_kwargs={"disabled_algorithms": ...}).
```

## Enums

### HostKeyPolicy

Bases: `Enum`

Controls how unknown remote host keys are handled.

Attributes:

- **`STRICT`** – Reject unknown hosts (production default).
- **`TRUST_ON_FIRST_USE`** – Save on first connect, verify after.
- **`AUTO_ADD`** – Accept any key (dev/testing ONLY).

Accepts the enum-name forms (`"auto_add"`, `"trust_on_first_use"`, `"STRICT"`) in addition to the canonical value strings (`"auto"`, `"tofu"`, `"strict"`).

## See also

- [SFTP Backend Guide](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) — connection setup, host key verification, and Key Vault integration
- [SFTP Backend example](https://docs.remotestore.dev/stable/tutorial/examples/sftp-backend/index.md) — end-to-end SFTP usage
