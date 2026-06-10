---
name: drift
description: Triage and act on the weekly drift-guard rolling issue (transitive dependency drift)
disable-model-invocation: true
argument-hint: "[issue number]"
---

Act on the `[drift-guard]` rolling issue: decide which extras are safe to
re-baseline, refresh those locks, and prepare a pushed branch for the user to
open the PR via `/pr`.

**Authority (do not duplicate — read these):**
- `sdd/CI-OPERATIONS.md` — the cross-guard handbook: where this guard sits in
  the scheduled/automated family and the durable-TODO principle it follows.
- `.github/workflows/drift-guard.yml` header — refresh procedure + the three
  hard non-goals (the workflow never edits `pyproject.toml`, never auto-merges
  a floor/pin, never auto-remediates).
- `infra/drift-locks/README.md` § Refreshing — the canonical command pair.
- `scripts/drift_check.py` module docstring — subcommand semantics.

**The core rule this skill exists to enforce:** the issue body reports *version*
drift only. Whether drift is *safe to accept* is decided per-extra by that
extra's **smoke job conclusion in the linked run** — not by the body. A red
smoke means either a real regression or a smoke-harness gap; never refresh an
extra whose smoke is red until you have explained why.

GitHub reads via `gh` CLI; writes (PR) via the configured GitHub MCP server,
falling back to `gh` for GraphQL-only flows. Repo: `haalfi/remote-store`.

## Steps

1. **Locate the issue.** If `$ARGUMENTS` is an issue number, use it. Otherwise
   find the single open rolling issue by title prefix (it carries no label):
   `gh issue list --repo haalfi/remote-store --state open --search '[drift-guard] in:title'`.
   None open → drift has cleared, nothing to do; stop and say so.

2. **Parse the body.** Extract: the drifted extras and their per-package
   `baseline → resolved` rows, the **Clear** list, and the **Last run** URL.
   The body is regenerated every run and auto-closes on clear — never edit it.

3. **Pull the run's per-extra smoke verdict (load-bearing).** From the run URL's
   id: `gh run view <id> --repo haalfi/remote-store --json jobs`. Each extra has
   a `check-<extra>` job. The drift workflow runs the smoke targets
   (`scripts/drift_smoke_map.py`) only when that extra drifted, so for every
   drifted extra the job conclusion *is* the smoke verdict:
   - **success** → smoke passed against the fresh resolution. Refreshable.
   - **failure** → do NOT refresh yet. Fetch the failed step
     (`gh run view --repo haalfi/remote-store --job <jobId> --log-failed`) and
     classify:
     - **Real regression** — a drifted dep actually broke backend/ext behaviour.
       This is a bug, not a baseline event: surface it, propose a backlog item
       (ask first — never open one unilaterally), and leave the lock alone so
       the issue keeps flagging it.
     - **Smoke-harness gap** — the failure is the smoke env's fault, not the
       dependency's (e.g. a test needs an extra the smoke env doesn't install,
       so it errors with `ModuleNotFoundError` regardless of the bump). Fix the
       harness (`drift_smoke_map.py` target or the workflow's smoke-install
       list), not the lock. Refresh only after the smoke is genuinely green.
   - **cancelled** → inconclusive (fail-fast neighbour or concurrency). Re-run
     that leg via `workflow_dispatch` before trusting it.

4. **Triage the version bumps** for the green extras. Classify each
   `baseline → resolved` by semver: patch/minor and `rc → stable` are routine;
   call out any **major** bump or yank explicitly for sign-off before refreshing.

5. **Decision gate.** Summarise per extra: `smoke verdict · bump severity ·
   refresh? (y/n)`. Before any local resolve (it builds throwaway venvs and hits
   PyPI — treat it like a test run), ask the user to confirm the refresh set.
   Default recommendation: refresh every extra that is *green-smoke + non-major*;
   hold the rest with the reason.

