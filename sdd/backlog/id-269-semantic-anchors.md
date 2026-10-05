# ID-269 — Mechanisms the repo defines in its own words have established names it never uses
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and advisory
prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Origin.** Evaluation of the Semantic Anchors project's Claude Code installer
(`LLM-Coding/Semantic-Anchors`, `docs/agent-installation.adoc`). The installer
was rejected: it writes a managed definition block into `CLAUDE.md` and
`AGENTS.md`, which copies definitions (principle 4), touches a file `CLAUDE.md`
says to ignore, and helps mainly small models. The catalogue's names were kept
as the idea worth taking: naming a published method lets a reader, human or
model, recall the whole method from one phrase.

## Evidence, measured 2026-10-05

**Catalogue.** Shallow clone of `LLM-Coding/Semantic-Anchors` at `749f20f`
(2026-10-03): `docs/anchors/` holds 461 files, which is 230 anchors in English
and German plus `_template`, counted with `os.listdir`.

**Repo hits.** 58 anchor terms hand-picked for relevance, each a regex counted
over every `.md`, `.py`, `.yml` and `.toml` file under the repo root, skipping
`.git`, `.venv`, `node_modules`, `site`, `tmp` and `htmlcov`; acronyms (MECE,
MADR, EARS, STRIDE, BLUF, FMEA, ADR, YAGNI) match case-sensitively, the rest
ignore case. At base `5971a7a`, 38 of 58 had zero hits. After this item is
filed, the count drops to 35: BLUF, Fagan and premortem match this item's own
index text, not a use.

Already in use (hits / files at `5971a7a`): ADR 1725/320, property-based or
`hypothesis` 186/57, Diátaxis 67/18, single source of truth 62/44, mutation
testing 44/18, SemVer 11/7, test doubles 5/4, Keep a Changelog 3/3.

## Shortlist (advisory)

Each names a mechanism the repo already has, so the anchor adds a name, not a rule.

| Anchor | Pattern counted | Where it applies |
| --- | --- | --- |
| BLUF, Pyramid Principle (Minto) | `\bBLUF\b`, `pyramid principle\|minto` | [`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz): lead with the core claim in at most three sentences |
| Fagan inspection, Premortem, Devil's Advocate | `fagan`, `pre-?mortem`, `devil'?s advocate` | [ADR-0035](../adrs/0035-vary-method-not-model.md), [ADR-0036](../adrs/0036-reviewers-by-subject-and-method.md): reviewers picked by method |
| EARS | `\bEARS\b` | Spec clause wording in `sdd/specs/` |
| TDD Chicago vs. London school | `chicago school\|classicist`, `london school` | `sdd/TESTING.md` mock discipline |
| Fallacies of Distributed Computing | `fallacies of distributed` | Backend reviews (S3, SFTP, Azure) |
| Chesterton's Fence | `chesterton` | Removals and refactors; principle 2 |
| Goodhart's Law (4 hits, 1 file, research only) | `goodhart` | Coverage gate; [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md) derived figures |

**Further candidates, unassessed.** The user asked to keep the list open. Zero
hits at `5971a7a`, each plausibly naming something present: Arrange-Act-Assert,
Testing Pyramid, Postel's Law (path and config parsing), Locality of Behaviour,
Command-Query Separation, Least Privilege and STRIDE (credential masking),
Poka-yoke (commit and push gates), Mikado Method, Tracer Bullet, Strangler Fig,
MECE (audit and review breakdowns). Deep Modules and Design by Contract have
research-only hits.

**Rejected.** Conventional Commits: it conflicts with the backlog-ID commit
prefix in `CLAUDE.md` § Backlog.

## Open decision

Which anchors to name, and where: inline in the document that owns each
mechanism (no indirection, but scattered), or one glossary in
`sdd/CLAUDE-REFERENCE.md` that maps anchor to mechanism and links to it (one
place, one more hop). Either way, the name goes beside the existing rule,
never instead of it: the repo's rule is the authority, the anchor is a pointer.
