# Development Backlog
<!-- doc: repo-only -->

Active work items. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

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
slow deletion that charged review attention on every pass, and items that
belonged in it were removed rather than migrated.

**Ordering.** Sections are in priority order: 1–3 pay users, 4–6 pay
maintainers. Within a section the order is execution sequence, so a dependency
never sits below the thing that needs it. No section declares its own
exception.

**Granularity.** Work that shares a fix surface is one item with sub-bullets. A
sub-bullet is not an ID and does not become one. A section that outgrows
itself splits into two promises, never into loose items.

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
- Decided against → delete from here, and fix every artifact that asserts the
  item exists. A removed item leaves no tracker behind, so an inbound citation
  becomes a claim about nothing.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. Monotonic, not reset per release. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |
| `AF-NNN` | Audit finding (retired — use `BUG` or `BK` for new items). |

**Assigning a new ID:** check `sdd/backlogid.json` (max per prefix from BACKLOG-DONE.md)
and the highest ID already in this file, then take the next integer. Run
`hatch run gen-backlogid` after moving items to BACKLOG-DONE.md to keep the JSON current.
`hatch run lint` flags drift and collisions.

**Retired IDs — never reassign:** `BK-334`, `BK-335`, `BK-337`, `BK-347`,
`BK-349`, `BK-350`, `BK-139d`, `ID-066`, `ID-067`, `ID-105`, `ID-114`,
`ID-118b`, `ID-123`, `ID-197`, `ID-205`, `ID-215`, `ID-218`, `ID-236`,
`ID-237`, `ID-239`, `ID-240`, `ID-246`, `ID-248`. Nine were absorbed into a
surviving item and fourteen were removed as unearned; traces and
`BACKLOG-DONE.md` still cite them as historical fact.
**`gen_backlogid.py` cannot see this list** — it derives each prefix's maximum
from the two backlog files, so removing the highest-numbered item lowers the
next "safe" number and offers a burned one. `BK-349` is offered today and must
not be taken. Teaching the generator to read this list is part of ID-235.

---

## Release Blockers

*(none)*

---

## 1. Failures are predictable

**Promise:** a caller catches one exception type, and an absent or denied
store answers the same way on every backend.

**Closes when:** BE-004, BE-005 and BE-021 hold on every registered backend
against a container that does not exist, and a newly registered backend cannot
pass CI without meeting them.

Four adapters currently disagree with the contract and with each other, so the
group ships together or not at all: fixing four backends and leaving the fifth
leaves portable error handling impossible, which is the whole promise. BUG-248
comes first because it decides what two of the others owe.

- [ ] **BUG-248 — BE-021's absent-container rule and GR-031's drive-identity escalation contradict each other**
  spec: BE-021, GR-031 · effort: M · audience: user.api
  Two clauses, both deliberate, giving opposite answers for the same call. BE-021
  says `delete(missing_ok=True)` and `delete_folder(missing_ok=True)` MUST return
  cleanly when the container is absent, binding **every** backend with no
  carve-out. GR-031 says a `404 resourceNotFound` — Graph's drive-identity code,
  honoured at any URL scope — maps to `BackendUnavailable` for every
  error-raising operation, because a deleted drive is a backend identity failure
  rather than a per-item condition. `GraphBackend`'s drive is a container, so the
  two clauses meet, and GR-031 wins today:
  | Graph `error.code` | `delete(missing_ok=True)` | `delete_folder(missing_ok=True)` | `exists` / `is_file` / `is_folder` |
  | --- | --- | --- | --- |
  | `itemNotFound` | tolerated | tolerated | `False` |
  | `resourceNotFound` | raises `BackendUnavailable` | raises `BackendUnavailable` | `False` |
  Measured on respx stubs and pinned in
  `tests/backends/graph/aio/test_absent_drive.py`. The probe row is not a
  divergence: GR-031's probe scope flattens every `404`, so BE-004/BE-005 hold.
  Only the two tolerant deletes disagree.
  Neither implementation is buggy — each matches its own spec — so this needs
  adjudicating before anything is coded. The case for GR-031: a drive that has
  been deleted or misconfigured is not the same event as an empty bucket, and
  silently returning from a delete against a store the caller cannot reach hides a
  configuration error behind a success. The case for BE-021: it binds every
  backend precisely because the earlier per-backend answers disagreed, and a
  container is a container.
  Note the escalation is defensive rather than observed: GR-031's own verification
  note records that live consumer OneDrive returned `404 itemNotFound` for a
  nonexistent drive on both URL forms, so the divergent row may be unreachable on
  that tier and reachable only on SharePoint-backed drives, which the live tier
  does not cover. Weigh how much a rule is worth when nobody has seen it fire.
  Whichever clause loses must say so explicitly — an amended cross-reference in
  both specs, not silence in one.

