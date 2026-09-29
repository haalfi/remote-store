# BK-387 — RFC-0017 is Draft with four open questions gating acceptance, and no item owns answering them
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit-021](../audits/audit-021-contract-placement.md)
(PR #1043, merged 2026-09-29) classified the 71 user-audience defects from
v0.28.0 onward and attributed 45 of them (63%) to rules stated once and
re-implemented per backend class. [RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md)
proposes the remedy: one `DriverBackend(Backend)` kernel over thin per-backend
`Driver`s, a session layer for SFTP and Graph, one driver per service, and an
accept-then-migrate lifecycle. The RFC was deliberately left untracked at
filing, because `CLAUDE.md` § Audits leaves the disposition of an audit's
proposals to the user; this item is that disposition, minted once the user
chose to author the ADR.

**Why § 1.** The item is filed under the promise the kernel's own items
serve. Audit-021's appendix places the 13 open cluster-A items by section:
11 in § 1 and 2 in § 2 (its *Section* column, filtered to `Cluster == A`
and `open`), and RFC-0017's ten kernel-owned items (R1) are the root rule,
the absent container and unwrapped listings, which are § 1's "absent or
denied store answers the same way on every backend". The formal-layer
extension (D7) serves § 2 and is the smaller part of the acceptance step.

**What the item owes** is RFC-0017 D8 step 1, and nothing under D3. In the
RFC's own words the step is: accept the RFC as an ADR once Open Questions 1, 4,
6 and 7 are answered and the amendments listed under § Impact are drafted;
acceptance is of the design, D1 to D7 plus those answers. Concretely:

1. **Answer OQ1** (D6): async kernel with a generated sync twin, or a sync-only
   kernel with a driver-level hop and the async surface served by
   `SyncBackendAdapter`; and, under the first, whether sync Azure callers get
   a generated driver or the adapter route, which decides whether the sync
   `AzureBackend` is replaced or retired (D4).
2. **Answer OQ4**: which spec contradictions the kernel adjudicates before it
   encodes them; BUG-240 (ASYNC-014 against DEPTH-003) is the named one.
3. **Answer OQ6**: `classify(exc, op, key)` inside each driver, or a wire
   signal the kernel maps; the eight R4 items are the argument either way.
4. **Answer OQ7**: extend `BackendContract.dfy` and its refinement with the
   root rule, the close posture and the absent container (D7's three "extend"
   rows), or not; and, if extended, where each lives (D7 and OQ7 narrow the
   placement to the trait for two of the three). A "yes" mints a `BK-` item
   for the extensions, which D7 lands before kernel code.
5. **Draft the amendment set** § Impact lists under "Amendments on acceptance":
   the benchmark acceptance band for D8 step 3 (b), stated under
   `benchmarks/` beside the run of record; the ADR amending ADR-0001,
   ADR-0011, ADR-0012 and ADR-0025; and the spec, guide, snippet and
   check-script amendments the same bullet enumerates.
6. **Record the decisions D3 needs before step 1** on the items that carry
   them, not here: BUG-276's arm, BUG-292's fail-open choice, BUG-240's
   reading. Each is an existing open item; a decision written into its body
   is an annotation and owes no trace.

**Inputs that already exist.** The cluster-A assignment (RFC § What each
cluster-A bug becomes, R1 to R6) and the audit's clause table are the
measurements the answers are weighed against; the RFC's Status header says
every figure is pinned to `8fa22d6` and to re-run rather than quote.

**What it does not include.** No kernel code, no driver, no migration: D8
states that nothing under D3 starts before acceptance. The kernel-and-Memory
item (D3 step 1) is minted when this item closes, dependent on the ADR; the
open items § Impact names for re-homing (BK-382, BK-242, BK-325, BK-332,
BUG-266, ID-181, ID-140, BUG-287, 288, 289, ID-217, BK-339) are re-homed or
closed with the disposition, and BK-345, ID-244 and ID-251 become kernel or
driver cells at step 1. BK-366's question is answered by the audit; whether
that closes it is a separate call on its exit criteria.

**Exit criteria:** OQ1, 4, 6 and 7 answered in the RFC; the amendment ADR
accepted and the § Impact amendment set drafted, the benchmark band among
them; RFC-0017's Status moved from Draft to Accepted (or returned to Draft
with the reason, if an answer defeats the design); a `BK-` item for D3 step 1
minted; and, if OQ7 is "extend", a `BK-` item for the Dafny extensions minted.

## Correction (2026-09-29, at close)

Three corrections to the prescription above:

- **The ADR stays Proposed.** The maintainer made acceptance conditional on
  the first backend running on the new design. ADR-0042 is therefore Proposed,
  RFC-0017 stays Draft with its questions answered, and both become Accepted
  in BK-389's PR (D3 step 1). RFC-0017 D8 was amended to match.
- **The amendment set is split by where each amendment becomes true**
  (`CLAUDE.md` principle 3). This item shipped the benchmark band and the ADR.
  Spec 003, spec 005, the guide, its check script and the homepage snippet
  moved to BK-389. The other specs went to BK-390, the remainder under
  § Completing work's "partly done".
- **Items minted:** BK-388 for the Dafny extensions, BK-389 for D3 step 1 and
  BK-390 for the remainder.

Not done here, and left as the paragraph above describes it: the re-homing of
the open items § Impact names. The decisions recorded on BUG-240, BUG-276 and
BUG-292 sit in those items' own dossiers.
