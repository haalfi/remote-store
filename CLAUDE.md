# Claude Code Instructions

## Project

Python library: unified file storage across backends (Local, S3, SFTP, Azure).
Spec-Driven Development (SDD).

## Principles

1. **Ship complete**: a change is finished when everything it touches is consistent: code, tests, docs, CHANGELOG, BACKLOG. Track gaps as `[~]`. For releases, follow the full checklist in `CONTRIBUTING.md` § Release.
2. **Verify beyond the diff**: search for what references the thing you changed. You MUST read `sdd/CLAUDE-REFERENCE.md` for the ripple-check table before committing changes that touch backends, errors, capabilities, versions, specs, or dependencies.
3. **Repo describes reality at every commit**: docs, backlog, and CHANGELOG reflect current state, not future intent. Same commit, or mark `[~]`.
4. **Single source of truth**: Authoritative references live in one place—link to them, don't copy. Examples: ripple-check, CHANGELOG section order, backlog ID format. Copies become stale.
5. **Specs are source of truth**: code vs spec conflict: code is wrong. Backlog vs history conflict: backlog is wrong. Fix the less authoritative side.
6. **Run it, don't just type-check it**: verify behavior, not signatures. Reproduce bugs before claiming fixes. Test what matters, not just what type-checks.
7. **Be critical, not agreeable**: challenge assumptions, question completeness, flag what's missing. Especially in reviews: a rubber-stamp is worse than no review. Ask what's untested, what could break, what's absent from the checklist.

## Feature reference

See `FEATURES.md` at the repo root for the authoritative list of backends,
extensions, capabilities, and install extras for the current version.

## Audits

1. **Report only.** Present findings with evidence. Do not fix anything.
2. **User decides next steps** — what to fix, whether to create backlog items or an audit doc.

## Bug-fix protocol

See `sdd/000-process.md` § Rule 6 for the canonical pipeline (BACKLOG →
CHANGELOG → failing TEST → FIX → COMMIT together). Per principle 6, **write
the failing test, run it, see it fail** before implementing the fix.

## Backlog (mandatory)

- See `sdd/BACKLOG.md` for workflow rules, ID prefixes, and active items.
  Completed items are in `sdd/BACKLOG-DONE.md`.
- **Completing work:** done → move item to `BACKLOG-DONE.md` (same commit). Partially done → split: ship done part to `BACKLOG-DONE.md`, create new ID here for remainder, link both.
- Commit messages start with item ID when applicable (e.g., `AF-008: Add credential masking`).

## Dev commands

Scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`.
Run `hatch run` to list them. `hatch run all` is the pre-commit gate.

Claude-specific shell constraints:

- **No `&&`, `||`, or `;`.** Split into separate Bash tool calls for auto-approval.
- **No shell redirects (`>`, `2>&1`, `| tee`).** Run commands plain and read output from the tool result. Redirects always
  trigger an approval prompt.
- **No heredoc in git commits.** `git commit -m "$(cat <<'EOF'...)"` breaks the `Bash(git:*)` auto-approve pattern. Use multiple `-m` flags instead.
- **No `/tmp/`.** Use `./tmp/` instead (gitignored). `/tmp/` is a system directory and triggers a separate permission prompt.

## Branching

- **Never commit or push directly to master.** Always create a feature branch.
- Branch naming: `id-021-store-child`, `fix-streaming-io`, `af-008-credential-masking`, etc.
- Push the feature branch; the user will create PRs or ask you to.

## Documentation conventions

See `sdd/DOCUMENTATION.md` for structure and placement rules.
See `sdd/CONTENT-RULES.md` for content quality and longevity rules — apply
these when writing or reviewing any README, guide, or docstring.

## Code conventions

See `sdd/DESIGN.md` for code style rules. See `sdd/000-process.md` § Rules for
spec/test traceability obligations. Run `hatch run lint` before committing.

## Testing conventions

See `sdd/TESTING.md` for testing quality rules (assertion depth, mock discipline,
spec tracing). Applies to all new or changed tests.

## GitHub operations

**Primary:** `github-pat` MCP server (fine-grained PAT, read+write).
**Fallback:** `MCP_DOCKER` (Docker OAuth token — writes return 404/403 in local CLI; may work on claude.ai). Use for reads only.
**Last resort:** `gh` CLI — needed for thread resolution (`gh api graphql`).

Priority: try `github-pat` first for all operations (read and write). Fall back to `MCP_DOCKER` for reads, then `gh` CLI.

PR workflows are codified as skills: `/pr`, `/review-pr`, `/fix-pr`. Use those instead of ad-hoc `gh` commands.
Use `/review-pr` for PR reviews, not the built-in `/review` CLI command.

For lookup tables, detailed procedures, and repo layout see `sdd/CLAUDE-REFERENCE.md`.

## Repo skills

Repo-specific skills live in `.claude/skills/`. When the user mentions "skill"
(e.g. "use the orchestrate skill", "run the /pr skill"), read the matching
`SKILL.md` in `.claude/skills/` for context, then serve the user's request.

Ignore AGENTS.md; this file defines Claude Code behavior for this repo.

---

For document structure rules see `CONTRIBUTING.md` § Authoritative Document Format.
