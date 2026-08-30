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
    io_timeout: float | None = 120.0,   # bound on a stalled open channel
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
reads `0` as non-blocking rather than as a bound, and every SFTP request waits
on a reply, so every operation fails at once — writes included, via the
acknowledgement read that follows them. (`settimeout(0)` does not fail an
operation that need not block: paramiko raises only when the read buffer is
empty or the send window is full. Every SFTP operation reaches one of those.)
`None` is therefore the only way to ask for an unbounded channel, and `0` is not
a spelling of it: the two look interchangeable to a caller reaching for
"no limit" from a default that is now a real bound (SFTP-030).
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
SFTP-030's `io_timeout` arms the bound — which it now does by default, so a
merely silent peer reaches this path on a store configured with nothing. A
caller who opts out with `io_timeout=None` puts it back out of reach for that
fault, and the other signals in the set are unaffected either way. Operations
outside the default
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
**The caveat covers a failure before the promote, and only that.** A stall whose
lost reply is the promote `posix_rename` itself leaves the rename *performed* —
the destination holds the new content, no temp remains, and the caller is told
`BackendUnavailable`. So "atomic" here guarantees no reader sees a half-written
file; it does not guarantee that a reported failure means the write did not
happen. Measured, not inferred:
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination)
carries the full table and the derivation.
**Postconditions:** On success, the temp file is gone and the target contains the
new content. On failure, the backend makes a **best-effort** temp-file cleanup that
never reconnects: when the failure is itself a dropped-connection signal (or the
client is already invalidated), the cleanup unlink is deliberately skipped rather
than triggering a fresh connect against a possibly-down server inside the
error-handling path — so the orphan-temp caveat above holds and the original error
propagates without a multi-second reconnect stall. An abnormal exit of an
`open_atomic` block (including a `GeneratorExit` / `KeyboardInterrupt`) removes the
temp file under the same best-effort guard.
**The contrast this caveat is read for** — what plain `write` leaves at the
destination path when it fails the same way — is
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination).
A reader choosing between the two operations is comparing the two, and stating
only this half is what left that choice undecidable.

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

`io_timeout` (default `120.0`; `None` means unbounded and is the opt-out; `0`
and negatives raise `ValueError`, see SFTP-005) is applied via
`Channel.settimeout()` in `_connect`, and **every** reconnect re-arms it on its
new channel because it is applied there rather than at construction.

**Why the default is a bound rather than `None`.** The option shipped defaulting
to `None`, which left the stall it exists to bound unbounded unless a caller
opted in. Two things in this library made that the wrong resting state rather
than a conservative one. `ReadOnlyHttpBackend` already defaults `timeout=30.0`
and that bound reaches reads, so a user met a bounded read on HTTP and an
unbounded one on SFTP with no principle separating them. And the recovery path
below — `_is_connection_dead` → `_map_exception` → cleared client — was written
presuming a bound exists; shipping the machinery without its trigger left the
clause internally contradictory.

**Why `120.0`.** The asymmetry picks it, not a benchmark. Raising the value
costs detection latency only, which is cheap: the bound is on silence *between*
bytes, so a slow link is unaffected at any value. Lowering it converts a
healthy-but-quiet server — an antivirus or dedup appliance scanning a large file
on `open()` — into intermittent `BackendUnavailable`, which reads as network
flakiness and is harder to diagnose than the hang it replaces. So the value is
chosen against the longest *pause* a healthy server is expected to take on one
operation, not against transfer duration — a stall surfaces inside two minutes,
while a server that goes quiet on `open()` of a large file is left room. The
originating issue's transfer times (214 MB in ~20 min, 2.0 GiB in ~70 min) do
not constrain the choice and are not what it was sized against: expressing the
bound as a fraction of them would use exactly the yardstick this clause tells
callers not to use, and no fraction of a transfer time discriminates one silence
bound from another. `120.0` is also the value the SFTP guide and the
troubleshooting page already used in their worked examples before it became the
default, so the value a reader was being shown and the one they got stop
disagreeing. **Both** worked examples have since moved off it, because
illustrating an option with its own default illustrates nothing; the pages state
the default in prose and in the options table instead, which is where a reader
looks for it.

