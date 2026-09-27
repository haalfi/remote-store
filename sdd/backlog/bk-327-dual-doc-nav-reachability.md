# BK-327 — Gate dual-doc nav reachability and index listing
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

A `<!-- doc: dual dest=explanation/design/*.md -->` marker publishes a page that
neither the docs-site nav nor the section index page lists, and nothing catches
either omission — so a published page a user cannot navigate to is a page they
never read. `mkdocs.yml` sets only `validation: links: not_found: warn`, so
`nav.omitted_files` stays at its INFO default and `--strict` cannot promote it;
`scripts/docs/nav.py` builds `SUMMARY.md` *from* `_nav.yml` and never diffs it
against the pages `gen_pages.py` emitted; the `_index.tmpl` Documents list is
hand-written and unchecked. So `hatch run docs-gate` goes green on a page that is
unreachable, unlisted, or both. Each surface had a live instance repaired by hand
in PR #938: `drift-rules` was absent from both, `ci-operations` was in `_nav.yml`
and absent from `_index.tmpl`.
Fix shape: a G-08 in `scripts/check_docs_framework.py` differencing emitted dual
`dest` paths against both `_nav.yml` and the `_index.tmpl` Documents list;
raising `nav.omitted_files` to WARNING covers the nav half only.
An unstated bound on `docs-gate` being trusted past its range
([`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate)).

## Re-measured, 2026-09-27

No instance is live today; the unchecked gap is. `rg -n '^<!-- doc: dual
dest=explanation/design/' sdd` finds eight markers on line 2 of their files
(the ninth hit, `AUTHORING.md:88`, is example text), and all eight appear in
both `docs-src/explanation/design/_nav.yml` (lines 1-8) and `_index.tmpl`'s
Documents list (lines 7-14). `check_docs_framework.py` still defines G-01
through G-07 only. Found by the ADR-0040 § 3 conversion.
