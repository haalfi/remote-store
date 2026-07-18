# Audit 020 — SFTP backend correctness (BK-313 / PR #910) round-trip-cut review

**Backlog item:** BK-313 (cut SFTP per-operation metadata round-trips; PR #910,
branch `claude/bk-313-sftp-roundtrips-pgx7n2`). Follow-ups proposed at the end.
**Date:** 2026-07-18
**Scope:** The SFTP backend code logic only — `src/remote_store/backends/_sftp.py`
(the 292-line BK-313 diff and the paths it touches) plus the lazy-read error
wrapper it depends on, `src/remote_store/_stream.py`. Specs and tests were read as
**helpers** (to establish intent and to check whether a suspected defect is
covered), not as audit targets. Adjacent changed files (`_capabilities.py`,
`_backend.py`, `_models.py`) were out of scope except where the SFTP path depends
on them.
**Method:** line-by-line read of the file and the full `master...HEAD` diff; two
scoped expert sub-agents (one on the connection-liveness / staleness / reconnect
layer, one on the file-vs-directory classification and error-code mapping);
then **live verification against the real `atmoz/sftp` (OpenSSH) container**
(`infra-sftp-1`, host port 2222) and **targeted exception-injection** to confirm
the connection-staleness behaviour that a clean channel close cannot reproduce.
Every finding below was reproduced empirically (live op, real read-only directory,
or injected paramiko exception) unless explicitly marked static-only. This is a
**report-only** audit — nothing was modified. Dispositions in the proposals section
are advisory; the user decides what becomes work.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low / Nit.
Each finding tag (H1, M2, L3…) is referenced by the proposals table at the end.

---

## Summary

The **visible core of BK-313 — moving file-vs-directory classification from eager
pre-`stat` checks to lazy post-failure classification — is correct on real
OpenSSH.** A 20-case live battery against `atmoz/sftp` passed every case: a
directory target yields `InvalidPath` across `read` / `read_bytes` / `write` /
`write_atomic` / `open_atomic` / `delete` (including `missing_ok=True`), a
file-ancestor yields `NotFound`, a missing path yields `NotFound`, and an existing
file with `overwrite=False` yields `AlreadyExists`. The raw probe confirmed the two
server behaviours the design rests on: OpenSSH opens a directory for reading without
error (so `read`/`open_atomic` correctly keep an eager check), and it reports a
directory `st_size` of **4096** (so `read_bytes`'s lazy path fires because the read
raises rather than returning empty). `_promote`/`_rename_fallback`, the
base-relative ancestor walk, the chroot boundary handling, and the
`WriteResult(last_modified=None)` behaviour change all check out.

**The material risk is not in the classification refactor — it is in the
connection-staleness layer the perf change quietly reshaped.** Master's
`_is_connected()` issued a `stat('.')` round-trip on **every** `_sftp` access; that
round-trip was the round-trip BK-313 set out to remove, but it doubled as a
**universal self-heal** — a dead client of *any* kind was detected and reconnected
on the very next operation. BK-313 replaced it with the local `transport.is_active()`
flag (the legitimate win) and compensated with a "tier-2" scheme: `_map_exception`
clears the cached client **only inside its `_is_connection_dead(exc)` branch**.
Because `is_active()` stays `True` on a channel-only death, that branch is now the
*sole* remaining reconnect trigger — and its signal set is incomplete. Every
dead-connection signal it does not recognise now **permanently wedges** the backend:
the op is reported (as `BackendUnavailable` or, worse, a generic `RemoteStoreError`),
the dead client is never cleared, `is_active()` keeps returning `True`, and **every
subsequent operation reuses the dead client forever** (H1). Master self-healed all of
these. This is a genuine High-severity availability regression, and it slipped all
three prior review rounds and both test lanes because every channel-death test uses a
*clean* close, which happens to hit the one handled signal.

Two related Medium error-mapping leaks share the same layer: a streaming `read()`
leaks a raw `EOFError` to the consumer (M1), and `open_atomic` leaks a raw
`PermissionError` where its siblings map to `PermissionDenied` (M2). A fourth item
(M3) is a portability edge in `read_bytes`'s new lazy directory rejection. The Low
items are mostly pre-existing patterns preserved through the refactor.

---

## 🔴 High

### H1 — Dead-connection signals outside `_is_connection_dead` permanently wedge the client (no reconnect)