**It is a behaviour change for a caller who sets nothing**, and shipped as one:
an operation that previously blocked forever now raises `BackendUnavailable`
after two minutes of silence. `io_timeout=None` restores the old behaviour.

**The value is restated in prose across the source, this spec, the guides, the
migration entry, the backlog and the tests, and nothing gates that.** The
constructor's signature is the source of the value;
`test_default_arms_the_bound_on_the_channel` pins the constructor against a
literal, so a silent change to the default fails there. No check compares any
prose site to the signature, so that sweep is a reviewer's job.

**No enumeration of those sites is given, deliberately.** A list is the obvious
mitigation and the wrong one: it is a second derived artifact over the same
fact, so it goes stale exactly as the prose does, and a checklist a reader
trusts and that is one entry short is worse than no checklist, because it stops
the search. This clause carried such a list twice and it was short both times.
Derive the set instead — `rg -n 'io_timeout' src docs-src sdd tests`, read the
hits that state a value.

Both halves are registered rather than assumed away.
[`DRIFT-RULES.md` Rule 5](../DRIFT-RULES.md#mandatory-path) asks why the check is
not gating: a gate would have to parse a default out of a signature and match it
against prose in four file formats, while the claim space is one number that
changes about once per major behavioural decision.
[`Rule 6`](../DRIFT-RULES.md#tolerated) asks for an owner and a rationale on what
that leaves tolerated: **owner BK-356**, rationale as above.
[`CONTENT-RULES.md` Rule 5](../CONTENT-RULES.md) is the authority the duplication
actually diverges from — source-code facts stay in source — and the divergence
is narrower than it looks: the options table and the migration entry have to
state values to do their jobs, and what is genuinely tolerated is the narrative
restatements beside them. The cost is real and was paid inside this item's own
review, twice: a derived figure in a test docstring went stale one commit after
review corrected it, and the enumeration this paragraph used to carry was
incomplete when written.

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

The "unaffected however long it takes" half is asserted by
`test_a_transfer_slower_than_the_bound_is_not_interrupted`, which throttles a
relay rather than stalling it — slow, never silent — and asserts both that the
transfer completes intact and that it *outlived* the bound, so it cannot pass by
finishing early. Named here for the reason the silent-close case below is: the
`SFTP-030` marker says a test pins this clause, not which of its claims, and
this is the claim that tells a slow-link caller to change nothing. It was
unexecuted while the default was `None` and load-bearing from the moment the
default became a bound.

Note which round-trip a stalled write fails on, because it depends on *when* the
peer went silent, not on which method was called. A stall already in effect when
the call starts never reaches the payload: `write()` issues an existence `stat`
on `overwrite=False`, and the file open is a round-trip on `overwrite=True`, so
the failure lands there. A stall that begins mid-transfer does reach
`SFTPFile.write`, and `write`, `write_atomic` and `open_atomic` all get there —
any handle that is open when the peer goes quiet will.

The distinction is stated because both halves have been got wrong here. An early
revision explained the pre-armed case by `SFTPFile.write` not being pipelined, an
explanation no run behind it had reached. Its replacement then said reaching
`SFTPFile.write` "requires a handle opened beforehand — `open_atomic`", which
generalised a measurement of the pre-armed case (`SFTPFile.write` entered 0 times)
to every route, and stood while two tests in the suite reached it through plain
`write` and `write_atomic`.

**Postconditions:** A stalled operation *that fails* raises `BackendUnavailable`,
via the existing `_is_connection_dead` / `_map_exception` path (SFTP-023), which
also clears the cached client so the next operation reconnects (SFTP-010 tier 2).

**The qualifier is load-bearing.** Every mechanism below — the classification guards, the handle guard, the
stream wrapper's futile-close guard, and the client invalidation the
Postconditions above promise — is triggered by an exception. A stalled operation
whose failure paramiko *discards* raises nothing, so it reaches none of them: it
neither reports nor clears the cached client, and the next operation therefore
re-enters the same dead channel and pays the bound again.

The case that used to demonstrate this was a `SEEK_END` seek, whose swallowed
size request left the cached client alive for the following operation to
re-enter. It no longer demonstrates it: [SIO-011](006-streaming-io.md) moved
that request into the wrapper, so the seek now raises and clears the client like
any other stalled operation. The demonstrating case is now the silent close
recorded further down, where paramiko's `SFTPFile._close` catches the stalled
`CMD_CLOSE` itself — asserted by
`test_releasing_a_stalled_handle_after_no_failure_is_silent`, which pins all
three halves the qualifier needs: the wait is bounded at one `io_timeout`,
nothing is raised, and the cached client survives. The seek's replacement is a
test, not a paragraph, because a qualifier resting on a figure in prose is one
paramiko release away from being silently unnecessary.

Read the Postconditions as scoped to the failures that surface; the exception
list is not a footnote to them.

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
3. **Skipped teardown.** Every promote-or-rename path skips what follows a dead
   rename: `_promote` skips the `rename` fallback, whose `remove` + `rename`
   would each pay the bound again, and `move` skips its own fallback chain — a
   suppressed `remove`, a `rename`, and the copy fallback's two file opens.
   `write_atomic` and `open_atomic` skip their temp cleanup. And **every**
   paramiko file handle held in a `with` block skips its close on a
   dead-connection exit, since `SFTPFile.close()` flushes and then issues a
   synchronous `CMD_CLOSE` whose reply never comes.

   That last is the worst of the set when unguarded, because paramiko swallows
   the timeout raised inside its own close, making it a wait with no error to
   explain it. The guard is one helper (`_handle`) rather than a per-site
   repeat, because the site that first exposed it was not the only one:
   `read_bytes`, `write`, `write_atomic`, `copy` and `move`'s copy fallback all
   hold a handle the same way, and `open_atomic` applies the same rule inline
   (its clean-exit close must sit inside `_errors` so a flush failure still
   maps). Measured at a 2 s bound, on a stream that goes quiet mid-transfer:
   4.00 s before the guard and 2.00 s after for both `write` and `write_atomic`,
   and 6.9 s before and 2.0 s after for `copy`, which holds two handles rather
   than one.

   Three of the five call sites are measured that way; the other two are named
   here rather than counted as covered, because the helper being shared is not
   evidence that a site was exercised. `read_bytes` prefetches, so a stall inside
   its read fails in paramiko's prefetch machinery rather than on the close of a
   partly-read handle, and a test there would pin something other than what it
   claimed. `move`'s copy fallback (`_copy_and_delete`) is reached only when both
   `posix_rename` and `rename` fail for non-dead reasons, which needs a server
   refusing both, so it carries a `no cover` pragma.

   The distinction is drawn because `copy` shipped unrouted for a round while
   five artifacts named it covered — the call-site list was read as evidence that
   the list had been run. The same reading is what put the pragma on too much
   code twice: first over `move`'s dead-rename guard, then over `_move_fallback`'s
   own, each of which is reachable well outside the case the pragma names. Each
   split moved the pragma down to the method that genuinely needs it, and the two
   guards now have a test apiece.

   The helper bounds what the caller waits inline; it does not promise the
   round-trip is never made. `SFTPFile.__del__` calls `_close(async_=True)`
   unconditionally, and the `BufferedFile.close` inside it — which flushes —
   sits outside `_close`'s own `try`, so a *write* handle still holding buffered
   bytes can attempt one blocking write when it is collected, on whatever thread
   collects it. A read handle cannot: its write buffer is empty and `_write_all`
   returns without a round-trip.

   The `move` guard is a case where a coverage pragma hid a gap: its fallback
   carries `# pragma: no cover -- fallback for servers without posix_rename`,
   which describes the fallback correctly, while the dead-connection guard above
   it is reachable on *any* server, since a stalled channel fails `posix_rename`
   like anything else. The fallback is therefore a separate method
   (`_move_fallback`), so the pragma covers only what it names.

**Bounded, with one stated exception.** It is not fixed here:

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

**Releasing a *streamed-read* handle is bounded by the wrapper, not by
`_handle`.** `read` hands back an `_ErrorMappingStream`, and that wrapper — not
this backend — owns the close, so the guard above cannot reach it; it serves the
S3, Azure and HTTP backends too. The wrapper takes `_is_connection_dead` as its
`is_fatal` predicate and skips a close its own failure has condemned
([SIO-010](006-streaming-io.md)), which is what makes the bound above hold for a
stream as well as for the handles `_handle` covers. Measured at a 2 s bound,
consuming part of a `read()` and then stalling: 4.00 s for the failed reads plus
the close before the guard, 2.00 s after
(`test_releasing_a_stalled_stream_costs_one_bound`).

**A `SEEK_END` seek on that stream is bounded the same way, and only because the
wrapper sizes the handle itself.** `SFTPFile.seek(offset, SEEK_END)` calls
`_get_size()`, whose body is `try: return self.stat().st_size` under a bare
`except: return 0`, so delegating to it discarded the stalled `stat`: the seek
blocked for the bound and then *answered* `0` on a file of any size, arming
nothing and leaving the dead client cached, and the close paid the bound again.
`read` therefore supplies the wrapper a `size_probe`
([SIO-011](006-streaming-io.md)) that issues `CMD_FSTAT` on the open handle and
lets the failure out, which is what brings this seek under the `is_fatal` guard
above. Measured at a 2 s bound: 4.00 s answering `0` on a 1 MiB file with the
client still cached, against 2.00 s raising `BackendUnavailable` with the client
dropped (`test_seek_to_end_on_a_stalled_channel_costs_one_bound`). This was a
stated exception to the bound until that clause landed; it is now an ordinary
bounded operation, which is why the list above holds one bullet rather than two.

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
closure. Every stall that surfaces reaches the caller.

**Not every stall surfaces**, and the exception above is the one worth stating
rather than an exhaustive list of the silent ones: releasing a stalled handle
after no prior failure is silent too, because paramiko's `SFTPFile._close`
catches `(IOError, socket.error)` and a stalled `CMD_CLOSE` arrives as
`socket.timeout`. Measured at a 2 s bound: 2.00 s, nothing raised, no
`remote_store` log record, the dead client still cached
(`test_releasing_a_stalled_handle_after_no_failure_is_silent`; paramiko emits
two DEBUG lines of its own, which are transport chatter rather than a report).
It is listed here rather than as a second exception because it costs one bound
and answers nothing — the one above is stated because it costs more than that,
and the `SEEK_END` seek was stated alongside it for the same reason until
SIO-011 brought its cost down to one bound and gave it something to raise.

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
machinery for exactly that fault already exists. That machinery lacked a trigger
for as long as the default was `None`; arming it on every store is what the
default above is for.
`unwrap(SFTPClient).get_channel().settimeout()` is not a substitute: a
transparent reconnect builds a fresh channel with `timeout=None`, so a
caller-applied bound evaporates precisely after a recovered drop. Keeping the
knob distinct from `timeout` matters because that name already carries four
connect-phase meanings.

<a id="stalled-write-destination"></a>
#### What a stalled operation leaves behind

Everything above says when a stalled operation *fails*. This says what it leaves
behind, which is a separate question and was undocumented while the clause above
was not — the gap BK-360 closes.

**A timeout reports one round-trip's lost reply.** `io_timeout` fires on a
receive that made no progress, so what the caller learns is that no answer came
back for the request outstanding at that moment — never that the request failed
to arrive. Two things follow, and the second is the one two review rounds of
this clause each got wrong:

- **Everything the operation did *before* that round-trip already happened.**
  Those replies came back; the silence started later. A stall in a write's body
  has already truncated the destination on the open, whichever direction goes
  quiet.
- **For the round-trip itself, the direction decides.** Client→server silenced,
  the request never arrived and it did not happen. Server→client silenced, the
  server performed it and only the answer was lost.

**A caller can observe neither**, and while BK-359 stands the raised
`BackendUnavailable` carries no message to help. So several operations below have
a state in which they did what they were asked and reported failure anyway.

Applying that to each operation's round-trips gives the reachable residue. The
source of a `copy` is never affected and is omitted:

| operation | reachable residue at the destination |
| --- | --- |
| `write` | **untouched** · **absent** · **empty** (the open truncated it; the old content is gone and nothing replaced it) · **a prefix** |
| `copy` | the same four; a pre-armed stall dies on the source `stat`, so `empty` needs the silence to begin at the destination open |
| `move` | **untouched** · **absent** · **the move completed** (source gone) · **the destination destroyed while the source survives** — fallback servers only |
| `write_atomic` / `open_atomic` | **untouched** or **absent**, usually with an orphan temp · **the write completed**, no temp · **the destination destroyed with the payload stranded in the temp** — fallback servers only |

Five consequences follow, and each is why the table is here rather than left to
a reader's inference.

**Reported failure does not mean unchanged.** For `move` and the atomic writes
the *whole* operation can succeed and then raise: a caller that reruns a failed
`move` meets `NotFound` on a source that is already gone.

**The old content is not safe on the non-atomic path.** The `empty` residue
destroys a pre-existing file and replaces it with nothing.

**`write_atomic` is the escape, and its bound is the promote.** Its `untouched`
residue is what the capability is bought for, and it holds against a failure in
the body — not against a lost promote reply, and not on a server without
`posix-rename@openssh.com`.

**The last row of each fallback line is the worst state here**, and it is
`_rename_fallback` / `_move_fallback`: those remove the destination and then
rename onto it, so a silence beginning at the `rename` leaves the destination
gone with nothing put in its place. It is pre-existing behaviour rather than
anything this clause introduced, it is reachable only on a server lacking
`posix-rename@openssh.com`, and it is tracked as **BUG-264** along with the
second `io_timeout` bound it costs — the suppressed `remove` swallows its own
timeout, which the one-bound paragraph above does not currently allow for.

**The prefix is not a resume point.** Its length is a function of the chunk size
and the SSH window, not of anything the caller controls or is told, so a caller
that seeks past it and appends will corrupt the file. Discard and re-write. This
is the same conclusion the streamed-read paragraph above reaches from the other
side of the transfer, and for the same reason.

**Which round-trip a stall *reaches* is a separate question from what that
round-trip does.** The `empty` residue belongs to the open at any depth; but a
stall already in effect when the call starts lands on the *first* round-trip the
operation makes, and `_ensure_parent_dirs` stats every ancestor before the open.
So a pre-armed stall reaches a `write`'s open only for a root-level target — at
any nesting an ancestor `stat` absorbs it and the destination survives. Both
halves are pinned, at depth 0 and depth 1, so the bound cannot be re-encoded
accidentally by a fixture that happens to use bare filenames.

In every row, parent directories `_ensure_parent_dirs` created on the way in
remain behind — a failed write is not a rollback.

**Derivation, and why it is an enumeration rather than an argument.** Two
successive revisions of this clause each proposed a *scope criterion* for the
residue — first "which method was called", then "which direction was silenced" —
and each was refuted in review by a state the argument had not considered. A
third reading is not more likely to be exhaustive than the first two, so the
condition space was parametrised and generated instead: operation x the
round-trip at which silence begins x direction x `overwrite` x whether the
destination pre-existed x whether the server offers `posix-rename@openssh.com`.
**164 combinations ran and 156 were pruned as unreachable**, every one against a
real silent peer through the `_StallRelay` harness, with the destination read
back through a second backend wired straight to the server rather than through
the condemned channel, and with the raised type recorded per case so that a
combination where no stall fired could not be mistaken for a residue
measurement. Those counts are the harness's own totals from that run. The
enumeration is not itself in the suite — it costs minutes, and its value was in
producing this table once. What ships is a spanning subset, one case per distinct
residue state, in
`test_stalled_write_leaves_one_of_four_destination_states`,
`test_stalled_copy_leaves_a_prefix_at_the_destination_too`,
`test_a_lost_reply_can_complete_the_operation_it_reports_as_failed` and
`test_a_stalled_atomic_write_preserves_the_destination_and_leaves_an_orphan_temp`
in `tests/backends/sftp/test_io_timeout.py`. Byte counts are deliberately absent:
the prefix length moves with the chunk size and the window, so a figure would be
a derived artifact going stale exactly as the enumeration this clause already
declines to keep does. The tests assert the *shape* — a strictly partial prefix —
for the same reason.

**This clause amends [SFTP-014](#sftp-014-atomic-write-simulated)'s caveat
rather than merely citing it.** That caveat's "the destination is untouched"
holds for a failure *before* the promote and is false both for a lost promote
reply and on the fallback path, which was found by running the contrast this
clause is stated against instead of quoting it.
