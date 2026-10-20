# Audit 024 — Specs 003, 052 and 053 against SPEC-DESIGN.md

**Date:** 2026-10-20

**Motivation:** BK-456 split spec 003 by kind of truth as a pure move (stage
two, PR #1169), so no clause was reworded. Stage three prunes each file
against [`SPEC-DESIGN.md`](../SPEC-DESIGN.md). This audit is that prune's
plan: what in each file fails which rule, what must survive, and what needs a
decision before any clause is reworded.

**Scope:** `sdd/specs/003-backend-adapter-contract.md`,
`052-backend-lifetime.md` and `053-contract-kernel.md` at `cf75f0c`, the head of
PR #1169 before its last skeleton fixes. Every line number below refers to
that commit. Read against `SPEC-DESIGN.md` Rules 1 to 8, § Ready and § Review
checklist, ADR-0048, the neighbouring specs each finding names, `sdd/formal/`
and `src/`.

**Excluded, already filed:** the leftovers in BK-456's dossier, § Left for the
prune; findings that touch one cite it.

**Method:** three read-only passes, one per file, each by a separate reader
with no brief beyond the rules. Each figure names its command in the appendix
that states it. Findings marked ✓ were confirmed by running code or reading
`src/`; the rest are readings of the text. Severity: blocks Ready, should fix,
optional.

**Verdict:** none of the three files is Ready. Each fails Ready items 1 (form,
mechanism), 4 (project state, assumptions) and 5; 003 also fails item 2
(CAP-007 carries no spec mark), and 052 and 053 fail item 3 (content left
undecided).

## 1. Findings against PR #1169's own text

Seven findings fell on text the split itself wrote, the new files' skeletons
and the dossier, not on moved sections. PR #1169 fixed them before merge: 053's
Overview named one interface where the spec holds two; the kernel intro's
retargeted "other clauses of spec 003"; 052's Terms (`Session`, closed guard,
live operation, condemned); both Notes sections; 053's Tested against
(`RootPath.dfy`, runnable commands); 052's out-of-scope owners; and the
dossier's list of other-kind sections left in 003.

## 2. Decisions the prune needs first (cross-file)