- [ ] **BUG-246 — An absent container raises where the contract says `False`, `NotFound`, or an empty listing**
  spec: BE-004, BE-005, BE-021 · effort: M · audience: user.api
  BE-004 and BE-005 say these never raise, and BE-021 repeats it: the three
  return `False` on any traversal error rather than raising. Against a container
  that does not exist, four backends raise instead. Measured on the
  `pytest-httpserver` stubs BUG-243 added (real `NoSuchBucket` /
  `ContainerNotFound` 404s, Stage 1, no Docker) and on a dropped SQLite table:
  | Backend | `exists(file)` | `is_file(file)` | `is_folder(folder)` |
  | --- | --- | --- | --- |
  | S3, S3-PyArrow | `False` | `False` | `False` |
  | S3-Boto3 | raises `NotFound` | `False` | raises `NotFound` |
  | Azure non-HNS (sync and async) | raises `NotFound` | `False` | raises `NotFound` |
  | SQLBlob | raises `BackendUnavailable` | raises `BackendUnavailable` | raises `BackendUnavailable` |
  `AzureBackend` and `AsyncAzureBackend` share a row because they answer
  identically and need the same fix.
  Two different root causes, so budget for two fixes. On S3-Boto3 and Azure the
  `is_file` column shows it is local: the HEAD-backed probe already absorbs the
  404 and only the prefix-listing-backed ones do not. On SQLBlob all three run
  their `SELECT` inside a bare `_map_errors`, so the driver's complaint maps
  straight through — the same gap BUG-243 closed for the two deletes only, and
  the fix shape is the one it used (`_absent_table_is_absent_path`, minus the
  `missing_ok` branch, answering `False` instead).
  `AzureBackend.exists`'s own docstring already says it never raises, so the
  code contradicts its documentation.
  **On SQLBlob the three probes are a third of it.** BE-021's divergence list
  says "every operation except the two deletes", and that is measured, not
  inferred — against a dropped SQLite table every one of these raises
  `BackendUnavailable`:
  | Operation | Canonical row (BE-021) | Measured |
  | --- | --- | --- |
  | `read`, `read_bytes`, `get_file_info`, `get_folder_info` | `NotFound` | `BackendUnavailable` |
  | `move` / `copy` source | `NotFound` | `BackendUnavailable` |
  | `list_files`, `list_folders` | empty listing | `BackendUnavailable` |
  | `exists`, `is_file`, `is_folder` | `False` | `BackendUnavailable` |
  | `write` | — | `BackendUnavailable` |
  Only `write` is arguably right: no clause says what a write owes against an
  absent container, so leaving it as a backend-identity failure is defensible
  and this item does not propose changing it. The other eleven owe a different
  answer, and the fix is one shape applied at three call sites, not eleven —
  they all run their statement inside a bare `_map_errors`.
  **The same split reaches a disposed in-memory engine.** Disposing one destroys
  the database rather than releasing a connection, so the table is genuinely
  absent and the two deletes return while everything else raises. Fixing the
  rows above fixes this with them; there is nothing separate to decide.
  Pre-existing — BUG-243 neither introduced nor touched it, having decided only
  what `missing_ok` owes on the two deletes.

