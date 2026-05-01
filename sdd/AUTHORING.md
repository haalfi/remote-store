# Documentation Authoring Standards

## Intent & Scope

Authoritative source for where documentation files belong and which
constraints apply to each. Governs all `.md` content in the repository.
Companion to `sdd/DOCUMENTATION.md` (structure and placement) and
`sdd/CONTENT-RULES.md` (longevity rules).

## Rules

1. **File classification** — Every `.md` belongs to exactly one class:
   repo-only (appears only in the repo), docs-only (appears only on the docs
   site), or dual (must read correctly in both). Classes are recorded
   centrally, not inferred from path or from build behavior.

2. **Single home** — Each `.md` lives at exactly one path. Other
   presentations are derived from that path, never copied.

3. **Dual files use plain Markdown** — Dual files contain only plain
   Markdown: no Jinja directives, no plugin macros, no links to build-time
   virtual paths. The docs build adapts to dual files; dual files do not
   adapt to the docs build.

4. **One bridge mechanism** — A single declared mechanism takes dual files
   into the docs site. New mechanisms are not added to handle special cases.

5. **PR-time enforcement** — A PR-blocking check validates that
   classifications are known, the bridge resolves cleanly for every dual
   file, and internal links resolve in their target presentation.

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
2. **Internal, process, or tooling?** → repo path of your choice; record it
   as repo-only.
3. **Otherwise it is dual** → its anchored repo path, plain Markdown only.
   The bridge handles the docs side.

If unsure, assume dual.
