# BK-362 — A `repo-only` marker does not stop the docs bridge claiming the file
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

[`AUTHORING.md`](../AUTHORING.md#file-classification) Rule 1 says a per-file
marker overrides the directory default, and for classification it does. The nav
and the design index do not consult it: they are generated from the `glob` in
each `sdd_kinds` entry of [`docs-src/_path_rules.yml`](../../docs-src/_path_rules.yml),
so a file matching `research-*.md` is claimed for the nav even when its marker
says `repo-only` and the bridge therefore emits no page.
**Measured, not predicted.** Adding a repo-only `research-*.md` produced four
strict-build failures — one `nav` reference and three links, from `SUMMARY.md`,
`explanation/design/index.md` and `explanation/design/research/index.md` —
each naming a page the bridge had correctly declined to emit. The file was
reverted; the tooling gap was not, which is why this item exists rather than a
paragraph in a merged PR description.
**The gate that should catch it does not.** `check_docs_framework.py` passes in
that state, reporting all seven of G-01..G-07 green, because classification is
in fact correct; only `docs-build --strict` aborts. So the fast checker is
wired and blind, which is the shape BK-333 documents for gate routing,
arriving here as a checker that runs and does not look.
**A precedented fix exists and is per-file.** `sdd/adrs/DIGEST.md` carries both
a `repo-only` marker and a `skip_stems` entry, and the pair is what works. That
is the disposition to weigh against: teach the generator to read markers, or
keep `skip_stems` and document the pairing where an author will meet it. The
second is cheaper and silently fails the next author who does not know.

## Re-measured, 2026-09-28

Holds. `scripts/docs/scan.py`'s `_scan_kind` consults only `skip_stems`, never
the marker, while `_scan_kind_for_dual` honours `repo-only`; a probe file with
the marker, fed through both, lands in the nav and index lists and in no dual
page. Latent today: the one marked file under a scanned kind,
`adrs/DIGEST.md`, is also in `skip_stems`. `scripts/check_sdd_index.py:47-51`
now documents this item as a bound, which is not a fix. Found by the ADR-0040 § 6 conversion.