**Files:** `src/remote_store/backends/_sftp.py:1553-1570` (`_is_connected`, now a
local flag read); `:1826-1848` (`_is_connection_dead`); `:1862-1873` (the
`_map_exception` branch that clears `_sftp_client` — the **only** clear on the
operation path); `:1932-1934` (the `SSHException` and generic-`RemoteStoreError`
tails that map an error **without** clearing the client).

The reconnect loop works only when `_map_exception` reaches the
`_is_connection_dead(exc)` branch and sets `self._sftp_client = None`; the next
`_sftp` access then sees `_sftp_client is None` and reconnects. But
`_is_connection_dead` matches only `EOFError` and `OSError` with errno in
`{ECONNRESET, EPIPE, ECONNABORTED}` or errno `None` + the literal `"socket is
closed"`. Any other dead-channel signal maps to `BackendUnavailable` (via the
`paramiko.SSHException` tail) or to a bare `RemoteStoreError` (the generic tail)
**without clearing the client**, and with `transport.is_active()` still `True`
the wedge is permanent.

**Empirically confirmed by injection** (exception injected at the client's `stat()`;
transport left active so `_is_connected()` keeps returning `True`):

| Injected signal | 1st op maps to | client cleared? | 2nd op |
|---|---|---|---|
| `EOFError` *(baseline)* | `BackendUnavailable` | ✅ | self-heals |
| `OSError('Socket is closed')` *(baseline)* | `BackendUnavailable` | ✅ | self-heals |
| `paramiko.SSHException('Server connection dropped')` | `BackendUnavailable` | ❌ | **WEDGED** |
| `paramiko.ChannelException` (SSHException subclass) | `BackendUnavailable` | ❌ | **WEDGED** |
| `paramiko.SFTPError('Garbage packet received')` | `RemoteStoreError` | ❌ | **WEDGED** |
| `socket.timeout` / `TimeoutError` | `RemoteStoreError` | ❌ | **WEDGED** |
| `OSError(EBADF)` | `RemoteStoreError` | ❌ | **WEDGED** |
| `OSError(ETIMEDOUT)` | `RemoteStoreError` | ❌ | **WEDGED** |

"WEDGED" = the second op re-fails identically with no reconnect attempt (verified).
Type facts underpinning the gap (checked against the installed paramiko):
`issubclass(EOFError, OSError)` is `False`; `socket.timeout is TimeoutError` and it
is an `OSError` but a half-open/idle instance typically carries no matching errno;
`paramiko.SFTPError` subclasses neither `OSError` nor `SSHException`;
`paramiko.ChannelException` subclasses `SSHException`, not `OSError`.

