# Backlog Sync — Update BACKLOG.md After Work

You are updating `sdd/BACKLOG.md` to reflect work that was just completed.
This skill ensures the backlog stays consistent with reality — the #1
systemic issue in this repo's history (7/9 audit-tagged commits forgot to
update the backlog).

## Instructions

### Step 1: Understand what was done

Review recent changes:
- `git log --oneline -10` — recent commits
- `git diff HEAD~N --name-only` — files changed in recent commits
- Ask the user what work was completed if unclear

### Step 2: Find matching backlog items

Read `sdd/BACKLOG.md` and identify items that were addressed:
- Match by ID prefix (AF-NNN, BK-NNN, BL-NNN, ID-NNN)
- Match by description (e.g., a commit about "streaming" matches ID-006)
- Match by files changed (e.g., backend changes match BK or AF items)

### Step 3: Update item status

For each matching item, apply the correct status:

**Fully done** — change `[ ]` or `[~]` to `[x]` and add a "Done:" note:
```markdown
- [x] **AF-005 — Fix `delete_folder` error types**
  ...existing description...
  Done: v0.6.0 — Added `DirectoryNotEmpty` error type; non-empty folder deletes now
  raise `DirectoryNotEmpty` instead of generic errors.
```

**Partially done** — change `[ ]` to `[~]` and add a note about what remains:
```markdown
- [~] **BK-002 — Glob / pattern matching strategy**
  ...existing description...
  Progress: Client-side fallback implemented. Server-side S3 prefix filtering pending.
```

### Step 4: Verify format

- Status markers: `[ ]` pending, `[~]` in progress, `[x]` done
- Done notes include the version: `(vX.Y.Z)` after the title
- The Done section is grouped by origin:
  - **Release blockers** (BL-NNN)
  - **Backlog items** (BK-NNN)
  - **Audit findings** (AF-NNN)
  - **Ideas shipped** (ID-NNN)
  - **Other completed work** (DONE-NNN)
  Place completed items under the correct subgroup.
- IDs are never reused or renumbered

### Step 5: Check for new items

If the work revealed new issues, bugs, or improvement ideas:
- Add them to the **Ideas** section with the next available `ID-NNN`
- Use the standard format: `- [ ] **ID-NNN — <Title>**` followed by description

### Step 6: Confirm inclusion

Remind the user (or yourself) that the backlog update MUST be in the same
commit as the code change. This is a hard rule from CLAUDE.md:

> Include the backlog update in the **same commit or PR** as the code change.
> Do not leave it for a follow-up.

## Important

- This skill exists because backlog drift was the #1 systemic issue. Seven
  audit finding commits (AF-001 through AF-007) were properly tagged in commit
  messages but NONE updated BACKLOG.md. The update came in a separate cleanup
  commit after the merge.
- Never change item IDs or reorder items within a tier.
- When in doubt about whether something is "done", mark it `[~]` with a note
  about what remains. Over-claiming completeness is worse than being honest.
