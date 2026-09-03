---
name: release
description: Version bump and release checklist for remote-store
disable-model-invocation: true
argument-hint: "[patch|minor|major]"
---

**Authority:** [`CONTRIBUTING.md` § Release](../../../CONTRIBUTING.md#release) is the authoritative checklist for all phases.
This skill carries the agent-specific execution layer (Phase 4 roles, release template) and
surfaced process notes that an agent must not miss.

Bump level: `$ARGUMENTS` (ask if missing). Minor = new API/feature/backend, patch = bugfix/refactor, no bump = CI/docs only.

Execute [`CONTRIBUTING.md` § Release](../../../CONTRIBUTING.md#release) (Phases 0–5). Agent notes per phase:

**Phase 1** — Update FEATURES.md content only; do NOT touch the version header
(`# Features — remote-store vX.Y.Z` where `X.Y.Z` is the *current* version) —
`bump-my-version` updates it in Phase 2.

**Phase 1 (CHANGELOG completeness cross-check)** — Resolve the checklist's
`previous_tag_name` (`vPREV`) with `gh release view --json tagName --jq .tagName`.
See the checklist item for what the gate compares and why its output is discarded.

**Phase 1 (CHANGELOG condensing)** — The checklist owns the procedure, the three
sources and the [section order](../../../CONTRIBUTING.md#changelog-section-order);
this note is only what an agent gets wrong. **Read each item's body under
`sdd/BACKLOG-DONE.md` § Unreleased before writing its entry** — the stub carries
neither the mechanism nor the figures, and an entry written from the stub alone
is a reworded stub, not the expansion. Condense to what a *user* does about the
change; the backlog body is arguing to a contributor and its length is not a
target. Follow the checklist's step ordering as written rather than from memory —
it is what keeps `check_changelog_unreleased.py` quiet mid-condense, and the
reason is stated there.

**Phase 2** — `bump-my-version` reads its target files from `[[tool.bumpversion.files]]`
in `pyproject.toml`.

**Phase 5** — Agent assists with conda steps (sha256 fetch, recipe update, branch+PR).
Staged-recipes steps apply only while conda-forge/staged-recipes PR #32401 is open; once
a feedstock exists, only the bot-PR verification step remains.

## Phase 4: Ship (Skill Agent)

- [ ] **[Agent]** Push release branch to origin
- [ ] **[Agent]** Create PR with link to this checklist
- [ ] **[User]** Review, approve, and merge PR to master — then tell agent "merged"
- [ ] **[Agent]** (Waits for user confirmation, then) Confirm CI green on merge commit
- [ ] **[Agent]** Create GitHub Release directly on GitHub (template below; triggers publish.yml + docs deploy)
- [ ] **[Agent]** Confirm publish.yml succeeds
- [ ] **[Agent]** Delete release branch

### Release Template

**Title:** `vX.Y.Z`

**Description:**
```markdown
## What's Changed

<Extract sections from this release's own `## [X.Y.Z]` section in CHANGELOG.md — Phase 2
 already renamed [Unreleased] to it and opened a fresh empty [Unreleased] above, so that
 heading now holds the *next* cycle — and condense each section further,
 following CONTRIBUTING.md § CHANGELOG section order.
 For each section with content, use brief bullet points (1 line per item, bold topic prefix).
 Prefer `**Topic**: explanation` or `**Topic** explanation.` over `**Topic** — explanation`.
 Em dashes belong to true asides, not bullet separators (CLAUDE.md § Response style).>

**Links:**
- [Full Changelog](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md#xyz---yyyy-mm-dd)
- [Compare vPREV...vX.Y.Z](https://github.com/haalfi/remote-store/compare/vPREV...vX.Y.Z)
```
