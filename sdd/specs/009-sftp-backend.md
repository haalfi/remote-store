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
**The destination is untouched only for a failure before the promote**, and that
half was previously unstated here — a reader took it from the word "atomic"
rather than from any clause, which is why it is written down now with its bound.
Two failures fall outside it. A stall whose lost reply is the promote
`posix_rename` itself leaves the rename *performed*: the destination holds the
new content, no temp remains, and the caller is told `BackendUnavailable`. And
the `_rename_fallback` path — entered when `posix_rename` raises an `OSError`
that `_is_connection_dead` does not recognise and `_raise_if_dir` has not
rejected the target, so not only on servers lacking the extension — cannot rename
onto an occupied path, so it displaces the destination to
`.~bak.<name>.<uuid8>` first and renames it back if the promote fails. Renaming
it back is best-effort, so a stall in that window leaves the destination path
empty with its old content in the backup and the payload in the temp — one row of
[§ Where the caller's previous file ends up](#where-the-previous-file-is), which
enumerates the rest rather than leaving a reader to infer the scope from this
sentence.
So "atomic" here guarantees no reader sees a half-written file; it guarantees
neither that a reported failure means the write did not happen, nor that the
destination path is still occupied — only that what occupied it is still
somewhere. Measured, not inferred:
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination)
carries the closure, the named states and the derivation.
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
**On success.** A failure can leave it replaced, unchanged, or displaced to
`.~bak.<name>.<uuid8>` with the destination path empty — see
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination).
The displaced case is the one this invariant reads as excluding, and which
failures reach it is enumerated at
[§ Where the caller's previous file ends up](#where-the-previous-file-is) rather
than scoped here. What no row does is leave the caller without the file, which is
the guarantee AW-003 states cross-backend and the reason the displace takes a
backup rather than deleting.

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
**On failure**, see
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination):
a reported failure may mean the move was performed, and over a dropped
connection the fallback path can leave the destination path empty with its old
content displaced to `.~bak.<name>.<uuid8>`. On a live connection a failed
`rename` is not reported at all — the copy rung answers it, which is the third
rung of this invariant — and a failure of *that* rung has a destination to give
back: the copy opens it before it can fail, so the restore clears the path before
renaming the backup onto it rather than assuming it free. Whether the caller gets
it back is the restore's own best-effort question, above. A destination the
fallback could not clear at all is never written: the displace propagates its
refusal instead of reporting nothing to restore, which is what kept the copy rung
from truncating a file it had no backup for.

### SFTP-019: Copy Via Read + Write

