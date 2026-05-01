# Authoring Guide

## Two presentations, one source

remote-store's documentation runs in two places: the GitHub repo browser and
the MkDocs site on `gh-pages` (served via mike).

| | Repo (GitHub) | Docs site (mike on gh-pages) |
|---|---|---|
| Reader | Contributors, agents, package-index and source-link arrivals | End users, evaluators, search-engine arrivals |
| Engine | Plain Markdown only | MkDocs + plugins + mike versioning |
| Role | Source of truth | Curated reading experience |

Neither presentation is canonical. The repo holds authority; the docs site
presents it. Both must read correctly without each other.

## Five principles

### 1. One file, one home

Each `.md` lives at exactly one path. Other presentations are derived from
that path, never copied.

*Why:* Duplicated prose drifts. A single home keeps authority unambiguous.

### 2. Every file has a class

Each `.md` belongs to exactly one of:

- **Repo-only**: internal process, agent tooling, contributor housekeeping.
  Stays in the repo, never appears on the docs site.
- **Docs-only**: site-specific prose, nav, or templates. Lives in `docs-src/`.
- **Dual**: must read correctly in both presentations. Lives at its anchored
  repo path.

Classifications are recorded centrally so the boundary is auditable.

*Why:* If the class is implicit, a reviewer cannot tell whether a missing
file was deliberately excluded or accidentally dropped.

### 3. Dual files use the smaller language

Dual files are plain Markdown. No Jinja directives, no plugin macros, no
links to build-time virtual paths. The docs build adapts to dual files; dual
files do not adapt to the docs build.

*Why:* GitHub renders only plain Markdown. A Jinja directive in a dual file
either renders raw text on GitHub or breaks the docs build. The smaller
language is the only one that works in both.

### 4. One bridge, not many

A single declared mechanism brings dual files to the docs site. New
mechanisms are not added to handle special cases.

*Why:* Multiple mechanisms doing the same job force every contributor to
learn all of them before placing a file correctly. One bridge is auditable;
many is not.

### 5. The contract is enforced at PR time

A single PR-blocking check validates that classifications are known, the
bridge resolves cleanly for every dual file, and links resolve in their
target presentation.

*Why:* A docs system that only fails after merge normalizes broken state on
master. Verification has to happen before merge, not after.

## Where does my new file go?

1. **Docs-site only?** → `docs-src/` under the right Diataxis bucket.
2. **Internal / process / tooling?** → repo path of your choice; mark it
   repo-only.
3. **Otherwise it is dual** → its anchored repo path, authored in plain
   Markdown. The bridge handles the docs side.

If unsure, assume dual. Anchored content usually needs both presentations.

---

For detailed structure rules see `sdd/DOCUMENTATION.md`. For the audit that
prompted these principles see `sdd/audits/audit-012-docs-structure.md`.
