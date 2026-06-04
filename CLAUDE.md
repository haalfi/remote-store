# Claude Code Instructions
<!-- doc: repo-only -->

## Project

Python library: unified file storage across backends (Local, S3, SFTP, Azure).
Spec-Driven Development (SDD).

## Principles

1. **Ship complete**: a change is finished when everything it touches is consistent: code, tests, docs, CHANGELOG, BACKLOG. Track gaps as `[~]`. For releases, follow the full checklist in [`CONTRIBUTING.md` § Release](CONTRIBUTING.md#release).
2. **Verify beyond the diff**: search for what references the thing you changed. The ripple-check in `sdd/CLAUDE-REFERENCE.md` has a Pre-work index (read **before starting** to anticipate ripples) and a Detailed checklist (read **before committing** to verify them). You MUST consult both presentations for changes that touch backends, errors, capabilities, versions, specs, or dependencies.
3. **Repo describes reality at every commit**: docs, backlog, and CHANGELOG reflect current state, not future intent. Same commit, or mark `[~]`.
4. **Single source of truth**: Authoritative references live in one place: link to them, don't copy. Examples: ripple-check, CHANGELOG section order, backlog ID format. Copies become stale.
5. **Specs are source of truth**: code vs spec conflict: code is wrong. Backlog vs history conflict: backlog is wrong. Fix the less authoritative side.
6. **Run it, don't just type-check it**: verify behavior, not signatures. Reproduce bugs before claiming fixes. Test what matters, not just what type-checks.
7. **Be critical, not agreeable**: challenge assumptions, question completeness, flag what's missing. Especially in reviews: a rubber-stamp is worse than no review. Ask what's untested, what could break, what's absent from the checklist.

## Feature reference

See `FEATURES.md` for the authoritative list of backends,
extensions, capabilities, and install extras for the current version.

## Audits

1. **Report only.** Present findings with evidence. Do not fix anything.
2. **User decides next steps** — what to fix, whether to create backlog items or an audit doc.
3. **An audit's authority is its diagnosis; its prescription is advisory.** When implementing a follow-up, re-evaluate the proposed disposition against the diagnosed pain — diverge if a different path fits better.

## Bug-fix protocol

See [`sdd/000-process.md` § Rule 6](sdd/000-process.md#workflows) for the canonical pipeline (BACKLOG →
CHANGELOG → failing TEST → FIX → COMMIT together). Per principle 6, **write
the failing test, run it, see it fail** before implementing the fix.

<a id="backlog"></a>
## Backlog (mandatory)

- See `sdd/BACKLOG.md` for workflow rules, ID prefixes, completing-work
  procedure, and active items. Completed items are in `sdd/BACKLOG-DONE.md`.
- Commit messages start with item ID when applicable (e.g., `AF-008: Add credential masking`).

<a id="trace-authoring"></a>
## Trace authoring (mandatory)

When working on a backlog item, maintain `sdd/traces/<id>-<slug>.yml` as you work, not after merge. Schema: `sdd/traces/_schema.yml`. **"Working on" means implementing or closing the item.** A pure advisory annotation to a body (e.g. recording a verification-run result) that neither implements nor closes the item does not require a trace; the trace is authored when implementation begins.

- **Before starting:** open the trace if it exists, otherwise create one from the schema example.
- **As you read:** record each gate and reference read as a step. Tag `outcome: unclear | misleading` on any read that did not deliver.
- **As events occur:** fill `discovery_followups` (new backlog IDs born during the work), `surprising_ripples` (paths the ripple-check table did not anticipate), `co_shipped_items` (other items closed by the same PR).
- **Before submitting:** tag `audience` priority-sorted; the CHANGELOG-required rule derives from it.
- **Ship the trace in the same PR as the work.** Not a separate later commit.

## Dev commands

Scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`.
Run `hatch run` to list them. `hatch run all` is the pre-commit gate.

Claude-specific shell constraints:

- **No `&&`, `||`, or `;`.** Split into separate Bash tool calls for auto-approval.
- **No shell redirects or pipes (`>`, `2>&1`, `| tee`).** Run commands plain and read output from the tool result for auto-approval.
- **No heredoc in git commits.** `git commit -m "$(cat <<'EOF'...)"` breaks the `Bash(git:*)` auto-approve pattern. Use multiple `-m` flags instead.
- **No `/tmp/`.** Use `./tmp/` instead (gitignored). `/tmp/` is a system directory and triggers a separate permission prompt.

<a id="coverage-gate"></a>
## Coverage gate

`hatch run all` uses a Stage-1, no-Docker test variant; the 95% strict gate lives in CI and the publish workflow. See pyproject.toml's `test-cov*` script comments for which variant to use when.

If `test-cov-strict` fails locally on coverage, **do not loop on "master is passing it, let me re-run"** — start Azurite or treat the strict gate as CI-only.

## Parallel tests

`test*` scripts run a parallel pass via `pytest -n auto` plus a serial pass for sftp_docker conformance — see `tests/backends/fixtures/registry.fixture_params` for the carve-out. Don't reintroduce `--dist loadgroup`, MaxStartups tuning, or banner retries: the simpler carve-out is the entire stabilisation story.

## Branching

- **Never commit or push directly to master.** Always create a feature branch.
- Branch naming: `id-021-store-child`, `fix-streaming-io`, `af-008-credential-masking`, etc.
- Push the feature branch; the user will create PRs or ask you to.

<a id="response-style"></a>
## Response style

Use em dashes (`—`) sparingly in prose responses. Default to periods, colons,
or commas. Never use `--` as an em dash substitute anywhere in written output.

In tables, `—` (em dash U+2014) is the standard N/A / none value. Never
`--` or `No`. See memory `feedback_table_style.md` for the full rule.

Preserve `--` only in: shell end-of-options separators (`git log -- path`),
spec-ID ranges (`BATCH-020 -- BATCH-025`), Mermaid edge syntax
(`A -- text --> B`), `--8<--` snippet includes, and code/SQL comments inside
fenced blocks. Table separator rows (`| --- |`) are structural Markdown.

<a id="documentation-framework"></a>
## Documentation framework

Three authority docs govern documentation. Apply in order:

1. **[`sdd/AUTHORING.md`](sdd/AUTHORING.md)**: placement (where files belong).
2. **[`sdd/DOCUMENTATION.md`](sdd/DOCUMENTATION.md)**: structure (what shape they take).
3. **[`sdd/CONTENT-RULES.md`](sdd/CONTENT-RULES.md)**: longevity (writing that stays accurate).

## Code conventions

See `sdd/DESIGN.md` for code style rules. See [`sdd/000-process.md` § Rules](sdd/000-process.md#rules) for
spec/test traceability obligations. Run `hatch run lint` before committing.

## Testing conventions

See `sdd/TESTING.md` for testing quality rules (assertion depth, mock discipline,
spec tracing). Applies to all new or changed tests.

## GitHub operations

PR workflows are codified as skills: `/pr`, `/rvw-pr`, `/fix-pr`. Use those instead of ad-hoc `gh` commands.
Use `/rvw-pr` for PR reviews, not the built-in `/review` CLI command.

For lookup tables, detailed procedures, and repo layout see `sdd/CLAUDE-REFERENCE.md`.

## Repo skills

Repo-specific skills live in `.claude/skills/`. When the user mentions "skill"
(e.g. "use the orchestrate skill", "run the /pr skill"), read the matching
`SKILL.md` in `.claude/skills/` for context, then serve the user's request.

Ignore AGENTS.md; this file defines Claude Code behavior for this repo.

---

For document structure rules see [`CONTRIBUTING.md` § Authoritative Document Format](CONTRIBUTING.md#authoritative-document-format).
