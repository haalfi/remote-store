# Development Backlog
<!-- doc: repo-only -->

Active work items. [BACKLOG-DONE.md](BACKLOG-DONE.md) holds everything that
left this file: work that shipped, IDs **absorbed** into a surviving item whose
work is still open, and items **decided against**. Only the first is "completed".

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Sections are promises, not topics.** Each section states one outcome and the
condition under which it closes. Its items are mutually reinforcing: shipping
half a section under-delivers its promise, which is why they sit together
rather than under the subsystem they happen to touch.

**Admission test.** An item that fits no section's promise has no demonstrated
value and is not filed. There is no holding area — the previous Icebox was a
slow deletion that charged review attention on every pass. Of its eight items,
seven were removed and one (ID-125) was re-argued against a promise and kept, so
abolishing the Icebox was a re-decision of each item rather than a bulk delete.
**Two carve-outs.** `## Release Blockers` carries no promise by design: a
blocker is urgent by prefix, not by outcome, and is filed there regardless.
And a **refused** idea is recorded the same way a removed one is — a line in
[`BACKLOG-DONE.md` § Decided against](BACKLOG-DONE.md#decided-against), with a
`—` where the ID would be. The reasoning under § Completing work applies
identically: the argument was had, so throwing it away means having it again.

**Ordering.** Within a section the order is execution sequence, so a dependency
never sits below the thing that needs it. No section declares its own
exception. **Between sections the order is how directly the promise is felt**,
which is not the same as an audience split and is not claimed to be: sections
3 and 4 both pay users, and section 5 holds two items tagged `user.*`. Read the
promise, not the ordinal.

**Dependencies may cross sections, and the ordering rule does not reach them.**
An item in section 1 can wait on one in section 2 — BK-345 does. A cross-section
dependency is stated by ID inside the item that has it, **and named in the
depending section's `Closes when`**, because nothing about position will show it.

**Granularity.** Two tests fold work into one item: its fix surface
*coincides* with the host's, **or** one pending decision resolves both. Surfaces
that merely *overlap* stay separate, with each side naming the other and the
co-ship recorded in the trace — BUG-249 and BUG-246, both now in
[BACKLOG-DONE.md](BACKLOG-DONE.md), are that case. The decision
test is why ID-218 sits inside ID-217 and ID-123 inside ID-121: those pairs touch
disjoint paths and would be misfiled on the surface test alone.
A sub-bullet is not itself tracked and does not get an ID **for the work it
describes** — an item may still designate future work that will need its own ID,
as ID-199 and ID-140 do. **Splitting:** a section that outgrows itself becomes
two promises, never loose items.

**The admission test, granularity and splitting are not gated.** The only
backlog check is `gen-backlogid --check`, which covers the ID floor and
active/done collisions and nothing about placement, granularity or section
membership. So all three are **review-enforced**, and that is a real weakness
worth stating plainly rather than a citation: the diagnosis behind this
structure is that topic groups decayed because nothing stopped unearned items
accumulating, and conventions without a mechanism decay the same way. ID-235 in
section 6 is the host for whatever part of this becomes checkable.
(No [`DRIFT-RULES.md`](DRIFT-RULES.md#rules) obligation is claimed here — that
file scopes itself to changes that add a check, a drift report, a second
description, or a period, and an authoring convention with no mechanism is none
of those.)

**Item scope:** idea + decision-relevant constraints + open questions.
Do not repeat process steps (those live in `sdd/000-process.md` and the
ripple-check table).

**Item authority:** an item's **diagnosis** — the observed problem and the
evidence for it — is durable, and is what the item is for. Any **prescription**
it carries — a fix shape, a disposition, a line reference, a scope claim, a
reproduction recipe — is advisory, and is presumed stale by the time it is
implemented. Re-derive it against the code before acting, and correct the item
body in the same commit ([principle 3](../CLAUDE.md#principles)). An item whose
prescription survived unchecked is not evidence the prescription was right.

This is the same shape as [`CLAUDE.md` § Audits](../CLAUDE.md#audits) rule 3, for
a different artifact pair — item body against implementation, rather than audit
finding against implementation. That rule is not restated here and does not
govern this pair; see it for the audit side.
Measured failure modes behind this rule:
[research § 3.2](research/research-spec-kit-comparison.md).

**Item attributes:** each item carries a compact `spec: · effort: · audience:` line for quick scanning.
Effort: S = <1 day · M = 1–3 days · L = >3 days. `—` = not applicable.

**Completing work:**

- Fully done → delete from here, add to `BACKLOG-DONE.md` as `[x]`
  (same commit as the code change).
- Partially done → split: ship the done part to `BACKLOG-DONE.md` as `[x]`
  under its original ID, create a new ID here for the remaining work, and
  link both.
- Absorbed → the work folds into another item under § Granularity above. Mark
  the host's sub-bullet `(was PREFIX-NNN, absorbed here)`, record an entry in
  `BACKLOG-DONE.md` § Absorbed naming the host, and run the same sweep as the
  outcome below — absorption retires an ID, so it falsifies the same class of
  sentence. In this file's own restructure it required repairs to two
  `BACKLOG-DONE.md` entries and to `sdd/specs/044-graph-backend.md`. The entry
  template and the tense rule below both apply unchanged.
- Decided against → delete from here, record an entry in `BACKLOG-DONE.md`
  § Decided against, then sweep the artifacts that assert the item is currently
  tracked. The entry **must** take the header shape the other outcomes use,
  because `gen_backlogid.py` matches it and a line that merely says the same
  thing in prose is invisible to the generator, silently freeing the number for
  reuse:

  ```
  - [x] **ID-NNN — Original title**
    Why it was not worth doing, and where the diagnosis now lives.
  ```

  Em dash, not hyphen or en dash; `[x]`; ID inside `**`. Carry the diagnosis
  across, not just the verdict — [§ Item authority](#how-this-file-works) makes
  the diagnosis the durable half, and a verdict without it cannot be re-decided
  without redoing the investigation.
  **The sweep is unbounded and reviewer-enforced**, stated as a bound rather
  than pretended away ([`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)).
  Run `rg -n '<ID>' -- sdd .claude scripts docs-src tests *.md` and **read every
  hit**, not only the ones that fail to resolve: the defect is an assertion
  going stale, not a reference breaking, so a dangling-link check cannot find
  it. BK-346 instance 6 measures the miss rate for exactly this task, including
  hits missed by an author grepping the ID on purpose. Some sites name no ID at
  all and no grep reaches them — `sdd/specs/004-path-model.md` forward-points to
  a follow-up in prose — so budget a read of the specs the item touched.
  **What to fix is decided by tense, not by directory.** Fix a present-tense
  assertion that something is tracked wherever it lives, including an `Owner:`
  field inside `sdd/research/**`. Leave past-tense narration of what was decided
  at the time, which is most of `sdd/traces/**`, `sdd/research/**` and
  `sdd/audits/**` — a recommendation a research doc made then is not a claim
  about now, and `000-process.md` § Document types forbids rewriting it.
  **Accepted ADRs are never edited either way**
  ([`000-process.md` Rule 4](000-process.md#rules)): supersede if the decision
  changed, otherwise let the citation stand and let the § Absorbed or
  § Decided against entry be what makes it resolve.
  **No trace is owed** for an item removed or absorbed without being
  implemented. The rule and its reasoning live in
  [`CLAUDE.md` § Trace authoring](../CLAUDE.md#trace-authoring), which is the
  authoritative home and states the carve-out; it is named here only because
  this is where a contributor closing an item is reading.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. Monotonic, not reset per release. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Evaluated enough to earn a section, not committed to. The open question is named in the body; what is unmade is the decision, not the value. (Was "idea — not evaluated"; the Icebox was where unevaluated ideas lived, and the admission test replaced it.) |
| `AF-NNN` | Audit finding (retired — use `BUG` or `BK` for new items). |

**Assigning a new ID:** check `sdd/backlogid.json` (max per prefix from BACKLOG-DONE.md)
and the highest ID already in this file, then take the next integer. Run
`hatch run gen-backlogid` after moving items to BACKLOG-DONE.md to keep the JSON current.
`hatch run lint` flags drift and collisions.

**Retired IDs are not listed here**, deliberately: a hand-maintained
"never reassign" list is the parallel artifact
[`DRIFT-RULES.md` Rule 3](DRIFT-RULES.md#claim-space) tells us not to build, and it
would have to stay right on a path nothing tests. Twenty-three IDs were retired
by the restructure that produced this file's shape — fourteen **removed**, each
with an entry in [`BACKLOG-DONE.md` § Decided against](BACKLOG-DONE.md#decided-against),
and nine **absorbed** into a surviving item. Every absorbed ID is marked
`(was <PREFIX-NNN>, absorbed here)` in the body that took it over — enumerate
them with `rg -c '\(was [A-Z]+-[0-9]+, absorbed here\)' sdd/BACKLOG.md`, which
returns 9 and is the only derivation this count has. Keep the marker in that
literal form when absorbing anything else; a variant spelling is invisible to
the enumeration and to any check built on it.
Both classes also get a header in `BACKLOG-DONE.md`, so `gen_backlogid.py`
counts them and `hatch run gen-backlogid` keeps `backlogid.json` right.
**That is safe only as far as the entry shape is right**, which is why
§ Completing work states it as a template: the generator matches
`^- \[.\] \*\*PREFIX-NNN — ` and silently ignores anything else, so a
well-meant prose line frees the number again. Making that mechanical rather
than conventional is ID-235's structural pass, and until it lands this is a
convention with a stated failure mode rather than a guarantee.
Registering the absorbed nine is not bookkeeping for its own sake — a sub-bullet
is not separately tracked, so without an entry their citations elsewhere in
`sdd/` would resolve nowhere, including one inside an Accepted ADR that cannot
be edited to point elsewhere.

---

## Release Blockers

*(none)*

---

<a id="predictable-failure"></a>
## 1. Failures are predictable

**Promise:** a caller catches one exception type, and an absent or denied
store answers the same way on every backend.

**Closes when:** the root of an absent container meets BE-029 on every
backend (BUG-254) and a write to that root does not occupy it with a regular
file (BUG-259); a listing does not truncate silently when its container is
deleted mid-scan (BUG-255) or when a folder vanishes part-way through a
recursive walk (BUG-257); `ping()` does not report a vanished store as healthy
(BUG-256); a constructor does not leak its driver's exception
(BUG-245); one operation does not answer by payload size (BUG-253); and a newly
registered backend cannot pass CI without meeting BE-004, BE-005 and BE-021
(BK-345). The spec contradiction is adjudicated — BUG-248, closed by
[ADR-0038](adrs/0038-absent-container-outranks-drive-identity.md) — the
never-leak invariant holds on the S3 listing path, closed by BUG-249 with
BUG-246, and the last adapter answers the contract against an absent container,
closed by BUG-247. **One cross-section dependency remains**, per
[§ How this file works](#how-this-file-works): BK-345 waits on **ID-244** in
section 2 for the seeding hook, stated inside the item that carries it, so this
section cannot close on its own items alone. BUG-249's denied half carried a
second such dependency on **ID-242**; it shipped with the denied path asserted by
the hand-written 403 probe that item names and by nothing in conformance, which
is why ID-242 is still open and still worth doing.

**Three backend classes** now disagree with **the absent-container clause** —
`S3Backend` and `S3PyArrowBackend` (BUG-255), and `GraphBackend` (BUG-257) —
counted from BE-021's § Known divergences list, which this section tracks bullet
for bullet and which holds two bullets, the first naming two classes. BUG-255 and
BUG-257 joined that list rather than the "further disagreements" below it when
BUG-246 gave § Reach an explicit first-page bound: before that the clause said
only what an absent container answers, so a container that vanished *during* a
listing was outside it; now the bound is part of the clause and missing it is a
breach of it. Writing a rule into a clause enlarges what the clause governs, and
the two items that changed side are the evidence — neither was a new defect, and
both were pre-existing behaviour that a new sentence made answerable.
**Five** further disagreements sit in this section and none of them is with the
absent-container clause, which is why they are not in that count: BUG-253 is
between two halves of one Graph operation; BUG-245 is a constructor leak, which
BE-021 scopes to operations and so does not reach; BUG-254 is with **BE-029's
root row**, which BE-021 § Reach now defers to rather than deciding, so the
breach is of the row § Reach points at and not of the clause this count is about;
BUG-256 is about a health probe, which is off the roster BE-021 governs; and
BUG-259 is a write to the store root leaving an absent container occupied by a
regular file, which is BE-029's root row again on the write path.
**Six classes** have left the list on the *empty-listing and NotFound* rows —
counted as classes, which is the frame this paragraph opens in and not the bullet
frame the sentence above it uses. `GraphBackend` went first — BUG-248 adjudicated
the spec contradiction behind it and brought the backend to the contract in the
same change, which is why BK-345's exemption list, blocked on that adjudication,
can now be written. `S3Boto3Backend`, `AzureBackend`, `AsyncAzureBackend` and
`SQLBlobBackend` followed with BUG-246 and BUG-249. `LocalBackend` is the sixth
and the last: BUG-247 stopped its containment check reporting an absent root as
a path escape, which was the one case where the clause *misreported* rather than
merely mistyped — an absent store answered as a malformed path, on the most-used
backend. Graph is on both sides of this paragraph and that is not a bookkeeping
error: it meets the rows it was brought to and misses the bound that arrived
after, which is what a clause growing a new sentence does to a backend that was
compliant the day before.

- [ ] **BUG-254 — Five backend classes breach BE-029's root row against an absent container**
  spec: BE-004, BE-021, BE-029 · effort: S · audience: user.api
  BE-029 already decides this and is not qualified by whether the container
  exists: the root is "a folder that always exists", `exists(root)` is `True`, and
  `get_folder_info(root)` "aggregates the whole store (never `NotFound`)".
  Measured against the absent-container stubs BUG-243 added and a dropped SQLite
  table. **Bold cells breach that row; the others are what it requires** — the
  table records both so the fix has its control:
  | Backend | `get_folder_info("")` | `exists("")` | `is_folder("")` |
  | --- | --- | --- | --- |
  | S3, S3-PyArrow | `FolderInfo(file_count=0)` | **`False`** | **`False`** |
  | S3-Boto3, Azure (sync and async) | **raises `NotFound`** | `True` | `True` |
  | SQLBlob | `FolderInfo(file_count=0)` | `True` | `True` |
  SQLBlob's row is what compliance looks like; BUG-246 brought it there.
  **Seven class-cells breach**, across three columns and five classes — counted
  by expanding each grouped row over its classes: the first row's two bold
  columns across two classes is four, the second row's one bold column across
  three classes is three.
  Five classes because the two Azure adapters carry their own copies and each
  needs its own fix, which is the frame BUG-246 and the CHANGELOG both use.
  The breaches run in two opposite directions, which is why one fix will not cover both:
  the s3fs lanes go to the wire for `exists("")` and report a missing bucket as
  "the root is not there", while S3-Boto3 and Azure short-circuit `exists` but let
  `get_folder_info` reach a listing whose 404 they do not tolerate at the root.
  A caller cannot ask "is my store there?" portably: `exists("")` answers `True`
  on three backends whose container is gone and `False` on two.
  **Pre-existing.** BUG-246 changed neither the root short-circuits nor
  `get_folder_info`'s root handling on any backend but SQLBlob, and did not touch
  the s3fs lanes at all (`git diff origin/master...HEAD` over `_s3.py`,
  `_s3_pyarrow.py`, and `_s3_boto3.py`'s `get_folder_info`). SQLBlob's row is the
  one exception, and it is compliant rather than breaching: that change did
  briefly introduce the `NotFound` breach there and then fixed it in the same PR,
  with `tests/backends/sqlblob/test_absent_table.py` pinning both spellings of
  the root. Re-measured on this branch against a dropped table
  (`tmp/measure_254_sqlblob.py`): `get_folder_info` returns
  `FolderInfo(file_count=0, total_size=0, modified_at=None)` and both probes
  answer `True`, for `""` and `"."` alike.
  No spec decision is needed first — BE-029 states the answer. What the fix owes
  is the *reason* each backend misses it, since the two directions have different
  causes, plus a conformance cell so a sixth backend cannot inherit either.
  **Filed on a wrong premise and corrected in the same PR:** the first version of
  this item said nothing decided the question and asked for a spec decision. That
  was read off BE-021 § Reach alone, which decides operations and is silent about
  the root; BE-029's table decides it and was not consulted. Recorded because the
  same miss is available to the next reader of § Reach.

- [ ] **BUG-256 — `ping()` reports a healthy store on three backends whose container is gone**
  spec: PING-001 · effort: S · audience: user.api
  PING-001's postconditions give `ping()` a `NotFound` for a "missing
  bucket/container/path". Measured against an absent container:
  | Backend | `check_health()` |
  | --- | --- |
  | S3, S3-Boto3, Azure (sync and async), Local | raises `NotFound` |
  | S3-PyArrow, SQLBlob, **SQLQuery** | returns cleanly |
  | ReadOnlyHttp | raises `BackendUnavailable` — wrong type, not a missing raise |
  Both SQL backends inherit the same bare `SELECT 1` on
  `_SQLAlchemyBaseBackend`: it verifies connectivity and never looks at the table
  or the queried relation, so a dropped table and a discarded in-memory store both
  read as healthy. `SQLQueryBackend` overrides nothing, which is why naming only
  `SQLBlobBackend` understates it. The `S3PyArrowBackend` probe misses it for the
  same reason one layer out. `ReadOnlyHttpBackend` is a fourth case of a different
  kind and is listed so a fix does not stop at the three.
  **Five documentation surfaces promise the behaviour** and are part of this item
  rather than of BUG-246, which measured the divergence but did not create it:
  `Backend.check_health` and `AsyncBackend.check_health` docstrings,
  `Store.ping()`, `AsyncStore.ping()`, and `docs-src/guides/health-check.md`.
  The caller this hurts is the one doing the obvious thing — using `ping()` at
  startup to check the store is really there — and getting "yes" for a store that
  is not. It is also the operation an absent-container caller is *sent* to by the
  error-model docs, which is how this was found.
  **Pre-existing**, and out of BE-021's reach: a health probe is off the roster
  that clause governs, which is why the divergence lives under PING-001 rather
  than in BE-021's list. Discovered while measuring BUG-246's migration advice,
  which is why that advice sends callers to `write()` instead.

- [ ] **BUG-255 — A container deleted mid-listing truncates the listing silently on the two s3fs lanes**
  spec: BE-021 · effort: M · audience: user.api
  `ListObjectsV2` answers an absent prefix with `200 KeyCount=0`, so the only 404
  a listing can raise is the container's — which is why reading that 404 as "the
  container is absent, so it holds nothing" is safe on the *first* page. It is not
  safe on the second: by then the listing has already yielded items, so the
  container demonstrably existed, and a 404 means it was deleted underneath the
  scan. Measured with a stub serving a valid first page carrying a
  `NextContinuationToken` and `NoSuchBucket` on the second:
  | Backend | `list_files("", recursive=True)` |
  | --- | --- |
  | S3, S3-PyArrow | yields 0 items, then returns cleanly |
  | S3-Boto3, Azure, Async Azure | raises `NotFound` after the first page — fixed by BUG-246 |
  Measured for `list_files` on a page of keys; re-measured for all five listings
  on both page shapes (keys-only and prefixes-only) once the bound moved onto the
  page, which is the parametrisation
  `TestTheAbsentBucketToleranceIsBoundedToTheFirstPage` and its two Azure twins
  now carry.
  The two s3fs lanes report a *complete* listing that is not complete — the other
  three rows are the control, and are what the fix looks like. The caller most hurt
  is the one doing list-then-delete or list-then-sync: it sees a short list, treats
  the absent entries as absent, and deletes or fails to copy data that was there.
  **Pre-existing on the two s3fs lanes**, which is what makes this an item rather
  than a BUG-249 residue: they truncated this way before that change and still do.
  **The two s3fs lanes are what this item is left holding.** BUG-246
  and BUG-249 briefly put `S3Boto3Backend` and both Azure adapters onto this
  truncation — the boto3 lane by replacing a leaked `ClientError` with a
  swallowed 404, the Azure adapters by adding a swallow where the flat lane
  previously raised — and then bounded the tolerance to the first page on all
  three. The bound is keyed on a **page** having come back, which is the second
  thing that PR got wrong and had to re-measure: keyed on a yielded *item*, as it
  first shipped, every listing stayed blind on the page shapes its own filter
  empties, so a folders-only first page still truncated `list_files` and a
  keys-only one still truncated `list_folders`. **Four** of the five listings per
  lane were blind — `list_files`, `list_files-recursive`, `list_folders` and
  `glob`, measured by putting the item-keyed source back under the current tests
  and counting failures (12, across the three lanes); `iter_children` yields both
  kinds and so has no blind page shape, which is why it is the control. The Azure
  HNS branches carry the bound too, and are executed: an ADLS Gen2 `List Path`
  wire stub reaches all ten of them without Docker, which retired the claim that
  only the Docker-gated fixture could. SQLBlob is not affected (one `SELECT`, no
  pages).
  **A correction worth keeping**, because it cost a round: that PR first recorded
  the Azure rows as pre-existing, on the strength of a base-versus-head
  measurement that was broken — the base run set `PYTHONPATH` to a worktree root,
  and this package lives under `src/`, so the import silently fell back to the
  editable install and measured *head* twice. Re-run with `PYTHONPATH` pointing
  at `<worktree>/src` and the module's `__file__` printed, the base revision
  raises. The lesson is the repo's own: a verification that can fail silently is
  worse than none.
  The fix shape is settled and already implemented on the other three lanes: a
  first-page bound — tolerate the container 404 only while nothing has been
  yielded, and let a later one propagate. `_flat_ns._ListingCursor` is the shared
  piece; `S3Boto3Backend._listing_errors` is the worked example. What remains is
  applying it to `_S3Base`'s s3fs-backed listings and pinning it per lane, which
  closes the divergence rather than opening one. Take the bound from the worked
  example rather than from this paragraph's first sentence: it is keyed on a page
  having come back, not on an item having been yielded.

- [ ] **BUG-257 — `GraphBackend` restarts the first-page bound at every folder of a recursive walk**
  spec: BE-021 · effort: M · audience: user.api
  BE-021 § Reach requires a container 404 arriving after a listing has received a
  page to propagate rather than end the iteration. `GraphBackend` keys that bound
  per **HTTP request** — `_iter_child_items` in
  `src/remote_store/aio/backends/_graph/backend.py` sets its `started` flag
  inside one request — while `_walk_files` issues one request per folder, so
  every subfolder listing starts the bound over at `False`.
  Measured with `respx` against the real backend: `list_files("", recursive=True)`
  where the root `/children` returns `[a.txt, sub/]` and `sub`'s `/children`
  returns 404 **returns `["a.txt"]` cleanly** — a truncated listing that reads as
  complete. Reproduced with both `itemNotFound` and `resourceNotFound` bodies,
  which matters because listings run at item scope where `graph_error_for` maps
  any 404 to `NotFound`, so a genuinely deleted drive produces this.
  The control passes: page 1 followed by a 404 on the `@odata.nextLink` **does**
  raise `NotFound`, so the single-listing bound is correct and only the walk is
  not.
  **Pre-existing, and surfaced by a spec edit rather than by a code change.**
  BUG-246 wrote the first-page bound into § Reach; before that no clause decided
  the mid-scan case and this was undecided behaviour rather than a breach.
  BUG-248 had brought Graph to the clause's other rows in the same section, which
  is why it appears on both sides of § 1's paragraph.
  The fix shape is `S3Boto3Backend.list_files`, where one `_listing_errors`
  cursor wraps the whole breadth-first walk so a 404 on any sub-prefix
  propagates: hoist the flag out of `_iter_child_items` and thread it through
  `_walk_files`. **The fix lands once**, unlike the Azure case: `GraphBackend` is
  a single class and sync access goes through `AsyncBackendSyncAdapter`
  ([ADR-0025](adrs/0025-async-to-sync-backend-adapter.md)), not a second copy of
  the walk. Only the *cells* need a sync lane.

- [ ] **BUG-259 — `SFTPBackend` writes leave an absent `base_path` occupied by a regular file**
  spec: BE-029, BE-021 · effort: S · audience: user.api
  Write to the store root of an SFTP store whose `base_path` does not exist and
  the bytes land at the container path itself, leaving the store's container a
  regular **file**. `open_atomic("")` does not even raise — it returns cleanly
  having done it. Measured against the Stage-1 in-process paramiko server, with
  `base_path` absent, checking the server-side filesystem after each call:

  | Call | Server-side result | Raised |
  | --- | --- | --- |
  | `write("")` / `write(".")` | `base_path` is a file, size 1 | `InvalidPath("Path is empty after normalization")` |
  | `write_atomic("")` / `write_atomic(".")` | `base_path` is a file, size 1 | `InvalidPath("Path is empty after normalization")` |
  | `open_atomic("")` / `open_atomic(".")` | `base_path` is a file, size 1 | — **returns cleanly** |
  | `write("")`, `base_path` present | unchanged directory | `InvalidPath("Not a file: ")` |

  Note the error on the absent-`base_path` rows carries no `backend=` attribute:
  it arrives from the `RemotePath` / `WriteResult` layer *after* the write, not
  from the backend before it. The backend's own root guard is the observational
  `is_dir()`-shaped check, which answers `False` when the container is gone.
  Afterwards `is_folder("")` still answers `True` from SFTP's root
  short-circuit, so BE-029's "a folder that always exists" becomes a claim about
  a regular file and every later call answers about a store that cannot exist.
  **This is BUG-247's defect on the other hierarchical backend**, found by that
  work's round-3 measuring pass rather than by reading: BUG-247 borrowed SFTP's
  *read*-side root short-circuits, which are correct, and did not look at its
  write paths. The fix has the same shape — refuse the root key definitionally,
  before the transport is touched — but the surfaces only *overlap*
  ([§ Granularity](#how-this-file-works)), so it is a separate item.
  **Not co-shipped with BUG-247 deliberately:** that item's scope is Local, and
  widening it to a second backend mid-review would have put an untested SFTP
  change into a PR whose SFTP claims are otherwise measurement-only.

- [ ] **BUG-245 — `SQLBlobBackend(create_table=False)` leaks `NoSuchTableError` from its constructor**
  spec: BE-021, SQL-BLOB-012 · effort: S · audience: user.api
  Reflection is unguarded: `sa.Table(name, meta, autoload_with=engine)` against an
  absent table raises `sqlalchemy.exc.NoSuchTableError`, which reaches the caller
  unmapped. Every other backend's constructor rejects bad configuration with
  `ValueError` (`validate_azure_params`, the S3 bucket check), so a caller
  wrapping construction in `except (RemoteStoreError, ValueError)` catches
  every backend but this one — and the escaping type is a SQLAlchemy import the
  caller may not have.
  Reproduction: `SQLBlobBackend(engine=sa.create_engine("sqlite:///:memory:"),
  table_name="nope", create_table=False)`.
  BE-021's "backend-native exceptions never leak" is scoped to operations, so
  this is a gap in the contract as much as in the code: decide whether
  construction is in scope for the mapping rule, then map it. Note the behaviour
  itself is right — refusing to bind to an absent table is a sound thing to do,
  and is pinned by `tests/backends/sqlblob/test_absent_table.py`; only the error
  type is wrong.

- [ ] **BUG-253 — `GraphBackend.write` answers a file-ancestor path differently by payload size**
  spec: BE-008, GR-019 · effort: S · audience: user.api
  `write("blocker.txt/child.bin", …)` raises `InvalidPath` when the body takes
  the small `PUT /content` path and `NotFound` when it takes the upload session,
  for the identical path against the identical store — the answer depends on
  whether the payload crosses `_SMALL_FILE_MAX_SIZE` (4 MiB), which is not
  something a caller reasons about.
  Cause: `_write_small` runs `_raise_if_file_ancestor(path)` before classifying
  its `404` (ID-209/ID-211), and the large path calls `upload_session(...)`
  directly with no such walk, so `_create_upload_session`'s `404` goes straight
  to the classifier. `write`'s own docstring promises `InvalidPath` "if the path
  … descends through a file ancestor" without qualifying by size, so the large
  path contradicts it.
  Predates BUG-248 — that change aligned the two halves on the absent-drive axis
  and left this one — and was found by its round-3 panel while checking both
  write halves. The fix is presumably to hoist the ancestor walk to `write`, or
  to run it on the session-creation `404` as the small path does; measure which
  before choosing, since the walk costs a round trip on a path that has already
  failed.

- [ ] **BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt**
  spec: BE-021 · effort: M · audience: infra.test
  The rule binds every backend that can delete and whose container can be
  absent, and it is verified by six hand-written per-backend suites
  (`tests/backends/{s3,azure,azure/aio,sqlblob,sftp,local,graph/aio}/`).
  `tests/backends/conformance/` gained nothing, so a seventh such backend
  inherits no cell and passes CI without ever meeting the clause.
  This is not hypothetical. `GraphBackend` went unexamined through six review
  rounds of the change that wrote the rule (BUG-243) and turned out to contradict
  it — BUG-248, since closed. A registry-driven cell would have failed on the
  first run, and would also have shown the contradiction's real width: BUG-248
  was filed as reaching two operations and measured at eleven.
  The repo already has the shape for this: [`sdd/TESTING.md`](TESTING.md)
  Rule 13 § "Declaring an exemption" — a self-pruning exemption list where
  silence is not consent. The work is a conformance cell parametrised over the
  backend registry, plus an explicit exemption entry for the four backends BE-021
  names as out of scope (`MemoryBackend` and `AsyncMemoryBackend`, whose
  container is an in-process dict; `SQLQueryBackend` and `ReadOnlyHttpBackend`,
  which do not declare `DELETE`).
  **Depends on ID-244 for the mechanism.** The other dependency, BUG-248 for the
  exemption list, is discharged: `GraphBackend` meets the clause on every
  operation BE-021 decides, so it is a plain cell rather than an exemption, and
  the two *backend operations* that keep Graph's drive-identity escalation
  (`write`, `check_health`) are outside what the clause states — as are its two
  non-operation callers, drive-id resolution and the copy/move monitor poller,
  which a per-backend conformance cell does not reach at all. See
  [ADR-0038](adrs/0038-absent-container-outranks-drive-identity.md).
  An absent container is not a state most conformance fixtures can reach: the S3
  and Azure lanes need a stub that 404s at container level (BUG-243 built those),
  SQLBlob needs a dropped table, Local needs its root deleted, and Graph needs a
  respx route. That is the same per-fixture arrangement hook ID-244 has to decide
  where to bind, so this item consumes that decision rather than making its own.
  **Graph's lane cannot be a cassette**, and not by preference: cassettes are
  recorded from live Graph, which answers a nonexistent drive with
  `itemNotFound` (GR-031's verification note), so the drive-identity code has
  never been recorded — `rg -l resourceNotFound tests/backends/cassettes/`
  returns 0 files against 53 Graph cassettes carrying a `404`. The `graph_replay`
  fixture therefore cannot reach the absent-container state at all, and a
  hand-written cassette would fabricate a response the tier has never produced.
  This is the item that makes the section's promise stay true for backend seven,
  which is why it sits here and not with the coverage work.

---

<a id="correct-and-proven"></a>
## 2. Answers are correct, and the contract is proven

**Promise:** the same call returns the same right result on every backend, and
no clause of the contract ships unexercised.

**Closes when:** the six defects and holes enumerated below are closed — three
wrong answers (BUG-241's unescaped `LIKE` metacharacters, BUG-240's `max_depth`
contradiction, BUG-251's cross-store cache collision) and three coverage holes
measured in cells (ID-244's WRITE-gated classes, ID-242's four pragmas,
ID-247's 22 root-path cells).
**Bounded deliberately.** "No clause ships unexercised" is the promise, not the
closing condition: nothing derives the full set of unreachable clauses today,
which is what ID-245's inventory in section 6 would supply. Until it does, this
section closes on a counted list rather than on a claim nobody can check —
saying otherwise would make the promise unfalsifiable, which is the failure this
structure exists to remove.

A corrected clause nobody tests is the same defect one layer up, which is why
the wrong-answer defects and the coverage holes are one promise. The wrong-answer
defects come first because a user can hit them today. **One item here is depended
on from section 1**: BK-345 waits on ID-244's per-fixture seeding decision, so
section 1 cannot close before it lands even though it sits here. ID-242 was a
second such dependency, from BUG-249's denied path; that item shipped without it,
leaving the denied listing asserted by one hand-written 403 probe and by nothing
in conformance — the exact hole ID-242 exists to fill, now with a shipped clause
resting on it rather than a pending one.

- [ ] **BUG-251 — A shared `cache_backend=` serves one store's bytes for another's**
  spec: RES-100 · effort: S/M · audience: user.api
  `ext.cache` derives keys from `(operation, path)` with nothing identifying the
  store, so two `Store`s at different roots sharing one `cache_backend=` collide
  on any path they both hold, and the second reader gets the first store's
  content. Silent wrong data, not a wrong error type.
  **Reproduced**, `hatch run python` against two `LocalBackend` roots each
  holding a distinct `same.txt`, sharing one `MemoryCache`:
  `store_a.read_bytes("same.txt")` → `b"FROM-STORE-A"`, then
  `store_b.read_bytes("same.txt")` → `b"FROM-STORE-A"`. Not Graph-specific —
  identical for two S3 buckets or two Azure containers.
  Filed from audit-016 L8, which diagnosed it as an aside to ID-123's
  key-derivation work. It is not an aside: it needs no `CompositeStore`, it is
  reachable on shipped code, and leaving it inside an idea that may legitimately
  close as "declined" would retire a data-correctness defect with it.
  **Fix shape is open and belongs with ID-121's design**, which is where
  identity-derived keys are being decided: the narrow fix is to mix the backend
  identity into the key, the wide one is the `ResolutionPlan`-derived scheme
  ID-121 carries. Opt-in surface, so no contract risk either way — but decide
  whether an unkeyed shared cache should raise rather than silently collide.
  **Test shape:** two stores at different roots, one shared cache, same relative
  path, assert each reads its own bytes.

- [ ] **BUG-241 — SQL prefix probes build `LIKE` patterns without escaping `_` and `%`**
  spec: — · effort: S · audience: user.api
  `SQLBlobBackend._reject_folder` builds `LIKE key + "/%"`, and every other
  prefix probe in `_sqlalchemy.py` follows the same convention. In SQL `LIKE`,
  `_` matches any single character and `%` matches any sequence, so a key
  containing either over-matches: probing `a_b` also matches `axb/...`, and a
  key containing `%` matches far more.
  **Consequence:** the wrong-type probe can report a folder that does not
  exist, turning a `NotFound` into an `InvalidPath` for a sibling key whose
  name merely resembles the target. Underscores in object keys are common, so
  this is a wrong answer on ordinary data rather than a wrong error type.
  The convention is file-wide, so fixing one site without the rest would be the
  inconsistency this section exists to remove. Fix them together with
  `ESCAPE`, or a dialect-appropriate equivalent.
  **Test shape:** seed sibling keys that differ only in a `LIKE` metacharacter
  position and assert the probe does not confuse them.

- [ ] **BUG-240 — ASYNC-014 and DEPTH-003 state opposite rules, and `GraphBackend` implements the async one**
  spec: ASYNC-014, DEPTH-003 · effort: S/M · audience: user.api
  [ASYNC-014](specs/029-async-store-backend-api.md) says "`max_depth` limits
  traversal depth (when set, `recursive` is ignored)" **while citing DEPTH-003**,
  which states the opposite for the Backend ABC: `max_depth` applies only when
  `recursive=True`. `GraphBackend.list_files` follows ASYNC-014 and pins it at
  `tests/backends/graph/aio/test_list.py:183` — `recursive=False, max_depth=2`
  returns depth-2 files, where a sync backend returns immediate children only.
  So identical arguments return different files depending on the backend.
  **Both readings are asserted by a passing test, on different backends.** That
  is the state Rule 7 calls a live disagreement rather than a defect in one side,
  so which way it resolves is a decision, not a lookup.
  **The split is inside the async lane, not between the lanes.**
  `AsyncMemoryBackend` and `AsyncAzureBackend` implement DEPTH-003's reading;
  `GraphBackend` implements ASYNC-014's — two async backends already disagree
  with a third.
  **Three artifacts assert the ASYNC-014 reading, not one.** ASYNC-014 itself,
  `tests/backends/graph/aio/test_list.py:183`, and `GraphBackend.list_files`'s
  own docstring — which BK-331 made *authoritative* for depth strategy by
  replacing spec 037's per-backend table with a pointer to each backend's
  docstring. So closing this means changing a doc BK-331 promoted to source of
  truth.
  **Why nothing caught it:** there is no async twin of
  `test_list_files_non_recursive_ignores_max_depth`, so conformance never
  cross-checks the two; and both `Store` and `AsyncStore` normalise `max_depth`
  into `recursive` before delegating, so the divergence is invisible to every
  caller above the ABC. Reachable only by a direct backend call.
  **Whichever way it goes, the async conformance cell is part of the fix** —
  without it the next divergence is equally invisible. Expect it to turn a
  backend red on arrival; that is the item working, not a regression.

- [ ] **ID-244 — A read-only backend cannot reach any WRITE-gated contract cell**
  spec: — · effort: M · audience: infra.test
  Sibling of [ID-241](BACKLOG-DONE.md) (shipped), and the same class: a rule
  gated so no fixture ever runs it. Here the gate is the **seeding discipline** —
  conformance cells that need data call `backend.write`, so they sit behind
  `fixture_params(Capability.WRITE)`. Any contract that happens to live in such a
  class is therefore unreachable for a read-only backend, *including contracts
  that have nothing to do with writing*.
  **Measured instance.** SIO-009 (laziness: a LAZY_READ backend must not return a
  BytesIO-backed stream) lives in `TestStreamingConformance`, a WRITE-gated class.
  `ReadOnlyHttpBackend` is the registry's **only read-only LAZY_READ declarer** —
  streaming is the whole justification for its capability set, per
  `tests/backends/http/test_config.py::test_capabilities_are_read_metadata_lazy` —
  and it was structurally excluded from the only cells asserting that contract.
  The two per-backend read tests did not compensate: both assert content and
  chunking, which a pre-loaded `BytesIO` satisfies identically.
  Pinned per-backend by BK-340 in `test_read_is_lazy_not_bytesio`; that is a patch
  over a structural hole, exactly as `tests/backends/sqlquery/test_config.py`'s
  root cells were before BK-340 registered a fixture.
  **The same hole is why BK-340's own `sqlquery` fixture reaches only 77 cells.**
  Its content-bearing surface — read, glob, listing with keys present — is
  WRITE-gated end to end, so registering the fixture bought the
  capability-independent contract and nothing else.
  **This item owns the arrangement-hook decision for BK-345 too.** The fix is a
  seeding indirection (a per-fixture `seed` hook the cells call instead of
  `backend.write`), and *where it binds* is unmade — on the fixture, on the
  helper, or as a capability-neutral rewrite of the affected classes. The answer
  decides how much of the conformance suite changes, and a hook whose seeded
  content cannot round-trip (SQLQueryBackend materialises result sets, so
  `read(k)` never returns the bytes a seeder "wrote") constrains it further: the
  hook must express *presence*, not content, or the cells that use it must not
  assert content. BK-345 needs the same indirection to make a container absent,
  so decide the binding once for both shapes.

- [ ] **ID-242 — Four `moto doesn't raise PermissionError` pragmas are coverage holes, not exemptions**
  spec: — · effort: S · audience: contributor
  `_s3_base.py` 510/540/573 and `_s3_pyarrow.py:626` each carry
  `# pragma: no cover -- moto doesn't raise PermissionError`. The mappings are
  correct and the pragmas are accurate statements about the fixture, which is
  exactly the problem: **BUG-242 was a defect living behind the fifth instance
  of this same pragma**, on the one branch that mattered, invisible to a suite
  of 7976 passing tests.
  A true "the fixture cannot reach this" is a coverage hole wearing an
  exemption's clothes. It is indistinguishable from a real exemption at read
  time, so it never gets revisited.
  **Now cheap to close:** `tests/backends/s3/test_denied_probe.py` established a
  `pytest-httpserver` harness that serves real 403s at Stage 1, no Docker and no
  credentials. Each remaining pragma is a few params on that harness. Ship it
  independently of ID-244 — nothing here waits on the seeding decision.

- [ ] **ID-247 — Record the Graph root-path cassettes**
  spec: BE-029 · effort: S · audience: infra.test
  22 `TestBackendRootPath` cells still skip on `graph_replay` for want of a
  recording — the "pinned nowhere" column of spec 003's BE-029 table. Graph is
  the only HTTP family with **no emulator tier** (`graph_live` Stage 3 and
  `graph_replay` Stage 1, nothing between), so those contracts are unexercised
  against `GraphBackend` at every stage below a live account; Azure's equivalent
  skips are covered by `azurite` at Stage 2. 14 of the 22 are Graph-only —
  Azure passes them with no cassette at all (ID-241).
  `python scripts/record_cassettes.py --backend graph` needs `RS_TEST_LIVE_GRAPH=1`
  plus `GRAPH_CLIENT_ID` / `GRAPH_TENANT_ID` / `GRAPH_DRIVE_ID` (device-code, so
  interactive). Prefer `--node` per cell: a full run re-records all 119 existing
  graph cassettes, churning their volatile headers into an unreviewable diff
  against TEST-009. Any op that raises before issuing a request records nothing
  and keeps skipping — correct since ID-241, and visible in the Step-5 replay.

---

<a id="users-succeed-unaided"></a>
## 3. Users succeed without asking us

**Promise:** a user gets set up, picks the right backend, writes their own, or
copies an example, without opening an issue.

**Closes when:** every published page and shipped example a user decides from is
**true** (BK-339, BK-325, ID-125), **reachable** (BK-327), and **walked
end-to-end by a maintainer** (BK-332, and ID-199's authoring contract). Each
clause names the items that move it, so closure is checkable rather than
asserted.

This is the group that converts directly into support load not arriving. The
rehearsal sits with the guides because it is the only mechanism that has ever
found their defects, and BK-327 sits here rather than with the gates because a
page nobody can navigate to is a page nobody reads — the gate is the mechanism,
not the payoff.

- [ ] **BK-339 — Decide what replaces `store.md`'s hand-maintained Backend Behavior Matrix**
  spec: — · effort: M · audience: user.site
  `docs-src/reference/api/store.md` § Backend Behavior Matrix hand-maintains five
  behavioural rows across ten backends, and carries the line *"Verify against
  actual code before relying on these in production"* — a reference page telling
  readers not to trust it, which is the admission that it drifts. Users read this
  table to choose a backend.
  **One measured error, not a suspicion.** The `copy()` preserves metadata` row
  says `—` for Memory, but `MemoryBackend.copy` constructs the destination with
  `metadata=src_node.metadata` (`src/remote_store/backends/_memory.py`), so user
  metadata survives a copy. The row is also **ambiguous in a way that hides the
  error**: Local's cell reads "Yes (`copy2`)", which is filesystem metadata,
  while Memory's concerns user metadata — one row conflating two different
  properties, which is why a reader cannot tell a wrong cell from an
  out-of-scope one. Fixing the cell without splitting the row re-hides it.
  **The disposition is the work.** Rows divide three ways: derivable from
  capability declarations (`Native glob()` duplicates the capabilities matrix's
  GLOB row — the two currently agree, so this is duplication rather than
  contradiction); genuinely useful user information available nowhere else
  (`move()` atomicity, `write_atomic()` mechanism); and under-specified
  (`list_files()` ordering, which the specs do not guarantee — publishing
  per-backend orderings invites reliance on an unguaranteed property). Deleting
  outright would remove real value; deriving needs declarations that do not exist
  for the middle group.
  **Check `capabilities-matrix.md` at the same time** — it is the neighbouring
  ten-backend table and a candidate home for the derivable rows, but whether it
  is generated or hand-maintained was not established.

- [ ] **BK-325 — Custom-backend guide: registry-integration and remaining contract-topic gaps**
  spec: — · effort: M · audience: user.site
  Guide content the PR #932 walkthrough showed a real backend needed but
  the guide never teaches:
  - Registry integration: credential-named YAML options arrive wrapped in
    `Secret` (constructors need `str | Secret` and `.reveal()`), and a
    `retry:` block injects a `retry=` kwarg. Step 13 says only "names
    must match". Reference shape: `S3Boto3Backend.__init__`.
  - Stream-time error mapping for `LAZY_READ` backends: the cardinal rule
    covers call time only; lazy streams surface native errors during
    `read()` and `test_streaming.py` enforces no-leak there.
  - The file-ancestor lane: `rejects_write_under_file_ancestor`,
    `strict_only` fixtures, and their `_MODULE_FOR` wiring are
    undocumented; skipping them silently drops ~25 conformance cells.
  - Small fixes: error-mapping checklist lacks a base-`RemoteStoreError`
    fallback row; `from exc` guidance omits the deliberate `from None`
    pattern; the `SEEKABLE_READ` note contradicts shipped range-readers.

- [ ] **ID-199 — Backend setup & configuration guides expansion**
  spec: — · effort: L · audience: user.site, library.maintainer
  Expand the backend-related guide set in `docs-src/guides/` based on user
  pain mined from two sources: in-repo signal (traces, BACKLOG, CHANGELOG,
  PRs) and an external survey of GitHub issues across `boto3`/`s3fs`/
  `azure-storage-blob`/`paramiko`/`fsspec`, Stack Overflow, Reddit, and
  vendor forums. Seven candidate guides identified; full pain mapping,
  scope boundaries, sequencing, and code-side flags are in
  [research](research/research-backend-setup-guides.md). The two existing
  guides (`azure-hns-setup.md`, `sftp.md`) are the proof-of-value pattern.

  **Authoring contract (binding — see research § 2.2):** every guide
  under this initiative must be self-validated (maintainer-walked
  end-to-end against a real target), practicable (copy-pasteable steps),
  proven (dogfood trace or artifact in the PR), down to the point
  (recipe + outcome + caveat, no marketing), and link only reliable
  external references (vendor docs, RFCs, library docs — not Stack
  Overflow, Reddit, blogs, or GitHub-issue threads). Candidates that
  cannot meet the contract are deferred or scope-reduced, never
  weakened to fit.

  **Tier-1 standalone guides (per-guide PR + dedicated backlog ID when
  each is picked up):**
  1. S3-compatible providers cookbook — greenlit; AWS S3 + MinIO + R2 + B2 tested scope
  2. Large-object & streaming tuning — **split-ship**: SFTP half greenlit; S3 5 GB cliff deferred until AWS dogfood budget
  3. Local-dev emulators — greenlit; already dogfooded via CI
  4. SFTP reliability — greenlit
  5. Azure keyless auth & private endpoints — **conditional** on Azure subscription with elevated RBAC + vNet rights
  6. Credential & secret rotation — greenlit per-backend; Azure half tied to #5
  7. SQLite operational notes — greenlit; sidebar in `sql-blob.md`

  **Tier-2 sidebars** for `s3.md`, `sftp.md`, `azure.md`,
  `azure-hns-setup.md` — see research doc § 4. Fold into adjacent
  Tier-1 PRs where scope overlaps.

  **Out of scope (Tier-3):** AWS root-email governance, MinIO operator
  UX, `s3fs-fuse` FUSE-only concerns, generic DB pool tuning,
  hypothetical Azure-Blob-like self-hosts. Redirect to vendor docs.

  **Three code-side flags surfaced** (NOT guide work) — see research doc
  § 6: `s3fs` typed-error mapping fidelity; `S3Backend`
  `use_listings_cache` default; third S3 lane (`s3-boto3` direct)
  viability. Tracked as **ID-200 / ID-201 / ID-202** — all complete;
  see [BACKLOG-DONE.md](BACKLOG-DONE.md) (ID-201's disposition shipped
  as BK-257).

  **Sequencing (dogfood-cost ordered, see research § 7):**
  Phase 1 (zero new setup) = §3.3 + §3.7 + §3.4;
  Phase 2 (free-tier accounts) = §3.1 + §3.6 non-Azure halves + §3.2 SFTP half;
  Phase 3 (budgeted dogfood — gated on the access decision in research § 8 Q5) = §3.2 S3 half + §3.5 + §3.6 Azure half;
  Tier-2 sidebars mop up alongside Phase 1/2.

  Effort `L` reflects the parent scope; each individual guide is M-sized.

- [ ] **ID-125 — Update medallion showcase to Dagster v2 resource pattern**
  spec: — · effort: S · audience: user.api
  Replace `dagster_io_manager(store)` calls in `examples/medallion_dagster/`
  with `RemoteStoreIOManager`. Demonstrates the config-driven pattern.
  Examples get copied verbatim, so a stale one teaches a superseded pattern
  from a first-contact surface.

- [ ] **BK-327 — Gate dual-doc nav reachability and index listing**
  spec: — · effort: S · audience: contributor.tooling
  A `<!-- doc: dual dest=explanation/design/*.md -->` marker publishes a page that
  neither the docs-site nav nor the section index page lists, and nothing catches
  either omission — so a published page a user cannot navigate to is a page they
  never read. `mkdocs.yml` sets only `validation: links: not_found: warn`, so
  `nav.omitted_files` stays at its INFO default and `--strict` cannot promote it;
  `scripts/docs/nav.py` builds `SUMMARY.md` *from* `_nav.yml` and never diffs it
  against the pages `gen_pages.py` emitted; the `_index.tmpl` Documents list is
  hand-written and unchecked. So `hatch run docs-gate` goes green on a page that is
  unreachable, unlisted, or both. Each surface had a live instance repaired by hand
  in PR #938: `drift-rules` was absent from both, `ci-operations` was in `_nav.yml`
  and absent from `_index.tmpl`.
  Fix shape: a G-08 in `scripts/check_docs_framework.py` differencing emitted dual
  `dest` paths against both `_nav.yml` and the `_index.tmpl` Documents list;
  raising `nav.omitted_files` to WARNING covers the nav half only.
  An unstated bound on `docs-gate` being trusted past its range
  ([`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)).

- [ ] **BK-332 — Schedule the custom-backend rehearsal**
  spec: — · effort: S to define, M per run · audience: contributor.process
  "Build a backend against the guide, from scratch, without help" runs today
  only as a side effect of guide PRs. Its output is a list of places the guide,
  the contract, or the conformance suite failed the builder — BK-324 and BK-325
  are one run's findings (PR #932), which is the argument for scheduling it
  rather than running it by accident.
  **Cadence:** once per minor release, or after any change to the `Backend` ABC
  or the conformance suite, whichever comes first — the two events that can
  invalidate the guide, per [`DRIFT-RULES.md` Rule 9](DRIFT-RULES.md#period).
  **Evidence level, stated because the ranking flatters it:** n = 1. The claim
  that rehearsal has the best findings-per-unit-noise rests on that single run.

---

<a id="no-workarounds"></a>
## 4. Users stop working around us

**Promise:** the library does the thing, instead of the user hand-rolling it
or paying for our shortcut.

**Closes when:** no shipped capability declaration is more pessimistic than what
the backend can actually do (ID-140, ID-217); no capability a user cannot
cheaply build themselves is left unbuilt without a recorded decision (ID-121,
ID-217); no security tradeoff is scoped wider than the backend that needs it
(ID-181); and no cost we know how to remove is left on the caller (BK-242,
BK-357).

Each item here is something a user currently works around or eats. They are
grouped because the decision in each is the same: build it, or say plainly and
permanently that we will not — which is why "declined, recorded" closes an item
here as legitimately as "built".

- [ ] **ID-217 — Async-native extension surface (owner for the deferred async `ext.*`)**
  spec: GR-003 · effort: L · audience: user.api
  `src/remote_store/aio/ext/` ships only `write.py` (`write_with_hash`); there is
  no async equivalent of `ext.glob`, `ext.observe`, `ext.otel`, or `ext.integrity`
  (audit-016 M6). A native `AsyncStore` consumer — the natural audience for an
  async-native backend such as Graph — reaches the full `ext.*` surface only by
  dropping to `AsyncBackendSyncAdapter` (ADR-0025), which forfeits the async
  streaming the backend exists to provide. GR-003 calls this out for `GLOB`
  specifically: async callers compose pattern matching over `list_files`
  themselves "until an async equivalent of `ext.glob` lands as a separate backlog
  item" — this is that item, and it owns the surface as a whole.
  **Decision pending:** build per-extension async equivalents (glob first, as the
  smallest and the one a spec promises), or formally decline the ecosystem and
  document the sync-adapter route as the supported path. Declining is a
  legitimate close; either outcome removes an open promise from a shipped spec.
  - **`ext.cache` warning on a bridged backend** (was ID-218, absorbed here).
    `CachedStore` with an unset `max_content_size` materialises whatever the
    wrapped backend yields (`ext/cache.py`). Over a sync REST backend that is
    merely inconvenient; over an async-native backend reached through
    `AsyncBackendSyncAdapter` it silently defeats the streaming the user chose
    the backend for. ADR-0025 § Risks flags this and promises the cache
    extension "should learn to warn when wrapped over a bridged backend
    (tracked separately)"; this bullet is that owner. Scope: emit a warning (or
    require an explicit `max_content_size`) when `cache()` wraps a `Store` whose
    backend is an `AsyncBackendSyncAdapter` and `max_content_size` is unset.
    It is the same root cause — extensions do not understand async backends —
    so it resolves with the decision above rather than beside it. ADR-0025's
    sentence still reads "(tracked as ID-218)" and is Accepted, so it is not
    edited; `BACKLOG-DONE.md` § Absorbed is what makes that citation resolve.

- [ ] **ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL**
  spec: SQL-BLOB-003, SQL-BLOB-020 · effort: L · audience: user.api
  The current blanket claim that `SQLBlobBackend` cannot do lazy reads is too
  strong (see spec 040 SQL-BLOB-020, `_sqlalchemy.py:47` excluding
  `Capability.LAZY_READ`), so users materialise large blobs they need not.
  Both primary dialects have a path to honest `LAZY_READ`; MySQL does not. This
  item captures the direction — **no implementation yet**.

  **SQLite (Py 3.11+):** `sqlite3.Connection.blobopen(table, col, rowid)`
  returns a seekable, chunked `Blob` handle. Reachable through SQLAlchemy via
  `sa_conn.connection.driver_connection`. Requires a `SELECT rowid FROM t
  WHERE key = :key` lookup first, and only works when the user-supplied table
  has an implicit rowid (i.e. not `WITHOUT ROWID`). Genuine streaming.

  **PostgreSQL (`bytea`, our current schema):** no native blob handle API.
  Pseudo-stream via repeated `SELECT substring(data FROM :off FOR :len) FROM
  t WHERE key = :k`. Client memory stays bounded (satisfies LAZY_READ
  semantics per spec 006 line 70-73), but each chunk is a round trip, and on
  compressed TOAST (`EXTENDED`, the default) the server must decompress per
  call. `ALTER COLUMN data SET STORAGE EXTERNAL` makes substring cheap at
  the cost of disk space — caller-controlled tradeoff.

  **PostgreSQL Large Objects (`lo_*`):** genuine streaming via
  `psycopg.connection.lobject()`, but requires an `oid` column and manual
  lifecycle (`lo_unlink` on delete/overwrite/move, otherwise we leak).
  Different storage model — belongs in a separate backend variant
  (e.g. `sql-largeobject`), not a retrofit to `SQLBlobBackend`.

  **MySQL:** no streaming story. Same `SUBSTRING()` pseudo-stream is
  possible but out of scope here (not a primary target).

  **Constraints & gotchas:**
  - `requires-python = ">=3.10"` (`pyproject.toml:11`) stays. SQLite
    `blobopen` is 3.11+ → runtime check, fall back to current eager path on
    3.10.
  - Capability becomes **per-instance, dialect-conditional** — new pattern
    in this codebase; no other backend varies capabilities at runtime.
    Consider whether `Capability` set should be computed in `__init__` and
    cached, and how `store.supports()` interacts with it.
  - Connection lifetime: streaming handle must keep the DBAPI connection
    checked out until the returned `BinaryIO.close()`. Needs a wrapper that
    owns both.
  - Custom tables (`create_table=False`): rowid may not exist; substring
    path is schema-agnostic and works as a universal fallback.

  **Ripple checks the ripple-check table does not carry.** Process steps are
  omitted per [§ Item scope](#how-this-file-works); these three are not process
  steps, and each would be missed by a reader following the table alone:
  - `FEATURES.md`'s capability matrix is the authoritative capability surface
    per [`CLAUDE.md` § Feature reference](../CLAUDE.md#feature-reference), and
    this item's whole subject is making a `Capability` declaration
    dialect-conditional — the first such declaration in the repo that is not a
    flat per-backend fact.
  - `tests/backends/sqlblob/test_config.py:148` asserts LAZY_READ is **not**
    declared, so it must split into dialect-conditional assertions rather than
    simply flip.
  - Verification shape: a large blob (e.g. 50 MiB) read in 4 KiB chunks with
    bounded RSS. Content and chunking assertions alone pass against an eager
    read, which is the same hole ID-244 records for SIO-009.

  **Open decisions for whoever picks this up:**
  1. SQLite-only first, or SQLite + PG `bytea` substring together?
  2. Declare `LAZY_READ` for PG substring path given the per-chunk
     round-trip cost, or reserve LAZY_READ for "true" lazy and add a
     separate `CHUNKED_READ` quality flag?
  3. PG Large Objects as a follow-up backend — separate idea, own ID.

  Related: ID-136 (non-lazy **write** is by-design; this item is about
  **reads** only — writes remain eager).

- [ ] **ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass**
  spec: SFTP-007 · effort: M · audience: user.api
  `SFTPUtils.enable_ssh_rsa_compat()` mutates paramiko's class attributes
  so every `Transport` instance in the process accepts SHA-1 host keys
  thereafter. For single-server use cases this is fine and documented as
  a security tradeoff. For processes that talk to a mix of modern and
  legacy SFTP backends (e.g. a Dagster job, a multi-tenant pipeline),
  the shim leaks SHA-1 acceptance into every other transport, so one legacy
  server weakens every other connection in the process.
  Sketch: `BackendConfig(type="sftp", options={..., "allow_legacy_ssh_rsa": True})`
  constructs a `Transport` subclass whose instance-level `_preferred_keys`
  / `_preferred_pubkeys` include `ssh-rsa`, leaving `paramiko.Transport`
  class attrs untouched. `Transport._key_info` and `RSAKey.HASHES` are
  read at class scope so they still need a module-level patch — but
  those are algorithm-name → impl lookup tables, not security policy.

- [ ] **BK-242 — Flat-NS file-ancestor pre-check perf (SQLBlob IN-list, memoisation)**
  spec: — · effort: S · audience: user.api, library.maintainer
  Two perf optimisations the ID-211 disposition (b) opt-in didn't ship:
  - **SQLBlob `WHERE key IN (ancestors)`**: today `_head_one` issues one
    `SELECT 1` per ancestor — N round trips for a depth-N path. The
    research note (`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md`
    § 5.4) already flagged this; a single `SELECT key FROM table WHERE
    key IN (:ancestors)` collapses the walk to one RTT. On in-memory
    SQLite the win is sub-ms; on PostgreSQL/MySQL over the network at
    depth 6 it is 6 RTTs → 1 RTT (~10-50 ms each).
  - **`head_one` memoisation**: bulk-write workloads (`a/b/c/file-{i}.bin`
    for i in 1..N) re-HEAD the same `a`, `a/b`, `a/b/c` ancestors N
    times. A bounded per-instance `TTLCache(maxsize=…, ttl=…)` on the
    closure collapses O(N×D) HEADs to ~O(D) per distinct prefix without
    changing the contract (the TTL accepts staleness within its window).
    Applies to S3, S3PyArrow, Azure non-HNS, and SQLBlob.
  Both ship behind the existing `reject_write_under_file_ancestor=True`
  opt-in only, so there is no contract risk. Includes refreshing `§ 4` /
  `§ 5.4` in the research note with measured before/after numbers. Touches
  `src/remote_store/backends/_flat_ns.py`,
  `src/remote_store/backends/_sqlalchemy.py`,
  `src/remote_store/backends/_s3.py`,
  `src/remote_store/backends/_s3_pyarrow.py`,
  `src/remote_store/backends/_azure.py`,
  `src/remote_store/aio/backends/_azure.py`.

- [ ] **ID-121 — CompositeStore (research complete)**
  spec: — · effort: L · audience: user.api
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only. The one genuinely new
  user-facing capability in this file, and one a user cannot cheaply build
  themselves.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120) — **satisfied**:
    `Store.resolve()` ships and returns a `ResolutionPlan` (see BACKLOG-DONE.md).
    Remaining: at least two working backends to be useful; pairs well with
    ID-119 (landed) — so both conditions are already met.
  - Next: design as a separate spec — backend-agnostic, useful independently.
  - **Cache-key derivation from `ResolutionPlan`** (was ID-123, absorbed here).
    `ext.cache` should derive cache keys from `ResolutionPlan` fields instead of
    ad-hoc `(operation, path)` tuples (RES-100, proposed in
    [043](specs/043-resolution-plan.md)). Single-backend cache keys are already
    correct *for the default per-store cache*, so this is only valuable once
    composition exists. **The one case that was reachable today is now
    BUG-251** in section 2: it reproduced, so it is a defect rather than a
    motivating example, and it is filed where declining CompositeStore cannot
    retire it. Keep it in view when designing here — identity-derived keys are
    the wide fix for it, and this is where that scheme gets decided.

- [ ] **BK-356 — `io_timeout` should default to a real bound, not `None`**
  spec: SFTP-030, SFTP-005 · effort: S · audience: user.api
  BK-354 shipped `io_timeout` defaulting to `None`, so the stall it exists to
  bound is still unbounded unless a caller opts in. The default was chosen for
  compatibility and the reporter's objection to it was recorded rather than
  answered (issue #970: "'no bound at all' is a surprising default given
  `_is_connection_dead` already assumes one"). It stands unrebutted.
  **Why the default is wrong on the library's own terms, not just on taste.**
  `ReadOnlyHttpBackend` already defaults `timeout=30.0`, which reaches reads, so SFTP
  is the outlier rather than the pioneer — a user meets a bounded read on HTTP
  and an unbounded one on SFTP with no principle separating them. And the SFTP
  recovery path (`_is_connection_dead` → `_map_exception` → cleared client) was
  written presuming a bound exists; shipping the machinery without its trigger
  is an internal contradiction that BK-354 documented instead of closing.
  **Decided: `120.0`.** It is the value the SFTP guide and troubleshooting page
  already use in their worked examples, so the docs and the default stop
  disagreeing. Against the longest transfer #970 reports (2.0 GiB, ~70 min) a
  120 s silence bound is 2.8% of runtime — a stall is caught inside two minutes
  while leaving room for a server that legitimately goes quiet, e.g. an
  antivirus or dedup appliance scanning a large file on `open()`.
  The asymmetry is what picks the value: too high costs detection latency,
  which is cheap because the bound is on silence *between* bytes and a slow
  link is unaffected at any value; too low converts a healthy-but-quiet server
  into intermittent `BackendUnavailable`, which reads as network flakiness and
  is harder to diagnose than the hang it replaces.
  **Breaking, and shipped as such.** Pre-1.0 (`0.30.0`, Development Status ::
  4 - Beta) with an established `docs-src/reference/migration.md` — v0.29.0
  made Azure's `hns` a *required* argument, a harder break than changing a
  default that keeps an opt-out. The migration entry must lead with the opt-out
  (`io_timeout=None` restores the old behaviour), because the reader who needs
  it is exactly the one with a legitimately slow or quiet server. Note `0` is
  not the opt-out: it raises `ValueError` (SFTP-005), since paramiko reads it
  as non-blocking.
  **No longer blocked.** BK-355 landed first, so releasing a stalled stream
  costs one bound rather than two and the flip does not ship a doubling with it.
  One doubling it does still ship is BK-357's `SEEK_END` case, which BK-355's
  guard cannot reach; weigh that when setting the default, since a real bound is
  what makes it cost anything.

- [ ] **BK-357 — A `SEEK_END` seek hides its own stall, so the futile-close guard cannot arm**
  spec: SFTP-030, SIO-010 · effort: M · audience: user.api
  BK-355's guard learns a connection is dead from an exception travelling through
  `_ErrorMappingStream`'s mapping paths. `SFTPFile.seek(offset, SEEK_END)` calls
  `_get_size()`, whose body is `try: return self.stat().st_size` under a bare
  `except: return 0`. On a stalled channel that `stat` blocks for `io_timeout`
  and is then swallowed, so the seek returns a bogus size of `0` and raises
  nothing: the guard stays unarmed and the close pays the bound a second time.
  Measured at a 2 s bound: 4.00 s, against 2.00 s for the read path BK-355 fixed
  (`test_seek_to_end_on_a_stalled_channel_still_costs_two_bounds`).
  **Two defects, and the second is the worse one.** The doubled wait is the
  visible cost, but the seek also *succeeds* with a size of `0` on a dead
  channel, so a caller sizing a file by seeking to its end reads zero and cannot
  tell that from an empty file. That is a wrong answer, not just a slow one, and
  it is the half that argues for fixing this rather than living with it.
  **Fix surface:** the wrapper issuing its own size probe for `SEEK_END` instead
  of delegating to paramiko's, so the failure surfaces where the mapper can see
  it. That is a change to the seek path of every backend `_ErrorMappingStream`
  serves, not just SFTP's, which is why it is `M` rather than `S` and why it was
  filed rather than widened into BK-355.
  **Open question:** whether the probe belongs in the wrapper (one place, but it
  round-trips on behalf of backends whose `seek` currently does not) or behind
  the same opt-in predicate mechanism BK-355 added, which keeps the cost with the
  backend that needs it. Undecided.
  Found by BK-355's round-2 measuring review, which ran the seek path rather than
  reading it — the reading rounds had all concluded the stream surface was bounded.

---

<a id="no-release-surprises"></a>
## 5. A release cannot ship a surprise

**Promise:** nothing reaches a user that we did not test, publish, or watch.

**Closes when:** every checker a diff can invalidate is reachable from a gate
that diff actually triggers (BK-333); every extra's drift smoke exercises the
packages it pins (BUG-250) and catches the drift that is visible only to a type
checker (ID-250); **every install channel we intend to offer is
published and working** (ID-018); and every upstream that can break us on its
own schedule has a standing watch (ID-229, ID-225).

Clause 3 is stated as *intend to offer* rather than *already advertised*
deliberately: ID-018 creates a channel rather than repairing a dead one, so the
narrower wording would be vacuously true while the item stays open.
**This section's closure is externally gated.** ID-018 is `[~]` and blocked on a
conda-forge reviewer, so no work in this repo can close section 5 — a real
property of the section, not a defect in it, and stated so nobody reads the
open item as neglect.

- [ ] **ID-250 — The drift smoke never type-checks, so a signature-only narrowing reaches PRs as a red gate**
  spec: — · effort: M · audience: infra.ci
  `.github/workflows/drift-guard.yml` resolves every extra with
  `--upgrade --pre`, diffs against the committed baselines and runs the smoke —
  which is a pytest target or an `--import-only` module import, per
  `scripts/drift_smoke_map.py`. It never runs `mypy`: `rg 'mypy'
  .github/workflows/drift-guard.yml` returns nothing. So a dependency change that
  is invisible at runtime and visible only to a type checker passes the smoke,
  the rolling `[drift-guard]` issue reports the version bump with a green
  verdict, and the first person to learn that it breaks us is whoever opens the
  next PR.
  **Measured, in BUG-258.** Dagster narrowed
  `ComputeLogManager.get_log_keys_for_log_key_prefix` from
  `Sequence[Sequence[str]]` to `Sequence[list[str]]`. Nothing raised, nothing
  failed to import, no test changed behaviour — and every open PR's
  `typecheck (3.13)` job went red against code no commit had touched. The version
  drift itself was inside drift-guard's remit; the consequence was outside its
  instrument.
  This is the sibling of BUG-250 one layer up: that item is about the smoke
  reaching the *packages* an extra pins, this one about the smoke reaching the
  *properties* of them that we actually depend on. Both are the same failure —
  a green verdict from an instrument that never looked.
  Fix shape is open, and the cheap option may not be the right one. Adding
  `mypy` to the smoke leg is small but types the whole tree against one drifted
  extra, so a failure will not say which; typing only the extra's own module is
  narrower but needs a map from extra to source path, which is
  `drift_smoke_map.py`'s existing shape. Either way the verdict must be
  *advisory* like the rest of drift-guard — the point is a triaged rolling-issue
  row before the PR, not a second gate that blocks one.
  **Not** about pinning `dagster`, which BUG-258 considered and rejected:
  `infra/drift-locks/dagster.txt` already freezes the extra, and the annotation
  fix it shipped is valid against both supertype versions, so no upper bound was
  needed.

- [ ] **BUG-250 — `[graph]`'s drift smoke reaches one of the extra's four declared dependencies**
  spec: — · effort: S · audience: infra.ci
  `scripts/drift_smoke_map.py:79` routes `graph` to
  `["--import-only", "remote_store.aio.backends._graph.http"]`. That module's only
  third-party import is `httpx`; `_graph/auth.py` imports `msal`, `msal-extensions`
  and `platformdirs` lazily inside the methods that need them (`auth.py:173`,
  `auth.py:194`). Reproduction: import the module and diff `sys.modules` — `httpx`
  loads, `cffi` / `cryptography` / `platformdirs` / `msal` / `msal_extensions` do not.
  So `check-graph` can go green while every drifted package in
  `infra/drift-locks/graph.txt` is unexercised, and a `cryptography` or `msal` major
  rides that verdict into a refresh and into a user's install. Hit in the
  2026-08-10 firing (trace finding #32): all three drifted packages were outside
  the smoke's reach, and the accepted `cryptography` 49→50 major turned out to be
  covered only incidentally, by `[azure]` and `[sftp]` smoking identical pins.
  The import-only shape is deliberate (BUG-225) — it catches a graph-hostile `httpx`
  without needing msal or a network. A fix must widen reach without regressing that:
  import the lazy call sites behind a no-network path, or add a cassette-backed target.
  Worth auditing the other `--import-only` entry (`otel`) for the same shape.

- [ ] **BK-333 — Gate routing: checkers unreachable for the diffs that invalidate them**
  spec: — · effort: S · audience: contributor.tooling, infra.ci
  Two classifiers decide which gates a diff runs, they disagree in both
  directions, and between them three checkers are unreachable for exactly the
  change that breaks them. `CODE_PAT` does not match `^sdd/`, so CI's `lint` job
  (and `preflight` inside it) is skipped; `FORMAL_PAT` is `^sdd/(formal|specs)/`
  **minus `sdd/formal/tla/`**, so the second-wiring escape hatch used for
  `check_spec_marks`, `check_formal_trace`, `check_capability_parity` and
  `check_dafny_twin_parity` does not reach these three; and `docs-gate` invokes
  none of them:
  - `gen_adr_digest.py --check` (in `preflight`) reads `sdd/adrs/`. Adding an ADR,
    accepting a draft or recording a supersession is exactly what bumps the
    **committed generated** `sdd/adrs/DIGEST.md` and can break supersession-graph
    consistency, so staleness ships.
  - `check_tla_no_emdash.py` reads `sdd/formal/tla/**/*.tla` — the one subtree
    `FORMAL_PAT` deliberately excludes, so a TLA-only change skips the check
    written for TLA files.
  - `check_ci_inventory.py` compares `.github/workflows/` against
    `sdd/CI-OPERATIONS.md`. The workflow side is covered (`CODE_PAT` matches
    `^\.github/workflows/`); editing the handbook alone is not.
  **The ADR digest half is measured, twice** (was BK-347, absorbed here). A
  standalone `gen-adr-digest-check` alias exists in `pyproject.toml` and
  **nothing composes it**, so the checker is one alias away from any gate that
  wants it. Commit `dc10a23` (PR #956): `gate`, `docs` and `setup` ran, `lint`
  skipped. Commit `26cf75b` (PR #958) adds an ADR *and* touches
  `.claude/skills/`, `CLAUDE.md` and `sdd/traces/` — not an ADR-only diff by any
  reading — and `lint` still skipped, with every test lane skipped alongside it.
  So the CI trigger is not how narrow the diff is; it is that **no path in it
  matches `CODE_PAT`**, which is true of most process deliveries. The local
  classifier misses a different set: an ADR plus a `.claude/hooks/` edit is
  outside `CODE_PAT` yet locally runs `all` → `preflight` → the check, while an
  ADR plus a `.github/workflows/` edit is inside `CODE_PAT` yet routes to
  `lint` + `docs-gate`, which compose it nowhere. **Scope any fix to both
  classifiers, not to one name.**
  **Consequence:** a hand-edited or stale `DIGEST.md` ships on the author's care
  alone, and the `STALE:` failure lands on the *next* PR that happens to touch
  code — the wrong PR to pay for it, and one whose author did not cause it.
  **Two claims to fix or qualify, not just the routing.** The
  [PR validation gates](CLAUDE-REFERENCE.md#pr-validation-gates) section says
  "the two paths stay equivalent on docs coverage despite composing different
  targets", which is false for this checker; and the Detailed checklist's **ADR**
  row names `preflight` as the gate, which is accurate and is precisely why the
  routing is wrong.
  Fix shape: add each checker to `docs-gate` beside the two BK-329 wired,
  following the precedent `check_ripple_parity` documents, and widen CI's path
  filter to treat `sdd/adrs/**` as lint-triggering. Filed rather than fixed in
  BK-329 because that PR touched no ADR, no TLA module and not the handbook.

- [~] **ID-018 — conda-forge publishing**
  spec: — · effort: — · audience: library.maintainer
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

- [ ] **ID-229 — Evaluate porting to httpx 1.0 (lift the `<1.0` cap)**
  spec: GR-033 · effort: M · audience: user.api
  BUG-225 capped the `graph` and `httpx` extras at `httpx>=0.24.0,<1.0`
  after the drift guard's `--pre` re-resolution pulled `httpx==1.0.dev3`
  and the async graph backend failed to import. That pre-release turned
  out to be a **wholesale API rewrite**, not the exception-hierarchy
  reorg the BUG-225 diagnosis first assumed: `1.0.dev3` drops
  `httpx.AsyncClient`, `httpx.TransportError`, `httpx.DecodingError`,
  `httpx.HTTPStatusError`, `Timeout`, `Limits` — essentially the entire
  client surface the graph backend (`AsyncClient` in ~30 sites) and the
  `[httpx]` HTTP adapter are built on. Coding around a single missing
  symbol would only convert an honest import failure into a falsely-green
  import that then explodes at runtime on `httpx.AsyncClient(...)`, so the
  cap is the honest interim posture. The cap constrains every dependency
  set a user resolves, so it needs a watch rather than silent drift.
  **Upstream context:** the cap matches the maintainers' own guidance.
  httpx 0.28.x is still a pre-1.0 line; the "1.0.dev" / "httpx2" threads
  are about the project's next major API *direction*, not a released
  stable 1.x series. In the late-2024 V1 discussion the maintainers said
  httpx was not yet at a 1.0 SemVer release and recommended **pinning to
  0.28 while reviewing deprecations** — which is exactly what `<1.0` does.
  Ref: [encode/httpx#3344](https://github.com/encode/httpx/discussions/3344).
  **When picked up:** real httpx 1.0 stable is out and pins install
  cleanly against it. Diff the actual 1.0 public API against 0.28
  (`AsyncClient`, `Response`, `Timeout`/`Limits`, the transport-error and
  decoding-error bases, `respx` compatibility); decide port-vs-hold; if
  porting, update `_graph/*.py` + the `[httpx]` backend, raise the cap,
  and refresh the `graph` / `httpx` drift baselines.
  **Why ID, not BK:** unevaluated migration against an upstream whose 1.0
  shape is not yet stable. Mirrors the revisit discipline of ID-150.

- [ ] **ID-225 — Evaluate migrating the docs stack from Material for MkDocs to Zensical**
  spec: — · effort: L · audience: user.site, library.maintainer, contributor.tooling
  Our docs foundation is entering maintenance mode as its authors converge on a
  successor. [Material for MkDocs is feature-frozen](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
  (critical bug/security fixes for ~12 months, no new features), MkDocs 1.x is
  itself being forked (a `properdocs` MkDocs-1.x continuation now surfaces as a
  transitive docs dep, and a build-time banner warns MkDocs 2.0 will break all
  plugins/themes), and `mkdocs-llmstxt` (adopted in ID-220) is in maintenance
  mode for the same reason. The whole ecosystem is pointing at
  [**Zensical**](https://github.com/zensical/zensical) — a new MIT static site
  generator (Rust core, reads `mkdocs.yml` natively, with a migration path) built
  by the Material team. Crucially, `mkdocstrings`' author is rebuilding
  API-reference-from-docstrings *inside* Zensical — the exact capability our docs
  depend on `mkdocstrings` for.
  **Not prioritized:** Zensical is pre-1.0 and does **not** yet ship the
  API-reference feature we require, so "not yet — revisit when Zensical reaches
  API-reference parity" is a legitimate outcome. Kept visible here as the
  **sunset trigger for the interim `mkdocs-llmstxt` adoption (ID-220)**, which is
  recorded nowhere else: when the migration lands, the HTML→Markdown plugin is a
  prime candidate for replacement by a native feature.
  **Scope when picked up:** trial `zensical build` against our `mkdocs.yml`;
  confirm parity for the pieces we rely on (gen-files pages, mkdocstrings API
  reference, literate-nav order, BK-171 link rewrites, mike/RTD versioning); and
  fold in native `llms.txt` / `llms-full.txt` generation if Zensical ships it.
  Background: [research](research/research-llms-full-txt-tooling.md).

---

<a id="repo-does-not-mislead"></a>
## 6. The repo does not mislead the next person

**Promise:** the artifacts maintainers coordinate through — this file, the
ripple-check, the revisit pins, the generated inventories — say what is
actually true.

**Closes when:** the backlog files are structurally linted (ID-235); the
ripple-check's six measured blind spots are answered (BK-346); the
hand-maintained inventories ID-245 names are generated — four bullets, of which
the checker inventory has shipped; `check_formal_trace` proves
assertion rather than citation (ID-207); and both open revisit pins have fired
and named successors (ID-150, ID-249).
**Bounded to those five deliberately.** "No artifact asserts what no mechanism
can check" is the promise and cannot be a closing condition: this section's own
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
    **Add the retirement sections to the structural rules**: every entry under
    `BACKLOG-DONE.md` § Absorbed names a host that exists in `BACKLOG.md`, and
    every ID retired by either route appears exactly once across both files.
    That is what keeps the ID space safe by construction rather than by whoever
    last remembered to add an entry.
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

- [ ] **BK-346 — The ripple-check table answers questions adjacent to the ones asked**
  spec: — · effort: S/M · audience: contributor.process
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
  the same way — and instance 5's choice sets the effort for the group, which is
  why `effort:` is a range.
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
  spec: — · effort: S/M · audience: contributor.tooling
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
    and BUG-254 — in **four incompatible frames**: bullets, backend classes,
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

- [ ] **ID-249 — Trace-outcome report revisit at the next release**
  spec: — · effort: S · audience: contributor.process
  First revisit ticket for the release-anchored trigger ID-238 shipped. Per
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
  **Baseline to difference against**, measured at `4076ed7`: 270 traces, 207
  negative tags, `sdd/BACKLOG.md` top-ranked at 22 over 236 reads (9.3%).
  **Exit criteria:** decision logged here, then the successor ticket opened and
  its ID named in this item's close note.
