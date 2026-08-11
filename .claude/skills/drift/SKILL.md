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

A green smoke means the committed pins were the ones *installed*: the smoke is
pinned to the candidate resolution with a pip constraints file, so it cannot
quietly run against a mixed set. A plugin that cannot coexist with that set
fails the smoke instead — which is why a red smoke is a real regression or a
harness gap, never a silent mixed-set pass.

**It does not follow that the drifted package was exercised.** Pin identity and
smoke *reach* are different claims, and reach varies per extra: an `--import-only`
target in `drift_smoke_map.py` may load one dependency and none of the others, so
a green verdict can cover none of what drifted (BUG-250 — `[graph]` is the known
case). Before treating a green verdict as licence, check that the extra's smoke
target can actually load the drifted package; where it cannot, say so and name
whatever real evidence you do have.

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
   - **success** → smoke passed against the fresh resolution. Refreshable, if the
     target reaches the drifted package — see the reach caveat above.
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

7. **Refresh.** [`infra/drift-locks/README.md` § Refreshing](../../../infra/drift-locks/README.md#refreshing)
   is authoritative on the routes, their preconditions, and the exact lock
   format — follow it rather than the summary here. You are in its
   **drift-guard finding** scenario, not its floor-bump one.

   What the skill adds, because it is about *this* execution context:

   - **Prefer reconstruction from the issue.** You want the resolution the run
     smoked, and reconstruction reproduces it whatever host you are on. A local
     `refresh-baseline` re-resolves with `--pre` at refresh time and can land
     above the snapshot (step 8); the artifact download needs a storage host
     outside `api.github.com`, which a sandboxed session's egress policy
     typically denies — a policy denial, so **do not retry it or route around
     it**, just switch routes.
   - **Reconstruction needs a non-stub baseline and `status: drift`.** A stub
     extra has no rows to apply and would reconstruct to an empty lock. For those,
     the candidate artifact is the route that works — the workflow emits the
     freeze whenever the resolve succeeded, regardless of status.
   - **If you do resolve locally, drive it with `python3.13` directly**, not the
     hatch env: `write_lock` stamps `# python:` from the *running* interpreter, so
     a 3.11 driver writes `# python: 3.11` over a 3.11 dependency set. Assert the
     version before you start, and note the OS matters as much as the version.

   Either way, once the locks are written run `hatch run drift-check render-docs`.

8. **Verify the diff.** `git diff infra/drift-locks docs-src/reference/tested-versions.md`:
   - only the approved extras' locks changed;
   - each refreshed lock's `# captured:` is today's date, and its **`==` lines**
     differ from the baseline in exactly the issue's rows and nothing else. Scope
     that check to the payload: the header is expected to change, so comparing
     whole files will flag `# captured:` as a spurious difference;
   - **no committed pin sits above the run's snapshot.** A local
     `refresh-baseline` re-resolves with `--pre` at refresh time and can land
     newer versions than the run smoked — including packages absent from the issue
     body entirely, so nothing in the drift report flags them. Enumerate any such
     package rather than accepting it, and default to pinning it back; README
     § Refreshing has the reasoning and the exception.
   Then `hatch run drift-check render-docs --check` (also a `preflight` gate) to
   confirm the docs page is in sync.

9. **CHANGELOG / trace.** A pure baseline + tested-versions refresh is
   infra-and-generated-docs only, so no CHANGELOG entry — add one only if this
   refresh accompanies a deliberate `pyproject.toml` floor bump.

   A routine refresh neither implements nor closes the drift-guard item, so a
   trace is not *required* ([CLAUDE.md § Trace authoring](../../../CLAUDE.md#trace-authoring)
   exempts a pure advisory annotation; it does not forbid one). In practice
   every firing so far has annotated the trace anyway, because what a firing
   teaches is how the guard behaves in production and that record has nowhere
   else to live. **So: append an "Operational firing" block to the drift-guard
   trace whenever the refresh taught you something** — a path that failed, a
   smoke that proved weaker than its verdict implied, a caveat a procedure doc
   missed. Follow the existing blocks' shape. A refresh that went entirely to
   plan needs no block.

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
