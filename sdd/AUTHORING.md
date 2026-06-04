# Documentation Authoring Standards
<!-- doc: dual dest=explanation/design/authoring.md -->

## Intent & Scope

Authoritative source for where documentation files belong. Governs the
placement of all `.md` content in the repository.

Part of the documentation framework (see [`CLAUDE.md` § Documentation
framework](../CLAUDE.md#documentation-framework)): structure →
[`sdd/DOCUMENTATION.md`](DOCUMENTATION.md); longevity →
[`sdd/CONTENT-RULES.md`](CONTENT-RULES.md).

<a id="rules"></a>
## Rules

1. <a id="file-classification"></a>**File classification.** Every `.md` belongs to exactly one class.
   Classification follows a marker on the file or a directory default
   when no marker is present. A file with no marker and no matching
   default is unclassified and fails G-01. See _Classification markers_
   and _Directory defaults_ below.

2. **Single home.** Each `.md` lives at exactly one path. Other
   presentations are derived from that path, never copied.

3. **On-disk links.** Every relative `](path)` link in every
   `.md` must resolve to a real on-disk file in the repo. External URLs
   and pure anchors are exempt. The bridge (Rule 4) rewrites on-disk
   targets to docs-site URLs at build time so both presentations render
   correctly. Dual files additionally use only plain Markdown; see
   [`sdd/CONTENT-RULES.md` Rule 6](CONTENT-RULES.md#code-examples-sourced) for the
   one snippet exception.

4. <a id="one-bridge-mechanism"></a>**One bridge mechanism.** The bridge presents dual files on the docs
   site and rewrites on-disk links in docs-only files to docs-site URLs
   at build time. Exactly one bridge applies; new mechanisms are not
   added. The implementation lives in the build tooling.

5. **PR-time enforcement.** A PR-blocking check verifies every framework
   rule. Failures block merge.

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
   [`DOCUMENTATION.md` Rule 1](DOCUMENTATION.md#diataxis-placement)).
2. **Pure internal tooling** (`sdd/BACKLOG.md`, `sdd/CLAUDE-REFERENCE.md`,
   `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, agent harness
   files)? → repo path; declare repo-only.
3. **Otherwise it is dual** → its anchored repo path, plain Markdown
   only. Includes `README`, `CHANGELOG`, `CONTRIBUTING`, the
   Authoritative Document Format trio, all process docs, and all SDD
   artefacts (specs, ADRs, RFCs, research, audits). The bridge handles
   the docs-site presentation. See
   [`sdd/CLAUDE-REFERENCE.md`](CLAUDE-REFERENCE.md) and
   [`CONTRIBUTING.md` § Authoritative Document Format](../CONTRIBUTING.md#authoritative-document-format) Scope subsection for the path map.

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
[`docs-src/_path_rules.yml`](../docs-src/_path_rules.yml) (loaded by
`scripts/docs/scan.py:SDD_KINDS`). Files in
[`sdd/templates/`](templates/) are authoring tools, not documentation,
and default to repo-only.

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

Files not covered by the table require explicit markers. Common cases:

- Top-level `sdd/*.md` process docs (AUTHORING, DESIGN, etc.) carry an
  explicit dual marker.
- Internal `sdd/*.md` files (BACKLOG, CLAUDE-REFERENCE, etc.) carry an
  explicit repo-only marker.
- Repo-root dual files (CHANGELOG, CONTRIBUTING, etc.) carry an explicit
  dual marker.
- Repo-root repo-only files (CLAUDE, README, etc.) carry an explicit
  repo-only marker.
- Example directories (`examples/<name>/README.md`, etc.): no directory
  default. Each declares its own marker.

For the complete path map see
[`sdd/CLAUDE-REFERENCE.md`](CLAUDE-REFERENCE.md) and
[`CONTRIBUTING.md` § Authoritative Document Format](../CONTRIBUTING.md#authoritative-document-format).

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
