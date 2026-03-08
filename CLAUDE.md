# Claude Code Instructions

## Project

Python library: unified file storage across backends (Local, S3, SFTP, Azure).
Spec-Driven Development (SDD).

## Principles

1. **Ship complete** — a change is finished when everything it touches is consistent: code, tests, docs, CHANGELOG, BACKLOG. Track gaps as `[~]`. For releases, follow the full checklist in `CONTRIBUTING.md` § Release.
2. **Verify beyond the diff** — search for what references the thing you changed. You MUST read `sdd/CLAUDE-REFERENCE.md` for the ripple-check table before committing changes that touch backends, errors, capabilities, versions, specs, or dependencies.
3. **Repo describes reality at every commit** — docs, backlog, and CHANGELOG reflect current state, not future intent. Same commit, or mark `[~]`.
4. **Specs are source of truth** — code vs spec conflict: code is wrong. Backlog vs history conflict: backlog is wrong. Fix the less authoritative side.
5. **Run it, don't just type-check it** — verify behavior, not signatures. Reproduce bugs before claiming fixes. Test what matters, not just what type-checks.
6. **Be critical, not agreeable** — challenge assumptions, question completeness, flag what's missing. Especially in reviews: a rubber-stamp is worse than no review. Ask what's untested, what could break, what's absent from the checklist.

## Backlog (mandatory)

- Read `sdd/BACKLOG.md` before starting. Note relevant item IDs (AF-NNN, BK-NNN, BL-NNN, ID-NNN).
- After work: mark items `[x]` (with version) or `[~]` (with what remains). Same commit as the code change.
- Commit messages start with item ID when applicable (e.g., `AF-008: Add credential masking`).

## Dev commands

```bash
hatch run test              # pytest, 95% coverage required
hatch run lint              # ruff check + format
hatch run typecheck         # mypy strict on src/
hatch run notebooks          # execute tutorial notebooks (no Jupyter needed)
hatch run all               # lint + format-check + typecheck + test-cov + examples + notebooks
```

- **Use single commands, not compound commands.** Compound commands (`&&`, `||`, `;`) cannot be auto-approved by permission patterns. Split them into separate tool calls instead. The extra round-trip cost is minor compared to blocking on a security prompt.

## Branching

- **Never commit or push directly to master.** Always create a feature branch.
- Branch naming: `id-021-store-child`, `fix-streaming-io`, `af-008-credential-masking`, etc.
- Push the feature branch; the user will create PRs or ask you to.

## Code conventions

- Tests: `@pytest.mark.spec("ID")` for spec traceability.
- New features require a spec in `sdd/specs/`. Ops changes (CI, docs) skip specs.
- Run `hatch run lint` before committing.

## GitHub CLI (`gh`) — restricted usage

The `gh` CLI is installed via a SessionStart hook (`.claude/setup-gh.sh`).
It requires a `GITHUB_TOKEN` environment variable with PR read/write scope.

> **Environment note:** These restrictions exist primarily for web/iOS sessions
> (Code on Mobile, claude.ai) where Claude operates with less interactive
> oversight. In the VS Code extension on your local machine, every tool call
> requires your explicit approval, so the guardrails are enforced interactively.
> The rules below apply to **both** environments for consistency.

**Allowed operations** (only when the user explicitly asks):

- `gh pr view` — read PR metadata
- `gh pr diff` — read PR diffs
- `gh pr review` — submit a review with comments
- `gh api` — post review comments on specific lines

**Forbidden operations** (never do these):

- Creating, closing, or merging PRs
- Pushing code or creating branches via `gh`
- Creating, closing, or commenting on issues
- Any `gh` operation not listed above
- Any `gh` operation without the user explicitly requesting it

For lookup tables, detailed procedures, and repo layout see `sdd/CLAUDE-REFERENCE.md`.

## Miscellaneous
Ignore AGENTS.md; this file defines Claude Code behavior for this repo.