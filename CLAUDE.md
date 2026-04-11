# Claude Code Instructions

## Project

Python library: unified file storage across backends (Local, S3, SFTP, Azure).
Spec-Driven Development (SDD).

## Principles

1. **Ship complete**: a change is finished when everything it touches is consistent: code, tests, docs, CHANGELOG, BACKLOG. Track gaps as `[~]`. For releases, follow the full checklist in `CONTRIBUTING.md` § Release.
2. **Verify beyond the diff**: search for what references the thing you changed. You MUST read `sdd/CLAUDE-REFERENCE.md` for the ripple-check table before committing changes that touch backends, errors, capabilities, versions, specs, or dependencies.
3. **Repo describes reality at every commit**: docs, backlog, and CHANGELOG reflect current state, not future intent. Same commit, or mark `[~]`.
4. **Single source of truth**: Don't copy authoritative tables (ripple-check, section orders, ID prefixes) across files. Reference them instead. Copies become stale.
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

Strict order — no skipping:

1. Backlog entry (`sdd/BACKLOG.md`)
2. CHANGELOG entry (`[Unreleased]`)
3. Failing test that reproduces the bug -- **write it, run it, see it fail**
4. Fix (make the test pass) -- **run the test again, see it pass**
5. Commit all together (or mark `[~]`)

## Backlog (mandatory)

- See `sdd/BACKLOG.md` for workflow rules, ID prefixes, and active items.
  Completed items are in `sdd/BACKLOG-DONE.md`.
- **Completing work:** done → move item to `BACKLOG-DONE.md` (same commit). Partially done → split: ship done part to `BACKLOG-DONE.md`, create new ID here for remainder, link both.
- Commit messages start with item ID when applicable (e.g., `AF-008: Add credential masking`).

## Dev commands

All scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`. Run `hatch run` to see available commands. Key ones:

```bash
hatch run test              # pytest, 95% coverage required
hatch run lint              # ruff check + format
hatch run typecheck         # mypy strict on src/
hatch run notebooks         # execute tutorial notebooks (no Jupyter needed)
hatch run check-test-quality # assertion + mock-spec CI checks
hatch run mutate-core-api      # mutation testing: Store, proxy, stream, glob, backend base
hatch run mutate-core-infra    # mutation testing: capabilities, errors, config, models, path, registry
hatch run mutate-ext-proxy     # mutation testing: arrow, batch, cache, observe, otel, partition, ...
hatch run mutate-ext-format    # mutation testing: parquet, yaml, pydantic, dagster
hatch run mutate-backends-local  # mutation testing: local, memory, http, sql backends
hatch run mutate-backends-cloud  # mutation testing: s3, sftp, azure backends
hatch run docs              # serve docs locally
hatch run docs-build        # build docs (strict mode)
hatch run all               # lint + format-check + typecheck + test-cov + examples + notebooks
```

- **No `&&`, `||`, or `;`.** Split into separate Bash tool calls for auto-approval.
- **No heredoc in git commits.** `git commit -m "$(cat <<'EOF'...)"` breaks the `Bash(git:*)` auto-approve pattern. Use multiple `-m` flags instead.

## Branching

- **Never commit or push directly to master.** Always create a feature branch.
- Branch naming: `id-021-store-child`, `fix-streaming-io`, `af-008-credential-masking`, etc.
- Push the feature branch; the user will create PRs or ask you to.

## Code conventions

See `sdd/DESIGN.md` for the full code style rules. Key points:

- Tests: `@pytest.mark.spec("ID")` for spec traceability.
- New features require a spec in `sdd/specs/`. Ops changes (CI, docs) skip specs.
- Run `hatch run lint` before committing.

## GitHub operations

**Primary:** `github-pat` MCP server (fine-grained PAT, read+write).
**Fallback:** `MCP_DOCKER` (Docker OAuth token — writes return 404/403 in local CLI; may work on claude.ai). Use for reads only.
**Last resort:** `gh` CLI — needed for thread resolution (`gh api graphql`).

Priority: try `github-pat` first for all operations (read and write). Fall back to `MCP_DOCKER` for reads, then `gh` CLI.

PR workflows are codified as skills: `/pr`, `/review-pr`, `/fix-pr`. Use those instead of ad-hoc `gh` commands.
Use `/review-pr` for PR reviews, not the built-in `/review` CLI command.

For lookup tables, detailed procedures, and repo layout see `sdd/CLAUDE-REFERENCE.md`.

Ignore AGENTS.md; this file defines Claude Code behavior for this repo.

---

For document structure rules see `CONTRIBUTING.md` § Authoritative Document Format.