**Invariant:** `copy(src, dst)` reads the source file and writes it to the destination.
There is no server-side copy operation in SFTP — data passes through the client.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and
`overwrite=False`.
**On failure**, the destination is written non-atomically and can hold any prefix
of the source, up to and including all of it — see
[SFTP-030 § What a stalled operation leaves behind](#stalled-write-destination).
The source is never affected.

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
So, finally, are the signals that say the host was **never reached**:
`paramiko.NoValidConnectionsError` (an `OSError` whose `errno` is `None`, which
is what a refused port actually raises), `socket.gaierror` (name resolution), and
an `OSError` carrying a connect-side errno (`ECONNREFUSED` / `EHOSTUNREACH` /
`ENETUNREACH` / `ENETDOWN` / `EHOSTDOWN`). Three of those five are the ordinary
path rather than a fallback: `SSHClient.connect` captures only `ECONNREFUSED`
and `EHOSTUNREACH` into `NoValidConnectionsError` and re-raises every other
`socket.error` unwrapped, so `ENETUNREACH` / `ENETDOWN` / `EHOSTDOWN` arrive as
a plain `OSError`.

These are a *connect-time* set and sit in their own arm rather than joining the
dropped-connection set above, **because the two predicates answer different
questions** — was the host ever reached, versus is a connection the backend had
now unusable.

**No claim is made about what is reachable when, and the omission is the
clause.** Three rationales of that kind were written for this split and each was
refuted by a state it had not considered: that no operation is in flight at
connect time (a connect that times out raises `socket.timeout`, which the
dropped-connection predicate already matches); that the `is_fatal` and re-entry
guards are never consulted on the connect path (they are — `read`, `read_bytes`
and `delete` evaluate the lazy `_sftp` property inside their own `try`, so a
failure raised by `_connect` reaches them); and that the shapes partition by
phase at all. A fourth reading is not more likely to be exhaustive than the
first three, so the condition's space is enumerated instead of argued:
`TestSFTPConnectTimePredicateSpace` generates the product of connect-time shape
and operation and asserts, per cell, that the caller gets `BackendUnavailable`
with a non-empty message and one `op="error_mapping"` record. Which predicate
claims a shape is therefore an implementation detail, which is the only footing
on which this split has survived review. The client-clearing invariant below is
pinned separately, by `test_a_host_never_reached_maps_to_backend_unavailable`,
which seeds a sentinel first — a per-cell assertion could not reach it, since
the client is `None` on entry to every cell.

**An operation against a host that was never reached enters `_connect` exactly
once**, whatever the operation and whichever connect-time shape occurred. The
guards those refuted rationales are about ask a third question — will another
round-trip buy anything — so they consult both predicates rather than the
dropped-connection one alone. A guard asking only the latter declines for every
shape the connect-time set claims, and control then falls through to a
classification path that re-evaluates the lazy `_sftp` property and pays the
whole `RetryPolicy` budget (SFTP-009) again. Measured over the product of shape
and operation before this held: 22 of 84 cells entered `_connect` two or three
times — 111 entries where 84 were owed — and **five** operations paid them:
`read`, `read_seekable` (which delegates to `read`), `read_bytes`, `delete`
(including `missing_ok=True`) and `write(overwrite=True)`. Every other operation
entered `_connect` once before this clause held and still does, which is why the
enumeration carries them as controls rather than as coverage padding.

**The third cycle is the file-ancestor walk**, so it is reached only when the
shape's `errno` is `None` — the refused-port case — and only on the four
read-and-delete operations, where a nested key therefore costs three against a
refused port and two against a DNS failure. `write(overwrite=True)` does **not**
follow that pattern and is the instructive exception: `_ensure_parent_dirs` runs
ahead of `_open_write`, so for a nested key it issues the first request and the
connect failure never reaches `_open_write`'s classification path at all.
Nesting makes that operation *cheaper* — one cycle against two for a flat key —
and the walk is never on its path.

At shipped defaults, warm-up discarded and both revisions timed on one machine:
a flat `read_bytes` against a refused port went from 8.00 s to 4.00 s and a
nested one from 12.00 s to 4.00 s, while `check_health` and `exists` cost 4.00 s
on both sides — one budget before and after, since neither has a re-entry guard
to decline.

`TestSFTPUnreachableHostCostsOneConnect` pins one entry per cell, over **every
operation that reaches the backend** rather than a sample, which is what makes
the "whatever the operation" above a measured claim rather than a generalisation
from the five that moved.

**The clause's subject is load-bearing: a host that was never reached.** It says
nothing about a transport that dies *mid-operation* and then fails to reconnect,
which reaches guards this clause does not cover and costs up to three budgets —
tracked as BUG-278, with the measurement. Every cell here builds a fresh backend
whose first `_sftp` evaluation fails, so the enumeration cannot reach that shape
and must not be read as ruling it out.

The clause is about the *budget*, not about probe counts: how many round-trips a
classification path would have made is the operation's own business, and the
enumeration above deliberately pins neither that nor which predicate claimed a
shape.

Every other `OSError` the errno dispatch declines keeps the base
`RemoteStoreError` — `EIO` and `ENOSPC` are faults of a connection that is
working.

**The two permission errnos are known exclusions rather than oversights**, and
one reason covers both: this mapping sees only the exception, so it cannot tell
a connect-time errno from a live-channel one. paramiko re-raises `EACCES` and
`EPERM` unwrapped like `ENETUNREACH` / `ENETDOWN` / `EHOSTDOWN`, and what each
then reaches differs:

- `EACCES` takes the `EACCES` arm and is answered `PermissionDenied` — naming
  the caller's key on a keyed operation, and a bare `Permission denied: ` on
  `check_health`. **Whether any connect produces it is unestablished**; BUG-273
  records the trigger as unknown, so this is what would happen and not a
  behaviour a reader can currently observe.
- `EPERM` has no arm at all and falls to the generic one as the base
  `RemoteStoreError`. This is the local rejection that *is* reproducible — a
  netfilter `REJECT` on the `OUTPUT` chain yields it — so it is the shape a
  reader meets, and it is BUG-265's own defect surviving in the errno the
  connect-time set does not claim. **BUG-273 carries this half** — a fix needs
  the connect-time context, which only `_connect` has. BUG-275 carries the
  absent `EPERM` arm itself, an older live-channel defect and the reason the
  fall-through lands where it does; it would change this shape's answer from
  the base class to `PermissionDenied`, which is still not the promised type.

Neither is claimed here because `_raise_if_dir`'s permission re-raise
deliberately passes **both** back through this mapping from a working channel,
so claiming either would answer a server-reported denial with
`BackendUnavailable` and discard a healthy client. BUG-273 carries that
exclusion for both.

**Every** `BackendUnavailable` this mapping returns — the `SSHException` family
included — invalidates the cached SFTP client so the next operation reconnects
(see SFTP-010, tier 2). The list is not the guarantee: recovery is anchored to
the `BackendUnavailable` *conclusion*, so a dead-connection signal the list has
not enumerated still clears the client rather than wedging the backend. One
exception keeps its own branch first: `IncompatiblePeer` (a connect-time
`SSHException`) is mapped with a diagnostic hint before the generic `SSHException`
mapping, so the hint is not lost.

**Every `BackendUnavailable` this mapping *constructs* carries a non-empty
message, and emits exactly one `WARNING` record.** Both halves are one method's
job (`_unavailable`), which is why they are stated in one clause: the arms that
could disagree are the same arms. *Constructs*, not *returns* — the mapping's
first arm passes a `RemoteStoreError` it was handed straight back, so a
`BackendUnavailable` built elsewhere and fed in carries neither guarantee. Only
one such object exists (`_open_sftp_bounded`'s direct raise, unreachable in
practice), so this is a bound on the clause rather than a live gap.

**"One record" is a claim about this mapping, not about the logger**, and the
distinction is load-bearing for the reader most likely to rely on it — someone
grepping their own logs. `remote_store.backends._sftp` carries other `WARNING`
records: `_connect` builds its tenacity retry with
`before_sleep_log(log, logging.WARNING)` on that same logger, so a connect that
exhausts its `stop_after_attempt` budget emits one per sleep, and `AUTO_ADD`
warns once per connect. A failed operation is therefore not a one-line event on
the logger; it is a one-line event per concluded mapping. A reader searching for
the mapping's record matches `op="error_mapping"` in the structured `extra`,
which the retry and policy records do not carry.

**No total is given, deliberately.** How many records a failure leaves on that
logger is a product of the retry policy's `max_attempts`, the host-key policy,
and which failure shape occurred — and a stated total is one cell of that
product presented as the whole of it. Three review rounds each refuted a
different cell written as a total here: "one WARNING on the logger", then
"three at the default policy" (three is the `AUTO_ADD` figure; the default is
`STRICT`), then "two per poll" (which assumes the default `max_attempts`).
Derive it for a configuration if you need it; do not restate it as a constant.

The message is the driver's own whenever the driver has one. Four of the signals
above — counting the `SSHException` family and the dropped-connection set, not
the unreachable-host set the paragraph after this one carves out — reach the
mapping with no arguments: `TimeoutError` (which `socket.timeout`
is), `EOFError`, `SFTPError` and a bare `SSHException`. For those
`BackendUnavailable(str(exc))` carried the empty string, which
[ERR-009](005-error-model.md) forbids and which no reader can act on. **"The
signals above" is this clause's own list**, which opens with the `SSHException`
family; it is deliberately not `_is_connection_dead`'s set, which excludes that
family and would therefore hold only three of the four. A stall
names the fault and the bound that fired (`io_timeout=<value>s`), and names no
bound when `io_timeout is None`, since a half-open socket reaches this arm with
the option off and claiming a limit the caller never set would be false. The
others name the signal's own class. A signal that *did* explain itself is never
overwritten: this is a fallback for silence, not a house style for messages.

Two kinds of arm depart from "the driver's own message whenever it has one" —
the `IncompatiblePeer` arms, which append a remediation hint, and the
unreachable-host arm, which supplies a message where the driver's answers the
wrong question.

**What each connect failure actually names, since no arm makes it uniform:**

| Failure | Message | Names |
|---|---|---|
| Refused / unreachable via `NoValidConnectionsError` | paramiko's own text | the **resolved address** and port |
| DNS | supplied by this arm | the configured host |
| `ENETUNREACH` / `ENETDOWN` / `EHOSTDOWN` | the driver's `[Errno n] strerror` | — |
| Connect timeout | `_is_connection_dead`'s arm, `"timed out"` | — |

**Note the first row's subject.** `NoValidConnectionsError` builds its text from
the addresses it tried, not from the hostname it was given, so a store
configured as `files.example.com` reports `Unable to connect to port 22 on
10.0.0.4`. It does **not** name the configured host, which is why the DNS arm
supplies its own message rather than deferring to the driver the way the refused
arm does: the driver names *enough* there — an address and a port a reader can
act on — where a `gaierror` names nothing at all.

The bottom two rows name neither host nor port. That is stated rather than
fixed, because narrowing it would mean re-partitioning the predicates, which is
the thing this section declines to do.

The arm also covers its own blank cases — **both** of them, the
resolution branch and the errno branch — rather than falling through, because
the generic fallback reports a connection *lost*, which is the wrong sentence
for one that was never made. Neither blank shape is raised by anything today:
an `OSError` built with an errno renders as `[Errno n] strerror`, and the
resolver always supplies text. They are guards, stated here because they are
pinned by tests and so remain checkable, not because a caller will observe them.

The record is emitted where the *conclusion* is reached rather than at each raise
site, so the cleanup and classification paths that re-enter the mapping do not
multiply one failure into several lines. That is asserted where the
multiplication could actually happen rather than where it is easiest to assert:
`copy` holds two handles and runs two mapped operations, and `open_atomic` maps
inside `_errors()` and then re-enters its own handler with the mapped error.
Both are pinned against the live stall relay
(`test_copy_stalling_mid_stream_costs_one_bound`,
`test_stall_during_streamed_write_costs_one_bound`); a read, which classifies
once and stops, cannot show it.

`check_health` maps through here, so a probe that fails **in a way this mapping
concludes on** logs one record and a `Store.ping()` poll repeats it. That now
includes the canonical down-server cases: until BUG-265 a refused connect and a
DNS failure raised the base `RemoteStoreError` from the generic `OSError` arm
without reaching `_unavailable` at all, contradicting `check_health`'s own
docstring, and they logged nothing from the mapping. Both now conclude here, so
a poll against a host that is not there leaves an `op="error_mapping"` record
where it left none — a change in log volume as well as in exception type. It is
still narrower than "a poll against a down server": a probe that fails at the
errno arms (a base path that is missing or denied on a server that answered)
logs nothing, because that is an answer rather than a fault.

**Which real-world failures land on which arm is not enumerated here**, and the
omission is deliberate. The arms are stated above by exception *type*, which is
what this mapping actually dispatches on and what the tests pin; the map from a
failure a reader can observe (a refused port, a wedged daemon, a rejected
credential) onto those types is a second question with its own axes, and four
successive attempts to summarise it in one sentence were each refuted by
measurement — the last of them, "only a probe that fails by timeout reaches
it", by a bad SSH banner, an accept-then-hangup and an auth failure, all three
of which reach `_unavailable` through the `SSHException` arm. BUG-266 carries
that table, to be written once against a parametrised test rather than as
prose.

The record carries the path it was mapped with, and omits the key entirely when
there is none — so a `check_health` record has no `path` at all rather than
`path=''`, in either the structured `extra` or the rendered line
(`test_a_probe_record_carries_no_path`). A routine errno is **not** logged: a
missing or denied path is an answer, not a fault.

### SFTP-024: No Native Exception Leakage

**Invariant:** No paramiko, socket, or OS exception raised *by the backend* — an
operation's own I/O, including `open_atomic`'s temp-file open, the caller-facing
handle's flush/close, the promote, and **reads from the stream `read()` returns**
— propagates to callers; all are mapped to `remote_store` error types per
BE-021. The only non-mapped exceptions are those the **caller** raises inside an
`open_atomic` yield block (their `with` body) that are not themselves
dead-connection signals: those are not the backend's and propagate unchanged,
leaving the target untouched. `open_atomic` distinguishes by scope — the temp
open, flush, and promote run inside `_errors()`, while the yielded write does
not; a dead-connection signal surfacing from that write is still mapped to
`BackendUnavailable` (it is indistinguishable from a real drop).
**Postconditions:** `backend` attribute is set to `"sftp"` on all mapped errors.

**The streamed read is the clause's hardest half, and was its longest-standing
breach.** A caller reads long after `_errors()` has exited, so nothing in this
backend is on the stack: `_ErrorMappingStream` is the whole mechanism, and it is
shared with five other backends. It caught `(OSError, EOFError)` only, which a
dropped connection is outside — paramiko converts the underlying `EOFError` to
`SSHException` before the wrapper sees it — so the ordinary mid-read drop
reached callers as a raw paramiko exception while the same drop on `read_bytes`
mapped correctly (BK-358, closed by
[SIO-012](006-streaming-io.md#sio-012-the-set-of-exception-shapes-a-stream-maps),
which is what `read()` supplies its paramiko shapes through). The general lesson
is worth more than the instance: this invariant is stated over the backend, and
the surface where it is hardest to hold is the one the backend has already
handed away.

**On that surface this clause is a goal rather than a description, and the
difference is worth stating** now that the clause names it. Every other surface
here runs inside `_errors()`, which catches `Exception` — the universal is what
the code does. The streamed handle is bounded instead by a set the backend
supplies ([SIO-012](006-streaming-io.md#sio-012-the-set-of-exception-shapes-a-stream-maps)),
and that set is only as wide as the shapes its transport has been *measured* to
raise. A shape outside it is therefore a **breach of this clause**, to be closed
by widening the supplied set, and not an exemption from it. BK-358 was exactly
that breach; the clause is what makes the next one findable rather than
arguable. SIO-010 states the same asymmetry from the other side, over the class
of shapes that escape rather than over the set that catches them.

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

**The two are distinct faults and the caller cannot tell them apart**, which is
worth stating now that the raised error carries a message (SFTP-023) and a
reader might reasonably assume it says which. It does not. Measured against the
stall relay in both directions at `io_timeout=2.0`, silencing server→client and
then client→server: one identical message,
`"SFTP channel stalled: no data within io_timeout=2.0s"`, and a `TimeoutError`
context in both. Both arrive on the receive side, so they enter the same arm and
nothing downstream of it knows which direction fell silent. A message that names
the *fault* is not a message that names its *side*, and only the first is
claimed.

Asserted on both halves, which is the point: `test_a_stall_says_what_it_was_and_logs_it`
drives the server→client stall and
`test_stalled_upload_request_raises_backend_unavailable` the client→server one,
and each pins the same literal message and a `TimeoutError` context. Pinning
only the download half would leave the claim resting on the direction a reader
is least likely to doubt.

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
the call starts never reaches the payload: it lands on whichever round-trip the
operation issues first. For `write` that is the existence `stat` on
`overwrite=False`; on `overwrite=True` it is the first ancestor `stat`
`_ensure_parent_dirs` issues, and only for a **root-level** target — which has no
ancestors to probe — is it the file open. (An earlier revision said the open
unconditionally, which is true only at depth 0; the residue subsection below
turns on that distinction.) A stall that begins mid-transfer does reach
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
The error names the stall and the bound that fired, and the mapping emits one
`WARNING` record — both per SFTP-023, which owns those clauses for every signal
rather than for this one. Named here anyway because the stall is the case a
caller who configured nothing now meets: while the message was empty, this
Postcondition was satisfied by an error that said nothing whatever about what
had failed, and the two artifacts that tell an upgrading user what to expect
(the troubleshooting page, the migration entry) had nothing to point them at.

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
several. **The one exception this clause used to carry is closed** (BUG-270): the
fallback opened with a `remove` under `contextlib.suppress(OSError)`, so a
silence beginning there was swallowed and the following `rename` re-entered the
same channel — 4.00 s at a 2.0 s bound, reached directly by `move`, which has no
`_raise_if_dir` step between the failed `posix_rename` and its fallback, and by
the promote path only when the silence began at that `remove` rather than at the
classification stat. `_displace` re-raises a dead-connection failure instead of
suppressing it, which is mechanism 2 below covering the round-trip that was
outside it. Measured after the change: 2.13 s (`move`), 2.11 s (`write_atomic`),
by `pytest tests/backends/sftp/test_io_timeout.py -k pays_one_bound
--durations=0`.

**That derivation reaches one shape of drop, and the guard has to cover two.**
The measurement stages a stall, so what it fires on is a `socket.timeout` /
`TimeoutError` — matched by `_is_connection_dead`. An EOF drop arrives as
`paramiko.SSHException`, which that predicate **deliberately excludes**, so
every guard on this path is written to reach it another way: `_displace` needs
no arm at all, since an `SSHException` is not an `OSError` and never reaches its
`except`; `_restore` carries the `or isinstance(exc, paramiko.SSHException)`
clause verbatim from the two temp-cleanup sites; and `_release`, which has no
exception to test, asks the transport instead. Stated because the figure above
cannot be read as covering the shape it could not raise.

The two-route detail is kept because it is what the guard's placement turns on:
an earlier revision attributed the 4.00 s to the promote path under the first
antecedent, where it was 2.00 s, and a guard written from that reading would have
gone in the wrong method.

A failed operation re-enters the channel two ways — to classify the
failure (`_raise_if_dir`, `_has_file_ancestor`) and to release resources — and
each re-entry would pay `io_timeout` again on a client `_map_exception` has not
yet cleared. **Three** mechanisms prevent that, because callers arrive at those
re-entries differently:

1. **A passed cause.** A caller holding a failed operation's exception passes it
   to `_raise_if_dir`, which skips the probe when that exception already
   concludes the connection is dead.
2. **A dead round-trip re-raise.** `_raise_if_dir`, `_has_file_ancestor` and
   `_displace` each re-raise a dead-connection error from their own request
   rather than swallowing it — as unclassifiable in the first two, as a
   destination that was not there in the third. This is what covers `read`, whose is-dir check is eager
   and so has no prior exception to pass, and it also fixes a correctness
   residue in `_has_file_ancestor`: swallowing there returned `False`, the
   caller's original error surfaced, and `_map_exception` classified it as a
   generic `RemoteStoreError` — which does *not* clear the cached client, so
   SFTP-010 tier 2 never fired on the operation that surfaced the drop.
3. **Skipped teardown.** Every promote-or-rename path skips what follows a dead
   rename: `_promote` skips the fallback and `move` skips its own fallback chain.
   **Each saves one bound, not the chain's length** — the displace re-raises a
   dead-connection failure, so the `rename` behind it and the copy fallback's two
   file opens are unreachable anyway; the displace is the round-trip that would
   otherwise be paid. **The chains were never worth their length**, and the
   figures are measured on both sides rather than inferred from the code shape:
   removing each guard costs 1 further round-trip at this head, and 2 against the
   base implementations (`remove` + `rename`) — never the 3 and 4 an earlier
   revision of this clause and its two source comments claimed, because
   `_raise_if_dir`'s cause-skip predates this change and `_move_fallback`'s own
   inner guard already stopped the copy rung. `write_atomic` and
   `open_atomic` skip their temp cleanup, and `_restore` skips putting a
   displaced destination back — on the temp cleanup's own predicate, the one
   that adds `SSHException` to this list's first clause — which is why that
   residue keeps its backup. And **every**
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
   `posix_rename` and `rename` fail for non-dead reasons; its handles are
   exercised, but never against a stall, because a dead channel stops the ladder
   a rung above them.

   The distinction is drawn because `copy` shipped unrouted for a round while
   five artifacts named it covered — the call-site list was read as evidence that
   the list had been run. The same reading is what put a `no cover` pragma on too
   much code twice: first over `move`'s dead-rename guard, then over
   `_move_fallback`'s own, each of which is reachable well outside the case the
   pragma named. Each split moved the pragma down a level; what finally removed
   it was staging the refusal client-side, which reaches every rung on a live
   connection. Both guards have a test apiece.

   The helper bounds what the caller waits inline; it does not promise the
   round-trip is never made. `SFTPFile.__del__` calls `_close(async_=True)`
   unconditionally, and the `BufferedFile.close` inside it — which flushes —
   sits outside `_close`'s own `try`, so a *write* handle still holding buffered
   bytes can attempt one blocking write when it is collected, on whatever thread
   collects it. A read handle cannot: its write buffer is empty and `_write_all`
   returns without a round-trip.

   The `move` guard is a case where a coverage pragma hid a gap. A
   `# pragma: no cover -- fallback for servers without posix_rename` sat on
   `_rename_fallback` and named a bound that does not hold: the residue
   subsection below establishes that neither fallback is confined to servers
   lacking the extension. What the gap was: the dead-connection guard above it is
   reachable on *any* server, since a stalled channel fails `posix_rename` like
   anything else. Splitting `_move_fallback` out is what stopped the pragma
   covering that guard; the pragma itself is gone, because denying the promote on
   a live connection reaches both fallbacks and the copy rung below them
   (`tests/backends/sftp/test_atomic_fallback.py`). A pragma whose stated bound
   is wrong is the shape to look for here, not the pragma.

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

**The same holds for a *drop*, and that was an open question rather than an
assumption.** A stall and a drop reach the caller by different mechanisms — a
stall is a receive timeout this bound produces, a drop is an EOF that raises at
once and trips no bound — so the claim above did not carry over, and BK-358
recorded the doubt: a send-side `EOFError` *is* swallowed by
`BufferedFile.read` into a short read before the wrapper sees it, and whether the
receive side did the same was unmeasured. It does not.
`test_a_dropped_stream_raises_rather_than_truncating` drives a relay that closes
the connection mid-transfer and asserts that the read raises rather than
returning what it has, and that the prefix delivered before the drop is a valid
prefix of the payload. It does not inspect bytes delivered *across* the drop:
that staging delivers none, because it tears the connection down on the reply
the client is already blocked waiting for, so the first read after it raises
before any byte arrives. The no-short-read half rests on the raise — had the
drop landed after the last byte, the drain would have returned cleanly. A drop is otherwise outside this clause's subject, which is what
`io_timeout` bounds; it is named here only because this one sentence is about
truncation rather than about the bound, and truncation does not care which fault
ended the transfer.

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

**A caller can observe neither**, and this clause rests on that. The
two-directions paragraph earlier in SFTP-030 measures it: silencing server→client
and client→server produce one identical message and one identical context, so the
error names the *fault* and not the *side*. The message therefore tells a reader
why the operation failed, and no message could tell them what the server did with
the request before falling silent, because the client never learns it.

**What that entails, and this is the whole of it: the residue is any prefix of
the operation's effects, up to and including all of them.** An operation is a
sequence of round-trips. The silence cuts that sequence at some point; everything
before the cut has happened, the cut round-trip has happened or not according to
direction, and nothing after it has. Every reachable state is the result of
running some initial segment of the operation — including the empty segment
(nothing happened) and the **complete** one (the operation was performed in full
and then reported failure).

**The closure is stated instead of an exhaustive state list because three
successive attempts at such a list were each caught short**, the third being a
generated enumeration built specifically to end the problem. It missed a
`write` whose silence falls on its *last* body acknowledgement, which leaves the
destination holding the payload entire. That is not an exotic case and it was
inside the declared condition space; the enumeration simply had no moment for
it. A fourth list would be a fourth thing to catch short, whereas the closure
above cannot be: it is a property of the mechanism rather than a survey of its
outputs.

So the states below are **named illustrations, not an enumeration**. They are the
ones with a test behind them and the ones a reader is most likely to meet; a
state absent from this list is not thereby unreachable. The source of a `copy` is
never affected and is omitted.

| operation | states named here |
| --- | --- |
| `write` | **untouched** · **absent** · **empty** (the open truncated it; the old content is gone and nothing replaced it) · **a prefix** · **complete** (every byte written, the final acknowledgement lost) |
| `copy` | the same five at `dst`; a pre-armed stall dies on the source `stat`, so `empty` needs the silence to begin at the destination open |
| `move` | **untouched** · **absent** · **the move completed** (source gone) · **the destination path empty, its old content in a `.~bak.<name>.<uuid8>`, the source still there** — fallback path only |
| `write_atomic` / `open_atomic` | **untouched** or **absent**, usually with an orphan temp · **the write completed**, no temp · **the destination path empty, its old content in a `.~bak.<name>.<uuid8>` and the payload in the temp** — fallback path only |

Seven consequences follow, and each is why the closure and its illustrations are
here rather than left to a reader's inference.

**Reported failure does not mean unchanged, and does not mean incomplete.**
Every operation here has a state in which it was performed in full and then
raised: a caller that reruns a failed `move` meets `NotFound` on a source that is
already gone, and one that reruns a failed `write` may be overwriting a file that
is already correct.

**The old content is not safe on the non-atomic path.** The `empty` residue
destroys a pre-existing file and replaces it with nothing.

**`write_atomic` is the escape, and its bound is the promote.** Its `untouched`
residue is what the capability is bought for, and it holds against a failure in
the body — not against a lost promote reply, and not on the fallback path.

**The fallback path is the worst state here**, and it is `_rename_fallback` /
`_move_fallback`: those displace the destination and then rename onto it, so a
silence beginning at the promote `rename` leaves the destination path empty. What
is at stake there is which copies survive, not whether the path is occupied.
Before BUG-272 the displace was a `remove` and this residue had no old content in
it at all — on a *non-dead* failure the same window also ran the temp cleanup,
and neither copy remained.
**It is not confined to servers lacking `posix-rename@openssh.com`.**
The route in is a `posix_rename` failure that `_is_connection_dead` does not
recognise, on a target the operation's own directory guard has not already
rejected — `_raise_if_dir` for the promote path, and for `move` the eager
destination `stat`, which fires before `posix_rename` is attempted at all.
The two are **not** the same guard and `move` never calls `_raise_if_dir`;
collapsing them is how an earlier revision of this sentence mis-assigned the
two-bound cost recorded above. That condition, per operation, is the whole of
the claim — a strictly larger set than "the server lacks the extension". **No example triggers are named here**, deliberately:
naming them requires knowing what every guard between `posix_rename` and the
fallback does, an earlier revision named three of which two were unreachable,
and the two guards involved (`_raise_if_dir` here, the destination `stat` in
`move`) are the kind of detail a reader should check in the code rather than
trust from prose.

**The path costs one bound, not two.** The exception the one-bound paragraph
above records was this one: the displace ran as a `remove` under
`contextlib.suppress(OSError)`, which swallowed its own timeout and let the
promote re-enter the same silent channel — 4.00 s at a 2.0 s bound. `_displace`
re-raises a dead-connection failure instead, so the promote is never attempted:
measured 2.13 s (`move`) and 2.11 s (`write_atomic`) at the same bound, by
`pytest tests/backends/sftp/test_io_timeout.py -k pays_one_bound --durations=0`.
`move`'s two rungs below the promote are unreachable on a dead channel for the
same reason, so nothing further is paid there either.

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

In every case, parent directories `_ensure_parent_dirs` created on the way in
remain behind — a failed write is not a rollback.

**Derivation.** The closure above is argued from the mechanism. The named states
are **not uniformly pinned, and the difference is stated rather than blurred**:
those with a test were run against a real silent peer through the `_StallRelay`
harness, with the destination read back through a second backend wired straight
to the server rather than through the condemned channel, and states whose silence
must begin at a specific round-trip are staged by silencing the relay from inside
the call that issues it, so the moment is deterministic rather than raced against
a timer. The rest follow from the closure and are **argued, not measured**. The
list is exhaustive rather than hedged, because a hedge is how the previous
revisions of this paragraph each claimed more coverage than they had: `copy`'s
untouched, absent and complete; `move`'s untouched and absent; and
`write_atomic`'s absent — six of the eighteen named states, each mechanically
the same event as a `write` or `move` state that does have a test.

A generated enumeration over the condition space — operation x the round-trip at
which silence begins x direction x `overwrite` x whether the destination
pre-existed x whether the server offers `posix-rename@openssh.com` — ran **164
combinations and pruned 156 as unreachable**, recording the raised type per case
so a combination where no stall fired could not be mistaken for a residue
measurement. Those are the harness's own totals from that run. It is **not** the
authority for the closure and did not ship: it is the artifact that failed, and
its failure is what the closure replaces. It earns its mention because the states
it *did* reach are sound and are among those named above.

The tests behind the named states are
`test_stalled_write_leaves_one_of_the_named_destination_states`,
`test_a_stalled_write_can_have_delivered_the_payload_in_full`,
`test_stalled_copy_leaves_a_prefix_at_the_destination_too`,
`test_a_lost_reply_can_complete_the_operation_it_reports_as_failed`,
`test_a_stalled_promote_in_the_fallback_leaves_the_old_content_in_a_backup` and
`test_a_stalled_atomic_write_preserves_the_destination_and_leaves_an_orphan_temp`
in `tests/backends/sftp/test_io_timeout.py`. The fallback's *non-dead* failures
are not stall states and are pinned separately, in
`tests/backends/sftp/test_atomic_fallback.py`. No claim is made that they span the
reachable space — the closure says no finite list can. Byte counts are
deliberately absent: the prefix length moves with the chunk size and the window,
so a figure would be a derived artifact going stale exactly as the enumeration
this clause already declines to keep does.

**This clause amends [SFTP-014](#sftp-014-atomic-write-simulated) rather than
merely citing it**, and amends it in two directions. SFTP-014's caveat said only
that the orphan temp remains; the untouched-destination half a reader takes from
"atomic" was never written down there, so it could not be relied on and is now
stated with its bound. Both halves are false outside that bound: a lost promote
reply leaves the rename performed, and the fallback path empties the destination
path while keeping both copies beside it. Found by running the contrast this
clause is stated against instead of quoting it.

<a id="where-the-previous-file-is"></a>
##### Where the caller's previous file ends up

**Enumerated rather than described**,
because describing it went wrong three times: each attempt narrowed the condition
to a dropped connection, and each was refuted by a live-connection state the
narrowing had not considered. The space is small enough to write down, so here it
is, and every other clause in the repo that speaks to it cites this table instead
of restating the scope. **Three steps decide it**, not two: whether the
destination was displaced, whether the promote landed, and what the fallback then
did about the backup — and that third step is best-effort in both directions,
`_restore` on each of its two calls and `_release` on its one.

The **Reached on** column is what makes the readings below countable rather than
recalled: `live` for a connection that never dropped, `drop` for one that did.

| Displace | Promote | Then | Reached on | The caller's previous file is | Pinned by |
| --- | --- | --- | --- | --- | --- |
| refused, or unprobeable | not attempted | the refusal propagates | live · drop | **at its path** — nothing was moved, and this is why a refusal is not reported as "nothing to restore". On a drop the probe raises instead of answering and a `.~tmp.` orphan is left, since the cleanup unlink is skipped rather than re-entering the channel | `test_a_refused_displace_reports_rather_than_writing_the_destination`, `test_a_probe_that_cannot_reach_the_server_reclassifies_nothing` |
| absent | attempted, and ordinarily lands | nothing to restore | live | there was none — the ordinary `overwrite=True` create | `test_an_errno_less_displace_failure_over_nothing_still_creates` |
| **landed, reported failed** | not attempted | the failure propagates | live | in `.~bak.<name>.<uuid8>` — the rename moved it and only the answer failed, so the path is empty and the caller is told so rather than the fallback guessing | `test_a_displace_that_landed_but_reported_failure_is_reported` |
| done, reply lost | not attempted | the drop propagates | drop | in `.~bak.<name>.<uuid8>`, the path empty — the landed-but-unreported row above, reached by a drop rather than by a server that answered | — argued from SFTP-030's closure |
| done | succeeded | `_release` drops the backup | live | replaced, as asked | `test_the_fallback_replaces_an_existing_destination` |
| done | succeeded | `_release` refused | live | replaced — but a `.~bak.<name>.<uuid8>` **outlives a successful call** | `test_a_release_the_server_refuses_leaves_a_backup_beside_a_good_write` |
| done | succeeded | `_release` reaches a silent channel | drop | replaced, and the call pays one `io_timeout` bound inside the suppressed unlink — the one place a **success** costs a bound. Whether a `.~bak.<name>.<uuid8>` outlives it depends on which direction went silent, and a caller cannot tell which they met | — argued |
| done | failed | restore ran and completed | live | **back at its path** — the ordinary failure, and what the fix buys | `test_a_failed_promote_leaves_the_destination_as_it_found_it` |
| done | failed | restore refused | live | in `.~bak.<name>.<uuid8>` | `test_a_restore_the_server_refuses_leaves_the_old_content_findable` |
| done | failed | restore not attempted | drop | in `.~bak.<name>.<uuid8>` | `test_a_stalled_promote_in_the_fallback_leaves_the_old_content_in_a_backup` |

**Which rows are measured is in the table** rather than left uniform, on the same
reasoning the named-states list above gives: eight of the ten carry a test, and
the two that do not say so.

**Two readings follow, and they are what the prose kept getting wrong.** The
`.~bak.` residue is **not** a dropped-connection signal: five rows leave one for
certain and a sixth may, and of those five, three are reached on a live
connection — one of them following a call that *succeeded* and raised nothing.
(The sixth is the silent-channel release, whose row says a caller cannot tell
which direction went silent and so cannot tell whether a backup outlived the
call. It is counted apart because a count that folds a maybe into a certainty is
the kind of figure this table exists to stop.) And the guarantee is the last
column never reading "gone", not the file being at its path: two rows do read "at
its path", but only one of them **restores** it there — the other never moved it
— so AW-003 promises the copy and the ordinary-failure row alone promises the
return. The three rows reading "replaced" replace the file by design, which is
the antecedent AW-003 carries and this table does not repeat.
