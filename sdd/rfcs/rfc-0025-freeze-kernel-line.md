# RFC-0025: Master returns to 0.33.0's code; the kernel line is frozen on a branch

## Status

Draft, 2026-10-25. Tracked as **BK-488**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) R1's D2, D9 and D10 rows, R2 and R3's
class P disposition. Decisions taken in this RFC's session: decision log
`sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl`.

## Summary

**Master's library code goes back to v0.33.0 plus four non-breaking 0.33
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

`src/` and the library tests return to v0.33.0. Four 0.33 fixes made since are
re-applied, each a bug fix the bump table rates patch: BUG-280 (Local listing
errors), BUG-298 (glob `$` anchoring), BUG-330 (sync adapter truncation) and
BUG-333 (`open_atomic` on a strided `memoryview`). BK-405 (glob patterns read as
paths) and BUG-329 (metadata must be a mapping), both **Breaking**, stay on the
snapshot with their migration-guide subsections and CHANGELOG lines. Their
behaviour returns through the flow of the operation it concerns, as a candidate
break record (RFC-0024 § R5).

### D3. Specs and formal models

- **Specs 052 and 053 leave master.**
- **In specs 001 to 050 only the kernel's edits are reverted.** Spec 003 returns
  to its text before BK-456's split, so BE-020 and BE-028 are back in it with
  unchanged meaning. Specs 013, 029 and the others lose their kernel sections.
  The process and correctness edits made since stay: BUG-337's contradictions,
  BK-456 stage one, the formatting fixes. The per-file list is the revert's
  derivation, recorded in its trace.
- **Formal models.** `StoreTree.dfy`, `KernelProtocol.dfy` and its generated
  oracle, and the kernel parts of `BackendContract.dfy` and `MemoryBackend.dfy`
  leave with the kernel. Spec 051, its Lean and Alloy models and their TeX
  account stay: they are ground.

### D4. Tooling and docs

Tooling that serves only the kernel leaves with it: `gen_sync_kernel.py`,
`gen_protocol_diagram.py`, `tests/_kernel/`, the driver checks of
`check_custom_backend_guide.py`, and the CI steps and gate rows that run them.
The `remote_store.drivers` API page and the custom-backend guide return to
v0.33.0. `remote_store.drivers` was never released, so no user loses it. Process
tooling stays.

### D5. One release line

`release/0.33.x` is retired. 0.33 patch releases are tagged from master and take
what the bump table rates patch or no bump, until v1 implementation begins on
master. A v1 flow that changes `src/` first cuts a `release/0.33.x` branch from
the last 0.33 tag, and RFC-0024's D2 and D9 apply from then on. Until then:

- A fix needs no cherry-pick.
- Master's suite is the 0.33 record for D8's comparisons, and R2's "the branch's
  suite, not master's" no longer applies.
- `CONTRIBUTING.md` § Release says so, and the migration guide's section for an
  unreleased fix is the next 0.33 patch's.

### D6. Spec numbering

Spec 054, the store key of PR #1171, becomes spec 052, once spec 052 has left
master. Its section IDs do not change. Records written before this RFC that cite
"spec 052" or "spec 053" mean the frozen specs. The ground register says so in
one line, since those records are never edited. No section ID changes meaning:
BE-020 and BE-028 return to spec 003 as they were, and BE-030 to BE-033 retire
with the snapshot and are not reused.

### D7. Backlog

- **Kernel and driver items.** The open items about kernel, driver,
  `Session` or migration work (RFC-0024 R3's class P) are absorbed into one
  host item, reviving or rewriting the frozen line, which is D10. Its dossier
  lists each absorbed ID with its diagnosis.
- **BK-456.** Its stage two is reverted with spec 003, and its stage three
  (PR #1172, the prune of spec 052) has no subject left.
- **BK-435.** Its open work on `StoreTree.dfy` is parked with that model.

### What changes in RFC-0024

| Clause | Becomes |
|---|---|
| D2 | Spec work runs on master. Until v1 implementation begins there, so do 0.33 patches (D5 here). |
| D9 | Master publishes nothing but 0.33 patches before 1.0.0. |
| D10 | When, and whether, the frozen kernel line is revived or rewritten. Still open. |
| R2 | The pause and the freeze apply to the snapshot, not to master. Memory is not on the kernel on master. |
| R3, class P | Absorbed into D10's host item (D7 here). |

RFC-0024 gets an "Amended by RFC-0025" line. RFC-0017, ADR-0042 and ADR-0047
each get "Implementation frozen on `frozen/kernel-driver` (RFC-0025)". Their
decisions are not withdrawn, and D10 decides whether they stand.

### Delivery

| PR | Content |
|---|---|
| 1 (this one) | This RFC, BK-488 and its trace. On acceptance, the status lines above. |
| 2 | The revert: D2 to D4 and D7, the CHANGELOG `[Unreleased]` trimmed to what master ships, `CONTRIBUTING.md` § Release (D5). |
| 3 | PR #1171 brought up to date: spec 054 renamed to 052 (D6). |

## Alternatives Considered

The maintainer decided each in this RFC's session:

- **Keep RFC-0024 R2 as it is.** The kernel stays frozen on master: no churn,
  but the costs of § Motivation stay until D10.
- **`git revert` of the kernel commits.** Spec 051, its models and RFC-0021
  landed inside the kernel's first PR (#1127), and #1151 mixes kernel and 0.33
  fixes, so a revert by commit drops ground or keeps kernel. The revert is made
  by path, against v0.33.0.
- **All six fixes re-applied.** That would put two **Breaking** changes into
  code that ships as 0.33 patches.
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
- **Backwards compatibility:** master behaves as v0.33.0 plus four bug fixes.
  BUG-280 changes which exception a refused Local listing raises, so it keeps its
  migration-guide subsection.
- **Testing:** the library suite is v0.33.0's plus the four fixes' tests.
  Tooling tests stay.
- **Process:** `CONTRIBUTING.md` § Release, the ground register's numbering
  line, the CLAUDE-REFERENCE and GATE-INVENTORY rows of the tooling that
  leaves.

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
