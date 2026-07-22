# CI Operations
<!-- doc: dual dest=explanation/design/ci-operations.md -->

## Intent & Scope

THE operations handbook for remote-store's scheduled and automated CI guards.
For each guard it answers the four questions a maintainer has when one fires:
what it does, when it runs, where its finding shows up, and how to act. Covers
every workflow under `.github/workflows/` that runs without a contributor
present (scheduled sweeps and review-triggered automation) plus the dependabot
update streams. One **external** entry — Read the Docs — is also covered: it
builds the docs site without a contributor present but lives outside
`.github/workflows/`, and its build triggers plus dashboard-held configuration
have no other home in the repo. The gating push/PR test matrix and coverage
lanes are merge gates, not maintenance guards, and live in
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

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
workflow is not named here. Read the Docs is the one **external** row — not a
`.github/workflows/` file, so `check_ci_inventory.py` does not parse it; it is
documented here by convention, not enforcement.

| Guard | When | Finding shows up in | How to act |
|---|---|---|---|
| `drift-guard.yml` | Mon 07:00 UTC | rolling `[drift-guard]` Issue | `/drift` skill |
| `mutation.yml` | Sat 05:00 UTC | rolling `[mutation]` Issue (harness failures) | `/mutation` skill |
| dependabot + `dependabot-auto-merge.yml` | Mon (weekly) | update PR + its CI status | per-ecosystem runbook below |
| `codeql.yml` | push / PR + Mon 06:00 UTC | Security tab alerts | runbook below (exception) |
| `benchmark.yml` | Mon 04:17 UTC + dispatch | red run + `benchmark-results` artifact + job summary | runbook below (exception) |
| `ci-full.yml` | `master` push + 03:00 UTC daily + dispatch | red run on the Actions tab | runbook below (exception) |
| Read the Docs (external) | `master` push + release tag | RTD build dashboard + the live site | runbook below (external exception) |

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
  `quick`/`standard`/`full` tier input, and a `run_of_record` toggle — see the
  run-of-record job below).
- **Where the finding shows up:** the **red run**, the **regression table in the
  job summary**, and the uploaded **`benchmark-results` artifact** (run JSON +
  text reports, 90-day retention). This is the exception: it opens no rolling
  issue and has no triage skill.
- **Why an exception:** the finding surfaces on GitHub-owned channels (the
  scheduled-run status and its artifacts), the same rationale as `codeql.yml`.
  A rolling-issue + triage-skill integration is **deferred** until the guard
  earns it — if weekly regression flags prove frequent or the correctness gate
  starts catching real rot, promote it to the drift-guard pattern.
- **The `run-of-record` job (ID-230).** A second, opt-in job in the same
  workflow produces the **published overhead story** — the fresh source behind
  `benchmarks/results/comparative.md` and the five docs charts. It runs **only**
  on `workflow_dispatch` with the `run_of_record` input checked (never on the
  weekly schedule — a full latency matrix every Monday is CI cost for no gate
  value). Unlike the correctness gate, it brings up the **full compose stack**
  (`infra/docker-compose.yml`, so Toxiproxy is wired in front of the network
  backends — the `start-backends` action has no Toxiproxy), runs the `clean`
  profile plus the `rtt20/rtt50/rtt100` matrix on the `-latency` backends,
  regenerates `comparative.md` + the SVGs (guarded by
  `benchmarks/slim_run_of_record.py` against the three silent-chart-failure
  modes), and uploads them as the **`run-of-record`** artifact. **CI never
  commits docs:** a maintainer downloads that artifact and commits the files.
  See `benchmarks/README.md` § Run of record for the regeneration recipe.
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

### `ci-full.yml` — full live-backend matrix backstop (exception to Rule 1)

- **What it does:** runs the complete two-pass live-Docker-backend suite (pass-1
  `-n auto` + serial `sftp_docker`) on **every** supported interpreter
  (3.10–3.14). This is the pre-BK-319 per-interpreter guarantee. `ci.yml` (the
  per-PR gate) runs this full Stage-2 suite only on the **primary** interpreter;
  the four non-primary interpreters run the repo-only **Stage 1** tier there to
  keep PR wall-clock under 5 min on the 20-concurrent-job cap. `ci-full.yml`
  restores full-matrix coverage off the per-PR critical path.
