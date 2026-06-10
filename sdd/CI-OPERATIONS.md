# CI Operations
<!-- doc: dual dest=explanation/design/ci-operations.md -->

## Intent & Scope

THE source for how remote-store's scheduled and automated CI guards notify a
maintainer and how each finding is triaged. Governs the workflows under
`.github/workflows/` that run without a contributor present (scheduled sweeps
and review-triggered automation) plus the dependabot update streams. The gating
push/PR test matrix and coverage lanes are merge gates, not maintenance guards,
and live in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Rules

1. **Durable-TODO principle.** Every scheduled-maintenance guard emits a durable
   GitHub Issue as its TODO and has a triage entry point (a skill or a checklist
   in this doc). A red X, a green check, and GitHub's actor email are
   insufficient alone: each is transient or filterable, so a guard whose only
   output is one of those is not a guard a maintainer can rely on.

2. **Three layers, kept in agreement.** Every guard is documented in three
   places: the workflow file header (what it does and its non-goals), the
   inventory below (when it runs and where its finding lands), and its triage
   skill or checklist (how to act). Adding or changing a guard means updating all
   three in the same change.

3. **Exceptions are recorded, never implicit.** A guard that deliberately does
   not satisfy Rule 1 — because it reports to a channel GitHub owns — is listed
   under _Exceptions_ with its reason and review cadence. An undocumented
   scheduled or review-triggered workflow fails `scripts/check_ci_inventory.py`.

## Guides

### Inventory

The scheduled/automated family is every workflow that runs on `schedule` or
`pull_request_review`, plus the dependabot update streams.
`scripts/check_ci_inventory.py` (wired into `hatch run lint`) parses
`.github/workflows/*.yml` and fails if a workflow on a family trigger is not
named in this table or under _Exceptions_.

| Workflow | Trigger | Finding surface | Durable TODO | Triage |
|---|---|---|---|---|
| `drift-guard.yml` | Mon 07:00 UTC | rolling `[drift-guard]` Issue | yes | `/drift` skill |
| `mutation.yml` | Sat 05:00 UTC | run summary + actor email | not yet | — |
| `dependabot-auto-merge.yml` | `pull_request_review` (approve) | auto-merge to `master` | partial | — |
| dependabot (pip / github-actions) | Mon (weekly) | PR, red or green | partial | — |
| `codeql.yml` | push / PR + Mon 06:00 UTC | Security-tab alerts | exception | _Exceptions_ |

`ci.yml` (push / PR) is the gating test matrix, not a maintenance guard: a
contributor is present to read its result, so it sits outside this family and is
documented in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

The `mutation.yml` and dependabot rows describe the surface as it stands today:
neither yet emits the rolling issue + triage skill Rule 1 calls for. Closing
that gap is tracked in `sdd/BACKLOG.md` (the `mutation` and dependabot-approval
items); this table moves to "yes" when they land.

### Exceptions

- **`codeql.yml`** — the weekly full sweep (Mon 06:00 UTC) reports findings as
  code-scanning alerts in the repository **Security tab**, GitHub's canonical
  surface for this class. By design it opens no rolling issue and has no triage
  skill. Reviewed when a Security-tab alert appears and during any security pass.

### Adding a guard

A new scheduled or review-triggered workflow must, in the same change:

1. carry a header comment stating what it does and its non-goals
   (`drift-guard.yml` is the reference);
2. gain a row in the inventory above (or an _Exceptions_ entry with a reason);
3. either reuse the rolling-issue + triage-skill pattern (`drift-guard.yml` +
   `scripts/drift_report.py` + the `/drift` skill) or record under _Exceptions_
   why it does not.

`scripts/check_ci_inventory.py` enforces step 2 mechanically; steps 1 and 3 are
reviewer-enforced.
