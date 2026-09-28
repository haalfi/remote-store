# ID-225 — Evaluate migrating the docs stack from Material for MkDocs to Zensical
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Our docs foundation is entering maintenance mode as its authors converge on a
successor. [Material for MkDocs is feature-frozen](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
(critical bug/security fixes for ~12 months, no new features), MkDocs 1.x is
itself being forked (a `properdocs` MkDocs-1.x continuation now surfaces as a
transitive docs dep, and a build-time banner warns MkDocs 2.0 will break all
plugins/themes), and `mkdocs-llmstxt` (adopted in ID-220) is in maintenance
mode for the same reason. The whole ecosystem is pointing at
[**Zensical**](https://github.com/zensical/zensical) — a new MIT static site
generator (Rust core, reads `mkdocs.yml` natively, with a migration path) built
by the Material team. Crucially, `mkdocstrings`' author is rebuilding
API-reference-from-docstrings *inside* Zensical — the exact capability our docs
depend on `mkdocstrings` for.
**Not prioritized:** Zensical is pre-1.0 and does **not** yet ship the
API-reference feature we require, so "not yet — revisit when Zensical reaches
API-reference parity" is a legitimate outcome. Kept visible here as the
**sunset trigger for the interim `mkdocs-llmstxt` adoption (ID-220)**, which is
recorded nowhere else: when the migration lands, the HTML→Markdown plugin is a
prime candidate for replacement by a native feature.
**Scope when picked up:** trial `zensical build` against our `mkdocs.yml`;
confirm parity for the pieces we rely on (gen-files pages, mkdocstrings API
reference, literate-nav order, BK-171 link rewrites, mike/RTD versioning); and
fold in native `llms.txt` / `llms-full.txt` generation if Zensical ships it.
Background: [research](../research/research-llms-full-txt-tooling.md).

## Correction, 2026-09-28

"Recorded nowhere else" is false: `mkdocs.yml:56-57` names the sunset at the
Material-to-Zensical migration (ID-225), `pyproject.toml:206` tags the
`mkdocs-llmstxt` pin with it, and the research doc linked above covers it
(`rg -n 'ID-225' mkdocs.yml pyproject.toml`). The MkDocs 2.0 and ProperDocs
warning is printed by every `mkdocs build --strict`, observed in this
conversion's own `hatch run docs-gate`. Found by the ADR-0040 § 5 conversion.