- **When:** every push to `master`, plus 03:00 UTC daily, plus
  `workflow_dispatch`.
- **Where the finding shows up:** the **red run on the Actions tab**. Like
  `codeql.yml` / `benchmark.yml` it opens no rolling issue and has no triage
  skill — this is a sanctioned Rule-1 exception.
- **Why an exception:** a maintainer merging to `master` (or reading the nightly
  status) is present to see a red run; the finding surfaces on GitHub-owned
  channels. A rolling-issue integration is **deferred** until it earns one — if a
  non-primary-interpreter-only live-backend regression ever actually slips past
  the per-PR gate, promote it to the drift-guard pattern.
- **How to act:** on a red run, open it and read the failing interpreter leg — a
  genuine test failure is fixed like any other. The same BK-279 image-cache
  false-red as `benchmark.yml` applies: a `start-backends` step failure
  (image pull / health-check) is infra noise — re-run the job.

### Read the Docs — docs site build & hosting (external, exception to inventory)

- **What it does:** Read the Docs builds the MkDocs site (`.readthedocs.yaml`,
  which points at `mkdocs.yml`) and serves it at **`docs.remotestore.dev`** — the
  canonical docs site. (The mike → `gh-pages` build in `docs.yml` is a *separate*
  GitHub Pages deployment with its own `dev`/`latest` aliases; it does not serve
  this domain.) A `post_build` job runs `scripts/docs/gen_llms_api.sh` (ID-226) to
  emit `/llms-api.txt` next to the `mkdocs-llmstxt` `llms.txt` / `llms-full.txt`
  (ID-220).
- **When:** every push to `master` (builds the `latest` version) and each release
  tag. Tag builds are activated by the RTD **automation rule** "Activate version
  on tag creation" (type Tag, empty pattern = all tags); RTD then re-points the
  built-in `stable` version at the newest tag. Not a `.github/workflows/` job.
- **Where the finding shows up:** the **RTD build dashboard** (build logs on
  app.readthedocs.org) and the live site. No GitHub Actions run, no red X, no
  rolling issue — this is why it is an **exception**, and why
  `scripts/check_ci_inventory.py` does not parse it (that gate reads
  `.github/workflows/*.yml` only; RTD is inventoried here by convention).
- **Out-of-repo state the maintainer owns (RTD dashboard):**
  - **Default version `stable`** with URL scheme `/<version>/<filename>`, so the
    canonical deep-link form is `docs.remotestore.dev/stable/…` and every doc link
    uses it.
  - **One redirect** (Admin → Redirects): `/context7.json` →
    `/stable/context7.json`. It lets Context7 fetch the docs-site manifest (built
    from `docs-src/context7.json`) at the domain root. Because `/stable/` is the
    highest-tag build, a change to that manifest reaches the redirect target only
    on the next release; repoint the redirect at `/latest/context7.json` to serve
    the `master` build sooner.
  - The **automation rule** above and the **`docs.remotestore.dev` custom
    domain**.
- **In-repo pieces kept in sync:** `.readthedocs.yaml` (Python pinned to
  `.python-version`, enforced by `scripts/check_readthedocs_python.py` in
  `hatch run lint`); `scripts/docs/gen_llms_api.sh` (pins `lx`, non-fatal by
  contract — always exits 0, so it never fails a build).
- **How to act:** on a failed build, open the RTD build log. A Python-version
  mismatch is already caught by `check_readthedocs_python.py`, so a red build is
  usually a `mkdocs build --strict` error (reproduce with `hatch run docs-build`);
  the non-fatal `post_build` cannot fail it. After a release, confirm
  `docs.remotestore.dev/stable/` shows the new version, per
  [`CONTRIBUTING.md`](../CONTRIBUTING.md) § Release, Phase 5. Editing the docs-site
  manifest identity or its redirect is a dashboard action, not a repo change.

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