6. **Branch hygiene.** Never on `master`; never piggyback unrelated work. Create
   a dedicated branch off `origin/master`, e.g. `drift-refresh-<YYYY-MM-DD>`.

7. **Refresh — match the resolution host, not just the Python version.** A lock
   is both Python- **and OS-specific**: the workflow resolves on **Linux 3.13**,
   and a resolve on another platform pulls platform-conditional deps the CI
   re-resolve never sees (`colorama` via click/tqdm and `pywin32` on Windows,
   etc.). Commit a non-Linux resolve and the *next* CI run diffs its Linux
   resolution against your lock, flags those packages as "removed" drift, and the
   rolling issue never clears. So choose the source by host:

   - **Not on Linux 3.13 (canonical path) — use the run's candidate artifacts.**
     The workflow uploads a Linux-resolved freeze per extra for exactly this:
     `gh run download <run-id> --repo haalfi/remote-store --pattern 'candidate-baseline-*' --dir <tmp>`
     (the `<run-id>` is the issue's **Last run**). For each approved extra, write
     `infra/drift-locks/<extra>.txt` as the lock header
     (`# extra:` / `# python: 3.13` / `# captured: <today>` / regenerate line, a
     blank line) followed by the artifact's freeze **sorted by package name**
     (the part before `==`, so `dagster` precedes `dagster-pipes`) — matching
     `scripts/drift_check.py::write_lock` exactly.
   - **On Linux 3.13 (matches the runner) — local resolve is fine.** Assert
     `python --version` is 3.13, then per approved extra:
     `hatch run drift-check refresh-baseline <extra>`.

   Either way, once the locks are written run `hatch run drift-check render-docs`.

8. **Verify the diff.** `git diff infra/drift-locks docs-src/reference/tested-versions.md`:
   - only the approved extras' locks changed;
   - the package deltas match the issue's rows. The candidate-artifact path
     matches the snapshot exactly (same run); a later local `refresh-baseline`
     re-resolves with `--pre` and may show *newer* stable/pre-release than the
     snapshot — expect the latest at refresh time, not the frozen versions;
   - each refreshed lock's `# captured:` advanced.
   Then `hatch run drift-check render-docs --check` (also a `preflight` gate) to
   confirm the docs page is in sync.

9. **CHANGELOG / trace.** A pure baseline + tested-versions refresh is
   infra-and-generated-docs only: no CHANGELOG entry, and a routine refresh
   neither implements nor closes the drift-guard item, so no trace. Add a
   CHANGELOG entry only if this refresh accompanies a deliberate
   `pyproject.toml` floor bump.

10. **Commit** the locks + regenerated docs together. Prefix the subject with
    the drift-guard backlog item ID (named in the `drift-guard.yml` header and
    `infra/drift-locks/README.md`), per [CLAUDE.md § Backlog](../../../CLAUDE.md#backlog):
    `<id>: refresh drift baselines (<extras>)`.

11. **Stop for the user to open the PR.** Push the branch, then **stop — do not
    run `/pr` automatically.** PR creation is user-initiated in this repo. Report
    the prepared state so the user can review and invoke `/pr` themselves:
    - the branch and its commits;
    - the per-extra refresh outcome, plus any held extras with reasons and any
      follow-up from step 3;
    - the harness fix, if one was needed to turn a red smoke green.

    Flag for the eventual PR body: list the accepted bumps per extra and
    **reference** the rolling issue with `Refs #<n>` — never `Closes`. The
    workflow owns the issue lifecycle and auto-closes it on the next run that
    resolves clean. To close promptly after merge, the user can re-resolve via
    `gh workflow run drift-guard.yml --repo haalfi/remote-store` (the workflow is
    on `master`, so dispatch resolves fine).

## Rules

- Per-extra gating is non-negotiable: green smoke is the licence to refresh.
- This skill prepares the refresh (locks, docs, any harness fix) and stops at a
  pushed branch; the user opens the PR via `/pr`. It never edits
  `pyproject.toml` floors, never merges, and never closes the rolling issue by hand.
