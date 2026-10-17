# BK-449 — No interaction protocol with states joins `Store`, kernel, driver and `Session`
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit 023](../audits/audit-023-kernel-migration-readiness.md),
finding T20 and proposal P0, at `52448e0`. The audit's evidence, probes and
**Checked:** lines are the record; this dossier does not copy them.

**The gap.** The contract is stated call by call, and the Python `Protocol`
classes fix signatures. No artifact states the interaction as a protocol: the
states each party passes through, which call is legal in which state, which
transition a failure, a cancellation or a close takes, and which party owns each
exit. The states exist, scattered: the backend's closed posture (BE-020), the
`Session`'s connect, invalidate and reconnect (RFC-0017 D5, an interface without
states), a write handle's open, commit or abort, a read stream's lifecycle, a
listing's cursor. `ResourceSafety.dfy` §1 and §3 model the pre-kernel classes.
Memory has no `Session`, so the audit drew this from the design text, not from
measurement.

**What it decides** (audit-023 P0, advisory):

- the state sets: backend, `Session`, read stream, write handle, listing cursor,
  caller's content iterator;
- each call's meaning in each state: the closed guard, `unwrap`, a repeated
  `close`, when a refusal surfaces (at the call or at the first iteration);
- the owner of each exit on every path, cancellation included;
- where it is stated and checked: a spec 003 section, a state model in the
  formal layer, one conformance cell per transition on a session-less and a
  `Session` driver.

**Findings it carries:** T20; the state half of T5 (close after a failed read),
T11 (`unwrap` after close) and T16 (the `open_write` handle); the lower-ranked
rows on repeated `close`, async `connection_dead`, cancellation routes and
async refusal timing.

- **(was BK-448, absorbed here)** The async kernel leaves a caller's content
  iterator suspended when it refuses a chunk or the write fails: `_marked`
  (`_kernel/_async/_io.py`) raises on a non-bytes chunk without `aclose()` on the
  caller's iterator, so its `finally` runs only at GC, on whatever loop is then
  current (BUG-335: 4 of 4 write routes). No spec covers caller-supplied content;
  the nearest, SEEK-011, closes a stream the library consumed. Its open decision,
  the kernel closes what it abandons or BE-030 says the caller owns it, is one of
  this item's exit owners.

**Due:** before RFC-0017 D3 step 2, the first remote driver and its `Session`.
BK-450's owner table names `Session` obligations that this item's states define.

## Plan (approved 2026-10-17)

Planned in one session, built in a fresh one. Every decision below is recorded in
`sdd/decisions/ad497154-50c4-54f3-9b47-d86d1878741d.jsonl`; orient verdicts are in
the trace (`sdd/traces/bk-449-interaction-protocol-states.yml`). Scope: protocol,
model, cells and one-site kernel fixes. The stream adapter (T4, T5) is BK-450's;
the refusal-timing implementation and the read handle go to one new `user.api`
item; the `Session` state set is fixed in the D3 step-2 PR.

### Decisions the build implements or states

1. Backend states: Open, Closed; `close_is_terminal` is a fixed declaration (BE-020). Non-terminal Closed re-initialises lazily.
2. Repeated `close`: driver obligation (idempotent); kernel forwards every call.
3. Timing rule (stated now, implemented by the new item): pure refusals at the call; stream I/O at open via a handle; listing I/O lazy; `InvalidPath` for a malformed key at the call, for a file-vs-folder mismatch at open. Record today's per-layer timing as the known gap.
4. Kernel closes a caller-supplied **async** content iterator it stops consuming (refusal, failure, cancel). Sync content is a caller *stream* (`read`), stays caller-owned and is never closed by the kernel (the caller may seek or retry it).
5. Close failure after a successful read: suppressed, logged, fed to `connection_dead`; a read failure wins over a close failure. Stated now; built by BK-450's adapter.
6. End-of-data integrity is a driver obligation: exhaustion is the SDK's EOF read, never a byte count (botocore validates length and checksum only on the empty read: `StreamingBody.read`, `StreamingChecksumBody.read`).
7. Write handle: the kernel aborts on any exception, `CancelledError` included (already true, `_async/kernel.py:891-897`); a failed abort is logged and fed to `connection_dead`, never raised; driver `abort` is legal after a failed `commit` and idempotent.
8. Overwrite refusal is atomic on the wire (driver); a conflict surfaces at `commit` (handle) or at the call (`put`); its mapping to `AlreadyExists` is a new BK-450 row.
9. `invalidate` closes the client now; streams on it fail mapped on their next read; `connection_dead` means transport-level death only. A `Session` never invalidates on cancel.
10. `unwrap`: terminal Closed raises `BackendUnavailable`; non-terminal is allowed; a session driver's goes through `run`, reconnecting after `invalidate`.
11. Concurrent close on a `thread_safe` backend (BE-028): accessor create and teardown are atomic against the closed flag (a mutex around the accessor only, never held over I/O; async re-checks after the connect await); `close` never waits for in-flight operations; driver teardown wakes blocked calls, which fail mapped. On `single_connection` backends (SFTP) concurrent close is caller misuse already. Owner: `Session`; stated now, cells at step 2.
12. Spec form: Markdown tables and numbered invariants (I1 terminal absorption; I2 `close ∘ close = close`; I3 cleanup on every kernel-observed exit), each naming its Dafny lemma. The guard order is taken from BE-030 (capability before the closed guard for `glob`, `write_atomic`, `open_atomic`), never restated.

