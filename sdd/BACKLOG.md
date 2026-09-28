# Development Backlog
<!-- doc: repo-only -->

Active work items. [BACKLOG-DONE.md](BACKLOG-DONE.md) holds everything that
left this file: work that shipped, IDs **absorbed** into a surviving item whose
work is still open, and items **decided against**. Only the first is "completed".

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
## How this file works

Operational rules only. Why each rule exists: [ADR-0040](adrs/0040-backlog-as-index.md).
**Migration in progress:** §§ 1–5 are converted. A section not yet converted carries
`<!-- backlog: unconverted -->` on the line under its heading and keeps its old
shape (long bodies, `Closes when`) until it is; do not extend that shape in new
edits. Converting a section deletes the marker. The marker, not this note, is
what the gate reads. Its preamble keeps only the Promise; every other sentence is
routed, not cut: one that bounds an open item moves verbatim to that item's
dossier under `## Moved from the § N preamble`, glossing any dangling reference
in the intro line; one whose fact an authoritative home states (a
`BACKLOG-DONE.md` entry, CHANGELOG, a spec, a published guide) is removed; the
section narrating its own history is removed. Nothing goes to an Accepted ADR,
which RFC-0016 D3 would otherwise ask for and `000-process.md` Rule 4 forbids.

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

**Item scope** (new items, and all items in converted sections). At most eight
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

**Item authority.** Each kind of content is corrected where it lives. In an
unconverted item all three sit in its body, under the same rules.

| Kind | Lives in | Status | Corrected when re-derivation disagrees |
|---|---|---|---|
| Diagnosis: the observed problem | index | authoritative, current | in the index, same commit |
| Evidence: what was measured, how | dossier | durable record, dated by its commit | a dated correction is added; the original is not rewritten |
| Prescription: fix shape, disposition, line reference, scope claim, reproduction recipe | dossier | advisory, presumed stale | re-derive against the code before acting; correct it in the same commit |

Where a dossier restates the diagnosis and disagrees, the index wins and the
dossier is corrected in the same commit. Agreement is review-enforced.

**Completing work** (same commit as the change):

- Done → delete here; add to `BACKLOG-DONE.md` as `[x]`.
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

**Assigning a new ID:** use the prefix's value on the "Next safe IDs" line of
`hatch run gen-backlogid-check`. Run `hatch run gen-backlogid` after moving items
to `BACKLOG-DONE.md`.

**What is gated:** the rows of [`GATE-INVENTORY.md`](GATE-INVENTORY.md) whose
subject names `sdd/BACKLOG*.md`. The admission test, granularity, section
membership, the item scope cap in unconverted sections, and agreement between
an index entry and its dossier are review-enforced.

---

## Release Blockers

**Promise:** nothing ships to PyPI while an item here is open; an item is filed
here only when shipping without it resolved would cost users more than delaying
the release.

- [ ] **BL-011 — `SQLBlobBackend.delete_folder` deletes sibling keys, and listings return them, because prefix `LIKE` patterns leave `_` and `%` unescaped**
  spec: — · effort: S · audience: user.api
  Nine unescaped prefix `LIKE` sites in `_sqlalchemy.py` (`key + "/%"`,
  `prefix + "%"`) let `_` and `%` match siblings: `delete_folder("a_b",
  recursive=True)` deletes `axb/y.txt`, and `list_files("a_b")` returns it.
  Silent data loss on ordinary keys. Open decision: none on shape; the fix
  scope and its evidence are in the dossier.
  Detail: [dossier](backlog/bl-011-sql-like-sibling-deletion.md)

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
  `_errors.py`'s arm is shared by all three S3 backends. Open decision:
  synthesise a fallback message or classify the fall-through, for all five; the
  fix deliberately falsifies AZ-025's blank-message clause and its pinning test.
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
  whose subfolder 404s returns what it has as a complete listing. The
  single-listing bound is correct. Open decision: none on shape; the fix shape
  is in the dossier.
  Detail: [dossier](backlog/bug-257-graph-walk-first-page-bound.md)

- [ ] **BUG-245 — `SQLBlobBackend(create_table=False)` leaks `NoSuchTableError` from its constructor**
  spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api
  `SQLBlobBackend(create_table=False)` against an absent table leaks
  `sqlalchemy.exc.NoSuchTableError` from reflection, where every other
  constructor rejects bad configuration with `ValueError`. Refusing is right;
  the type is wrong. Open decision: whether BE-021's mapping rule, scoped to
  operations today, covers construction.
  Detail: [dossier](backlog/bug-245-sqlblob-no-such-table.md)

- [ ] **BUG-253 — `GraphBackend.write` answers a file-ancestor path differently by payload size**
  spec: BE-008, GR-019 · effort: S · audience: user.api
  `GraphBackend.write("blocker.txt/child.bin", …)` raises `InvalidPath` below
  the 4 MiB small-upload threshold and `NotFound` above it: only `_write_small`
  runs the file-ancestor walk before classifying its 404, and `write`'s
  docstring promises `InvalidPath` unqualified. Open decision: hoist the walk
  into `write`, or run it on the session-creation 404; measure first.
  Detail: [dossier](backlog/bug-253-graph-write-ancestor-by-size.md)

- [ ] **BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt**
  spec: BE-021 · effort: M · audience: infra.test
  BE-021's absent-container rule is verified only by hand-written per-backend
  suites; `tests/backends/conformance/` has no cell for it, so a new backend
  that can delete passes CI without meeting it, as `GraphBackend` did until
  BUG-248. Open decision: none of its own; it consumes ID-244's seeding-hook
  decision (§ 2), on which it depends.
  Detail: [dossier](backlog/bk-345-absent-container-conformance.md)

- [ ] **BUG-280 — `LocalBackend`'s three listing methods leak a raw `PermissionError`**
  spec: BE-021 · effort: S · audience: user.api
  `LocalBackend.list_files`, `list_folders` and `iter_children` leak a raw
  `PermissionError` from `iterdir`, breaching BE-021's never-leak invariant,
  while every other `LocalBackend` path maps it. It is the generator shape
  BUG-249 fixed on `S3Boto3Backend`. Open decision: fix the three here, or the
  listing-generator pattern once across backends.
  Detail: [dossier](backlog/bug-280-local-listing-permission-leak.md)

- [ ] **BUG-292 — The file-ancestor gate fails open on every `SQLAlchemyError`, so it degrades to a no-op without a signal**
  spec: BE-008, SQL-BLOB-031 · effort: M · audience: user.api, library.maintainer
  All five flat-namespace `_head_one` probes read any driver error (and
  `OSError`) as "no ancestor", so the file-ancestor gate vanishes silently;
  measured letting `move` succeed under a file ancestor. An anonymous in-memory
  SQLite on `QueuePool` defeats it with no error at all. Open decision: narrow
  the catch, warn, or add a strict mode; BE-008 must say which.
  Detail: [dossier](backlog/bug-292-ancestor-gate-fails-open.md)

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

- [ ] **BUG-240 — ASYNC-014 and DEPTH-003 state opposite rules, and `GraphBackend` implements the async one**
  spec: ASYNC-014, DEPTH-003 · effort: M · audience: user.api
  ASYNC-014 says a set `max_depth` overrides `recursive`, citing DEPTH-003,
  which says `max_depth` applies only when `recursive=True`. `GraphBackend`,
  its docstring and its test follow ASYNC-014; `AsyncMemoryBackend` and
  `AsyncAzureBackend` follow DEPTH-003. `Store` normalises, so only a direct
  backend call diverges. Open decision: which reading wins.
  Detail: [dossier](backlog/bug-240-max-depth-spec-contradiction.md)

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
  gated on `Capability.WRITE` and a read-only backend reaches none of them,
  write-related or not: `ReadOnlyHttpBackend` never runs SIO-009's laziness
  cells. Open decision: where a per-fixture seeding hook binds (fixture,
  helper, or capability-neutral classes); BK-345 (§ 1) consumes the answer.
  Detail: [dossier](backlog/id-244-write-gated-conformance-cells.md)

