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

**Promise:** a caller catches one exception type, an absent or denied store
answers the same way on every backend, and the failure they catch says which
failure it was.

**Closes when:** the root of an absent container meets BE-029 on every
backend (BUG-254); a listing does not truncate silently when its container is
deleted mid-scan (BUG-255) or when a folder vanishes part-way through a
recursive walk (BUG-257); `ping()` does not report a vanished store as healthy
(BUG-256); a constructor does not leak its driver's exception
(BUG-245); one operation does not answer by
payload size (BUG-253); a caller who meets a failure on **any** backend catches
the type the docs promised and can tell *which* failure it was, rather than an
empty message (BUG-264, which carries both halves — its Disposition is exactly
whether the base-class fall-throughs should be classified or merely given a
message); a connect that fails locally is not reported against the caller's path
(BUG-273); what a failed operation *leaves behind* is not
worse than the failure itself, so a reported failure never silently destroys the
caller's file (BUG-270, BUG-272); and a newly
registered backend cannot pass CI without meeting BE-004, BE-005 and BE-021
(BK-345). BK-359 is why the Promise above carries a third clause, added with it
rather than left implicit: an error that is
the right *type* on every backend but says nothing is predictable to a checker
and not to the person reading their log, and this section is where that reader
is served. That clause is now met on SFTP's `BackendUnavailable` arms and
nowhere else — BK-359 closed the backend whose stall BK-356 had just made the
default failure surface, and BUG-264 carries the same question outward with the
answer already measured rather than guessed: Azure reproduces the defect, both
botocore arms are immune, and the base-class arms leak a blank
`RemoteStoreError` on SFTP too. A promise clause honoured on one arm of one
backend is the shape this section exists to catch, and the count of arms is why
BUG-264 is not the tidy one-line follow-up it was first filed as.
The spec contradiction is adjudicated — BUG-248, closed by
[ADR-0038](adrs/0038-absent-container-outranks-drive-identity.md) — the
never-leak invariant holds on the S3 listing path, closed by BUG-249 with
BUG-246, and on SFTP's streamed-read path, closed by BK-358: a dropped
connection reached a caller holding a `read()` stream as a raw
`paramiko.SSHException` where the same drop on `read_bytes` mapped, and the
shared stream wrapper now takes the shapes a backend's transport was measured to
raise outside its base tuple (SIO-012). The two halves of the clause the item
spanned are why it sat here rather than with the streaming work: a caller who
catches one exception type is this section's promise verbatim, and the
`read()`/`read_bytes` split meant the same fault answered two ways.
The last adapter answers the contract against an absent container,
closed by BUG-247, and a write to the store root no longer occupies that root
with a regular file, closed by BUG-259 — which also brought the five
flat-namespace classes that reached their SDK with the root key to the same
rule. The catches-the-promised-type half is met on SFTP's connect path, closed
by BUG-265: a refused port and a DNS failure raise the `BackendUnavailable`
fifteen docstrings and the health-check guide promise, where both raised the
base class. That is one backend's connect arm, not the clause — BUG-264 carries
the rest, and the two are the same promise met at different depths. It also
opened BUG-273: the same connect path still answers the wrong type when the
connect is rejected locally — `PermissionDenied` blaming the caller's key on the
`EACCES` shape, whose trigger is unknown, and the base `RemoteStoreError` on the
`EPERM` one a netfilter `REJECT` does produce. Neither is `BackendUnavailable`,
so it is the promised-type defect again; the qualifier is load-bearing, because
the reproducible half is the one that answers the base class.
**One cross-section dependency remains**, per
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
**Four** further disagreements sit in this section and none of them is with the
absent-container clause, which is why they are not in that count: BUG-253 is
between two halves of one Graph operation; BUG-245 is a constructor leak, which
BE-021 scopes to operations and so does not reach; BUG-254 is with **BE-029's
root row**, which BE-021 § Reach now defers to rather than deciding, so the
breach is of the row § Reach points at and not of the clause this count is about;
and BUG-256 is about a health probe, which is off the roster BE-021 governs.
BUG-259 (BE-029's root row on the write path) and BK-358 (the never-leak clause
reached through the shared stream wrapper) were of this kind too and have both
closed; each is named in the closures above rather than counted here. **No
ordinal is given for them**, and that is a correction rather than a style choice:
this sentence read "a sixth of this kind" against a list that has stood at five
and at six within one release, so an ordinal over a list items keep leaving is
wrong from the next closure onward. The count above is derived from the entries
that follow it; nothing else here is counted.
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

