---
name: mutation
description: Triage and act on the weekly [mutation] rolling issue (mutation-testing run health)
disable-model-invocation: true
argument-hint: "[issue number]"
---

Act on the `[mutation]` rolling issue: classify each failing scope, fix the
harness/implementation regression behind it, and prepare a pushed branch for
the user to open the PR via `/pr`.

**Authority (do not duplicate — read these):**
- `sdd/CI-OPERATIONS.md` — the cross-guard handbook: where this guard sits in
  the scheduled/automated family and the durable-TODO principle it follows.
- `.github/workflows/mutation.yml` header — the two-outcome model and its
  non-goals (the run never fails on surviving mutants).
- `scripts/mutation_report.py` module docstring — outcome JSON shape,
  classification rules, and the partial-run-never-closes semantics.
- `scripts/mutate_scopes.py` — the scope manifest (targets, tests, containers).

**The core rule this skill exists to enforce:** the issue tracks **run
health**, not mutants. A scope listed under *Harness / implementation
failures* is a regression — the run itself broke — and is fixed like any bug
(backlog item, failing test where applicable, fix, same commit). *Surviving
mutants* are advisory test-coverage gaps: they never open the issue, never
turn the run red, and are folded into a coverage-hardening pass, not patched
ad hoc to silence a report.

GitHub reads via `gh` CLI; writes (PR) via the configured GitHub MCP server.
Repo: `haalfi/remote-store`.

## Steps

1. **Locate the issue.** If `$ARGUMENTS` is an issue number, use it. Otherwise
   find the single open rolling issue by title prefix:
   `gh issue list --repo haalfi/remote-store --state open --search '[mutation] in:title'`.
   None open → the run is healthy, nothing to do; stop and say so.

2. **Parse the body.** Extract the failing scopes with their reasons, any
   advisory survivor counts, and the **Last run** URL. The body is regenerated
   on every full run and auto-closes on a healthy run — never edit it.

3. **Pull the failing legs' logs (load-bearing).** From the run URL's id:
   `gh run view <id> --repo haalfi/remote-store --json jobs`, then for each
   failing `mutate-<scope>` job:
   `gh run view --repo haalfi/remote-store --job <jobId> --log-failed`.
   Classify the failure:
   - **Baseline test failure** — the scope's tests fail before mutation even
     starts. Fix the test/code regression first; mutation is a bystander.
   - **Harness/tooling break** — an import error, plugin INTERNALERROR,
     dependency/config change, or a timeout cascade (`no tests ran`). Fix the
     harness (`mutate_scopes.py` targets, the workflow's install step, or the
     plugin pin), not the tests.
   - **`(setup)` pseudo-scope** — the setup job died before listing scopes
     (e.g. an import chain reaching for a dep the bare runner lacks). Fix
     `scripts/run_mutate.py` / `mutate_scopes.py` imports or the workflow.

4. **Reproduce locally** before claiming a fix: `hatch run mutate <scope>`
   (containers per the scope's `needs` start via `infra/docker-compose.yml`).
   Per CLAUDE.md principle 6, see it fail, fix, see it pass.

5. **Survivors (advisory).** If the body or the run-summary table lists
   surviving mutants, do not treat them as part of this triage. Note them for
   a coverage-hardening pass; the per-scope detail is in the
   `mutation-report-<scope>` HTML artifacts.

6. **Branch hygiene.** Never on `master`; create a dedicated branch off
   `origin/master`, e.g. `fix-mutation-<slug>`.

7. **Ship complete.** Backlog item + trace per CLAUDE.md; CHANGELOG only if a
   `user.*` audience is touched (a pure harness fix is not).

8. **Stop for the user to open the PR.** Push the branch, report the per-scope
   diagnosis and fix, then stop — PR creation is user-initiated via `/pr`.
   Reference the rolling issue with `Refs #<n>` — never `Closes`: the workflow
   owns the issue lifecycle and closes it on the next healthy full run. To
   close promptly after merge, dispatch a full run:
   `gh workflow run mutation.yml --repo haalfi/remote-store`.

## Rules

- A red mutation run is always a harness/implementation regression — pytest's
  exit code never reflects survivors. Treat it with bug-fix urgency.
- Never silence a scope (skip, filter, pardon) to make the issue close;
  fix the cause or escalate with the diagnosis.
- A single-scope dispatch can verify one fix but never closes the issue or
  rewrites its body (its findings land as comments); only a healthy **full**
  run closes it. Never close the rolling issue by hand.