### Subject list (the review contract; the mark is the author's evidence)

| Subject | Edge cases | Risk | Mark |
|---|---|---|---|
| Kernel `unwrap`, both runtimes | terminal vs non-terminal posture; fake's wrong-type answer | native handle after terminal close (T11) | executed |
| Async kernel `read` (`aio_backend.py`) | `connection_dead` true and false; close skipped when condemned | async and sync SIO-010 diverge | executed |
| Write routes: `put`, handle (`_write_through_handle`, `_HandleWriter`), temp and rename | abort raising; cancel at each await; commit conflict | silent orphan (abort failure swallowed) | executed |
| Caller async content iterator (`_async/_io._marked`) | async generator, custom iterator without `aclose`, non-bytes refusal, driver or handle failure, cancel | `finally` at GC on the wrong loop (BUG-335) | executed |
| Sync caller content stream | never closed by the kernel | closing the caller's file | executed |
| Driver protocol duties (`_async/driver.py` docstrings, generated sync) | idempotent close, abort after failed commit, EOF integrity, atomic overwrite, transport-level `connection_dead` | stated, unenforced | read only |
| Close posture states | repeated close reaches the driver; close, reuse, close on non-terminal | short-circuit regressions | executed |
| Generated sync twin | the generator's `--check` | runtimes drift | executed |
| Spec 003 BE-033 and its links (BE-020, 022, 028, 030; ASYNC-006, 088; SIO-010) | guard order vs BE-030; BUG-310's Closed-stream row | contradicts an existing clause | read only |
| Dafny `ResourceSafety.dfy` § 5 | every observed exit path | model claims more than the kernel does | executed (dafny verify) |
| `Session` obligations (decisions 9 to 11) | no `Session` exists | stated without a witness | not reached |
| Legacy (non-kernel) backends | BE-033 binds kernel classes only | scope creep | read only |

### Build steps

1. **Spec 003, `### BE-033: Interaction Protocol on the Kernel`**, after BE-032: state tables (backend, read stream, write handle, listing, caller iterator; a `Session` row "fixed at D3 step 2"), the transition matrix (state, call) to (next state, result), the exit-owner table (decisions 2 and 4 to 11), the timing rule with today's gap table, invariants I1 to I3 with lemma names. The read-stream Closed row cites BUG-310's spec 006 clause, BUG-310 owning the legacy adapters. One-line links, not copies, from BE-020, BE-022 (unwrap posture), BE-028 (close race), BE-030 (guard order), spec 029 ASYNC-006 (timing gap) and ASYNC-088, spec 006 SIO-010 (async parity).
2. **Failing cells first**: `tests/_kernel/test_protocol.py`, `@pytest.mark.spec("BE-033")`, both runtimes over the fake; Memory rows in `tests/backends/memory/test_kernel_cells.py`. Cells: unwrap after a terminal close; async read skips close on a condemned stream; the caller iterator `aclose`d on non-bytes refusal, handle failure and cancel; a sync caller stream left open; a failed abort logged (caplog) with the original error raised; a repeated close reaches the driver; close, reuse, close on non-terminal. Run them and see them fail.
3. **Fixes**, in the async source, then regenerate the sync twin (`scripts/gen_sync_kernel.py`):
   - `_async/kernel.py` `unwrap`: `self._guard()` first; the fake's `unwrap` raises `CapabilityNotSupported` (`tests/_kernel/_fake.py:600-603`).
   - `aio_backend.py` `read`: keep the caught exception; skip `close_stream` when `driver.connection_dead(exc)`, as `backend.py:64` does.
   - `_async/_io.py` `_marked`: a `try`/`finally` that `aclose()`s the caller's iterator when it was not exhausted and has `aclose`; the kernel's write routes `aclose()` the guarded wrapper after `_put` or `feed` on every path.
   - Abort sites (`_async/kernel.py:896, 924`; `backend.py:207, 214`): replace the bare `suppress` with one helper that logs `WARNING` on `remote_store._kernel` and calls `connection_dead`.
   - Driver protocol docstrings (`_async/driver.py`): the five duties.
