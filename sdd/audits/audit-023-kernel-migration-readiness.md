# Audit 023 — What must close before backends move onto the contract kernel

**Date:** 2026-10-17

**Motivation:** RFC-0017 moves every backend onto one contract kernel, a new
interaction between `Store`, kernel and driver (D3 steps 2 to 8). That move is
sound only once the specs and open design issues the kernel rests on are
closed; otherwise each migration re-decides them, differently. The Memory
drivers are the means of this audit, not its subject: they are the only drivers
on the kernel today, so what they and the kernel leave unspecified, unpinned or
contradictory is what every migrated backend would inherit.

**Scope:** The RFC-0017 contract kernel (`src/remote_store/_kernel/`, async
source and generated sync twin), `MemoryDriver` and `AsyncMemoryDriver`
(`backends/_memory.py`, `backends/_memory_tree.py`,
`aio/backends/_memory.py`) and the public `remote_store.drivers`, at
`52448e0`. Read against spec 003 (BE-0xx, BE-032 Appendix A), 013, 018, 029,
045, 051, the kernel's design (RFC-0017 D1, D2 and D5, ADR-0042), the driver docs (`docs-src/reference/api/drivers.md`,
`docs-src/guides/custom-backend-guide.md`), the formal model
(`BackendContract.dfy`, `MemoryBackend.dfy`, `RootPath.dfy`, `StoreTree.dfy`)
and the tests under `tests/_kernel/`, `tests/backends/memory/` and the
conformance cells Memory runs. The question: where spec, code, tests and
model disagree, or a clause is unspecified or unpinned, that must be closed
before backends migrate.

**Excluded, already filed:** BK-439, BK-438, BK-446, BK-447, BUG-334,
BK-436, BK-435, BK-390, BK-345. A finding below touches one of them only
where it says so.

**Method:** six read-only passes, one per cluster: kernel contract, Memory
drivers, async parity, glob and tree, formal model, driver docs. Each
behavioural claim was measured with a probe script on `52448e0` (`hatch run
python`), most against a subclass of `MemoryDriver` or the kernel test fake
`tests/_kernel/_fake.py` with one primitive overridden; the output is quoted
under each finding. A second reader then re-checked each finding and records
how on its **Checked:** line (or in the § Lower-ranked *Checked* column): the
probe re-run, the cited line opened, a grep or command run, or "first pass
only" where it was not repeated.

**Probes:** committed in [`audit-023-probes/`](audit-023-probes/), one
directory per pass (`c1` kernel to `c6` docs) plus the second reader's
`lead_v_meta.py` and `lead_v_write_alias.py`. `hatch run python sdd/audits/audit-023-probes/run_all.py`,
from the repo root, runs all 32 and records each output beside it as
`<probe>.out`; the committed `.out` files are the run this audit quotes, at
`52448e0` on CPython 3.13.16. Timestamps, temp names and object addresses
differ between runs.

**Tool state at the audit:** `dafny 4.11.0`, `dafny verify` on the four files 1953 verified and 0
errors; `hatch run check-dafny-oracle-fresh` fresh; `hatch run
gen-sync-kernel-check` "up to date"; `hatch run lint` exit 0.

This is a **report-only** audit; nothing was modified. Dispositions are advisory.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low.

---

## Summary

**The kernel's pipeline is sound; what it trusts from a driver is not
pinned.** The BE-030 order, addressing, the choke point, BE-031, BE-017 and
BE-029 match the spec and are pinned by named tests (§ Checked clean). The
findings cluster where the kernel takes a driver's word without a clause or a
check: a mapping it hands out uncopied (T1), a protocol body it never looks
behind (T2), keys and declarations it does not validate (T9, T10), and stream
errors it maps three ways (T4, T5). Around those calls, no protocol states who
may call what in which state (T20). The formal model trails the kernel in four
places (T3, T12, T13, T14), one of which would fail a correct test.

**The tree concepts are sound; the boundary lacks three.** The tree came back
clean (§ Checked clean). The boundary between `Store`, kernel, driver and
`Session` lacks an interaction protocol with states (T20), a fault taxonomy
that tells a wire error from a programming error by rule (T4, T5), and one
meaning per capability flag across runtimes (T6). The remaining findings are
bindings: existing concepts not yet wired to glob, the formal model, a flat
template, or the `Store`-kernel split. Seven proposals (§ Proposals, P0 to P6)
close both kinds; T1 to T16, T19 and T20 each name the one that absorbs them;
T17, T18 and most lower-ranked rows are direct fixes with no open choice.

**Recommendations from triage.** Each item is placed by one criterion: does
closing it change what a migrating driver implements or may rely on?

- **(a) Before D3 step 2:** P0 (T20), P1 (T1, T2, T4, T5, T9, T10, T11, T13's
  driver half, T15, T16), P2 (T7, T8; `S3Boto3Backend` declares `GLOB`,
  `_s3_boto3.py:88`, and globs through `pattern_to_regex`, `:809`), P4 (step 2's S3 is the first flat
  driver) and P5 (T6).
- **(b) Before the migration finishes (D3 step 8):** P3 (T3, T12, T13's model
  half, T14, T19's model half), P6, T17, T18 and T19's test half. P3 moves to
  (a) if the formal model is to gate step 2's own acceptance, as triage
  recommends it gate driver acceptance.

T7 stays open (§ Open questions); the rows under § Lower-ranked are recorded,
not gated. Effort was ruled out as an argument for or against a proposal; each
is judged by whether later drivers need it and what it prevents. Like
everything in an audit these are advisory (CLAUDE.md § Audits). Suggested home
if adopted: a new ADR for the two-tier gate and the model's role, with a
backlog item carrying the gate, the way BACKLOG already carries "due before"
gates (BK-439).

| Severity | Count | Findings |
|---|---|---|
| 🔴 High | 3 | T1, T3, T20 |
| 🟠 Medium | 17 | T2, T4 to T19 |
| 🟡 Low | 27 | § Lower-ranked |

Counts are of the finding sections and the § Lower-ranked table rows in this
document, after merging findings that two passes reported separately.

---

## Findings

### T1 🔴 `FileInfo.metadata` is the live stored dict

**Proposal:** P1. **Kind:** contradiction. **Clause:** `FileInfo` "Immutable snapshot"
(`_models.py:82`), BE-019.
Mutating a returned info's `metadata` mutates the stored file's, and `copy`
leaves source and destination sharing one dict. On the write side,
`WriteResult.metadata` is the caller's own dict.

**Checked:** probes `lead_v_meta.py`, `lead_v_write_alias.py` and `c2/measure.py` § D, § F re-run; cited lines opened.

- Code: `_memory_tree.py:58` (`metadata=node.metadata`), `:212` (copy stores
  `entry.metadata`); the kernel's `_file_info` passes it uncopied
  (`_kernel/_async/kernel.py:635`, sync `:620`) while it copies `extra`.
- Probe: write `a.txt` with `{"k": "v"}`, mutate `get_file_info("a.txt")`,
  copy to `b.txt`, mutate `b.txt`'s info.
  ```
  sync stored after mutating info: {'k': 'MUTATED'}
  sync src after mutating dst info: {'k': 'VIA_DST'}
  async stored after mutating info: {'k': 'MUTATED'}
  ```
- Write side: `MemoryTree.put` returns `PutResult(metadata=metadata)`, the
  caller's mapping (`_memory_tree.py:145`; only the stored copy at `:133` is
  copied); the kernel's `_write_result` passes it on (`_async/kernel.py:149`,
  sync `:134`). Probe: write with `m = {"k": "v"}`, then mutate `m`:
  ```
  sync WriteResult.metadata after caller mutates its dict: {'k': 'CALLER'} | is caller's: True
  async WriteResult.metadata after caller mutates its dict: {'k': 'CALLER'} | is caller's: True
  ```
