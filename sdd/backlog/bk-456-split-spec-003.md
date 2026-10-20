# BK-456 — Spec 003 is too long to keep free of contradictions, so it is split
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The maintainer, during PR #1159 (BK-449): spec 003
is "much too long to be maintained and kept correct with no inconsistencies and
contradictions". The scope and shape below are the maintainer's choices,
recorded in `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl` ("When
should spec 003 be split?": "Separate PR after BK-449"; "Which split shape
should the work follow?": "By layer, 4 files").

**Section sizes.** Not kept current here, since every edit to the spec moves
them (the dated figures below are a measurement, not a reference):
re-run `rg -n '^##+ ' sdd/specs/003-backend-adapter-contract.md` before
planning and take each section's size as the gap to the next heading. At
PR #1159 the four largest were BE-021 Error Mapping, BE-029 Root Path, BE-032
The Store Tree on the Kernel and BE-033 Interaction Protocol on the Kernel,
then BE-030, BE-008 and BE-031; the CAP- sections and most BE- operation
sections are short.

**The ripple.** `git grep -l "003-backend-adapter-contract"` outside
`sdd/decisions`, `sdd/traces` and `sdd/research` names the files that cite the
spec: specs, RFCs, ADRs, the custom-backend guide, `scripts/gen_graph.py` and
`scripts/gen_protocol_diagram.py`, `src/` modules and
`docs-src/_data/graph/graph.json`. `git grep -l
"003-backend-adapter-contract.md#"` narrows them to anchored links. Run both
before planning: the split must move every anchor a section takes with it.

**Order.** After the status-out step below (which needs no ADR), BK-457's ADR
first (the maintainer's choice, same decision log: "ADR first, then BK-456"),
then this split, then a prune of each new file against that ADR.

**Spec 003 measured against RFC-0022, 2026-10-18** (PR #1160, at master
`32a5653`). The four largest sections held 1,417 of the file's 2,197 lines
(heading-to-heading gaps, Python regex `^#{2,3} `, the last section closed at
`wc -l`). Backlog IDs occur 84 times, 38 distinct (`\b(?:BK|BUG|ID)-\d+`);
"not yet" occurs 10 times case-sensitive, 11 ignoring case. An agent's
line-range classification, not re-derivable by a command, put these ranges in
history, measurement and coverage narrative ("Known divergences … what ships
today", test tallies, "this clause used to …"): BE-021 lines 941 to 1037 and
1061 to 1216, BE-029 lines 139 to 157, 193 to 217, 295 to 339 and 386 to 426.
It put these in prescribed mechanism (named helpers, call order, probe
sequences): lines 219 to 232, 289 to 293, 489 to 513, 670, 789 to 835, 1262 to
1270, 1613 to 1641 and 1869 to 1951. The contradictions found are BUG-337.

**Prescription** (advisory):

- **Status out first, before the ADR.** Moving project status, history and
  measurement out of the spec into the owning dossiers and traces needs no
  new rule (`CONTENT-RULES.md` Rules 1 and 4 already ask it), shrinks what
  the split moves, and keeps the split PR a pure move. One PR, no clause
  reworded; what leaves names its new home.
- **Split by kind.** The maintainer's answer of 2026-10-19 (decision log
  `sdd/decisions/d8d56944-7c57-56f1-9c46-bc7c6222fa45.jsonl`; ADR-0048): by
  kind of truth, interface contracts as the second cut. It replaced a
  four-file layer split.
- Move only in the split PR, then the prune against `SPEC-DESIGN.md`, a file
  per PR.

**Left for the prune** (stage one removed IDs, "yet" and status blocks, not
these): coverage-status sentences in spec 003, by
`rg -n 'no conformance fixture|fixture arranges|no cell|close-failure row'`
on the spec at PR #1168's review: BE-029's absent-container order (two), BE-029's
write roster, and BE-033's **Conformance** exceptions and its `Session` and
driver rows. Each carries reasoning, so removing it rewords a clause. The
split adds these, each a rewording a move may not make: 003's Overview still
says every operation, error condition and capability is defined there; 052's
and 053's Assumptions lift nothing out of the sections (BE-028's native-client
reliance is environment); and the mixed sections § Stage two names, BE-029 and BE-021 with
function-shaped parts, BE-030 to BE-032 with driver duties and a pipeline order.

**One obligation reworded, deliberately.** BE-021's no-page-boundary licence
said its residue "MUST then be stated as a divergence", and the list it was
stated in left the spec. It now reads "MUST then be stated in that backend's
spec as a declared variation": the maintainer's choice in this session's
decision log ("Where does the statement go now?": "The backend's own spec").
No backend spec states such a residue at this change
(`rg -n -i 'no page boundary|truncated page|first-page bound' sdd/specs --glob '!003-*'`).

## Stage two: the cut, 2026-10-20

The maintainer's choices, decision log
`sdd/decisions/c7fc25a1-86c3-542e-a8f0-b02e630d3fd3.jsonl`, re-derived from
each section's witness shape (`SPEC-DESIGN.md` Rule 2):

| File | Sections | Kind |
| --- | --- | --- |
| [003](../specs/003-backend-adapter-contract.md) | CAP-001 to CAP-007, BE-001 to BE-019, BE-021 to BE-027, BE-029 | single call, at the Backend interface |
| [052](../specs/052-backend-lifetime.md) | BE-020, BE-028, BE-033 | lifetime |
| [053](../specs/053-contract-kernel.md) | § Contract kernel, BE-030 to BE-032 | single call, at the Backend interface of a class on the kernel, with the driver duties at the kernel-to-driver interface |

- The orient candidate called BE-021, BE-029 and BE-032's encoding function
  clauses. Most of their witnesses need a state and a call, so they are
  single-call clauses: only BE-029's root predicate and BE-021's never-leak
  mapping are function-shaped. Moving BE-021 and BE-029 to files of their own
  would cut inside one kind by subject, not by interface, so they stay in 003
  and shrink in the prune.
- 003 also keeps sections of other kinds, for the prune to place: CAP-001 to
  CAP-006 (structure and function), BE-001 to BE-003 (structure), BE-023 and
  BE-025 (function, which spec 010's NPR sections also state) and BE-027
  (tooling metadata, which no call can fail).
- BE-028 goes with the lifetime clauses: a breach is an interleaving of calls
  on one instance. Only its reliance on native clients is environment.
- The kernel file does not split further.
- Three sentences that said "this spec" and meant 003 now link to it; the
  kernel intro's also drops "other", since no clause left in 003 is a kernel
  clause. That is the one class of edit besides link targets.
  `sdd/research/bk-456-split/check_move.py` proves the rest byte-identical.

**Stage three's plan** is
[audit 024](../audits/audit-024-spec-003-052-053-design.md): what each file
fails, what must survive, and the decisions to take first. Its process gaps are
BK-465, BK-466 and BK-467; the rest stays under this item.

## Moved out of spec 003, 2026-10-19

Verbatim from `sdd/specs/003-backend-adapter-contract.md` at master
`35ea366`, links re-based to this directory, by BK-456's first stage: the
text stated project state, which a spec does not carry
([`SPEC-DESIGN.md` Rule 7](../SPEC-DESIGN.md#no-project-state)). A dated
record, not kept current.

### BUG-259

BE-021, the write-to-root tally:

> **The write-to-root rule is a different count and every class now meets it.**
> Of the same thirteen, **two** have no `WRITE` capability and are not bound
> (`ReadOnlyHttpBackend`, `SQLQueryBackend`). The other eleven split by *which
> half* they already met, and the split differs between the two halves — which is
> itself the finding, since a class compliant on the writers was not thereby
> compliant on the destination:
>
> | | Refused it definitionally already | Refused it, but by observation | Did not refuse it |
> |---|---|---|---|
> | **The three writers** | `LocalBackend`, `MemoryBackend`, `AsyncMemoryBackend`, `SQLBlobBackend`, `GraphBackend` — 5 | — | `SFTPBackend`, `S3Backend`, `S3PyArrowBackend`, `S3Boto3Backend`, `AzureBackend`, `AsyncAzureBackend` — 6 |
> | **The `move`/`copy` destination** | `MemoryBackend`, `AsyncMemoryBackend`, `SQLBlobBackend` — 3 | `LocalBackend`, `SFTPBackend` — 2 | `S3Backend`, `S3PyArrowBackend`, `S3Boto3Backend`, `AzureBackend`, `AsyncAzureBackend`, `GraphBackend` — 6 |
>
> `LocalBackend`'s writers are in the first column because BUG-247 put them there;
> an earlier draft of this table had them under observation, which described the
> tree *before* that item rather than the one this clause ships in.
>
> The middle column is why the destination fix is not smaller. Those two classes
> answered correctly, and answered by looking — an is-a-directory probe on a
> container that was present. Neither of the two states this clause is about (an
> absent container; a flat namespace with nothing to observe) leaves that probe
> anything to see. All eleven now decide both halves from the key.
>
> Only two classes could destroy anything: `SFTPBackend` on the writers, and
> `S3Boto3Backend` on the destination — the latter answered a `move` to the root
> destination by returning cleanly and **deleting the source**. The rest reached
> their SDK and answered with the wrong class, which breaches the paragraphs at the
> head of this clause rather than this row.
>
> `GraphBackend` is the instructive row: it decided the writers definitionally,
> under more spellings than anything else here, and was still in the last column
> for the destination — and its root check ran ahead of its own closed-backend
> guard, so a closed store answered "cannot write to the drive root" instead of
> "backend is closed". Compliance on one half of a clause is not evidence about the
> other.
>
> Coverage is **not** uniform, and the shortfall is fixtures rather than rule. The
> cells this clause added collect **266** and execute **188**; the **78** skips are
> unrecorded replay cassettes (the Azure sync, Azure async and Graph lanes),
> backends that do not declare the capability under test, and the PyArrow lane,
> which needs the MinIO fixture on current PyArrow. The backends those skips cover
> were each measured directly instead — `S3PyArrowBackend` and `AzureBackend`
> against an unreachable endpoint, where an `InvalidPath` naming the root proves
> the guard ran before the transport; `AsyncAzureBackend` with the guard stubbed
> out, to establish what it did before; and `GraphBackend` against an unreachable
> endpoint for both halves.
>
> `GraphBackend` is the class where the two halves of that split are clearest, and
> the split is per-cell rather than per-backend. Its lane skips both new rosters,
> because those seed through `write` and so need a cassette — hence the cells
> fencing its source and destination guards live in `tests/backends/graph/aio/`,
> where they need no recording since those guards refuse before a request exists.
> One destination cell does reach it within conformance: BE-018's
> root-destination carve-out cell, which seeds nothing (BK-388). It measures the
> guard without fencing it: with the guard removed the call reaches an
> unrecorded request and the cell skips, so the per-backend cells stay the fence.
> Its **closed-guard ordering is pinned within conformance**, by the `aio/` twin of
> the close-posture cell: that one never seeds, so the Graph lane executes it, and
> it is the cell that caught the ordering breach in the first place. A cassette-less
> lane is not an unpinnable one; what it cannot host is a cell that seeds.

### BUG-246, BUG-247, BUG-249

BE-021 § Known divergences, its preamble:

> **Known divergences, stated rather than implied.** These are what ships today,
> recorded so a reader does not mistake an obligation for a description, and
> tracked in the backlog. They are scoped to the whole absent-container question
> rather than to the two deletes alone: the Reach paragraph rules that the other
> operations keep obligations this clause did not write, and a divergence from one
> of *those* is no less real for having been written down elsewhere. Listing them
> here is what makes the container case answerable from one place.

BE-021 § Known divergences, the departed bullets:

> Four bullets have left this list and are recorded rather than deleted, because
> each was a *measured* divergence and the measurement is what a later reader
> needs in order to trust the entries that remain:
>
> - `LocalBackend` answered **every** operation with
>   `InvalidPath("Path escapes root directory")` once its root directory was
>   deleted, including both tolerant deletes: the containment check walked up to
>   the deepest existing ancestor, which is above the root once the root is gone,
>   so absence was misreported as an escape. It was the furthest from the clause
>   any backend sat, and the only one where the error type actively misled. The
>   walk now stops at the root, which brings the whole surface to the clause at
>   once — the tolerant deletes return, the strict ones and the reads raise
>   `NotFound`, the probes answer `False`, the listings are empty. The store root
>   itself is decided by BE-029 rather than by this clause, and now meets that
>   row too (BUG-247).
> - `exists()` and `is_folder()` raised `NotFound` against an absent container on
>   `S3Boto3Backend`, `AzureBackend` and `AsyncAzureBackend`, where the strict
>   prefix probe was reached after the tolerant HEAD came back empty. All three now
>   answer `False`, as `S3Backend` and `S3PyArrowBackend` already did (BUG-246).
> - `S3Boto3Backend`'s `list_files`, `list_folders` and `iter_children` raised a
>   raw `botocore.exceptions.ClientError`, breaching the never-leak invariant at
>   the top of this section rather than the mapping row: they were the only methods
>   on that class whose wire call was not wrapped in its error mapper, against
>   fifteen methods that do wrap. All three now return an empty listing, as the two s3fs-backed
>   lanes already did against the identical response (BUG-249).
> - On `SQLBlobBackend`, **every operation except the two deletes** answered an
>   absent table with `BackendUnavailable` (or the base error, by dialect), because
>   they mapped the driver's complaint without asking whether the table was still
>   there. It was the widest divergence this list ever held by operation count —
>   fourteen operations, measured against a dropped SQLite table, of which thirteen
>   owed a different answer — **counting `move` and `copy` separately here**, which
>   is the opposite of the roster paragraph's frame above and is why fourteen and
>   twelve can both be right about the same backend. Each of the thirteen now takes the answer § Reach
>   gives it or its named sibling: `exists`, `is_file` and `is_folder` answer
>   `False`; `read`, `read_bytes`, `get_file_info`, the `move`/`copy` source and
>   `get_folder_info` **below the root** raise `NotFound`, while the root
>   aggregates to an empty store under BE-029; `list_files`, `list_folders`,
>   `iter_children` and `glob` come back empty. Three of those thirteen —
>   `read_bytes`, `iter_children` and `glob` — are siblings § Reach does not name,
>   per the roster paragraph above. `read_seekable` is not among them: this backend
>   does not override it, so it is not a distinct operation here. The same split showed on a disposed in-memory engine, where disposal
>   destroys the database rather than releasing a connection to it — one divergence
>   with two ways in, closed by the same change, and the reclassification
>   deliberately does not try to tell them apart; see
>   [SQL-BLOB-050](../specs/040-sql-blob-backend.md#sql-blob-050-exception-translation).
>   **`write` keeps `BackendUnavailable`** and is not a residue: it is the one
>   roster operation § Reach declines to decide, so a backend answering it its own
>   way contradicts nothing here (BUG-246).

### BUG-248

BE-021 § Known divergences, the Graph bullet and the list's count:

> `GraphBackend` was a bullet too, adjudicated by
> [ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md). Counting
> bullets rather than backend classes — one of the two frames `sdd/BACKLOG.md` § 1
> uses, and the one it counts this list in — **this list holds three live bullets
> today**: two of the first-page bound, `S3Backend`/`S3PyArrowBackend` and
> `GraphBackend`, and `LocalBackend`'s recursive walks. Four are recorded above as
> having left, the most recent
> being `LocalBackend` (BUG-247) — first in that list by position, last by date,
> and the last of the original entries still standing. The two first-page bullets
> are both *newer* than the list they joined: the
> first-page bound BUG-246 wrote into § Reach made them breaches of a clause they
> were outside of before. A list of divergences grows when its clause does, not
> only when a backend regresses — and this one has now turned over completely,
> every original entry closed.
> [GR-031](../specs/044-graph-backend.md#gr-031-404-discrimination-item-vs-drive) mapped
> `404 resourceNotFound` to `BackendUnavailable` for every error-raising
> operation, deliberately, on the grounds that a deleted drive is a backend
> identity failure rather than a per-item condition — and a drive is a container,
> so two clauses of this repository's own specs gave opposite answers for the same
> call. The divergence was recorded as reaching the two tolerant deletes; measured
> across every operation it reached **eleven** of the ones named above, plus
> `read_bytes` and `iter_children`.
> [ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md) adjudicated
> it in favour of this clause for every operation this clause decides. GR-031 keeps
> what it does not: `write`, the one roster operation § Reach declines; and, off
> the roster entirely, `check_health`, Graph's drive-id resolution and its
> copy/move monitor poller.

BE-021, the two sentences of the roster paragraph that counted against it:

> (The Graph paragraph below says
> GR-031 reached "eleven of the ones named above" and kept `write`; eleven plus
> `write` is the same twelve.)

> But that is a *reading*, and it is the reading
> this section elsewhere makes explicit when it counts Graph's divergence as
> "eleven of the ones named above, plus `read_bytes` and `iter_children`".

### BUG-243

BE-021, the two false premises:

> **Two earlier premises for the rule were false, and both are recorded rather
> than quietly dropped** — each was asserted from a reading and disproved by a
> run, which is the argument for the rule being stated as an obligation rather
> than inferred from what backends happened to do.
>
> The first was that the hierarchical backends had already settled it, because on
> Local an absent store root is just an absent path. It was not: with its root
> deleted, `LocalBackend` raised `InvalidPath("Path escapes root directory")` from
> the containment check, before either delete's `missing_ok` branch was reached. It
> was a divergence from this clause, not evidence for it, and it went unnoticed
> because both deletes look correct in isolation — the guard that fired was two
> lines upstream in `_resolve`. BUG-247 has since made the premise true, which does
> not make the reasoning sound: it was asserted from a reading, and what settled it
> either way was running it.
>
> The second was that the rule merely ratified what `delete` already did on every
> flat-namespace backend, correcting only its sibling. That holds for the S3 and
> Azure family, whose bodyless `HeadObject` 404 cannot name the bucket, and it is
> where the reported symptom came from. It does not hold for `SQLBlobBackend`,
> which is flat-namespace by this spec's own classification and whose `delete` was
> measured raising `BackendUnavailable` against a dropped table before this
> change, exactly as its sibling did — that is the state *before BUG-243*, which
> is the change this paragraph is about, and not the state the departed bullet
> above describes, which is after it. The rule therefore changes `delete` on one
> backend rather than ratifying it everywhere. Both are recorded above, among the
> four bullets that have left this list; the
> premise survived six review rounds because "the S3 family" and "the
> flat-namespace backends" were used interchangeably by a clause whose whole
> purpose is to bind the second set.
