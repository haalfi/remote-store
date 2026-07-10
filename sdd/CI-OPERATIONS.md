# CI Operations
<!-- doc: dual dest=explanation/design/ci-operations.md -->

## Intent & Scope

THE operations handbook for remote-store's scheduled and automated CI guards.
For each guard it answers the four questions a maintainer has when one fires:
what it does, when it runs, where its finding shows up, and how to act. Covers
every workflow under `.github/workflows/` that runs without a contributor
present (scheduled sweeps and review-triggered automation) plus the dependabot
update streams. The gating push/PR test matrix and coverage lanes are merge
gates, not maintenance guards, and live in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Rules

1. **Durable-TODO principle.** Every scheduled-maintenance guard emits a durable
   GitHub Issue as its TODO and has a triage entry point (a skill or a runbook
   in this doc). A red X, a green check, and GitHub's actor email are
   insufficient alone: each is transient or filterable, so a guard whose only
   output is one of those is not a guard a maintainer can rely on.

2. **Three layers, kept in agreement.** Every guard is documented in three
   places: the workflow file header (what it does and its non-goals), the
   runbook below (when it runs, where its finding lands, how to act), and its
   triage skill where one exists. Adding or changing a guard means updating all
   three in the same change.

3. **Exceptions are recorded, never implicit.** A guard that deliberately does
   not satisfy Rule 1 — because it reports to a channel GitHub owns — is listed
   as an exception with its reason and review cadence. An undocumented scheduled
   or review-triggered workflow fails `scripts/check_ci_inventory.py`.

## Guides

### Inventory at a glance

The scheduled/automated family is every workflow that runs on `schedule` or
`pull_request_review`, plus the dependabot update streams. Each row below has a
runbook in this section. `scripts/check_ci_inventory.py` (wired into
`hatch run lint`) parses `.github/workflows/*.yml` and fails if a family
workflow is not named here.

| Guard | When | Finding shows up in | How to act |
|---|---|---|---|
| `drift-guard.yml` | Mon 07:00 UTC | rolling `[drift-guard]` Issue | `/drift` skill |
| `mutation.yml` | Sat 05:00 UTC | rolling `[mutation]` Issue (harness failures) | `/mutation` skill |
| dependabot + `dependabot-auto-merge.yml` | Mon (weekly) | update PR + its CI status | per-ecosystem runbook below |
| `codeql.yml` | push / PR + Mon 06:00 UTC | Security tab alerts | runbook below (exception) |
| `benchmark.yml` | Mon 04:17 UTC + dispatch | red run + `benchmark-results` artifact + job summary | runbook below (exception) |

`ci.yml` (push / PR) is the gating test matrix, not a maintenance guard: a
contributor is present to read its result, so it sits outside this family and is
documented in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

### `drift-guard.yml` — transitive dependency drift

- **What it does:** re-resolves every `remote-store[<extra>]` against the latest
  available transitive versions (including pre-releases), diffs against the
  committed baselines in `infra/drift-locks/`, and runs the most-likely-to-break
  smoke tests for any extra that drifted. It never edits `pyproject.toml` and
  never auto-merges a floor/pin — it is early warning, not remediation.
- **When:** Monday 07:00 UTC, plus manual `workflow_dispatch` (optionally for a
  single extra).
- **Where the finding shows up:** a single **rolling `[drift-guard]` GitHub
  Issue** — opened or updated when any extra drifts, commented "cleared" and
  closed when all are clean. The per-extra **smoke verdict** lives in the linked
  Actions run, not the issue body.
- **How to act:** run the **`/drift` skill**. It reads the rolling issue, then
  for each drifted extra reads that extra's smoke-job conclusion in the linked
  run — the load-bearing signal — and refreshes only the baselines whose smoke is
  green and whose bump is non-major. A red smoke is never refreshed until its
  cause (real regression vs smoke-harness gap) is explained. The skill prepares a
  pushed branch and stops; the maintainer opens the PR.

### `mutation.yml` — mutation testing

- **What it does:** runs mutation testing across the scopes defined in
  `scripts/mutate_scopes.py`. Every `mutate-<scope>` leg records a per-scope
  outcome JSON (`job.status` + the pytest-gremlins report counts), and the
  `summary` job classifies them via `scripts/mutation_report.py` and
  reconciles the rolling issue.
- **When:** Saturday 05:00 UTC, plus manual `workflow_dispatch` (optionally for a
  single scope).
- **Where the finding shows up:** depends on which of the two outcomes
  occurred. They are deliberately split:
  - **Harness / implementation failure** (the run itself broke: an import,
    config, or tooling error, a baseline test failure, a leg that recorded no
    outcome or no readable report): the run is **red** AND the single
    **rolling `[mutation]` GitHub Issue** is opened or updated. This diverges
    from drift-guard's never-red model on purpose: a broken weekly guard is a
    real regression worth both a red X and a durable TODO.
  - **Surviving mutant** (a mutated line no test caught): **advisory only**.
    The run stays green and no issue is opened; counts appear in the
    run-summary table and the per-scope HTML report artifacts. The mutation
    runner never fails a run on survivors, and strict coverage gates already
    run in CI, so survivors feed a coverage-hardening pass rather than a
    standalone TODO.
