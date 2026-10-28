# Development Backlog
<!-- doc: repo-only -->

Active work items. [BACKLOG-DONE.md](BACKLOG-DONE.md) holds everything that
left this file: work that shipped, IDs **absorbed** into a surviving item whose
work is still open, and items **decided against**. Only the first is "completed".

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
## How this file works

Operational rules only. Why each rule exists: [ADR-0040](adrs/0040-backlog-as-index.md),
and for the done register [ADR-0041](adrs/0041-done-register-links-dossiers.md).

**Status legend:** `[ ]` pending · `[~]` in progress

**Admission test.** A section is a heading and a **Promise** of at most three
sentences. An item is filed under the promise it serves, or not at all: there is
no holding area. A refused idea gets a
[`BACKLOG-DONE.md` § Decided against](BACKLOG-DONE.md#decided-against) entry,
with `—` for the ID. A section with no items is removed or re-argued with a new
item. `## Release Blockers` is the one standing section: `BL-` items go there by
prefix, and empty is its normal state.

**Ordering.** Within a section, execution sequence: a dependency never sits
below what needs it. Between sections, how directly the promise is felt. A
dependency across sections is stated by ID inside the dependent item.

**Granularity.** Fold work into one item when its fix surface *coincides* with
the host's, or one pending decision resolves both; surfaces that merely
*overlap* stay separate, each naming the other. A sub-bullet is not tracked and
gets no ID for the work it describes. A section that outgrows itself splits into
two promises.

**Item scope.** At most eight
content lines: header; the attribute line; a diagnosis of at most five lines, the
observed problem and the open decision; an optional
`Detail: [dossier](backlog/<id>-<slug>.md)` line.
Blank lines, `---` and anchors do not count. No process steps; those live in
`000-process.md` and the ripple-check.

**Item attributes:** `spec: <IDs or —> · effort: S|M|L · audience: <values>`
directly under the header. S < 1 day, M 1–3 days, L > 3 days, a range takes its upper
bound; audience values from `sdd/traces/_schema.yml`'s enum.

**Dossiers.** `sdd/backlog/<id>-<slug>.md`, marked `<!-- doc: repo-only -->`,
only when an item needs more than eight lines. Converting an item moves its body
there verbatim. The path never moves; a trace's orient phase reads it. Its H1 is
`# <ID> — <index title>` and follows the index title when that changes.

**Item authority.** Each kind of content is corrected where it lives.

| Kind | Lives in | Status | Corrected when re-derivation disagrees |
|---|---|---|---|
| Diagnosis: the observed problem | index | authoritative, current | in the index, same commit |
| Evidence: what was measured, how | dossier | durable record, dated by its commit | a dated correction is added; the original is not rewritten |
| Prescription: fix shape, disposition, line reference, scope claim, reproduction recipe | dossier | advisory, presumed stale | re-derive against the code before acting; correct it in the same commit |

Where a dossier restates the diagnosis and disagrees, the index wins and the
dossier is corrected in the same commit. Agreement is review-enforced.

**Completing work** (same commit as the change):

- Done → delete here; add to `BACKLOG-DONE.md` as `[x]`. For an item with a
  dossier the entry is short: what shipped and where, then the link; its
  evidence and derivations stay in the dossier. Released entries are not
  condensed.
- Partly done → ship the done part as `[x]` under its ID; give the rest a new ID
  here; link both.
- Absorbed → mark the host's sub-bullet `(was PREFIX-NNN, absorbed here)`, in
  that literal form; add a § Absorbed entry naming the host.
- Decided against → delete here; add a § Decided against entry carrying the
  diagnosis, not only the verdict.

Every entry, whatever the outcome, links the item's dossier if it has one; the
dossier stays where it is. Every entry takes the header shape `- [x] **PREFIX-NNN — Title**` (em dash,
`[x]`, ID inside `**`), because
[`gen_backlogid.py`](../scripts/gen_backlogid.py) counts headers only and a
prose line frees the ID. After absorbing or deciding against, sweep
`rg -n '<ID>' -- sdd .claude scripts docs-src tests *.md` and read every hit, plus
the specs the item touched: fix present-tense claims that it is tracked, leave
past-tense narration, never edit an Accepted ADR. No trace is owed
([`CLAUDE.md` § Trace authoring](../CLAUDE.md#trace-authoring)).

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish; only for an item (a defect, or a packaging or release-process fault) whose shipping unresolved costs users more than delaying the release (a minor bug is a `BUG-` in its section). Monotonic, not reset per release. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Evaluated enough to earn a section, not committed to; the open decision is named in the body. |
| `AF-NNN` | Audit finding (retired — use `BUG` or `BK` for new items). |

**Assigning a new ID:** a lone session uses the prefix's value on the
"Next safe IDs" line of `hatch run gen-backlogid-check`, which is safe for that
tree only. Sessions run in parallel mint only IDs reserved for them up front by
whoever dispatches them, one disjoint set each: an unpushed branch is invisible
to every derivation. `hatch run gen-backlogid --check --remote` compares this
tree's new IDs with every pushed branch; re-mint any it reports before either
side merges. Run `hatch run gen-backlogid` after moving items to
`BACKLOG-DONE.md`.

**What is gated:** the rows of [`GATE-INVENTORY.md`](GATE-INVENTORY.md) whose
subject names `sdd/BACKLOG*.md`. The admission test, granularity, section
membership, agreement between an index entry and its dossier, and the short
done entry are review-enforced.

---

## Release Blockers

**Promise:** nothing ships to PyPI while an item here is open; an item is filed
here only when shipping without it resolved would cost users more than delaying
the release.

---

<a id="predictable-failure"></a>
## 1. Failures are predictable

**Promise:** a caller catches one exception type, an absent or denied store
answers the same way on every backend, and the failure they catch says which
failure it was.

- [ ] **BUG-323 — `SFTPBackend.delete_folder` on a link to a folder deletes the target's files, then raises `NotFound`**
  spec: BE-013, BE-021 · effort: S · audience: user.api
  `delete_folder("ld", recursive=True)` with `ld -> realdir` emptied `realdir` and raised
  `NotFound` (atmoz/sftp, `_sftp.py` as on master, 2026-10-12): `_rmtree` lists and removes
  through the link (`listdir_attr` follows the key itself), and the final `rmdir` on the link
  fails. A link nested below the key is removed as an entry. Open decision: none; refuse a
  link at the key with `InvalidPath` (`lstat`) before `_rmtree`.

- [ ] **BUG-276 — A mapped error still reaches the caller with an empty message through five base-class arms**
  spec: ERR-009, AZ-025 · effort: M · audience: user.api
  Seven `RemoteStoreError(str(exc))` sites in five files; five of them, driven
  in the dossier, render `''` from a message-less exception, breaking ERR-009.
  `_errors.py`'s arm is shared by all three S3 backends. Decided (BK-387):
  synthesise a fallback message at all five, the RFC-0017 kernel's ERR-009
  floor; the fix deliberately falsifies AZ-025's blank clause and its test.
  Detail: [dossier](backlog/bug-276-empty-base-class-message.md)

- [ ] **BUG-273 — A locally-rejected SFTP connect answers the wrong type, and neither permission errno can be claimed without connect-time context**
  spec: SFTP-021, SFTP-023 · effort: S · audience: user.api
  A connect rejected on the local host (`EPERM` from an `OUTPUT`-chain `REJECT`;
  `EACCES`, no known trigger) answers `PermissionDenied` naming the caller's
  key, where the health-check guide promises `BackendUnavailable`.
  `_map_exception` sees the errno, not that it arose at connect. Open decision:
  where connect-time context can classify it; the `EACCES` half may be docs-only.
  Detail: [dossier](backlog/bug-273-local-connect-reject-type.md)

- [ ] **BUG-279 — `unwrap(SFTPClient)` leaks the raw paramiko or socket error when the connection cannot be established**
  spec: SFTP-024, SFTP-026 · effort: S · audience: user.api
  `unwrap()` evaluates the lazy `_sftp` property outside `_errors()`, so a
  failed connect escapes as `NoValidConnectionsError`, `socket.gaierror` or
  `TimeoutError` where every other operation answers `BackendUnavailable`,
  breaching SFTP-024. Open decision: wrap it, or carve `unwrap` out of
  SFTP-024 explicitly; either way SFTP-026 gains a `Raises:` line.
  Detail: [dossier](backlog/bug-279-unwrap-leaks-connect-error.md)

- [ ] **BUG-266 — No artifact maps an observable SFTP failure onto the arm that handles it, and four prose attempts were each refuted**
  spec: SFTP-023, SFTP-030 · effort: M · audience: user.site, library.maintainer
  No artifact maps an observable SFTP failure (refused port, wedged daemon,
  silent peer, bad credential, DNS) to the `_map_exception` arm it reaches and
  what the caller gets; four one-sentence summaries were each refuted, because
  the space has four axes. Open decision: where that mapping lives and which
  failure × arm cells it covers.
  Detail: [dossier](backlog/bug-266-sftp-failure-to-arm-map.md)

- [ ] **BUG-269 — `observe.md`'s level and `op` tables are enumerations that were already false on master, and BK-359 adds to both**
  spec: OBS-008 · effort: S · audience: user.site
  `observe.md`'s level and structured-`extra` tables claim to enumerate the
  whole library and were already false on master; BK-359 adds a third and a
  sixth counterexample. Open decision: whether `op` means "Store operation"
  (so `connect`, `transfer`, `error_mapping` misuse it) or "operation or
  internal stage"; take it with BUG-267's, not inside a fix pass.
  Detail: [dossier](backlog/bug-269-observe-level-op-tables.md)

- [ ] **BUG-267 — OBS-008 demands an `ERROR` level that nothing emits and nothing asserts**
  spec: OBS-008 · effort: S · audience: contributor.process
  OBS-008 requires an `ERROR` record "before re-raise" in all library modules;
  nothing in `src/` logs at `error` or above and no OBS-008 test asserts a
  level, so the clause is undecided (000-process Rule 7, Unenforced). Open
  decision: add the call site and its level assertion, or withdraw the clause
  with the reason recorded; decide it with BUG-269.
  Detail: [dossier](backlog/bug-267-obs-008-error-level.md)

- [ ] **BUG-263 — The migration guide promises a drive folder named `.` stays reachable as a key; no key spelling reaches it**
  spec: GR-058 · effort: S · audience: user.site
  The migration guide says a Graph drive folder named `.` stays reachable as a
  key under a non-root `base_path`; no key spelling reaches it under any
  `base_path`, because `_addressable_segments` strips `.` from keys and
  `base_path` alike, and must. Open decision: none on shape; the guide's
  sentence is what changes, and the dossier drafts its replacement.
  Detail: [dossier](backlog/bug-263-graph-dot-folder-guide.md)

- [ ] **BUG-293 — Twelve Azure `except Exception` arms re-type an already-typed error, so a closed store reports the base class**
  spec: BE-020, BE-021, AZ-029 · effort: S · audience: user.api
  `classify_azure_error` has no `RemoteStoreError` pass-through, so a broad
  arm routed through it downgrades an error already typed: a closed store's
  `BackendUnavailable` becomes `RemoteStoreError`. Twelve such arms lack a
  pass-through, seven sync and five async (dossier: derivation and correction).
  Open decision: which arms can receive a typed error, and what pins each.
  Detail: [dossier](backlog/bug-293-azure-arms-retype-errors.md)

- [ ] **BUG-256 — `ping()` reports a healthy store on three backends whose container is gone**
  spec: PING-001 · effort: S · audience: user.api
  PING-001 promises `NotFound` for a missing container; `S3PyArrowBackend`,
  `SQLBlobBackend` and `SQLQueryBackend` return cleanly (the SQL pair only runs
  `SELECT 1`) and `ReadOnlyHttpBackend` raises the wrong type. Docstrings, the
  health-check guide and the migration guide's table promise the behaviour.
  Open decision: what each probe must touch to see its container.
  Detail: [dossier](backlog/bug-256-ping-healthy-absent-container.md)

- [ ] **BUG-255 — A container deleted mid-listing truncates the listing silently on the two s3fs lanes**
  spec: BE-021 · effort: M · audience: user.api
  `S3Backend` and `S3PyArrowBackend` swallow a container 404 on any listing
  page, so a container deleted mid-scan yields a truncated listing that reads
  as complete: the list-then-delete hazard. The other lanes bound the tolerance
  to the first page (BE-021 § Reach). Open decision: none on shape; the fix
  shape and its worked example are in the dossier.
  Detail: [dossier](backlog/bug-255-s3fs-midlisting-truncation.md)

- [ ] **BUG-257 — `GraphBackend` restarts the first-page bound at every folder of a recursive walk**
  spec: BE-021 · effort: M · audience: user.api
  `GraphBackend` keys BE-021 § Reach's first-page bound per HTTP request, and
  `_walk_files` issues one request per folder, so a recursive `list_files`
  whose subfolder 404s returns what it has as a complete listing; the
  single-listing bound is correct. Open decision: none; RFC-0017 Open Question
  2 is decided (BK-389 dossier, decision 1) and agrees with the dossier's fix.
  Detail: [dossier](backlog/bug-257-graph-walk-first-page-bound.md)

- [ ] **BUG-245 — `SQLBlobBackend(create_table=False)` leaks `NoSuchTableError` from its constructor**
  spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api
  `SQLBlobBackend(create_table=False)` against an absent table leaks
  `sqlalchemy.exc.NoSuchTableError` from reflection, where every other
  constructor rejects bad configuration with `ValueError`; refusing is right,
  the type is wrong. Open decision: whether BE-021's mapping covers
  construction, decided here (RFC-0017 Open Question 5's deferral to D3 step 3 is paused by RFC-0024).
  Detail: [dossier](backlog/bug-245-sqlblob-no-such-table.md)

- [ ] **BUG-253 — `GraphBackend.write` answers a file-ancestor path differently by payload size**
  spec: BE-008, GR-019 · effort: S · audience: user.api
  `GraphBackend.write("blocker.txt/child.bin", …)` raises `InvalidPath` below
  the 4 MiB small-upload threshold and `NotFound` above it: only `_write_small`
  runs the file-ancestor walk before classifying its 404, and `write`'s
  docstring promises `InvalidPath` unqualified. Open decision: hoist the walk
  into `write`, or run it on the session-creation 404; measure first.
  Detail: [dossier](backlog/bug-253-graph-write-ancestor-by-size.md)

- [ ] **BUG-339 — `GraphBackend.write` runs the user-metadata gate before the root refusal**
  spec: BE-008, BE-029, WR-010 · effort: S · audience: user.api
  `GraphBackend.write("", b"x", metadata={"k": "v"})` raises `CapabilityNotSupported`
  where BE-008's order and the Dafny `Write` require `InvalidPath`: `write` calls
  `_reject_user_metadata` before `_require_writable_key`. No test pins the live
  root+metadata cell. Found in PR #1165's review. Open decision: none (swap the two calls).

- [ ] **BUG-318 — `LocalBackend.glob` and `get_folder_info` leave out a subtree they cannot read**
  spec: BE-021 · effort: S · audience: user.api
  `glob` (`Path.glob`) and `get_folder_info` (`rglob`) swallow a denied subfolder
  scan, which should raise `PermissionDenied` as `list_files` does since BUG-280
  (entry stat leak: BUG-319). Every Local walk also skips a subfolder deleted
  mid-walk, breaching BE-021 § Reach (dossier). Open decision: raise or skip a
  vanished one, since a dangling Windows junction is absent from the start.
  Detail: [dossier](backlog/bug-318-local-glob-folder-info-denied-subtree.md)

- [ ] **BUG-319 — `LocalBackend`'s single-path stats leak a raw `PermissionError`, and a looping key a `RuntimeError`**
  spec: BE-021 · effort: S · audience: user.api
  An injected `os.stat` denial on one file (Windows 3.13) leaks a raw
  `PermissionError` from `get_file_info`, `exists`, `is_file`, and BUG-318's
  `glob` and `get_folder_info`. A looping-symlink key raises `RuntimeError` from
  `_resolve`, shared by the keyed operations (measured on `list_files`, `exists`:
  3.11; not 3.14). Open decision: the mapping; RFC-0024 paused the kernel alternative (D3 step 5).
  Detail: [dossier](backlog/bug-319-local-single-path-stat-leaks.md)

- [ ] **BUG-334 — `LocalBackend.write` of a name Windows refuses leaks a raw `OSError`**
  spec: BE-021 · effort: S · audience: user.api
  `write("gn/b.csv\n")` on Windows raises `OSError: [Errno 22] Invalid argument`
  from `write_bytes` (CI `test-cross-platform (windows-latest)`, PR #1154, run
  39010222112, Python 3.13.16); `write` maps only directory and permission
  errors. Other Windows-invalid names (`:`, `?`, `<`) and `write_atomic`, `move`
  and `copy` are unmeasured. Open decision: `InvalidPath` or another type; D3 step 5 is paused (RFC-0024).

- [ ] **BUG-299 — `LocalBackend.write` and `write_atomic` on a `..` key inside the root write the file, then raise `InvalidPath`**
  spec: BE-008, BE-010 · effort: S · audience: user.api
  `write("a/../b.txt", b"x")` and `write_atomic("a/../c.txt", b"x")` raise
  `InvalidPath`, yet the file exists afterwards (both measured at master
  `9caef6b`, BK-389's planning PR): `_resolve` accepts an in-root `..`, and the
  refusal comes after the write. Open decision: none; refuse before writing in
  both (the kernel key rule's route, RFC-0017 step 5, is paused by RFC-0024).

- [ ] **BUG-292 — The file-ancestor gate fails open on every `SQLAlchemyError`, so it degrades to a no-op without a signal**
  spec: BE-008, SQL-BLOB-031 · effort: M · audience: user.api, library.maintainer
  All five flat-namespace `_head_one` probes read any driver error (and
  `OSError`) as "no ancestor", so the file-ancestor gate vanishes silently;
  measured letting `move` succeed under a file ancestor. An anonymous in-memory
  SQLite on `QueuePool` defeats it with no error at all. Decided (BK-387):
  narrow the catch so only a confirmed miss reads as "no ancestor"; BE-008 changes with the fix.
  Detail: [dossier](backlog/bug-292-ancestor-gate-fails-open.md)

- [ ] **BUG-300 — `MemoryBackend`, `AsyncMemoryBackend` and `SQLBlobBackend` `write("\\")` store, then raise `InvalidPath`**
  spec: BE-008, WR-001 · effort: S · audience: user.api
  A direct `write("\\")` stores the entry, raises, and `exists("\\")` is then `True` (SQLBlob at
  master `57d0797`; both Memory classes on v0.33.0's code, 2026-10-25); `Store` refuses first.
  Open decision: none; refuse before storing in each.
  - **(was BUG-297, absorbed here)** Both halves: SQLBlob's, and Memory's, which BK-394 fixed
    on the kernel, frozen by RFC-0025. Evidence: BK-395's dossier.

- [ ] **BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt**
  spec: BE-021, BE-029 · effort: M · audience: infra.test
  BE-021's absent-container rule is verified only by hand-written per-backend
  suites; `tests/backends/conformance/` has no cell for it, so a new backend
  that can delete passes CI without meeting it, as `GraphBackend` did until
  BUG-248. Open decision: none of its own; it consumes ID-244's seeding-hook decision (§ 2).
  - **(was ID-261, absorbed here)** BE-029's root order, unobservable where a present root answers.
  Detail: [dossier](backlog/bk-345-absent-container-conformance.md)

---

<a id="correct-and-proven"></a>
## 2. Answers are correct, and the contract is proven

**Promise:** the same call returns the same right result on every backend, and
no clause of the contract ships unexercised.

- [ ] **BUG-341 — A returned `FileInfo.metadata` is the stored file's own dict, and `copy` shares it**
  spec: BE-019 · effort: S · audience: user.api
  On `Store(MemoryBackend())`, setting a key on `get_file_info("a.txt").metadata` changes the
  stored file's, and after `copy` to `b.txt` mutating `b.txt`'s changes `a.txt`'s (v0.33.0 and
  master `74538f0`, 2026-10-23), against `FileInfo`'s immutable snapshot. Audit-023 T1 found it,
  and the write side, on the kernel; v0.33.0's `_memory.py` has five such sites (`git grep -c
  "metadata=[a-z_]*\.metadata" v0.33.0`). Open decision: none; copy at each.

- [ ] **BUG-342 — `MemoryBackend.write` stores a truncated file from a stream whose `read()` answers `None`**
  spec: BE-008, BE-010 · effort: S · audience: user.api
  Its read loop takes a `None` chunk for the end (`git show v0.33.0:src/remote_store/backends/_memory.py`,
  `write`; `write_atomic` delegates), so a stream answering `b"ab", None, b"c"` stores `b"ab"` on
  `write` and `write_atomic` (reproduced on master after RFC-0025's revert, 2026-10-25). BUG-328
  fixed this on the kernel's Memory driver, now frozen; BUG-330 fixed the adapter's twin. Open
  decision: none; raise `TypeError` as BUG-330 does (patch-rated, RFC-0025 R3 class K).

- [ ] **BUG-343 — `copy`, `deepcopy` and `pickle` of a `CapabilitySet` raise `AttributeError`**
  spec: CAP-002, CAP-006 · effort: S · audience: user.api
  `CapabilitySet` has `__slots__` and a `__setattr__` that always raises, so the default slot-state
  rebuild fails with "CapabilitySet is immutable" (v0.33.0, and master after RFC-0025's revert,
  reproduced 2026-10-26). Anything holding one fails to copy too, e.g. a `SQLBlobBackend`. BK-394
  fixed it with `__reduce__` on the kernel line, now frozen. Open decision: none; restore
  `__reduce__` and its CAP-002 test (patch-rated, RFC-0025 R3 class K).

- [ ] **BK-454 — A refusal surfaces at the call in one layer and at the first iteration in another**
  spec: ASYNC-006 · effort: M · audience: user.api
  `Store` raises a read's I/O refusal at the call, `AsyncStore` at the first `__anext__`; a
  read handle (`with`/`async with store.read(...)`) would put both at open. Moving sync listing
  refusals to the call changes behaviour. Re-scoped by RFC-0024: candidate R-2 of `read()`'s
  flow. Open decision: the timing rule, the handle's shape, and whether bare `async for` stays lazy.
  Detail: [dossier](backlog/bk-454-refusal-timing-read-handle.md)

- [ ] **BK-460 — A lifetime's state diagram has no check against its TLA+ module, so no lifetime can take its spec form**
  spec: — · effort: M · audience: contributor.tooling, library.maintainer
  `SPEC-DESIGN.md` Rule 3 makes a lifetime's Mermaid diagram a view whose edges must equal
  the phase transitions of a small TLC configuration, in a declared subset (flat states,
  `[*]`, `A --> B : Action`) read by an in-repo parser. Neither the parser nor the check
  exists, so lifetime clauses stay prose tables. Due with the first lifetime given a module
  (a v1 flow's; BK-455's candidate froze with RFC-0025). Open decision: phases from a named variable or a declared action map.

- [ ] **BK-463 — The compiled Dafny oracles have no Rule 8 statement, so no Dafny model governs a clause**
  spec: — · effort: S · audience: library.maintainer, infra.test
  `SPEC-DESIGN.md` Rule 4 counts a bridge, one already in the repo included, only once
  Rule 8's six items are stated for it; none are for the two compiled oracles
  (`formal/README.md` § Compiled oracle holds most of the facts), so prose governs every
  clause, against RFC-0022 D5's path ("Dafny for single calls first"). Open decision: one
  `formal/README.md` heading per oracle or one for both; T14's key glue goes under item 2.

- [ ] **BK-461 — No TLA+ module is bridged to code, so none can gate or govern a lifetime**
  spec: — · effort: L · audience: infra.test, library.maintainer
  ADR-0048 gates a TLA+ module from the PR that bridges it; RFC-0022 D5's first
  bridge is model-generated ITF traces replayed by pytest, and no Python ITF replayer
  exists (research-spec-design § 9). The first module's gating splits `verify-tla` per
  module (BK-455's close/run race, the likely one, froze with RFC-0025); ID-270 decides the rest. Open decision:
  which checker emits the traces, and how a model action maps onto API calls.

- [ ] **BK-451 — `glob` has no definition in tree terms and no single pattern dialect**
  spec: GLOB-007, GLOB-011, GLOB-014 · effort: M · audience: user.api, library.maintainer
  No clause defines `glob` over the tree, and the shared `pattern_to_regex`, which the fallback
  uses, lets `**` and classes cross `/` where Local's native glob does not, so one pattern
  answers by tier (audit-023 T8). Re-scoped by RFC-0024: decided in `glob`'s flow, as
  candidate input. Open decision: the defining clause, then the dialect, `\` included.
  Detail: [dossier](backlog/bk-451-glob-tree-definition.md)

- [ ] **BK-452 — Memory's counter and mtime clauses are unpinned, and two misstate the overwrite case**
  spec: MEM-004, MEM-015, MEM-016, MEM-016b · effort: M · audience: library.maintainer
  MEM-016 and MEM-016b misstate the overwrite case in v0.33.0's spec 013; the counter clauses
  have no assertion after a `delete`, `delete_folder` or replacing move or copy, and the mtime
  clauses are asserted only as `is not None` (audit-023 T18, T19). Its flat reference driver
  went to BK-489 (RFC-0025 D7). Open decision: none; pins in both runtimes, as in the dossier.
  Detail: [dossier](backlog/bk-452-template-reference-set.md)

- [ ] **BUG-251 — A shared `cache_backend=` serves one store's bytes for another's**
  spec: RES-100 · effort: M · audience: user.api
  `ext.cache` keys entries on `(operation, path)` with nothing naming the
  store, so two `Store`s sharing one `cache_backend=` return each other's bytes
  for a path both hold; re-measured with two `LocalBackend` roots and one
  `MemoryCache`. Silent wrong data. Open decision: key on backend identity,
  adopt ID-121's derived keys, or refuse an unkeyed shared cache.
  Detail: [dossier](backlog/bug-251-shared-cache-cross-store-bytes.md)

- [ ] **BUG-260 — `SQLBlobBackend.list_files("./")` answers empty for a non-empty root**
  spec: BE-008, BE-029, SQL-BLOB-010 · effort: S · audience: user.api
  On a root holding two files, `list_files("./", recursive=True)` returns
  nothing while `exists` and `is_folder` answer `True` and `""` and `"."` list
  both: `is_root` misses `"./"`, so the listing prefix becomes `'./%'`. Open
  decision: fix the prefix locally, or revisit BE-008's read-side root
  predicate, to which this item is the counterexample.
  Detail: [dossier](backlog/bug-260-sqlblob-dot-slash-root-listing.md)

- [ ] **ID-244 — A read-only backend cannot reach any WRITE-gated contract cell**
  spec: BE-029 · effort: M · audience: infra.test
  Conformance cells seed data through `backend.write`, so their classes are
  gated on `Capability.WRITE` and a read-only backend reaches none of them:
  `ReadOnlyHttpBackend` never runs SIO-009's laziness cells. Open decision:
  where a per-fixture seeding hook binds (fixture, helper, or capability-neutral
  classes); BK-345 (§ 1, paused by RFC-0024) consumes it.
  Detail: [dossier](backlog/id-244-write-gated-conformance-cells.md)

- [ ] **ID-242 — Four `moto doesn't raise PermissionError` pragmas are coverage holes, not exemptions**
  spec: — · effort: S · audience: infra.test
  Four `# pragma: no cover -- moto doesn't raise PermissionError` arms on the
  s3fs lanes mark mappings no test reaches, and read as exemptions; BUG-242
  was a defect behind a fifth. Open decision: none on shape; the harness that
  reaches them, and corrected line numbers, are in the dossier.
  Detail: [dossier](backlog/id-242-moto-permission-pragmas.md)

- [ ] **ID-247 — Record the Graph root-path cassettes**
  spec: BE-029 · effort: S · audience: infra.test
  54 `TestBackendRootPath` cells skip on `graph_replay` for want of a cassette
  (`pytest tests/backends/conformance -k TestBackendRootPath -rs`), and Graph
  has no emulator tier, so those 54 never run against `GraphBackend` below a
  live account; the 16 key-decided cells that issue no request do. Open decision:
  none on shape; the recording procedure is in the dossier.
  Detail: [dossier](backlog/id-247-graph-root-path-cassettes.md)

- [ ] **ID-260 — The async non-recursive `max_depth` cell never runs on Graph or Azure replay**
  spec: ASYNC-014, DEPTH-003 · effort: S · audience: infra.test
  `test_list_files_non_recursive_ignores_max_depth` skips its 8 replay cells,
  4 `graph_replay` and 4 `azure_replay_async`, for want of a cassette
  (`pytest tests/backends/conformance/test_async_extended.py --stage=3 -rs -k non_recursive_ignores`),
  so no conformance cell reaches `GraphBackend` on this rule. Recorded, they go red on a
  regression to extra `/children` calls: replay skips only an absent cassette. Open decision: none.

- [ ] **ID-262 — On Azure replay lanes a regressed root-write guard skips instead of failing**
  spec: BE-029 · effort: S · audience: infra.test
  `test_root_destination_outranks_a_missing_source` passes on `azure_replay(_async)`
  without HTTP; with `_reject_root_as_write_target` narrowed to `is_root` (PR #1050
  round 5) its 16 non-canonical cells reach the SDK and skip "replay cassette missing".
  Open decision: fail a key-decided cell that issues a request on replay, or record
  cassettes for it.

- [ ] **BK-382 — The file-ancestor gate ships unexercised on the overwrite path, where the pre-check runs inside an open write transaction**
  spec: BE-008 · effort: M · audience: infra.test
  The move and copy cells for the file-ancestor gate, sync and async, target a
  destination that does not exist, so the pre-check never runs inside the open
  write transaction `overwrite=True` holds; a reintroduced pool regression
  passed the whole suite. Open decision: a flat-namespace gate in the
  registry, or per-backend seeding; hierarchical backends cannot hold the state.
  Detail: [dossier](backlog/bk-382-ancestor-gate-overwrite-path.md)

- [ ] **BUG-310 — A closed Azure `read_seekable()` or HTTP `read()` stream keeps answering instead of raising `ValueError`**
  spec: SIO-001, SEEK-006 · effort: M · audience: user.api
  After `close()`, Azure `read_seekable()` raises `RemoteStoreError` while bytes
  remain, returns `b""` at EOF, and its `seek`/`tell` return positions. HTTP
  `read()` returns `b""` (urllib), unread bytes (httpx) or `BackendUnavailable`
  (requests). Azure `read()` raises `ValueError`; no spec clause or conformance cell covers this.
  Open decision: guard each adapter, or once in `_ErrorMappingStream`; the reach of each is in the dossier.
  Detail: [dossier](backlog/bug-310-closed-stream-read.md)

- [ ] **BUG-312 — `tell()`/`seek()` on a non-seekable `read()` stream raise `RemoteStoreError` instead of `io.UnsupportedOperation`**
  spec: SIO-012 · effort: S · audience: user.api
  On an open HTTP `read()` stream (urllib, requests, httpx) both raise
  `BackendUnavailable: Stream error: seek`; on Azure `read()` only `tell()` does,
  its `BufferedReader` refusing `seek()` first. A plain non-seekable stream raises
  `io.UnsupportedOperation`, which SIO-012 maps as an `OSError`. BUG-310 shares the wrapper.
  Open decision: exempt it in SIO-012, or keep mapping it.

- [ ] **BK-407 — Mutation scopes miss every backend's `async_sources` and ten split-topic tests**
  spec: — · effort: S · audience: infra.test
  `_src` reads only `[backend.<x>].sources`: `-async-extended-graph` mutates only
  `_sync_adapter.py`, which its tests never run (26 survived, 0 zapped, pre-scan
  "no data"), and Azure's and Memory's `async_sources` are mutated nowhere. Ten
  atomic/identity tests match no transport `-k` filter (backend-name ids, or none);
  `_KNOWN_UNSPLIT_TESTS` in `test_mutate_scopes.py` lists them. Open decision: none.

- [ ] **BK-413 — `backends-ssh` leaves 26 gremlins without a verdict at `mutant_timeout = 120`**
  spec: — · effort: S · audience: infra.ci
  Run 50 (BUG-307's validation): 26 ERRORs, each a timeout whose unmutated
  selection ran past 60 s, half the limit; every other scope fits. The leg took
  139.7 min. Re-measure on the first run after BUG-336 before choosing: run
  38989738880's 77 ERRORs ran with a dead pre-scan. Open decision: faster sftp
  test selections, a per-scope timeout in `mutate_scopes.py`, or splitting the scope.

- [ ] **BK-453 — A coverage pre-scan that records nothing goes unflagged, so every gremlin silently runs its full scope**
  spec: — · effort: S · audience: infra.ci
  BUG-303 (`PYTEST_ADDOPTS`) surfaced only at the 6 h cap; BUG-336 (`filterwarnings`)
  ran green from run 38016030800 to 38989738880: the plugin discards the pre-scan's
  output, `mutation.yml` shows "Coverage collection returned no data" as `default`,
  and the outcome record never sees it. Open decision: fail the leg or flag it;
  BK-407's `-async-extended-graph`, whose tests never run its target, is the known exception.


- [ ] **BK-496 — The v1 API has no spec for getting a store, configuring it and the shape of a call**
  spec: OPS-001 -- OPS-002 · effort: M · audience: user.api, library.maintainer
  Specs 052 and 053 leave to "the API's spec" how a store is obtained and configured, how operations
  and keys are spelled and displayed, handles' language-level behaviour and what sets an extension
  apart; nothing owns it. Reading key settings back is meant for OP-18 (BK-480), handle lifetime is
  `shared.md`'s. Runs after several entries' flows, which also decide core against extension beyond
  the 24 entries, never a session. Open decision: when, and after which entries.

- [ ] **BK-498 — After `/clear`, a worker restart can resume the armed `/observe` session instead of the new one**
  spec: — · effort: M · audience: contributor.tooling, contributor.process
  After `/clear` started a new session, a worker restart resumed OP-01's pre-clear `/observe` session, armed
  (by `rearm` or a marker `disarm` never removed; unknown which): Bash and reads off the ground were refused,
  and the new session's open dialog was answered into it, logged under OP-01's id and lost uncommitted. The
  hook arms a resumed design session as designed; why the harness resumed it is not in the repo's code. Open
  decision: what a hook could tell such a resume by, and how a wrongly armed session gets out by itself.
  Detail: [dossier](backlog/bk-498-observe-resume-rearm.md)

- [ ] **BK-499 — `/observe` checks a decision only against earlier ones and never sees a backend, so contradictions reach the record**
  spec: — · effort: M · audience: contributor.process, library.maintainer
  OP-01's record took thirteen reopens after its session closed (O14 to O16 in PR #1188's review, O17 to O26
  by [audit-025](audits/audit-025-op-01-record-review.md), whose § 5 sorts them): step 3 checks each decision
  against earlier ones only, so a later decision against an earlier reason passes, and the unprimed ground (S1)
  keeps backend behaviour out with no step between record and spec that reads it. Open decision: the End
  step's whole-record pass, and where a primed backend review sits in RFC-0024 § 9 (D4's method amended).

- [~] **BK-485 — The v1 Store API has no observable-semantics specs, so implementation runs ahead of decided behaviour**
  spec: — · effort: L · audience: library.maintainer, contributor.process
  Specs 001 to 050 mix what a caller observes with how 0.33 achieves it. RFC-0024 binds the reset
  (§ 9 steps 1, 2); step 3 built `/observe`, its hook and `sdd/observe/` (ground register, axes, records).
  Its test runs are in the dossier; step 4 is spec 052, step 4b spec 053 and the catalogue (BK-493).
  Step 5's `/observe OP-01` wrote its [record](observe/records/OP-01.md). Not done: step 5's spec, model,
  profile tables and 0.33 comparison; step 6. Open decision: § 8's open points 2 to 4 and 11 (D10 is BK-489's); where the record's `shared:` open items land; its reopens O14 to O26 ([audit-025](audits/audit-025-op-01-record-review.md)).
  Detail: [dossier](backlog/bk-485-spec-first-reset.md)

- [ ] **BK-489 — The frozen kernel line has no decision: revive it, rewrite it or drop it**
  spec: — · effort: L · audience: library.maintainer, contributor.process
  RFC-0025 froze the contract kernel, the drivers, Memory on the kernel and specs 052 and 053 on
  `frozen/kernel-driver` at `814c1f6`; whether that line is revived, rewritten or dropped is
  RFC-0024 D10, and RFC-0025 D7 makes this the host of its open kernel and driver items (the
  dossier lists each absorbed ID with its diagnosis and records). Open decision: D10.
  Detail: [dossier](backlog/bk-489-frozen-kernel-line.md)

- [ ] **BK-482 — Azure conformance runs on Azurite, which stores raw keys the HNS service rewrites**
  spec: — · effort: M · audience: infra.test, library.maintainer
  `research-backend-path-authorities.md` § 5 (2026-10-22): sent raw, `a//b`, `.`, `..`, a leading `/` and a
  trailing `.` are stored as sent by Azurite 3.35.0 and rewritten by an HNS account; they agree only on the
  control key and `\` becoming `/`. An assertion about such keys on Azurite may hold only on the emulator. A
  flat account, measured through the SDK only for `//` and a leading or trailing `/`, stored them as sent.
  Open decision: which assertions rerun on `azure_live` or are emulator-only, and whether a flat account is probed.

- [ ] **BK-483 — A stored Azure name holding `..` may be read back at a different path**
  spec: PATH-003 · effort: M · audience: library.maintainer, user.api
  The HNS service resolves `..` in a raw path before authorising (`research-backend-path-authorities.md`
  § 5), and the SDK's urllib3 removes dot segments client-side (its § 3.7). A listed `..` name (possible on
  a flat account, unmeasured) would be read, written or deleted at the resolved path, under an account key
  maybe in another container; PATH-003 refuses only input. Open decision: whether Azure listings yield such
  names, omitted or refused; spec 052 leaves the general listing rule to the listing operations' specs.

- [ ] **BK-436 — No backend's observed tree is checked against spec 051**
  spec: TREE-001 -- TREE-012 · effort: M · audience: library.maintainer
  Spec 051's sections are tested only against a reference model (`tests/test_store_tree.py`). A
  flat backend can hold an item with keys below it, and a case-insensitive or normalizing one
  merges names spec 051 keeps apart. Open decision: which listings and probes observe a
  backend's tree, how its name equality is measured, how a coarser one answers
  (`research-key-model.md` answers writes).

- [ ] **BK-462 — Alloy and Lean run in no CI job, so no structure clause can be model-governed**
  spec: TREE-001 -- TREE-012 · effort: M · audience: library.maintainer, infra.ci
  `SPEC-DESIGN.md` Rule 4 lets a model govern only while its check gates in CI. `rg -n -i -w
  "alloy|lean" .github/workflows` finds `ci.yml`'s path filter excluding both, its comment,
  and a `benchmark.yml` comment ("lean" as an adjective); no job runs either (maintainer
  decision, 2026-10-13), so spec 051 stays prose-governed. Open decision: a CI job for
  each, at which toolchain cost, or keep both review aids and say so in Rule 4's table.

- [ ] **BK-438 — A flat raw key with an empty segment, such as an S3 folder marker `a/`, has no decoding**
  spec: BE-017 · effort: M · audience: library.maintainer, user.api
  Today's S3 backends answer a foreign `a/` or `a//b` differently per shape (a file named `""`, a
  phantom `a/a`, an unlistable root; RFC-0021 Open question 1's table). Open decision: how such
  keys decode (leaning: an
  empty folder, if the service holds a prefix with no object behind it). Re-scoped by RFC-0024:
  a profile-table question of the listing flows (D6), the leaning as candidate input.

- [ ] **BK-443 — A backend missing from the fixture registry gets no conformance coverage, and no test notices**
  spec: — · effort: S · audience: infra.test
  Conformance runs only the fixtures `tests/backends/fixtures/fixtures.toml` declares, each keyed by
  a family from `backends.toml` (`"azure"`, `"sqlblob"`), and no test compares them with the concrete
  backend classes. `SQLBlobBackend` was missing until cb300156c (#471); adding it surfaced BUG-175 and
  BUG-176. `_concrete_backends()` in `test_health_probe_declared.py` lists the classes; BK-345 gates
  BE-021 on the same registry. Open decision: how a class maps to its family (no map exists), then exemptions.

---

<a id="users-succeed-unaided"></a>
## 3. Users succeed without asking us

**Promise:** a user gets set up, picks the right backend, writes their own, or
copies an example, without opening an issue.

- [ ] **BK-480 — No API lets a caller set or read a store's separator set and acceptance language**
  spec: KEY-008, KEY-009 · effort: S · audience: user.api, user.api_docs
  Spec 052 makes the `\` opt-out, the portability opt-in and P_b store settings (KEY-008, KEY-009)
  and leaves setting, reading back and announcing a P_b below L_shared to the API's spec; no type
  carries any. F4 (`research-spec-first-reset.md`) fixes the form. Class F (RFC-0024 § R3): setting
  is BK-496's; reading back is meant for OP-18, a spec 052 reopen its session records. Candidate:
  a helper such as `is_portable_key(key) -> bool`. Open decision: the shape.

- [ ] **BUG-321 — A list that directly follows paragraph text renders as literal dashes on the docs site**
  spec: DOCFRAME-004 · effort: S · audience: user.site
  GitHub starts a list right after a paragraph line; Python-Markdown needs a
  blank line, so `guides/observe.md`'s `Parameters:` + `- max_queue …` reaches
  the site as one paragraph with literal dashes. Scanning the G-08 published
  set for a top-level marker after paragraph text finds 447 sites in 81 files.
  Open decision: none on shape (insert the blank line; extend G-08).

- [ ] **BK-364 — `transfer-operations.md` documents partial files for `download` only, and the other direction is the one that can destroy data**
  spec: — · effort: S · audience: user.site
  `transfer-operations.md` warns that a failed `download` can leave a partial
  local file and says nothing about `upload` or `transfer`, which call
  `store.write()` and so can leave a partial or replaced remote object;
  re-read on the page and in `ext/transfer.py`. Open decision: none on
  shape; the per-backend residue question is in the dossier.
  Detail: [dossier](backlog/bk-364-transfer-partial-residue.md)

- [ ] **BK-339 — Decide what replaces `store.md`'s hand-maintained Backend Behavior Matrix**
  spec: — · effort: M · audience: user.site
  `store.md`'s Backend Behavior Matrix hand-maintains five rows across ten
  backends and tells readers to verify it against the code. Reproduced: its
  `copy() preserves metadata` row says `—` for Memory, yet a Memory copy keeps
  user metadata. Open decision: which rows to derive from capability
  declarations, which to keep as prose, and which to drop.
  Detail: [dossier](backlog/bk-339-store-behavior-matrix.md)

- [ ] **ID-199 — Backend setup & configuration guides expansion**
  spec: — · effort: L · audience: user.site, library.maintainer
  Backend setup pain mined from repo signal and a public survey maps to seven
  guides; none ships as a page or sidebar (research § 3's six paths are
  absent, `sql-blob.md` has no backup note), though guide 4's SFTP stall
  material now sits in `sftp.md` and troubleshooting. Open decision: the
  Phase 3 budget (research § 8 Q5); ungated guides are greenlit (dossier).
  Detail: [dossier](backlog/id-199-backend-setup-guides.md)

- [ ] **ID-125 — Update medallion showcase to Dagster v2 resource pattern**
  spec: — · effort: S · audience: user.api
  The medallion example wires silver and gold with two `dagster_io_manager`
  calls; the item called that superseded, but `dagster.md` recommends v1
  when a Store already exists, as it does here, and v2 would drop the
  `otel_observe` wrapping. Open decision: show v2 beside v1, or decide
  against.
  Detail: [dossier](backlog/id-125-medallion-dagster-v2.md)

- [ ] **BK-327 — Gate dual-doc nav reachability and index listing**
  spec: — · effort: S · audience: contributor.tooling
  A dual-published design page can be missing from the docs nav and the
  design index, and `docs-gate` passes: nothing differences emitted `dest`
  paths against `_nav.yml` or `_index.tmpl`. PR #938 fixed two by hand;
  re-checked, all eight dual pages are listed today. Open decision: none on
  shape; the fix shape is in the dossier.
  Detail: [dossier](backlog/bk-327-dual-doc-nav-reachability.md)

- [ ] **BK-376 — Half the llmstxt `sections:` map is hand-listed, and four published pages are already missing from both outputs**
  spec: — · effort: S · audience: contributor.tooling
  The llmstxt `sections:` map hand-lists Explanation and half of Reference,
  and nothing checks it against `_nav.yml`. Re-measured, `index.md`,
  `reference/changelog.md`, `explanation/contributing.md` and
  `development-story.md` match no pattern and no comment says why, so both
  bundles omit them. Open decision: one check with BK-327's new gate, or two.
  Detail: [dossier](backlog/bk-376-llmstxt-sections-hand-listed.md)

- [ ] **BK-332 — Schedule the custom-backend rehearsal**
  spec: — · effort: M · audience: contributor.process
  Building a backend from the `Backend`-ABC guide (RFC-0025 restored it), unaided, ran once, in PR #932, and
  found BK-324 and BK-325; nothing schedules it, and `rg -i rehearsal` over `sdd/traces/` and
  `BACKLOG-DONE.md` finds no later run. Open decision: none on shape; cadence, effort split
  and n = 1 caveat are in the dossier.
  - **(was BK-325, absorbed here)** The guide's remaining gaps, which the rehearsal checks.
  Detail: [dossier](backlog/bk-332-custom-backend-rehearsal.md)

- [ ] **BUG-344 — The custom-backend guide's `RedisBackend` reads `*?[` in a path as wildcards and answers a wrong-kind path wrongly**
  spec: BE-005, BE-014, BE-021 · effort: S · audience: user.api_docs
  `examples/snippets/custom_backend_guide.py` (v0.33.0 and master) puts paths unescaped into SCAN
  MATCH, so `list_files('w*', recursive=True)` also lists `w1/` and `w[1]/`; and `read_bytes` of a
  folder is `NotFound`, `write` over a folder succeeds and `get_folder_info` of a file answers,
  against BE-021 (reproduced 2026-10-26). Kernel PR #1144's rewrite fixed both and froze. Open
  decision: none; escape MATCH, add the type checks.

---

<a id="no-workarounds"></a>
## 4. Users stop working around us

**Promise:** the library does the thing, instead of the user hand-rolling it
or paying for our shortcut.

- [ ] **ID-217 — Async-native extension surface (owner for the deferred async `ext.*`)**
  spec: GR-003 · effort: L · audience: user.api
  `aio/ext/` ships only `write.py` against fifteen sync `ext/` modules
  (`ls`), so an `AsyncStore` caller reaches `ext.glob`, `ext.cache` and the
  rest only through `AsyncBackendSyncAdapter`, forfeiting async streaming;
  GR-003 names this item as the async `ext.glob` owner. Open decision: build
  per-extension equivalents (glob first) or decline and document the adapter.
  Detail: [dossier](backlog/id-217-async-native-ext-surface.md)

- [ ] **ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL**
  spec: SQL-BLOB-003, SQL-BLOB-020 · effort: L · audience: user.api
  `SQLBlobBackend` withholds `LAZY_READ` on every dialect (re-read:
  `_ALL_CAPABILITIES` in `_sqlalchemy.py`), so a large blob is materialised in
  full, although SQLite's `blobopen` and PostgreSQL's `substring` both allow
  bounded reads. Open decision: SQLite first or with PostgreSQL, and whether
  a read costing one round trip per chunk may declare `LAZY_READ`.
  Detail: [dossier](backlog/id-140-sqlblob-lazy-reads.md)

- [ ] **ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass**
  spec: SFTP-007 · effort: M · audience: user.api
  `SFTPUtils.enable_ssh_rsa_compat()` patches four paramiko class attributes,
  so SHA-1 acceptance meant for one legacy server reaches every transport in
  the process, as its docstring warns; it matters on paramiko ≥ 5, which the
  unbounded `paramiko>=3.1` pin admits. Open decision: build the per-backend
  opt-in sketched in the dossier, or decide against it.
  Detail: [dossier](backlog/id-181-per-backend-ssh-rsa-opt-in.md)

- [ ] **BK-242 — Flat-NS file-ancestor pre-check perf (SQLBlob IN-list, memoisation)**
  spec: — · effort: S · audience: user.api, library.maintainer
  The opt-in file-ancestor pre-check issues one probe per ancestor per write
  (SQLBlob: one query, one connection each) and memoises nothing across a bulk write;
  re-read, `S3Boto3Backend` runs it too, which the body's list omits (dossier
  correction). Open decision: none on shape; both optimisations and the
  research-note refresh are in the dossier.
  Detail: [dossier](backlog/bk-242-flat-ns-ancestor-precheck-perf.md)

- [ ] **ID-121 — CompositeStore (research complete)**
  spec: — · effort: L · audience: user.api
  No `CompositeStore` exists (`rg -l CompositeStore src` finds nothing), so
  fallthrough reads, union listings and primary-tier writes across stores are
  left to the user; its prerequisites, `Store.resolve()` and a second working
  backend, have shipped. It owns `ResolutionPlan`-derived cache keys, the wide
  fix for BUG-251 (§ 2). Open decision: design it as its own spec, or decline.
  Detail: [dossier](backlog/id-121-composite-store.md)

- [ ] **BK-433 — A store cannot choose how it reads links, and no capability says whether a backend has them**
  spec: — · effort: M · audience: user.api, user.api_docs
  RFC-0021 D7 decides a store-level link policy (`follow_within_root` by default, or
  `no_follow`) and backend-declared links, and defers the public
  surface. Today Local and SFTP follow links on keyed calls, and SFTP hides them in
  listings (measured, RFC-0021). Open decision: the constructor option's name and
  the capability's shape.

- [ ] **ID-272 — Backend breadth: Apache OpenDAL as a transport under remote-store's contract layer**
  spec: — · effort: L · audience: user.api, library.maintainer
  Waits on BK-489 (D10) and BK-485 (v1 specs), both § 2. OpenDAL is a transport layer covering
  far more services than the nine sync backend types in `FEATURES.md` § Backends; remote-store
  is the contract layer above one. No spec, ADR, RFC or doc covers OpenDAL (dossier § Evidence),
  so nothing measures which contract clauses it keeps. Open decision: spike, then an RFC choosing
  an OpenDAL driver, delegation, positioning only, or decline.
  Detail: [dossier](backlog/id-272-opendal-positioning.md)

---

<a id="no-release-surprises"></a>
## 5. A release cannot ship a surprise

**Promise:** nothing reaches a user that we did not test, publish, watch, or
give them a way to absorb.

- [ ] **BK-469 — Spec 052 has not been compared with 0.33, so the key layer's breaks have no record**
  spec: KEY-002 -- KEY-005, KEY-008, KEY-A-02 · effort: M · audience: user.api, library.maintainer
  RFC-0024 D8's pass for the key layer. Known differences: 0.33 refuses every `..` (PATH-003) where
  ν climbs; at `7491289` `Store` took `"\ud800"` (Memory stored it, Local leaked `UnicodeEncodeError`)
  and Local leaked `OSError` [Errno 36] for a 300-character name; on windows-latest at `74271f9c4`
  Local stored `a `, `a.`, `d/x. ` and `a./b` under stripped names. Each becomes a `sdd/v1-breaks.md`
  row or a 0.33 defect, read from `release/0.33.x`'s suite. Open decision: none.

- [ ] **BK-490 — The key model's decisions on the root, parents and child stores have no flow, so 0.33's sections stand**
  spec: PATH-010, PATH-015, CHILD-001, CHILD-003, ERR-003, ERR-005 · effort: M · audience: user.api, library.maintainer
  `research-key-model.md` § 10 decides that parent(`a`) is ε (PATH-010 has none), the root's name is
  ε with no segments (PATH-015: `.`, `(".",)`), a child at ε is the store (CHILD-001 rejects it), a
  subpath's `..` climbs (CHILD-003 refuses it), and ERR-005 and ERR-003 widen. Spec 052 leaves each to
  the API's or the operation's spec, which no flow has written. Open decision: none; each flow takes its own.

- [ ] **BK-409 — Python 3.15 is due 2026-10-09 and no spelling of the supported set names it**
  spec: — · effort: M · audience: user.api, infra.ci, contributor.tooling
  PEP 790 schedules `- 3.15.0 final: Friday, 2026-10-09`, so its security
  window ends 2031-10-09 (final + 5 years). The classifiers, CI matrices and
  `PYTHON_RELEASES` stop at 3.14, so nothing tests it. Gated on final, not
  rc3. Open decision: whether an extra with no 3.15 wheel holds support back,
  measured per extra at final.

- [ ] **BK-392 — A release can drop an interpreter before its support window closes, and nothing checks the date**
  spec: — · effort: S · audience: user.api, contributor.tooling
  Rule 8 promises support until security fixes end; `check-support-windows`
  dates floor raises, but nothing dates a dropped classifier, and the chart
  and drift-guard stop showing it, so the Rule 8 release step is blind to it.
  **Until then: v0.33.0, which drops 3.10 (BK-380), is not tagged before
  2026-10-04.** Open decision: script or checklist step.

- [ ] **BUG-289 — Two floors are clean for a user and red for the suite, because the suite rejects warnings**
  spec: — · effort: S · audience: user.api, infra.test
  The floor lane runs each extra's pytest target under this repo's
  `filterwarnings = error`, so `[sftp]` at paramiko 3.1 (a `TripleDES`
  deprecation, its text re-read verbatim) and `[s3]` at s3fs 2024.2.0 fail on
  warnings a user at those versions never sees. Open decision: which release
  to raise each floor to, measured per candidate; the strictness is kept.
  Detail: [dossier](backlog/bug-289-floor-warnings-fail-suite.md)

- [ ] **BUG-290 — A workflow `run:` step that pipes into `tee` cannot fail, and one of them is a gate**
  spec: — · effort: S · audience: infra.ci
  A workflow `run:` step with no `shell:` key runs `bash -e` without
  `pipefail`, so `benchmark.yml`'s regression gate (`report.py --regression
  … | tee`) stays green when `report.py` exits non-zero; re-read,
  `benchmark.yml` still sets no `shell:`. Open decision: fix the one step, or
  also gate every piped `run:` step.
  Detail: [dossier](backlog/bug-290-workflow-tee-swallows-failure.md)

- [ ] **BUG-291 — A single-extra dispatch can still close the rolling drift issue on one extra's evidence**
  spec: — · effort: S · audience: infra.ci
  `drift_report.decide` refuses to close after a one-lane run but not after
  a one-extra run, so dispatching `extra: s3` closes the rolling issue on
  one extra's evidence; reproduced through `decide`. `main` already computes
  the unnarrowed test that `decide` never sees. Open decision: none on shape;
  the fix and the test pinning today's close are in the dossier.
  Detail: [dossier](backlog/bug-291-single-extra-dispatch-closes-issue.md)

- [ ] **BUG-287 — Three extras declare a `pyarrow` floor that installs and then cannot import**
  spec: — · effort: S · audience: user.api, infra.test
  `[arrow]` and `[sql-query]` declare `pyarrow>=12.0.0`, `[s3-pyarrow]`
  `pyarrow>=14.0.0` (re-read); at those floors `import pyarrow` fails against
  a current `numpy` after a clean install, measured on the floor lane. Open
  decision: raise the three floors, or bound `numpy`, which fixes the
  combination a user hits rather than the one the lane tests.
  Detail: [dossier](backlog/bug-287-pyarrow-floor-cannot-import.md)

- [ ] **BUG-288 — `[azure]`'s `aiohttp` floor names a release no supported interpreter can import**
  spec: — · effort: S · audience: user.api, infra.test
  `[azure]` declares `aiohttp>=3.0`, copied from azure-core's metadata, and
  `aiohttp==3.0.0` installs on the oldest supported interpreter and then fails
  to import, so the range's bottom runs nowhere; re-read, `pyproject.toml`
  and both conda recipes still say `>=3.0`. Open decision: none on shape;
  the floor to find and the files it touches are in the dossier.
  Detail: [dossier](backlog/bug-288-aiohttp-floor-cannot-import.md)

- [ ] **ID-250 — The drift smoke never type-checks, so a signature-only narrowing reaches PRs as a red gate**
  spec: — · effort: M · audience: infra.ci
  Nothing in the drift smoke runs `mypy` (`rg mypy` over `drift-guard.yml`
  and its smoke action finds nothing), so a dependency change visible only to
  a type checker, as in BUG-258's Dagster narrowing, first shows as a red
  `typecheck` job on an unrelated PR. Open decision: type the whole tree per
  drifted extra, or only the extra's own source, which needs a new map.
  Detail: [dossier](backlog/id-250-drift-smoke-never-typechecks.md)

- [ ] **BUG-250 — `[graph]`'s drift smoke reaches one of the extra's four declared dependencies**
  spec: — · effort: S · audience: infra.ci
  `[graph]`'s smoke imports `_graph.http`, which loads `httpx` alone
  (reproduced by diffing `sys.modules`); `msal`, `msal-extensions` and
  `platformdirs` load lazily, so drift in three of four declared packages
  passes unexercised. Open decision: a no-network import of the lazy sites,
  or a cassette-backed target; `otel` re-checked does not share the shape.
  Detail: [dossier](backlog/bug-250-graph-drift-smoke-reach.md)

- [ ] **BUG-282 — A single-extra drift-guard dispatch rewrites the rolling issue body to that extra alone**
  spec: — · effort: S · audience: infra.ci, library.maintainer
  `drift_report.py` replaces the rolling issue's body with whatever the run
  produced, so a single-extra `workflow_dispatch` rewrites it to that extra
  and drops the rows a lock refresh reconstructs from; `drift-guard.yml`'s
  own header warns of it (re-read). Open decision: comment on a partial run,
  or merge its report into the existing body.
  Detail: [dossier](backlog/bug-282-single-extra-dispatch-rewrites-body.md)

- [ ] **BK-367 — The drift guard's only legacy-sftp authentication runs on a 5 s budget after a deliberately failed connection**
  spec: BK-198 · effort: S · audience: infra.ci
  S4 in `test_sftp_legacy_recovery.py` authenticates to `legacy-sftp` with
  `auth_timeout=5` right after a kex-refused connection, and one runner
  failed it on auth timeout with pins that passed before and after; on the
  newest lane it is the only test that authenticates there. Open decision: a
  bounded auth retry, or a wider timeout after checking the container's sshd.
  Detail: [dossier](backlog/bk-367-legacy-sftp-auth-timeout.md)

- [ ] **BK-333 — Gate routing: checkers unreachable for the diffs that invalidate them**
  spec: — · effort: S · audience: contributor.tooling, infra.ci
  Three checkers do not block the CI diffs that break them: the ADR
  digest check rides only `preflight` and the CI-inventory check only
  `lint`, both skipped when no path matches `CODE_PAT`, and `verify-tla`
  runs the TLA check without `gate` needing it (re-derived; dossier
  correction). Open decision: `docs-gate`, a wider `CODE_PAT`, or both.
  Detail: [dossier](backlog/bk-333-gate-routing-unreachable-checkers.md)

- [ ] **BK-381 — `check_backend_order` never tests an enumeration naming fewer than six backends**
  spec: — · effort: M · audience: user.discoverability.human, contributor.tooling
  `check_backend_order` skips any enumeration naming fewer than six distinct
  backends (`_MIN_BACKENDS = 6`), so the conda recipe's `summary`, out of
  order with four detected, passes; reproduced by importing the module.
  Lifting the constant reaches every enumeration at once. Open decision:
  which surfaces are held to membership and which to order only.
  Detail: [dossier](backlog/bk-381-backend-order-min-six.md)

- [ ] **ID-229 — Evaluate porting to httpx 1.0 (lift the `<1.0` cap)**
  spec: GR-033 · effort: M · audience: user.api
  `[graph]` and `[httpx]` cap `httpx<1.0` because `1.0.dev3` drops
  `AsyncClient`, on 29 lines of the Graph backend (`rg -c`), and the error
  types both backends catch. The cap holds every user's resolution below 1.0
  until someone looks. Open decision: port or hold, once a stable httpx 1.0
  exists.
  Detail: [dossier](backlog/id-229-httpx-1-port.md)

- [ ] **ID-225 — Evaluate migrating the docs stack from Material for MkDocs to Zensical**
  spec: — · effort: L · audience: user.site, library.maintainer, contributor.tooling
  Material for MkDocs is feature-frozen and `mkdocs-llmstxt` is in
  maintenance mode, while their successor, Zensical, lacks the API-reference
  feature our docs need; `hatch run docs-gate` prints a MkDocs 2.0 warning
  on every build. Open decision: trial `zensical build` now, or wait for
  API-reference parity.
  Detail: [dossier](backlog/id-225-zensical-migration.md)

- [ ] **ID-271 — Nothing lints the shell in `.github/actions/*/action.yml`, so a regression there passes CI**
  spec: — · effort: S · audience: infra.ci
  actionlint reads workflows only. `start-backends` (4 `run:` blocks) and `drift-smoke`
  (1) are linted by no job (`rg -c 'run:' .github/actions/*/action.yml`); BK-458 fixed the
  former by hand. Open decision: a CI step that shellchecks their `run:` blocks, or accept it.

---

<a id="repo-does-not-mislead"></a>
## 6. The repo does not mislead the next person

**Promise:** the artifacts maintainers coordinate through — this file, the
ripple-check, the revisit pins, the generated inventories, the unreleased
CHANGELOG the release body is built from — say what is actually true.


- [ ] **BK-465 — The spec template's Assumption IDs fail the spec-mark grammar, so no test can cite one**
  spec: — · effort: S · audience: contributor.process
  `templates/spec-template.md` gives `<PREFIX>-A01`; `check_spec_marks._SPEC_ID` fully matches
  `BE-A-01` and neither `BE-A01` nor `KERN-A01` (run with `re.fullmatch`), so a template-form
  row is never declared and a mark citing it goes unfound, against `SPEC-DESIGN.md` Rule 6.4.
  One prefix spanning specs (BE- over 003, 052, 053 before RFC-0025) would also collide. Open decision: change
  the template or the grammar, and the prefix per spec. Found by audit 024 § 2.

- [ ] **BK-466 — `SPEC-DESIGN.md` Rule 1 relocates mechanism to a design note, which has no home**
  spec: — · effort: S · audience: contributor.process
  Rule 1 sends a sentence that mandates an algorithm to "an ADR, a design note or the task's
  plan"; `rg -n -i 'design note'` over `AUTHORING.md`, `000-process.md` and `DOCUMENTATION.md`
  finds nothing, and AUTHORING's placement table has no such type. Every BK-456 prune
  relocates mechanism (audit 024 § 2). Open decision: a placement for design notes, or
  Rule 1 drops the option and names ADRs and the custom-backend guide.

- [ ] **BK-492 — The formal trace check makes a restating file tag sections it does not model**
  spec: — · effort: S · audience: contributor.process
  `check_formal_trace.py` R2 fails a restated spec's section that its Lean or Alloy file tags
  nowhere, and offers no route for a section the file deliberately leaves out. `KeyModel.lean`
  so tags KEY-008, KEY-A-02 and KEY-A-03 on `Cfg.tier`, an arbitrary predicate, and a reader of
  the trace takes them as restated. Open decision: the form of an explicit not-restated marker.

- [ ] **BK-491 — `SPEC-DESIGN.md` Rule 5 asks for a capability or driver flag where RFC-0024 D6 puts a profile table**
  spec: — · effort: S · audience: contributor.process
  Rule 5 states a per-backend behaviour as a profile "declared by a capability or a driver flag";
  D6 records each backend's cells in a table beside the spec, as spec 052's profile table does, and
  R4 says `SPEC-DESIGN.md` binds every v1 spec, so a reviewer applying Rule 5 flags the table.
  Open decision: the format RFC amends Rule 5 to admit D6's table, or D6 yields.

- [~] **BK-456 — Spec 003 is too long to keep free of contradictions, so it is split**
  spec: BE-001 -- BE-029, CAP-001 -- CAP-007 · effort: M · audience: library.maintainer
  PR #1159's rounds kept finding one section of spec 003 contradicting another. Stage one
  (IDs, "yet" and status blocks out; coverage sentences remain, dossier) shipped. Stage two's
  split by kind was reverted by RFC-0025 with spec 003, and stage three's prune (PR #1172, of
  spec 052) has no subject left; RFC-0024 D7 supersedes spec 003 rather than reworking it.
  Open decision: whether to close it.
  Detail: [dossier](backlog/bk-456-split-spec-003.md)

- [ ] **BUG-322 — Spec 047's G-07 row describes a check `check_docs_framework.py` does not run**
  spec: DOCFRAME-004 · effort: S · audience: contributor.process
  The DOCFRAME-004 table says G-07 is "`mkdocs build --strict` succeeds";
  `_check_g07` asserts that `docs-src/api/` does not exist. Its Performance
  paragraph says G-06 and G-07 invoke MkDocs; `_check_g06` parses `_nav.yml`
  and neither calls MkDocs. Found reviewing PR #1115. Open decision: correct
  the spec to the code, or move the strict build into the gate.

- [ ] **BUG-340 — RFC-0015 Table 1's derivation, `rounds.py`, crashes on Windows**
  spec: — · effort: S · audience: contributor.process
  `python sdd/rfcs/rfc-0015/rounds.py 24d9464 --at 2a1bbfe` prints the first population (n=26),
  then dies: `_git` decodes `git show` with the locale codec (cp1252, byte 0x90), and the
  traces' `read` gets `None`. Without `--at`, `relative_to` spells paths with `\`, so none
  match git's and `statistics.median([])` raises. master's copy fails identically (PR #1174).

- [ ] **ID-235 — Backlog-file integrity lint (structure and inbound tracker citations)**
  spec: — · effort: S · audience: contributor.tooling
  `gen_backlogid.py`'s R1–R4 cover open items only: nothing checks
  `BACKLOG-DONE.md`'s status marks, absorbed hosts or conflict markers, and
  no pass resolves inbound tracker citations. Re-derived, those three would
  land green; header uniqueness would not, BK-385 gating it only above released history.
  Open decision: which rules to add, and what a dangling ID means.
  Detail: [dossier](backlog/id-235-backlog-integrity-lint.md)

- [ ] **ID-254 — The `[Unreleased]` stub's bold marker has no defined meaning beyond `**Breaking**`, and nobody owns section assignment**
  spec: — · effort: S · audience: contributor.process
  The bold marker after an `[Unreleased]` entry's ID is a gated obligation
  when it reads `**Breaking**` and undefined otherwise, and no rule says who
  assigns an entry's section; re-tallied, 1 of 10 entries is marked, so the
  mixed state the item was filed on is gone (dossier correction). Open
  decision: marker as the author's section assignment, or emphasis only.
  Detail: [dossier](backlog/id-254-unreleased-stub-marker.md)

- [ ] **ID-255 — The stand-down note gives a reason that is false in the state the release checklist prescribes**
  spec: — · effort: S · audience: contributor.tooling
  `check_changelog_unreleased.py` says its rules stood down because the
  prose no longer leads with IDs, while any `###` line under `[Unreleased]`
  is the trigger, and it counts the lines that still do; reproduced on a
  scratch copy with one `### Fixed` added. Open decision: state the trigger
  alone, or the trigger and the consequence, pinned by a new assertion.
  Detail: [dossier](backlog/id-255-stand-down-note-reason.md)

- [ ] **BK-361 — Typography rules are asserted in `CLAUDE.md` and enforced by nobody**
  spec: — · effort: M · audience: contributor.tooling
  `CLAUDE.md` § Response style states four typography rules and no checker
  scans prose for them; re-counted over 399 tracked `.md` files, 9 `--` em
  dashes sit in 7 files and 73 `No` table cells in 17. Only TLA files have
  an em-dash check. Open decision: correct the existing hits first or
  baseline them, which decides whether the gate lands green.
  Detail: [dossier](backlog/bk-361-typography-rules-unenforced.md)

- [ ] **BK-362 — A `repo-only` marker does not stop the docs bridge claiming the file**
  spec: — · effort: S · audience: contributor.tooling
  `scripts/docs/scan.py`'s `_scan_kind` never reads a file's `doc:` marker,
  so an `sdd/` page marked `repo-only` still reaches the site's nav and
  index pages against AUTHORING Rule 1; reproduced with a probe file. Only
  the skip-listed `adrs/DIGEST.md` carries it today. Open decision: none on
  shape; the fix and its strict-build evidence are in the dossier.
  Detail: [dossier](backlog/bk-362-repo-only-marker-docs-bridge.md)

- [ ] **BK-363 — Two coordination artefacts demand a trace the authority does not owe**
  spec: — · effort: S · audience: contributor.process
  `/pr`'s trace gate stops on every claimed ID with no trace, and both
  ripple-check "Backlog item touched" rows owe one on filing, while
  `CLAUDE.md` § Trace authoring owes none for filing or an advisory edit;
  `/fix-pr` relies on the same gate (dossier correction). Open decision: a
  gate exemption for a diff with no implementation, or a registered divergence.
  Detail: [dossier](backlog/bk-363-coordination-trace-demand.md)

- [ ] **BK-346 — The ripple-check table answers questions adjacent to the ones asked**
  spec: — · effort: M · audience: contributor.process
  Six ripple-check triggers ask a neighbouring question, for instance the
  new-test-file row asks only about `os_sensitive`; re-read, none of the six
  is answered, and the parity gate guarantees only Pre-work → Detailed, not
  both ways (dossier correction). Open decision: per instance, widen the
  row, add one, or point at the checker, which BK-329's reasoning bars.
  Detail: [dossier](backlog/bk-346-ripple-check-blind-spots.md)

- [ ] **ID-207 — Push `check_formal_trace.py` past citation hygiene (steps 3 and 4 only)**
  spec: — · effort: M · audience: contributor.tooling
  `check_formal_trace.py` certifies citation, not assertion: a marker on a
  skipped test or a wrong-but-real ID passes, and `_BASELINE` grows by
  editing it; re-read, neither is built. The research-ranking qualification
  that scoped it to these two steps is now in the dossier. Open decision:
  none on shape; both steps and the dropped half's measurement are there.
  Detail: [dossier](backlog/id-207-formal-trace-assertion.md)

- [ ] **ID-245 — Derived inventories replacing hand-maintained ones**
  spec: — · effort: M · audience: infra.test, contributor.tooling
  Three of four inventories are not derived: the hand-counted cassette-reachability
  table (after ID-244, § 2), a per-spec accountability record nothing renders (after
  ID-207), and the absent-container divergence counts, in four frames that drift; the first
  and last left spec 003 (BK-456), so their home is open. The checker inventory has shipped.
  Open decision: the divergence table's input, whose clause half has no form.
  Detail: [dossier](backlog/id-245-derived-inventories.md)

- [ ] **ID-270 — Revisit informational `verify-tla` CI status (2027-04-19)**
  spec: OBS-003, OBS-003a · effort: S · audience: library.maintainer, infra.ci
  ID-150 re-deferred `verify-tla`: TLC checks `Observer.tla` with no bridge to code, so
  no code regression can turn it red. Due 2027-04-19, or in the PR that first bridges a
  TLA+ module (BK-455's race is likely), whichever first; that module gates from its PR.
  Open decision: promote, remove or re-defer each unbridged module, and RFC-0019's
  `merge-gate` job set; evidence in ID-150's dossier.

- [ ] **ID-267 — Trace-outcome report revisit at the next release**
  spec: — · effort: S · audience: contributor.process
  The release-anchored trace-outcome revisit fires at the next release; ID-259
  closed it at v0.33.0 over 356 traces and 358 negative tags, deferring
  `CONTRIBUTING.md` § Release on a stated test. Open decision: at that
  release, act, defer or accept per selected reference, and name the successor.
  Detail: [dossier](backlog/id-267-trace-outcome-revisit.md)

- [ ] **BK-406 — ADR-0041's short done entry is measured on one release only**
  spec: — · effort: S · audience: contributor.process
  BK-386 kept ADR-0041's review-only rule at the v0.33.0 release base: 11 dossier
  entries, all linked, median 100 words against 529 without. One release is one sample, so
  the reading repeats once. Open decision: at the next release, keep, gate or
  reverse, and whether the Phase 0 line stays.
  Detail: [dossier](backlog/bk-406-done-entry-shape-remeasure.md)

- [ ] **BK-366 — Bug share of shipped work rose 3% → 35% across five releases, undiagnosed**
  spec: — · effort: M · audience: contributor.process
  The `BUG-` share of shipped items rose from 3% at v0.27.0 to 41% at
  v0.31.0 (re-derived), but v0.25.0 was already 32%, so the trend depends
  on where it starts; 25 of 68 open items are `BUG-`. Nothing separates
  better detection from worse quality. Open decision: none on shape; the
  escaped-or-caught classification is in the dossier.
  Detail: [dossier](backlog/bk-366-bug-share-undiagnosed.md)

- [ ] **BK-384 — RFC-0015 is built but unmeasured: three deliveries decide whether it graduates**
  spec: — · effort: M · audience: contributor.process
  Every RFC-0015 decision is in force, but its graduation criterion, three
  deliveries pooled through `rfc-0015/findings.py`, has not been read; at
  least nine traces carry a derived block for a PR after #1026, and the body
  names no rule for which count (dossier correction). Open decision: which
  deliveries form the sample, then graduate or return to Draft.
  Detail: [dossier](backlog/bk-384-rfc-0015-graduation-measurement.md)

- [~] **BK-397 — Interview-mode decisions leave no record in the repo, so their rejected options are unrecoverable**
  spec: — · effort: M · audience: contributor.process, contributor.tooling
  `AskUserQuestion` decisions persisted only in the session transcript. RFC-0018
  accepted 2026-10-04, `failed` path omitted. Done: D5 steps 1 and 2 and D2's
  staging and exclusions. Pending: step 3 (`/pr` Decisions section, without
  priming `/ship`'s unprimed passes), which acceptance's delivery count waits
  on, and a remedy for one session's log across two branches (D2 bound; BK-486 cleared its case 2).

- [ ] **BK-402 — `ci.yml` says `tests/scripts/` does not exercise `remote_store`, and it does**
  spec: — · effort: S · audience: infra.ci
  The `tooling-tests` comment (`ci.yml:451`) says `tests/scripts/` tests "not
  remote_store", but `test_gen_features.py` imports it, and eight test files
  there read `src/` other than by import (BK-403's scan,
  `bk-403-testmon-poc/srcreads.py`). A selector built on the comment would
  drop the directory. Open decision: none.

- [ ] **BUG-324 — `ship-report` reports `ci: GREEN` for a PR on which no CI ran**
  spec: — · effort: S · audience: contributor.tooling
  On PR #1130, stacked on `bk-389-kernel`, `ci.yml` never triggers (it runs for
  pull requests into master), and the only check is a skipped dependabot job. Yet
  `hatch run ship-report 1130 --trace-block-only` printed `ci: {verdict: GREEN,
  failed: 0, pending: 0}` (2026-10-13), and that block goes into the trace unedited.
  Open decision: none; report no checks run as its own verdict.

- [ ] **BUG-325 — `backlog-find --spec` misses every item whose `spec:` line names a range**
  spec: — · effort: S · audience: contributor.tooling, contributor.process
  `_spec_ids` in `scripts/sdd_lookup.py` splits the attribute value on `,` only, so
  `spec: TREE-001 -- TREE-012` is one token and `--spec TREE-00n` matches nothing:
  `hatch run backlog-find --spec TREE-001 ... --spec TREE-012` printed no match while BK-435
  and BK-436 carry that range (2026-10-14). `/ship` § Orient finds related work this way.
  Open decision: expand ranges, or reject range syntax on attribute lines.

---

<a id="gate-cost"></a>
## 7. The gate costs only what it needs

**Promise:** while work is in progress, a contributor waits only for the checks
the change can affect; once, before merge, the whole gate runs, and pays for
nothing it does not need. Narrowing never lifts the full pre-merge run or the
coverage floor.

- [ ] **BUG-302 — `CODE_PAT` names a `FEATURES.md` path that does not exist, so a `FEATURES.md`-only PR runs no checks**
  spec: — · effort: S · audience: infra.ci
  `ci.yml` `CODE_PAT` lists `docs-src/reference/FEATURES.md`. `git ls-files`
  has only the root `FEATURES.md`, which matches no class pattern, although
  `tests/scripts/test_gen_features.py` checks it. Found in RFC-0019 review
  (D4 known violator); the wider class hole is BUG-306. Open decision: none;
  bug-fix protocol, with a test that every literal `CODE_PAT` path is tracked.

- [ ] **BUG-306 — 48 tracked files that `tests/scripts/` tests read match no CI class pattern, so a PR touching only them runs no checks**
  spec: — · effort: S · audience: infra.ci
  RFC-0019 Phase 0's D4 audit ([report](research/bk-403-phase-0/report.md)
  Appendix G) lists them: `.claude/skills/*`, `.claude/agents/*`, `CONTRIBUTING.md`,
  `CLAUDE.md`, `infra/drift-locks/*` and more, each read by a test that never runs
  for such a PR; 776 further `docs`-class files have readers outside `docs-gate`.
  Open decision: per file, move it to a class whose jobs run its readers, or accept it.

- [ ] **BUG-316 — `infra/.env` and `infra/docker-compose.yml` match no CI class pattern, so editing either alone runs no checks**
  spec: — · effort: S · audience: infra.ci
  `infra/_settings.py` reads `infra/.env` at import for the ports and credentials
  tests use, and `.github/actions/start-backends` sources it; its guard,
  `check_infra_settings.py`, runs in `lint`, which `CODE_PAT` gates. Since
  BUG-315, `CODE_PAT` covers `infra/*.py` only. Not in BUG-306's list, which is
  files `tests/scripts/` reads. Open decision: which class, at what CI cost.

- [ ] **BUG-327 — `lint` and `format-check` skip the tracked `.py` files under `sdd/`, which only the pre-commit hook checks**
  spec: — · effort: S · audience: contributor.tooling
  Both run ruff on `src/ tests/ examples/ scripts/`; `git ls-files "sdd/*.py"` lists 67 files
  (59 `sdd/research/`, 4 `sdd/rfcs/`, 4 Dafny-generated `sdd/formal/*-py`). The only stated
  rationale is pyproject's `[tool.ruff]` comment excluding the Dafny output. The pre-commit hook
  checks any staged one, so the next edit inherits old violations (PR #1142). Open decision:
  widen the gate's paths, or exclude `sdd/` from the hook on purpose.

- [ ] **ID-266 — Every in-progress PR push runs the full pre-merge CI gate**
  spec: — · effort: L · audience: infra.ci, contributor.process
  `ci.yml` runs the whole gate on every PR push, including each `/ship` round
  (audit-022 § M1). [RFC-0019](rfcs/rfc-0019-two-speed-test-gate.md) proposes a
  fast lane on every push and a full lane on a `merge-candidate` head. The local
  gate is selected since BK-403 (`scripts/fast_gate.py`) and leans on CI's full run per push.
  Open decision: whether the CI lane reuses that selector; then RFC-0019 Phases 1–3 and ADR-0043's amendment.
  Detail: [dossier](backlog/id-266-two-speed-ci-gate.md)

- [ ] **BK-400 — The shard durations go stale between manual refreshes, so the primary shards balance on partial data**
  spec: — · effort: M · audience: infra.ci
  `.test_durations_pass1` misses part of what the primary shards split and
  names tests that no longer exist (audit-022 § M2); refreshing is a manual
  duty. Open decision: the drift threshold for a `ci-full.yml`-opened refresh
  PR, and its token, since a `GITHUB_TOKEN` PR does not trigger `ci.yml`.
  Detail: [dossier](backlog/bk-400-durations-refresh-pr.md)

- [ ] **ID-265 — The PR gate's critical path waits for a runner slot behind setup-only jobs**
  spec: — · effort: S · audience: infra.ci
  `test-primary` can queue only after `prepare-images`, by which time the
  setup-only jobs hold the slots ([audit-022](audits/audit-022-gate-speed-strategies.md)
  § L3, at most ~30 s). Gating them behind `prepare-images` delays them in
  turn. Open decision: adopt only if a measured run shows a net gain.

- [ ] **ID-268 — Closing a PR needs a manual agent round trip before it can merge**
  spec: — · effort: M · audience: contributor.process, infra.ci
  The trace's `review:` block is pasted at the close (`CLAUDE.md` § Trace
  authoring), so a converged, green PR waits for an agent run, a push and a CI
  re-run before the maintainer can merge (PR #1071). GitHub has no pre-merge
  step that edits a PR. Open decision: which of the dossier's nine shapes, if
  any (shape 6, post-merge, under study); it touches ID-266 and BK-384.
  Detail: [dossier](backlog/id-268-pr-close-step.md)

---

<a id="delivery-cost"></a>
## 8. A delivery costs only what it needs

**Promise:** a session's token spend follows the work it does, not the context
it has piled up or the rounds that repair its own fixes. A change to how
sessions work is measured before it becomes process.

- [ ] **BK-420 — BK-414's lookup tool is not yet measured against its baseline of 78 search-and-reread cycles**
  spec: — · effort: S · audience: contributor.tooling, contributor.process
  BK-414 pointed `CLAUDE.md` and five skills at `scripts/sdd_lookup.py` to cut
  Grep → Read cycles and overlapping re-reads on the backlog and reference files:
  78 over 37 transcripts before it. Re-walk the transcripts about 30 days after
  #1099 merges, by [BK-414's dossier](backlog/bk-414-sdd-lookup.md) § Acceptance
  measure. Open decision: keep, change or remove the pointers, by that result.

- [ ] **BK-445 — A measuring reviewer pushed off `env -C <root>` tests the main checkout's code**
  spec: — · effort: S · audience: contributor.process, contributor.tooling
  `env -C <root> hatch run python <file>` imports the review worktree's own `src` and `.venv`. Claude
  Code's worktree-isolation guard refuses an `env -C` command parsing as `stmt; call(...)`, such as
  `python -c "import os; print(1)"`; a bare `python` fallback imports the main checkout's `src` (PR #1151:
  100+ false failures). The route lives in `rvw-pr/SKILL.md` § Review root. Open decision: script-file
  probes, naming the guard there, or widening its `os.chdir` spelling, which clears the guard, to it.
