# ID-207 — Push `check_formal_trace.py` past citation hygiene (steps 3 and 4 only)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

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
([`000-process.md` Rule 5](../000-process.md#rules)) on which ~11,800 citations
across 518 files depend. Step 1 (derive D mechanically from contract `ensures`)
goes with it, being step 2's precondition.
**Do not re-file the dropped half without new evidence** — the measurement
above is the reason, and it is recorded here so the argument is not had twice.
