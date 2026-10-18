# BK-457 — No rule says what a spec owes, where it ends, which form it takes, or which layer governs it
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** An external AI review of spec 003 the maintainer
brought into PR #1159 (BK-449), and agreed with on its main point: the spec
"attempts to use prose to mandate internal algorithmic determinism (like
error-path probe counts and precise sequencing of checks) rather than pure
boundary invariants". Its four proposals: declarative pre- and postconditions
instead of how-to prose; formal behavioural profiles instead of one forced
check sequence; the executable models (Dafny, Hypothesis) as the normative
specification; and the kernel protocol scoped to lifecycles. The maintainer's
choices, recorded in `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl`:
"ADR first, then BK-456", and "Lemma governs where it exists".

**Evidence, checked at BK-449's branch head, 2026-10-17.**

- Mechanism in the spec: `git grep -n -i "probe set" sdd/specs/003-backend-adapter-contract.md`
  hits BE-032, which prescribes the probe set, what follows a refusal in it per
  call, and a table of which `stat` runs when. BE-021, one of the spec's largest
  sections (BK-456 gives the sizing command), is mostly per-backend remapping
  that is each driver's `classify`.
- Profiles exist unnamed: BE-032's probe table has a hierarchical / flat
  column, and the kernel branches on `_flat`.
- The authority order today: `sdd/000-process.md` Rule 3 ("Specs are
  authoritative") and Rule 7 (prose carries no presumption against a verified
  postcondition or an unasserted claim).

**Where the review needs qualifying** (BK-449's assessment, for the ADR to
weigh, not settled):

- Some sequencing is contract. Which refusal a caller sees when two hold (a
  capability gate against the closed guard, BE-030's gate order) is observable;
  the ADR keeps it, stated as error precedence, not as an order of steps.
- Wire counts are partly a cost promise on remote backends (`FEATURES.md` has a
  cost table): moved to a per-profile cost statement, not deleted.
- "Models normative" in full would supersede Rule 3 and leave every clause
  without a model with no normative home; the chosen form is narrower: where a
  lemma exists it governs, and the prose states the invariant in a sentence and
  links it.
- BE-033 (BK-449) is already lifecycle-scoped: ownership, transitions,
  cancellation. Its most detailed rows (the temporary's `NotFound` carve-out)
  decide an observable log, so they are postconditions.

**A second review** (Gemini, brought by the maintainer to the same PR, filed
here by the maintainer's choice, same decision log: "Into BK-457 and BK-450")
raised two questions for this ADR, checked against the code on 2026-10-17:

- *"Forcing flat namespaces to run ancestor stat walks before every write."*
  Not so on the kernel: the refusal path walks ancestors only when
  `driver.namespace` is hierarchical (`walk=not self._flat` in
  `_write_refused`), and a flat folder operation spends one `stat` on the key
  itself (BE-032 A.3, `_flat_item`). The S3 and Azure specs carry no ancestor
  pre-check; SQL blob, not yet on the kernel, does (SQL-BLOB-031). The profile
  it asks for exists as `driver.namespace` and is unnamed in the specs. Its
  further proposal, marker objects (`key/`, zero bytes) behind an opt-in
  strict-tree flag, writes new objects other tools would see: a design option
  for the ADR, not a fix.
- *"Tolerant deletes spend a speculative probe."* Accurate: BE-021 has
  `delete(path, missing_ok=True)` on an absent key spend one `MaxKeys=1`
  listing (the "is this a folder?" row), because type mismatch outranks
  `missing_ok`, a verified Dafny postcondition (`Delete: IsDir → InvalidPath`
  whatever `missing_ok`). The proposal, `NotFound` unless a strict flag is set,
  changes behaviour (`delete(folder, missing_ok=True)` returns quietly on a
  flat backend). Open question for the ADR: whether type strictness on tolerant
  calls is per profile, against its wire cost.

**Scope widened, 2026-10-18.** A maintainer session walked one operation, a
streaming read, from key to bytes, and found the spec-003 symptom is one case
of a missing design rule: nothing says where one spec ends (the read crosses
key admission, scoping, one call's outcome, a handle's lifetime, a concurrent
writer and retry), which form a lifecycle takes (the template in
`000-process.md` § Spec format narrates it), or which formal layer governs a
kind of truth. Spec 051 was taken as the exemplar; its status prose was the one
defect found and fixed. The maintainer chose to rewrite this item rather than
file a parent, and to compile the session into an RFC that graduates to one ADR
and one guide (decision log
`sdd/decisions/6b9890d9-f718-508d-b861-aef8c0398c78.jsonl`).

**Prescription** (advisory):

- [RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md) carries the proposal.
  This dossier's earlier prescription (postconditions and error precedence, not
  recipes; named profiles; wire-call bounds as a per-profile cost; a lemma
  governs where one exists, Rule 7 extended, Rule 3 amended, not superseded) is
  its D1, D5 and D6.
- Then BK-456 splits spec 003 by kind of truth (RFC-0022 D3) and prunes each
  file against D1, a file per PR so each prune is reviewable on its own.