**Consumer impact.** The most realistic trigger is **`socket.timeout`**:
`_connect` sets `channel_timeout=self._timeout` (default 10 s), so a single slow or
half-open operation raises `socket.timeout` → generic `RemoteStoreError` → wedge, and
the long-lived `SFTPBackend` becomes **permanently unusable even after the server
recovers**, until the process restarts. Long-lived connections are exactly this
backend's use case. Two secondary problems ride along: (a) `socket.timeout` and
`SFTPError` are availability failures but map to a bare `RemoteStoreError`, so a
caller backing off on `BackendUnavailable` never catches them; (b) the
`_is_connection_dead` docstring asserts its enumeration is complete ("paramiko
surfaces a dead channel as `EOFError` or … `ECONNRESET`/`EPIPE`/`ECONNABORTED`"),
which is false for the cases above. The PR summary's own claim — "a **second
detection tier** keeps SFTP-010 honest … the next call reconnects instead of
wedging" — does not hold for this signal tail.

**Origin:** BK-313-introduced. Master's `stat('.')` liveness probe self-healed every
row of the table on the following operation, at the cost of the round-trip this PR
correctly removed. The regression is the incompleteness of the compensating tier-2,
not the removal itself.

---

## 🟠 Medium

### M1 — Streaming `read()` leaks a raw `EOFError` to the consumer (unmapped) and does not invalidate the client

**Files:** `src/remote_store/_stream.py:71-85` (`_ErrorMappingStream.readinto`/`read`
catch **only `OSError`**); reached via `src/remote_store/backends/_sftp.py:774-775`
(the lazy `BufferedReader` returned by `read()`).

`read()` returns a lazy stream; by the time the caller pulls bytes, the `_errors()`
context manager has exited, so `_ErrorMappingStream` is the sole mapping site. It
intercepts `OSError` only. paramiko raises `EOFError` (not an `OSError`) on read EOF
in `_read_all`/`_read_response`, so a channel death that surfaces that way escapes
**raw** to the consumer. **Confirmed by direct injection:** an inner stream raising
`EOFError`, wrapped exactly as `read()` wraps it (`_ErrorMappingStream` +
`io.BufferedReader`), delivers a bare `EOFError` to `buf.read()`
(`isinstance(e, RemoteStoreError)` is `False`). Because the raw error never routes
through `_map_exception`, it is also an H1 instance for the read path (client not
cleared → wedge on subsequent ops).

Nuance worth recording: a *clean* socket close during a live streamed read surfaces
as `OSError('Socket is closed')`, which **is** caught and correctly mapped to
`BackendUnavailable` (live-confirmed: mid-stream channel close → `BackendUnavailable`,
client cleared). So M1 bites only on the `EOFError` death mode, but that mode is real
on paramiko's read path.

**Origin:** the raw-`EOFError`-on-read contract leak is pre-existing (the wrapper
never handled `EOFError`); the *wedge* consequence is BK-313 (master's probe
self-healed it regardless of how it was reported). The listing ops
(`list_files`/`list_folders`/`iter_children`) do **not** share this leak — BK-313
correctly routed them through `_map_exception`, and an `EOFError` raised during lazy
`listdir_attr` iteration is caught there (live-confirmed: `BackendUnavailable` +
reconnect).

### M2 — `open_atomic` leaks a raw `PermissionError` where `write`/`write_atomic` map to `PermissionDenied`

**File:** `src/remote_store/backends/_sftp.py:992-1011` (the yield-phase `try/except`).

The temp-file open (`self._sftp.file(tmp_path, "w")`) and the caller's streamed
writes run **outside** `_errors()` — deliberately, so a caller's own exception
propagates unmapped. But the `except` handler maps **only** connection-death
(`_is_connection_dead(exc)`); every other backend failure during the temp-open hits
the bare `raise` at `:1011` and escapes raw, unlike `write`/`write_atomic`, whose
temp-open runs inside `_errors()`. Unlike `_map_exception`, this inline handler also
lacks the `paramiko.SSHException → BackendUnavailable` fallback.

**Live-confirmed** against a real `chmod 0o555` directory on the container: `write`
→ `PermissionDenied` ✅, `write_atomic` → `PermissionDenied` ✅,
**`open_atomic` → raw `PermissionError`** ❌. This violates `open_atomic`'s own
documented `Raises: PermissionDenied` clause and the backend contract that all
backend errors are `RemoteStoreError` subtypes. The same window leaks any other
non-connection-dead temp-open failure raw (disk-full `ENOSPC`, quota `EDQUOT`, a
race that removes the parent between setup and open, a `paramiko.SSHException`).

**Origin:** the temp-open-outside-`_errors()` shape is pre-existing, but BK-313
rewrote this exact `except` handler (adding the tier-2 arm) and left the general
mapping gap in place; the method's docstring promises `PermissionDenied`.

### M3 — `read_bytes` on a directory depends on the server *raising* on read; a server reporting dir `st_size==0` returns `b''` (wrong data)

**File:** `src/remote_store/backends/_sftp.py:794-811`.

BK-313 removed `read_bytes`'s eager `_check_not_dir`; the `InvalidPath`
classification now runs only inside `except OSError` (the lazy `_raise_if_dir` at
`:805`). It fires only if `_sftp.file(dir,'r')` + `prefetch()` + `read()` **raises**.
When a server opens a directory for reading (which OpenSSH does) and reports a
directory `st_size` of `0`, paramiko's prefetch issues no read request and
`read()` short-circuits at EOF, **returning `b''`** — so `read_bytes` would return
empty bytes for a directory instead of raising `InvalidPath`. This is a wrong-*data*
outcome, not merely a wrong error type.

**On the audited server the risk does not materialise:** OpenSSH reports dir
`st_size == 4096`, so the read raises `Failure` (errno `None`) and the lazy path
correctly produces `InvalidPath` (live-confirmed). The exposure is to a
non-OpenSSH / non-standard server that opens a directory for read and reports size
`0`. Not reproducible on the available container.

**Origin:** BK-313-introduced (the eager check that previously covered this on all
servers was removed). Static-plus-partial-live; the empty-`b''` branch needs a
server that reports dir size 0 to confirm end-to-end.

---

## 🟡 Low / Nits

- **L1 — `_raise_if_dir` swallows *all* `OSError`, so a directory whose
  classification stat itself fails goes unclassified.**
  `_sftp.py:1640-1645` (`except OSError: return`). If the follow-up stat fails for a
  reason other than the target being a readable directory — e.g. a
  permission-restricted server returns `EACCES` on the stat — `InvalidPath` is
  silently not raised and the caller re-raises its original error, degrading to a
  generic `RemoteStoreError`. Master's `_check_not_dir` re-raised non-`ENOENT` stat
  errors (`if errno != ENOENT: raise`), surfacing that as `PermissionDenied`. Narrow
  (needs a server whose classification stat errors differently from the op); BK-313
  widened the swallow. Static-only.

- **L2 — Mode-less servers: a directory target yields `AlreadyExists`/generic, never
  `InvalidPath`.** `_sftp.py:855, 918, 983`. The guard is `st.st_mode is not None and
  S_ISDIR(...)`; when `st_mode is None` the is-dir branch is skipped and
  `overwrite=False` falls through to `AlreadyExists`. Inconsistent with
  `_ensure_parent_dirs` (`:1809`), which treats mode-less defensively as "not a
  directory ⇒ `InvalidPath`". Three different mode-less policies coexist across the
  file. **Pre-existing** (guard predates BK-313, relocated verbatim). Static-only.

- **L3 — `delete` under a file-ancestor lacks the `_has_file_ancestor` recheck that
  `read`/`read_bytes` have.** `_sftp.py:1024-1037`. On OpenSSH the case is correct
  (unlink under a file-ancestor → `ENOENT` → `NotFound`, live-confirmed). On a server
  that surfaces it as an errno-less `SSH_FX_FAILURE`, `delete` has no `code is None
  and _has_file_ancestor → NotFound` recheck (unlike `read` at `:760` and `read_bytes`
  at `:806`), so `_raise_if_dir` swallows the generic failure and it degrades to
  `RemoteStoreError` instead of `NotFound`. **Pre-existing** read-vs-delete
  inconsistency. Static-only.

- **L4 — Cleanup after a promote-death reconnects.** `_sftp.py:943-944` (write_atomic),
  `:998-1000` (open_atomic). When `_promote` fails inside the inner `_errors()`,
  `_map_exception` clears `_sftp_client`; the outer `except` then calls
  `self._sftp.remove(tmp_path)`, which re-enters the `_sftp` property and triggers a
  full `_connect()`. **Confirmed:** 1 reconnect call during the failed op (fast
  against the up server, 0.17 s). Against a genuinely down server this runs the full
  tenacity retry/backoff loop (up to `max_attempts`, exponential backoff to
  `backoff_max`) **inside best-effort temp cleanup**, blocking the original error's
  propagation for many seconds. Efficiency, bounded, suppressed. Surfaced more sharply
  now that `is_active()` gates the property.

- **L5 — `open_atomic` temp file orphaned on `GeneratorExit`/`KeyboardInterrupt`.**
  `_sftp.py:998`. The cleanup `remove(tmp_path)` lives under `except Exception`; both
  interrupt types are `BaseException`, so an abandoned/GC'd `with open_atomic(...)`
  block leaves the `.~tmp.<name>.<hex>` file on the server. The atomic contract holds
  (`_promote` never runs → target untouched), so this is litter, not corruption.
  **Pre-existing** shape, restructured by BK-313.

- **L6 — `_has_file_ancestor` returns `False` on any opaque stat error while
  walking.** `_sftp.py:1758-1764`. If the stat of an ancestor that *is* a regular file
  fails non-`ENOENT` (e.g. `EACCES` on that file), the helper returns `False`, so the
  `read`/`read_bytes` file-ancestor recheck does not fire and the errno-less failure
  degrades to `RemoteStoreError` instead of `NotFound`. Documented as deliberately
  conservative; unusual to be able to stat a directory but not its file child.
  **Pre-existing** (ID-209). Static-only.

---

## Verified strengths (checked, not rubber-stamped)

- **Is-dir classification is correct on real OpenSSH.** 20/20 live cases pass:
  directory → `InvalidPath` across `read`/`read_bytes`/`write`/`write_atomic`/
  `open_atomic`/`delete` (incl. `overwrite=True/False` and `missing_ok=True`);
  file-ancestor → `NotFound`; missing → `NotFound`; existing file + `overwrite=False`
  → `AlreadyExists`. The raw probe confirmed the two server facts the design rests on
  (OpenSSH opens a directory for reading without error; directory `st_size == 4096`).
- **`_promote` / `_rename_fallback` are correct.** `_raise_if_dir` runs *before* the
  fallback, so a directory target is never fed to the fallback's `remove` + `rename`;
  the fallback respects the overwrite contract (plain `rename` when `overwrite=False`,
  `remove`-then-`rename` when `True`).
- **The handled tier-2 path works.** A clean channel close (transport still active)
  is detected on the next op: `EOFError`/`OSError('Socket is closed')` →
  `BackendUnavailable`, client cleared, next op reconnects. Live-confirmed for a
  single-object op, a listing op, and `open_atomic`'s inline yield-phase arm.
- **`_connect` failure leaves clients `None`.** `_close_clients()` nulls both up
  front; new clients are assigned only after `_do_connect()` succeeds; on failure
  `ssh.close()` + re-raise leaves `_sftp_client` `None`, so the next access retries.
  No half-open client.
- **`WriteResult(last_modified=None)` change is sound.** `size` is the byte count
  taken during upload; the dropped post-write stat bought only `last_modified`, and
  WR-001a permits `None` when the write response omits it.
- **`__del__` / `_del_cleanup` / `_close_clients` are shutdown-safe** (guarded
  `getattr`, no `contextlib` reliance during teardown, TOFU host-key save before
  close).

---

## Proposed backlog items

Advisory groupings for the user to accept, split, or decline (per the Audits rule,
this audit proposes; nothing is filed without sign-off).

| Group | Findings | Scope / files | Suggested disposition |
|-------|----------|---------------|-----------------------|
| **G1 — Tier-2 staleness completeness (the regression)** | **H1** (+ the `socket.timeout`/`SFTPError` mis-classification and the M1 read-stream wedge) | `_is_connection_dead` (`:1826`), `_map_exception` `SSHException`/generic tails (`:1932-1934`), the `open_atomic` inline handler (`:992-1011`), `_stream.py` (`:71-85`); SFTP-010 | Make client-invalidation follow the **conclusion** (unusable connection ⇒ clear `_sftp_client`) rather than one predicate: clear in the `SSHException` branch and the generic tail when the error is an availability failure; widen `_is_connection_dead` to `SFTPError` and socket-teardown/timeout errnos (map those to `BackendUnavailable`, not generic); give the `open_atomic` handler the `SSHException` fallback; have `_ErrorMappingStream` catch `EOFError`. Restores master's universal self-heal without the per-op `stat('.')`. Add channel-death tests that inject **non-`EOFError`** signals (the existing tests use clean closes and miss the whole tail). Correct the `_is_connection_dead` docstring's completeness claim. |
| **G2 — `open_atomic` error-mapping parity** | **M2** | `open_atomic` yield phase (`:992-1011`) | Map non-connection-dead backend failures from the temp-open to `RemoteStoreError` subtypes (as `write`/`write_atomic` do) while still letting the caller's own in-block exceptions propagate unmapped. Add a read-only-directory test asserting `PermissionDenied` (folds into G1 if the handler is reworked there). |
| **G3 — `read_bytes` directory rejection portability** | **M3** | `read_bytes` (`:794-811`) | Decide: restore an eager directory check for `read_bytes` (as `read` keeps), or document that lazy rejection assumes the server reports a non-zero directory `st_size` / raises on directory read. Low real-world hit on OpenSSH; the decision is whether to guarantee it cross-server. |
| **G4 — Low-severity correctness edges (mostly pre-existing)** | **L1, L2, L3, L4, L5, L6** | as cited per finding | Independent, splittable: fold the mode-less policy into one helper (L2); add the `delete` file-ancestor recheck for parity with `read` (L3); bound or skip the reconnect during best-effort cleanup (L4); consider `BaseException`-aware temp cleanup (L5); reconsider `_raise_if_dir`'s swallow-all vs re-raising non-classifying stat errors (L1, L6). |

**Priority ordering:** G1 (High availability regression, and the natural place to
also close M1/M2's shared root) → G2 → G3 → G4.

**Note on this PR.** H1, M1, M2, and M3 are BK-313-introduced (H1/M3 directly; M1/M2
are pre-existing leaks whose *wedge* consequence or *touched-handler* ownership this
PR takes on). A companion handover records which of these PR #910 should address
before merge versus defer to a follow-up.