- **How to act:** run the **`/mutation` skill**. It reads the rolling issue,
  classifies each failing scope from the linked run's logs (baseline test
  failure vs harness/tooling break vs setup death), and fixes the regression
  on a pushed branch. Surviving mutants are noted for a coverage-hardening
  pass, never patched ad hoc. The issue auto-closes on the next healthy full
  run; a single-scope dispatch never closes it or rewrites its body (its
  findings land as comments).

### dependabot + `dependabot-auto-merge.yml` — dependency update PRs

- **What it does:** dependabot opens weekly update PRs for the `pip` and
  `github-actions` ecosystems (`.github/dependabot.yml`).
  `dependabot-auto-merge.yml` triggers on a maintainer's `pull_request_review`
  approval and enables `--auto --squash` merge to `master`, for the **`pip`
  ecosystem only**. `github-actions` PRs are excluded from auto-merge by the
  workflow's head-ref guard (`dependabot/github_actions/`): an action bump
  usually exercises nothing in the test suite, so a green check means the
  workflow *parses*, not that the bumped action *behaves*, and approval alone
  carries no real signal there. The exclusion is a control, not a convention;
  it is pinned by `tests/scripts/test_dependabot_automerge_control.py`.
- **When:** Monday, weekly.
- **Where the finding shows up:** the **PR list** and each PR's CI status. For
  `pip` PRs the approval click is the load-bearing gate: it fires the merge.
  For `github-actions` PRs the merge itself is the manual step.
- **How to act, per ecosystem:**
  - **`github-actions` (`Chore(deps)`):** diff the action's changelog and
    confirm no `with:` input or permission surface changed. Then merge
    manually: `gh pr merge <N> --squash --delete-branch` (approval alone does
    nothing for this ecosystem).
  - **`pip` dev-dep (`Chore(deps-dev)`):** a red CI is a real signal. Decide
    whether the failing ceiling is real (hold the PR, or bump the floor) or
    transient/unsupported (close it). Approve only when green and understood:
    approval auto-merges to `master`, irreversibly.

### `codeql.yml` — security scanning (exception to Rule 1)

- **What it does:** CodeQL static analysis. The weekly full sweep runs regardless
  of paths, catching what the path-filtered push/PR runs miss.
- **When:** push / PR, plus Monday 06:00 UTC.
- **Where the finding shows up:** **code-scanning alerts in the repository
  Security tab** — GitHub's canonical surface for this class. By design it opens
  no rolling issue and has no triage skill; this is the one sanctioned exception
  to Rule 1.
- **How to act:** review Security-tab alerts when one appears and during any
  security pass; fix or dismiss per alert with a recorded reason.

### `benchmark.yml` — benchmark suite (exception to Rule 1)

- **What it does:** runs the `benchmarks/` suite (local + Docker-backed S3/SFTP/
  Azure) as a **correctness gate** — a benchmark that errors or leaks a resource
  fails the run — and compares a fresh local-backend run against the committed
  baseline (`benchmarks/baseline/local-baseline.json`) via
  `report.py --regression`, flagging any op that regresses past `2x` above a
  `500us` floor. It exists because every `ci.yml` lane runs `-p no:benchmark`, so
  the suite otherwise executes nowhere and rots undetected (its first job was to
  close BUG-228, a benchmark leak that had gone unnoticed for exactly that
  reason). It is intentionally kept off push/PR CI: shared-runner timing is noisy
  and would flake a merge gate.
- **When:** Monday 04:17 UTC, plus manual `workflow_dispatch` (with a
  `quick`/`standard`/`full` tier input).
- **Where the finding shows up:** the **red run**, the **regression table in the
  job summary**, and the uploaded **`benchmark-results` artifact** (run JSON +
  text reports, 90-day retention). This is the exception: it opens no rolling
  issue and has no triage skill.
- **Why an exception:** the finding surfaces on GitHub-owned channels (the
  scheduled-run status and its artifacts), the same rationale as `codeql.yml`.
  A rolling-issue + triage-skill integration is **deferred** until the guard
  earns it — if weekly regression flags prove frequent or the correctness gate
  starts catching real rot, promote it to the drift-guard pattern. The
  data-freshness follow-up (a reproducible run of record feeding the published
  overhead numbers) is tracked as ID-230.
- **How to act:** on a red run, open the run and read the regression table.
  A flagged op is either a real regression (fix it) or a baseline that has
  drifted from the current runner class — refresh the baseline from a known-good
  run per `benchmarks/README.md` § Continuous Benchmarking. A correctness failure
  (a benchmark erroring/leaking) is always real and fixed like any test failure.
  **One false-red to rule out first:** the job restores the shared BK-279 image
  cache but has no `prepare-images` job of its own, so on a cache miss it pulls
  Azurite/SFTP from their block-prone registries. A failure in the
  `start-backends` step (image pull/health-check) is infra noise — re-run the
  job — not a benchmark regression.

### Adding a guard

A new scheduled or review-triggered workflow must, in the same change:

1. carry a header comment stating what it does and its non-goals
   (`drift-guard.yml` is the reference);
2. gain a runbook section above — when it runs, where its finding shows up, and
   how to act — or be recorded as an exception with a reason;
3. either reuse the rolling-issue + triage-skill pattern (`drift-guard.yml` +
   `scripts/drift_report.py` + the `/drift` skill) or record why it does not.

`scripts/check_ci_inventory.py` enforces that the workflow is named here; the
runbook content and the issue/skill wiring are reviewer-enforced.
