# Documentation Authoring Standards
<!-- doc: dual dest=explanation/design/authoring.md -->

## Intent & Scope

Authoritative source for where documentation files belong. Governs the
placement of all `.md` content in the repository.

Part of the documentation framework (see [`CLAUDE.md` § Documentation
framework](../CLAUDE.md#documentation-framework)): structure →
[`sdd/DOCUMENTATION.md`](DOCUMENTATION.md); longevity →
[`sdd/CONTENT-RULES.md`](CONTENT-RULES.md).

## Rules

1. **File classification.** Every `.md` belongs to exactly one class:
   repo-only (appears only in the repo), docs-only (appears only on the docs
   site), or dual (must read correctly in both). Each file is classified by
   one of two routes: an explicit HTML-comment marker on the file itself,
   or a directory-default rule when no marker is present. A file that
   carries no marker AND matches no directory default is unclassified;
   the gate (G-01) fails on unclassified files. Marker syntax, the three
   classes, and the directory-default table are normative in
   _Classification markers_ and _Directory defaults_ below. The class is
   not inferred from path alone or from build behavior.

2. **Single home.** Each `.md` lives at exactly one path. Other
   presentations are derived from that path, never copied.

3. **Dual files use plain Markdown.** Dual files contain only plain
   Markdown: no Jinja directives, no MkDocs plugin macros (the
   `pymdownx.snippets` `--8<--` form is the one exception, per
   [`sdd/CONTENT-RULES.md` Rule 6](CONTENT-RULES.md#rules)), no links
   to build-time virtual paths (paths resolvable only after MkDocs
   renders, e.g. into gen-files outputs). The docs build adapts to dual
   files; dual files do not adapt to the docs build.

4. **One bridge mechanism.** The bridge is the mechanism that takes dual
   files from their repo path and presents them on the docs site. Exactly
   one bridge applies; new mechanisms are not added to handle special
   cases. The bridge implementation lives in the build tooling.

5. **PR-time enforcement.** A PR-blocking check verifies that every rule
   in the documentation framework is satisfied. Failures block merge.

## Guides

### Two presentations, one source

remote-store's documentation has two presentations: the GitHub repo browser
and the rendered docs site.

| | Repo | Docs site |
|---|---|---|
| Reader | Arrivals from code, package indexes, agents | End users and evaluators |
| Engine | Plain Markdown | MkDocs |
| Role | Source of truth | Curated reading experience |

The repo is authoritative; the docs site is a presentation of it. Both
must read correctly without each other.

The docs site may be served from more than one host. Authors target "the
docs site"; host configuration is a deployment concern, not an authoring one.

### Where does my new file go?

1. **Docs-site only?** → `docs-src/` (Diataxis bucket per
   [`DOCUMENTATION.md`](DOCUMENTATION.md#1-diataxis-placement) Rule 1).
2. **Pure internal tooling** (`sdd/BACKLOG.md`, `sdd/CLAUDE-REFERENCE.md`,
   `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, agent harness
   files)? → repo path; declare repo-only.
3. **Otherwise it is dual** → its anchored repo path, plain Markdown
   only. Includes `README`, `CHANGELOG`, `CONTRIBUTING`, the
   Authoritative Document Format trio, all process docs, and all SDD
   artefacts (specs, ADRs, RFCs, research, audits). The bridge handles
   the docs-site presentation. See
   [`sdd/CLAUDE-REFERENCE.md`](CLAUDE-REFERENCE.md) and
   [`CONTRIBUTING.md`](../CONTRIBUTING.md) § Authoritative Document
   Format Scope for the path map.

If unsure, declare dual.

### Classification markers

A marker is an HTML comment in the first 5 non-blank lines of the file.
HTML comments are invisible in every Markdown renderer, so the marker
adds no visible content. Three forms:

```markdown
<!-- doc: dual dest=explanation/design/authoring.md -->
<!-- doc: repo-only -->
<!-- doc: docs-only -->
```

Class semantics:

- **`dual`** — the file appears at its repo path AND at the virtual
  `dest` on the docs site. `dest=` is required.
- **`repo-only`** — the file appears only at its repo path. The bridge
  emits no virtual page. `dest=` MUST be absent.
- **`docs-only`** — the file is authored under `docs-src/` and consumed
  by MkDocs directly. `dest=` MUST be absent.

The marker MAY follow a `# Title` line. Whitespace inside the comment
is normalised; one or more spaces between tokens is accepted.

### Directory defaults

When no marker is present, the file is classified by directory. The
SDD-subdir rows follow the kind globs declared in
`scripts/docs/scan.py:SDD_KINDS`. Files in [`sdd/templates/`](templates/)
are authoring tools, not documentation, and default to repo-only.

| Source pattern | Default class | Default dest |
|---|---|---|
| `sdd/adrs/*.md` | dual | `explanation/design/adrs/<slug>.md` |
| `sdd/specs/*.md` | dual | `explanation/design/specs/<slug>.md` |
| `sdd/rfcs/rfc-*.md` | dual | `explanation/design/rfcs/<slug>.md` |
| `sdd/audits/audit-*.md` | dual | `explanation/design/audits/<slug>.md` |
| `sdd/research/research-*.md` | dual | `explanation/design/research/<slug>.md` |
| `sdd/templates/*.md` | repo-only | — |
| `docs-src/**/*.md` | docs-only | — |
| anything else | requires explicit marker | — |

In practice:

- Files added under `sdd/specs/`, `sdd/adrs/`, `sdd/rfcs/`, `sdd/audits/`,
  `sdd/research/` need no marker.
- Files added under `sdd/templates/` need no marker (repo-only by default).
- Files added under `docs-src/` need no marker.
- Top-level `sdd/*.md` process docs (000-process, AUTHORING, DESIGN,
  DOCUMENTATION, TESTING, CONTENT-RULES) carry an explicit dual marker.
- Internal `sdd/*.md` files (BACKLOG, BACKLOG-DONE, CLAUDE-REFERENCE)
  carry an explicit repo-only marker.
- Repo-root dual files (CHANGELOG, CONTRIBUTING, DEVELOPMENT_STORY,
  FEATURES) carry an explicit dual marker. `FEATURES.md` lives at
  the repo root (not under `docs-src/reference/`) — the dual bridge
  renders it at `reference/FEATURES.md`. Its peers (capabilities-matrix,
  migration) live under `docs-src/reference/` as docs-only files.
- Repo-root repo-only files (CLAUDE, CODE_OF_CONDUCT, README, SECURITY)
  carry an explicit repo-only marker. `README.md` is repo-only; its
  quick-start content is served on the docs site via
  `docs-src/tutorial/getting-started.md` instead.
- Example directories (`examples/<name>/README.md`, etc.): no directory
  default. Each example README declares its own marker. The medallion
  showcase's docs-side page is rendered separately and is not a default
  dual mapping.

### Examples

```markdown
<!-- A new guide. docs-src/ is docs-only by default; no marker needed. -->
# Streaming reads
...

<!-- A repo-root contributor doc. Explicit dual marker; bridge emits docs/contributing/. -->
<!-- doc: dual dest=contributing.md -->
# Contributing
...

<!-- A Claude-only operational file. Explicit repo-only marker; never reaches the docs site. -->
<!-- doc: repo-only -->
# Claude Code Reference
...

<!-- A new spec. sdd/specs/ has a directory default; no marker needed. -->
# Spec 048 -- Some Topic
...
```
