# RFC-0025: Master returns to 0.33.0's code; the kernel line is frozen on a branch

## Status

Draft, 2026-10-25. Tracked as **BK-488**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) R1's D2, D8, D9 and D10 rows, R2, R3's
class K and class P dispositions, R4, R5 and § Impact's Process bullet, and
[`000-process.md`](../000-process.md) Rule 5 (§ What changes in RFC-0024 and
elsewhere). Decisions taken in this RFC's session: decision log
`sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl`.

## Summary

**Master's library code goes back to v0.33.0 plus three non-breaking 0.33
fixes. Everything built since for the contract kernel stays, unchanged, on the
branch `frozen/kernel-driver`.** RFC-0024 paused the migration onto the kernel
but kept the kernel, Memory on it and their specs on master. This RFC moves them
off master instead, so master's code is again the code users run. 0.33 patches
are then tagged from master, and `release/0.33.x` is retired. The spec-first
work of RFC-0024, the process and the tooling stay on master. Spec 054 becomes
spec 052.

## Motivation

RFC-0024 froze the kernel in place. Master kept about 6,000 lines of kernel
code: `git diff --stat v0.33.0 origin/master -- src` at `814c1f6` counts 30
files, 5,978 insertions and 1,506 deletions. Of the 92 commits since the tag
(`git rev-list --count v0.33.0..814c1f6`), 9 touch `src/` (`git log
v0.33.0..814c1f6 -- src`). Six are kernel, driver or Memory-on-the-kernel
work, and three carry 0.33 fixes, one of them mixed with kernel fixes (#1151).
Every v1 flow will rewrite what that kernel does, and RFC-0024's freeze lets it
change only to keep the gates green. Yet it costs on every change while it
stays:

- **Two specs, 052 and 053, bind code** that no flow will keep, while they are
  not ground and not superseded.
- **Master's code is not 0.33's.** RFC-0024 R2 therefore made
  `release/0.33.x`'s suite the 0.33 record and every fix a cherry-pick or a
  port. That branch still has no CI, protection or patch checklist (RFC-0024
  Open Question 2).
- **The gates, agents and process files** carry the kernel's tooling and rows:
  the sync twin generator, the protocol diagram, the Dafny kernel model and its
  oracle, `tests/_kernel/`.

## Proposal

### D1. The snapshot

`frozen/kernel-driver` was pushed at `814c1f6` (master after #1179) on
2026-10-25. It is never merged back, rebased or pushed to. Its contents are
input, not ground: a later flow may read it as candidate design, as RFC-0024
§ R1 reads PR #1173's research. Protecting the branch against deletion is a
repository setting, the maintainer's (Open Questions).

### D2. Master's library code

`src/` and the library tests return to v0.33.0. Three 0.33 fixes made since are
re-applied with their tests, each a bug fix the bump table rates patch:

- BUG-280: a refused Local listing raises `PermissionDenied`.
- BUG-298: glob anchoring at the true end of a key.
- BUG-330: the sync adapter truncates on a `None` read.

Everything else stays on the snapshot:

- **Breaking changes.** BK-405 (glob patterns read as paths) and BUG-329
  (metadata must be a mapping), both **Breaking**, together with their code,
  tests, spec edits, docs, migration-guide subsections and CHANGELOG lines.
  Their behaviour returns through the flow of the operation it concerns, as a
  candidate break record (RFC-0024 § R5).
- **Kernel-only defects.** BUG-328, BUG-331 and BUG-333, fixed on the kernel's
  streams, with their tests: v0.33.0's Memory never had those streams. Its
  `open_atomic` already yielded a `BytesIO`, which refuses a strided buffer
  (`git grep -n BytesIO v0.33.0 -- src/remote_store/backends/_memory.py`).

### D3. Specs and formal models

- **Specs 052 and 053 leave master.**
- **In specs 001 to 050, each edit made since the tag stays or leaves with the
  change it belongs to.**
    - Edits belonging to the kernel, BK-405 or BUG-329 leave.
    - Edits belonging to BUG-280, BUG-298 or BUG-330, BUG-337 outside kernel
      text, BK-456 stage one or the formatting fixes stay.
    - The per-file list is PR 2's derivation, recorded in its trace.
    - Two commits mix both kinds and are split by clause. **#1151**
      (`git show a62295f2a -- sdd/specs`): all its spec 003 edits sit in kernel
      text or are BUG-329's, so none of them stays. **#1154**
      (`git show --stat 52448e023 -- sdd/specs`, specs 001, 018, 029 and 040):
      it is BK-405's except BUG-298's GLOB-014, which stays.
- **Spec 003** returns to v0.33.0's text plus the edits above that stay.
    - BE-020 and BE-028, which stage two moved to spec 052, return with
      unchanged meaning. Both are in v0.33.0's spec 003: `git grep -n -E
      '^#+ BE-0(20|28)' v0.33.0 -- sdd/specs/003-backend-adapter-contract.md`.
    - **BE-030 to BE-033 leave.** They entered spec 003 with the kernel PRs
      from #1127 on (`git log -S BE-030 v0.33.0..814c1f6 --
      sdd/specs/003-backend-adapter-contract.md`). v0.33.0's spec 003 has none
      of them; BE-029 is its highest. BUG-337's edits to BE-032 leave with
      BE-032.
- **A pointer is not ground.** Changing a cross-spec pointer in a ground spec's
  non-normative paragraph (its Layering or Tested against) does not change the
  ground, so it needs no reopen (RFC-0024 § R1). The ground register records
  each such edit.
    - Spec 051's Layering cites spec 053's BE-032 and names spec 004 as the
      input layer's owner.
    - PR 2 drops the BE-032 sentence. PR 3 points input strings at the key
      spec.
    - The ruling closes BK-487, which PR #1171 filed. That item reaches master
      with PR 3 and is closed there.
- **Spec 051's test stays.** `tests/test_store_tree.py`, the reference model
  spec 051 is tested against, holds every TREE mark (`git grep -l
  'mark.spec(.*"TREE-0' -- tests`). It stays with the spec, though it came
  after the tag.
- **Formal models.**
    - **Leave with the kernel:** `StoreTree.dfy`, `KernelProtocol.dfy` and its
      generated oracle, and the kernel parts of `BackendContract.dfy` and
      `MemoryBackend.dfy`.
    - **Stay:** CI's `verify-formal` job, which v0.33.0 already ran
      (`git grep -n 'verify-formal:' v0.33.0 -- .github/workflows/ci.yml`), and
      the Dafny models v0.33.0 had. Only its `StoreTree.dfy` and
      `KernelProtocol` lines and its oracle step leave.
    - **Stay as ground:** spec 051, its Lean and Alloy models and their TeX
      account.

### D4. Tooling and docs

- **Tooling.** What serves only the kernel leaves with it:
  `gen_sync_kernel.py`, `gen_protocol_diagram.py`, `tests/_kernel/`, the driver
  checks of `check_custom_backend_guide.py`, and the CI steps and gate rows that
  run them. Process tooling stays.
- **Docs pages return with the code they describe.** Each page that
  `git diff --stat v0.33.0 814c1f6 -- docs-src` lists is judged by its content.
    - **Kernel or driver text returns to v0.33.0's:**
      `reference/api/drivers.md` (removed),
      `reference/api/backends/memory.md`, `reference/api/aio/backends/memory.md`,
      `reference/api/backend.md`, `reference/api/index.md`,
      `reference/api/_nav.yml`, `guides/backends/index.md`,
      `guides/custom-backend-guide.md`, `index.md`'s "Bring your own" and
      `context7.json`'s custom-backend line.
    - **`guides/glob-pattern-matching.md` is split.** BK-405's path-reading
      text leaves, and BUG-298's newline sentence stays.
    - **Process pages** keep their edits: the design indexes, and
      `_path_rules.yml`'s index status columns (BUG-338).

`remote_store.drivers` was never released, so no user loses it.

### D5. One release line

`release/0.33.x` is retired. 0.33 patch releases are tagged from master and take
what the bump table rates patch or no bump, until v1 implementation begins on
master. A v1 flow that changes `src/` first cuts a `release/0.33.x` branch from
the last 0.33 tag, and RFC-0024's D2 and D9 apply from then on. Until then:

- A fix needs no cherry-pick.
- Master's suite is the 0.33 record for D8's comparisons, and R2's "the branch's
  suite, not master's" no longer applies.
- `CONTRIBUTING.md` § Release says so, Phase 1's migration-guide bullet
  included.
- An unreleased fix that owes a migration-guide subsection gets it under the
  next 0.33 patch's own heading: BUG-280's subsection, and BUG-298's sentence
  moved out of BK-405's.

### D6. Spec numbering

Spec 054, the store key of PR #1171, becomes spec 052, once spec 052 has left
master. Its section IDs do not change.

- **Records.** A record committed before PR 3's merge, this RFC, its trace and
  PR 2 included, that cites "spec 052" or "spec 053" means the frozen spec. The
  ground register says so in one line, dated by that merge commit, since those
  records are never edited.
- **Section IDs.** None changes meaning. BE-020 and BE-028 return to spec 003
  as they were. BE-030 to BE-033 retire with the snapshot (§ What changes,
  Rule 5's row) and are not reused.

### D7. Backlog

- **Kernel and driver items.** One host item, reviving or rewriting the frozen
  line, which is D10, absorbs the open class P items of RFC-0024 § R3 whose
  whole subject is the kernel, a driver, the `Session` or the migration. Its
  dossier lists each absorbed ID with its diagnosis and the records it cites.
  Each verdict below comes from reading the item's dossier against v0.33.0
  (the trace's orient):
    - **Absorbed whole:** BK-390, BK-439, BK-446, BK-455 and BK-434. BK-434's
      drift findings on `BackendContract.dfy` are re-checked against the model
      master keeps.
    - **Absorbed, linking its record:** BK-450. Its T1 is BUG-341, and its
      decision log `062e5181-cc50-5b17-963f-e9da78bad8ee` travels to the host
      dossier.
    - **Split:** BK-452. Its flat reference driver goes to the host. Its Memory
      clauses stay on master: MEM-016 and MEM-016b misstate the overwrite case
      in v0.33.0's spec 013, and the mtime clauses are unpinned.
    - **Kept on master:**
        - BUG-341, a defect in v0.33.0 (`backends/_memory.py` passes the stored
          `metadata` dict out uncopied).
        - ID-140 and ID-181, features of 0.33 backends. Their "Placement: D3
          step" lines revert.
        - BK-345, whose gap (no absent-container cell over the `Backend`
          registry) predates the kernel. It goes back to its scope before the
          2026-10-02 re-scope to drivers.
- **Other open items that cite a retired ID or a kernel premise.** PR 2 applies
  one rule to each item that `hatch run backlog-find "kernel|driver|StoreTree|spec
  053|spec 052|BE-03[0-3]"` lists open, and records each verdict in its trace:
    - A retired ID (BE-030 to BE-033) is dropped from its `spec:` field.
    - An item whose whole subject is the kernel is absorbed into the host.
    - An item whose premise the revert falsifies is re-scoped to v0.33.0, or
      decided against with that reason. BK-332's premise was "BK-394 rewrote
      the guide as a driver", and D4 reverts the guide.
    - The review that asked for this rule found BUG-292, BUG-310, BUG-323,
      BK-332, BK-433, BK-436, BK-438, BK-451, BK-454, BK-467, BK-482, BK-483
      and BK-484. That is the list's state at `51f2c06`, not a bound.
- **Completed entries for work that leaves master.** Entries under
  `BACKLOG-DONE.md` § Unreleased move to a new section, `## Frozen on
  frozen/kernel-driver (RFC-0025)`, verbatim and each still `[x]`, so the next
  0.33 patch does not record them as shipped. The CHANGELOG audience gate reads
  § Unreleased only, so their CHANGELOG lines leave with them. This applies to
  the kernel items, BK-405, BUG-329, BUG-328, BUG-331 and BUG-333. The list is
  PR 2's derivation.
- **BK-456.** Its stage two is reverted with spec 003, and its stage three
  (PR #1172, the prune of spec 052) has no subject left.
- **BK-435.** Its open work on `StoreTree.dfy` is parked with that model.

### What changes in RFC-0024 and elsewhere

Each row holds until v1 implementation begins on master. From then, RFC-0024's
own text applies again, with a `release/0.33.x` cut as D5 says.

| Clause | Becomes |
|---|---|
| D2 | Spec work runs on master, and so do 0.33 patches (D5 here). |
| D8 | Master's suite is the evidence of what 0.33 does, since master's code is 0.33 plus patch fixes. |
| D9 | Master publishes nothing but 0.33 patches before 1.0.0. |
| D10 | When, and whether, the frozen kernel line is revived or rewritten. Still open. |
| R2, the pause and the freeze | Apply to the snapshot, not to master. Memory is not on the kernel on master. |
| R2, the breaking-fix rule | A fix the bump table rates minor does not land on master. Every master commit ships in a 0.33 patch, so such a fix is recorded as a candidate break for its operation's flow (R5) instead. |
| R3, class K | Fixed on master when the bump table rates the fix patch, and shipped in the next 0.33 patch, with no cherry-pick. Otherwise R2's breaking-fix row applies. |
| R3, class P | Absorbed into D10's host item (D7 here). |
| R4, incorporation by reference | The rule stands, but its one instance leaves: with BE-032 off master, no binding spec incorporates spec 051, so 051 binds no code until a flow implements it. |
| R5 | The register is unchanged. `## v0.33.0 to v1.0.0` in the migration guide holds a break only once its v1 implementation lands. A patch fix's subsection goes under its 0.33 patch's own heading (D5). |
| § Impact, Process | Its reason for leaving CLAUDE.md principle 5 and `store-backend-expert.md` unamended was that spec 051 was the only ground spec and BE-032 incorporated it. Both premises fail, so PR 2 gives both copies R4's exception. PR #1171 drafted that wording. |
| `000-process.md` Rule 5 | Keeps "not removed" with a second exception: a spec file this RFC freezes leaves master. Its section IDs are retired in the ground register (next row), so no ID is reused. They are BE-030 to BE-033. BE-020 and BE-028 return to spec 003 and are not retired. |
| Ground register § Retired IDs | Its lead sentence gains the same second exception. The table keeps its two columns. A frozen ID's Successor cell reads `— (frozen on frozen/kernel-driver, RFC-0025)`. |

RFC-0024 gets an "Amended by RFC-0025" line. RFC-0017, RFC-0021, ADR-0042 and
ADR-0047 each get "Implementation frozen on `frozen/kernel-driver`
(RFC-0025)". RFC-0021's text names `StoreTree.dfy`, run by CI's `verify-formal`
job, as its check: that model leaves master and the job stays (D3). None of
these decisions is withdrawn, and D10 decides whether they stand.

### Delivery

| PR | Content |
|---|---|
| 1 (this one) | This RFC, BK-488 and its trace. On acceptance, the status lines above. |
| 2 | The revert: D2 to D4, D7, the amendments above (Rule 5, the register, the two Rule 3 copies, `CONTRIBUTING.md` § Release, the CLAUDE-REFERENCE rows), and CHANGELOG `[Unreleased]` trimmed to what master ships. |
| 3 | PR #1171 brought up to date: spec 054 renamed to 052 and the register's numbering line (D6), spec 051's Layering pointed at it (D3), and BK-487 closed. |

## Alternatives Considered

The maintainer decided each in this RFC's session:

- **Keep RFC-0024 R2 as it is.** The kernel stays frozen on master: no churn,
  but the costs of § Motivation stay until D10.
- **`git revert` of the kernel commits.** Spec 051, its models and RFC-0021
  landed inside the kernel's first PR (#1127), and #1151 mixes kernel and 0.33
  fixes, so a revert by commit drops ground or keeps kernel. The revert is made
  by path, against v0.33.0.
- **The breaking fixes re-applied too.** That would put two **Breaking** changes
  into code that ships as 0.33 patches.
- **Specs 001 to 050 back to v0.33.0 wholesale.** That loses BUG-337's
  contradiction fixes and stage one's cleanup, which describe 0.33 better.
- **Keep `release/0.33.x`.** Master and the branch would carry nearly the same
  code, with a cherry-pick per fix.
- **Keep the number 054, or number v1 specs separately.** Records keep their
  meaning, but the maintainer prefers a dense sequence, and one line in the
  ground register maps the records.
- **Keep `StoreTree.dfy` on master.** Its encoding half cites spec 053, which
  leaves.

## Impact

- **Public API:** none against v0.33.0. `remote_store.drivers`, `MemoryDriver`
  and `AsyncMemoryDriver` leave master unreleased.
- **Backwards compatibility:** master behaves as v0.33.0 plus three bug fixes.
  BUG-280 changes which exception a refused Local listing raises, and BUG-298
  which keys `*.csv` matches, so both keep a migration-guide note (D5).
- **Testing:** the library suite is v0.33.0's plus the three fixes' tests and
  spec 051's `tests/test_store_tree.py` (D3). Tooling tests stay.
- **Process:**
    - **`000-process.md` Rule 5** and **the ground register's § Retired IDs**
      gain the exception above. The register also gains the numbering line
      (D6) and a record of the pointer edits (D3).
    - **CLAUDE.md principle 5** and **`store-backend-expert.md`** get R4's
      exception (§ Impact row).
    - **`CONTRIBUTING.md` § Release**, including Phase 1's migration-guide
      bullet (D5).
    - **CLAUDE-REFERENCE:** the Breaking change rows (pre-work index and
      detailed checklist), which name `v0.33.0 to v1.0.0` as a master break's
      section, and the rows of the tooling that leaves. GATE-INVENTORY follows
      the tooling.

## Open Questions

1. **Branch protection** for `frozen/kernel-driver`: a repository setting only
   the maintainer can make.
2. **PR #1172** (BK-456 stage three): closed as having no subject, its branch
   kept, or left open as a draft until D10.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md) and
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md).
- [RFC-0017](rfc-0017-contract-kernel-over-thin-drivers.md),
  [ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md),
  [ADR-0047](../adrs/0047-store-tree-key-resolution.md).
- [`CONTRIBUTING.md` § When to bump](../../CONTRIBUTING.md#when-to-bump).
