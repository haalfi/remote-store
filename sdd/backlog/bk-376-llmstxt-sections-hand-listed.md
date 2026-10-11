# BK-376 — Half the llmstxt `sections:` map is hand-listed, and four published pages are already missing from both outputs
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BK-327's defect one surface further out. `mkdocs.yml` gives the `llmstxt`
plugin a `sections:` map whose four entries fall into three shapes:
`Tutorial` and `Guides` are globs that maintain themselves; `Explanation` is
hand-listed page-by-page, for a stated reason (an `explanation/*.md` fnmatch
glob would also pull the contributor-facing `explanation/design/` subtree);
and `Reference` is **mixed** — `reference/api/*.md` is a recursive glob, the
other four entries are hand-listed, and no reason is given for the split.
The hand-listed halves are where pages go missing.
Nothing differences those lists against `_nav.yml`, so a new
page is published, navigable, and silently absent from **both** bundles a
coding agent reads: `mkdocs.yml:61` sets `full_output: llms-full.txt` on the
same plugin instance that carries the map, so `llms.txt` loses the link and
`llms-full.txt` loses the page's entire text. `llms-api.txt` is **out of
scope** and stays that way: `scripts/docs/gen_llms_api.sh` builds it from
`src/` with `lx`, out of `.readthedocs.yaml`'s `post_build`, and never reads
`sections:`.
**Three pages are absent today.** `mkdocs.yml:113-119` lists six
`Explanation` pages while `docs-src/explanation/_nav.yml` declares eight plus
`design/`, so `contributing.md` and `development-story.md` have no entry.
`docs-src/reference/_nav.yml` declares five pages plus `api/`, and
`mkdocs.yml` hand-lists four of the five (`capabilities-matrix.md`,
`migration.md`, `tested-versions.md`, `FEATURES.md`), leaving
`reference/changelog.md` as the only omission — `api/` is covered by the
recursive `reference/api/*.md` glob the comment at `mkdocs.yml:92-96`
explains. The changelog is the one that costs, and it costs most in
`llms-full.txt`: "what changed in 0.32.0" is a question agents ask, and the
bundle that exists to carry the answer's *text* omits it, not merely the link
to it.
**The gap is not knowing which of the three are decisions.** All three are
plausibly deliberate — two are project meta, the third is long and churns —
but `mkdocs.yml`'s comments explain only the `design/` exclusion and the
omitted section-landing stubs, so a reader cannot tell a choice from an
oversight. That is the defect, and it is the same one BK-327 names for the
nav: the omission is invisible either way.
**Fix shape follows BK-327's.** A check differencing each hand-listed
`sections:` entry against the corresponding `_nav.yml`, with an explicit
opt-out list in `mkdocs.yml` carrying a reason per excluded page — so the
three above become declared exclusions or become entries, and the next one
cannot be neither. The open choice is **one check or two**: BK-327's fix
shape already claims a new gate in `check_docs_framework.py`, so this either
folds into that same check or takes its own ID beside it. Folding is the likely economy, since both difference
emitted pages against `_nav.yml`.
**Measured, not hypothetical:** `explanation/dependency-policy.md` (BK-371)
had to be added to this list by hand, and was caught by reading the config
rather than by any gate.

## Correction, 2026-09-27

Four pages, not three. Matching every published page against the
`sections:` patterns (`mkdocs.yml:97-119`, fnmatch as the plugin expands them)
leaves `index.md`, the home page, unmatched as well. The page set was every
`docs-src/**/*.md` plus what `scripts/docs/scan.py` makes the build emit:
dual-file dests, scanned `sdd/` pages, `_index.tmpl` index pages and example
pages, 325 in all; six non-design pages match no pattern, two of them the
stubs below. No comment in the plugin block names `index.md`: the `markdown_description` note (`mkdocs.yml:62-65`)
covers the positioning blurb, and the stub note (`:108-112`) covers the
section-landing `explanation/index.md` and `reference/index.md` only. The other
three re-derive as stated. The index title changed with this correction. Found
by the ADR-0040 § 3 conversion.
