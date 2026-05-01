# Documentation Authoring Standards

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
   site), or dual (must read correctly in both). The class is explicitly
   declared, not inferred from path or from build behavior. Default class
   is **dual**; any unclassified `.md` is treated as dual. If unsure,
   declare dual.

2. **Single home.** Each `.md` lives at exactly one path. Other
   presentations are derived from that path, never copied.

3. **Dual files use plain Markdown.** Dual files contain only plain
   Markdown: no Jinja directives, no plugin macros, no links to build-time
   virtual paths. The docs build adapts to dual files; dual files do not
   adapt to the docs build.

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

Neither presentation is canonical. The repo holds authority; the docs site
presents it. Both must read correctly without each other.

The docs site may be served from more than one host. Authors target "the
docs site"; host configuration is a deployment concern, not an authoring one.

### Where does my new file go?

1. **Docs-site only?** → `docs-src/` under the right Diataxis bucket.
2. **Internal, process, or tooling?** → repo path of your choice; declare
   it as repo-only. SDD artefacts (specs, ADRs, RFCs, research, audits) go
   under `sdd/`; see [`sdd/CLAUDE-REFERENCE.md`](CLAUDE-REFERENCE.md) for
   the full path map.
3. **Otherwise it is dual** → its anchored repo path, plain Markdown only.
   The bridge handles the docs side.

If unsure, declare dual.