- [ ] **BUG-249 — Three `S3Boto3Backend` listings leak a raw `botocore.ClientError`**
  spec: BE-021 · effort: S · audience: user.api
  BE-021's first invariant: "Backend-native exceptions never leak. All
  exceptions are mapped to `remote_store` error types." `list_files`,
  `list_folders` and `iter_children` are the only methods on the class that call
  the wire without `_boto_errors` around it — every other method wraps, at
  fourteen sites. So the paginator's exception reaches the caller untouched.
  Measured against the missing-bucket stub, and against a 403 stub to show the
  cause is local rather than contractual:
  | Backend | `list_files` on an absent bucket | on a denied bucket |
  | --- | --- | --- |
  | S3, S3-PyArrow | empty listing | `PermissionDenied` |
  | S3-Boto3 | raises `botocore.exceptions.ClientError` | raises `botocore` `AccessDenied` |
  Two backends answer correctly against the identical wire response, so this is
  an omission in one adapter, not an unstated contract question. The escaping
  type is the worst part: a caller catching `except RemoteStoreError` catches
  every backend but this one, and `ClientError` comes from a library they may
  never have imported.
  Pinned by `tests/backends/s3/test_denied_probe.py::TestS3Boto3ListingsLeakTheirNativeError`,
  which asserts both that the error *is* a `ClientError` and that it is *not* a
  `RemoteStoreError` — so the fix breaks the cell rather than making it vacuous.
  The fix is one `with self._boto_errors(path):` per method, but note all three
  are generators: the wrapper must be inside the generator body, not around the
  call that returns it, or it will not be entered until the first `next()`.
  **Co-ship with BUG-246's S3-Boto3 row** — same adapter, same idiom, and
  BUG-246's diagnosis puts its S3-Boto3 failures on the prefix-listing paths
  this item wraps.

- [ ] **BUG-247 — `LocalBackend` reports a deleted root as "Path escapes root directory"**
  spec: BE-004, BE-012, BE-013, BE-021 · effort: S · audience: user.api
  Delete a `LocalBackend`'s root directory out from under it and **every** operation
  raises `InvalidPath("Path escapes root directory")` — including
  `delete(missing_ok=True)` and `delete_folder(missing_ok=True)`, which BE-021's
  absent-container rule requires to return cleanly, and `exists()`, which BE-004
  forbids from raising at all.
  Nothing is escaping. `_within_root` walks up from the target to the deepest
  *lexically existing* ancestor for its symlink-escape check; once the root is
  gone that walk climbs past the root, so
  `anchor.resolve().relative_to(self._root)` raises `ValueError` and containment
  is reported as an escape. `InvalidPath` is the worst of the plausible answers:
  it tells the caller their path is malformed when the path is fine and the store
  is simply absent.
  Reproduction and the current behaviour are pinned in
  `tests/backends/local/test_absent_root.py` — the contract cells are
  `xfail(strict=True)`, so fixing this flips them to XPASS and fails the suite
  until the markers come off.
  **Care required:** `_within_root` is the symlink-escape guard, so a fix must
  distinguish "anchor escaped because the root is gone" from "anchor escaped
  because the path really does point outside" without weakening the second. A
  root-existence check before the walk is the obvious shape, at the cost of a
  `stat` per call — measure before adopting it.
  Local is the most-used backend, so this reaches more callers than any other
  item in this section.

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

