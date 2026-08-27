# SFTP Backend Specification

## Overview

`SFTPBackend` implements the `Backend` ABC for SSH File Transfer Protocol (SFTP) servers
using **pure paramiko** internally. It maps the Backend contract onto a real remote
filesystem accessed over SSH/SFTP.

Unlike fsspec's `SFTPFileSystem` (which hardcodes `AutoAddPolicy`), this backend
provides explicit host key policy control via a `HostKeyPolicy` enum, PEM key
sanitization for Azure Key Vault compatibility, and tenacity-based retry for
transient SSH errors.

**Dependencies:** `paramiko`, `tenacity` (optional extra: `pip install "remote-store[sftp]"`)

---

## Construction

### SFTP-001: Constructor Parameters

**Invariant:** `SFTPBackend` is constructed with a required `host` and optional
connection/authentication parameters.
**Signature:**
```python
SFTPBackend(
    host: str,
    *,
    port: int = 22,
    username: str | None = None,
    password: str | None = None,
    pkey: Any = None,                   # paramiko.PKey, lazy-typed
    base_path: str = "/",               # root on remote server
    host_key_policy: HostKeyPolicy = HostKeyPolicy.STRICT,
    known_host_keys: str | None = None,
    host_keys_path: str | None = None,  # defaults to ~/.ssh/known_hosts
    config: dict | None = None,         # may contain "known_host_keys"
    timeout: int = 10,                  # connect phase only (see SFTP-030)
    io_timeout: float | None = None,    # bound on a stalled open channel
    connect_kwargs: dict | None = None, # extra SSHClient.connect() kwargs
)
```
**Postconditions:** The backend stores configuration but does not connect during
construction (see SFTP-004).

### SFTP-002: Backend Name

**Invariant:** `name` property returns `"sftp"`.

### SFTP-003: Capability Declaration