- [ ] **ID-242 — Four `moto doesn't raise PermissionError` pragmas are coverage holes, not exemptions**
  spec: — · effort: S · audience: infra.test
  Four `# pragma: no cover -- moto doesn't raise PermissionError` arms on the
  s3fs lanes mark mappings no test reaches, and read as exemptions; BUG-242
  was a defect behind a fifth. Open decision: none on shape; the harness that
  reaches them, and corrected line numbers, are in the dossier.
  Detail: [dossier](backlog/id-242-moto-permission-pragmas.md)

- [ ] **ID-251 — BE-029's widest clause is one the conformance suite cannot fail on**
  spec: BE-029 · effort: M · audience: infra.test
  BE-029 requires the write guard to refuse every spelling of the root, but
  the conformance root-write cells run only `""` and `"."`, so a backend
  guarding with `is_root(path)` passes. Open decision: when the cells widen,
  normalise `"./"` in `DafnyOracleBackend` or carve it out of the roster.
  Detail: [dossier](backlog/id-251-root-write-cells-narrow-spellings.md)

- [ ] **ID-247 — Record the Graph root-path cassettes**
  spec: BE-029 · effort: S · audience: infra.test
  30 `TestBackendRootPath` cells skip on `graph_replay` for want of a cassette
  (`pytest tests/backends/conformance -k TestBackendRootPath -rs`), and Graph
  has no emulator tier, so BE-029's root-path cells never run against
  `GraphBackend` below a live account. Open decision: none on shape; the
  recording procedure is in the dossier.
  Detail: [dossier](backlog/id-247-graph-root-path-cassettes.md)

- [ ] **BK-382 — The file-ancestor gate ships unexercised on the overwrite path, where the pre-check runs inside an open write transaction**
  spec: BE-008 · effort: M · audience: infra.test
  The move and copy cells for the file-ancestor gate, sync and async, target a
  destination that does not exist, so the pre-check never runs inside the open
  write transaction `overwrite=True` holds; a reintroduced pool regression
  passed the whole suite. Open decision: a flat-namespace gate in the
  registry, or per-backend seeding; hierarchical backends cannot hold the state.
  Detail: [dossier](backlog/bk-382-ancestor-gate-overwrite-path.md)

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

- [ ] **BK-325 — Custom-backend guide: registry-integration and remaining contract-topic gaps**
  spec: — · effort: M · audience: user.site
  The custom-backend guide does not teach `Secret`-wrapped credentials, the
  injected `retry=` kwarg, stream-time error mapping for `LAZY_READ`, or the
  `strict_only` file-ancestor fixtures, and owes three smaller fixes; re-read,
  `_MODULE_FOR` is now taught (dossier correction). Open decision: none on
  shape; the gap list and reference shapes are in the dossier.
  Detail: [dossier](backlog/bk-325-custom-backend-guide-gaps.md)

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
  run. Open decision: none on shape; the proposed cadence, its effort split
  and its n = 1 caveat are in the dossier.
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

- [ ] **BK-380 — Python 3.10 stops getting security fixes on 2026-10-04, and the drop is a breaking change of its own**
  spec: — · effort: M · audience: user.api
  CPython 3.10 loses security support on 2026-10-04, and ADR-0039 already
  ties our support to that; dropping it moves seven spellings of the
  supported set at once, no gate compares all of them, and it is breaking.
  Re-read, all seven still say 3.10. Open decision: none on shape; the
  ripple list and the measured CI saving are in the dossier.
  Detail: [dossier](backlog/bk-380-drop-python-310.md)

---

<a id="repo-does-not-mislead"></a>
## 6. The repo does not mislead the next person
<!-- backlog: unconverted -->

**Promise:** the artifacts maintainers coordinate through — this file, the
ripple-check, the revisit pins, the generated inventories, the unreleased
CHANGELOG the release body is built from — say what is actually true.

