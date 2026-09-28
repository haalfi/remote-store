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

## Moved from the § 6 preamble

Verbatim from the section preamble the conversion removed, links re-based to
this directory: its research pointer and the qualification that depends on it,
moved together as [ADR-0040 § Section Promises](../adrs/0040-backlog-as-index.md)
anticipated. Glosses: "that research doc" is
`research-inconsistency-detection-multi-artifact.md`; "recorded here" meant the
§ 6 preamble; "ID-207 below" is this item; "this programme" is § 6's
cross-artifact consistency work; "§ 1" is that research doc's § 1.

The argument and gap ranking behind
the programme:
[research](../research/research-inconsistency-detection-multi-artifact.md) § 9.

**Measured qualification on that research doc's ranking**, recorded here
because [`000-process.md` § Document types](../000-process.md) makes a research doc
a point-in-time snapshot rather than a living one. It designates the
canonical claim space — research § 9 step 2, which ID-207 used to carry — as
the strategic item. That step builds an *omission detector*, research § 1 class
E. BK-324's four instances were class A/C/D: one claim restated in several homes
and updated in one. So step 2 is **not** what would have caught anything this
programme has actually caught, which is why ID-207 below is scoped to steps 3
and 4 and step 2 is gone. Detecting the rest needs semantic comparison of prose,
which § 1 marks as having no general oracle. The mechanisms that did catch them
were an author-side sibling sweep ([BK-336](../BACKLOG-DONE.md)) and running the
code rather than reading the diff ([BK-344](../BACKLOG-DONE.md) and
[BK-338](../BACKLOG-DONE.md)) — neither in the research doc's ranking.

## Correction, 2026-09-28

The moved qualification says "BK-324's four instances were class A/C/D", but
the research doc's class table places BK-324 facet 4 in class E, silent
omission (`research-inconsistency-detection-multi-artifact.md:127`, via
`rg -n 'BK-324' sdd/research/research-inconsistency-detection-multi-artifact.md`),
and its step 2 names facet 4 as what it closes (`:982`). The body above
records the design investigation's result that step 2 would have caught none of
the four; the two statements are left side by side rather than reconciled here.
Figures above re-derived with `python scripts/check_formal_trace.py`: 938
declared sections (the body says 933), 26 Dafny-tagged IDs and 94 tag sites
unchanged. The "~11,800 citations across 518 files" names no derivation and
was not reproduced. Found by the ADR-0040 § 6 conversion.
