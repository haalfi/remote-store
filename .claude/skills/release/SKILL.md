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

**Phase 1 (CHANGELOG completeness cross-check)** — Run the `generate-notes` call from
the checklist purely as a completeness gate: it emits GitHub's merged-PR list since
`vPREV`, which you diff against CHANGELOG `[Unreleased]` to catch any user-facing PR
missing an entry. **Discard the output** — the release body is authored from CHANGELOG
in Phase 4, never from these auto-notes (they are a flat PR-title list, not the curated
by-section prose this project ships). `vPREV` = the latest release tag (`gh release view --json tagName --jq .tagName`).

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

<Extract sections from [Unreleased] in CHANGELOG.md and condense by section,
 following the section order in sdd/CLAUDE-REFERENCE.md § Ripple-check table > Detailed checklist.
 For each section with content, use brief bullet points (1 line per item, bold topic prefix).
 Prefer `**Topic**: explanation` or `**Topic** explanation.` over `**Topic** — explanation`.
 Em dashes belong to true asides, not bullet separators (CLAUDE.md § Response style).>

**Links:**
- [Full Changelog](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md#xyz---yyyy-mm-dd)
- [Compare vPREV...vX.Y.Z](https://github.com/haalfi/remote-store/compare/vPREV...vX.Y.Z)
```
