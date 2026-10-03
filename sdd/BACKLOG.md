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
  construction (RFC-0017 Open Question 5, deferred to D3 step 3; BK-389 dossier).
  Detail: [dossier](backlog/bug-245-sqlblob-no-such-table.md)

- [ ] **BUG-253 — `GraphBackend.write` answers a file-ancestor path differently by payload size**
  spec: BE-008, GR-019 · effort: S · audience: user.api
  `GraphBackend.write("blocker.txt/child.bin", …)` raises `InvalidPath` below
  the 4 MiB small-upload threshold and `NotFound` above it: only `_write_small`
  runs the file-ancestor walk before classifying its 404, and `write`'s
  docstring promises `InvalidPath` unqualified. Open decision: hoist the walk
  into `write`, or run it on the session-creation 404; measure first.
  Detail: [dossier](backlog/bug-253-graph-write-ancestor-by-size.md)

- [ ] **BUG-280 — `LocalBackend`'s three listing methods leak a raw `PermissionError`**
  spec: BE-021 · effort: S · audience: user.api
  `LocalBackend.list_files`, `list_folders` and `iter_children` leak a raw
  `PermissionError` from `iterdir`, breaching BE-021's never-leak invariant,
  while every other `LocalBackend` path maps it. It is the generator shape
  BUG-249 fixed on `S3Boto3Backend`. Open decision: fix the three here, or the
  listing-generator pattern once across backends.
  Detail: [dossier](backlog/bug-280-local-listing-permission-leak.md)

