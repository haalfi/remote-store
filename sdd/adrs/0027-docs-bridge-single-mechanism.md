# ADR-0027: Single-Bridge Documentation Pipeline with Inline Classification

## Status

Draft

## Context

[BK-167](../BACKLOG-DONE.md) defined the documentation framework as three
authority docs ([`AUTHORING.md`](../AUTHORING.md) → placement,
[`DOCUMENTATION.md`](../DOCUMENTATION.md) → structure,
[`CONTENT-RULES.md`](../CONTENT-RULES.md) → longevity).
[`AUTHORING.md`](../AUTHORING.md) Rule 4 states: "exactly one bridge applies;
new mechanisms are not added to handle special cases." Today three coexist.

[Audit-012](../audits/audit-012-docs-structure.md) F-12 enumerates them:

| Files | Mechanism | Layer |
|---|---|---|
| `docs-src/design/{authoring,content-rules,design,documentation,testing}.md` | `include-markdown` Jinja wrappers | MkDocs plugin |
| `CONTRIBUTING.md`, `sdd/000-process.md` | `docs-src/_link_map.yml` consumed by `render.render_link_rewritten` | `gen-files` |
| `sdd/{adrs,specs,rfcs,audits,research}/` subdirs | `render.render_sdd_wrappers` filesystem scan | `gen-files` |

The wrapper files render as raw Jinja text in the GitHub repo browser
(F-02); virtual-page links break in repo navigation (F-01); excluded files
are not auditable from any single source (F-13); `_link_map.yml`'s scope
contradicts its own contents (F-11).