- Predates the kernel: `git grep metadata 107a5a1 --
  src/remote_store/backends/_memory.py` shows the same at lines 459 and 619.
- No MEM clause or test covers isolation.

**Template impact:** the kernel never copies `Entry.metadata`, so every driver
that returns its own mapping inherits it, and every driver that echoes the
caller's in `PutResult`. **Disposition:** copy (or wrap read-only) in
`_file_info`, `_write_result` and `MemoryTree.copy`; a conformance cell in both
runtimes for each direction.

### T2 🟠 An optional protocol's own body passes construction and no-ops

**Proposal:** P1. **Kind:** spec-gap, untested. **Clause:** BE-030 (construction refusals).
A driver that subclasses `SupportsCopy` and `SupportsRemoveFolder` without
overriding them constructs, and `copy` and `delete_folder` return success
having done nothing.

**Checked:** probes `c1/probe4.py` and `c1/probe4_async.py` re-run; cited lines opened.

- Code: `_check_construction` refuses an inherited body only for
  `_PRIMITIVE_BODIES`, built from `vars(AsyncDriver)`
  (`_kernel/_async/kernel.py:116-130`); optional protocols are detected by
  `isinstance` alone (`:325-336`, sync `_sync/kernel.py:310-321`).
- Probe (`class Forgetful(_SyncBase, SupportsCopy, SupportsRemoveFolder)`,
  declares `COPY`):
  ```
  copy returned; 'dst' in store: False
  delete_folder returned; folder 'd' still present: True
  ```
- Spec 003 l.1435-1438 refuses an inherited body "for a primitive"; whether an
  optional member is one is unstated. BK-441 (done) added that refusal for the
  required primitives; this is the optional half it left.
  `test_the_body_checked_set_is_every_protocol_method_but_probe`
  (`tests/_kernel/test_kernel.py:1590`) pins the narrow set.