**Closes when:** the backlog files are structurally linted (ID-235); the
`CLAUDE.md` typography rules that are mechanically checkable are checked
(BK-361); the two mechanisms that claim more authority than the rule they route
on are reconciled with it (BK-362, BK-363);
CHANGELOG `[Unreleased]` is linted for duplicate entries, stub shape and the
audience rule — **met** by ID-252 (`check_changelog_unreleased.py`), whose
stated bound is that it keys on the ID at line start, so a single entry whose
*content* went stale is still nobody's to catch; the
CHANGELOG expansion step Phase 1 depends on is written down or dropped —
**met** by ID-253, which wrote the step and gave the CHANGELOG section order its
first home (`CONTRIBUTING.md` § CHANGELOG section order), leaving the step manual
and the order ungated, both stated where they are written; the `[Unreleased]`
stub's section marker means one thing or nothing (ID-254); the release-window
stand-down's stated reason matches what actually switches the rules off
(ID-255);
the ripple-check's six measured blind spots are answered (BK-346); the
hand-maintained inventories ID-245 names are generated — four bullets, of which
the checker inventory has shipped; `check_formal_trace` proves
assertion rather than citation (ID-207); both open revisit pins have fired
and named successors (ID-150, ID-259 — the trace-outcome pin has fired twice
already, as ID-249 at v0.31.0 and ID-258 at v0.32.0); the two backlog files are readable by the
person they are for, or the decision that their length is the right price is
recorded (BK-365); the repo can say whether its own quality promise is
holding rather than only asserting it (BK-366); two sessions working in
parallel cannot mint the same backlog ID with every derivation telling both they
are right (ID-257); and the review loop stops recording itself in the artifacts
it reviews (BK-384, after BK-379's pilot and BK-378's build of RFC-0015's D1
and D4 left the re-measurement as the last thing it owes).
**Bounded to those fifteen deliberately** — count derived by enumerating the
semicolon-separated clauses above, not carried forward. "No artifact asserts what
no mechanism can check" is the promise and cannot be a closing condition: this section's own
preamble records that detecting the remaining class needs semantic comparison of
prose, which research § 1 marks as having no general oracle. Nor is "no figure
was counted by hand" the rule — [principle 9](../CLAUDE.md#principles) requires a
figure to **name its derivation**, and counting a list below the sentence is a
derivation. Items here comply with principle 9 by naming their counts' sources.
**Cross-section dependencies**, per
[§ How this file works](#how-this-file-works): ID-245's cassette inventory waits
on **ID-244** in section 2, which moves the surface it would measure.

Lowest priority. Design and review rules for anything added here:
[`DRIFT-RULES.md`](DRIFT-RULES.md#rules). The argument and gap ranking behind
the programme:
[research](research/research-inconsistency-detection-multi-artifact.md) § 9.

**Measured qualification on that research doc's ranking**, recorded here
because [`000-process.md` § Document types](000-process.md) makes a research doc
a point-in-time snapshot rather than a living one. It designates the
canonical claim space — research § 9 step 2, which ID-207 used to carry — as
the strategic item. That step builds an *omission detector*, research § 1 class
E. BK-324's four instances were class A/C/D: one claim restated in several homes
and updated in one. So step 2 is **not** what would have caught anything this
programme has actually caught, which is why ID-207 below is scoped to steps 3
and 4 and step 2 is gone. Detecting the rest needs semantic comparison of prose,
which § 1 marks as having no general oracle. The mechanisms that did catch them
were an author-side sibling sweep ([BK-336](BACKLOG-DONE.md)) and running the
code rather than reading the diff ([BK-344](BACKLOG-DONE.md) and
[BK-338](BACKLOG-DONE.md)) — neither in the research doc's ranking.

**Order within this section:** ID-207 precedes ID-245 because ID-245's
accountability-record bullet waits on it — step 3 changes what counts as a
satisfied trace, which moves the matrix that bullet renders. ID-245's first
bullet additionally waits on **ID-244 in section 2**, per the cross-section
rule in [§ How this file works](#how-this-file-works).

Shipped so far: step 1 as BK-328, step 5.1 as BK-329, step 4 as BK-331, step 3
as BK-330 plus ID-238. Four findings from them apply to what follows: a
documented gap statement is not a measured one; pinning what an exemption
covers beats exempting the whole item; an authority rule is worth exactly the
live disagreements it decides, so run a proposed one against them before
believing it; and a hand-counted figure about a growing corpus is stale before
the commit that writes it lands, so cite the generator instead.

- [ ] **ID-235 — Backlog-file integrity lint (structure and inbound tracker citations)**
  spec: — · effort: S · audience: contributor.tooling
  Two passes over the same artifact, in the same script family, sharing one
  wiring trap. Home: extend `scripts/gen_backlogid.py` and
  `scripts/check_no_tracker_refs.py`, both of which already parse the ID
  pattern and already know both backlog files.
  - **Structural integrity.** A string-anchored edit swallowed an entry header
    in `BACKLOG-DONE.md` (PR #932), merging two items — and because
    `gen_backlogid.py` derives IDs from headers, the stale JSON was masked too.
    Lint the structure: every metadata line follows an entry header, headers
    unique across both files, BACKLOG-DONE status `[x]` only.
    **And no merge-conflict marker survives**: a rebase of BK-378's branch left
    a `<<<<<<< HEAD` line above an item in this file, and `docs-gate` passed
    twice with it there (neither `gen_backlogid.py` nor `mkdocs --strict` reads
    the line). A `^(<{7}|={7}|>{7})` scan over both files is the cheapest rule
    in this list and the one a rebase-heavy workflow needs most.
    **Add the retirement sections to the structural rules**: every entry under
    `BACKLOG-DONE.md` § Absorbed names a host that exists in `BACKLOG.md`, and
    every ID retired by either route appears exactly once across both files.
    That is what keeps the ID space safe by construction rather than by whoever
    last remembered to add an entry.
    **ADR-0040's four shape rules are in this pass**, all shipped under
    BK-365: R1 (attribute vocabulary), R2 (item cap) and R3 (section shape)
    on sections without the `unconverted` marker, R4 (dossier link) on all.
  - **Inbound citations resolve** (was ID-246, absorbed here). Specs cite
    backlog coordinates as provenance, and `check_no_tracker_refs.py` actively
    *pushes* IDs here — it fails a docstring or `docs-src/` page and tells the
    author to move the coordinate into `sdd/specs/` or `sdd/BACKLOG-DONE.md`,
    listing `sdd/**` as out of scope because "the trackers are how those
    documents are addressed". **Nothing checks that they resolve.** Measured
    across all 50 specs: 166 citations, 80 distinct IDs, 28 files, **zero
    dangling** — 69 resolve into `BACKLOG-DONE.md`, the rest here. The
    invariant holds by discipline, not construction. Add a second, inverted
    pass: every `PREFIX-NNN` under `sdd/` must appear as an item in either
    backlog file, failing with the citing file and line
    ([DRIFT-RULES Rule 2](DRIFT-RULES.md#localize): localize, don't merely fail).
    Rule 3 makes it cheap — the claim space is *derived* from the citing
    documents. Rule 4 needs a decision this does not presuppose: when a spec
    cites an ID no backlog file carries, which side is wrong.
    **Extend the walk to `.py` docstrings while building it.** A repo-relative
    Markdown link written in a `scripts/*.py` docstring is validated by nothing
    (`scripts/docs/check_links.py` walks git-tracked `.md` only) — 7 such links
    into `sdd/DRIFT-RULES.md` anchors exist today, per
    `rg -n '\.md#' scripts/report_trace_outcomes.py scripts/_trace_corpus.py`.
    That was BK-335, retired because its own trigger ("the first time a rename
    breaks one") is unobservable: a silent break is what nobody notices. The
    marginal cost here is near zero once this pass walks non-`.md` files, and it
    makes the trigger a check rather than an aspiration.
  **Both passes key on an ID, and the measured misses do not carry one.**
  Retiring 23 IDs in one change falsified three sites a grep-for-IDs pass cannot
  reach: `sdd/specs/004-path-model.md` forward-pointed to "the follow-up" in
  prose without naming it, `tests/scripts/test_gen_backlogid.py` justified a
  fixture in a comment, and `DEVELOPMENT_STORY.md` described the file's tier
  structure. All three were found by reading rather than grepping. Scope the
  item honestly against that: an ID-keyed pass is worth building and will not
  close the class, so state its miss rate rather than implying coverage
  ([`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)).
  **Note the wiring trap BK-333 documents:** a check reading `sdd/` must reach a
  gate an `sdd/`-only change actually runs. This item is a live instance of its
  own subject — the deletions that produced this file's current shape are
  exactly the event the second pass exists to catch.

- [ ] **ID-254 — The `[Unreleased]` stub's section marker means one thing on half the entries and nothing on the other half**
  spec: — · effort: S · audience: contributor.process
  Twelve of the 25 entries under CHANGELOG `[Unreleased]` open with a bolded
  marker and thirteen open with none (`- <ID>: **<marker>** —` against
  `- <ID>: <text>`, tallied over the section as of this item's filing; re-tally
  rather than reading the split, which every merged PR moves). Four of the twelve are
  `**Breaking**`, which is a real obligation the ripple-check's **Breaking
  change** row states and `check_breaking_migration_link.py` half-enforces. The
  other eight are decoration nobody wrote down: `**Fix**` (5), `**Docs**` (1),
  `**Added**` (1), `**Change**` (1).
  **Three of those four names are not section names.** The canonical names are
  [`CONTRIBUTING.md` § CHANGELOG section order](../CONTRIBUTING.md#changelog-section-order),
  which ID-253 gave its one home; against that list `**Fix**`, `**Change**` and
  `**Docs**` each look like they name the section the entry will land in
  (`Fixed`, `Changed`, `Documentation`) and each names something else. A reader
  cannot tell whether the marker is a section assignment the author made or an
  emphasis they chose, and the release step reassigns sections from the item
  regardless — which is what ID-253 recorded the v0.30.0 release doing to eight
  unmarked stubs.
  **What it decides.** Either the marker becomes a section assignment the PR
  author owes — spelled with the canonical names and gateable in
  `check_changelog_unreleased.py` alongside the three rules already there, which
  would move section assignment off the release manager and onto the author who
  knows the change — or it stays free-form emphasis and says so, in which case
  `**Breaking**` is documented as the one marker that means anything and the
  other eight are normalised or dropped. **Do not split the difference**: a
  marker that is a section name on some entries and a mood on others is the
  state this item exists to leave.
  **Section assignment is this item's either way.** ID-253 wrote the expansion
  step's sources, its per-entry shape and the section order, but not the rule for
  *which* section a given entry lands in — and that is the one decision the step
  makes per entry. If the marker becomes an obligation, the author assigns and
  the rule is the marker's definition; if it stays emphasis, the release manager
  assigns and the rule has to be written for them. Either resolution owes it, so
  it does not fall between the two.
  **Not urgent, and the reason bounds it:** nothing downstream reads the
  marker except the breaking-change gate, which keys on `**Breaking**` alone, so
  the cost today is a reader's confusion rather than a wrong release. Found by
  ID-253 while deriving the section order, and deliberately left out of its
  scope.

- [ ] **ID-255 — The stand-down note gives a reason that is false in the state the release checklist prescribes**
  spec: — · effort: S · audience: contributor.tooling
  `_release_window_note` in `scripts/check_changelog_unreleased.py` prints: "The
  stray-line rule, the audience rule and the unknown-ID note all key on entries
  leading with an ID, **which condensed prose does not**, so all three stood
  down." That reason is true at the *end* of Phase 1 and false at its
  *beginning* — and the beginning is the state
  [`CONTRIBUTING.md` § Release Phase 1](../CONTRIBUTING.md#release) mandates,
  since it says to add the `###` groupings **before** condensing any bullet.
  **Reproduce it:** put a bare `### Fixed` *inside* an untouched `[Unreleased]`,
  above its entries — `parse_unreleased` scans forward from the `## [Unreleased]`
  heading, so a grouping placed above that heading sets nothing and the symptom
  never appears.
  The note claims the entries do not lead with an ID, then reports "over the 25
  line(s) that still parse as entries" — counting the ones that do.
  What actually switches the three off is the `###` itself: `grouped` is a bare
  `startswith("### ")` and `collect` branches on it alone, never on whether any
  line still parses. The reason describes a *consequence* of finishing the
  condense, not the *trigger*.
  **What it decides.** Whether to state the trigger instead ("a `###` grouping,
  not the absence of IDs, is what switches these off") or to state both. It is a
  message-string change; no existing assertion pins the reason clause — the
  tests key on `_STOOD_DOWN` and on the surviving-entry count, deliberately, per
  the comment at that assertion — so whoever takes it should add one, or the
  corrected reason is unpinned in exactly the way the wrong one was.
  **A second half worth deciding at the same time**, being the same paragraph's
  blind spot: the docstring's "The cost, stated in full" costs out uniqueness
  and the prose budget but never costs out the **audience rule**, which is what
  the groupings-first ordering trades away earliest.
  **Filed rather than fixed by ID-253**, which found it: that PR's whole diff to
  `scripts/check_changelog_unreleased.py` is inside the module docstring —
  verified by AST, base and head byte-identical with the docstring stripped —
  and it declined to trade that property for a one-sentence message fix.

- [ ] **BK-361 — Typography rules are asserted in `CLAUDE.md` and enforced by nobody**
  spec: — · effort: M · audience: contributor.tooling
  [`CLAUDE.md` § Response style](../CLAUDE.md#response-style) states four
  typography rules: em dashes used sparingly, never `--` as an em dash
  substitute, `—` as the table N/A value rather than `--` or `No`, and a closed
  list of contexts where `--` survives. Nothing checks any of them.
  `scripts/check_tla_no_emdash.py` is the nearest thing and reads only
  `sdd/formal/tla/**/*.tla`, so it reaches none of the prose the rules govern.
  The promise this sits under is the one at stake: an authority doc asserting a
  convention the corpus does not follow misleads the next person who reads it as
  a description of the corpus.

  **Measured over the 318 tracked `.md` files** (`git ls-files '*.md'`, scanned
  with fenced blocks and HTML comments stripped and the rule's own exemption
  list applied):
  - **9 uses of `--` or `---` as an em dash, across 7 files.** Three are in
    user-facing pages: `docs-src/guides/backends/sql-query.md`,
    `docs-src/guides/glob-pattern-matching.md`, and
    `docs-src/reference/api/backends/sql-query.md`.
  - **73 table cells reading `No` or `no` where the rule requires `—`, across 17
    files.** Twelve sit in three specs — `014-pyarrow-filesystem-adapter.md`,
    `031-ext-dagster.md`, `045-write-result.md` — and those are capability
    tables, the exact shape the rule names.
  - **23 numeric ranges written `192--214`, across 4 files.** Left unclassified
    on purpose: the exemption covers spaced spec-ID ranges, and whether an
    unspaced line-number range is the same thing is a decision this item does
    not pre-make.

  **Two of the four rules are mechanical; two are not.** The `--` substitute and
  the table N/A value have exact definitions. "Sparingly" has no threshold, and
  measuring one first shows why inventing it would fail: per-file em dash density
  across the 51 `sdd/research/` records over 500 words runs from 0.3 to 40.9 per
  1000 words, a 136× spread over files nobody has called wrong. Scope a first
  pass to the two absolute rules and leave density review-enforced.

  **Constraints for whoever implements this.** A line-based scanner over-reports:
  the scan above produced one false positive at `sdd/BACKLOG-DONE.md:3560`, where
  a backtick span wraps two lines and hides a CLI flag from a per-line filter.
  Multi-line backtick and comment handling is a requirement, not a refinement.
  The exemption list is a closed set living in `CLAUDE.md`, so the check either
  reads it there or restates it — the second is a second description and is what
  [`DRIFT-RULES.md`](DRIFT-RULES.md#rules) governs, which applies here in full
  because this adds a cross-artifact check. And note the wiring trap BK-333
  documents: a checker reading `.md` under `sdd/` must reach a gate that an
  `sdd/`-only diff actually triggers, which is the failure `check_tla_no_emdash`
  already demonstrates.

  **Open question:** whether the 73 cells and 9 substitutions are corrected in
  the same change or baselined the way `check_formal_trace` baselines its two
  known gaps. The corpus fix is the larger half of the effort, and it is the half
  that decides whether the gate can land green.

- [ ] **BK-362 — A `repo-only` marker does not stop the docs bridge claiming the file**
  spec: — · effort: S · audience: contributor.tooling
  [`AUTHORING.md`](AUTHORING.md#file-classification) Rule 1 says a per-file
  marker overrides the directory default, and for classification it does. The nav
  and the design index do not consult it: they are generated from the `glob` in
  each `sdd_kinds` entry of [`docs-src/_path_rules.yml`](../docs-src/_path_rules.yml),
  so a file matching `research-*.md` is claimed for the nav even when its marker
  says `repo-only` and the bridge therefore emits no page.
  **Measured, not predicted.** Adding a repo-only `research-*.md` produced four
  strict-build failures — one `nav` reference and three links, from `SUMMARY.md`,
  `explanation/design/index.md` and `explanation/design/research/index.md` —
  each naming a page the bridge had correctly declined to emit. The file was
  reverted; the tooling gap was not, which is why this item exists rather than a
  paragraph in a merged PR description.
  **The gate that should catch it does not.** `check_docs_framework.py` passes in
  that state, reporting all seven of G-01..G-07 green, because classification is
  in fact correct; only `docs-build --strict` aborts. So the fast checker is
  wired and blind, which is the shape BK-333 documents for gate routing,
  arriving here as a checker that runs and does not look.
  **A precedented fix exists and is per-file.** `sdd/adrs/DIGEST.md` carries both
  a `repo-only` marker and a `skip_stems` entry, and the pair is what works. That
  is the disposition to weigh against: teach the generator to read markers, or
  keep `skip_stems` and document the pairing where an author will meet it. The
  second is cheaper and silently fails the next author who does not know.

- [ ] **BK-363 — Two coordination artefacts demand a trace the authority does not owe**
  spec: — · effort: S · audience: contributor.process
  [`CLAUDE.md` § Trace authoring](../CLAUDE.md#trace-authoring) owes a trace when
  work *implements* an item or closes it by implementing it, and carves out an
  item decided against, one absorbed, and a pure advisory annotation. Two
  artefacts that route on the same rule are stricter than it.
  - `.claude/skills/pr/SKILL.md` step 3 extracts `^([A-Z]+-\d+[a-z]?)[:\s]` from
    every commit subject and stops when any ID lacks `sdd/traces/<id>-*.yml`,
    with no exemption for an item that is *filed* rather than implemented. The
    commit filing BK-361 is subject-prefixed `BK-361:` per
    [§ Backlog](../CLAUDE.md#backlog), so the gate would block a PR the authority
    says owes nothing.
  - [`CLAUDE-REFERENCE.md`](CLAUDE-REFERENCE.md) "Backlog item touched" carries
    the narrower form: it exempts only an item decided against or absorbed, and
    omits both the filed-without-implementation case and the advisory annotation.
  **Same promise as BK-361, opposite polarity.** BK-361 is an authority asserting
  what no mechanism checks; this is a mechanism enforcing more than the authority
  asserts. Both make a coordination artefact say something untrue, which is what
  this section is for.
  **What it does not decide.** Whether the fix is an exemption in the gate keyed
  on the diff containing no implementation, a convention that a filing commit
  carries no ID prefix — which would contradict § Backlog — or an accepted
  divergence registered under [`DRIFT-RULES.md` Rule 6](DRIFT-RULES.md#tolerated).
  The first is the only one that leaves both artefacts true.

- [ ] **BK-346 — The ripple-check table answers questions adjacent to the ones asked**
  spec: — · effort: M · audience: contributor.process
  One class with **six** measured instances, not six items — counted from the
  numbered list below, which is the only derivation this figure has. Each is a
  reader who consulted the
  [Pre-work index](CLAUDE-REFERENCE.md#pre-work-index), got an answer, and acted
  on it — and the answer was to a neighbouring question. Any row change lands in
  **both** presentations; `check_ripple_parity.py` enforces trigger-parity, so a
  row added to one and not the other fails `lint`.
  **The open question is the shape of the fix**, not whether there is a defect:
  N rows, N widened rows, or a note about the table's granularity. That question
  is shared by instances **1 to 4**, which want a row and differ only in trigger.
  **Instances 5 and 6 each carry a second disposition of their own**, stated in
  place: 5's is deleting the restating copies rather than adding a row, and 6's
  is that a gate over "an assertion went stale" is harder than it looks. So this
  is one class with one shared question and two members that may not answer it
  the same way — and instance 5's choice sets the effort for the group: S if it
  goes one way, M the other, and `effort:` states the upper bound.
  1. **New test file** asks whether the file needs an `os_sensitive` mark and is
     silent on placement, so nothing routes an author to TEST-003 when adding
     one. `check_test_placement.py` enforces three other rules and not this one.
     Two files landed mixing sync and async in one module; a round-1 reviewer
     caught it.
  2. **Public method signature** answers for signatures. A spec clause can change
     what an operation *tolerates* without touching a signature, and then no row
     points from the clause to the ABC docstrings that define it — four of them
     said nothing about the new rule for seven rounds.
  3. **CHANGELOG entry** says where a new entry goes and stops. It does not ask
     whether an *unreleased sibling* entry has been invalidated by the new one.
     One had been, by the same item, in the same section.
  4. **Adding a `hatch` script alias** (was BK-334, absorbed here). No trigger covers adding an
     entry to `pyproject.toml`'s `[tool.hatch.envs.default.scripts]`. That edit
     decides whether a new `scripts/*.py` is reachable by anything — whether it
     joins `lint` / `preflight` / `docs-gate` / `all`, or is deliberately left
     out. It fires on every new script in `scripts/`, of which the repo has
     dozens and every one carries an alias. BK-330 reasoned to the right answer
     only via the adjacent cross-artifact row, which now covers drift reports and
     still says nothing about a `gen_*` or a `bench-*`.
  5. **Widening an authority doc's scope** (was BK-337, absorbed here). There is a row for a
     **new** authoritative process doc, and one for an authority **direction**
     amended. Neither fires on the commonest amendment: an existing doc's scope
     or subject sentence widening, after which nothing finds the copies that
     restate that scope. Measured target set at filing — six live restating
     copies of one direction: `CLAUDE.md` § Drift checks, `sdd/CI-OPERATIONS.md`,
     `sdd/CLAUDE-REFERENCE.md` in both ripple presentations,
     `.claude/agents/sdd-expert.md` and `documentation-expert.md`, and
     `.claude/skills/rvw-pr/SKILL.md` and `audit/SKILL.md`. PR #944 widened
     `DRIFT-RULES.md`'s scope sentence and took four review rounds to find them
     all, being one copy short in three of those rounds. `check_ripple_parity.py`
     structurally cannot help — it enforces parity between the two ripple
     presentations, not between them and copies scattered through `.claude/**`.
     **This instance has a better second disposition:** delete the restatements
     and let each reader link to the doc that states its own scope, as
     `CLAUDE.md` § Drift checks already half-does. A row keeps N copies
     synchronised; deletion removes the synchronisation problem. The obstacle is
     that agent-facing files are read cold by a process that may not follow a
     link, which is the reasoning BK-329 recorded when it accepted the copies.
     **Choosing between the two is the first half of this item**, and it decides
     the effort for the whole group.
  6. **Closing a backlog item** (was ID-248, absorbed here). The **Backlog item touched** row
     names the trace, the schema and the CHANGELOG-audience rule. It does not
     name the **inbound** references: other items, section preambles, and
     `BACKLOG-DONE.md` entries that cite the closing item by ID and assert
     something about its state. Measured from closing ID-238 in one PR — four
     instances, each carrying a claim the close falsified rather than a bare
     cross-reference; two caught by the author's grep, **two more only by
     review**, which is itself the measurement. The asserting kind is what makes
     this more than link rot: [principle 3](../CLAUDE.md#principles) is violated
     the moment the item closes, and the stale sentence reads as current. One
     instance is a **distinct sub-shape**: not a stale assertion *about* the
     closed item, but a live citation *of* it whose referent the close destroyed
     — the rewrite into `BACKLOG-DONE.md` dropped the paragraph, so the ID
     resolved and the sentence around it pointed at nothing. That sub-shape sits
     between this row and ID-235's inbound-citation pass, because the ID keeps
     resolving while the target is gone; **decide which owns it when either is
     picked up.** Note a gate is harder than it looks: the defect is an assertion
     going stale, not a reference dangling, so ID-235's mechanism does not reach
     it, and the open question is whether the row can say anything more useful
     than "grep the ID and read every hit".

- [ ] **ID-207 — Push `check_formal_trace.py` past citation hygiene (steps 3 and 4 only)**
  spec: — · effort: M · audience: contributor.tooling
  ID-206 shipped `scripts/check_formal_trace.py`; a PR #663 review confirmed it
  certifies *citation hygiene at spec-ID granularity*, not clause-level
  enforcement. Two of the four hardening steps originally proposed are cheap,
  have measured motivation, and are what remains of this item:
  3. **Push T past citation.** A marker only cites an ID; it does not prove the
     test asserts the clause, is enabled, or cites the *right* ID — a
     wrong-but-real ID passes F2 and even satisfies F1. This is the
     "citation ≠ assertion" half of what BK-324's four instances exhibited.
  4. **Bar baseline growth mechanically.** `_BASELINE` shrink-only is a review
     convention; a new violation can be parked by editing the frozenset. A
     committed count or hash pinned by a separate check would make it mechanical.
  **Steps 1 and 2 were dropped, on this item's own measurement.** Step 2 (clause
  granularity instead of ID granularity) carries an L cost over roughly **2.5%**
  of the claim space — the Dafny model reaches 26 of 933 declared sections and 94
  tag sites of a corpus estimated near 3,600 clauses — and a design investigation
  found it would have caught **none** of the four motivating instances. The
  decisive case is review findings 1/3/4: BE-021's F1 was green for the entire
  life of the divergence, because the tests existed, cited the right ID, and were
  enabled, while carrying per-fixture skips and capability gates. Finer
  identifiers make omission detection finer; they do not convert it into a
  contradiction detector. It also needed an ADR before implementation, since
  sub-IDs change the spec-ID grammar
  ([`000-process.md` Rule 5](000-process.md#rules)) on which ~11,800 citations
  across 518 files depend. Step 1 (derive D mechanically from contract `ensures`)
  goes with it, being step 2's precondition.
  **Do not re-file the dropped half without new evidence** — the measurement
  above is the reason, and it is recorded here so the argument is not had twice.

- [ ] **ID-245 — Derived inventories replacing hand-maintained ones**
  spec: — · effort: M · audience: infra.test, contributor.tooling
  Four generated surfaces — three of them sharing one design decision, the
  fourth independent — and the same
  [`DRIFT-RULES.md`](DRIFT-RULES.md#rules) obligations on each: Rule 3 (the claim
  space must be *derived*, and its granularity stated), Rule 4 (which of document
  and generator governs), Rule 5 (gating or advisory, and why).
  - **Spec 003's cassette-reachability table.**
    [`003-backend-adapter-contract.md`](specs/003-backend-adapter-contract.md)
    BE-029's coverage note tabulates, per backend, which root-path conformance
    cells execute and which are pinned only in a per-backend home. Every figure
    was counted by hand, against a corpus that grows, and ID-241 has already
    rewritten it once for that reason. This is the direct instance of
    [principle 9](../CLAUDE.md#principles) on a published spec. Fix shape: a
    script that runs the conformance suite (or its collection plus the replay
    guard's verdict) and emits, per replay fixture, which cells execute and which
    skip for want of a cassette; spec 003 then cites the generator. Not derivable
    from collection alone — whether a cell needs a cassette depends on whether
    the backend issues a request, which only running it answers (ID-241).
    **Position: after ID-244**, which changes which cells a read-only backend can
    reach, so building this first would measure a surface about to move.
  - **The characteristic-accountability record** (was ID-236, absorbed here),
    research § 9 step 7.
    `check_formal_trace.py` computes a spec-coverage matrix and discards it.
    Render it at release time — every spec ID, its verification evidence (test
    marker, Dafny tag, TLA+ invariant), its status — so "what was verified, and
    by what" is answerable historically rather than only at HEAD. Its shape
    changes under ID-207, so cost is unknown until that lands.
  - [x] **The cross-artifact checker inventory** (was ID-237, absorbed here),
    research § 9 step 8. **Shipped.** [`GATE-INVENTORY.md`](GATE-INVENTORY.md),
    derived by `scripts/gen_gate_inventory.py` and gating via `--check` in both
    `lint` and `docs-gate` (two homes because CODE_PAT skips `lint` for an
    `sdd/`-only edit, which is exactly an edit to the generated file). Both
    named complications were answered as scoped: single-artifact rule checks
    carry `kind: rule` and render in their own section, alongside a third
    `kind: report` for the mechanisms that measure rather than assert; read the
    per-kind split off that file's section headings rather than from here, since
    it moves whenever a mechanism is declared. The claim space is the wiring in
    `pyproject.toml`, `.pre-commit-config.yaml`
    plus `.github/workflows/` rather than a glob, which is what reaches
    `scripts/docs/check_links.py`. Research § 4b's eleven-row table is annotated
    as a dated measurement naming the generated file as its successor. Two
    bounds worth carrying forward: a mechanism that is not a script invocation
    is out of range (the conformance suite, § 4b's one row with no successor
    entry), and the declarations' *content* is unverified — a gate rewritten to
    compare something else, with its block left alone, renders a truthful-looking
    wrong row. The full bound list is the generated file's last section.
    **One measured lesson worth carrying to the remaining bullets**, since they
    build the same shape: across six review passes the *code* converged after two
    (the last four execution-based passes found no bug between them), while the
    *narrative* around it — the generator's docstring, this entry, the research
    annotation, the trace — kept producing defects at roughly the rate the fix
    passes edited it. Every recurrence was a sentence describing code that a later
    commit changed. Two remedies worked and are worth reusing rather than
    rediscovering: name a thing once in code and render it (`_WIRING_SOURCES`,
    `_BOUNDS`), and point at the derived artifact for any figure that moves rather
    than restating it. One did not: correcting the prose in place, which is what
    the first four passes did.
  - **BE-021's divergence counts, and the artifacts that re-count against them.**
    The absent-container divergence set is stated as a bullet list in BE-021, as
    a class count in `sdd/BACKLOG.md` § 1, and again in the CHANGELOG, spec 040
    and BUG-254's register entry — in **four incompatible frames**: bullets, backend classes,
    operations, and helper call sites. Nothing derives any of them, and each
    frame is explained in prose that is itself a claim that can go stale.
    Measured cost: BUG-246 ran four numbered review rounds plus the closing
    gates, and **11 of its round-4 findings were figures or scope sentences in
    this set**, including one fixed by appending the right number beside the
    wrong one and one corrected in the same commit that falsified it by adding an
    item to the section being counted. Each fix pass added figures and produced a
    fresh defect, and the closing audit found three more after round 4 had
    declared the set clean: a `ping()` divergence titled "two backends" over a
    table naming three, a root-breach cell count stated as six in two artifacts
    where expanding the grouped rows gives seven, and a truncation item saying
    "all three" of a set the same item had just reduced to two. Fix shape: one
    authoritative divergence table that the other artifacts link to rather than
    re-count against, and delete the meta-prose explaining which frame each
    sentence uses — that prose was two of the eleven findings on its own.
    **Position: independent of the other three**, and the only one of the four
    with a measured defect rate behind it.
    **Four qualifications from the session that closed BUG-246**, each amending
    the fix shape above rather than restating it:
    1. **The four frames are four different questions, so one flat table serves
       none of them.** Bullets answer how many divergence entries exist; classes,
       how many backends disagree; operations, how wide the breach is on one
       backend; call sites, how much code implements the rule. The shape that
       works is one row per (backend × operation) carrying the clause it
       breaches, with every count derived by filtering it — never a second table.
    2. **"Delete the meta-prose" is too blunt, and following it literally will
       create a defect.** BE-021 counts move/copy as one operation in the roster
       paragraph and as two in the SQLBlob divergence bullet, seventy lines
       apart; the sentence saying so is the only thing stopping a future reader
       "fixing" fourteen or twelve to match the other. Delete prose that explains
       which frame a sentence uses; keep prose that explains why two frames
       legitimately differ.
    3. **A generator cannot produce the whole table.** "Pre-existing", "outside
       the clause until BUG-246 wrote the bound", "the error type actively
       misleads" are judgements. Realistic shape: generated columns for what each
       backend answers, curated annotations for why — which means
       [`DRIFT-RULES.md` Rule 4](DRIFT-RULES.md#authority) is answered **per
       column, not per table**. Bullet 3 shipped that pattern; its per-column
       authority table is the worked example. It also settles this bullet's
       [Rule 5](DRIFT-RULES.md#mandatory-path) side: **advisory, not gating** —
       a gate over a table containing judgements produces false failures, where
       bullet 3 gates precisely because no column of it carries one.
    4. **The set changes when the clause changes, not only when code changes** —
       and this is the blocker. BUG-255 and BUG-257 entered § Known divergences
       with no behaviour changing at all: writing the first-page bound into
       § Reach enlarged what the clause governs. A generator keyed on backend
       behaviour alone would have missed both. The input is code-behaviour ×
       clause-text, and the clause-text half has no machine-readable form today.
    **The surface to re-point**, counted at `959814e` with a case-sensitive
    match on `absent container|absent-container`, one count per file, `sdd/` and
    docs prose only: `sdd/specs/003` 15, `sdd/BACKLOG.md` 15,
    `sdd/BACKLOG-DONE.md` 9, `sdd/specs/044` 5, `sdd/specs/040` 3,
    `sdd/specs/029` 2, `sdd/specs/026` 2, `sdd/adrs/0038` 2,
    `docs-src/guides/custom-backend-guide.md` 2, `CHANGELOG.md` 1. Traces and
    the `src/`/`tests/` hits are excluded as records and as the behaviour itself.
    Read the custom-backend guide first: it is the one artifact in that set that
    never drifted, so it shows what a correctly placed statement of this clause
    looks like.
  **The shared question, now answered once by bullet 3:** a docstring
  convention, not a curated mapping — a curated mapping is precisely the
  parallel-artifact-that-drifts problem these exist to close. It shipped as the
  `Drift-gate::` block that [`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)
  now requires of every wired mechanism. The two unbuilt inventory bullets
  inherit that decision rather than re-make it. The fourth bullet never shared
  it: its answer is one table rather than a better-maintained several, and what
  it takes from bullet 3 instead is the per-column authority pattern, since the
  convention governs generated columns only and its curated ones need their
  authority stated per column.

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  spec: — · effort: S · audience: library.maintainer
  First revisit ticket for the informational `verify-tla` job landed under
  ID-147 on 2026-04-19. Per [`sdd/formal/README.md` § Authoring rules](formal/README.md#authoring-rules) (3),
  the status is revisited every 6 months or every 10 spec amendments touching
  TLA-backed sections (whichever first). At the revisit, record one of:
  **promote** (check caught a real regression — add to the gate's `needs`),
  **remove** (no catches, no active modules — drop the job), or **re-defer**
  (still useful but no catch yet — open the next revisit ticket). A calendar
  without a ticket is the same as no calendar, which is why this item exists.
  **Exit criteria:** decision logged in the ticket's close note; if re-deferred,
  the successor ticket is linked here; if promoted, `verify-tla` joins the
  `gate.needs` list in `.github/workflows/ci.yml` and the caveat in
  `sdd/formal/README.md` is updated.

- [ ] **ID-259 — Trace-outcome report revisit at the next release**
  spec: — · effort: S · audience: contributor.process
  Third revisit ticket for the release-anchored trigger ID-238 shipped;
  successor to [ID-258](BACKLOG-DONE.md), which fired at v0.32.0. Per
  [`CONTRIBUTING.md` § Release](../CONTRIBUTING.md#release) Phase 0, each release
  reads `hatch run report-trace-outcomes` and closes the open revisit ticket.
  This item is the pin that makes the ticket findable.
  **The pin lives here, not in the checklist.** `CONTRIBUTING.md` is a published
  surface, so [CONTENT-RULES Rules 1 and 5](CONTENT-RULES.md#rules) bar a tracker
  ID from it (`check_no_tracker_refs` enforces this, and caught the first attempt).
  The checklist therefore describes the behaviour and points here; this file is
  the single place that says *which* ticket is open — the same split
  `sdd/formal/README.md` uses to pin ID-150. **Separate from ID-150 for that
  reason**: two published documents pin two different tickets, with different
  triggers and different exit sets, and each mints its own successor. One merged
  ticket would falsely close one trigger with the other.
  **Record at the revisit:** the corpus totals (the baseline the following
  release differences against — the report keeps no history); the references
  selected (top-ranked row, plus any row with `rate` ≥ 1.5× the top row's at
  `reads` ≥ 20 — a fitted threshold, re-check it rather than inherit it); and per
  selected reference one of **act** (file work against it), **defer** (leave it,
  say why), or **accept** (the tags are exposure, not a defect).
  **Baseline to difference against**, measured at `1d43c1b` (the v0.32.0
  release base): 310 traces, 306 negative tags (263 `misleading`, 43 `unclear`),
  `sdd/BACKLOG.md` top-ranked at 30 over 302 reads (9.9% as the report displays
  it; compute the bar from 30/302, not from the rounded figure — ID-258 did the
  latter and review caught it). The previous two
  baselines were 302 traces / 284 tags at `6cd170c` and 270 / 207 at `4076ed7`,
  with the same top row at 9.8% and 9.3%; ID-258's close note carries both
  differences and how each selected reference was dispositioned.
  **Read the interval, not only the cumulative table.** ID-258 selected the same
  five references as ID-249, and three of them had gained no tag at all in
  between — an absolute-count ranking over a cumulative corpus re-selects on
  standing totals, so a reference can be selected twice on the strength of
  evidence already dispositioned. Difference the per-reference counts against the
  baseline above before dispositioning, and say which selections are new
  evidence and which are carry-over.
  **Exit criteria:** decision logged here, then the successor ticket opened and
  its ID named in this item's close note.

- [~] **BK-365 — Both backlog files grew past what a maintainer can read, and nothing measures it**
  spec: — · effort: M · audience: contributor.process
  **In progress: [RFC-0016](rfcs/rfc-0016-backlog-as-index.md) is accepted as
  [ADR-0040](adrs/0040-backlog-as-index.md)** for the `BACKLOG.md` half — an
  index with per-item dossiers. Shipped: the rules header, R1–R4, the § 1
  pilot (16 items to `sdd/backlog/`), § 2 (9 items), § 3 (8 items), § 4
  (5 items) and § 5 (14 items), per `sdd/rfcs/rfc-0016-measure.py`; what
  remains is the exit criteria below.
  **`sdd/BACKLOG.md` is 20,097 words at `6cec225`.** That is the file a maintainer
  reads to decide what to work on, and it is now roughly eighty pages of prose. Two
  independent multipliers got it there over seven weeks (2026-07-18 → 2026-09-05):
  the item count doubled, 28 → 57, and the median words per item doubled too,
  145 → 290. Total 4,823 → 20,097 words — 4.2× against 12.7% growth in `src/`
  over the same window. `BACKLOG-DONE.md` shows the same shape at 104,328 words
  over 651 items, and its per-release medians run from **10 words per completed
  item at v0.3.0 to 649 under `Unreleased`** — 65×, of which 2.8× arrived in the
  current cycle alone (v0.30.0 sat at 234). **Pinned because both files change on
  every merge**: re-derive rather than quote, and read the ratios, which are stable,
  rather than the totals, which are not.
  **Measured, not felt.** Derivation: for each entry, the words between its
  `- [x] **ID-NNN` header and the next header or heading, over
  `git show <sha>:sdd/BACKLOG.md` across the file's history; per-release figures
  from `BACKLOG-DONE.md`'s own `## vX.Y.Z` sections. Both were run before this
  entry was written.
  **Why this is not simply Rule 7's job.**
  [`CONTENT-RULES.md` Rule 7](CONTENT-RULES.md#kernsatz) binds `sdd/`, so it
  formally reaches both files, but it tests whether a *section* opens with its
  core claim and a backlog entry is not a section. Nothing tests whether an entry
  has outgrown its next reader, and the release step
  ([`CONTRIBUTING.md` § Release](../CONTRIBUTING.md#release)) renames
  `## Unreleased` to `## vX.Y.Z` without condensing, so nothing shortens an entry
  after it is written.
  **Answered for `BACKLOG.md` by ADR-0040:** whether a 290-word median is a
  defect or the price of [principle 9](../CLAUDE.md#principles)'s derivations.
  Length moves to a dossier rather than being cut, which is what
  [research](research/research-appropriate-level-of-detail.md) § 9.2 permits,
  and the caps are a recorded departure from its § 9.1. The question stays open
  for `BACKLOG-DONE.md`.
  **Exit criteria:** § 6 converted (dropping its `unconverted` marker, so
  R2/R3 then gate it), and a recorded decision on the
  `BACKLOG-DONE.md` half with any mechanism's bound stated per
  [`DRIFT-RULES.md`](DRIFT-RULES.md#rules).

- [ ] **BK-366 — Bug share of shipped work rose 3% → 35% across five releases, undiagnosed**
  spec: — · effort: M · audience: contributor.process
  Counting `BUG-` against all items in each `BACKLOG-DONE.md` release section:
  **v0.27.0 3%, v0.28.0 12%, v0.29.0 21%, v0.29.1 23%, v0.30.0 35%**, with
  `Unreleased` at 33% (16 of 49). Over the same window open `BUG-` items in
  `BACKLOG.md` went 1 → 22 while `src/` grew 12.7%, so a larger codebase does not
  explain it and the queue is growing rather than being worked down.
  **Two readings fit these numbers and they need opposite responses.** Detection
  improved — this repo added gates steadily, and a gate finds defects that
  previously shipped silently, which would make the trend good news. Or quality
  degraded. Nothing measured here distinguishes them, and that is the finding:
  **the repo cannot currently tell whether its central promise is holding.**
  **What would separate them**, none of it needing new tooling: whether each open
  `BUG-` escaped to a released version or was caught pre-merge; which gate or
  review caught it; and whether the classes cluster on the surfaces that grew. A
  rise concentrated in pre-merge catches on new code is detection working; a rise
  in escapes to released behaviour is not.
  **Derivation:** `BUG-` versus total entry headers per `## vX.Y.Z` section of
  `BACKLOG-DONE.md`; open counts and `src/` line totals from `git show <sha>:`
  across the same window. Run before this entry was written.
  **Exit criteria:** each open `BUG-` classified escaped/caught with the catching
  mechanism named, and a recorded answer to which reading the data supports.

- [ ] **ID-257 — Two sessions working in parallel mint the same backlog ID, and every derivation says both are right**
  spec: — · effort: S · audience: contributor.tooling
  **Reproduced by having happened**: BUG-275's branch minted `BUG-278` for a
  cross-backend divergence while a concurrent BUG-274 session minted `BUG-278`
  for something else. Neither session was careless — at mint time `master`
  carried no 278 in either backlog file, so both computed the same next integer
  and both were correct about everything they could see. It surfaced only when
  the second branch rebased and `gen-backlogid --check` reported the collision;
  one of the two items had to be retired and re-homed after the fact.
  **The gap is unmerged branches, not the floor.** `gen_backlogid.py`'s `--check`
  already takes `max(BACKLOG-DONE, BACKLOG open)` for its "Next safe IDs" line,
  and [§ How this file works](#how-this-file-works) sends an author to that
  line — so the documented procedure is sound and was followed. What no
  derivation reads is *another branch*, which is where a concurrently minted ID
  lives until it merges. An earlier account of this incident inside BUG-275's
  trace blamed the floor for reading `BACKLOG-DONE.md` only; that was wrong, and
  opening the script is what showed it.
  **One real inaccuracy to fix in passing**: the collision message prints
  `(floor: sdd/backlogid.json)`, and that file *is* BACKLOG-DONE-only, so an
  author who follows the pointer rather than the prose gets a number that may
  already be taken.
  **The open question is what mechanism**, which is why this is `ID-` and not
  `BK-`. Cheapest is a check against the remote — `git ls-remote` plus the
  backlog files on each open branch — which costs a network call on a gate that
  is currently offline and pure. Alternatives worth pricing against it: minting
  from a range reserved per session, deriving the ID from the branch, or
  accepting collisions and making the *rebase* the enforcement point, which is
  what caught this one and cost only a re-home.
  **Filed here rather than as a `BUG-`** because nothing is defective: every
  component behaved as specified, and it is the coordination between them that
  has no owner. That is this section's promise — the artifacts maintainers
  coordinate through say what is actually true — failing across two working
  copies rather than inside one.
  **A second instance, and it narrows the check's reach.** ID-182's branch
  (#998) and BK-378's branch both minted `BK-367`, for unrelated items, from a
  `master` whose next safe BK was 367 for each. The rebase reported nothing,
  because `gen-backlogid --check` compared open IDs against done ones and two
  *open* items sharing an ID passed it, so the duplicate was found by reading
  `rg -n 'BK-367' sdd` after the rebase rather than by a gate.
  **That half is now built and is no longer this item's**, under
  [`BK-383`](BACKLOG-DONE.md): `_duplicate_ids` reports one ID carried by two
  open headers, and `gen-backlogid --check` fails on it. What it does not do is prevent the
  mint, which is the open question below and the whole of what remains here —
  the gate catches the collision only once both branches have merged, and the
  re-home still has to happen by hand.
  **A third instance, one week later, on the same branch.** Re-homed to
  `BK-368`, that branch waited on review while ID-018's work minted `BK-368`
  for the conda-recipe pin gate (#1009) and closed it in the same window. This
  one the gate did report, because the other item was done by the time the
  branch rebased. Two collisions on one branch in nine days is the rate a
  long-lived PR should expect under the current scheme; the item moved to
  `BK-378`.

- [ ] **BK-385 — The duplicate-ID gate cannot see the done register, where a collision would be permanent**
  spec: — · effort: S · audience: contributor.tooling
  `_duplicate_ids` reports one ID on two **open** headers; `BACKLOG-DONE.md` is
  not read, and `_extract_ids` collapses a repeat there exactly as it did on
  the open side before `BK-383`.
  **The path is reachable and is the ordinary shape, not an exotic one.** Two
  branches mint one ID and each *closes* its item before merging — which is what
  a `/ship` delivery does at the close. Neither ID is ever open, so the
  open-versus-open rule sees nothing and the open-versus-done comparison sees
  nothing either, and the register keeps two distinct completed items under one
  ID with nothing reporting it. The open-side collision, by contrast, is loud
  the moment either branch rebases.
  **Why it was not simply widened under BK-383.** `_duplicate_ids` already takes
  `status_chars`, so `_duplicate_ids(done_text, "x")` is the entire code change —
  it was written, run, and reverted. Measured: it fails on **four** pairs already
  in the register — `BK-001` (audit workflow / Azure backend), `BUG-001`,
  `BUG-144`, and `BK-167b`, whose second header is the sanctioned `(partial)`
  split shape rather than a collision at all. Derivation:
  `python scripts/gen_backlogid.py --check` with that one line restored. The
  first three are genuine ID reuse from before the discipline existed, inside
  released sections; renumbering them would falsify the release record, and a
  gate that ships with an exemption list on its first run is fighting its
  subject.
  **So the decision this item carries is what to do about the four**, and the
  options are not equal. Grandfathering by ID has repo precedent (audit-014's
  allow-list) and costs one entry per pair plus a justification. Exempting the
  `(partial)` shape by rule is cleaner but reaches only `BK-167b`. Narrowing the
  check to the `## Unreleased` section alone would catch every *future*
  collision at the point it lands and leave released history untouched, which is
  the option this item should price first — nothing in the register's older
  sections can collide again.
  **Exit criteria:** either the done register is checked, with the four resolved
  by whichever mechanism is chosen and that choice recorded here; or the gap is
  accepted with its reason, and `gen_backlogid.py`'s stated bound is the durable
  record of it.

- [ ] **BK-384 — RFC-0015 is built but unmeasured: three deliveries decide whether it graduates**
  spec: — · effort: M · audience: contributor.process
  The open half of **BK-378**, which shipped D1 and D4 and is recorded in
  `BACKLOG-DONE.md`. Every decision RFC-0015 proposes is now in force in the
  skills — D2, D3's worktree half and D5's posting half since #1020, D1 and D4
  with BK-378 — so the RFC has, for the first time, a state its acceptance
  criterion can be read against. Nothing has read it yet.
  **What is owed** is the criterion as § Impact wrote it: three deliveries run
  under the rules, pooled, then `rfc-0015-findings.py` over them. Graduate if
  (1) the loop-introduced share of must-fix findings from round 3 on is below
  50%, (2) the derived trace block draws a finding in at most one round across
  the three, and (3) the retraction trigger fires at most once. **One delivery is
  one draw and is not the criterion.** With every decision shipped, any of the
  three failing sends the RFC back to Draft with the measured figures attached,
  not to the ADR with a softened threshold — the branch BK-379's miss was
  explicitly *not* on, and this one is.
  **Clause 2 is askable for the first time.** It had no referent until
  `ship_report.py` generated the block it names; it is read from the per-file
  count the script emits about the trace, against the hand-written block's
  measured rate of eleven stalenesses across four traces.
  **Three things stay held until the measurement, not because they are
  undecided.** D3's cap lift — panel composition must not move finding counts
  between BK-379's pilot share (RFC-0015 § Pilot result, re-based by BUG-295)
  and this sample. D5's stop-rule wiring — its dry run fired
  zero times under all three readings, so the constants ship unchanged and there
  is no firing to tune them against. D6's deferred half — the whole-file brief
  excluding the trace's `review:` key, and a measuring member re-running
  `ship-report`.
  **Three measured observations BK-378's review surfaced, for whoever takes
  this.** First, **the repo's own tooling is unmeasured by the coverage gate**:
  `pyproject.toml` scopes coverage to `--cov=remote_store`, and `ci.yml`'s
  `tooling-tests` job states it runs without coverage, so no gap in any
  `scripts/` gate can reach the 95% floor — those guards' whole value is that
  job's pass/fail. Left alone deliberately: extending the scope would put every
  existing script under a floor none was written against. Second, **D6's
  deferred half has a permission problem**, recorded in the RFC under D6: a
  measuring member cannot run `ship-report`, because it is not on `/rvw-pr`'s
  by-name allowlist and it reads comment bodies, which that skill's carve-out
  excludes. Independent re-derivation needs a mode that reads no feedback.
  Third, **the figures D4 does not cover still went stale inside BK-378's own
  loop**: the guard count and the scanned-surface count are about the work rather
  than about the review, so `ship-report` does not emit them, and both were wrong
  at the closing gate because a fix pass moved them after they were last derived.
  D4 bounds the review block alone; the rest of a trace and a register entry stays
  hand-derived, and re-deriving at the close is a convention nothing enforces.
  Whether that gap is worth a gate is this item's to decide — it is the same
  failure shape the RFC measured, one surface over.
  **The two block-handling defects BK-378's review recorded are shipped** under
  [`BK-383`](BACKLOG-DONE.md), with the duplicate-ID gate ID-257 hands over:
  D4 now states that a squash merge retires every SHA in
  `review_driven_commits`, so the list is orphaned on arrival whoever wrote it,
  and the block carries `pr` as the handle that survives; and `check_traces.py`
  refuses the duplicate `review:` key that a second paste leaves behind. What
  stays here is the measurement they were blocking, not the mechanism.
  **When pooling BK-378's PR, use 5 rounds and 54 findings, not the block's 4
  and 41.** Round 5 was the closing exit gates, run analyze-only; its 13
  must-fix findings were relayed to the author and fixed without being posted,
  so no comment endpoint carries them and `ship-report` cannot see them —
  `sdd/traces/bk-378-d1-d4.yml` states this in a note above the block. Pooled at
  4/41 that PR contributes a denominator understated by 13 of 54, which is 24%.
  Treat the 13 as loop-introduced-detectable-only-at-the-close.
  **The sample is the next three deliveries**, whichever they are. `BK-380`
  (Python 3.10's security-fix end, dated 2026-10-04) is next in line and could be
  the first of them.
  **Exit criteria:** RFC-0015 accepted or rejected with its open questions
  answered — 1, 3, 4 and 6 remain; 5 was answered by BK-378; 2 is BK-353's line
  of work and the RFC already declares it out of scope — and, if accepted,
  an ADR amending **ADR-0033/0034/0035/0037**, 0035 because D3 widens the
  one-seat trade in its "Every panel carries one measuring member" Decision
  bullet, the floor unchanged.