- [ ] **BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt**
  spec: BE-021 · effort: M · audience: infra.test
  The rule binds every backend that can delete and whose container can be
  absent, and it is verified by six hand-written per-backend suites
  (`tests/backends/{s3,azure,azure/aio,sqlblob,sftp,local,graph/aio}/`).
  `tests/backends/conformance/` gained nothing, so a seventh such backend
  inherits no cell and passes CI without ever meeting the clause.
  This is not hypothetical. `GraphBackend` went unexamined through six review
  rounds of the change that wrote the rule (BUG-243) and turned out to
  contradict it, which is BUG-248 above. A registry-driven cell would have failed
  on the first run.
  The repo already has the shape for this: [`sdd/TESTING.md`](TESTING.md)
  Rule 13 § "Declaring an exemption" — a self-pruning exemption list where
  silence is not consent. The work is a conformance cell parametrised over the
  backend registry, plus an explicit exemption entry for the four backends BE-021
  names as out of scope (`MemoryBackend` and `AsyncMemoryBackend`, whose
  container is an in-process dict; `SQLQueryBackend` and `ReadOnlyHttpBackend`,
  which do not declare `DELETE`).
  **Depends on ID-244 for the mechanism, and on BUG-248 for the exemption list.**
  An absent container is not a state most conformance fixtures can reach: the S3
  and Azure lanes need a stub that 404s at container level (BUG-243 built those),
  SQLBlob needs a dropped table, Local needs its root deleted, and Graph needs a
  respx route. That is the same per-fixture arrangement hook ID-244 has to decide
  where to bind, so this item consumes that decision rather than making its own.
  This is the item that makes the section's promise stay true for backend seven,
  which is why it sits here and not with the coverage work.

---

## 2. Answers are correct, and the contract is proven

**Promise:** the same call returns the same right result on every backend, and
no clause of the contract ships unexercised.

**Closes when:** no two backends can legally answer one call differently, and
no contract clause is reachable only by a fixture that does not exist.

A corrected clause nobody tests is the same defect one layer up, which is why
the wrong-answer defects and the coverage holes are one promise. ID-244 leads
because it owns the seeding decision BK-345 above also consumes.

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

## 3. Users succeed without asking us

**Promise:** a user gets set up, picks the right backend, or writes their own,
without opening an issue.

**Closes when:** every published page a user decides from is true, reachable,
and walked end-to-end by a maintainer.

This is the group that converts directly into support load not arriving. The
rehearsal sits with the guides because it is the only mechanism that has ever
found their defects.

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

## 4. Users stop working around us

**Promise:** the library does the thing, instead of the user hand-rolling it
or paying for our shortcut.

**Closes when:** no shipped capability declaration is more pessimistic than
what the backend can actually do, and no documented workaround stands in for a
feature we agreed to build.