- [ ] **BUG-272 — A non-dead rename failure in the atomic fallback removes the destination *and* the temp, losing both copies**
  spec: SFTP-014, AW-003 · effort: M · audience: user.api
  Distinct from BUG-270, which is about a *stall* in the same window and where the
  payload survives in the orphan temp. Here nothing survives.
  Measured against the in-process server with `posix_rename` unsupported and the
  fallback `rename` failing for a **non-dead** reason (`EACCES`, and again with
  `EIO`), for both `write_atomic` and `open_atomic`: `_rename_fallback` removes the
  destination, the `rename` fails, and `write_atomic`'s `except BaseException`
  handler then computes `connection_lost = False` and *successfully* unlinks the
  temp. Observed `remove()` calls were the destination followed by the temp, and
  the directory was left empty. `PermissionDenied` is raised, so the caller is
  correctly told the write failed — and their pre-existing file is gone with no
  copy of the replacement anywhere.
  **The cleanup guard is doing exactly what it was designed to do**, which is why
  this is a design question rather than a typo: it skips the unlink only when the
  failure is a dropped connection, on the reasoning that a live connection can
  afford the tidy-up. That reasoning does not account for the fallback having
  already destroyed the destination before the failure, which makes the temp the
  only remaining copy.
  **`AW-003`** ("If `overwrite=True`, the atomic rename replaces the existing
  file") is unqualified against this path and is the cross-backend clause to
  amend, on the same terms AW-004 was amended by BK-360.
  **Found by BK-360's review round 4, by a measuring pass.** BK-360 softened the
  recoverability claims in the guide and in BUG-270 rather than asserting a temp
  the caller may not have; it does not fix this.

- [ ] **BUG-271 — `022-streaming-atomic-writes.md` carries three `open_atomic` invariants that shipped tests refute**
  spec: SAW-004, SAW-005, SAW-009 · effort: S · audience: contributor.process
  BK-360 amended AW-004 for the SFTP dropped-connection divergence and corrected
  `open_atomic`'s docstring, but the spec that governs `open_atomic` was not told:
  - **SAW-004** "On exception, target path is unchanged (no partial file)" —
    refuted by `test_the_rename_fallback_destroys_the_destination_when_the_promote_stalls[open_atomic]`
    (destination gone) and `test_a_lost_reply_can_complete_the_operation_it_reports_as_failed[open_atomic]`
    (destination replaced), both shipped and passing.
  - **SAW-005** "Temp artifact is cleaned up on both success and failure" — the
    same clause AW-004 was amended for, refuted by
    `test_a_stalled_atomic_write_preserves_the_destination_and_leaves_an_orphan_temp[open_atomic]`.
  - **SAW-009**'s per-backend prose, "On failure, `sftp.remove()` cleans up" —
    contradicted by the deliberate skip AW-004 now records.
  The divergence is already established in code, in `open_atomic`'s docstring and
  in AW-004; only this spec is stale, so the work is to carry the same scoping
  across rather than to decide anything new. Left out of BK-360 deliberately: that
  item's review had already absorbed two cross-spec surfaces, and the evidence
  there was that each absorption was where the next defect came from.
  **Found by BK-360's review round 4, by a measuring pass.**

- [ ] **BUG-270 — `_rename_fallback` destroys the destination and strands the payload when the promote stalls**
  spec: SFTP-014, SFTP-030 · effort: M · audience: user.api
  Under `overwrite=True`, `_rename_fallback` and `_move_fallback` each
  `remove(dst)` and then `rename(tmp, dst)`. A silence beginning at that `rename`
  leaves the destination **gone** with nothing put in its place — for
  `write_atomic` / `open_atomic` the payload is stranded in the orphan
  `.~tmp.<name>.<uuid8>`; for `move` the source survives. Measured at
  `io_timeout=2.0`, client→server silenced at the `rename`: destination absent,
  one orphan temp for the atomic paths and an intact source for `move`.
  The `overwrite=True` condition is load-bearing and part of the recipe: both
  fallbacks guard the `remove` on it, and with `overwrite=False` the prior stat
  raises `AlreadyExists` before either fallback is reached.
  **It is not confined to servers lacking `posix-rename@openssh.com`.** The route
  in is a `posix_rename` failure `_is_connection_dead` does not recognise, on a
  target `_raise_if_dir` (or, for `move`, the destination `stat`) has not already
  rejected. Measured per trigger against a server that answers the extended
  request: `EACCES` reaches both fallbacks; `EXDEV` reaches `_move_fallback`
  only, since `write_atomic` puts its temp in the target's own directory; a
  **directory target reaches neither** — the promote path is guarded by
  `_raise_if_dir` and `move` by its eager destination `stat`, which are different
  guards and were conflated at one point in BK-360's own review.
  Reproduced on a server that advertises and answers the extended request and
  fails this one, with nothing patched client-side: destination gone, payload in
  the temp. That widens who is exposed from a legacy-server edge case to any
  store where a rename can fail for a mundane reason.
  **It is the residue state that leaves the caller worst off**, and it is reached
  through the operation the library recommends for safety. Under a *stall* the
  payload usually survives — in the orphan temp for the atomic paths, or in the
  source for `move` — because `_is_connection_dead` is true and the cleanup unlink
  is skipped. **That consolation does not hold for a non-dead failure**: BUG-272
  records a measured case where the fallback removes the destination, the rename
  fails for a non-dead reason, and the cleanup then successfully removes the temp
  too, so neither copy remains. So this item should not be fixed on the assumption
  that the temp is a recovery path.
  **A second, independent half: it costs two `io_timeout` bounds, not one.** The
  `remove` runs under `contextlib.suppress(OSError)`, so its own timeout is
  swallowed and the following `rename` re-enters the same stalled channel.
  Measured 4.00 s at a 2.0 s bound. SFTP-030's one-bound paragraph does name a
  suppressed `remove` in mechanism 3, so the gap is not a missing list entry.
  It is that the mechanisms are **per operation**: `move` has no `_raise_if_dir`
  step, so nothing fires between its failed `posix_rename` and `_move_fallback`
  and it pays two bounds. The promote path does have one, and under the same
  antecedent mechanism 2 fires — `_raise_if_dir`'s own stat re-enters the silent
  channel and re-raises — so `_rename_fallback` is never entered and the cost is
  one bound. `_rename_fallback` reaches two only when the silence begins later,
  at its own suppressed `remove`. An earlier version of this item said all three
  mechanisms key on the caller's `exc`; mechanism 2 does not, and that
  conflation is what sent the spec's first attempt at this wrong.
  **Fixing the first half needs a decision, not just a patch:** the
  remove-then-rename ordering is what makes a non-atomic overwrite possible when
  `posix_rename` is unavailable, so removing the window may mean accepting that
  such a store cannot overwrite atomically and saying so, rather than silently
  narrowing it.
  `_rename_fallback` carries `# pragma: no cover` (`_move_fallback` does not, and
  its docstring explains why). BK-360 added
  `test_the_rename_fallback_destroys_the_destination_when_the_promote_stalls`,
  which drives both, so the behaviour is pinned even though the pragma still
  suppresses coverage reporting for one of them — worth revisiting with the fix.
  **Found by BK-360's review round 2, by a measuring pass**, with the server-class
  scope corrected by its round 3. BK-360 documents the resulting state in
  SFTP-030 and the SFTP guide; it does not fix it.

- [ ] **BUG-264 — A mapped error can still reach the caller with an empty message on Azure, and through the base-class arms everywhere**
  spec: ERR-009 · effort: M · audience: user.api
  BK-359 fixed the SFTP `BackendUnavailable` arms. Two things it did not reach
  are measured here rather than assumed, because the first draft of this item
  filed the question as "unmeasured" and both halves of that guess were wrong.

  **Azure is a confirmed reproduction, not a hypothesis.** A genuine
  `asyncio.TimeoutError` — obtained by running `asyncio.timeout(0.001)` around a
  sleep, not by constructing one — carries `args=()` and `str() == ''`.
  `azure/core/pipeline/transport/_aiohttp.py` wraps it as
  `ServiceResponseTimeoutError(err, error=err)` at lines **397, 483 and 580** of
  the installed 3.x, and `AzureError.__init__` sets `self.message =
  str(message)`. That subclasses `ServiceResponseError`, so
  `classify_azure_error`'s `ServiceRequestError | ServiceResponseError` arm
  (`backends/_azure_common.py:173`) returns `BackendUnavailable('')`, rendering
  as `" | path='delivery.csv' | backend='azure'"` — character for character the
  SFTP defect. **Line 395 is a fourth raise site on the same arm**, wrapping the
  same `asyncio.TimeoutError` as `ServiceRequestTimeoutError`, which subclasses
  `ServiceRequestError`; an earlier revision of this item cited three sites and
  had each line number one low, so treat the set as four.
  It reaches `AsyncAzureBackend` (**10** `classify_azure_error` call sites:
  611, 894, 943, 1020, 1056, 1091, 1118, 1155, 1181, 1658) and `AzureBackend`
  (**3**: 1818, 1965, 2024) — counted as call sites, with the `from ... import`
  line excluded, which is where the earlier 11-and-4 figures came from.
  The sync side is exposed the same way but is
  **not** reproduced: `requests`' `ConnectionError`, `ReadTimeout`,
  `ConnectTimeout` and `ChunkedEncodingError` all stringify empty when
  argument-less, and the requests transport wraps them identically, but requests
  itself normally supplies urllib3 text, so only the async timeout is an
  end-to-end reproduction.

  **Both boto3 arms are immune**, which the first draft of this item implied
  might need fixing. `ClientError` always formats from a template — even
  `ClientError({}, "GetObject")` gives `"An error occurred (Unknown) when calling
  the GetObject operation: Unknown"` — and `BotoCoreError` formats from a class
  `fmt`, with a bare instance giving `"An unspecified error occurred"`. Recorded
  so the next reader does not re-derive it.

  **The `BackendUnavailable` framing was too narrow**, which is the second thing
  BK-359 did not reach. ERR-009 is a claim about `str()` on *any* error, and the
  same construction spelled with the base class is at **7** sites in 5 files:
  `rg -n 'RemoteStoreError\(str\(exc\)' src/` → `backends/_azure_common.py:198`
  and `:199`, `backends/_s3_boto3.py:972`, `backends/_s3_pyarrow.py:651`,
  `_errors.py:194`, and **two in `backends/_sftp.py`** — the `OSError` and final
  fall-through arms of `_map_exception`, cited without line numbers because that
  method is what BK-359 was editing and two successive revisions of this item
  cited numbers its own diff had already shifted. Those two are the fall-through
  arms of the very `_map_exception` BK-359 rewrote, so SFTP is not finished
  either — reading that item's title would suggest otherwise.
  Two of these are reachable and were driven through the real code:
  `_classify_by_message(OSError(''))` returns `RemoteStoreError('')`, and an
  empty `OSError` through `S3PyArrowBackend._pyarrow_errors` does the same. Note
  those two sites are *unreachable* for `BackendUnavailable` — its branch needs
  one of `endpoint`/`connect`/`timeout`/`dns`/`name or service` in the message
  and `""` contains none — so reading the guard alone concludes "safe" and
  running it finds the exit one line below. That is the whole reason this item
  exists in measured form.

  **Disposition:** the SFTP `_unavailable` helper is the shape to copy for
  Azure. The base-class arms need a decision first — whether a blank
  `RemoteStoreError` deserves the same synthesised fallback, or whether those
  fall-throughs should be classified rather than passed through — which is why
  this is M and not S.
  **Filed by BK-359's `/ship` run**, whose round-1 reviewer found the
  base-class half; the Azure half was measured after the item was challenged for
  asserting rather than checking.

- [ ] **BUG-273 — A locally-rejected SFTP connect answers the wrong type, and neither permission errno can be claimed without connect-time context**
  spec: SFTP-021, SFTP-023 · effort: S · audience: user.api
  BUG-265 gave `_map_exception` a connect-time arm for the unreachable-host
  errnos and deliberately left **both** permission errnos out of it. This is
  that exclusion, recorded rather than left for the next reader to re-derive.
  **`EPERM` was tried and reverted inside BUG-265, which is the sharpest
  evidence this item has.** A round of review found a firewall-rejected connect
  answering the base `RemoteStoreError` and argued `EPERM` was free to claim,
  because `_map_exception`'s errno dispatch has no `EPERM` arm. That premise is
  true of the dispatch and false of the module, and the next round measured it:
  `_raise_if_dir` re-raises **both** permission errnos on purpose
  (`_sftp.py`, the classification-stat guard, and its docstring says why), from
  a **working** channel, inside the caller's `_errors(path)` block. Driving the
  exact shape `test_raise_if_dir_permission_stat_maps_permission_denied` uses:
  `EPERM` gave `RemoteStoreError` before the change and
  `BackendUnavailable("[Errno 1] Permission denied")` after it, **and with a
  sentinel seeded the new arm cleared the cached client** — so a healthy
  connection was discarded on a server-reported denial. **The grounds matter
  and were first stated too strongly:** the published v0.29.1→v0.30.0 migration
  row promising `PermissionDenied` for that stat was *already* not honoured for
  `EPERM` before the change and is not honoured after it, which is BUG-275, not
  this item. What claiming `EPERM` did was move that path from the base class to
  `BackendUnavailable` plus a client reset — worse, and enough on its own.
  Reverted; `test_the_permission_errnos_stay_out_of_the_connect_arm`
  now pins the exclusion so a future widening fails loudly instead of silently
  changing what a live channel reports.
  **The lesson for whoever picks this up:** "nothing else wants this errno" is a
  claim about the whole module, not about one if-chain, and `rg -n 'EPERM' src/
  docs-src/` is the derivation. Both errnos are one problem, not two.
  **What was measured**, by monkeypatching `socket.socket.connect` to raise a
  chosen errno and driving `paramiko.SSHClient.connect` on paramiko 5.0.0:
  `EACCES` is re-raised unwrapped, exactly like `ENETUNREACH` / `ENETDOWN` /
  `EHOSTDOWN` (`SSHClient.connect` captures only `ECONNREFUSED` and
  `EHOSTUNREACH` into `NoValidConnectionsError`; its own docstring says so). It
  therefore reaches the mapping as a plain `PermissionError` and takes the
  `EACCES` arm. Measured per operation, since the two answers differ:
  `read_bytes("delivery.csv")` and `exists("delivery.csv")` answer
  `PermissionDenied("Permission denied: delivery.csv")`, while `check_health()`
  — which runs under `_errors()` with no key — answers a bare
  `PermissionDenied("Permission denied: ")`. That is BUG-265's own defect shape,
  a caller following the health-check guide catching the wrong type, in two
  flavours: on a keyed operation the message names a path as the subject of a
  failure the path had no part in, and on the probe it dangles a colon with
  nothing after it — the shape
  `test_a_message_less_dns_failure_does_not_trail_an_empty_colon` exists to
  prevent on the sibling arm.
  **What was NOT measured, and it is the item's open question:** that any real
  network produces `EACCES` on `connect()`. **No trigger is known**, and the
  first work here is finding one. An earlier revision of this item offered
  `iptables --reject-with icmp-admin-prohibited`; that is wrong and is recorded
  here so it is not tried twice. It sends ICMP type 3 code 13, which Linux's
  `icmp_err_convert` maps to `EHOSTUNREACH` — an errno BUG-265 already put in
  `_is_unreachable`'s tuple, so following that recipe lands on the new arm and
  shows nothing. A local `OUTPUT`-chain `REJECT` yields `EPERM`, also not
  `EACCES`. `EPERM` **does** have that trigger, which is what made it tempting;
  it is not a reason to claim it. If no `EACCES` trigger exists, that half is a
  documentation item rather than a code one.
  **What it costs a caller if left: nothing observable today, and that is the
  finding rather than a reason to close it.** No connect anyone has produced
  raises `EACCES`, so the wrong-type answer is unreachable; were it reachable, a
  caller following the health-check guide's `except BackendUnavailable` would
  catch nothing and meet `PermissionDenied` naming their key, or a bare
  `Permission denied: ` from `check_health`, for a request that never left the
  machine. The item's real value is the measurement it carries: the next person
  to consider widening `_is_unreachable`'s tuple finds here why that breaks a
  working channel, instead of rediscovering it the way BUG-265 did across two
  rounds.
  **Disposition:** not widening the tuple — that was tried and measured harmful,
  above. The same errnos on a live operation genuinely are a denied path
  (`test_eacces_maps_to_permission_denied` pins one, `_raise_if_dir`'s guard the
  other), and `_map_exception` dispatches on the exception alone, so it cannot
  tell a connect-time one from an operation-time one. The cheap shape is for the
  lazy `_sftp` property to classify what `_connect` raises **before** the
  caller's `_errors(path)` block sees it, which reaches both errnos at once and
  is the only place the connect-time context exists.
  **Found by BUG-265's round-3 measuring member**, which reported the `EACCES`
  half as a `Possible: Bug:` with its trigger flagged unreproduced; the `EPERM`
  half was found, fixed and reverted across its rounds 5 and 6.

- [ ] **BUG-275 — `_raise_if_dir`'s permission re-raise delivers `PermissionDenied` for one of the two errnos it names, and four artifacts promise both**
  spec: SFTP-021 · effort: S · audience: user.api, user.api_docs
  Pre-existing, not introduced by BUG-265 — found by its closing whole-file
  pass, which was checking whether that item's `EPERM` revert had left half a
  claim standing and found a whole one that predates it.
  **Measured on the shipped code**, driving `_map_exception` with a plain
  `OSError` carrying each errno:
  `EACCES` → `PermissionDenied("Permission denied: delivery.csv")`;
  `EPERM` → base `RemoteStoreError("denied")`. The errno dispatch has an
  `EACCES` arm and **no `EPERM` arm**, so a re-raised `EPERM` classification
  stat falls to the generic arm.
  **What promises otherwise**, all saying the re-raise exists "so a server that
  denies even statting the target surfaces `PermissionDenied` rather than a
  generic `RemoteStoreError`": `_raise_if_dir`'s docstring, its BK-316 inline
  comment beside the guard, BK-316's `BACKLOG-DONE.md` register entry, and —
  published — the v0.29.1 → v0.30.0 migration table row
  `| Permission-denied classification stat (EACCES/EPERM) | RemoteStoreError | PermissionDenied |`.
  For `EPERM` that row's "after" column is exactly its "before" column.
  **Trigger is unestablished, and that bounds the priority rather than the
  diagnosis.** paramiko's `SFTPClient._convert_status` maps
  `SSH_FX_PERMISSION_DENIED` to `EACCES`, so an SFTP-protocol `EPERM` looks
  unproducible; the re-raise names both errnos because BK-316 was written for
  "non-OpenSSH servers whose error shapes differ from OpenSSH", which is the
  case nobody has a fixture for.
  **What it costs a caller if left:** a user on such a server whose stat is
  denied with `EPERM` gets the base `RemoteStoreError`, so an `except
  PermissionDenied` clause written on the strength of the published migration
  row falls through to their generic handler and a permissions problem is
  logged as an unknown failure. BUG-265 caveated that published row, so what
  remains is the code-vs-docs divergence rather than a silently misleading
  page — the cost of leaving it is that three in-tree artifacts still describe
  behaviour the module does not have, and the next reader of `_raise_if_dir`
  has to re-derive which half is true.
  **Disposition:** two ways to make the four artifacts agree, and they differ in
  what a caller gets. Either give the dispatch an `EPERM` arm mapping to
  `PermissionDenied` — which makes every promise true and is a behaviour change
  — or narrow all four to say `EACCES` alone reaches `PermissionDenied` and
  `EPERM` reaches the base class. **Do not answer it by widening
  `_is_unreachable`**: BUG-273 records that attempt and its measured harm.
  **Found by BUG-265's closing pass**, which also caught the two places where
  that item's own body had cited the migration row as though it were satisfied
  before and after — corrected there.

- [ ] **BUG-274 — A keyed SFTP operation against an unreachable host pays the connect budget two or three times over**
  spec: SFTP-010, SFTP-023 · effort: S · audience: user.api
  Not a regression — master behaves identically — but BUG-265 introduced the
  predicate that would close it, and BUG-265's own round-4 measurement is what
  exposed the mechanism.
  **The fourteen mid-operation re-entry guards all ask `_is_connection_dead`
  alone**, and that predicate answers `False` for every shape `_is_unreachable`
  claims. Measured on `read_bytes("delivery.csv")` against a just-released
  ephemeral port, with `_is_connection_dead` wrapped in a frame-recording
  counter: three consultations (`_sftp.py:903` — `read_bytes`'s own guard,
  `_sftp.py:2047` — `_raise_if_dir`, and the mapping's own) and **two full
  `_connect` cycles**. The guard at 903 declines, so control falls through to
  `_raise_if_dir`, which re-evaluates the lazy `_sftp` property and pays the
  whole `RetryPolicy` budget again — three attempts with 2–10 s exponential
  backoff by default. For a nested key `_has_file_ancestor` makes it three.
  `check_health` is unaffected: it has no re-entry guard, which is why
  BUG-265's "connect attempts are identical on both revisions" holds for the
  probe and not for keyed operations.
  **What it costs a caller, measured as wall clock at shipped defaults** — no
  `retry=` passed, against a just-released ephemeral port, timed per call:

  | call | elapsed |
  |---|---|
  | `check_health()` | 4.37 s |
  | `exists("a.csv")` | 4.00 s |
  | `read_bytes("a.csv")` | **8.00 s** |
  | `read_bytes("a/b/c.csv")` | **12.01 s** |

  That is the 1x / 2x / 3x cycle count showing up as time. **A refused port is
  the cheap case**: each attempt fails instantly, so the elapsed time is almost
  all backoff. Against a blackholed address every attempt also burns the 10 s
  `timeout`, so the same multiplier lands on a base roughly an order of
  magnitude larger. A caller reading many keys from a store that is down pays
  this per key, which is the shape most likely to be reported as "the library
  hangs" rather than as a latency bug.
  **Disposition:** `or self._is_unreachable(exc)` at those guard sites is the
  one-line shape, and it is a **behaviour change**, not only a saving: `read`
  and `read_bytes` would then raise at their guard instead of falling through
  to classification. That is the correct answer for a host that was never
  there, but it is the same widening BUG-265 declined to make under review, so
  it wants its own failing test first — and note that
  `TestSFTPConnectTimePredicateSpace` deliberately asserts the observable answer
  and *not* a connect count, so nothing in the suite would notice this either
  way today. Pinning the count is part of the work.
  **Found by BUG-265's round-5 unprimed reviewer**, as a `Possible: Perf:`.

- [ ] **BUG-266 — No artifact maps an observable SFTP failure onto the arm that handles it, and four prose attempts were each refuted**
  spec: SFTP-023, SFTP-030 · effort: M · audience: user.site, library.maintainer
  `_map_exception` dispatches on exception *type*, and SFTP-023 states the arms
  that way — correctly, and pinned by tests. What no artifact states correctly is
  the other direction: given a failure a reader can observe (a refused port, a
  wedged daemon, a silent peer, a rejected credential, a DNS failure), which arm
  does it reach and what does the caller get.
  **Four attempts to summarise that in a sentence were each refuted by
  measurement**, all during BK-359's review loop: "a failed probe logs once per
  poll"; "two records per poll, three under `AUTO_ADD`"; "a failed probe writes
  more than one record" (zero under `RetryPolicy.disabled()`); and "only a probe
  that fails by timeout reaches the mapping" — refuted by a bad SSH banner, an
  accept-then-hangup and an `AuthenticationException`, all three of which reach
  `_unavailable` through the `SSHException` arm with one `op="error_mapping"`
  record.
  **The diagnosis is that the space has axes a sentence cannot carry**: the
  observable failure, the mapping arm, the retry policy's `max_attempts`, and
  the host-key policy. Each refuted attempt stated one cell of that product as
  though it were the whole table.
  **Disposition:** write it once as a parametrised test enumerating
  observable-failure x arm, asserting the resulting type, message shape and
  record count, then let the spec and the guides point at the test rather than
  restate it. The harness exists — `_StallRelay` plus the in-process server
  already drive stalls in both directions, and BK-359's review produced working
  probes for a refused port, a DNS failure, a bad banner and an
  accept-then-hangup. Sized M because the enumeration, not the assertion, is the
  work.
  **Filed by BK-359's round 4**, after that loop's repeat-site check fired:
  three rounds refuting one condition means enumerate the space rather than
  restate it a fourth time.

- [ ] **BUG-269 — `observe.md`'s level and `op` tables are enumerations that were already false on master, and BK-359 adds to both**
  spec: OBS-008 · effort: S · audience: user.site
  `docs-src/guides/observe.md` § *Logging levels used* and § *Structured `extra`
  fields* are written as enumerations over the whole library — the section three
  headings up names `remote_store.backends._local` as an example logger, so
  backend records are in scope, not just `ext.observe`'s.
  **Both were already false on master**, which is what keeps this out of
  BK-359's scope rather than in it:
  | Row | Says | Contradicted on master by |
  | --- | --- | --- |
  | `WARNING` | "Suppressed hook exceptions, fallback behaviour" | the `AUTO_ADD` host-key warning, `backends/_sftp.py:1828` — neither |
  | `op` | "Operation name (`"read"`, `"write"`, ...)" | `op="connect"` (3 sites), `"download"`, `"upload"`, `"transfer"` — 5 non-operation values, counted by `git grep -n 'extra={"op"' origin/master -- src/` |
  | `ERROR` | "Before re-raising backend errors" | nothing in `src/` logs at that level — **BUG-267**, filed separately |

  BK-359 adds one more of each: an `op="error_mapping"` `WARNING` that is not a
  suppressed hook exception and not an operation name. It is the third and sixth
  instance respectively, not the first.
  **Why it is filed and not fixed.** BK-359 rewrote these rows once; the rewrite
  was reverted with the rest of its guide prose after four rounds found defects
  in it, and this item is the paired record that revert owes — the same pairing
  BUG-268 made for `troubleshooting.md`. Correcting the `op` row is not a fact
  but a contract decision: whether `op` means "Store operation" (in which case
  `connect`, `transfer` and `error_mapping` are misuses of the field) or
  "operation or internal stage" (in which case the row is merely under-written).
  That decision sits next to **BUG-267**'s, which is why both should be taken
  together and neither inside a fix pass. **BUG-266** owns the observable-failure
  → arm table and reaches neither row.

- [ ] **BUG-267 — OBS-008 demands an `ERROR` level that nothing emits and nothing asserts**
  spec: OBS-008 · effort: XS · audience: contributor.process
  OBS-008's Levels bullet read "ERROR (before re-raise)" as an invariant over
  "all library modules". No call site in `src/` logs at `error`, `exception`,
  `critical` or `fatal` — verified by grep across the package — and none of the
  four `@pytest.mark.spec("OBS-008")` tests in `tests/ext/test_observe.py`
  asserts a level at all.
  That is [`000-process.md` Rule 7](000-process.md#intent-attribution)'s
  **Unenforced** row: prose demanded it, nothing enforced it, so the claim is
  undecided and **nothing moves yet**.
  **BK-359 twice tried to resolve it in passing and both attempts were wrong.**
  It first deleted the clause and wrote current behaviour into the spec — the
  code made right by prose inside a review fix pass. Its round 4 caught that and
  suspended the clause instead, which left the spec saying *undecided* while the
  guide `docs-src/guides/observe.md`, rewritten in the same PR, still published
  the withdrawal as settled. Round 5 found that split. Both edits are reverted;
  OBS-008 and the guide are back at their pre-BK-359 text, so the divergence is
  intact and undecided rather than half-resolved in two directions.
  **The decision owed** is one of two: either the library should report before
  re-raising, and the deliverable is that call site plus the level assertion
  Rule 2 wants; or it should not, and the clause is withdrawn on the ordinary
  path with the reason recorded. Either way it is decided once rather than
  inherited.

- [ ] **BUG-263 — The migration guide promises a drive folder named `.` stays reachable as a key; no key spelling reaches it**
  spec: GR-058 · effort: XS · audience: user.site
  `docs-src/reference/migration.md` § *`GraphBackend(base_path=".")` now means
  the drive root* tells a caller whose drive holds a folder literally named `.`
  that it "stays reachable as an ordinary key under a `base_path` that is not
  itself a root spelling". It is not reachable under any `base_path`, because
  the predicate that strips `.` from `base_path` is the same one that strips it
  from every key: `GraphBackend._key_segments` delegates to
  `_flat_ns._addressable_segments`, and `native_path` /
  `_parent_ref_path` / the write and source guards all route through it.
  Measured with `base_path="reports"`:
  | key | addresses |
  | --- | --- |
  | `./x` | `/drives/D/root:/reports/x:` |
  | `.` | `/drives/D/root:/reports:` |
  | `x/./y` | `/drives/D/root:/reports/x/y:` |

  So the folder is unaddressable, not relocated — which is a strictly larger
  break than the section describes, and the sentence sends a caller looking for
  a workaround that does not exist.
  **The fix is the sentence, not the code.** `_addressable_segments`' own
  docstring records why the two predicates must stay identical (a draft that
  widened one broke the `to_key(native_path(key)) == key` identity on 4 of 7
  measured keys), so the guide should say the folder can no longer be addressed
  and name what a caller does instead — rename it before upgrading.
  The neighbouring claim, "Every other `base_path` value is unaffected", was
  checked and **holds**: the only behavioural difference between the old `if s`
  split and `if s and s != "."` is dot segments, and the preceding sentence
  already covers those. Recorded so the next reader does not re-litigate it.
  Found by ID-252's closing review reading outside its own diff; shipped by
  BUG-261.

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
  **This item now has a published-docs consequence, acquired in BUG-261, and it
  covers both breaching columns rather than one.** `docs-src/reference/migration.md`
  § v0.30.0 to v0.31.0 publishes the root row to users and therefore had to
  publish its exceptions too. Four passages exist only while this item is open,
  and closing it deletes or rewrites **all four** — a sweep that stops at the
  first leaves the guide telling users a store is unfinished in a way it no
  longer is:
  1. The root section's "Three backends answer the first row differently"
     paragraph — the `exists("")` / `is_folder("")` cells on `S3Backend` and
     `S3PyArrowBackend`. Its third bullet is `GraphBackend` and is **not** this
     item's: that answer is deliberate and stays.
  2. The absent-container section's two-row divergence table. Row 1 is the
     `get_folder_info("")` cells on `S3Boto3Backend`, `AzureBackend` and
     `AsyncAzureBackend`; row 2 is the same `S3Backend` / `S3PyArrowBackend`
     cells as (1).
  3. The "Treat both as unfinished" paragraph under that table, including its
     `NotFound`-handler advice.
  4. The two redirects that only make sense while the divergence exists — one in
     the root section, one under the divergence table — both saying `exists("")`
     is not a portable "is my store there?".
  Together these are the same **seven** class-cells this item counts, so the
  guide and the item are now scoped alike. The first version of this note named
  only the `get_folder_info` half and said the `exists` row "stays as written",
  which was the fix-reaches-half-the-surfaces defect this note exists to prevent.
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
  **Six documentation surfaces promise the behaviour** and are part of this item
  rather than of BUG-246, which measured the divergence but did not create it:
  `Backend.check_health` and `AsyncBackend.check_health` docstrings,
  `Store.ping()`, `AsyncStore.ping()`, `docs-src/guides/health-check.md`, and
  `docs-src/reference/migration.md` § v0.30.0 to v0.31.0, whose
  absent-container section sends a caller to `ping()` as the replacement for the
  `except` clause this release stops firing. The sixth was **five** until BUG-261
  added that section; it is counted here rather than left to the grep because the
  figure is the derivation ([principle 9](../CLAUDE.md#principles)) and a fix
  scoped to a stale enumeration reaches five of six surfaces. That section already
  carries this item's bound in published prose — a table naming all three
  backends measured above, `SQLBlobBackend` and `SQLQueryBackend` on the bare
  `SELECT 1` and `S3PyArrowBackend` on a `get_file_info(bucket)` whose result
  `check_health` discards (`_s3_pyarrow.py:188-190`), which is the same shape
  stated without this file's shorthand, plus a statement that "is my store
  there?" is unanswered on `S3PyArrowBackend` today —
  so closing this item edits that table rather than discovering it. It stops at
  the three: `ReadOnlyHttpBackend`'s wrong-type raise is not published anywhere,
  because no migration section names that backend.
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
ID-247's 30 root-path cells).
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

- [ ] **BUG-260 — `SQLBlobBackend.list_files("./")` answers empty for a non-empty root**
  spec: BE-029, SQL-BLOB-010 · effort: S · audience: user.api
  Measured on a root holding two files: `exists("./")` is `True`, `is_folder("./")`
  is `True`, and `list_files("./", recursive=True)` returns **zero** entries —
  where `""` and `"."` both return two. So the probes agree the folder is there
  and the listing comes back empty, which is worse than either answering
  consistently. `LocalBackend` and `MemoryBackend` answer `True / True / 2` under
  all three spellings, so this is not the shared read-side behaviour.
  The cause is the listing prefix: `is_root` recognises only `""` and `"."`, so
  `"./"` falls through to the non-root branch and becomes the LIKE prefix
  `'./%'`, which matches no stored key. The probes do not use that branch.
  **Not fixed by widening `is_root`**, which has 52 call sites across 13 files
  including `native_path` / `to_key` — BE-008's asymmetry paragraph explains why
  that is a spec-amendment-class change rather than a local fix. The local fix is
  in the prefix construction, and the general question — whether the read side
  owes the wider predicate at all — is the one BE-008 currently answers "no" to
  on the strength of the cost being an error class. This item is the
  counterexample to that reasoning and should be read alongside it.
  Found by the closing gate of BUG-259, which guarded the write side under the
  wider predicate and left the read side stated but unmeasured.

- [ ] **ID-251 — BE-029's widest clause is one the conformance suite cannot fail on**
  spec: BE-029 · effort: M · audience: infra.test
  BE-029 requires the write guard to refuse **every spelling that addresses the
  root**, and says outright that a backend implementing it as `if is_root(path)`
  is not conformant. The conformance cells cannot detect that: `_ROOT_WRITE_OPS`
  and `_ROOT_WRITE_DST_OPS` are parametrised over `["", "."]` only, because they
  also `assert is_root(exc.value.path)`. So a backend that reimplements the guard
  narrowly ships green, and the only things holding the wider rule are
  `tests/backends/test_flat_ns.py` (the shared helper in isolation) plus the
  Local, SFTP and Graph per-backend modules — none of which a third-party backend
  runs.
  **Widening the parametrisation is not a one-liner**, which is why this is an
  item rather than a follow-up commit. `assert exc.value.path == root` has to
  replace the `is_root` assertion, and `DafnyOracleBackend` — registered with all
  capabilities bar GLOB and LAZY_READ, so bound by these cells — passes `"./"`
  through to the Dafny model unnormalised. Either the oracle normalises first or
  the roster carries a documented carve-out for it; that choice is the work.
  Found by the closing gate of BUG-259, which introduced the clause and the cells
  in the same change and so had no round in which the gap was visible as a
  regression.

- [ ] **ID-247 — Record the Graph root-path cassettes**
  spec: BE-029 · effort: S · audience: infra.test
  **30** `TestBackendRootPath` cells still skip on `graph_replay` for want of a
  recording — the "pinned nowhere" column of spec 003's BE-029 table. Graph is
  the only HTTP family with **no emulator tier** (`graph_live` Stage 3 and
  `graph_replay` Stage 1, nothing between), so those contracts are unexercised
  against `GraphBackend` at every stage below a live account; Azure's equivalent
  skips are covered by `azurite` at Stage 2.
  The 30 is re-derived by `pytest -k TestBackendRootPath -rs`, summing the skip
  reasons naming `cassettes/graph`. Twelve of the 30 are the rosters BUG-259
  added — `test_write_to_root_is_refused_and_the_store_survives` at 2 ops × 2
  overwrite modes × 2 root spellings, and
  `test_root_as_move_or_copy_destination_is_refused` at 2 ops × 2 spellings —
  both seeding through `write` and so skipping on the same terms, leaving **18**
  that predate it. The item previously said 22, which the 30 does not reproduce
  (18 + 12); the 22 is superseded rather than reconciled. Section 2's "Closes
  when" cites this figure and was updated with it — a superseded number is only
  harmless once nothing reads it, and checking that is part of superseding it.
  **The old "14 of the 22 are Graph-only" split is not re-derived here** —
  the new cells skip on the Azure replay lanes too, so the split did not simply
  move with the total, and separating it needs a per-node comparison of the graph
  and azure lanes rather than a count of skip reasons. Left for this item's own
  work rather than guessed at.
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
**true** (BK-339, BK-325, BK-364, ID-125), **reachable** (BK-327), and **walked
end-to-end by a maintainer** (BK-332, and ID-199's authoring contract). Each
clause names the items that move it, so closure is checkable rather than
asserted.

This is the group that converts directly into support load not arriving. The
rehearsal sits with the guides because it is the only mechanism that has ever
found their defects, and BK-327 sits here rather than with the gates because a
page nobody can navigate to is a page nobody reads — the gate is the mechanism,
not the payoff.

- [ ] **BK-364 — `transfer-operations.md` documents partial files for `download` only, and the other direction is the one that can destroy data**
  spec: — · effort: S · audience: user.site
  § Error semantics carries one bullet on residue — *"Partial files on failed
  download: if `download` fails mid-transfer a partial local file may remain …
  When retrying, pass `overwrite=True`"* — and says nothing about `upload` or
  `transfer`, which route through `store.write()` and so leave a partial file at
  the **remote** destination on exactly the same fault. The asymmetry is
  backwards: a partial local file is the caller's own disk and their own
  `overwrite` flag, while a partial remote file may have replaced data they
  cannot re-derive.
  **Found by BK-360's review round 1, while checking whether that item's SFTP
  rule rippled here.** It was left out of BK-360 deliberately: the SFTP rule is
  measured for one backend, and this bullet is about a helper that works over
  *any* `Store`, so stating it needs the residue question answered per backend
  rather than borrowed from SFTP. That is the work — establish what
  `upload`/`transfer` leave behind on the backends the helper is used with, then
  state it once beside the `download` bullet.
  BK-360 established the SFTP half and is the model: the governing fact there is
  that a timeout reports a *lost reply*, so an operation reported as failed may
  have been performed. Whether the flat-namespace backends share that shape is
  the open question, not an assumption to carry over.

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
(ID-181); and no cost we know how to remove is left on the caller (BK-242).
That last clause was carried by two items; BK-357 closed one of them, removing a
stalled `SEEK_END` seek's second `io_timeout` — and, more than a cost, the wrong
answer it returned instead of failing.

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

---

<a id="no-release-surprises"></a>
## 5. A release cannot ship a surprise

**Promise:** nothing reaches a user that we did not test, publish, watch, or
give them a way to absorb.

**Closes when:** every checker a diff can invalidate is reachable from a gate
that diff actually triggers (BK-333); every extra's drift smoke exercises the
packages it pins (BUG-250) and catches the drift that is visible only to a type
checker (ID-250); **every install channel we intend to offer is
published and working** (ID-018); every upstream that can break us on its
own schedule has a standing watch (ID-229, ID-225); and every breaking change
carries a published upgrade path by the time it ships — **satisfied**: the four
`[Unreleased]` entries marked `**Breaking**` all have a `migration.md` section,
and the obligation to write one moved onto the PR making the break, where its
author already looks (BUG-261, in [BACKLOG-DONE.md](BACKLOG-DONE.md)).

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
and named successors (ID-150, ID-249); the two backlog files are readable by the
person they are for, or the decision that their length is the right price is
recorded (BK-365); and the repo can say whether its own quality promise is
holding rather than only asserting it (BK-366).
**Bounded to those thirteen deliberately** — count derived by enumerating the
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

- [ ] **ID-254 — The `[Unreleased]` stub's section marker means one thing on half the entries and nothing on the other half**
  spec: — · effort: XS/S · audience: contributor.process
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
  spec: — · effort: XS · audience: contributor.tooling
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
  spec: — · effort: S/M · audience: contributor.tooling
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

- [ ] **BK-365 — Both backlog files grew past what a maintainer can read, and nothing measures it**
  spec: — · effort: M · audience: contributor.process
  **`sdd/BACKLOG.md` is 20,041 words.** That is the file a maintainer reads to
  decide what to work on, and it is now roughly eighty pages of prose. Two
  independent multipliers got it there over seven weeks (2026-07-18 → 2026-09-05):
  the item count doubled, 28 → 56, and the median words per item doubled too,
  145 → 292. Total 4,823 → 20,041 words — 4.2× against 12.7% growth in `src/`
  over the same window. `BACKLOG-DONE.md` shows the same shape at 103,446 words
  over 650 items, and its per-release medians run from **10 words per completed
  item at v0.3.0 to 646 under `Unreleased`** — 65×, of which 2.8× arrived in the
  current cycle alone (v0.30.0 sat at 234).
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
  **The question to answer before any rule is written:** is a 292-word median a
  defect, or the correct price of the derivations
  [principle 9](../CLAUDE.md#principles) requires? The research record
  ([research](research/research-appropriate-level-of-detail.md) § 9.2) supplies
  the test that would decide it — rationale a reader can reconstruct from what
  survives may be cut, rationale carrying a fact from elsewhere may not — and its
  § 4 supplies the reason a word budget is the wrong instrument. Run that test
  against a sample of entries and report before proposing anything.
  **Exit criteria:** a recorded decision on whether entry length is a defect;
  if it is, a mechanism named with its bound stated per
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
