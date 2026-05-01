# Authoring Guide

## Two presentations, one source

remote-store's documentation runs in two presentations: the GitHub repo
browser, and the rendered MkDocs site.

| | Repo (GitHub) | Docs site (MkDocs) |
|---|---|---|
| Reader | Contributors, agents, package-index and source-link arrivals | End users, evaluators, search-engine arrivals |
| Engine | Plain Markdown only | MkDocs + plugins |
| Role | Source of truth | Curated reading experience |

Neither presentation is canonical. The repo holds authority; the docs site
presents it. Both must read correctly without each other.

The docs site is published from the same `mkdocs.yml` build to two hosts:

- **ReadTheDocs** (`https://docs.remotestore.dev/`): primary host. Serves
  released versions; `/stable/` is the user-facing default.
- **GitHub Pages via mike**: secondary host. Serves the `dev` track from
  master and provides the version-selector archive.

Authors do not target a specific host. They target "the docs site"; both
hosts render the same build.

Every authored `.md` falls into exactly one class by which presentations it
serves:

- **Repo-only**: appears only in the repo (internal process, agent tooling,
  contributor housekeeping).
- **Docs-only**: appears only on the docs site (site-specific prose, nav,
  templates).
- **Dual**: must read correctly in both presentations.

The class fixes which of the principles below apply.

## Five principles

### 1. One file, one home

Each `.md` lives at exactly one path. Other presentations are derived from
that path, never copied.

*Why:* Duplicated prose drifts. A single home keeps authority unambiguous.

### 2. Every file's class is recorded centrally

Each `.md` is recorded as repo-only, docs-only, or dual in one place — not
inferred from where it lives or from how the build happens to handle it.

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