Each item here is something a user currently works around or eats. They are
grouped because the decision in each is the same: build it, or say plainly and
permanently that we will not.

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
    so it resolves with the decision above rather than beside it.

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
  - `tests/backends/sqlblob/test_config.py:148` asserts LAZY_READ is NOT
    declared — must split into dialect-conditional assertions.

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
  spec: — · effort: S · audience: infra.test, library.maintainer
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
    composition exists — with one exception that is reachable today
    (audit-016 L8): a **shared** `cache_backend=` across two top-level stores at
    different backends or drives collides on `(op, path)` and serves one store's
    bytes for another's. Not Graph-specific (same for two Local roots or S3
    buckets) and opt-in, but exactly the case identity-derived keys would close.
    **Reproduce that collision before treating it as fact** — it is an audit
    finding, and [`CLAUDE.md` principle 6](../CLAUDE.md#principles) wants it run,
    not read. If it reproduces it is a defect that should not wait for this
    item; file it as a `BUG` and fix it independently.

---

## 5. A release cannot ship a surprise

**Promise:** what we tested is what ships, and no dependency or toolchain
change reaches a user through a gate that never ran.

**Closes when:** every checker a diff can invalidate is reachable from a gate
that diff actually triggers, and every extra's drift smoke exercises the
packages it pins.

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

## 6. The repo does not mislead the next person

**Promise:** the artifacts maintainers coordinate through — this file, the
ripple-check, the revisit pins, the generated inventories — say what is
actually true.

**Closes when:** no coordination artifact asserts a fact that a mechanism
cannot check, and no figure in a durable artifact was counted by hand.

Lowest priority and deliberately capped. Design and review rules for anything
added here: [`DRIFT-RULES.md`](DRIFT-RULES.md#rules). The argument and gap
ranking behind the programme:
[research](research/research-inconsistency-detection-multi-artifact.md) § 9.

**Measured qualification on that research doc's ranking**, recorded here
because the doc is point-in-time and does not get rewritten. It designates
ID-207 (the canonical claim space) as the strategic item. ID-207 builds an
*omission detector* — research § 1 class E. BK-324's four instances were class
A/C/D: one claim restated in several homes and updated in one. So ID-207 is
**not** the item that would have caught what this programme has actually
caught. Detecting those needs semantic comparison of prose, which § 1 marks as
having no general oracle. The mechanisms that did catch them were an
author-side sibling sweep ([BK-336](BACKLOG-DONE.md)) and running the code
rather than reading the diff ([BK-344](BACKLOG-DONE.md) and
[BK-338](BACKLOG-DONE.md)) — neither in the research doc's ranking.

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
    ([DRIFT-RULES Rule 2](DRIFT-RULES.md#rules): localize, don't merely fail).
    Rule 3 makes it cheap — the claim space is *derived* from the citing
    documents. Rule 4 needs a decision this does not presuppose: when a spec
    cites an ID no backlog file carries, which side is wrong.
  **Note the wiring trap BK-333 documents:** a check reading `sdd/` must reach a
  gate an `sdd/`-only change actually runs. This item is a live instance of its
  own subject — the deletions that produced this file's current shape are
  exactly the event the second pass exists to catch.

- [ ] **BK-346 — The ripple-check table answers questions adjacent to the ones asked**
  spec: — · effort: S/M · audience: contributor.process
  One class with four measured instances, not four items. Each is a reader who
  consulted the [Pre-work index](CLAUDE-REFERENCE.md#pre-work-index), got an
  answer, and acted on it — and the answer was to a neighbouring question. Any
  row change lands in **both** presentations; `check_ripple_parity.py` enforces
  trigger-parity, so a row added to one and not the other fails `lint`.
  **The open question is the shape of the fix**, not whether there is a defect:
  N rows, N widened rows, or a note about the table's granularity. Decide once,
  across all four.
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
  4. **Adding a `hatch` script alias** (was BK-334). No trigger covers adding an
     entry to `pyproject.toml`'s `[tool.hatch.envs.default.scripts]`. That edit
     decides whether a new `scripts/*.py` is reachable by anything — whether it
     joins `lint` / `preflight` / `docs-gate` / `all`, or is deliberately left
     out. It fires on every new script in `scripts/`, of which the repo has
     dozens and every one carries an alias. BK-330 reasoned to the right answer
     only via the adjacent cross-artifact row, which now covers drift reports and
     still says nothing about a `gen_*` or a `bench-*`.
  5. **Widening an authority doc's scope** (was BK-337). There is a row for a
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
  6. **Closing a backlog item** (was ID-248). The **Backlog item touched** row
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

- [ ] **ID-245 — Derived inventories replacing hand-maintained ones**
  spec: — · effort: M · audience: infra.test, contributor.tooling
  Three generated surfaces, one shared design decision, and the same
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
  - **The characteristic-accountability record** (was ID-236, research § 9 step
    7). `check_formal_trace.py` computes a spec-coverage matrix and discards it.
    Render it at release time — every spec ID, its verification evidence (test
    marker, Dafny tag, TLA+ invariant), its status — so "what was verified, and
    by what" is answerable historically rather than only at HEAD. Its shape
    changes under ID-207, so cost is unknown until that lands.
  - **The cross-artifact checker inventory** (was ID-237, research § 9 step 8).
    The research doc's own inventory of which artifact pairs are checked was
    assembled by hand, and says of itself: "The table will drift, and nothing
    will notice." Derive it from the `check_*.py` docstrings. Two complications
    belong in the scope rather than in the implementation surprise: a substantial
    minority of gates are single-artifact rule checks whose docstrings state a
    *rule*, not a pair (assertion presence, mock discipline, forbidden RST roles,
    em dashes in TLA+), so the deliverable needs an explicit "rule check, no
    pair" classification; and the `scripts/check_*.py` glob under-reaches —
    `scripts/docs/check_links.py` is a genuine cross-artifact gate outside it.
  **The shared open question:** both complications push toward either a docstring
  convention or a curated mapping, and a curated mapping is precisely the
  parallel-artifact-that-drifts problem these exist to close. That decision is
  unmade and it is one decision, not three.

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