**Template impact:** none copied today: Memory subclasses only the required
`Driver` (`backends/_memory.py:29`), whose bodies the check covers, and presents
its optional protocols structurally, as the guide teaches ("define the method,
and the kernel uses it", guide l.344-345); no class in `src/`, `docs-src/`,
`examples/` or `tests/_kernel/` subclasses a `Supports*` protocol (grep
`class \w+\(.*Supports`). The exposure is that the protocols are public,
runtime-checkable classes in `drivers.__all__`, so subclassing one is a natural
author's move, and the failure is a silent no-op. Ranked 🟠 on that
likelihood. **Disposition:** run the body check over
every optional protocol presented and over `WriteHandle`; state it in BE-030.

### T3 🔴 The model's `ListFolders` lists every nested folder

**Proposal:** P3. **Kind:** model-gap. **Clause:** BE-015.
`BackendContract.dfy`'s soundness and completeness clauses for `ListFolders`
use `IsChildOf`, which is any depth, while BE-015 and the kernel list
immediate subfolders.

**Checked:** probe `c5/probe2.py` re-run; `IsChildOf` and the `ListFolders` clauses opened.

- `IsChildOf` (`BackendContract.dfy:256-264`) checks prefix and `/`, no depth;
  the clauses at `:1034-1043` say "immediate" in the comment only.
  `MemoryBackend.dfy:862` refines the same. BE-015 (spec 003 l.630) says
  immediate.
- Probe, after writing `a/b/c.txt`:
  ```
  [kernel] list_folders(''): ['a']
  [oracle] list_folders(''): ['a', 'a/b']
  ```
- The oracle lane is green because the BE-015 cells seed one level
  (`tests/backends/conformance/test_listing.py:75, :333-343`).

Rule 7: prose and kernel agree; the model is the stale side. A correct
grandchild cell would fail on the oracle, which the formal README reads as the
test's bug. **Disposition:** add a depth bound to both clauses and the
refinement, regenerate the oracle, add a grandchild cell.

### T4 🟠 One stream fault, three answers by method

**Proposal:** P1. **Kind:** contradiction. **Clause:** BE-021 kernel row, SIO-012.
`read` maps only `(OSError, EOFError, *stream_catch)`, while `read_bytes` and a
ranged `read_seekable` map any `Exception` through the choke point.

**Checked:** probe `c1/probe2.py` re-run.

- Code: `_kernel/backend.py:58-67`, `aio_backend.py:48-57` (`read`);
  `kernel.py:716-720` (`read_bytes` under `_choke`); `backend.py:117-121`
  (ranged read under `_choke`).
- Probe, `stream_catch=()`, both runtimes alike:
  ```
  read:       mid-stream FakeDown       -> raw FakeDown
  read_bytes: mid-stream FakeDown       -> BackendUnavailable
  read:       mid-stream AttributeError -> raw AttributeError
  read_bytes: mid-stream AttributeError -> RemoteStoreError
  ```
- BE-021's kernel row (spec 003 l.767) has no stream carve-out, and
  `stream_catch` is in no spec-003 clause (`rg "stream_catch|SIO-012"
  sdd/specs` hits 006 and 009 only). SIO-012 (006 l.299-333) names "one fault,
  two answers depending on which method the caller used" as the defect BK-358
  fixed. `test_a_streams_caught_set_is_the_same_in_both_runtimes`
  (`test_kernel.py:629`) covers `read` only.

**Disposition:** one caught set for all three, stated with `stream_catch` in
BE-021's driver column; cells for `read_bytes` and the ranged read.

### T5 🟠 A failing stream close: swallowed, leaked, or masking

**Proposal:** P0, P1. **Kind:** contradiction, undecided under Rule 7. **Clause:** ASYNC-024,
BE-021.
When the driver stream's close raises, sync `read` suppresses it, async `read`
leaks it raw, and `read_bytes` maps it but lets it replace an earlier read
error.

**Checked:** probes `c3/close_oserror.py` and `c3/streams.py` re-run; `aio_backend.py` opened.

- Code: sync suppresses in `_stream.py:238-245`; async closes in a `finally`
  outside the mapping (`aio_backend.py:59-60`) and calls `stream.__aiter__()`
  before the `try` (`:49`); `_io.read_all` closes in a `finally`
  (`_sync/_io.py:29-34`, `_async/_io.py:25-30`).
- Probe, close raises `ConnectionResetError`:
  ```
  sync read() + close():  OK b'abc'
  sync read_bytes():      RemoteStoreError: ConnectionResetError: close reset
  async read():           builtins.ConnectionResetError: close reset
  async read_bytes():     RemoteStoreError: ConnectionResetError: close reset
  ```
  With a mid-stream error and a close error, `read_bytes` reports the close
  error in both runtimes; the wire error survives only as `__context__`.
- No test faults a stream close: the fake's async stream (`_fake.py:685`) has
  no close fault.

**Disposition:** state that a close failure never masks a read failure and
that `read` and `read_bytes` agree; move `__aiter__` inside the guarded block;
add a close fault to the fake.

### T6 🟠 `AsyncMemoryBackend` declares `LAZY_READ` and `SEEKABLE_READ`

**Proposal:** P5. **Kind:** contradiction (prose against prose), spec-gap. **Clause:** MEM-003
against CAP-007; spec 029.
MEM-003 has the async class declare `LAZY_READ` for "its one-chunk read stream
being lazy"; CAP-007 says in-memory, pre-loading backends do not declare it.

**Checked:** probes `c3/lazy.py` and `c2/measure.py` § L re-run; MEM-003, CAP-007 and ASYNC-084 opened.

- MEM-003: spec 013 l.229-232. CAP-007: spec 003 l.55. ASYNC-084 (spec 029
  l.526) preserves the flag through the sync adapter, citing ASYNC-080.
- `AsyncMemoryDriver.get` copies the whole value under the lock and yields it
  once (`aio/backends/_memory.py:67-71`). Probe:
  `LAZY_READ declared=True; file=4194304 chunks=1 first_chunk=4194304`.
- The async class also declares `SEEKABLE_READ` (`set(Capability) - {GLOB}`,
  `aio/backends/_memory.py:26`) with a forward-only async generator; CAP-007
  defines the flag by `stream.seekable()`.
- The only async laziness test exempts it:
  `tests/e2e/test_async_streaming_integrity.py:8-10, 302-308` ("capability
  vs. behavior diverge"). `hatch run backlog-find LAZY_READ` finds no item.

**Disposition, with the reasoning asked for at triage.** `LAZY_READ` should
mean per-chunk pull: memory held by a read is bounded by the chunk size, not
the file size, so a caller reading a prefix of a large object never holds the
whole of it. That is the promise CAP-007 and SIO-009 make ("pulled as the
caller reads"), and the one a caller checks the flag for. The alternative,
"nothing is fetched before the first iteration", states only timing: a driver
that buffers a 10 GB object into one chunk on the first `__anext__` would
satisfy it, so the flag would stop protecting memory exactly where an async
driver over S3 or Azure needs it. Memory holds the bytes already, so it has
no fetch to defer; per CAP-007 neither Memory class declares `LAZY_READ`, and
the async one also withholds `SEEKABLE_READ`. Spec 029 then defines both flags
for an async read, and an async conformance cell replaces the e2e exemption.
MEM-003 is amended to match.

### T7 🟠 Kernel `glob` through an item raises where listings answer empty

**Proposal:** P2. **Kind:** contradiction between spec prose and a test. **Clause:** BE-032 A.5,
A.8.
BE-032 A.5 puts `glob` in the folder-read family "over its pattern's literal
prefix", and A.8 rule 4 replaces a listing's refusal by the probe when the row
holds nothing; the kernel's `glob` catches only `NotFound`, and a test asserts
that every other refusal propagates.

**Checked:** probe `c4/m5_kernel_glob.py` re-run; A.5, A.8 and the test opened.

- Spec 003 l.1808 (A.5 family row), l.1894-1900 (A.8 rule 4). A.3 l.1756
  defers glob's omissions and `stat` to BK-439, not A.8's refusal handling.
- Code: `_sync/kernel.py:1215, 1227` (async `1232, 1244`) against the
  listings' `_holds_nothing` (`_sync/kernel.py:624-647`).
- Test: `tests/_kernel/test_condition_space.py:7-9, 42-63`, over every driver
  shape in `DRIVERS`, hierarchical included.
- Probe, a `MemoryDriver` whose `glob` refuses a pattern through the item
  `f.txt`, as A.8 allows a wire's ENOTDIR to arrive:
  ```
  InvalidPath:      list_files('f.txt/x') -> []   glob('f.txt/x/*') -> InvalidPath
  PermissionDenied: list_files('f.txt/x') -> []   glob('f.txt/x/*') -> PermissionDenied
  ```

Rule 7: the test asserts the code's behaviour, so the prose is not
automatically right; which side moves is open (§ Open questions). BK-439
covers flat drivers only.

### T8 🟠 The shared glob regex differs from a Unix glob

**Proposal:** P2. **Kind:** contradiction, undecided under Rule 7. **Clause:** GLOB-014, GLOB-011.
`pattern_to_regex` accepts a `**` that ends a segment and matches across `/`;
its character classes can match `/`; `[^x]` is negation there and literal in
`fnmatch`; a malformed class raises `re.PatternError`, not a `ValueError`.

**Checked:** probe `c4/m2_regex.py` re-run; GLOB-014 opened.

- Code: `_glob.py:92-102` checks only the character after `**`.
- Probe, Memory (fallback, no `GLOB`) against Local (native) on one tree:
  ```
  'a**'          Memory ['a[b','ab/c.csv','abc']   Local ['a[b','abc']
  'd**/c.csv'    Memory ['d/e/c.csv','dx/c.csv']   Local ['dx/c.csv']
  'd[!x]e/c.csv' Memory ['d/e/c.csv']              Local []
  'd[/]e/c.csv'  Memory ['d/e/c.csv']              Local []
  'd[^x]e'       Memory ['d^e','dae']              Local ['d^e']
  '[z-a]'        Memory re.PatternError            Local []
  ```
  `issubclass(re.PatternError, ValueError)` is `False`; Tier 1
  `list_files("", pattern="[^x]*")` answers `[]`.
- GLOB-014 (spec 018 l.190-192) says a `**` inside a segment raises
  `ValueError`; only the leading form is tested (`tests/test_glob.py:406-408`).
- Called at `ext/glob.py:71`, `_s3_base.py:666`, `_s3_boto3.py:809`,
  `_azure.py:1347`, `aio/backends/_azure.py:1221`, `_sqlalchemy.py:1383, 1821`
  (`rg "pattern_to_regex\(pattern\)" src/`, 7 hits). The first is
  `glob_files`' fallback for every store that does not declare `GLOB`, the
  path the probe's Memory column runs through; the rest are native globs.
  It is also the natural helper for a Memory `SupportsGlob` (BK-446).

**Disposition:** decide the dialect in GLOB-014 (a class never matches `/`;
the meaning of `^`; the error type), then cells comparing fallback and native.

### T9 🟠 A driver's listed and `stat`ed keys are trusted

**Proposal:** P1. **Kind:** spec-gap. **Clause:** BE-014, BE-015, BE-032 A.8 (what drivers owe).
The kernel neither checks that a listed key lies under the listed prefix nor
that `stat(k)` returns key `k`.

**Checked:** probe `c1/probe1.py` (P3, P4, P4b) re-run.

- Code: `_files_of`, `_folders_of` (`kernel.py:1108-1141`) filter only by
  `_keys.listable` and A.3; `_file_info` takes the path from `entry.key`
  (`:626-637`).
- Probe:
  ```
  stat('a') returns Entry('zzz/other') -> get_file_info('a').path == 'zzz/other'
  list_page('d') also returns 'e/g'    -> list_files('d') == ['d/f', 'e/g']
  list_page('d') also returns 'x/y'/   -> list_folders('d') == ['x/y']
  ```
- A.8's driver obligations (spec 003 l.1950-1974) state neither.

**Template impact:** a flat driver listing `d` instead of `d/` leaks `dx/...`.
**Disposition:** add both to the obligations with a cell, or have the kernel
omit and log such keys as BE-030 does.

### T10 🟠 `namespace` and `parents` are not checked against their domain

**Proposal:** P1. **Kind:** spec-gap, untested. **Clause:** BE-032 A.2, BE-030.
`self._flat = driver.namespace == "flat"` (`kernel.py:322`), so any other
string is hierarchical, and `parents` is compared only to `"none"` and
`"explicit"`.

**Checked:** probe `c1/probe1.py` (P1, P1b, P1c) re-run.

- Probe, both runtimes: `namespace="Flat"` constructs, and writing `k/a.txt`
  below the item `k` succeeds (`files=['k', 'k/a.txt']`), a state A.4 rules
  out; `namespace="object"` and `parents="None"` construct.
- `test_a_driver_whose_declarations_its_protocols_cannot_back_is_refused`
  (`test_condition_space.py:250`) crosses only valid values.

**Disposition:** refuse an out-of-domain value at construction; one cell.

### T11 🟠 `unwrap` bypasses the closed guard

**Proposal:** P0, P1. **Kind:** spec-gap. **Clause:** BE-020, BE-022, BE-030 step 1.
`unwrap` is forwarded with no closed guard and no choke point
(`kernel.py:350-352`); BE-030 exempts only the addressing members.

**Checked:** probes `c1/probe5.py` and `c1/probe1.py` (P7) re-run.

- Probe: on a closed kernel with `close_is_terminal=True`, `unwrap(FakeStore)`
  returns the handle while `exists("a")` raises `BackendUnavailable`; both
  runtimes.
- `S3Backend` refuses today: its accessor calls `_raise_if_closed`
  (`backends/_s3.py:542-546, 573-574`).
- The kernel fake's `unwrap(int)` raises `TypeError`
  (`tests/_kernel/_fake.py:600-603`), not BE-022's `CapabilityNotSupported`;
  Memory's driver is right (`backends/_memory.py:122-127`).

**Template impact:** the first terminal driver (S3, Azure, Graph) would hand
out a client after close. **Disposition:** state `unwrap`'s posture in BE-030;
state BE-022's refusal in the driver protocol; fix the fake.

### T12 🟠 Capability gate before the closed guard: model and BE-020/027 disagree

**Proposal:** P3, P6. **Kind:** model-gap, doc-drift. **Clause:** BE-030 § Gates, BE-020, BE-027.
The kernel refuses an undeclared `MOVE` or `COPY` with
`CapabilityNotSupported` before the closed guard, pinned by
`test_condition_space.py:164-233`; the model and two prose clauses say a
closed backend answers first.

**Checked:** probe `c5/probe1.py` § 4 re-run; `Move` clauses, BE-027, the `in capabilities` grep and the trait-method enumeration run.

- Probe, closed terminal backend without `MOVE`/`COPY`:
  `move('s','d'): CapabilityNotSupported`, `copy('s','d'):
  CapabilityNotSupported`.
- Model: `Move` ensures `!old(Live()) ==> r == Err(BackendUnavailable(name))`
  unconditionally (`BackendContract.dfy:1110-1111`); `Copy` the same (`:1229`);
  no `CapMove` or `CapCopy` clause (`rg "in capabilities"
  sdd/formal/BackendContract.dfy`). The comment at `:554-561` and BE-020's
  formal note (spec 003 l.725) say closed answers "ahead of every other
  clause".
- BE-027 (spec 003 l.1322, 1336): "Backend has no runtime `_gate()`
  equivalent"; enforcement "by `Store._gate()`". Stale on the kernel.
- `sdd/formal/README.md:282` claims "all operation pre/postconditions". The
  `Backend` operations with no `method` in the trait are `read_bytes`,
  `read_seekable`, `write_atomic`, `open_atomic`, `iter_children`, `glob`
  and `check_health`; `unwrap`, `to_key`, `native_path` and `resolve` are
  absent too (`rg -n "^    def [a-z]" src/remote_store/_backend.py` against
  `rg -n "^\s*method " sdd/formal/BackendContract.dfy`, 15 methods).
- `glob`'s exclusion rests on a premise the kernel no longer meets:
  `BackendContract.dfy:89-92` says it "delegates to ListFiles + pattern
  matching", but the kernel's `glob` calls the driver's `SupportsGlob.glob`
  with its own NotFound handling (`_async/kernel.py:1229-1248`, T7).

Rule 7: the test decides; model and prose are stale. Latent for Memory, which
declares both. **Disposition:** add the gate to `Move` and `Copy` ranked first;
amend BE-020's note, BE-027 and the README sentence.

### T13 🟠 The aggregate push-down skips BE-030's omission

**Proposal:** P1, P3. **Kind:** contradiction, model-gap. **Clause:** BE-030, BE-017.
BE-030 omits non-canonical keys from listings and aggregates and says a native
aggregate "owes the same omission"; `MemoryTree.folder_stats` counts every
node, and the model guards only `DeleteFolder` with `CanonicalUnder`.

**Checked:** probe `c5/probe1.py` § 1 and § 1b re-run.

- Spec 003 l.1533-1544. Code `_memory_tree.py:252-272`. Model
  `BackendContract.dfy:936-956`; the listing and aggregate completeness clauses
  (`:1006-1011`, `:1041-1043`, `:1078-1081`) count every key.
- Probe, `a/ok` (2 B) written, `a/./hidden` (3 B) and `a/sl\ash` (1 B) planted
  through the driver:
  ```
  list_files('a', recursive=True)            -> ['a/ok.txt']
  get_folder_info('a'), folder_stats push-down -> (3, 6)
  get_folder_info('a'), listing fallback       -> (1, 2)
  ```
- Unreachable on Memory through the public API
  (`tests/_kernel/test_encoding_observations.py:51-64` says so); reachable on
  S3, SFTP and Azure, which hold keys other tools write.

**Disposition:** filter `folder_stats` with `_keys.listable`; add the
`Canonical` guard to the model's listing and aggregate clauses; a push-down
omission cell for the first driver that can hold such keys.

### T14 🟠 The oracle runs keys outside the domain it was proven for

**Proposal:** P3. **Kind:** model-gap. **Clause:** BE-030 key rule; the formal README's
compiled-oracle principle.
`tests/backends/dafny/_helpers.py:76-79` maps only `""` and `"."`, and the
compiled Python does not check `WellFormedPath`.

**Checked:** probe `c5/probe1.py` § 2 and § 5 re-run.

- Probe:
  ```
  write('d//f'); exists('d/f')     kernel True        oracle False
  list_folders('') after d//f, e/./g kernel ['d','e']  oracle ['d','e','d','e']
  write('h\\i')                    kernel InvalidPath oracle stores 'h/i'
  move('k/f','k//f'); exists('k/f') kernel True        oracle False
  ```
- No conformance cell uses such keys today (`rg` for `//"`, `"./`, `/./` and
  `\\` in `tests/backends/conformance` finds only root spellings), so it is
  latent; it blocks any BE-030 conformance cell.

**Disposition:** route adapter calls through a verified raw-key entry, as
`RootPath.dfy` § 5 does for root spellings, or refuse such keys in the
adapter.

### T15 🟠 `metadata={}` comes back as `{}`, stored as `None`

**Proposal:** P1. **Kind:** contradiction, undecided under Rule 7. **Clause:** WR-012 (WR-010,
WR-011).
`write(..., metadata={})` returns `WriteResult.metadata == {}` while the
stored file has `None`; the model says `None`.

**Checked:** probes `lead_v_meta.py`, `c2/measure.py` § E/F and `c5/probe2.py` re-run.

- Code: `_memory_tree.py:133` stores `None`, `:145` returns
  `PutResult(metadata=metadata)`; the kernel copies it through.
- Model: `BackendContract.dfy:829-833` with `HasUserMetadata` non-empty
  (`:170-173`).
- Probe: sync and async `{}`; oracle `None`. On a subclass without
  `USER_METADATA` the field is still `{}`, which BK-239's populated-field check
  never sees (`test_atomic.py:362` passes `None`).
- Prose: spec 045 l.348 "passed: verbatim" against WR-011 (l.339-342) `{}`
  equivalent to `None`. No test asserts the `{}` echo.

**Disposition:** decide in WR-012 and normalise in one place (the kernel);
one cell.

### T16 🟠 The `open_write` route's overwrite duty is unstated

**Proposal:** P0, P1. **Kind:** spec-gap (driver docs). **Clause:** `SupportsOpenWrite`,
`WriteHandle`.
Who refuses an existing target under `overwrite=False` is stated for `put`
only (`_sync/driver.py:88`); `open_write` (`:208-216`) and `commit`
(`:186-188`) are silent, and the kernel makes no existence check on that
route.

**Checked:** probe `c6/s6_openwrite.py` re-run.

- Probe, flat driver whose handle ignores `overwrite`:
  ```
  write_atomic onto existing, overwrite=False -> OK, value b'new'
  calls: list_page x limit=1, open_write x False, commit x
  ```
- Memory refuses at open and at commit (`backends/_memory.py:142-150,
  187-188`), undocumented. Conformance `test_atomic.py:61, :146` catch it
  for registered fixtures only.

**Disposition:** state the duty on `open_write` and `commit`.

### T17 🟠 CONTRIBUTING sends new backends to the `Backend` ABC

**Kind:** doc-drift. `CONTRIBUTING.md:84-85` calls the guide "a full
walkthrough of the `Backend` contract", and step 2 (`:88`) says "Implement
`Backend` ABC". The guide calls a driver "the documented route" (guide
l.53-58) and links back to that step (guide l.577). Every in-repo backend
starts from this checklist. **Disposition:** rewrite steps 2 and 3 as a driver
plus a `DriverBackend` subclass, linking the guide.

**Checked:** `CONTRIBUTING.md:84-88` opened; guide lines first pass only.

### T18 🟠 Memory's counters are unpinned, and two clauses misstate them

**Kind:** untested-clause, doc-drift. **Clause:** MEM-004, MEM-014, MEM-016,
MEM-016b.
MEM-016 says `file_count` "is unchanged" on move (spec 013 l.391) and MEM-016b
"increments by 1" on copy (l.409); the code correctly decrements or skips when
the destination is replaced (`_memory_tree.py:197-198, 206-207`).

**Checked:** probe `c2/measure.py` § A re-run; MEM-016/016b lines and the counter grep run.

- Counter assertions (`rg "files=\d+, folders=\d+|\.counts\b" tests`):
  `test_coverage.py:476, 483, 498`, `aio/test_copying.py:27`,
  `aio/test_driver_open_write.py:45, 93`. None follows a `delete`, a
  `delete_folder`, or a replacing move or copy.
- A 16-operation sequence in both runtimes matched a tree walk, so the
  behaviour is right today.

**Disposition:** a counters-against-walk invariant in the stateful property
test, both runtimes; fix the two sentences.

### T19 🟠 mtime on move, copy and folders is unpinned and unmodelled

**Proposal:** P3 (model half). **Kind:** untested-clause, model-gap. **Clause:** MEM-015, MEM-016, MEM-016b.
Move keeps `modified_at`, copy sets a new one, a folder's is the maximum; the
behaviour holds in both runtimes, but tests assert only `is not None`.

**Checked:** probes `c2/measure.py` § G and `c2/measure3.py` re-run; the `modified_at` grep run; the two Dafny lines first pass only.

- `rg "modified_at\s*(==|>|!=|<|is None)" tests` outside other backends'
  directories: `test_folder_info_depth.py:108`, `_kernel/test_kernel.py:938`,
  both `is None`. The MEM-016b cell (`test_atomic.py:524-530`) checks bytes
  only.
- Model: copy sets `last_modified` to `None` (`MemoryBackend.dfy:1219-1220`);
  `FolderInfo` has no time field (`BackendContract.dfy:153`).

**Disposition:** pin the three clauses in both runtimes; decide whether the
contract owns copy and move mtime.

### T20 🔴 No interaction protocol with states joins `Store`, kernel, driver and `Session`

**Proposal:** P0. **Kind:** spec-gap. **Clause:** BE-020, BE-030, RFC-0017 D2
and D5, ASYNC-088.
The contract is stated call by call, as each operation's pre- and
postconditions, and the Python `Protocol` classes fix signatures. No artifact
states the interaction as a protocol in the sense of TCP or OAuth: the states
each party passes through, which call is legal in which state, which
transitions a failure, a cancellation or a close takes, and which party owns
each exit (close, abort, invalidate) on every path.

**Checked:** grep run; `ResourceSafety.dfy` §1 and §3 opened; RFC-0017 D3 and D5 opened.

- `rg -n -i "state machine|lifecycle|state diagram|stateDiagram"` over specs
  003, 005, 006, 007, 022, 026, 029, RFC-0017, RFC-0021, ADR-0042, ADR-0047 and
  `sdd/formal/README.md` hits fragments only: RFC-0017 D5 and D8, ADR-0042's
  `Session` bullet, SAW-015 (an otel span), ASYNC-088 (`close(timeout)`), and
  the formal README's `ResourceSafety.dfy` rows. None defines states or
  transitions across the parties.
- The states exist, scattered: the backend's closed posture, terminal or not
  (BE-020); the `Session`'s connect, invalidate and reconnect (RFC-0017 D5,
  l.494-531, an interface with no states); a write handle's open, commit or
  abort (`_kernel/_sync/driver.py`, `WriteHandle`); a read stream's open,
  iterate, fail, abandon and close; a listing's page cursor.
- `ResourceSafety.dfy` models a handle lifecycle (§1, `_safe_wrap` in
  `_stream.py`) and a connection lifecycle (§3, the BUG-144 pattern), both of
  the pre-kernel classes, not of the kernel's parties.
- The `Session` lands at D3 step 2 with the first remote driver (RFC-0017
  l.374-376) and is "the same lifecycle entry, so `unwrap`, `close` and
  connect-time classification have one path" (l.529-531). Memory has no
  `Session` (l.497), so this audit observed only the session-less half.
- Symptoms already found here, each a transition nobody owns: a failing close
  after a read error (T5); `unwrap` after close (T11); the `open_write`
  route's overwrite duty (T16); and the lower-ranked rows on repeated `close`,
  async `connection_dead`, cancellation routes and async refusal timing.
  BK-448 (filed after `52448e0`) is the write-side sibling: the async kernel
  leaves a caller's content iterator suspended on refusal.

**Template impact:** every remote driver from step 2 on implements a
`Session` against a protocol that names its methods but not its states; each
decides alone what `close` after `invalidate`, `unwrap` after close, or a
cancel mid-stream means. **Disposition:** P0.

---

## Lower-ranked

Recorded, not gated. Each was measured or read as its evidence column says.

| Finding | Kind | Evidence | Checked |
|---|---|---|---|
| Async `connection_dead` is required but never called | spec-gap | Required through `vars(AsyncDriver)` (`_async/kernel.py:116-130`); `rg connection_dead src/remote_store/_kernel` hits the two protocol definitions and `backend.py:64` (sync) only; no async SIO-010 counterpart | `connection_dead` grep run |
| Driver return shapes are not validated, and fail inconsistently | spec-gap | `stat` returning `str`, `put` returning `None`, `list_page` returning `None` raise raw `AttributeError`; a 2-tuple from `folder_stats` is mapped (inside the choke); negative counts are accepted; `kind="dir"` reads as a folder (`kernel.py:472`) | `c1/probe1.py` P2, P5, P9, P9b, P10, P13 |
| `container_absent` applies only to untyped errors, unstated in BE-021 | spec-gap | `kernel.py:399-401`; BE-021 kernel row l.772; asserted by `test_kernel.py:498`; a typed `BackendUnavailable` from `delete` defeats `missing_ok` | `c1/probe1.py` P6, P6b |
| `ensure_parents` used only with `parents="explicit"`; `SupportsRename` needs `rename_replaces` | doc-drift | `_sync/kernel.py:317-319`; guide l.344-345 "define the method, and the kernel uses it"; the MOVE refusal message names no missing member | `c6/s2_behaviour.py`; kernel line opened |
| MEM-020's invalid-path row is not the kernel's alone | spec-gap | `MemoryTree` raises `InvalidPath` at `_memory_tree.py` 101, 117, 135, 156, 160, 168, 178, 188, 223 (`rg "raise InvalidPath"`); the table has no wrong-type row | `raise InvalidPath` grep run |
| Async `read` refusals surface on the first iteration | spec-gap | `read('nope')`, `read('../x')` and a closed terminal `read` return an async generator; the error comes at `__anext__`; ASYNC-006 states no timing | `c3/lazy.py`, `c3/streams.py` |
| Kernel `write_atomic` cancellation routes untested | untested-clause | Correct on the handle and temp-plus-rename routes when measured; `tests/aio/test_async_cancellation.py` covers Memory's `put` route only | `c3/cancel.py` |
| Error `path` is canonical after normalisation, raw on refusal | spec-gap | `read_bytes('x//missing')` gives `NotFound` with `path='x/missing'`; `read_bytes('a/../b')` gives `InvalidPath` with the raw path; ERR-001 and ERR-002 do not say which | `c1/probe3.py` |
| Driver `move`/`copy` precondition `src != dst` stated in the guide only | spec-gap | `MemoryDriver.move("k", "k", overwrite=True)` leaves counts `(0, 0)` against a walk's `(1, 0)`; the kernel short-circuits (`kernel.py:961-964`). The guide states it (`custom-backend-guide.md:347-348`, "A move or copy onto itself never reaches your driver"); the protocol docstrings do not (a case-insensitive `rg` for `itself`, `src == dst` or `src != dst` over both `driver.py` files hits only `delete`, `list_page`, `delete_tree` and `ensure_parents`), and spec 003 only orders the source check "for a self-operation" (l.1498-1500) | `c2/measure.py` § A2; guide, driver and spec lines opened |
| `Op.IDENTITY` and `Op.MONITOR` never reach `classify` | doc-drift | Only the enum (`_model.py:47-48`) and `_CLASSIFY_DECIDES` (sync `kernel.py:63`, async `:76`) | grep run |
| Driver `close` must tolerate repeats, unstated | untested-clause | A second `Backend.close()` reaches the driver; a non-idempotent driver close gives `RemoteStoreError: native RuntimeError`; spec 003 l.725 says close stays callable | `c6/s6_openwrite.py` |
| Negative `max_depth` at the backend: model unlimited, kernel empty | spec-gap | `BackendContract.dfy:963, 1000`; kernel `list_files('x', recursive=True, max_depth=-1)` gives `[]`, oracle every file; DEPTH-003 silent | `c5/probe1.py` § 3 |
| `StoreTree` names admit `.`, `..`, `\`, NUL | model-gap | `StoreTree.dfy:55`; the "Not modelled" list (`:42-46`) names links, empty segments, page-by-page omissions and changes under an operation, not these names | lines opened |
| BE-030 and BE-031 cannot carry an `@spec` tag | doc-drift | `scripts/check_formal_trace.py:10-11` counts markers under `tests/backends/conformance/` only; the cells live in `tests/_kernel/` | script docstring opened |
| Tier-1 `list_files(pattern=)` folds case on Windows | spec-gap | `_store.py:497, 551` use `fnmatch.fnmatch` (`normcase`); spec 051 compares names exactly; measured by simulating `ntpath` only | `c4/m3_tree.py` (simulated) |
| GLOB-012 prose against its test for an all-literal pattern | doc-drift | Prose gives `data/file.csv`; `tests/test_glob.py:332` asserts `"data"` | test line opened |
| GLOB-015 has no spec-marked test | untested-clause | `tests/ext/test_glob.py:200-202` "exercised implicitly" | `c4/m4_cov.py` |
| The glob guide's native-glob list omits the SQL backends | doc-drift | `docs-src/guides/glob-pattern-matching.md:86-88, 164`; `_sqlalchemy.py:49` declares `GLOB` | guide lines opened |
| MEM-DS-003, MEM-DS-004, MEM-041 figures | doc-drift | A 10 MB buffer overwritten with 1 KB shrinks (10000057 to 1057 B by `sys.getsizeof`); overwrite peak is 1.00x content (`tracemalloc`); per-entry sizes on CPython 3.13.16 differ from the 3.12 figures | `c2/measure.py` § B, C, K; `c2/measure4.py` |
| MEM-030 "56-test conformance suite" | doc-drift | Spec 013 l.520; `pytest tests/backends/conformance -k "memory and not async and not dafny" -rs` gave 316 passed, 8 skipped, every skip capability or opt-in gated | pytest command re-run |
| `content_type` is a dead field in Memory | spec-gap | Set only at `_memory_tree.py:31, 57, 211`, never supplied; MEM-016b's "copied" is vacuous | grep run; `c2/measure.py` § G |
| MEM-tagged conformance cells never run on async Memory | untested-clause | `pytest --collect-only -k memory_async` over the MEM-tagged files collects none; async snapshot timing differs (first iteration, not call) | collect command re-run |
| The generated sync twin drops the contract prose | doc-drift | `scripts/gen_sync_kernel.py:88-94` replaces each module docstring; the "addressing members must stay total" sentence is in the async source only | generator lines opened |
| Guide: "nothing checks that the two agree" | doc-drift | ID-159 (`tests/backends/conformance/test_identity.py:44-48`) checks instance capabilities against `CAPABILITIES`; construction checks nothing | guide and test lines opened |
| Guide: `size_probe` typed only as "callable" | doc-drift | The real contract is `(inner_stream) -> int` (`_stream.py:123-125, 217`) | guide line opened; `_stream.py` lines first pass only |
| Guide: `store.glob()` "raises" | doc-drift | It raises at iteration; the call returns a generator | `c6/s2_behaviour.py`, `c6/s3_more.py` |
| Guide: a typed driver error "passes through unchanged" | doc-drift | A driver `PermissionDenied` for an absent key surfaces as `NotFound`; the kernel's probes re-type it | `c6/s3_more.py` |

---

## Open questions

**T7: which side moves.** (a) The kernel gives `glob` the listings' first-page
probe over its literal prefix and `test_condition_space.py` is amended, so
`glob` through an item answers empty like every listing; this could widen
BK-439 beyond flat drivers. (b) BE-032 A.5 is narrowed to say only the listing
bound applies to `glob`, and code and test stay. Left open at triage; P2's
defining clause is where it is decided.

---

## Proposals

Advisory, per CLAUDE.md § Audits: the diagnosis above is the audit's
authority, and whoever implements a proposal re-weighs it against the
findings it cites. Each proposal is required because a later driver inherits
the gap it closes; none adds a tree axiom, since the tree came back clean.

### P0 An interaction protocol with states

**Claim.** `Store`, kernel, driver and `Session` interact through calls whose
legality and cleanup depend on state, yet only the calls are specified (T20).
P0 states the interaction as a protocol: the parties' states, the transitions
each call, failure, cancellation and close takes, and the party that owns each
exit. It is the frame P1's clauses and P5's flag meanings sit in.

It decides:

- the state sets: the backend (constructed, open, closed terminal or not,
  BE-020); the `Session` (unconnected, connected, condemned, reconnecting,
  RFC-0017 D5); and per operation a read stream (opened, iterating,
  exhausted, failed, abandoned, closed), a write handle (opened, committed,
  aborted), a listing's cursor, and a caller's content iterator (BK-448);
- each call's meaning in each state: the closed guard, `unwrap`, a repeated
  `close`, when a refusal surfaces (at the call or at the first iteration);
- the owner of each exit on every path, cancellation included: who closes a
  stream after a failure, who aborts a handle, who invalidates a condemned
  connection and who skips the second wait on it (SIO-010's async gap);
- where it is stated and checked: a spec 003 section, a state model in the
  formal layer (the TLA+ `Observer.tla` or `ResourceSafety.dfy`'s state
  tracking are the precedents), and one conformance cell per transition, run
  against a session-less and a `Session` driver.

**Absorbs:** T20, the state half of T5, T11 and T16; the lower-ranked rows on
repeated `close`, async `connection_dead`, cancellation routes and async
refusal timing; BK-448.

### P1 Driver boundary contract

**Claim.** Every later driver implements the boundary between what it
observes and what the kernel decodes, and that boundary's failures are wrong
answers, not errors. Today the trust is partly stated (BE-032 A.8's
obligations), partly unchecked, and partly enforced only by Memory, and the
kernel decodes driver records at scattered sites: `_keys.listable` filters at
async `kernel.py:1119, 1134, 1254, 1470-1473, 1525` (`rg -n "listable"`), each
a site a new operation must remember. The `folder_stats` push-down at `:1277`
returns a count, which no kernel step can filter, so its omission (T13) is a
driver obligation, not a decode-step site. P1 gives every item one owner and
enforces the kernel's items with one mechanism, so a new kernel operation
cannot forget a check.

Owners, each a kernel check, a driver obligation or a `Session` obligation
(RFC-0017 D5):

| Item | Owner | Mechanism |
|---|---|---|
| A listed key lies under the listed prefix; `stat(k)` names `k` (T9) | kernel check | decode step |
| Canonical-key omission (BE-030) on listings | kernel check | decode step |
| The same omission in a native aggregate (T13) | driver obligation; the kernel cannot filter a count | stated with `SupportsFolderStats` |
| Metadata in `FileInfo` and `WriteResult` is a copy (T1); `{}` against `None` (T15) | kernel check | decode step |
| Driver return shapes | kernel check | decode step |
| `namespace`, `parents` in their domain (T10); optional protocols implemented, not inherited (T2); `rename_replaces`; `ensure_parents` only with `explicit` | kernel check | declaration record |
| `open_write` and `commit` refuse an existing target without `overwrite` (T16) | driver obligation | stated on the protocol |
| `src != dst` on driver `move` and `copy` | kernel guarantee to the driver | stated on the protocol |
| One caught set for `read`, `read_bytes` and the ranged read (T4) | kernel check | stream adapter |
| A failing close never masks a read failure; async close guarded like sync (T5) | kernel check | stream adapter |
| `container_absent` applies to untyped errors only | kernel check, stated in BE-021 | choke point |
| `unwrap` after close (T11) | `Session` obligation for remote drivers (D5: `unwrap` goes through `run`); the kernel's closed guard for session-less ones | P0 |
| Repeated `close`; skipping a second wait on a condemned connection | `Session` obligation; the kernel's for session-less drivers | P0, stream adapter |

The mechanisms:

- **(a) One decode step** that every `Entry`, `Page` and `PutResult` passes
  before the kernel uses it: domain and shape check, mapping copy,
  canonical-key omission, key under prefix, `stat` names its key.
- **(b) One stream adapter** shared by `read`, `read_bytes` and the ranged
  read: one caught set, one close policy, one cancellation path.
- **(c) One declaration record** validated once at construction: namespace,
  parents, capabilities, presented protocols with the body check,
  `rename_replaces`, `ensure_parents`.

The absorbed findings become the acceptance tests of (a), (b) and (c).

**Absorbs:** T1, T2, T4, T5, T9, T10, T11, T13 (driver half), T15, T16; the
lower-ranked rows on return shapes, `container_absent`, close repeatability,
the self-move precondition and async `connection_dead`.

### P2 Glob in tree terms

**Claim.** `glob` is the one folder read that names no key, so BE-032 can only
approximate it ("over its pattern's literal prefix"), and fallback and native
already disagree on one tree (T8). P2 defines `glob(p)` as the files of the
tree whose path matches `p`, makes the kernel's prefix listing and probes
optimisations judged against that, and fixes one pattern dialect.

It decides: the defining clause and how A.5 cites it (which decides T7's open
question); whether a character class may match `/`; what `^` means in a
class; `**` as a whole segment only; the error type of a malformed pattern;
what `\` means (BK-447).

**Absorbs:** T7, T8, BK-439, BK-447; the lower-ranked rows on GLOB-012's prose,
GLOB-015, and Tier-1 case folding.

### P3 One formal truth

**Claim.** `StoreTree.dfy` states the tree; `BackendContract.dfy`, which the
compiled oracle runs, still ranges over a path map and never sees an encoding
(BK-434). Two models of one store drift: T3, T12, T13, T14, T19's model half
and the `StoreTree` name gap are that drift. In T3, T12 and T14 the model, not
the kernel, was wrong; in T13 both were. Recommended at triage: the model gates driver acceptance, so
`BackendContract` is refined against `StoreTree`, with BE-030's key rule
inside its domain.

It decides: BK-434's open choice (refinement lemmas per encoding, or one
encoding-parametric trait); how the oracle adapter reaches the key rule
instead of passing raw keys (T14); the trait methods the model lacks
(`read_bytes`, `read_seekable`, `write_atomic`, `open_atomic`,
`iter_children`, `glob`, `check_health`, and the non-I/O members, T12),
including `glob`, whose exclusion premise (`BackendContract.dfy:89-92`) is
stale and which P2 redefines; where kernel-only cells count for traceability.

**Absorbs:** T3, T12, T13 (model half), T14, T19 (whether the contract owns
copy and move mtime); the lower-ranked rows on
`StoreTree` names, negative `max_depth`, and BE-030/031 traceability.

### P4 The template is a set: Memory and a flat reference driver

**Claim.** Both Memory drivers are hierarchical with implicit parents
(`backends/_memory.py:43-44`, `aio/backends/_memory.py:39-40`) and hold the
tree directly, so flat decoding, the `list_page` byte-order obligation, A.3's
shadow omission and `stat`, and A.4's ancestor checks run only against the
kernel's test fake (`tests/_kernel/_cells.py:37-42`, shape `flat-none`). The
flat drivers of D3 (S3, Azure, SQLAlchemy) would have no reference to copy,
and the first of them would become the template by accident. P4 makes the
template a reference set with a flat member.

It decides: the members of the set; which kernel and conformance cells each
runs; that both Memory drivers present `SupportsGlob`, so P2 has a real runner
(BK-446).

**Absorbs:** the template coverage behind T13 and BK-446; the lower-ranked row
on MEM-tagged cells that never run on async Memory, for the async member.

### P5 One meaning per capability flag, checked in each runtime

**Claim.** One `CapabilitySet` crosses runtimes unchanged: the sync kernel is
generated from the async source, and ASYNC-084 preserves a flag through the
sync adapter. A flag that promised different things per runtime would carry a
different promise through every adapter, so a caller checking `LAZY_READ` on an
adapted backend could not know which holds. P5 gives each flag one meaning and
checks it by conformance in both runtimes; where an async read cannot keep a
flag's meaning, the async side withholds the flag rather than redefine it.

It decides: `LAZY_READ` as per-chunk pull, so a read holds at most a chunk,
never the file (T6's reasoning; CAP-007 and SIO-009 already say so for sync);
`SEEKABLE_READ` withheld by async backends, whose read is a forward-only
generator; whether any other flag cannot hold across runtimes; the async
conformance cell that replaces the e2e exemption.

**Absorbs:** T6.

### P6 One owner per check between `Store` and kernel

**Claim.** Two layers own the same checks. `Store` gates capabilities per
operation (`_store.py:1011-1017`, 18 call sites by `rg "self._gate\(" src/remote_store/_store.py`,
`move` at `:631`, `copy` at `:665`) and validates paths through `RemotePath`
(`_full_path`, `:1019-1032`); the kernel also gates capabilities (BE-030; T12)
and validates and normalises keys (BE-030). Each migrated backend inherits
whichever split is in place. P6 assigns each check to one layer.

It decides: which layer owns capability gating, path validation and
normalisation, and error-path attribution (canonical or raw, the lower-ranked
row); what the other layer keeps (none, or a documented fast path); BE-027's
text once the answer is in place.

**Absorbs:** T12 (prose half, BE-027); the lower-ranked row on error `path`
spelling.

### Not proposed

More tree axioms: the tree came back clean. T17, T18, T19's test half and the
doc-drift rows: each is a direct fix with no open choice.

---

## Checked clean

Measured by the probes (`c3/parity.py`, `c3/surface.py`, `c4/m1_glob.py`,
`c4/m3_tree.py`, `c6/s1_surface.py`, `c6/s2_behaviour.py`, `c6/s5_redis.py`)
and re-run with `run_all.py`, or read against the named tests. The Dafny,
oracle and snippet-test figures are the first pass's runs, not repeated.

- **Generated sync kernel:** `gen-sync-kernel-check` up to date; a word diff
  of async against sync `driver.py` and `kernel.py` shows token renames, import
  order and the docstring headers only. The `_io.py` size gap is specified by
  BE-030 § Content.
- **Kernel pipeline:** BE-030 order (gates, closed guard, refusal,
  normalisation, root, WR-010, content), addressing totality, BE-020
  construction posture, the choke point on a classifier returning `None` or
  raising, `BaseException` passthrough, caller-content passthrough, BE-031,
  BE-017 empty-aggregate typing, BE-029 root probes; read against spec 003 and
  pinned by tests in `test_kernel.py` and `test_condition_space.py`.
- **Memory parity:** 48 of 50 operations identical across runtimes in results,
  info fields, error types, messages and `path`; the two differences are
  `TypeError` wording.
- **Memory tree against spec 051 and BE-032:** A.4 write refusals, A.5 folder
  reads on and through an item, A.6 empty folders, name equality (case, NFC
  against NFD), the root.
- **Glob:** whole-segment `**`, leading `/`, `""`, `.` and `/`, dot files,
  absent and file prefixes, newline keys; fallback and native agree.
- **Driver docs:** the 30 `::: remote_store.drivers.X` references equal
  `drivers.__all__`; 14 required primitives and 6 attributes; the construction
  refusals in `drivers.md`; the key rule; write cost; the guide's Redis driver
  (35 snippet tests).
- **Formal:** Dafny verifies; the oracle is fresh; 546 oracle tests pass;
  `RootPath.dfy` tags cite existing IDs; the `folder_stats` differential
  (`tests/test_pbt_folder_info_aggregates.py`) is green.

## Not verified

- Real SDK behaviour when an async stream's `aclose` or `__aiter__` fails; T5
  was measured on fake streams.
- T8 on the S3, Azure and SQL native globs, which need live services; inferred
  from the shared helper.
- Windows case folding, simulated with `ntpath`.
- `AsyncMemoryDriver`'s `asyncio.Lock` across two event loops (ASYNC-094).
- The guide's redis-py claims (redis not installed) and the rendered site.
- Alloy and Lean.
- The `Session` layer (RFC-0017 D5). Memory has none (RFC-0017 l.497) and no
  remote driver is on the kernel yet, so a Memory-driven audit cannot observe
  connect, invalidate or reconnect; T20 and P0 are drawn from the design text,
  not from measurement.