1. **Assumption ID format.** The template's `<PREFIX>-A01` fails `check_spec_marks._SPEC_ID` (`BE-A01` False, `BE-A-01` True), so a template-form row is never declared and a mark citing it is silently unfound. A `BE-` prefix would also collide across 003/052/053. Fix the template or the regex, and pick prefixes.
2. **A home for "design note".** Rule 1 relocates mechanism to "an ADR, a design note or the task's plan"; no design-note home exists (`AUTHORING.md`, `000-process.md`). All three prunes need it.
3. **Rule 4 vs the repo's models.** Lifetime is TLA+-only in Rule 4, but 052's lifetime model is Dafny (`KernelProtocol.dfy`), so it can never govern BE-033. `check_formal_trace.py` reads only `tests/backends/conformance/` marks, so no `@spec BE-03x` tag can exist for kernel clauses (none of the 88 test lines marking BE-030, BE-031 or BE-032 is a conformance cell: `rg -c 'spec("BE-03[0-2]"' tests`). Amend Rule 4 and/or the trace check, or note both limits in BK-463.
4. **Profiles with no declaration in code** (Rule 5): namespace off the kernel (only `fixtures.toml`); concurrency posture (only `backends.toml`; varies by configuration per SQL-BLOB-072, HTTP-CONC-001); `links` / store link policy (BE-032 A.7, not in code at all; BK-433); who runs WR-010's gate. Each: add a declaration, or amend Rule 5, or narrow the clause.
5. **Driver-duty home.** Duties are scattered across 053 (five construction-refusal sites, A.8's "each stated once here" is false) and 003 BE-021's table (four duties 053 never states, one citing a nonexistent A.7). One 053 section, or a driver-interface spec — the latter revisits stage two's "does not split further".
6. **Further kind cuts of 003** (the 003 audit, by Rule 2, not by size): a declarations spec (CAP-001–006 taxonomy, BE-001–003, the Rule 5 profiles); BE-023/025 and BE-029's predicate into 010 (which already states the same functions); BE-027 to 001 or tooling docs. After pruning, 003 is estimated at 450–550 lines.
7. **ADRs to draft at prune time:** close and concurrency postures declared per backend (052); root-ness from the key by one predicate (003 BE-029/BE-008); absent-container scope and error-path-only probe (003 BE-021; ADR-0038 amendment or new). Kernel mechanism can go to ADR-0042 or the design-note home.

## 3. Contradictions (each needs a choice of which side is wrong)

Confirmed by running code or reading `src/` are marked ✓.

| Where | Contradiction | Sev. |
| --- | --- | --- |
| 003 CAP-007 l.62 vs WR-010 ✓ | Gate claimed on a backend; `LocalBackend.write(..., metadata=…)` without USER_METADATA raises nothing; WR-010 puts it on `Store.write*()` | blocks |
| 003 BE-005 vs BE-029 ✓ | "Root is always a folder" unscoped; `ReadOnlyHttpBackend.is_folder` always False | blocks |
| 003 BE-021 internal | "regardless of backend" vs hierarchical-only write half; unscoped NotFound row vs probes/listings/tolerant deletes; broad-handler "ONLY" vs empty listings; l.828 stale "BE-012 … hierarchical" | blocks |
| 003 vs 029 ASYNC-008/018/019 | dst-directory scope; self-move/copy no-op carve-out missing in 029 | blocks |
| 052 BE-028 | "each operation atomic" vs CAP-007, S3-028, ASYNC-091; SQL "thread_safe" vs SQL-BLOB-072, SQL-QUERY-092, `backends.toml`; "documented thread-safe" vs S3PA-028; posture varies by configuration | blocks |
| 052 BE-020 vs ASYNC-083 ✓ | `AsyncBackendSyncAdapter` inherits `close_is_terminal = False` yet raises `RuntimeError` after close | blocks |
| 052 BE-033 Refusal timing ✓ | Names a read handle that does not exist (BK-454); `AsyncStore.read` returns `AsyncIterator`; `test_protocol.py:225-236` pins the opposite | blocks |
| 052 BE-033 Session rows | Bind a component that does not exist (BK-455) | blocks |
| 053 A.6 vs RFC-0021 OQ1 | "flat cannot hold an empty folder" vs `a/` marker making `is_folder` True; carve-out "not decided here" | blocks |
| 053 A.7 vs code ✓ | `links`, `follow_within_root`, `no_follow` declared nowhere in `src/` or tests | blocks |
| 003 BE-029 vs PATH-008 ✓ | `RemotePath('./')` raises, not normalises to the root | should |
| 003 BE-029/025 vs `BackendContract.dfy` NativePath | bare root vs `root + "/."` | should |
| 052 BE-020 rosters vs code ✓ | `AsyncAzureBackend` (terminal), `AsyncMemoryBackend` missing | should |
| 003 BE-008/BE-025 lists vs code ✓ | `S3Boto3Backend` kwarg and `native_path` override missing; two strict fixtures missing; `ReadOnlyHttpBackend.native_path` missing | should |
| Capability gate vs closed guard off the kernel | Ranked on the kernel, never stated for other classes (Ready 3) | should |

## 4. Double homes (one fact, several specs)

Closed-guard precedence (five homes); `unwrap` closed guard (003, 052, 053); construct refusal on `close_is_terminal` (052, 053); metadata-gate rank on the kernel (003 BE-008, 053 BE-030); never-leak (003 BE-021, 005); `to_key` / `native_path` (003, 010); CAP-007 flag meanings (006, 036, 045); SIO-010's release (052, 006); 20 "On the kernel" lines in 003 vs 053; BE-021's kernel/driver table (003) vs 053.

## 5. Proposed order

Merged from the three audits' own orders:
1. **Process first** (one PR): Assumption ID format, design-note home, Rule 4 / trace-check limits (§ 2 items 1–3).
2. **Decisions** (one dialog per file, or backlog items): the § 3 contradictions, the profiles (§ 2.4), the driver-duty home (§ 2.5), the further 003 cuts (§ 2.6).
3. **052 prune** (smallest): relocations to a new posture ADR and `formal/README.md`; skeleton; BE-033 split per invariant with re-marked tests and anchors.
4. **053 prune:** skeleton and project state; Assumptions KERN-A01–A08; one home per fact; pipeline → precedence table; one invariant per section with A.n mapped.
5. **003:** the kind cut (a move), then skeleton/state, BE-029, BE-021 (with § Reach its own ID), BE-008 and the operations — six PRs by the 003 audit.

## Appendix A: spec 003

Report only, at `cf75f0c`. Not Ready: every Ready item but 3 fails somewhere. Largest problems: Rule 5 (implied per-backend profiles), Rule 6 (no Terms/Assumptions/Notes/Tested against), Rule 7 (test paths, measured counts, stale lists), Rule 1 (BE-029 and BE-021 mostly mechanism and history). Eight new contradictions, three confirmed by running code or reading `src/`. BK-456 dossier leftovers marked **(bk-456 leftover)**. Severity: **[blocks Ready]**, **[should fix]**, **[optional]**.

### Figures
- 1,067 lines (`wc -l`). Heading gaps (`^#{2,3} `): BE-029 316 (91–406), BE-021 312 (700–1011), BE-008 131 (418–548) = 759 of 1,067; then BE-014 28, BE-018 25, BE-019 23, BE-027 20.
- Top-level headings only Overview, Capabilities, Backend ABC.
- Spec marks (scan of `tests/**/*.py`): CAP-007 **0**; BE-001, BE-023, BE-027 exactly 1; BE-021 212; BE-029 92.
- Model tags (`sdd/formal/*.dfy` `@spec`): 16 sections tagged; none for BE-010, BE-023, BE-025, CAP-* except CAP-004.

| Line kind | Count | Lines |
| --- | --- | --- |
| `**Formal coverage:**` | 8 | 521, 559, 596, 621, 633, 650, 671, 694 |
| `**Conformance:**` / invariant | 3 | 80, 380, 987 |
| `tests/` paths | 9 | 80, 166, 204, 380, 544, 546, 650, 987, 1065 |
| Backend class names (excl. `*.dfy`) | 59 | BE-021 17, BE-008 14, BE-029 13, BE-025 9, BE-018 5, BE-003 1 |
| "measur…" | 8 | 274, 299, 325, 359, 464, 487, 656, 1028 |
| "On the kernel" | 20 | 10 sections |
| `**Example:**` | 3 | 21, 38, 1032 |
| Backlog IDs, "yet" | 0 | — |

- Inbound anchored links (`git grep -o "003-backend-adapter-contract\.md#…"`): 14 — `#be-021-error-mapping` 7, `#be-029-root-path` 3, `#be-008-write` 2, `#be-025-native_path` 2.
- "§ Reach" / "An absent container reads as an absent path" cited by name in ADR-0038, ADR-0042, RFC-0017, specs 029, 040, 044 and eight `src/` files (`_kernel/_sync/kernel.py`, `_kernel/_async/kernel.py`, `aio/backends/_graph/backend.py`, `aio/backends/_graph/http.py`, `backends/_azure.py`, `_flat_ns.py`, `_s3_boto3.py`, `_sqlalchemy.py`).

### Cross-cutting

#### Rule 6: skeleton [blocks Ready]
Missing Terms, Assumptions, Notes, Tested against. Overview l.5 **(bk-456 leftover)**, plus "the most critical spec in the system" (cannot fail). Undefined or double-sense terms: path/key (004 and ERR-005 mean `RemotePath`; 003 a raw key); root, root spelling, store root; container; flat/hierarchical; file-/folder-shaped; roster (two sets, l.927–932); determinant, error path, probe; class on the kernel (053); quality flag, strict gate; backend (does 003 bind `AsyncBackend`? it names async classes and "async mirror" while 029 owns async). Tested against should name `BackendContract.dfy`, `RootPath.dfy`, `MemoryBackend.dfy`, the compiled oracle, `tests/backends/conformance/`, `tests/_kernel/`, replacing the 8 Formal coverage and 3 Conformance paragraphs.

#### Rule 4 [should fix]
No `formal/README.md` heading states Rule 8's six items ("### Compiled oracle as conformance gate", l.514, does not list them), so prose governs every section. Formal coverage paragraphs restate model postconditions: a second home (Rule 7), e.g. l.718.

#### Rule 5: implied profiles [blocks Ready]

| Implied behaviour | Where | Declared today | Proposal |
| --- | --- | --- | --- |
| Flat vs hierarchical namespace | BE-008 l.474–477; BE-018 l.655; BE-021 l.724–727, 753–762; BE-013 l.584; BE-029 l.136, 285–287 | only `driver.namespace` on the kernel (`_kernel/_sync/kernel.py:307`); else `fixtures.toml` `flat_namespace`; Azure HNS per account | profile `namespace: flat \| hierarchical`, per instance, outcomes in the clause |
| Who runs WR-010's gate | BE-008 l.422, 429–434 | nothing | declare a profile, or move the gate wholly to Store (045 l.280) |
| Atomic move | BE-018 l.664–670 | `ATOMIC_MOVE` | state against `ATOMIC_MOVE` |
| Container can be absent | BE-021 l.962–972; BE-029 l.146–151 | kernel `container_absent` | profile or Assumption |
| Root as addressable node (MAY/MUST) | BE-029 l.126–151 | nothing | remove: root answers hold with or without the container |
| Listing with no page boundary | BE-021 l.886–891 | nothing | named profile |
| Listings that follow links | BE-021 l.1009–1010 | nothing | named profile |
| `LAZY_READ` / `WRITE_RESULT_NATIVE` examples | CAP-007 l.57, 58 | declared | drop examples |
| File-ancestor opt-in | BE-008 l.480–499 | `reject_write_under_file_ancestor` flag | the flag as profile; drop stale lists |

Proposed Assumptions: A01 a container can vanish outside the library at any time, incl. mid-listing; A02 SDK errors are distinguishable by type/errno/status; A03 transient probe failures carry no type verdict; A04 outside writers can act between a start-of-call check and the data plane; A05 native rename is atomic where `ATOMIC_MOVE` is declared; A06 Python's `abc` refuses an incomplete subclass. Azure HNS `hdi_isfolder` (BE-008 l.505–511) belongs in 012; duplicated in 029 l.60.

#### Rule 7 [blocks Ready]
Beyond leftovers (BE-029 l.161–167, 286–288, 391–405):
- Test locations: l.80, 198–205, 380–385, 491–498, 544–547, 650, 656, 987–988, 1065.
- Counts: l.452–458 "Seven of the eleven" (true at HEAD by `_reject_root_as_file` callers, but moves with code); l.464–469 measured values; l.656.
- **Stale, verified:** BE-008 l.482–483 omits `S3Boto3Backend` (`_s3_boto3.py:239` has the kwarg); BE-008 l.492–497 names five strict fixtures, `fixtures.toml` has seven (`tomllib`; missing `s3_boto3_moto_strict`, `s3_pyarrow_minio_strict`); BE-025 l.1031 omits `S3Boto3Backend`, `ReadOnlyHttpBackend` (`def native_path\(`).
- History: l.146–151, 206–211, 213–219, 224–225, 260–262, 297–302, 304–305, 325–326, 352–360, 656, 756–759, 934–944, 971–972, 974–977.

#### Rule 3 [blocks Ready for every section a prune touches]
Six tables (l.107, 198, 707, 740, 780, 1053), none in State | Result | Raises form. BE-008 states precedence as step order, which Rule 1 forbids. Examples (l.21, 38, 1032) go to tests.

#### "On the kernel" second homes [should fix]
20 lines in 10 sections plus BE-021's placement table (l.735–751). `unwrap` closed guard in 003 BE-022 l.1016, 052 l.126, 053 l.54. BE-017 l.649 `modified_at` only in 003 (not in 053), and "Backends not on the kernel are outside this sentence" leaves it undecided for the rest (Ready 3).

#### Process gap [should fix]
No design-note home (`design note|sdd/design` absent from AUTHORING.md). Implementer advice can go to `docs-src/guides/custom-backend-guide.md`; rationale with alternatives to ADRs.

### Per section

#### CAP-001 to CAP-006 [blocks Ready, Rule 2]
CAP-001 structure; CAP-002–005 function (CAP-004 total with error output); CAP-006 lifetime as written, structure if restated "no mutating member" (recommended). None is a Backend-interface call: they leave 003. Examples to tests.

#### CAP-007
- **[blocks Ready]** 0 marks; `scripts/check_spec_marks.py:224` exempts it ("design principle"), but its clauses can fail (a backend without `SEEKABLE_READ` still serves `read_seekable`), and flag meanings are tested under SIO-008, SIO-009 (`test_streaming.py:134, 38`), SEEK-001 (`test_identity.py:275`).
- **[should fix]** One home: `SEEKABLE_READ` (CAP-007, SIO-008, SEEK-001), `LAZY_READ` (SIO-009), `WRITE_RESULT_NATIVE` (WR-004), `USER_METADATA` (WR-010).
- **[blocks Ready] confirmed by running:** l.62 says passing `metadata=` to a backend without the capability raises before I/O; `LocalBackend.write('f.txt', b'x', metadata={'k':'v'})` returns `WriteResult(..., metadata=None)` and raises nothing, matching BE-008 l.432–434 and WR-010 (`Store.write*()`). CAP-007 is the wrong side, and omits the empty-mapping carve-out.
- Rule 1: l.55, 57 caller advice → user docs. `ATOMIC_MOVE`'s meaning is lifetime (interleaving) → 052.

#### BE-001 to BE-003 [should fix, Rule 2]
Structure. BE-001 fails only through `abc` (A06) [optional]; BE-002 "unique" across what [optional]; BE-003 l.78 rationale, l.80 project state; the ⊆ invariant stays.

#### BE-004 to BE-007
**[blocks Ready] confirmed in code:** BE-005 l.89 "the store root … is always a folder" unscoped; BE-029 l.93 scopes it to `LIST`; `ReadOnlyHttpBackend` declares `READ`, `METADATA`, `LAZY_READ` (`_http.py:43`) and `is_folder` always returns False (`_http.py:294–296`). Justification clauses (l.88) [optional]. All need outcome tables.

#### BE-029 (l.91–406)
Kinds: root predicate (l.290–292) function, proved `AddressesRoot(s) <==> RootSpelling(s)` (`RootPath.dfy:75–76`) **(bk-456 leftover)**; table, file-shaped refusal, write refusal, BE-020 precedence single call; l.153–159 health-check clause → spec 026.

Load-bearing: LIST-only scope as profile (l.93, first and last sentence); table (l.107–115); file-shaped roster (l.120–123); root answers hold with or without the container (l.141–151's conclusion); closed outranks every root answer but addressing (l.169–184), restated as precedence; `to_key(native_path("."))` is `""` (l.249–252, home BE-025); root-addressed writers and destination refused before transfer under every predicate spelling (l.257–259, 290–292, 350–351); one key addresses one node across operations (l.323–324); backslash-only key not a root spelling (l.314); `delete_folder("")` out of scope, STORE-002 (l.364–369).

| Lines | Quote (abridged) | Fails | Destination |
| --- | --- | --- | --- |
| 95–101 | "ReadOnlyHttpBackend, for instance …" | narrative, rationale | ADR |
| 126–139 | "MAY hand the root to its SDK … MUST decide from the key" | algorithm | guide; keep outcome |
| 141–151 | "LocalBackend took the MAY …" | history | dossier |
| 186–193 | "Do not restate that carve-out …" | author instruction, history | ADR |
| 195–219 | three pre-checks table, helpers, cells, "None is hypothetical" | helpers, tests, history | test docstrings, dossier |
| 221–228 | `is_root`, `strip_root` | helpers | guide |
| 230–234 | "must short-circuit" | mechanism (keep outcome) | guide |
| 236–240 | "must answer False itself" | mechanism | guide |
| 242–247 | Layering | scope | Overview line |
| 253–255 | Graph/Memory fold | per-backend | BE-025 |
| 260–289 | "This clause used to …", measurements | history | dossier, tests |
| 293–294 | `_addressable_segments`, `_key_segments` | helpers | guide |
| 296–322 | backslash withdrawal, "first version … wrong" | history, rationale | ADR |
| 325–348 | "measured on GraphBackend", `is_root` call sites | history | ADR |
| 352–362 | "move(src, '.') … deleted the source" | history | dossier |
| 371–378 | On the kernel | second home | 053 |
| 380–405 | Conformance, `_ROOT_FILE_OPS`, write roster (leftover) | project state | tests |

l.169–177 is precedence phrased as step order; restate.
- **[should fix] confirmed by running:** l.273–274 "`./`, which RemotePath normalises to the root" vs PATH-008; `RemotePath('./')` raises `InvalidPath: Path is empty after normalization`. Same for `"\"` at l.297.
- **[should fix] model vs prose:** table's `native_path(".")` bare root vs `BackendContract.dfy:417–437` `NativePath(root, ".")` = `root + "/."`, `ToKey` "."; `NativePathRoundTrip` (l.1533, NPR-020) unconditional. Align the model or state its domain.

#### BE-008 (l.418–548)
Load-bearing: signature, raises; precedence table (closed, root, metadata gate on profile, type, ancestor, overwrite; refusal has no side effect); two-predicate floor (l.447–452, 459); flat exemption as profile; opt-in as profile with cost statement; start-of-call and fail-open (l.512–520), concurrency half A04.
Relocate: l.443–446 rationale; 452–458 tally; 461–473 measurement → dossier, rationale → ADR; 481–499 stale lists, research path, fixtures, `_acheck_no_file_ancestor`; 505–511 → 012; 521–547 → Tested against/Notes. l.539–542 "The model … is stricter" is a model/prose divergence: Note or resolve.
**[should fix] undecided precedence:** on the kernel capability gates outrank the closed guard (053 l.65–70; `tests/_kernel/test_kernel.py:1066–1074`); off the kernel never ranked; BE-010 l.557 "from the closed guard". Ready 3.

#### BE-009 to BE-019
- Formal coverage (BE-010 l.559, BE-014 l.596, BE-015 l.621, BE-016 l.633, BE-017 l.650, BE-018 l.671, BE-019 l.694) → Tested against/Notes; BE-014 l.602–612 model history → formal README.
- BE-010 l.555 "temporary file + atomic rename" mechanism; no-partial-path is lifetime, 007's.
- BE-012 l.578 "pinned in Python" project state.
- BE-018 l.656 `mkdir_parents`, `_check_no_file_ancestor` mechanism (precedence stays); l.664–668 SHOULD/document/caller advice → guide; clause becomes `ATOMIC_MOVE`.
- BE-019 l.691–692 advice; "MUST NOT silently return success" stays.
- BE-013 l.584 history; "MUST read it as no children" mechanism (outcome is BE-021's).

#### BE-021 (l.700–1011)
Kinds: never-leak single call; `classify` mapping function **(bk-456 leftover)**, owner 005 or 053; mid-listing 404 (l.869–876) lifetime + A01 → 052.
- **[should fix]** one home with 005 l.5.
- **[blocks Ready] contradictions inside 003:** (1) l.704–705 "regardless of backend" vs l.724–727 hierarchical only; (2) `NotFound` row (l.711) unscoped vs BE-004/005/014/015/026 and tolerant deletes; (3) broad-handler "ONLY" (l.993–998) vs empty listings and `missing_ok`, and mechanism; residue: no error mapped to a type its condition does not warrant; (4) l.828 "BE-012 already states for hierarchical backends" — BE-012 has no such scope.

Load-bearing: never-leak; table (scope corrected); type mismatch over `NotFound` (l.718) and over `missing_ok` (l.825–827); type-mismatch roster incl. `read_seekable` (l.720–727, 817); flat error-path obligation as per-profile cost (found target: no extra request; miss: at most one), replacing `MaxKeys=1`/HEAD; fail-open probe vs fail-closed determinant (l.796–807); absent container for both tolerant deletes (l.830–836); no extra round trip on a miss (l.838–843); § Reach answers (l.845–867), needs its own ID; mid-listing propagation (l.869–876, → lifetime); page bound (l.878–884); no-page-boundary licence as profile (l.886–891); BE-029 wins for root (l.893–910); narrow catch (l.946–950); listing denial scope (l.1000–1010).

| Lines | Quote | Fails | Destination |
| --- | --- | --- | --- |
| 735–751 | kernel/driver table | second home | 053 |
| 756–762 | "quietly optional … for a long time" | history | dossier |
| 768–774, 787–790 | kernel cost departures | second home | 053 BE-032 |
| 808–815 | "wraps it at the error-path call site" | mechanism | guide |
| 912–915, 927–932 | navigation meta-text | cannot fail | delete |
| 934–944 | HeadObject/ListObjectsV2 narrative | history, rationale | ADR |
| 952–960 | per-backend absent container | mechanism | 008, 012, 040 (SQL-BLOB-050) |
| 962–972 | class roster, "six review rounds" | state, history | profile, dossier |
| 974–979 | "Three criteria … were tried" | rationale | ADR |
| 981–985 | root before probe | duplicate of BE-029 | one home |
| 987–988 | Conformance | project state | — |

Rule 3: about 16 invariants (the load-bearing list); BE-021's anchor keeps never-leak and the table, so its 7 inbound links stay valid.

#### BE-022, BE-024, BE-026 [should fix]
BE-022 l.1016 triple-home `unwrap` guard. BE-024 l.1043, BE-026 l.1037 describe code structure; residues: no `GLOB` ⇒ `CapabilityNotSupported`; `iter_children` equals the union of both listings, non-recursive.

#### BE-023, BE-025 [blocks Ready, Rule 2]
Function ("Pure, deterministic, total", l.1022, 1029); 010 owns the same (NPR-003–005, NPR-020/021, 010 l.93–105): one home, 010. BE-025 l.1028 measurement, l.1031 stale Overrides, l.1032 Example.

#### BE-027 [blocks Ready, Rule 1]
Tooling metadata (`_BACKEND_GATING` in `scripts/gen_graph.py`); no black-box Backend test can fail it (only mark `tests/scripts/test_gen_graph.py:255`). l.1065 "enforcement … by Store._gate(), not by Backend" contradicted by BE-011, BE-024 (kernel tests; `_backend.py:479`). Table → 001 (STORE-006) if contract; sync rule → drift/ripple docs; ASYNC-045a moves with it.

### Contradictions with neighbours

| With | 003 | Neighbour | Severity |
| --- | --- | --- | --- |
| 029 ASYNC-008/018/019 | dst-directory `InvalidPath` binds hierarchical + kernel only | unscoped (AsyncAzure is flat) | blocks Ready |
| 029 ASYNC-018/019 | `AlreadyExists` only when `src != dst` | no self carve-out | blocks Ready |
| 029 ASYNC-013/016/017 | `InvalidPath` on type mismatch | omitted | should fix |
| 045 WR-010 | CAP-007 l.62 gate on "a backend" | gate on `Store.write*()` (code agrees) | blocks Ready |
| 004 PATH-008 | RemotePath normalises "./" to root | rejected | should fix |
| 005 | never-leak | same, 005 l.5 | should fix |
| 010 NPR-003–005, 020/021 | BE-023/025 | same functions | should fix |
| 006, 036, 045 | CAP-007 flags | SIO-008/009, SEEK-001, WR-004 | should fix |
| 052 / 053 | 20 kernel lines; unwrap guard | same facts | should fix |
| 053 l.65–70 | gate vs guard unranked off kernel | kernel ranks gate first | should fix |
| `BackendContract.dfy` NativePath | `native_path(".")` bare root | `root + "/."` | should fix |

No contradiction with 052's BE-020 posture (addressing is ghost functions, `BackendContract.dfy:417, 430`); 052 l.37's accessor mechanism should go rather than coexist with BE-029 l.186–191.

### ADR coverage
Needed at prune time, drafted in the PR that removes the text: (1) root-ness decided from the key by one predicate per backend; `is_root` not widened; backslash fold withdrawn; write end wider than source end (BE-029 l.296–348, BE-008 l.447–473). (2) absent-container scope "every backend", probe on the error path only (BE-021 l.934–944, 974–979): ADR-0038 amendment or new.

### Process guides
- SPEC-DESIGN.md accurate but for the design-note home.
- `check_spec_marks.py:224` exempts CAP-007 as "no runtime behavior", against Ready 2 and existing tests.
- Stage two's cut holds for BE-021/029, but § Stage two did not list four other-kind groups left in 003: CAP-001–006 (structure/function), BE-001–003 (structure), BE-023/025 (function), BE-027 (not contract).

### Must survive any prune
Precedence (closed, capability (to rank), root, metadata gate (profile), type, ancestor, overwrite; `src` NotFound over dst except a root dst, BE-018 l.656); no side effect on refusal; type mismatch over NotFound and `missing_ok`; § Reach answers and BE-029 winning the root; fail-open vs fail-closed; per-profile miss cost; mid-listing propagation, page bound; listing-denial scope; metadata preserved by move/copy; no silent success on failed copy/move; BE-003 ⊆; two-predicate floor; every BE-029 table answer.

### Size after a prune
Relocatable lines sum to 468 of 1,067 (Python sum over the ranges above; classification is judgement). Other-kind moves (CAP-001–006 l.13–47, BE-001–003 l.68–81, BE-023/025 l.1019–1034) ~70 more; skeleton +40; estimate 450–550 lines, ~60 one-invariant sections (BE-021 ~16, BE-029 ~9, BE-008 ~6). No further size cut; Rule 2 cuts instead:
1. Kind: a declarations spec (CAP taxonomy, BE-001–003, the Rule 5 profiles: namespace, close posture, concurrency posture, gate location, opt-in flags).
2. Kind: BE-023, BE-025, BE-029's predicate into 010.
3. Interface: Store-facing clauses to 001 (BE-027's gate table, BE-029 Layering, CAP-007 caller advice).
4. Interface: reduce 029's ASYNC-001–028 per-op restatements (four contradict 003) to "as BE-0xx, with these runtime differences".
Cutting BE-021 or BE-029 out by subject stays rejected.

### Proposed prune order (6 PRs)
1. Contradictions (each a maintainer choice): BE-005/BE-017 root scope; CAP-007 l.62; BE-021 table scope, NotFound row, broad-handler "ONLY", l.828; BE-029 RemotePath claim; capability gate vs closed guard off the kernel; ASYNC-008/018/019; Dafny `NativePath(".")`; CAP-007 mark exemption replaced by a real mark.
2. Kind cut (a move): CAP-001–006 + BE-001–003 → new declarations spec, CAP-007 reduced to taxonomy; BE-023/025 → 010 (`#be-025-native_path`, 2 inbound); BE-027 → 001 or tooling docs; kernel paragraphs dropped for 053; BE-017 `modified_at` → 053 with a decision for other classes.
3. Skeleton and project state: Overview (leftover), Terms, Assumptions A01–A06, Notes, Tested against; drop 8 Formal coverage and 3 Conformance paragraphs and every test path; drop stale BE-008/BE-025 lists; the BE-029 leftovers.
4. BE-029 prune (ADR 1).
5. BE-021 prune and split; § Reach its own ID (update 040, 044, ADR-0038, ADR-0042, 8 `src/` comments); mid-listing → 052; ADR 2.
6. BE-008, BE-009–019, BE-022, BE-024, BE-026 into outcome tables; BE-008 precedence as a table; flat and opt-in as named profiles.

## Appendix B: spec 052

Report only, at `cf75f0c`. Subject `sdd/specs/052-backend-lifetime.md`, 290 lines (`wc -l`). Leftovers already in the BK-456 dossier's "Left for the prune" are cited **[dossier]**, not counted new. Severity: **B** blocks Ready · **S** should fix · **O** optional.

### Whole-file figures
- Backlog IDs / "yet": none; `rg -n -o '\b(BK|BUG|ID|…)-\d+\b|\byet\b|\bnow\b|\bused to\b|\bno cell\b'` hits only other specs' IDs and "no cell" at 265, 267 **[dossier]**.
- Other specs' IDs, 15 (same command): AZ-029, S3-019, GR-051 (37); MEM-026 (59); MEM-025 (64, 85); GR-059 (67); SFTP-029 (68); HTTP-CONC-001 (69); STORE-007 (75, 84); CAP-007 (79); ASYNC-094 (86); RFC-0017 (104); SIO-010 (134). Mostly per-backend rosters (Rule 5/7).
- Test paths and private helpers, 15 (`rg -n -o 'tests/[A-Za-z0-9_/.]+|`_[a-z_A-Z]+`'`), at 39, 185–187, 256–264, 286–287.
- Spec marks: BE-033 in `tests/_kernel/test_protocol.py` 9, `test_protocol_oracle.py` 5, close-posture lanes 1 each, `test_protocol_stateful.py:203`, `tests/backends/memory/test_kernel_cells.py` 2; BE-028 in `test_concurrency.py` 3, `test_store.py` 1.

### Overview
- **S** Out of scope incomplete (Rule 6.1, Ready 3): ASYNC-094 (029), the adapter's close lifecycle ASYNC-083/088 (029), SIO-010 (006), STORE-007 (001) need an owner line or a move here.

### Terms
- **S** Circular/missing (Rule 6.2): `Session` defined by a paragraph that defines nothing; undefined: closed guard (`rg -c 'closed guard'`: 052:5, 003:9, 053:3, 029:1, 026:1; defined only implicitly in 053 BE-030 step 1), live operation, addressing members, exit, owner, condemned, `connection_dead`, Released, stream adapter, temp-and-rename write, wire temporary.
- **S** `thread_safe` in two senses: BE-028's "safe to share across threads" vs line 67's Graph "on the async axis" (GR-059, ASYNC-094 one-loop safety; `tests/backends/conformance/aio/test_concurrency.py:75`).

### BE-020: close()
**Kind:** lifetime. Other kinds inside: construct refusal "the kernel refuses to construct over one that differs" duplicates 053 BE-030 step 1 (**S**, keep in 053); "close() is optional (default no-op)" (structure); rosters at 36–37 and "MemoryBackend … on the kernel" (Rule 5/7 project state).

| Sentence | Fails | Relocate |
| --- | --- | --- |
| "Called for resource cleanup." | can fail | delete |
| "re-initialises its clients lazily" | two impls | delete, keep outcome |
| "every lazy client accessor guards on it" | two impls; false on the kernel | delete; restate as a race: a call that begins after `close()` begins raises `BackendUnavailable` |
| line 39 conformance lane sentence | Rule 7, Rule 6.6 | delete |
| Rationale | not a clause | ADR |
| Formal coverage | model description; no Rule 8 bridge (BK-463) | `formal/README.md` or Notes — but **lift** "Every operation that returns a result, except `RequireCapability`, answers `BackendUnavailable` when `!Live()`, ahead of every other clause and with `fs` unchanged" **into the invariant** |

**Form (S):** move BE-033's backend transition table (123–128) up to BE-020 for every backend, kernel differences in a column (gates before guard, `unwrap` guarded, close forwarded).

**Rule 5 (B):**
- Content survival after a reusable close unstated; `BackendContract.dfy:1299-1301` says contents need not survive (in-memory SQLite), MEM-018 implies they do, `test_close_posture.py:50-59` tolerates `BackendUnavailable` from in-memory SQL after close. Restate as "never refused *for being closed*" (`ReusableNeverRefuses`); declare retention as a profile or out of scope.
- Whether `close()` can raise: unstated (model: no error; GR-051: must not raise).
- Repeated-close idempotence stated only on the kernel (I2), relied on for all (`test_close_posture.py:17`; `MemoryBackend.dfy:1243`, `:2313`).

**Contradictions:**
- **B** Postures not closed-world vs ASYNC-083: `AsyncBackendSyncAdapter` inherits `close_is_terminal = False` (`rg 'close_is_terminal' src/remote_store/_async_to_sync_adapter.py` empty) yet raises `RuntimeError` after close (`_guard`, `:129-130`).
- **S** Rosters vs code: `AsyncAzureBackend` is terminal (`src/remote_store/aio/backends/_azure.py:104`) and in neither roster; `AsyncMemoryBackend` in neither. Delete rosters; terminal postures have homes AZ-029 (012:275), S3-019 (008:167), GR-051 (044:1516).
- **S** Closed-guard precedence has five homes (003 BE-008:425, 003 BE-029:169–177, 053 BE-030, 052 BE-033, the Formal note) and no clause in BE-020. Gap: closed guard vs BE-011's capability gate unstated off the kernel.
- Spec vs code tracked: BUG-293.

**Load-bearing:** terminal close refuses every live operation with `BackendUnavailable` first and without side effect; exceptions close / capability data / addressing; a call starting after close begins is refused; reusable never refused for being closed; default `False`.

### BE-028: Concurrent-Use Posture
**Kind:** lifetime. Inside: environment (native clients 62–67 **[dossier]**; "serialised by the operating system"); process obligation (document in spec and docstring).

| Sentence | Fails | Relocate |
| --- | --- | --- |
| "MUST document the posture in its spec and class docstring" | can fail | AUTHORING / backend guide |
| "An undeclared posture is a contract violation, not a silent default…" | can fail; self-contradictory | delete |
| "(stateless; delegates to os/shutil…)", "(a single threading.Lock, MEM-025)" | two impls | delete |
| "single_connection: … not safe under concurrent use" | can fail | restate: no guarantee, and one instance per thread works (`test_one_instance_per_thread_works`, `test_concurrency.py:261`) |
| Rationale "STORE-007 … bottoms out" | derived | Notes |
| "Like CAP-007's quality flags…" | rationale | ADR |
| "authoritative source for the machine-readable concurrency registry field" | Rule 7 link direction | delete; the registry cites the spec |

**Form:** one table *Posture | Guarantee | Remedy that must work* plus Assumptions.

**Rule 5:**
- **S** Not declared by capability or flag: `rg 'thread_safe|single_connection' src` empty; only `tests/backends/fixtures/backends.toml`. Decide: add an attribute, or amend Rule 5.
- **B** Posture depends on configuration: SQL-BLOB-072 gives four outcomes over URL × pool; HTTP-CONC-001 on transport. Needs named profiles.

**Contradictions (B):**
1. "each operation is atomic with respect to other operations on the same instance" vs CAP-007 (no `ATOMIC_MOVE` ⇒ must not assume), S3-028 (008:298, copy-then-delete), ASYNC-091 (partial write bytes visible). No BE-028 test asserts it (lane docstring, `test_concurrency.py:20`).
2. "the cloud and SQL backends … thread_safe" vs SQL-BLOB-072, SQL-QUERY-092, `backends.toml:88`, `:106` (`single_connection`), `test_registry.py:278`.
3. "documented thread-safe" vs S3PA-028 (011:218: PyArrow pins no guarantee).
4. **S** Graph "async axis" belongs to ASYNC-094; delete and link.

**Proposed Assumptions** (IDs need a format, P1): BE-A-01 vendor-documented native-client safety for `thread_safe`; BE-A-02 the OS keeps each filesystem call consistent, not a multi-call operation; BE-A-03 a pooled engine reaches one database (SQL-BLOB-072's durable case).

**Load-bearing:** the two guarantees restated testably; no multi-operation transactionality; no ordering between concurrent callers; the remedy works; default `thread_safe`.

### BE-033: Interaction Protocol on the Kernel
**Kind:** lifetime at the kernel/driver interface. Inside: single-call overwrite-conflict row (→ 053 or 003 BE-008); store-layer Refusal timing (`store.read(...)`, 001/029's); a restatement of SIO-010 (006:93-96) (**S**, one owner).

**B** Rule 3 / 6.3: about nine invariants in one section (states, transitions, exit ownership, Refusal timing, I1, I2, I3, read-after-close, the abort-logging bound). Re-IDing ripples to 15+ marks and inbound `#be-033-…` links from 029, 006, 003, 053 (`rg 'BE-033' sdd/specs`).

| Sentence | Fails | Relocate |
| --- | --- | --- |
| "The other clauses of spec 003 and spec 053 state each call; this one states the states between them." | can fail; repeats Overview | delete |
| "…outside the model" (100) | model coverage | Notes |
| end-of-data row "client's own end-of-data read … never a byte count" | two impls | driver docstring; restate: a stream ending short raises |
| overwrite row "refuses in one step on the wire…" | two impls | keep race outcome (two racing creators cannot both succeed); rest → 053 |
| close-race row "lock held around the accessor alone, never over I/O, async re-checks" | two impls | ADR/design note; keep "close waits for no in-flight call", "blocked calls fail mapped" |
| unwrap row "goes through run" | two impls | BK-455 dossier |
| Guard order paragraph | can fail | delete |
| The model is the oracle (184–200) | Rule 7 | `formal/README.md` under the oracle's Rule 8 heading (BK-463); blind-spot list is load-bearing |
| The model drawn | Rule 7 | `formal/README.md` § Compiled oracle (554–557 already says it) |
| Conformance | **[dossier]** | |

**Form:** prose-governed tables (no TLA+ module; BK-460/461 open). Only the backend party has a full transition table; read stream (5 states), handle, listing and iterator only "Leaves a state by". Proposal: one table per party *state | event | next | observable result | owner* plus "a transition not tabled is forbidden".
- Prose vs model state sets differ (`rg 'datatype' sdd/formal/KernelProtocol.dfy`): stream `SOpen|SClosed|SReleased` vs five; handle adds `HNone`; listing absent from the model.
- **S** Generated diagrams state nothing under Rule 3: checked against Dafny not TLA+ (`tests/scripts/test_gen_protocol_diagram.py:134-148`), and outside the declared subset (composite states, `<br/>` labels, no `[*]` in three). Move under Notes as a view (generator ripple, `scripts/gen_protocol_diagram.py:55`).
- **S** "each a lemma of KernelProtocol.dfy" reads as model-governed; prose governs (Rule 4). Lemma names to Notes as proofs.

**Rule 5 (O):** "on the kernel" is a profile declared by class type; name it in Terms. **Rule 7 (O):** "such as MemoryBackend and AsyncMemoryBackend" in Scope; Conformance exceptions **[dossier]**.

**Ready 3 (B):**
1. `Session` rows (152–154) bind a component that does not exist (`rg 'class \w*Session|def invalidate|def run\(' src/remote_store` finds only `ext/cache.py:306`, unrelated); state set is BK-455's open decision → its dossier, one out-of-scope line. BE-028's See also (87) points at the close-race row.
2. Refusal timing names a read handle that does not exist (BK-454 open decision); `AsyncStore.read` returns `AsyncIterator[bytes]` (`src/remote_store/aio/_async_store.py:85`), contradicting ASYNC-006/020. `test_protocol.py:225-236` (marked BE-020) pins the opposite. Undecided under `000-process.md` Rule 7.

**Load-bearing:** the tables; I1–I3; exit rows (abort on any exception incl. cancellation with the write's error raised; abort failure logged on `remote_store._kernel` at WARNING with its verdict; temporary deleted with the NotFound exception; caller iterator `aclose`d before return, its error never replacing the write's; sync stream never closed); close failure logged never raised, read failure outranks close failure; condemned-stream release both runtimes for `read`/`read_bytes`; read after close `ValueError` sync / ends async; the oracle's blind-spot list.

### Assumptions
**B [dossier]**. Add: BE-A-04 closing a native client wakes blocked calls with a mappable error; BE-A-05 a dead transport's stream close may block (shared with 006: needs one owning environment spec, Rule 6.4, none exists); BE-A-06 cancellation arrives as an exception at an await point.

### Notes
**S** "None." is wrong: STORE-007's dependency on BE-028; I2 as a consequence; lemma names as proofs; diagrams as views; BE-020's model note.

### Tested against
Correct (`RootPath.dfy` tags BE-020 at 232, 253, 275); per-section test lists inside BE-020/BE-033 contradict its closing paragraph — delete them.

### ADR coverage
`rg -l -i 'close_is_terminal|terminal close|concurrent-use posture|single_connection' sdd/adrs sdd/rfcs` finds only RFC-0017: no ADR records why close is terminal or concurrency is a declared posture. Relocated rationales need one ("Close and concurrent-use postures are declared per backend"); the B contradictions' decisions too, via backlog first.

### Process-guide accuracy
- **P1 (S)** Template's `<PREFIX>-A01` fails `check_spec_marks._SPEC_ID` (`r'^[A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[a-z]?$'`: `BE-A01` False, `BE-A-01` True), so a template-form Assumptions row is never declared and a mark citing it silently unfound (`findall`, line 461).
- **P2 (S)** Rule 4 gives lifetime to TLA+ only; the lifetime model is Dafny (`KernelProtocol.dfy`), so even after BK-463 it cannot govern BE-033. Amend Rule 4 or note it in BK-463.
- **P3 (S)** "Design note" has no home (`rg -i 'design note'` over AUTHORING.md, 000-process.md: none).
- **P4 (O)** `## Sections` (052) vs `## Contract kernel` (053): Rule 6.3 silent on a Sections heading.
- Code side: `backends.toml:15-25`, `_loader.py:56-59` still cite "specs 003/029" and "until BK-287 lands".

### Proposed prune order
1. Decide first (backlog + dialog): BE-028 profiles by configuration and code declaration; BE-028 atomicity vs CAP-007; adapter posture vs ASYNC-083; content survival on reusable close; Refusal timing and Session rows into BK-454/BK-455.
2. Fix P1–P3.
3. Pure relocations: rationales → new ADR; Formal coverage / model-is-oracle / model-drawn → `formal/README.md` (BK-463 heading); test lists and rosters deleted (terminal postures already homed).
4. Fill skeleton: Terms, Assumptions BE-A-01–06, Notes, out-of-scope owners.
5. Restate mechanism as outcomes; BE-020 precedence into its invariant, others point at it; construct refusal only in 053.
6. Restructure: backend table up to BE-020; split BE-033 per invariant; re-mark tests and anchors; diagrams under Notes.
7. Re-run the Review checklist, contract before form.

## Appendix C: spec 053

Report only, at `cf75f0c`. 652 lines (`wc -l`). Heading gaps (`^#{2,3} `): Overview 15, Terms 10, § Contract kernel 13, BE-030 162, BE-031 107, BE-032 326, Assumptions 4, Notes 4, Tested against 10. Dossier items cited as ⟨L1⟩ (Assumptions lift nothing), ⟨L2⟩ (driver duties and a pipeline order), ⟨M⟩ (stage-zero mechanism ranges). Severity: **[blocks Ready]**, **[should fix]**, **[optional]**.

### Whole spec

**W1 [should fix] The Overview names the wrong interface.** It says "single-call clauses at the interface between the kernel and its driver" (so does the dossier row). Most clauses are at the **Backend interface of a class on the kernel** (BE-030's key-class table, BE-031's tables, A.5); only the driver duties are kernel-to-driver. Line 11 admits both. So 053 holds two interface contracts of one kind — the interface form of ⟨L2⟩. *(This Overview sentence is new text from PR #1169.)*

**W2 [should fix; split is a maintainer decision] Driver duties scattered; A.8's "each stated once here" is false.**
- Construction refusals at five sites: lines 52–54, 71–75, 121, 214–215, 361 (`rg -n 'refuses to construct|MUST provide'` plus reading); 121 and 361 state the same fact.
- Owed behaviour at 173, 211–225, 233–236, 386–390 is all restated in A.8's list (588–597).
- Duties only in 003 BE-021's two-halves table (003 l.735–751): `classify` types a denial; `container_absent` recognises its wire's shape; `list_page` one `Page` per wire request; `list_page` raises the denial of the folder it lists. That last row cites "(A.7)", which is about links (`rg -n 'denial|the folder it lists'` on 053 finds only line 529): a dangling citation.
- Remedy: one home for every driver duty — one 053 section, or a driver-interface spec on prune (a cut by interface, which Rule 2 allows). The latter revisits stage two's "does not split further": needs a dialog.

**W3 [blocks Ready] No section has one invariant (Rule 3).** 64 bold/italic lead-ins (`rg -n '^\*\*[^*]+\*\*|^- \*'`), 50+ sub-rules under three IDs. Tests mark whole sections (`tests/_kernel/test_tree_results.py` marks only "BE-032"), so Ready 2 cannot be checked per invariant. A.n labels are load-bearing: 184 lines in 13 files cite them (`rg -c '\bA\.(10|[1-9])\b' src tests sdd/formal -g '!*.md'`; StoreTree.dfy 36, each kernel.py 31, test_encoding_observations.py 39). Keep the labels or map them in one move and re-mark.

**W4 [should fix; record as known state] Rule 4: nothing governs and nothing can yet.** `StoreTree.dfy` 0 `@spec` tags; `BackendContract.dfy` has none for BE-030–032, and says why (348–349): `check_formal_trace.py` needs a conformance cell citing the ID, and reads only `tests/backends/conformance/` (docstring 10–11), while none of the 88 test lines marking BE-030 to BE-032 is under it (`rg -c 'spec("BE-03[0-2]"' tests`, re-derived when this audit was committed; the first pass's 127 did not reproduce) Even after BK-463 no tag can reach 053 unless the trace check accepts kernel cells. Record in BK-463 or BK-434.

| Clause | Candidate model | Bridge |
| --- | --- | --- |
| A.1 resolution | StoreTree.dfy §2; 051 Lean/Alloy | none (BK-434) |
| A.2 partial `decode` | §4 | none |
| A.3 listings | §5, §8 | none |
| A.4 write checks | §6 (+§3) | none |
| A.6 no empty folder flat | §7 | none |
| walk omitted entry → DirectoryNotEmpty | §9; BackendContract `DeleteFolder` + `CanonicalUnder` (367–370, 934–955) | oracle, no Rule 8 (BK-463), no BE-031 tag |
| transfer | §10 | none |
| A.8 rules 1–4, tables | §11 | none |
| BE-030 metadata-gate rank | BackendContract `Write` (721–766) | oracle, no Rule 8 |
| BE-030 listing rule | BackendContract `Canonical` (350–359) | untagged by design |
| BE-030 145–148 root predicate | RootPath.dfy `RootSpellingCharacterisation` | compiled, no Rule 8 |
| BE-030 step 1 | KernelProtocol.dfy I1 | 052's |

Model-citing sentences (87, 293–299, 548–551) are informative: Notes or Tested against.

**W5 Contradictions and double homes.**
- **[should fix]** 052 line 40 restates BE-030 step 1's construct refusal (two homes; 053 should own it), plus project state.
- **[should fix]** Metadata-gate rank on the kernel in both 003 BE-008 (429–434) and 053 BE-030 (75–88).
- **[should fix]** 003 BE-013 lists `DirectoryNotEmpty` for `recursive=False` only; 053 290–299 adds a concurrent writer mid-walk, which affects every backend: that half belongs in 003 BE-013 plus an assumption.
- **[should fix]** 003 BE-021's kernel/driver table is 053's subject; it cites "BE-030's step 4" (003 l.749) and the nonexistent "(A.7)" (l.751).
- **051, no contradiction:** A.1 "Key is not a caller's input" restates 051 § Layering → link [optional]; A.2's `a\b` agrees with TREE-007; "is_file and is_folder never both true" is derived (TREE-001, TREE-010) → Notes.
- **013, 029 [optional]:** 029 line 19 restates "public in `remote_store.drivers`"; 013 line 29 relies on `put_is_atomic` choosing a route, which 053 never declares.
- **045 WR-011:** consistent.
- **[blocks Ready] A.6 internal contradiction:** "An encoding without folder objects cannot hold an empty folder, so there it vanishes" vs RFC-0021 OQ1 (284–287): on the kernel a stored `a/` alone makes `is_folder("a")` True with empty listings; A.6's last sentence leaves it "not decided here".
- **[optional] A.8 rule 3:** "A determinant fails closed" vs a determinant listing's `NotFound`/`InvalidPath` read as empty (A.4 l.431, BE-031 269–271); add the flat-listing carve-out to rule 3.

**W6 Rule 6 skeleton.**
- **[should fix]** Terms defers into sections; undefined: family, flat/hierarchical namespace, folder objects, canonical key, decode, `Nothing`, route, the walk, error-path probe, fail open/closed, link, store policy.
- **[should fix]** "probe" in two senses: lines 73–74 (`probe`'s inherited body, PING-008, the health probe) vs A.8's error-path probes.
- **[should fix]** Notes "None." untrue: derived claims at 145, 160–161, 331, 548–551, 293–299.
- **[should fix]** Tested against names no command (`bash scripts/dafny_verify.sh StoreTree.dfy`, the pytest invocation over `tests/_kernel/`) and omits `RootPath.dfy`.
- **[should fix]** Conformance lists in sections (194–201, 306–308, 616–621; the last also describes the fake's design) against Rule 6.6.

### Overview (3–16)
W1 [should fix]; "These are single-call clauses … (Rule 2)" is a meta-claim [optional].

### Terms (18–24)
W6; add the class-on-the-kernel definition [should fix].

### § Contract kernel (28–39)
No witness: a definition, provenance, project state. **[should fix]** line 35 "first such classes" (project state); line 39 "RFC-0021 …, which BE-032 lands" (history); line 37 "an answer the other clauses of spec 003 leave to the backend" — after the split "other" is stale (one of PR #1169's three relinked sentences; the relink kept the wording). [optional] link ADR-0042, ADR-0047 over the RFCs. **Load-bearing:** anchor `#contract-kernel`, 7 inbound links; fold content into Terms, keep the anchor.

### BE-030 (41–201)
Kind: single call at the Backend interface. Inside: function (step 3, 58–59; root equivalence 145–148; glob normalisation 185–189); driver interface (construct refusals 52–54, 71–75, 121–124; `put` types 90; `folder_stats` 172–174); environment (non-blocking `None`, line reads not covered, 99, 107–109).

| Quote | Verdict | Where |
| --- | --- | --- |
| "Pipeline, per operation, in this order: 1.…5." | step order | restate as precedence: CapabilityNotSupported > BackendUnavailable > InvalidPath (key, root) > WR-010 gate > content TypeError > observed checks > I/O; step list → ADR-0042 or design note. External step citations, 5: 003 l.373, 749; 052 l.40; kernel.py sync 836, async 851 |
| "result's path is built from that key before the driver commits…" | mechanism + postcondition | keep: an accepted key never fails on that key after commit |
| "since capability data is not a live operation" (66, 184) | rationale | ADR-0042 / Notes |
| "Ranking it after those checks instead would cost…" | rationale | ADR |
| "BackendContract.dfy's Write states the same order." | other artifact (true, 721–725) | Notes / Tested against |
| "On sync the stream a driver receives answers an unsized read…" | mechanism | keep: a `None` chunk raises TypeError whatever read the driver uses, except line reads |
| "Async content is checked chunk by chunk…" | mechanism | same |
| "displaced and restored by a rename that cannot replace" | mechanism + outcome | keep "never AlreadyExists with overwrite" |
| "Folding it would name another node… withdrawn fold…" | rationale, history | ADR / Notes |
| glob worked examples | Rule 3 | glob tests |
| Conformance | Rule 6.6 | delete |

Stays: capability gate before closed; WR-011 shape before USER_METADATA refusal; content TypeError rank and verbatim pass-through; two-key source-first per profile; key-class table; Addressing stays total; listing omission and its log; glob precedence. Rule 3 [blocks Ready via W3]: split into key rule (function), addressing, listing omission, glob, content, construction.

### BE-031 (203–308)
Kind: single call at the Backend interface + driver duties ⟨L2⟩ + environment (mid-walk writer).
**[blocks Ready]** The invariant "removes folders through two driver primitives … and sequences them … in one place" fails both Rule 1 tests ("in one place" is code locality); the real invariant is the tables (276–288).

| Quote | Verdict | Where |
| --- | --- | --- |
| "in one step where the wire has one (rmdir, a lock)" | hint | design note; keep "without removing it" |
| "checks first and documents that race" | cannot fail | driver guide + Assumption |
| "The kernel calls it with no probe before it…" | call order | driver duty (already in A.8) |
| "stat is called with False by the three calls…" | call parameters | driver-interface spec |
| The sequence (246–274) | step order, probe sequences | ADR-0042 / design note; restate as outcome rows + cost rows per `parents`/`namespace`/`delete_tree` (BE-032's cost table has no delete_folder row) |
| 293–299 CanonicalUnder, "the model now covers" | model, project state | Notes |
| Conformance (306) | Rule 6.6 | delete |

Duplicates [should fix]: 216–217 = A.6; 238–244 = A.8; 256–259 = A.9; omitted-entry DirectoryNotEmpty three times (BE-030 177–180, BE-031 290–292, A.3 408–411). Stays: both tables; The root; `missing_ok` on the answer when NotFound; link outcomes.

### BE-032 (310–632)
- **A.1 [should fix]:** function + structure restated from 051 + environment. "Exactly one of Item, Folder, Nothing" → Terms, proof in Notes (or 051 lemma); "Key is not a caller's input" → link to 051 § Layering; name equality → Assumption (owner 051's Name equality, which SPEC-DESIGN's Exemplar calls an environment assumption); "no depth" stays; `ensure_parents` creates every missing folder → driver duty. 051 should not take resolution ("no operation, backend or encoding").
- **A.2:** declarations table → Terms or driver-interface spec; partial `decode` stays as a Terms definition here (a separate encoding spec is not worth it); spec 004 copies (377–378) → links [should fix]; 361 duplicates 121 [should fix]; 369–371 "not decided here" [blocks Ready].
- **A.3:** single call. Mechanism: "stack of open items rather than a buffer"; "stat k first, success included"; "stat the key alone" (cost table covers) [should fix]; ordering duty duplicated (590); undecodable link at 405 and 494 [should fix]. Stays: omission rule, item rows, the flat limit `read("k/a.txt")`.
- **A.4:** single call + environment ("Neither check is race-free…" → Assumption). Probe sequence ("one stat per ancestor, shallowest first…") is step order; Rule 5 says cost per profile [should fix]; "after the transfer source check" precedence stays. Stays: the two InvalidPath writes; fail-closed reading.
- **A.5:** core outcome table, best Rule 3 form here. Load-bearing. Families table → Terms. "The per-operation clauses keep…" organisational [optional].
- **A.6 [blocks Ready]:** W5 and Ready 3; duplicated in BE-031 216–217.
- **A.7 [blocks Ready] spec vs code:** `links` and store policy (`follow_within_root`, `no_follow`) **do not exist in code**: driver attributes are `name, namespace, parents, capabilities, put_is_atomic, close_is_terminal` (`src/remote_store/_kernel/_sync/driver.py` 49–54); `rg '\blinks\b' src/remote_store/_kernel` finds two docstrings (kernel.py sync 1368, async 1385); no test uses `links="present"`, `follow_within_root`, `no_follow`. ADR-0047 and RFC-0021 say links are stated but not on the kernel. Future intent (principle 3), undeclarable profile, no test (Ready 2); undecided under 000-process Rule 7; owner BK-433. Stays only: "Whatever its driver declares, a class on the kernel has delete and a move source probe their key without following a link, and delete_folder keeps BE-031's follow_links=False view." [should fix] "Local and SFTP" names backends not on the kernel. [optional] "replacing a link … without a signal" → ADR-0047.
- **A.8:** single call + driver interface + mechanism. [should fix] "cheapest call first", the Probe columns (keep Concludes; counts → cost table), ancestor walk "shallowest first … skipped" (537–541), "no stat is asked" (578, a cost). [optional] "Drivers owe no rule…" → kernel obligation: the answer does not depend on which probe-set shape a refusal takes, beyond the two typing rules. [should fix] ENOTDIR sentences → Assumptions. Load-bearing: rules 3 and 4; the probe set; the two typing rules; namespace split with the `parents="none"` exception; the two-key paragraph.
- **A.9:** precedence + environment; duplicated in BE-031 256–259; "kept once per operation" restates 003 § Reach → link [optional].
- **A.10 [should fix]:** test tier; delete.
- **Costs:** right form, stays. [should fix] relative to "a class not on it" (last row cannot fail on the kernel): restate as absolute bounds per profile; add rows for delete_folder per profile, get_folder_info's determinant stat, the destination stat on stat-first routes.
- "not decided here": multiline Grep `not\s+decided\s+here` → 345–346, 370, 469.

### Assumptions [blocks Ready, ⟨L1⟩]
Prefix needs a decision: template `<PREFIX>-A01` with BE- collides across 003/052/053; `KERN-` placeholder.

| ID | Assumption | From |
| --- | --- | --- |
| KERN-A01 | The encoding compares names exactly, as 051's do (owner 051 § Name equality; link) | A.1 341–346 |
| KERN-A02 | No other writer changes the encoding between a determinant and the call it decides, or during a walk | A.4 432–433, BE-031 291, A.9 |
| KERN-A03 | A wire's ENOTDIR arrives as a probe-set shape | A.8 507, 536 |
| KERN-A04 | A flat wire's listing is byte-lexicographic | A.3, A.10 621 |
| KERN-A05 | A wire rmdir (or lock) removes an empty folder and refuses otherwise in one step, where it has one | BE-031 213 |
| KERN-A06 | Caller streams follow Python binary I/O; a non-blocking stream may yield None | BE-030 98–101 |
| KERN-A07 | Python's buffer protocol: a non-C-contiguous buffer is refused by its exporter | BE-030 112–114 |
| KERN-A08 | An absent container's listing answers NotFound or InvalidPath (owner 003 BE-021; link) | A.8 578, 604 |

### Rule 5: undeclared profiles

| Profile | Declared by | In 053 |
| --- | --- | --- |
| namespace | `Driver.namespace` | yes (A.2), but two A.2 "properties" map to one flag: state as one profile |
| parents | `Driver.parents` | yes |
| links, store link policy | nothing in code | stated, undeclarable [blocks Ready] |
| put_is_atomic | `Driver.put_is_atomic` (driver.py 53; kernel.py 882) | absent (`rg -n 'put_is_atomic\|rename_replaces' 053`: 0) [should fix] |
| rename_replaces (line 132) | `SupportsRename.rename_replaces` (kernel.py 84) | absent [should fix] |
| rename route, temp and rename, wire temporary vs spool (110, 112, 135, 516–517) | `SupportsRename`, `SupportsOpenWrite`, `SupportsAtomicMove`, `SupportsCopy` (kernel.py 34–42, 99) | named only as routes [should fix] |
| native aggregate, native glob, tree delete | `SupportsFolderStats`, `SupportsGlob`, `SupportsDeleteTree` | by primitive; list in one table |

### Rule 7
`rg -n -i '\b(yet|now|already|today|first such|lands|landed|existing|still|withdrawn|used to|later|comes later)\b'`, backlog IDs 0. [should fix] 36 "first such classes"; 39, 323 "lands"; 175 "withdrawn fold"; 296 "the model now covers"; 477 "Local and SFTP"; Conformance lists 194–201, 306–308, 616–621. [optional] 392 "already writes"; 486 "existing rule".

### Ready 3: "not decided here"

| Line | Sentence | Owner | Disposition |
| --- | --- | --- | --- |
| 345–346 | "which backends compare names how … not decided here" | BK-436 | KERN-A01 |
| 370 | "how it decodes is not decided here" | BK-438 | state only the rule in force (omitted, BE-030) |
| 468–469 | "Whether a flat raw key with an empty segment … holds an empty folder is not decided here" | BK-438 | contradicts A.6: scope A.6 as a precondition, or decide [blocks Ready] |

### Load-bearing
Anchors `#contract-kernel` (7), `#be-030-…` (9), `#be-031-…` (2), `#be-032-…` (10) (`rg -o '053-contract-kernel\.md#…' | sort | uniq -c`); A.1–A.10 labels (184 lines) or a one-move mapping; BE-030 step numbers until their 5 citations change; BE-030's key-class table, Addressing stays total, listing omission and log, glob precedence, content TypeError rank and pass-through; BE-031's tables and root refusal; A.5 and A.4's two InvalidPath writes; A.8 rules 3 and 4, probe set, typing rules, Concludes columns; costs as absolute bounds; A.3's flat limit. Mechanism goes to ADR-0042 or a kernel design note, relocated not deleted.

### Proposed prune order
1. Skeleton and project state (no clause changes): fold § Contract kernel into Terms keeping the anchor; complete Terms, disambiguate "probe"; delete Conformance lists and A.10; derived claims and model citations → Notes; runnable Tested against.
2. One dialog: A.7 (strip to the entry-view rule until BK-433, or add a `links` declaration); A.6 empty-segment scope; Assumptions ID prefix; driver-duty home (one 053 section vs a driver-interface spec).
3. Assumptions KERN-A01–A08, replacing the three "not decided here".
4. One home per fact: inside 053 (omitted-entry ×3, undecodable link ×2, flat-with-folder-objects ×2, A.6 ×2, A.9 ×2); across specs (052 l.40, 003 BE-008 429–434, 003 BE-021's table and its dangling A.7, 003 BE-013's concurrent-writer half).
5. Rule 1 relocation: pipeline → precedence table; BE-031 sequence → outcome + cost rows; A.8 Probe column → costs; cost rows for `put_is_atomic`, `rename_replaces`, optional protocols; rewrite the 5 step citations.
6. Rule 3: one invariant per section, A.n mapped, tests re-marked.
7. Rule 4 last, outside the spec: BK-463's Rule 8 statement and a BK-434/BK-463 decision on letting `check_formal_trace.py` accept kernel-cell marks.

### ADR and process docs
No new ADR for the audit; step 5's mechanism home is ADR-0042 or a kernel design note. SPEC-DESIGN.md gives no guidance on a spec holding two interface contracts of one kind (W1, W2); one sentence ("a spec binds one interface") would settle it [optional].