[BK-167a](../BACKLOG.md#bk-167a) calls for one bridge. `LinkResolver`
([scripts/docs/link.py](../../scripts/docs/link.py)) already does the
shared work — rewriting relative links per a source→dest map and falling
back to GitHub blob URLs. The three mechanisms differ only in **how they
discover the source→dest pair**, not in what they do with it.

### Constraints from the framework

- AUTHORING Rule 1: every `.md` belongs to exactly one class (repo-only,
  docs-only, dual; default dual). Files may carry an explicit class
  marker; absence means dual.
- AUTHORING Rule 2: each `.md` lives at exactly one path; presentations
  are derived, never copied.
- AUTHORING Rule 3: dual files are plain Markdown (`--8<--` snippet
  includes excepted by [CONTENT-RULES Rule 6](../CONTENT-RULES.md#rules)).
- AUTHORING Rule 5: a PR-blocking check enforces every framework rule.

### Q4 from BK-167a: classification storage

Two candidates:

1. **Central manifest** (e.g. `docs-src/_classification.yml`): single
   auditable file, one place to read; but a second source of truth that
   can drift from disk.
2. **Inline marker on each file**: class lives next to the file; no drift
   surface; absence == dual default falls out for free.

## Decision

**Adopt one bridge with inline HTML-comment classification markers, plus a
PR-time gate that enforces every framework rule.**

### The bridge

Replace `scan.scan_include_wrappers` and `scan.load_link_map` with one
scanner `scan.scan_dual_files(repo_root)` that walks every `.md` in the
repository and yields `(source: Path, dest: str | None, klass: str)`.

- Existing SDD subdir scans (`scan.scan_all_sdd`) keep their declarative
  config — they already produce the `(source, dest)` pair from a directory
  convention. They are part of the single bridge: the convention IS the
  classification rule for those directories.
- All other `.md` files are classified by an inline marker (see below) or
  by the dual default.
- `render.render_dual_pages(writer, dual_entries, resolver)` replaces
  both `render_link_rewritten` (gone) and the include-markdown wrappers
  (deleted).

### Classification marker

Each `.md` file may carry an HTML-comment marker on its first content line
(after the `# Title` header is allowed):

```markdown
<!-- doc: dual dest=design/authoring.md -->
<!-- doc: repo-only -->
<!-- doc: docs-only -->
```

- Plain Markdown — invisible in GitHub repo browser, parseable in 8 lines
  of regex code.
- Absence ⇒ dual (the safe default per AUTHORING Rule 1).
- For SDD subdirs (`adrs/`, `specs/`, `rfcs/`, `audits/`, `research/`),
  the directory convention determines `dest`; an inline marker is not
  required and not used.
- Top-level `sdd/*.md` files (DESIGN, DOCUMENTATION, TESTING,
  CONTENT-RULES, AUTHORING, 000-process) carry `dual dest=design/<slug>.md`.
- Root-level files: README, CHANGELOG, CONTRIBUTING, DEVELOPMENT_STORY
  carry `dual dest=...`. CLAUDE, CODE_OF_CONDUCT, SECURITY, AGENTS carry
  `repo-only`. BACKLOG, BACKLOG-DONE, CLAUDE-REFERENCE carry `repo-only`.
- `docs-src/**/*.md` carry `docs-only` implicitly by location.

### What gets deleted

- `docs-src/design/authoring.md`, `content-rules.md`, `design.md`,
  `documentation.md`, `testing.md` — five include-markdown wrappers.
- `docs-src/_link_map.yml` and `scripts/docs/scan.py:load_link_map` and
  `scripts/docs/render.py:render_link_rewritten`.
- `scripts/docs/scan.py:scan_include_wrappers` (superseded by
  `scan_dual_files`).

### The gate

`scripts/check_docs_framework.py` runs as part of `hatch run all`. It
emits one failure line per violation, returns nonzero on any. The
[spec](../specs/047-docs-framework-tooling.md) defines the exact rules;
this ADR records the enforcement-by-tooling decision.

### Q2 (move sdd/?) — no

Skills, agents, ripple-check tables, external links, and BACKLOG items
all reference `sdd/` paths. The bridge's job is to adapt the docs build
to the canonical repo paths, not the reverse. `sdd/` stays.

### Q3 (single declarative file?) — no, the marker IS the declaration

A central YAML file recreates the drift-surface problem the marker
avoids. The combination of (directory convention for SDD subdirs) +
(inline marker for everything else) is one declarative system in two
loci that cannot diverge: the convention is checked into code, the
markers are checked into the files they classify.

## Consequences

### Positive

- One mechanism, satisfying AUTHORING Rule 4 by construction.
- Five wrapper files deleted; `_link_map.yml` deleted.
- Audit-012 F-01, F-02, F-11, F-12, F-13 closed by tooling.
- Excluded files are auditable: every `.md` either has a marker or falls
  under a directory rule. No central exclusion list to maintain.
- AUTHORING Rule 3 is enforceable: the gate flags any Jinja or macro in a
  dual file.

### Negative / costs

- Every classified-non-default file gets a one-time edit to add its
  marker (~15 files at the trio + sdd top-level + repo-root level).
- Contributors learn the marker syntax. Mitigation: marker is documented
  in [`AUTHORING.md`](../AUTHORING.md) Rule 1's body alongside the class
  definitions.

### Migration order (sequenced commits within BK-167a)

1. Add `scan_dual_files` and the marker parser; tests cover marker
   syntax, dual default, classification edge cases.
2. Add `render_dual_pages`; tests assert byte-equivalence with
   `render_link_rewritten` output for the two existing link-map entries.
3. Add markers to every classified-non-default file.
4. Wire `gen_pages.py` to the new scanner/renderer; remove
   `_link_map.yml`, `scan_include_wrappers`, `render_link_rewritten`,
   the five wrapper files.
5. Land `scripts/check_docs_framework.py` and add `docs-check` to the
   `all` hatch script.
6. Flip `mkdocs.yml` `not_found: warn → error`; restore `--strict` in CI.
7. Apply nav/URL fixes (F-05, F-06, F-07, F-08, F-10) and let the gate
   green-light them.

Each step is independently testable; (5) gates the sequence's
correctness, (6) closes F-03/W-01, (7) closes the remaining audit-012
findings.

## Alternatives considered

### A. Keep three mechanisms, add a gate that whitelists them

Rejected: contradicts AUTHORING Rule 4. The framework rule is "one
bridge," not "any number of bridges plus enforcement that they each
follow rules."

### B. Central YAML manifest (`docs-src/_classification.yml`)

Rejected for the drift reason. The manifest must be edited every time a
file moves or is added; the marker is edited once when the file is
written and never again. A manifest also re-creates F-13's audit
problem in a different location: now the manifest must be checked
against disk reality on every PR.

### C. YAML frontmatter instead of HTML comment

Rejected for now. Frontmatter renders cleanly on GitHub and is
machine-parseable, but adds a YAML parser to the gate hot path and
imposes a syntax (`---` fences) on all classified files. HTML comments
need 8 lines of regex and zero runtime deps. If frontmatter becomes
useful for other reasons (e.g. front-matter-driven nav metadata), this
ADR can be superseded.

### D. Move `sdd/` under `docs-src/design/`

Rejected. See "Q2 — no" above. Skills, agents, and the existing ripple
check table treat `sdd/` paths as canonical; moving them would break
external links and skill content addressed at canonical paths, for a
gain (one fewer bridge layer) that the single-mechanism scanner already
delivers.
