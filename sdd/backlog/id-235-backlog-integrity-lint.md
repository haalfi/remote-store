# ID-235 — Backlog-file integrity lint (structure and inbound tracker citations)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Two passes over the same artifact, in the same script family, sharing one
wiring trap. Home: extend `scripts/gen_backlogid.py` and
`scripts/check_no_tracker_refs.py`, both of which already parse the ID
pattern and already know both backlog files.
- **Structural integrity.** A string-anchored edit swallowed an entry header
  in `BACKLOG-DONE.md` (PR #932), merging two items — and because
  `gen_backlogid.py` derives IDs from headers, the stale JSON was masked too.
  Lint the structure: every metadata line follows an entry header, headers
  unique across both files, BACKLOG-DONE status `[x]` only.
  **And no merge-conflict marker survives**: a rebase of BK-378's branch left
  a `<<<<<<< HEAD` line above an item in this file, and `docs-gate` passed
  twice with it there (neither `gen_backlogid.py` nor `mkdocs --strict` reads
  the line). A `^(<{7}|={7}|>{7})` scan over both files is the cheapest rule
  in this list and the one a rebase-heavy workflow needs most.
  **Add the retirement sections to the structural rules**: every entry under
  `BACKLOG-DONE.md` § Absorbed names a host that exists in `BACKLOG.md`, and
  every ID retired by either route appears exactly once across both files.
  That is what keeps the ID space safe by construction rather than by whoever
  last remembered to add an entry.
  **ADR-0040's four shape rules are in this pass**, all shipped under
  BK-365: R1 (attribute vocabulary), R2 (item cap) and R3 (section shape)
  on sections without the `unconverted` marker, R4 (dossier link) on all.
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
  ([DRIFT-RULES Rule 2](../DRIFT-RULES.md#localize): localize, don't merely fail).
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
([`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate)).
**Note the wiring trap BK-333 documents:** a check reading `sdd/` must reach a
gate an `sdd/`-only change actually runs. This item is a live instance of its
own subject — the deletions that produced this file's current shape are
exactly the event the second pass exists to catch.

## Correction, 2026-09-28

Two statements about existing scripts are false. R1 is not scoped to converted
sections: `_attribute_violations` runs over the whole active file
(`scripts/gen_backlogid.py:366`); only R2 and R3 skip a marked section. And
`check_no_tracker_refs.py` never opens either backlog file: its two mentions
of `BACKLOG` are prose (`rg -n BACKLOG scripts/check_no_tracker_refs.py`, lines
38 and 448). Re-derived with a scratch script over the two files: all 687
`BACKLOG-DONE.md` headers are `[x]`, 200 of its entries carry an attribute line
(so `gen_backlogid.py`'s "entries carry no attribute line" is false too),
neither file holds a conflict marker (`rg -c '^(<{7}|={7}|>{7})'
sdd/BACKLOG.md sdd/BACKLOG-DONE.md` prints nothing), and the § Absorbed
register's ten entries name seven hosts,
all seven open (`rg -c` over their headers in `BACKLOG.md` gives 7). So those
rules would land green; "headers unique across both files" would fail on
BK-385's four pairs, which repeat inside `BACKLOG-DONE.md`. Over the 50
spec files, 33 cite 206 backlog IDs, 102 distinct, 91 of them in
`BACKLOG-DONE.md`, none dangling (the body's 166/80/28/69 is older). Found by the ADR-0040 § 6 conversion.
