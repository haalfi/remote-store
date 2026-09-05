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
| `timeout` | `int` | `10` | Connect-phase timeout in seconds (connect, banner, auth, channel open) |
| `io_timeout` | `float` | `120.0` | Seconds a blocking read or write on the open channel may stall before failing. Pass `None` for no bound; `0` and negatives are rejected |
| `connect_kwargs` | `dict` | `None` | Extra kwargs passed to `SSHClient.connect()` |

### Bounding a stalled transfer

`timeout` covers only the connect phase. Once the channel is open, paramiko
places no bound of its own on reads, so a peer that completes the handshake and
then stops sending mid-transfer would block indefinitely — holding whatever pool
slot or worker the transfer was running on, with no error to act on. `io_timeout`
is what stops that, and it is armed for you.

`io_timeout` bounds the silence *between* bytes rather than the transfer as a
whole, which is what makes it usable on slow links: a multi-gigabyte fetch that
takes an hour is unaffected, while a flow that goes quiet for longer than the
bound raises [`BackendUnavailable`](../../reference/api/errors.md). That error
names the stall and the value that fired (`SFTP channel stalled: no data within
io_timeout=120.0s`), and the backend logs it once at `WARNING`, so a stall is
distinguishable from any other `BackendUnavailable` in a log you read later. What
it does not say is whether the operation happened —
[a stalled operation may have succeeded](#capabilities).

**It is on by default, at 120 seconds.** You get the bound without asking for
it, so nothing you write hangs forever on a silent peer. What you configure is
whether that value suits your server:

```python
from remote_store.backends import SFTPBackend

backend = SFTPBackend(
    host="files.example.com",
    username="deploy",
    io_timeout=300,   # a server that legitimately goes quiet for longer
)
```

**Size it against the longest legitimate pause your server can produce, not
against total transfer time.** Raising it costs only how quickly a stall is
noticed, which is cheap — the bound is on silence between bytes, so a slow
transfer is unaffected at any value. Lowering it is the riskier direction: a
server that goes quiet for legitimate reasons, such as an antivirus or dedup
appliance scanning a large file when you open it, starts failing intermittently,
which looks like network flakiness and is harder to diagnose than the hang the
bound replaced.

To turn the bound off entirely, pass `None`:

```python
backend = SFTPBackend(host="files.example.com", username="deploy", io_timeout=None)
```

`0` is **not** how you ask for that — it is rejected with `ValueError`, because
paramiko reads `0` as non-blocking rather than as a bound, and every SFTP
operation waits on a reply, so all of them would fail at once.

It is an ordinary option, so it is equally settable from a declarative config:

```python
BackendConfig(
    type="sftp",
    options={"host": "files.example.com", "username": "deploy", "io_timeout": 300},
)
```

**Opting out declaratively takes an explicit null, not an omitted key** — leaving
`io_timeout` out selects the default, as it does in Python. In YAML that is
`io_timeout: null`; TOML has no null literal, so a TOML-configured store that
needs an unbounded channel has to construct the backend in code.

The bound is re-applied on every reconnect, including the transparent ones the
backend performs after a dropped connection, and it covers most of the SFTP
session setup as well as later transfers. Setting it through the
[escape hatch](#escape-hatch) instead does not survive those reconnects, because
each one opens a fresh channel.

!!! warning "Two limits, different in kind"
    **A wedged SSH daemon is not bounded at all.** A server that opens the SSH
    channel and then never answers the `sftp` subsystem request still hangs,
    regardless of `io_timeout`: paramiko waits for that reply on an untimed
    event, so no channel timeout applies, and every reconnect re-enters that
    window. It needs a wedged SSH daemon rather than a wedged SFTP subsystem, so
    it is rarer than the stall this option does cover — but if a peer hangs
    despite the bound, this is the shape to suspect.

    **Releasing a handle that never failed is bounded but silent.** Closing a
    stream you have not read to a failure on a stalled connection waits one
    `io_timeout` and then returns normally: paramiko catches that timeout inside
    its own close, so nothing is raised, `remote-store` logs nothing, and the
    dead connection stays cached for the next operation to wait on again. You
    see the delay, not the cause — paramiko's own DEBUG logging shows the close
    going out, but nothing there names the stall either. A stream whose read
    *did* fail costs nothing extra: that close is skipped.

A stall that surfaces is reported, and no stall is retried: the connect-phase
`RetryPolicy` does not cover one, so a partially consumed stream is never
silently restarted underneath you.
A streamed **read** raises rather than returning short, so a truncated transfer
is never mistaken for a complete one — discard the handle and start again, since
the bytes already delivered are a valid prefix but the handle is dead. The
backend drops the dead client, so the next operation reconnects.

Seeking to the end of a stream (`stream.seek(0, os.SEEK_END)`) asks the server
for the file's size, so it is bounded and reported like any other operation on
the channel. Worth knowing because you may not be the one writing the seek:
`read_seekable()` hands the stream to analytical readers such as PyArrow, and a
reader that sizes a file internally reaches it the same way — for files large
enough to stream. The [PyArrow adapter](../pyarrow-adapter.md) materialises
anything at or below its `materialization_threshold` and never seeks the stream
at all.

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

## Legacy Servers (`ssh-rsa` / SHA-1) { #legacy-ssh-rsa }

**What changed.** Paramiko 5.0 removed `ssh-rsa` from its host-key
defaults — empirically verified, see the [research note][bk-198-research]
for the version matrix.

- **paramiko `< 5`** ships `ssh-rsa` in defaults at all four negotiation
  sites. A freshly-imported paramiko already negotiates against an
  `ssh-rsa`-only server out of the box.
- **paramiko `>= 5`** has `ssh-rsa` removed from all four sites.
  Connecting to an `ssh-rsa`-only server raises
  `IncompatiblePeer: Incompatible ssh peer (no acceptable host key)`
  during KEX, before authentication is attempted.

The `[sftp]` extra has no upper bound on paramiko, so current resolvers
pick paramiko 5+ by default. New installs hit the failure unless they
call the helper described below.

### Diagnose first

Before mutating paramiko's defaults, confirm the failure shape. An
`IncompatiblePeer` error from paramiko wraps four distinct negotiation
failures — host key, KEX, cipher, or MAC — and only the first is fixed
by `enable_ssh_rsa_compat()`. The other three need
`connect_kwargs={"disabled_algorithms": ...}` instead.
[`SFTPUtils.scan_host_algorithms()`](../../reference/api/sftp-utils.md#remote_store.backends.SFTPUtils.scan_host_algorithms)
parses the server's `SSH_MSG_KEXINIT` advertisement (RFC 4253 § 7.1)
over a raw socket — no paramiko, no authentication, so the result
reflects exactly what the server advertises:

<!-- Rule 6 exemption: requires a live SFTP server; cannot execute in CI. -->
```python
from remote_store.backends import SFTPUtils

info = SFTPUtils.scan_host_algorithms("legacy.example.com")
print("host-key algos:", info["server_host_key_algorithms"])
print("kex algos:     ", info["kex_algorithms"])
```

[bk-198-research]: https://github.com/haalfi/remote-store/blob/master/sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md

If `server_host_key_algorithms == ["ssh-rsa"]`, this guide applies and
the next subsection is the fix. If it's `kex_algorithms` that's narrow
(e.g. only `diffie-hellman-group14-sha1`), `enable_ssh_rsa_compat()`
will not help; widen the relevant list via
`SFTPBackend(connect_kwargs={"disabled_algorithms": ...})`.

### Fix: re-enable `ssh-rsa` at process startup

[`SFTPUtils.enable_ssh_rsa_compat()`](../../reference/api/sftp-utils.md)
adds `ssh-rsa` to all four paramiko host-key sites in one call. It is a
no-op on paramiko `< 5` (all four guards short-circuit) and the required
recovery path on paramiko `>= 5`:

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

### Alternative: pin `paramiko<5`

Pinning `paramiko<5` keeps the consumer on the empirically-verified
compatible range (`>= 3.0,< 5`) and avoids the helper entirely. The
tradeoff is freezing on paramiko 4.x while upstream moves on:

| Approach | Loses |
|----------|-------|
| `paramiko<5` pin | Future paramiko 5+ improvements (perf, protocol features, CVE fixes once 4.x EOLs) |
| `enable_ssh_rsa_compat()` | Process-wide SHA-1 host-key acceptance only |

Either composes cleanly with the library's `[sftp]` floor of
`paramiko>=3.0`. To pin the consumer must override at their own dependency
layer (e.g. `requirements.txt` line `paramiko>=3.0,<5`).

## Connection Behaviour

- **Lazy connect** — no network call happens during construction. The SSH/SFTP connection is established on the first operation.
- **Auto-reconnect** — if the connection goes stale between operations, the backend reconnects transparently.
- **Retry** — transient SSH errors (`SSHException`, `OSError`, `EOFError`) are retried up to 3 times with exponential backoff (2 s min, 10 s max). Retry covers establishing the SSH connection only; nothing after that is restarted, and a stall bounded by `io_timeout` is reported to the caller unless it is one of the silent cases above.
- **Stall detection** — on by default: [`io_timeout`](#bounding-a-stalled-transfer) bounds a read or write that stops making progress on an open channel at 120 s. Tune it, or pass `None` to opt out.
- **Single connection, not thread-safe** — each `SFTPBackend` instance holds one paramiko `SFTPClient`. Calling it from multiple threads simultaneously (e.g. via `SyncBackendAdapter` + `asyncio.gather`) races on the shared socket. Create one `SFTPBackend` per thread for parallel workloads.

## Capabilities

The SFTP backend supports all capabilities except `GLOB` and `ATOMIC_MOVE`.
See the [capabilities matrix](../../reference/capabilities-matrix.md) for full details.

!!! warning "Atomic write caveat"
    Atomic writes use a temp file (`.~tmp.<name>.<uuid>`) and rename. If the
    connection drops between write and rename, the destination is untouched but
    the orphan temp file will remain on the server. If it drops *during* the
    rename, see the danger note below — the write may have landed, and on the
    fallback path a `.~bak.<name>.<uuid>` may hold your previous file.

!!! danger "A stalled operation may have succeeded"
    When a transfer stalls, the timeout tells you **no reply came back**. It
    does not tell you the server never got the request. If the silence was on
    the return path, the server did the work and only the answer was lost — so
    every operation here has a state where it did what you asked and raised
    `BackendUnavailable` anyway.

    The general rule is that **any amount of the operation may have happened,
    from none of it to all of it**, and the error does not tell you which. The
    states below are the ones worth naming, not a complete list:

    | Operation | What a `BackendUnavailable` may have left |
    | --- | --- |
    | `write()` | The destination unchanged, absent, **emptied**, holding an unpredictable prefix, or **written in full** |
    | `copy()` | The same five, at `dst`; the source is never affected |
    | `move()` | The paths unchanged, **the move completed** (source gone), or **the destination path empty** with its old content in a `.~bak.<name>.<uuid>` file and the source still there |
    | `write_atomic()` / `open_atomic()` | The destination unchanged, often with an orphan temp; **the write completed**; or **the destination path empty** with its old content in a `.~bak.<name>.<uuid>` file and your data in an orphan temp |

    The empty-destination cases come from a rename fallback, which cannot rename
    onto a path that is occupied: it moves the old file aside first and moves it
    back if the rename fails. Moving it back is best-effort: over a dropped
    connection it is not attempted at all, and on a live one the server can
    refuse it. Either way you get the state above — **nothing is lost, but the
    path you wrote to is not the file you had.** Your previous file is beside it
    as `.~bak.<name>.<uuid>`. The
    second copy depends on the operation: for `write_atomic()` / `open_atomic()`
    it is the `.~tmp.<name>.<uuid>` next to it, and for `move()` it is your
    source file, untouched at its own path — which may be in another directory
    entirely. `move()` never writes a temp. The
    fallback is not confined to old servers: any rename that *fails* for a reason
    the backend cannot attribute to a dropped connection takes that path. It also
    needs `overwrite=True`: with the default the call raises `AlreadyExists`
    before the fallback is reached. No example failure is given: which ones reach
    it depends on guards that differ per operation, and every attempt to name one
    here has been wrong.

    So:

    - **Do not treat a failure as a no-op.** Re-check the state before acting on
      it. A failed `move()` that actually succeeded gives `NotFound` on retry;
      a failed `write(..., overwrite=True)` may have truncated your previous
      file without replacing it.
    - **Retry with `overwrite=True`.** The path is usually still occupied, so a
      plain retry raises `AlreadyExists` instead of retrying.
    - **Do not resume from a partial file.** The prefix length depends on
      buffering you cannot see, so appending to it corrupts the file. Discard
      and re-write from the start.

    - **Look for a `.~bak.` file beside the target** before you re-create
      anything. On the fallback path it is your previous file, left where a
      failed call could not put it back. Your payload is in the `.~tmp.` beside
      it for `write_atomic()` / `open_atomic()`, and still at `src` for `move()`.

    **`write_atomic()` is still the right choice when readers must never see a
    half-written file** (see the caveat above, and
    [atomicity semantics](../../explanation/concurrency.md)): no reader ever
    observes a partial file at the destination. What it does not promise is that
    a reported failure means nothing happened, nor that your existing file
    survives one: a stall that loses the reply to a *successful* rename has
    replaced it, and nothing was kept. The fallback path is the one that keeps a
    copy, because it is the one that moved your file aside to begin with.

    Parent directories created for a write remain behind in every case — a
    failed write is not a rollback.

!!! note "Move fallback"
    `move()` tries `posix_rename` (atomic), then standard `rename()`, then
    copy + delete as a last resort. Most servers support at least `rename()`.

!!! note "TOCTOU on `overwrite=False`"
    Like most backends, the exists-check and write are separate operations.
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