- [ ] **BUG-299 — `LocalBackend.write` and `write_atomic` on a `..` key inside the root write the file, then raise `InvalidPath`**
  spec: BE-008, BE-010 · effort: S · audience: user.api
  `write("a/../b.txt", b"x")` and `write_atomic("a/../c.txt", b"x")` raise
  `InvalidPath`, yet the file exists afterwards (both measured at master
  `9caef6b`, BK-389's planning PR): `_resolve` accepts an in-root `..`, and the
  refusal comes after the write. Open decision: refuse before writing in both
  here, or leave it to RFC-0017 step 5's kernel key rule.

- [ ] **BUG-292 — The file-ancestor gate fails open on every `SQLAlchemyError`, so it degrades to a no-op without a signal**
  spec: BE-008, SQL-BLOB-031 · effort: M · audience: user.api, library.maintainer
  All five flat-namespace `_head_one` probes read any driver error (and
  `OSError`) as "no ancestor", so the file-ancestor gate vanishes silently;
  measured letting `move` succeed under a file ancestor. An anonymous in-memory
  SQLite on `QueuePool` defeats it with no error at all. Decided (BK-387):
  narrow the catch so only a confirmed miss reads as "no ancestor"; BE-008 changes with the fix.
  Detail: [dossier](backlog/bug-292-ancestor-gate-fails-open.md)

- [ ] **BK-395 — The kernel's key rule is undecided for addressing, backslash keys and `glob`**
  spec: BE-025, NPR-021, NPR-004, RES-020, PATH-002, BE-008, WR-001 · effort: S · audience: library.maintainer, contributor.process
  BK-389's decision 6 covers the operations only. The kernel's answer for the
  addressing members (BE-025, NPR-021: total), a backslash key (PATH-002 folds
  one; a direct `write("\\")` stores the row, then raises) and `glob` is
  undecided. Open decision: all three; the maintainer's preferred answers and
  the measurements are in the dossier. BK-389 waits on it.
  Detail: [dossier](backlog/bk-395-kernel-key-rule-addressing.md)

- [ ] **BK-389 — RFC-0017's kernel does not exist, so no backend can migrate onto it**
  spec: BE-017, BE-020, BE-021, BE-029, ERR-001, ERR-009, DEPTH-003, PING-002, AW-001, SAW-003 · effort: L · audience: library.maintainer, infra.test
  D3 step 1's first PR: the async kernel and its `unasync` sync twin, private,
  with a fake-driver suite and the spec 003 clauses it traces to, under the
  Proposed ADR-0042; BK-394 lands Memory on it. After the v0.33.0 tag. Needs BK-388
  and BK-395. Open decision: none of its own; the rest are in the dossier's
  § Decisions (`delete_folder`'s, decided in BK-396), the key rule's remainder BK-395's.
  Detail: [dossier](backlog/bk-389-kernel-step-1-memory.md)

- [ ] **BK-394 — No backend runs on RFC-0017's kernel, so ADR-0042 stays Proposed**
  spec: BE-017, BE-020, BE-021, BE-029, ERR-001, ERR-009, DEPTH-003, ASYNC-001, AW-001, SAW-003, SAW-012, PING-002, PING-008, MEM-DS-005, MEM-013, MEM-014, MEM-015, MEM-018, MEM-020 · effort: L · audience: library.maintainer, user.api_docs, contributor.process
  ADR-0042 is accepted only with the first backend on the new design: the two
  Memory drivers on BK-389's kernel, step 1's other spec amendments (listed in
  the dossier's item 4, BK-395's contradicted clauses outside spec 003 among
  them), and the guide as a driver. After BK-389, the v0.33.0 tag and ID-244's decision (§ 2). Open
  decision: none; Memory's identity and spec 013's placement are in the dossier.
  Detail: [dossier](backlog/bk-394-memory-drivers-accept-adr-0042.md)

- [ ] **BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt**
  spec: BE-021 · effort: M · audience: infra.test
  BE-021's absent-container rule is verified only by per-backend suites, so a
  new backend that can delete passes CI without meeting it, as `GraphBackend`
  did until BUG-248. Its kernel half lands in BK-389; what stays here is the
  gate, as per-driver `container_absent` cells from D3 step 2. Open decision:
  none of its own; depends on ID-244 (§ 2) for the seeding hook, and on BK-394.
  Detail: [dossier](backlog/bk-345-absent-container-conformance.md)

- [ ] **BK-390 — RFC-0017's spec amendments after D3 step 1 have no owner once BK-387 closes**
  spec: SIO-008, SEEK-004, SEEK-006, PING-003, PING-004, PING-005, PING-006, PING-007, PING-011, SFTP-010, GR-039 · effort: M · audience: contributor.process
  RFC-0017 § Impact lists amendments to specs 006, 008, 009, 026, 036, 044,
  the later drivers' half of 007 and 022, and the per-backend specs, each true only
  once a later D3 step lands (s3fs clauses at step 2, SFTP-010 at step 6).
  Remainder of BK-387. Open decision: none; each lands in its step's PR, and
  the dossier maps amendment to step.
  Detail: [dossier](backlog/bk-390-rfc-0017-spec-amendments.md)

---

<a id="correct-and-proven"></a>
## 2. Answers are correct, and the contract is proven

**Promise:** the same call returns the same right result on every backend, and
no clause of the contract ships unexercised.

- [ ] **BUG-251 — A shared `cache_backend=` serves one store's bytes for another's**
  spec: RES-100 · effort: M · audience: user.api
  `ext.cache` keys entries on `(operation, path)` with nothing naming the
  store, so two `Store`s sharing one `cache_backend=` return each other's bytes
  for a path both hold; re-measured with two `LocalBackend` roots and one
  `MemoryCache`. Silent wrong data. Open decision: key on backend identity,
  adopt ID-121's derived keys, or refuse an unkeyed shared cache.
  Detail: [dossier](backlog/bug-251-shared-cache-cross-store-bytes.md)

- [ ] **BUG-260 — `SQLBlobBackend.list_files("./")` answers empty for a non-empty root**
  spec: BE-029, SQL-BLOB-010 · effort: S · audience: user.api
  On a root holding two files, `list_files("./", recursive=True)` returns
  nothing while `exists` and `is_folder` answer `True` and `""` and `"."` list
  both: `is_root` misses `"./"`, so the listing prefix becomes `'./%'`. Open
  decision: fix the prefix locally, or revisit BE-008's read-side root
  predicate, to which this item is the counterexample.
  Detail: [dossier](backlog/bug-260-sqlblob-dot-slash-root-listing.md)

- [ ] **ID-244 — A read-only backend cannot reach any WRITE-gated contract cell**
  spec: — · effort: M · audience: infra.test
  Conformance cells seed data through `backend.write`, so their classes are
  gated on `Capability.WRITE` and a read-only backend reaches none of them:
  `ReadOnlyHttpBackend` never runs SIO-009's laziness cells. Open decision:
  where a per-fixture seeding hook binds (fixture, helper, or capability-neutral
  classes); BK-345 (§ 1) consumes it, due before BK-394 (§ 1) changes the registry.
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

- [ ] **BUG-298 — `glob("*.csv")` matches a key ending in a newline, because `pattern_to_regex` anchors with `$`**
  spec: GLOB-014, BE-024 · effort: S · audience: user.api
  Python's `$` also matches before one final `\n`, so `pattern_to_regex("*.csv")`
  accepts `"a.csv\n"`: `SQLBlobBackend.glob` and `ext.glob` over `MemoryBackend`
  return it (measured); the S3, Azure and async Azure native globs share the
  regex (read only). Open decision: anchor with `\Z` on every backend, or state
  the newline rule in GLOB-014.

---

<a id="users-succeed-unaided"></a>
## 3. Users succeed without asking us

**Promise:** a user gets set up, picks the right backend, writes their own, or
copies an example, without opening an issue.

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
  bundles omit them. Open decision: one check with BK-327's G-08, or two.
  Detail: [dossier](backlog/bk-376-llmstxt-sections-hand-listed.md)

- [ ] **BK-332 — Schedule the custom-backend rehearsal**
  spec: — · effort: M · audience: contributor.process
  Building a backend from the guide, unaided, has run once, as a side effect
  of PR #932, and found BK-324 and BK-325; nothing schedules it, and
  `rg -i rehearsal` over `sdd/traces/` and `BACKLOG-DONE.md` finds no later
  run. Runs after BK-394 (§ 1) rewrites the guide as a driver. Open decision:
  none on shape; cadence, effort split and n = 1 caveat are in the dossier.
  Detail: [dossier](backlog/bk-332-custom-backend-rehearsal.md)

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

---

<a id="no-release-surprises"></a>
## 5. A release cannot ship a surprise

**Promise:** nothing reaches a user that we did not test, publish, watch, or
give them a way to absorb.

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

---

<a id="repo-does-not-mislead"></a>
## 6. The repo does not mislead the next person

**Promise:** the artifacts maintainers coordinate through — this file, the
ripple-check, the revisit pins, the generated inventories, the unreleased
CHANGELOG the release body is built from — say what is actually true.

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
  Three of four inventories are not derived: spec 003's hand-counted
  cassette-reachability table (after ID-244, § 2), a per-spec accountability
  record nothing renders (after ID-207), and BE-021's divergence counts,
  stated in four frames that drift. The checker inventory has shipped. Open
  decision: the divergence table's input, whose clause half has no form.
  Detail: [dossier](backlog/id-245-derived-inventories.md)

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  spec: — · effort: S · audience: library.maintainer
  `verify-tla` has been informational since 2026-04-19 and is due its first
  revisit on 2026-10-19; the item narrows the README's cadence of 10 spec
  amendments to TLA-backed sections and drops "on a production branch"
  (dossier correction). No catch is recorded. Open decision: promote,
  remove or re-defer, with a successor ticket.
  Detail: [dossier](backlog/id-150-verify-tla-revisit.md)

- [ ] **ID-259 — Trace-outcome report revisit at the next release**
  spec: — · effort: S · audience: contributor.process
  The release-anchored trace-outcome revisit fires at the next release, and
  none has happened since v0.32.0 (no `v0.33.0` tag); today's report counts
  335 traces and 331 negative tags against the recorded 310 and 306. Open
  decision: at that release, act, defer or accept per selected reference,
  and name the successor.
  Detail: [dossier](backlog/id-259-trace-outcome-revisit.md)

- [ ] **BK-386 — ADR-0041's short done entry is unmeasured until the next release**
  spec: — · effort: S · audience: contributor.process
  ADR-0041 keeps a done entry for an item with a dossier short, by review
  alone, so compliance shows only in the next release section;
  `hatch run report-done-length` over the register at `8fa22d6` gives
  medians of 403 words at v0.32.0, 646 at v0.31.0, 67 for Unreleased's one
  dossier entry. Open decision: at the next release, keep, gate or reverse the rule.
  Detail: [dossier](backlog/bk-386-done-entry-shape-measure.md)

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
  deliveries pooled through `rfc-0015-findings.py`, has not been read; at
  least nine traces carry a derived block for a PR after #1026, and the body
  names no rule for which count (dossier correction). Open decision: which
  deliveries form the sample, then graduate or return to Draft.
  Detail: [dossier](backlog/bk-384-rfc-0015-graduation-measurement.md)

- [ ] **BK-397 — Interview-mode decisions leave no record in the repo, so their rejected options are unrecoverable**
  spec: — · effort: M · audience: contributor.process, contributor.tooling
  Mid-work decisions are taken in `AskUserQuestion` dialogs whose question,
  options, recommendation and answer persist only in the session transcript;
  research § 2.3: code shows behaviour, not whether it was decided. RFC-0018
  (Draft) proposes hook capture; step 0 ran 2026-10-03. Open: what fires
  `PostToolUseFailure` (dismissal, timeout); then accept RFC-0018.