4. **Hypothesis state machine**, `tests/_kernel/test_protocol_stateful.py`, patterned on `tests/aio/test_async_pbt_stateful.py`: rules open, iterate, fail, cancel, close backend, unwrap, write over the fake; invariants I1 to I3.
5. **Dafny**, `sdd/formal/ResourceSafety.dfy` § 5: datatypes for stream, handle and iterator, a `KernelExit` method over every observed exit, lemmas I1 to I3; a row in `sdd/formal/README.md`.
6. **Guide**: the driver duties in the custom-backend guide under `docs-src/`, with no tracker IDs in published prose.
7. **Backlog**: a new item (next safe ID from `hatch run gen-backlogid-check`), "Refusal timing rule and read handle (`with` / `async with store.read`)", `user.api`, its dossier citing BE-033's gap table; a new BK-450 row (conflict mapping); a new item "`Session` state set and the TLA+ close/run model", due at D3 step 2; BK-449 to done with remainder pointers; `hatch run gen-backlogid`.
8. **CHANGELOG** `[Unreleased]`: `- BK-449: ...` (kernel `unwrap` refuses after a terminal close; async caller iterators are closed when abandoned).
9. **Trace**: a step per read; the `review:` block only at the close, from `hatch run ship-report <PR> --trace-block-only`.

### As built (2026-10-17)

Where the build left the plan above, and why:

- Step 5's model is `sdd/formal/KernelProtocol.dfy`, not `ResourceSafety.dfy`
  § 5. `BackendContract.dfy` includes `ResourceSafety.dfy`, so § 5 shared the
  trait's namespace and compiled into the Dafny oracle (`check_dafny_oracle_fresh.py`
  failed, its `module_.py` diff reporting "444 more diff lines" past those it
  printed). A file nothing includes adds
  nothing to the oracle; `scripts/dafny_verify.sh` and CI verify it, so
  § Verification's `dafny verify` line means `KernelProtocol.dfy`.
- That model is also an oracle of its own: `scripts/dafny_translate.sh` compiles
  it to `sdd/formal/KernelProtocol-py/` (kept fresh by
  `check_dafny_oracle_fresh.py`), `tests/_kernel/test_protocol_oracle.py`
  drives the kernel against it over the exits BE-033 enumerates, and
  `scripts/gen_protocol_diagram.py` draws BE-033's diagrams from it. After
  editing the `.dfy`: `bash scripts/dafny_translate.sh`, then
  `hatch run gen-protocol-diagram` (sdd/formal/README.md § The second oracle).
- Step 3's `_marked` became a class, `_Marked`, with its own `aclose`, which
  `release_content` calls on every write exit; a generator wrapper's `finally`
  runs only once something closes the wrapper, so the route would have had to
  close it anyway.
- The kernel takes the caller's iterator with its first chunk. A refusal
  before that (the gates, a write check, an `open_write` refused, an occupied
  target on temp and rename) leaves it unstarted and the caller's: closing it
  made a retry with the same iterator write an empty file over the target
  (round 2 of PR #1159, measured against `ad56f9a8b`), and an unstarted
  generator has no suspended frame to protect.
- Step 7's IDs: BK-453 was already on a pushed branch (`gen-backlogid --check
  --remote`), so the timing item is BK-454 and the `Session` item BK-455.
- BE-033's conformance includes a repeated-close cell in both close-posture
  lanes, scoped to classes on the kernel, so the Dafny tags have a conformance
  citation (`check_formal_trace.py` F1).

### Verification

- Step 2's cells fail before step 3 and pass after (`tests/_kernel`, `tests/backends/memory`).
- `hatch run fast`, `hatch run lint`, and the sync generator's `--check` (in `preflight`).
- `dafny verify sdd/formal/ResourceSafety.dfy`.
- `python scripts/check_traces.py`; `hatch run gen-backlogid --check`.
- The ripple-check Detailed checklist before committing.
