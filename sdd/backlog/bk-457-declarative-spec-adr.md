# BK-457 — Specs prescribe how a check runs where they should state what the caller observes
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

**Evidence, measured at BK-449's branch head, 2026-10-17.**

- Mechanism in the spec: `git grep -n -i "probe set" sdd/specs/003-backend-adapter-contract.md`
  hits BE-032 (lines 1605 to 2002 at that head), which prescribes the probe set,
  what follows a refusal in it per call, and a table of which `stat` runs when.
  BE-021 is 557 lines, much of it per-backend remapping that is each driver's
  `classify`.
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

**Prescription** (advisory):

- An ADR: a spec states preconditions, postconditions, observable side effects
  and error precedence; a sentence that tells a driver how to reach an outcome
  is moved to the driver or deleted. Behavioural profiles are named and declared
  (a capability, or the kernel's existing flag); the contract is universal and
  the profile decides when it is validated. Wire-call bounds become a cost
  statement per profile. A lemma governs where one exists (Rule 7 extended, Rule
  3 amended, not superseded).
- Then BK-456 splits spec 003 and prunes each file against it, a file per PR so
  each prune is reviewable on its own.