**Invariant:** `SFTPBackend` declares capabilities:
`READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `WRITE_RESULT_NATIVE`. Does not declare `GLOB` (no native pattern matching; use `list_files(pattern=…)` or `ext.glob` for client-side fallback).
**Rationale:**
- `WRITE_RESULT_NATIVE`: `write()` and `write_atomic()` populate `size` (counted
  during upload) and `source` from the write path itself. Every rich field
  (`etag` / `version_id` / `last_modified` / `digest`) is `None` — SFTP's write
  response carries no metadata at all, and the backend does not stat after
  upload/rename to fetch any (BK-313: that round-trip was paid on every write).
  WR-001a permits `None` for a field the write response omits, so the declaration
  rests on `size` / `source`; callers needing the metadata call `get_file_info()`.
- `ATOMIC_WRITE`: Simulated via temp file + rename (see SFTP-014). Orphan temp
  files are possible on connection failure — documented caveat.
- `MOVE`: Implemented via `posix_rename` with fallback (see SFTP-018).
- `COPY`: Implemented via read + write (no server-side copy in SFTP, see SFTP-019).
- Read-path directory rejection is **lazy** for `read_bytes` (BK-313: the eager
  `stat` was the round-trip removed): a directory target raises `InvalidPath`
  only because reading it fails. This assumes the server either refuses to open
  a directory for reading or reports a non-zero directory `st_size` — both hold
  on OpenSSH, where a directory reports `st_size == 4096`. A non-standard server
  that opens a directory for reading *and* reports `st_size == 0` would make
  `read_bytes` return empty bytes rather than raising `InvalidPath`. `read`
  (streaming) keeps an **eager** check instead, because a streaming read never
  issues the in-band I/O that would surface the directory. Accepted as a
  documented server assumption (audit-020 M3).

### SFTP-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. The SSH/SFTP connection is
established lazily on first operation.
**Rationale:** Fail-fast at construction is undesirable — the backend may be created
during application wiring before the network is available. Automatic reconnection
on staleness is also supported (see SFTP-010).

### SFTP-005: Construction Validation

**Invariant:** `host` must be a non-empty string. Passing an empty or whitespace-only
host raises `ValueError` at construction time. `io_timeout`, when not `None`, must
be a positive number of seconds; `0` and negatives raise `ValueError` — paramiko
reads `0` as non-blocking, which would fail every read immediately rather than
bound it.
**Postconditions:** No network validation of host reachability at construction time.

---

## Connection

### SFTP-006: HostKeyPolicy Enum

**Invariant:** `HostKeyPolicy` controls how unknown remote host keys are handled:
- `STRICT` (default): Reject unknown hosts. Requires host key in known_hosts.
- `TRUST_ON_FIRST_USE`: Accept and save on first connect, verify on subsequent connects.
- `AUTO_ADD`: Accept any key. **Development/testing only — not safe for production.**

String values (`"strict"`, `"tofu"`, `"auto"`) passed from TOML/YAML config are
coerced to the enum in `__init__` via `HostKeyPolicy(value)`. The enum-name
forms (`"STRICT"`, `"TRUST_ON_FIRST_USE"`, `"AUTO_ADD"`) are also accepted,
case-insensitive on the name (`"auto_add"` and `"Auto_Add"` both resolve to
`AUTO_ADD`); value-form aliasing (e.g. `"AUTO"` for canonical value `"auto"`)
is not folded and continues to raise `ValueError`. Invalid strings, and any
non-string input, raise `ValueError`. See
[020-credential-hygiene.md](020-credential-hygiene.md) SEC-005.

### SFTP-007: Host Key Resolution Chain

**Invariant:** Known host keys are resolved with first-match precedence:
1. `known_host_keys` constructor parameter (code-level override)
2. `config["known_host_keys"]` dict value
3. `SFTP_KNOWN_HOST_KEYS` environment variable
4. `host_keys_path` file on disk (default: `~/.ssh/known_hosts`)

**Postconditions:** If none of the above yield keys and the policy is `STRICT`,
connection will fail with a host key verification error.

### SFTP-008: PEM Key Sanitization

**Invariant:** `_sanitize_pem()` normalizes PEM line separators, handling the Azure
Key Vault quirk where newlines may be replaced with spaces or other characters.
**Postconditions:** The sanitized PEM string has standard `\n` line separators within
the Base64 payload. Invalid PEM structures (not 5 parts) raise `ValueError`.

### SFTP-009: Tenacity Retry on Connect

**Invariant:** `_connect()` retries the `ssh.connect()` call on transient SSH
errors using tenacity. The retried closure is that call alone, **not** the whole
of `_connect`: the SFTP channel open and session setup that follow it run once,
outside the retry, so a failure there is reported rather than retried (SFTP-030
depends on this scope being stated precisely).
When no `RetryPolicy` is provided, uses defaults: 3 attempts, exponential backoff
(2s min, 10s max). When a `RetryPolicy` is provided via the `retry` constructor
parameter, maps its fields to tenacity: `max_attempts` -> `stop_after_attempt`,
`backoff_base` -> `wait_exponential(min=)`, `backoff_max` -> `wait_exponential(max=)`,
`jitter` -> `wait_random(0, jitter)`, `timeout` -> `stop_after_delay`.
See also: spec `025-retry-policy.md` (RET-010).
**Retried exceptions:** `paramiko.SSHException`, `OSError`, `EOFError`.
**Postconditions:** After all retries are exhausted, the original exception is reraised.

### SFTP-010: Staleness Detection and Reconnect

**Invariant:** Staleness is detected in two tiers, neither of which spends a
per-operation round-trip. **(1)** The lazy `_sftp` property reads the SSH
transport's `is_active()` flag — a local check, no bytes on the wire; a
transport that has gone inactive is reconnected before the operation runs.
**(2)** A drop that leaves the transport flag `True` but the SFTP channel dead
(idle-channel timeout, subsystem restart, half-open partition) is invisible to
tier 1; it is caught on the operation itself and mapped to `BackendUnavailable`,
which invalidates the cached client so the *next* `_sftp` access reconnects. The
trigger is the *conclusion* that the connection is unusable, not any single
signal: **every** mapping that concludes `BackendUnavailable` clears the client,
across the full dead-connection signal set (`EOFError`, `OSError('Socket is
closed')`, the socket-teardown errnos, `socket.timeout`, and the paramiko
`SFTPError` / `SSHException` / `ChannelException` families — see SFTP-023).
Anchoring recovery to that conclusion rather than an enumerated list is what
keeps a signal the list forgot from wedging the long-lived backend — the list
above is evidence of the current signals, not the guarantee. No worked example
is given deliberately: every signal named here is enumerated, mapped and
tested, so any example drawn from the list would illustrate the opposite of the
claim. Note also that this tier only *handles* a `socket.timeout`; nothing here
causes one. A read that stalls on an open channel raises nothing at all unless
SFTP-030's `io_timeout` arms the bound, so with its default of `None` this path
is unreachable for a merely silent peer. Operations outside the default
`_errors()` scope must still route through this mapping for the guarantee to
hold: the listing operations route their failure through `_map_exception`, and
`open_atomic`'s streamed-write phase — which yields the handle outside
`_errors()` — routes its backend failures (a dead channel or any paramiko SSH /
protocol error surfaced during the caller's writes) through `_map_exception`
too, while its temp-file open and promote steps run inside `_errors()`.
**Rationale:** The property is accessed several times per operation, so the
former `stat('.')` liveness probe multiplied each operation's RTT count — but it
doubled as a universal self-heal, reconnecting a dead client of *any* kind on
the next op. The transport flag costs nothing on the wire; tier 2 restores that
self-heal for a channel-only death by clearing the client on every
`BackendUnavailable`, without adding a probe to the happy path.
**Postconditions:** A healthy connection is reused with no per-operation probe
round-trip. A dropped connection surfaces as `BackendUnavailable` and the
following call re-establishes it — recovery may take one failed call when the
drop is channel-only (tier 2).

---

## Filesystem Model

### SFTP-011: Real Directories

**Invariant:** SFTP operates on a real remote filesystem with actual directories,
unlike S3's virtual prefix-based folders. `is_folder()` uses `stat()` + `S_ISDIR`.
**Postconditions:** Folders exist independently of their contents.

### SFTP-012: Write Creates Intermediate Directories

**Invariant:** `write("a/b/c.txt", content)` creates intermediate directories `a/`
and `a/b/` if they do not exist.
**Rationale:** SFTP servers reject writes to non-existent directories. Creating them
automatically matches the convenience of local and S3 backends.

### SFTP-013: Empty Folders Persist

**Invariant:** Unlike S3 (where folders vanish when empty), empty directories on an
SFTP server persist after their contents are deleted.
**Postconditions:** `is_folder("dir")` returns `True` even after all files under
`dir/` are deleted.

---

## Operations

### SFTP-014: Atomic Write (Simulated)

**Invariant:** `write_atomic` writes to a temporary file `.~tmp.<name>.<uuid8>` in
the same directory as the target, then renames to the target via `posix_rename`.
**Caveat:** If the connection drops between write and rename, the orphan temp file
remains. This is **simulated** atomicity, not true atomicity — the capability is
declared to enable the write-then-rename pattern, but the caveat must be documented.
**Postconditions:** On success, the temp file is gone and the target contains the
new content. On failure, the backend makes a **best-effort** temp-file cleanup that
never reconnects: when the failure is itself a dropped-connection signal (or the
client is already invalidated), the cleanup unlink is deliberately skipped rather
than triggering a fresh connect against a possibly-down server inside the
error-handling path — so the orphan-temp caveat above holds and the original error
propagates without a multi-second reconnect stall. An abnormal exit of an
`open_atomic` block (including a `GeneratorExit` / `KeyboardInterrupt`) removes the
temp file under the same best-effort guard.

### SFTP-015: Atomic Write Overwrite Semantics

**Invariant:** `write_atomic(path, content, overwrite=False)` raises `AlreadyExists`
if the target already exists. With `overwrite=True`, the existing file is replaced.

### SFTP-016: delete_folder Recursive

**Invariant:** `delete_folder(path, recursive=True)` walks the directory tree
bottom-up, deleting files then directories.
**Raises:** `NotFound` if the folder does not exist and `missing_ok=False`.

### SFTP-017: delete_folder Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` succeeds only if the directory
is empty.
**Raises:** `NotFound` if missing. `RemoteStoreError` if the directory is not empty.

### SFTP-018: Move Via posix_rename

**Invariant:** `move(src, dst)` attempts `posix_rename` (atomic overwrite), falls back
to `rename`, and falls back to copy + delete if rename fails entirely.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and
`overwrite=False`.

### SFTP-019: Copy Via Read + Write

**Invariant:** `copy(src, dst)` reads the source file and writes it to the destination.
There is no server-side copy operation in SFTP — data passes through the client.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and
`overwrite=False`.

---

## Error Mapping

### SFTP-020: NotFound Mapping

**Invariant:** `IOError` with `errno.ENOENT` (errno 2) and `FileNotFoundError` are
mapped to `NotFound`.
**Postconditions:** `path` and `backend` attributes are set on the error.

### SFTP-021: PermissionDenied Mapping

**Invariant:** `IOError` with `errno.EACCES` (errno 13) is mapped to `PermissionDenied`.

### SFTP-022: AlreadyExists Mapping

**Invariant:** `IOError` with `errno.EEXIST` (errno 17) is mapped to `AlreadyExists`.

### SFTP-023: BackendUnavailable Mapping

**Invariant:** `paramiko.SSHException` and its subclasses (authentication failures,
`ChannelException`, etc.) are mapped to `BackendUnavailable`. So are the dropped-
connection signals that are *not* `SSHException` subclasses: `EOFError`,
`OSError('Socket is closed')` (no `errno`), `OSError` with `errno` in
`ECONNRESET` / `EPIPE` / `ECONNABORTED` / `ETIMEDOUT` / `ESHUTDOWN` / `ENOTCONN` /
`EBADF`, `socket.timeout` / `TimeoutError` (matched by type, since a half-open
instance often carries no matching `errno`), and `paramiko.SFTPError` (an
SFTP-protocol failure that subclasses neither `OSError` nor `SSHException`).
**Every** `BackendUnavailable` this mapping returns — the `SSHException` family
included — invalidates the cached SFTP client so the next operation reconnects
(see SFTP-010, tier 2). The list is not the guarantee: recovery is anchored to
the `BackendUnavailable` *conclusion*, so a dead-connection signal the list has
not enumerated still clears the client rather than wedging the backend. One
exception keeps its own branch first: `IncompatiblePeer` (a connect-time
`SSHException`) is mapped with a diagnostic hint before the generic `SSHException`
mapping, so the hint is not lost.

### SFTP-024: No Native Exception Leakage

**Invariant:** No paramiko, socket, or OS exception raised *by the backend* — an
operation's own I/O, including `open_atomic`'s temp-file open, the caller-facing
handle's flush/close, and the promote — propagates to callers; all are mapped to
`remote_store` error types per BE-021. The only non-mapped exceptions are those
the **caller** raises inside an `open_atomic` yield block (their `with` body)
that are not themselves dead-connection signals: those are not the backend's and
propagate unchanged, leaving the target untouched. `open_atomic` distinguishes
by scope — the temp open, flush, and promote run inside `_errors()`, while the
yielded write does not; a dead-connection signal surfacing from that write is
still mapped to `BackendUnavailable` (it is indistinguishable from a real drop).
**Postconditions:** `backend` attribute is set to `"sftp"` on all mapped errors.

---

## Resource Management

### SFTP-025: close()

**Invariant:** `close()` closes both the SFTP client and the underlying SSH transport.
**Postconditions:** Safe to call multiple times (idempotent). After close, further
operations will trigger a new connection via lazy init.

### SFTP-026: unwrap(SFTPClient)

**Invariant:** `unwrap(paramiko.SFTPClient)` returns the underlying SFTP client.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need paramiko-specific features (per ADR-0003).

### SFTP-027: Idempotent Close

**Invariant:** Calling `close()` multiple times must not raise. Internal state is
set to `None` after close, and the next operation will reconnect lazily.

### SFTP-028: TOFU Host Key Persistence

**Invariant:** When `host_key_policy` is `TRUST_ON_FIRST_USE` and keys are resolved
from the file-based path (not from inline `known_host_keys`, config, or environment),
the backend persists newly accepted host keys to disk on disconnect.

**Preconditions:**

- `_resolved_host_keys` is `None` (no inline keys).
- Policy is `TRUST_ON_FIRST_USE`.

**Postconditions:**

- The known_hosts file (default `~/.ssh/known_hosts` or `host_keys_path`) and its
  parent directory are created if absent, with `0o700` directory / `0o644` file
  permissions (best-effort on Windows).
- `load_host_keys(path)` is always called so paramiko records the filename internally.
- `save_host_keys(path)` is called in `_close_clients()` before SSH client closure.
- On reconnection, keys saved during the previous session are loaded back.
- Save failures are suppressed — they must not prevent connection teardown.
- Inline keys (`known_host_keys` parameter, config dict, or env var) are never
  persisted to disk.

## Concurrency

### SFTP-029: Concurrent-Use Posture

**Invariant:** `SFTPBackend` is `single_connection` (the BE-028 non-default
posture): a single instance drives one paramiko `SFTPClient` over one SSH
channel, which is **not** safe for concurrent use. Concurrent operations on one
instance race on the shared channel and may interleave or corrupt protocol
state.

**Remedy:** Use one instance per thread, or drive it through
`AsyncBackendSyncAdapter` (which funnels concurrent callers onto a single
private loop and serializes them — ASYNC-089). A `single_connection` backend
wrapped by `SyncBackendAdapter` and driven with `asyncio.gather` is **not** safe
(ASYNC-094). This pins the caveat previously stated only in the class docstring
and `docs-src/guides/async.md`.

**See also:** [003-backend-adapter-contract.md](003-backend-adapter-contract.md)
(BE-028), [029-async-store-backend-api.md](029-async-store-backend-api.md)
(ASYNC-094).

---

## Timeouts

### SFTP-030: Channel I/O Timeout

**Invariant:** `timeout` bounds the connect phase only. It is passed to
`ssh.connect()` as `timeout`, `banner_timeout`, `auth_timeout` and
`channel_timeout`; the last bounds how long the client waits for a channel to
*open*, not traffic on an opened one. Blocking I/O on the open channel is
governed by `Channel.timeout`, which paramiko initialises to `None`.

`io_timeout` (default `None`, meaning unbounded — no behaviour change for
callers that do not set it; `0` and negatives raise `ValueError`, see SFTP-005)
is applied via `Channel.settimeout()` in `_connect`, and **every** reconnect
re-arms it on its new channel because it is applied there rather than at
construction.

**It is armed before the SFTP session exists, not after.** `_connect` opens the
channel, arms the bound, then invokes the `sftp` subsystem and constructs the
`SFTPClient`. That order is load-bearing: `SFTPClient.__init__` performs the
SFTP version exchange, which *blocks reading the server's reply* on a channel
`Transport.open_session` hands back with `Channel.timeout` still `None`. Arming
after `ssh.open_sftp()` returns would leave that exchange unbounded — a peer
that completes the SSH handshake and then falls silent hangs there forever,
which is the exact fault this clause exists to bound, reached before the bound
is set. It is not a connect-only edge case: every reconnect re-enters that
window, so the guarantee would be missing precisely for the half-alive peer
that motivates it, and `RetryPolicy` cannot cover it because a hang raises
nothing to retry.

**Semantics:** the bound is on a single blocking operation making no progress,
not on the duration of a transfer. A large file over a slow link is unaffected
however long it takes; a peer that goes silent for longer than `io_timeout`
raises `socket.timeout`. Since it is `settimeout()`, the bound covers writes as
well as reads, and a stalled write reaches it on the receive side like a read
does. The distinct fault it covers is a request that never reaches the server,
as against a reply that never returns.

Note which round-trip a stalled write actually fails on, because it is not the
payload: `write()` issues an existence `stat` on `overwrite=False`, and the file
open is a round-trip on `overwrite=True`, so a client→server stall always fails
before any payload byte is sent. Reaching `SFTPFile.write` with a stall armed
requires a handle opened beforehand — `open_atomic`. Stated because an earlier
revision of this clause explained the write case by `SFTPFile.write` not being
pipelined, an explanation no run behind it had reached.

**Postconditions:** A stalled operation raises `BackendUnavailable`, via the
existing `_is_connection_dead` / `_map_exception` path (SFTP-023), which also
clears the cached client so the next operation reconnects (SFTP-010 tier 2).

The caller-visible wall clock for a stalled operation is one bound, not
several. A failed operation re-enters the channel two ways — to classify the
failure (`_raise_if_dir`, `_has_file_ancestor`) and to release resources — and
each re-entry would pay `io_timeout` again on a client `_map_exception` has not
yet cleared. **Three** mechanisms prevent that, because callers arrive at those
re-entries differently:

1. **A passed cause.** A caller holding a failed operation's exception passes it
   to `_raise_if_dir`, which skips the probe when that exception already
   concludes the connection is dead.
2. **A dead-stat re-raise.** `_raise_if_dir` and `_has_file_ancestor` each
   re-raise a dead-connection error from their own stat rather than swallowing
   it as unclassifiable. This is what covers `read`, whose is-dir check is eager
   and so has no prior exception to pass, and it also fixes a correctness
   residue in `_has_file_ancestor`: swallowing there returned `False`, the
   caller's original error surfaced, and `_map_exception` classified it as a
   generic `RemoteStoreError` — which does *not* clear the cached client, so
   SFTP-010 tier 2 never fired on the operation that surfaced the drop.
3. **Skipped teardown.** `_promote` skips the `rename` fallback, whose `remove`
   + `rename` would each pay the bound again; `write_atomic` and `open_atomic`
   skip their temp cleanup; and `open_atomic` skips the best-effort
   `handle.close()` on an abnormal exit, since paramiko's `SFTPFile.close()`
   issues a synchronous `CMD_CLOSE`. That last one is the worst of the set when
   unguarded, because `contextlib.suppress` makes it a wait with no error to
   explain it. Measured on a streamed write at a 2 s bound: 4.04 s before the
   guard, 2.04 s after.

**Bounded, with two stated exceptions.** Neither is fixed here:

- **The `subsystem` request.** `Channel.invoke_subsystem` waits in
  `Channel._wait_for_event`, a bare `threading.Event.wait()` with no timeout
  argument, which never reads `Channel.timeout`. A peer that opens the session
  channel and then never answers the request hangs regardless of `io_timeout`,
  and every reconnect re-enters that window. Bounding it would mean inlining
  `invoke_subsystem`'s own body — deeper into paramiko internals than the
  `from_transport` copy this clause already accepts — so it is recorded rather
  than taken. Narrower than the version-exchange window that *is* bounded: a
  server that accepts a channel but never answers a channel request is a wedged
  SSH daemon, not a wedged subsystem.
  This exception is **characterised by a test**, not asserted: a server variant
  that parks in its subsystem handler (so no `CHANNEL_SUCCESS` is ever sent)
  leaves the client blocked well past the bound, with the handler's entry
  observed so the block is pinned to the request rather than to an earlier
  handshake step. If that test ever fails, the wait has become bounded and this
  bullet should be deleted with it.
- **Releasing a stream handle.** `_ErrorMappingStream.close` closes the
  underlying paramiko file under `contextlib.suppress`, so exiting the `with`
  block of a stream that has already failed may block once more. The fix belongs
  to the shared stream wrapper rather than to this backend — it serves the S3,
  Azure and HTTP backends too — so it is tracked as BK-355. When BK-355 lands,
  this exception goes.

For a **streamed** read (`read`), a stall after the caller has consumed bytes
raises rather than returning short, so a truncated stream is never
indistinguishable from a complete one. The bytes already delivered are a valid
prefix and the handle is dead: the caller discards it rather than resuming.
This is the premise the retry exclusion below is argued from, so it is stated
here rather than left implied.

**Excluded from retry:** `RetryPolicy` wraps the `ssh.connect()` call alone, not
the whole of `_connect` (SFTP-009), so **no** stall bounded by `io_timeout` is
retried — neither one on a caller's operation nor one in the session setup
described above, which happens inside `_connect` but outside the retried
closure. Every stall reaches the caller.

For an operation-level stall the exclusion is deliberate: retrying
transparently would restart a partially consumed stream underneath a caller
that had already read from it. That rationale does **not** reach a
version-exchange stall, where nothing has been consumed yet, so the exclusion
there is a consequence of where the retry boundary sits rather than a decision
argued on its merits. Recorded as an open question rather than presented as
settled: a session-setup stall is arguably a connect failure and could be
retried like one.

**Rationale:** Without this, a silent peer blocks forever while holding whatever
pooled resource the operation runs on, and emits no signal — while the recovery
machinery for exactly that fault already exists and merely lacks a trigger.
`unwrap(SFTPClient).get_channel().settimeout()` is not a substitute: a
transparent reconnect builds a fresh channel with `timeout=None`, so a
caller-applied bound evaporates precisely after a recovered drop. Keeping the
knob distinct from `timeout` matters because that name already carries four
connect-phase meanings.
