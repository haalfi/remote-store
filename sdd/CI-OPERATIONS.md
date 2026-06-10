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
| `mutation.yml` | Sat 05:00 UTC | Actions run summary + actor email | runbook below |
| dependabot + `dependabot-auto-merge.yml` | Mon (weekly) | update PR + its CI status | per-ecosystem runbook below |
| `codeql.yml` | push / PR + Mon 06:00 UTC | Security tab alerts | runbook below (exception) |

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
  `scripts/mutate_scopes.py`; a `summary` job tabulates each scope's outcome.
- **When:** Saturday 05:00 UTC, plus manual `workflow_dispatch` (optionally for a
  single scope).
- **Where the finding shows up:** today, the **Actions-tab run summary and
  GitHub's actor email only** — there is no rolling issue yet. This is the open
  Rule 1 gap, tracked by the `mutation` item in [`sdd/BACKLOG.md`](BACKLOG.md);
  until it lands, scan the Saturday run even on a quiet inbox.
- **How to act:** open the run and classify which of two outcomes occurred — they
  need different responses:
  - **Surviving mutant** — a genuine test-coverage gap (a mutated line no test
    caught). Advisory: fold it into a coverage-hardening pass; not urgent, since
    strict coverage gates already run in CI.
  - **Harness / implementation failure** — the run itself broke (an import,
    config, or tooling error, not a mutant; this is what the weekend break was).
    Treat it as a regression: fix the harness or code so the weekly run is green
    again.

### dependabot + `dependabot-auto-merge.yml` — dependency update PRs

- **What it does:** dependabot opens weekly update PRs for the `pip` and
  `github-actions` ecosystems (`.github/dependabot.yml`).
  `dependabot-auto-merge.yml` triggers on a maintainer's `pull_request_review`
  approval and enables `--auto --squash` merge to `master`.
- **When:** Monday, weekly.
- **Where the finding shows up:** the **PR list** and each PR's CI status. The
  approval click is the load-bearing gate — it is what fires the merge.
- **How to act — verify before approving, per ecosystem:**
  - **`github-actions` (`Chore(deps)`):** a green check means the workflow still
    *parses*, not that the bumped action *behaves* — most action bumps exercise
    nothing testable. Diff the action's changelog and confirm no `with:` input or
    permission surface changed before approving.
  - **`pip` dev-dep (`Chore(deps-dev)`):** a red CI is a real signal. Decide
    whether the failing ceiling is real (hold the PR, or bump the floor) or
    transient/unsupported (close it).
  - Auto-merge to `master` is irreversible once approval fires; tightening this
    control (e.g. dropping auto-merge for `github-actions`) is tracked by the
    dependabot-approval item in [`sdd/BACKLOG.md`](BACKLOG.md).

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
