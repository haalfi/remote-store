# RFC-0019: Two-speed test gate with a rule-based selector

## Status

Draft. **Phase 0 (2026-10-04) stopped the selector as designed in D5; the
motivation stands, and the RFC needs a better selection idea before any later
phase.** Nothing below is built. The maintainer approved Phase 0 only. Its
report, [Phase 0 report](../research/bk-403-phase-0/report.md),
measured the precision rule set against targets fixed before the run. Typical
code diffs still run the full suite: 72.6% of 106 code PRs fall back to FULL,
and the median wall-clock share is 100%, against targets of at most 30% and
50%. Both stop conditions fire.

- **Where the fallback comes from.** D5's FULL row alone fires on 59 of the
  106 code PRs, through `pyproject.toml` and `.github/**`. Base modules every
  test reaches account for most of the rest. Any revision has to narrow those
  rows or reduce that fan-out.
- **What already works.** Where the selector narrows, it is sound and small.
  The reader inventory, the seeds and the historical misses are reported
  separately.
- **Five defects in D5 and D7.** The report records them; they are not yet
  amended here.

Tracked as **BK-403**, with the design for BK-404 (local target) and ID-266
(CI lane). All three stay open.

*Superseded framing:* this RFC sought approval for Phase 0 and a limited local
pilot, and treated the target architecture below as the direction rather than a
build order.

## Management Summary

**The full gate is removed from intermediate iteration pushes, but stays
mandatory for the exact head that is meant to merge.** Those pushes run only
the tests a change can reach. Today both gates run everything on every push.
The selector that picks the tests is a committed rule set, not a runtime
coverage map, and it runs the full suite whenever it cannot place a change.

- **Every PR push, including each review and fix round:** the fast lane. Lint,
  typecheck and the selected tests, on every supported interpreter.
- **On request, and always on the merge head:** the existing full gate,
  unchanged, whenever a head is marked `merge-candidate`. The final head must
  carry a full run; the author or a reviewer may also mark an earlier head when
  a full run is useful, for example after a risky round.
- **After merge:** the existing `ci-full.yml` backstop, unchanged.

**What it costs today.**

- `hatch run all` runs all 11,932 Stage-1 tests whatever the diff touched;
  tests are 532 s of its 666 s ([audit-022](../audits/audit-022-gate-speed-strategies.md)
  § H1, per-member timing).
- `ci.yml` ran the full gate 8 times on PR #1054 in under two hours
  (audit-022 § M1, `list_workflow_runs` on its head branch). `/ship` pushes
  each review round to a PR that `/pr` already opened as non-draft (audit-022
  § M1, "`/ship` constraint"), so a trigger based on draft state would not
  reach those pushes.

**Why rules and not a coverage map.** The `pytest-testmon` PoC
([research](../research/research-bk-403-testmon-poc.md)) found two blockers
that belong to the mechanism, not to selection:

- it missed the known failing test on 7 of 13 seeded changes: non-Python
  inputs, a package `__init__.py`, and source read as text (Appendix B, rows
  marked **no**);
- it discards its map on any change of Python patch version or package minor
  version (Appendix C), which makes it unusable across CI legs.

Rules see what a tracer cannot, depend only on the diff and the repository,
and can explain every test they pick.

**What the decision guards.**

1. The full gate stays the only merge barrier, enforced by branch protection on
   the exact head.
2. A selected run never claims the 95% coverage floor.
3. The selector fails open: unknown path, selector error, or a selection too
   large to save time runs the full suite.
4. The existing change-class filter (docs, formal, TLA, hooks) stays the first
   axis; a change with no code part runs the same jobs in both lanes and needs
   no merge-candidate mark.
5. Nothing is switched on before it has been measured: Phase 0 validates on
   seeded changes and historical PRs with a stop criterion fixed in advance,
   and the CI lane runs in shadow mode before it decides anything.
6. The first selector is deliberately narrow (D5, pilot rule set). Precision
   is added one layer at a time, each layer gated by its own measurement.
7. Every fast run records whether it selected or fell back to FULL and why
   (D7). Falling back to FULL is safe, but if it happened unrecorded it would
   quietly remove the saving.

## Motivation

**The cost is in the loop before merge, and the existing mechanisms do not
narrow it.** The repo already narrows CI by file class (`CODE_PAT`,
`DOCS_PAT`, `FORMAL_PAT`, `TLA_PAT`, `HOOKS_PAT`, `.github/workflows/ci.yml`
`setup`) and by tier ([ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md)).
Neither narrows by what a code change can reach: any `src/` or `tests/` edit
sets `code=true`, and `code` starts 15 jobs (`grep -c "outputs.code == 'true'"`
over `ci.yml`, `tooling-tests` counted once).

**Three lessons shape the design.**

1. **Selection by coverage map failed on this repo** (§ Management Summary).
   Its blind spots are exactly the path classes a written rule can name.
2. **Draft state is the wrong switch.** `/ship` and `/fix-pr` push most of
   their rounds after the PR is open for review, so a draft-only fast lane
   saves little. What matters is whether a head is meant to merge.
3. **`/ship` needs the full interpreter matrix per round.**
   `.claude/skills/ship/SKILL.md` § Close each round records an
   interpreter-specific red that only the matrix showed. The fast lane keeps
   every interpreter and narrows tests, not legs.

## Proposal

### D1. Two lanes, switched by a merge-candidate signal

**Every PR push runs the fast lane; the full lane runs on a head marked
`merge-candidate`, and any push clears the mark.** Draft state plays no role.
The mark is a request for a full run, not a promise that the head is final: it
is required on the merge head (D2) and allowed on any earlier head the author
or a reviewer wants checked in full. The full gate therefore runs on every PR's
merge head, and on an intermediate push only on request.

**The label is the pilot mechanism, and a known piece of process debt.** The
merge-time enforcement a merge queue would give is not available. ADR-0043's
reversal clause names merge-queue capacity as missing for this personal
account (audit-022 § M1). The label stays until that changes. If a merge queue
becomes available, the full lane moves to the queue and the label goes.

| Lane | Trigger | Runs | Coverage floor |
| --- | --- | --- | --- |
| Local fast | before every push | lint, typecheck, selected tests | — |
| Local full | recommended before marking a merge candidate; not enforced | `hatch run all` | — |
| CI fast | `opened`, `synchronize`, `reopened` with `code=true` and a narrowed selection | lint, typecheck, selected tests on every interpreter | — |
| CI full | `merge-candidate` label added; or `opened`/`synchronize`/`reopened` with `code=false` or a FULL selection (D4) | today's `ci.yml` | yes |
| Post-merge | master push | `ci.yml` full, `ci-full.yml` | yes |

The local fast target is the gate for every round push. `hatch run all` keeps
its meaning as the full local check; running it before marking a merge
candidate catches a red full run locally instead of in CI, but the CI full lane
is the enforced barrier.

### D2. The merge barrier is a commit status only the full lane posts

**Branch protection requires a status that a successful full run posts on the
PR's head commit; no untampered workflow path can produce it otherwise.** The
limits of that guarantee (a PR editing its own workflow, the admin bypass) are
stated below. A required *job* is not
enough: GitHub reports a required job skipped by its `if:` as passing, so a fast
run, or a run started by an unrelated label, would satisfy a required `gate` job
it skipped.

- The full lane's last step posts commit status `merge-gate: success` on
  `github.event.pull_request.head.sha` (`statuses: write`). Not on `github.sha`:
  on a `pull_request` event that is the synthetic merge commit of
  `refs/pull/<n>/merge` (which is why `setup` uses it only for the diff), and
  branch protection evaluates statuses on the head, so a status there would
  never be seen. On a master `push`, `github.sha` is the head. The fast lane
  never posts the status.
- A push creates a new head without that status, so merge is blocked until the
  full lane has passed on exactly that head. This holds by construction and
  needs no clean-up.
- Branch protection moves from the `gate` job to the `merge-gate` status. The
  `gate` job stays as the full lane's aggregator; the fast lane reports
  `gate-fast`, which is not required.
- **Fork PRs cannot merge on their own.** On a fork `pull_request` event,
  `GITHUB_TOKEN` is read-only whatever `permissions:` asks for, so no lane can
  post `merge-gate` on a fork head. To merge a fork PR, the maintainer pushes
  its head to a branch in this repository and merges from a PR on that branch,
  which runs the normal lanes. A `pull_request_target` or `workflow_run`
  follow-up that posts the status is rejected: it would give a write token to a
  workflow that acts on untrusted code. Forks are rare in this
  single-maintainer repo, so the manual path is enough.

**Who can post `merge-gate`.** A commit status can be written by any workflow
whose token has `statuses: write`, and by anyone with write access.

- **Mechanism:** a commit status via the workflow's `GITHUB_TOKEN`
  (`statuses: write` on the posting job only). A check run created through the
  Checks API (`checks: write`) would work equally well, since it can carry any
  name. The status is chosen because it is simpler: one API call, no check-suite
  semantics.
- **Source pinning:** the ruleset's required check names `merge-gate` with the
  GitHub Actions app as its expected source. A status from another integration
  or a personal token then does not satisfy it.
- **One poster, by convention:** a lint check (Phase 4) asserts that only
  `ci.yml` declares `statuses: write`, and only on the full lane's final job.
  This catches accidents, not an adversary. A same-repo PR runs its *own*
  version of the workflows, so it can edit `ci.yml` or the lint and post
  `merge-gate` itself. That is the same trust model as today's required `gate`
  job, which a PR can also edit, so the design is no weaker. But the barrier
  against a tampered workflow is human review of workflow changes, not the
  status mechanism.
- **Override is the ruleset bypass, not a hand-posted status.** Source
  pinning means a status posted by hand does not satisfy the requirement,
  whether it comes from a personal token or the `gh` CLI's OAuth app. The only
  way to merge without a full run is therefore the ruleset's bypass list (the
  repository admin). It leaves its own audit trail, separate from statuses. The
  Phase 4 runbook in `sdd/CI-OPERATIONS.md` documents that bypass, and only
  that bypass, for unblocking a merge while CI is down.

**Status lifecycle.** The status is posted by the full lane's final job. That
job depends on every other full-lane job and runs after they finish
(`if: ${{ !cancelled() }}`). It uses today's `gate` rule (`ci.yml` `gate` job):

- **`success`** when `setup` succeeded and every other full-lane job ended
  `success` or `skipped`. The class filter skips jobs routinely, for example
  `docs` when `docs=false` or every `code` job on a non-code diff.
- **`failure`** otherwise.
- **Nothing** when the run is cancelled.

Each row below is a Phase 4 exit check:

| Event | Expected result |
| --- | --- |
| Full run passes | `merge-gate: success` on the head SHA |
| Full run fails | `merge-gate: failure` on the head SHA; it replaces an earlier success there, which is conservative |
| Full run cancelled | Nothing posted. Only an earlier full run that passed on the same SHA leaves a success there |
| Push while a full run is active | That run is cancelled and the label cleared. The new head has no status, so merge is blocked |
| `merge-candidate` added twice, or removed and re-added | The concurrency group cancels the earlier run; at most one full run completes per head |
| Unrelated label added | Separate concurrency group: no cancellation, no status |
| Full workflow re-run | Posts on the same head SHA (the event payload is replayed); the latest status per context wins |
| A run finishes after a newer push | It posts on its own, older head SHA; the new head is unaffected |
| Re-run of a superseded fast run while a full run is active | The re-run enters the per-PR concurrency group and cancels the full run. This is the one residual gap, because concurrency is evaluated before any job can check staleness. Its `setup` sees payload head ≠ live head, keeps the label and ends with no lane. Merge stays blocked (fail safe). Recovery, in the runbook: remove and re-add `merge-candidate`, and re-run only the current head's runs |
| Fork PR push | Fast lane runs; label clearing and status posting are skipped; no repository mutation is attempted |

### D3. Lane mechanics in `ci.yml`

**`setup` decides the lane from the event, and clearing the label on push makes
"add the label" the single action that requests a full run.**

- **Triggers:** `pull_request` with `types: [opened, synchronize, reopened,
  labeled]`. A `labeled` event for any other label runs nothing beyond `setup`,
  and must not cancel anything (next bullet).
- **Clearing:** on `synchronize`, `setup` removes `merge-candidate` if set
  (`pull-requests: write`), but only when the payload's
  `github.event.pull_request.head.sha` equals the PR's current head, read live
  through the API. A re-run of a superseded run replays an old payload, so it
  must not clear a label that belongs to a newer head. Such a stale run ends in
  `setup` with no lane. Events caused by `GITHUB_TOKEN` start no workflow,
  so this cannot loop. The step is skipped when the head repository is not
  this one (`github.event.pull_request.head.repo.full_name !=
  github.repository`). A fork's read-only token would otherwise fail `setup`,
  and with it `gate-fast`.
- **Concurrency:** the per-PR group with `cancel-in-progress`
  (`ci.yml` `concurrency`) stays for pushes and `merge-candidate`: adding the
  label cancels a fast run on the same head, and a push cancels a full run and
  clears the label. A `labeled` event for **any other label** gets a group of
  its own, so it cannot cancel a running full lane: the group expression
  appends `github.run_id` when `github.event.action == 'labeled'` and
  `github.event.label.name != 'merge-candidate'`. Without it, a bot or manual
  label would cancel the full run while `merge-candidate` stays set, and
  nothing would re-trigger it. Concurrency is workflow-level and evaluated
  before any job, so a job-level `if:` cannot prevent this.
- **Master push:** always the full lane, as today.
- **Who sets the label:** the maintainer, by hand. A skill change that has
  `/ship` set it at its close is outside this RFC (§ Open Questions 4); the
  fast-lane saving on round pushes does not depend on it.

### D4. Two axes: the class filter picks jobs, the selector picks tests

**The existing class filter keeps deciding which jobs exist; the selector only
refines what runs inside `code` jobs and never turns on a job the filter turned
off.**

- **Lanes collapse without code.** When `code=false` (docs, formal, TLA or
  hooks only), both lanes would run the same jobs, so `setup` classifies that
  run as the **full lane**, whatever the event. The lane is therefore full on
  any of four conditions:
    - a `merge-candidate` label event;
    - a master push;
    - `code=false` on an event that starts a lane (`opened`, `synchronize`,
      `reopened`);
    - a selection that is FULL (D5).

    A FULL selection runs every job anyway, so it is the full lane and needs no
    label. That is also what keeps `dependabot-auto-merge.yml` working: a pip
    bump touches `pyproject.toml`, which is a FULL row. A `labeled` event for any
    other label starts no lane, even with `code=false` (D3). The same final job
    posts `merge-gate` in every case. D2's "the
    fast lane never posts" and the single-poster lint hold as written, and a docs
    PR needs no label.
- **The non-code classification fails toward code.** Because a non-code run
  posts `merge-gate`, a misclassification is a merge-barrier defect, not a
  slowdown.
    - **The property the barrier needs:** every tracked file a test reads or
      imports classifies into a class whose jobs run that test. "Classify as
      code" is too broad. It would undo deliberate carve-outs whose own jobs run
      the reading tests: `.claude/hooks/` and the RFC-0015 scripts are
      `HOOKS_PAT` (run by `tooling-tests`, `ci.yml` comment above `HOOKS_PAT`),
      and `sdd/formal/MemoryBackend-py/`, which `tests/backends/dafny/_helpers.py`
      imports, is `FORMAL_PAT` (run by `verify-formal`).
    - An error in the classifier itself selects the code class and the full
      lane.
    - The class outputs are recorded in the same structured output as the
      selection (D7).
    - **A known violator exists today.** `CODE_PAT` names
      `docs-src/reference/FEATURES.md`, which does not exist (`git ls-files`).
      The real generated file is the root `FEATURES.md`: it matches neither
      `CODE_PAT` nor `DOCS_PAT`, and `tests/scripts/test_gen_features.py` reads
      it. A `FEATURES.md`-only diff therefore classifies as non-code. Today that
      means nothing runs and `gate` passes. Under this RFC it would post
      `merge-gate`. The fix is tracked as BUG-302, outside this RFC, and must
      land before Phase 4.
    - **Phase 0 audits every class pattern:** each literal path in `CODE_PAT`,
      `DOCS_PAT`, `FORMAL_PAT`, `TLA_PAT` and `HOOKS_PAT` must match a tracked
      file, and every tracked file a test reads must meet the property above.
      The audit is expected to find more than BUG-302. `tests/scripts/` tests read
      `sdd/` files that are `DOCS_PAT` only, and `tooling-tests` runs only for
      `code` or `hooks`, so those tests do not run on a docs-only PR today. Each
      such case is listed. It is then either moved to a class whose jobs run the
      test, or recorded as accepted because a `docs-gate` check covers the same
      claim.
    - **Phase 4's classifier migration carries this as a test.** The history
      replay must show identical class outputs, with one exception: a
      non-code → code change is allowed when it is a listed correction, such as
      the `FEATURES.md` fix. A code → non-code change always blocks the
      migration.
- **Locally the same split.** The `/pr` mechanical gate already composes
  `all` for code diffs and `lint` + `docs-gate` otherwise
  ([PR validation gates](../CLAUDE-REFERENCE.md#pr-validation-gates)); the
  fast target replaces only the code branch.
- **One classifier, later.** The class patterns move from `ci.yml`'s bash into
  the selector in Phase 4, once the selector is proven, so path classification
  has one home (§ Roadmap).

### D5. The selector: four layers, fail open

**Input is the diff from the merge base to HEAD (plus the working tree
locally); output is either `FULL` with a reason, or pytest arguments and
per-job flags with the rule behind each.** It is static: no test run, no
installed environment, no cached state, so one result serves every interpreter
leg. It is computed once in `setup`.

**Maturity: a narrow pilot first, then precision layer by layer.** The layers
below are the target. The first production increment (Phase 1) uses only the
high-confidence part. The rest is added one layer at a time in Phase 2, each
gated by seeds and the D7 cross-check. A layer that does not pay for its
maintenance is not added.

| Level | Rules | Everything else |
| --- | --- | --- |
| **Pilot** (Phase 1) | **Every layer-1 row, plus layer 4's mapped readers**, with layers 2 and 3 absent. A row whose selection uses only layer 1 applies as written; this covers the test-file, cassette, non-root `conftest.py` without session-wide hooks, `examples/**`, `scripts/<x>.py` and generated-artifact rows. A path the reader inventory lists also selects its readers: `test_check_traces.py` for a `scripts/` edit, `test_registry.py` and `test_large_payload_guard.py` for a conformance edit. The one exception is a **leaf backend module** → its backends' fixture allowlist and `tests/backends/<backend>/` | FULL in four cases. (1) A row whose selection defers to layer 2 or 3: the `src/` rows other than a leaf backend, the `run_examples.py`/`run_notebooks.py` row, and the three fixture-registry rows (`_cassettes*.py`, fixture modules, `fixtures.toml`), whose consumers reach beyond conformance. (2) Any module under `tests/` or `scripts/` that a module **other than its own mapped test** imports by name or by literal string. A script loaded by its own `tests/scripts/test_<x>.py`, through `sys.path` or `spec_from_file_location`, does not count. (3) A script whose mapped test does not exist. (4) Anything unmatched |
| **Precision** (Phase 2, one at a time) | Layer 2 with hub resolution and the import-time scan, including registry-consumer edges; layer 3 through transitive helper edges; notebook import parsing for D6 | — |

**A leaf backend module** is a backend source in `backends.toml` that meets
two conditions:

- **No other `src/` module imports it,** at any level, including function-local
  imports.
- **Every test file that imports it lies under `tests/backends/<backend>/`**
  for one of the backends that list it.

Both are checked statically when the selection is made, and a module that
fails either one runs FULL in the pilot. Neither condition is cosmetic:

- **The first** matters because `backends.toml` names a module under one
  backend while other backends use it too. `_s3_base.py` is listed under `s3`
  only, but `_s3_pyarrow` and `_s3_boto3` import it.
- **The second** matters because backend modules are imported directly well
  outside their own folders, for example in `tests/test_store.py`,
  `tests/ext/`, `tests/scripts/test_gen_features.py`, `tests/aio/` and
  `tests/e2e/` (a Grep for `remote_store.backends._` over `tests/`), and by
  string from parametrize lists (layer 2).

**No module qualifies today, so the pilot narrows no `src/` edit.**
`_registry.py:31-87` imports every registered backend module inside a function,
and function-local imports count. Sibling modules import the remaining backend
helpers. `_s3_boto3.py`, which nothing in `src/` imports, has its tests under
`tests/backends/s3/` and in conformance. The pilot narrows only edits to test
files, cassettes, non-root `conftest.py` files, examples, scripts and generated
artifacts. The fixture-registry rows run FULL in the pilot too, because the
registry is consumed outside conformance (per-backend conftests, `tests/scripts/`
registry guards), and only layer 2 can name those consumers. Narrowing `src/` edits arrives with
layer 2 in Phase 2, which is why Phase 0 measures both rule sets (§ Roadmap).
The leaf rule stays in the pilot so that a future leaf module narrows without a
spec change.

**The pilot is only as safe as the text-reader inventory, which is why layer
4 belongs in the pilot.** No rule helps with a reader the inventory has missed,
whether that rule selects the reader or sends the path to FULL. Research
Appendix D records that the inventory is incomplete for readers of `tests/` and
`scripts/` files. Completing it is therefore a Phase 0 exit criterion. Once it
is complete, selecting the mapped readers is exactly as safe as FULL. A blanket
"read as text → FULL" rule would add no safety, and it would stop every
`scripts/` edit narrowing, because `test_check_traces.py` reads the whole
`scripts/` tree, and every conformance edit too, because `test_registry.py`
reads all of `conformance/`.

**Composition.** Layer 1 classifies each changed path; layers 2–4 then expand
the result and are always unioned, never skipped:

- If any changed path classifies as FULL, the result is FULL.
- Otherwise each path contributes its layer-1 selection, and every changed
  path, whatever its row, also contributes its layer-4 readers.
- A `src/**` path contributes its layer-2 dependents. A module that a backend
  source reaches also contributes its layer-3 fixture allowlist. Allowlists
  from several paths are unioned, and conformance from any path without an
  allowlist (a conformance test edit, say) runs unrestricted.
- The union is checked against the cut-off below.

1. **Path classes**, first matching row per path. A committed table in the
   style of `scripts/drift_smoke_map.py`'s `SMOKE_TARGETS`:

    | Path class | Layer-1 selection |
    | --- | --- |
    | `tests/conftest.py`, `tests/_helpers.py`, `pyproject.toml`, `.python-version`, `.test_durations_pass1`, `.github/**`, `scripts/run_tests.py` | FULL |
    | Any package `__init__.py` under `src/` (re-export hubs, layer 2) | FULL |
    | Core modules: those every backend passes through, and those with import-time effects beyond definitions (layer 2). The list is part of the table and Phase 0 derives it | FULL |
    | Shared fixture infrastructure: `tests/backends/fixtures/` `registry.py`, `_loader.py`, `_state.py`, `_live_env.py`, `_cassette_pytest.py`, `__init__.py`, and `backends.toml` | FULL |
    | Any other `conftest.py` | every test under its directory, unless it defines a session-wide hook (`pytest_configure`, `pytest_unconfigure`, `pytest_sessionstart`, `pytest_sessionfinish`, `pytest_collection_modifyitems`, or a session-scoped autouse fixture), which makes it FULL. Those hooks act on the whole session: `tests/backends/azure/conftest.py` and `tests/backends/conformance/conftest.py` share one missing-cassette guard, armed by whichever `pytest_configure` runs first. Checked by AST scan |
    | A `src/` module that is a backend source, or that a backend source reaches (layer 3) | none of its own; layers 2 and 3 |
    | Other `src/**/*.py` | none of its own; layer 2 |
    | `tests/**/test_*.py` | that file |
    | Cassettes under `tests/**/cassettes/<backend>/` | that backend's replay tests, including `tests/backends/<backend>/`, and the PII sweep |
    | `tests/backends/fixtures/_cassettes*.py` | `tests/backends/fixtures/`, the replay fixtures' conformance, `tests/backends/<backend>/` of the profile's backend (`tests/backends/azure/conftest.py` and its `aio/` twin import constants from `_cassettes_azure.py`), every other importer (layer 2), and the `test-cassette-pii` job. FULL in the pilot |
    | `tests/backends/fixtures/<module>.py` that registers fixtures | conformance limited to **every** fixture id the module registers, and `tests/backends/fixtures/`. The module → ids map is the inverse of `_MODULE_FOR` in `tests/backends/fixtures/__init__.py`, read as a literal dict, with each unmapped `fixtures.toml` key mapping to itself. So `s3_moto.py` selects `s3_moto` and `s3_moto_strict`, and `memory_async.py` selects both `memory_async_*` ids. Editing that map is FULL, because `__init__.py` is a FULL row. The selection also includes every **registry consumer** outside conformance (layer 2):
    - `tests/backends/<backend>/` for each backend whose fixtures change. For example, `tests/backends/azure/conftest.py` parametrizes HNS tests with records from `all_fixtures()`.
    - Tests that call `all_fixtures()`, `fixture_params()` or `fixtures()`, or import `tests.backends.fixtures`. For example, `tests/scripts/test_mutate_scopes.py` and `test_record_cassettes.py` assert over every registered fixture.

    FULL in the pilot |
    | `fixtures.toml` | conformance limited to the fixture ids whose block changed (both versions parsed), `tests/backends/fixtures/`, and the same registry consumers as the fixture-module row; FULL if it does not parse. FULL in the pilot |
    | `examples/notebooks/**` | no tests; the `notebooks` job |
    | Other `examples/**` | the `examples` job, plus the tests that import or read examples directly: `tests/test_examples.py` and `tests/test_snippets.py` (both `from examples.…`), and `tests/backends/conformance/test_examples.py` (opens an example by path). The `examples` job runs only `run_examples.py`, not these tests |
    | `tests/scripts/run_examples.py`, `tests/scripts/run_notebooks.py` | the `examples` or `notebooks` job, plus layers 2 and 4 for tests that import or read them |
    | `scripts/<x>.py` | `tests/scripts/test_<x>.py`, with leading underscores of `<x>` dropped (`_dafny_classorder.py` → `test_dafny_classorder.py`); FULL if no such test exists. An empty mapping is never an empty selection |
    | Generated artifacts (`FEATURES.md`, graph data) | their generator and check tests |
    | Anything unmatched | FULL |

2. **Static import graph.** An `ast`-built reverse graph from each `src/`
   module to the test files that depend on it. Its edge rule:
    - **Every import counts**: module-level, function-local (most `_flat_ns`
      uses are lazy, e.g. `_s3_base.py`, `_azure.py`, `_sftp.py`) and inside
      `TYPE_CHECKING`, which over-selects slightly rather than miss.
    - **`src/` → `src/` edges are followed transitively**, and so are edges
      through `tests/` helper modules.
    - **The graph covers `tests/` and `scripts/` modules as nodes, not only
      `src/`.** A test module imported by another test (for example,
      `test_async_extended.py` imports from `test_atomic.py`) selects its
      importers. Scripts import each other by bare name after a `sys.path`
      insert (`from gen_features import …`, `from _trace_corpus import …`), so a
      bare import that matches `scripts/<name>.py` is an edge.
    - **String-named imports count.** Tests import modules by name:
      `importlib.import_module`, `__import__` and `pytest.importorskip`, often
      from a parametrize list (`tests/test_capabilities.py`,
      `tests/backends/conformance/test_health_probe_declared.py`, the
      `tests/backends/s3/` helpers). Every string literal in a test file that
      names an existing module (`remote_store.…` or `tests.…`) is an edge. A
      dynamic import whose target is not a literal puts the file in an
      always-run set for every code change. D7's cross-check cannot see these
      edges: those tests touch only class-body lines, which are import-phase. So
      this rule is held by seeds, not by the oracle.
    - **Package `__init__.py` files are re-export hubs, not dependencies.**
      `remote_store/__init__.py` imports `_store`, `_path`, `_config`,
      `_registry`, `_proxy` and every `ext.*` module, so treating it as a node
      would make every module reach every test. Instead, an import of a name
      from a hub resolves to the module that defines that name, using the hub's
      own import statements. `import remote_store` followed by
      `remote_store.<name>` resolves the same way.
    - **Fail open:** an unresolvable hub import (star import, `getattr`, a bare
      module object passed around) depends on every module the hub imports.
      Editing a hub is FULL (layer 1).
    - **Import-time effects:** importing any submodule runs the package
      `__init__`, so a module's top-level code runs in every test. A module
      whose top level does more than define names (registration, patching,
      environment reads) is therefore a core module (layer 1, FULL). Phase 0
      derives that list by AST scan, and D7's cross-check ignores import-phase
      lines for the same reason.
3. **Backend axis.** It limits conformance to the fixtures of the backends a
   change can reach, using two static registry facts:
    - `backends.toml` names each backend's `sources` and `async_sources`, the
      latter covering `src/remote_store/aio/backends/`;
    - `fixtures.toml` names each fixture's `backend`.

    A changed `src/` module selects every backend whose source modules reach it
    through layer-2 edges. A shared helper such as `_flat_ns.py`, `_s3_base.py`
    or `_fileinfo.py` therefore selects the several backends that import it,
    not a backend named after the file. The selection is the fixture ids of
    those backends, plus `tests/backends/<backend>/`. A helper that reaches
    every backend hits the cut-off and runs FULL.

    The filter goes through the fixture registry (`fixture_params` honours an
    allowlist of fixture ids), not `-k`. `-k s3` also matches `s3_pyarrow` and
    `s3_boto3`, which `SMOKE_TARGETS` already works around.
4. **Text readers.** A generated table maps `.py` source globs to the tests
   that read them as text, for `src/`, `tests/` and `scripts/` alike. Non-Python
   inputs (cassettes, `fixtures.toml`, generated artifacts) are out of its
   scope. They are owned by their explicit layer-1 rows, and any other
   non-Python file falls to the unmatched row and runs FULL. This matches
   research § "If it is ever built" ("`.py` files as text"), and it keeps the
   pilot's "listed in the inventory → FULL" rule from overriding those rows. It is built by two
   independent methods, because each has blind spots the other covers:
    - **Runtime scan,** extending `sdd/research/bk-403-testmon-poc/srcreads.py`
      from readers of `src/` to readers of `tests/` and `scripts/` files.
      Research Appendix D records two
      blind spots in it: subprocess reads are not seen, and
      `linecache`/`inspect.getsource` attribution depends on test order. A rerun
      in the fixed default order reproduces both blind spots, so it is run in
      default order **and** under `hatch run test-isolation`'s randomised
      order, and the union is kept.
    - **Static scan:** `read_text`, `open`, `ast.parse`, `glob`/`rglob` and
      `subprocess` calls whose targets resolve to repository paths, across
      `tests/` and `scripts/`. 16 files under `tests/` call `subprocess.*`
      (Grep `subprocess\.(run|check_output|call|Popen)` over `tests/`, count
      mode), mostly in `tests/scripts/`.

    Completeness cannot be proven, so the criterion is agreement between the
    methods. A reader found by only one method is investigated and added before
    the table is accepted. The static half is regenerated by D7's freshness
    check. Examples of readers of test files: `test_large_payload_guard.py`
    parses `conformance/**/test_*.py`, and `test_registry.py` reads
    `conformance/**/*.py` (research Appendix D). A conformance test edit
    therefore also selects those readers.

**Cut-off:** a selection whose estimated cost is above a threshold runs FULL,
because above it selection saves too little to be worth the risk. Cost is
measured in estimated wall-clock time and jobs triggered, not test count: a
selection holding 40% of tests can still start nearly every expensive job.
Estimated time comes from the committed `.test_durations_pass1`; jobs come
from D6. Phase 0 sets the number from the metrics in § Roadmap.

### D6. Job selection inside `code`

**Each `code` job that runs fixed targets is a named target set: it runs in the
fast lane only when the selector reaches one of its targets, and runs whenever
a target cannot be placed.** The rules below apply only to non-FULL
selections, because a FULL result (D5) runs every job. A trigger path must
therefore be a layer-1 row that is not FULL, and a `code` path: a rule naming a
FULL path such as `pyproject.toml`, or a non-`code` path such as `packaging/`
(`DOCS_PAT` only), would never fire.

| Job | Fast-lane rule |
| --- | --- |
| `lint`, `typecheck` | always |
| `test`, `test-primary` | selected tests |
| `tooling-tests` | selected `tests/scripts/` tests |
| `test-primary-sftp` | selection holds conformance tests whose fixture allowlist (layer 3) contains `sftp_docker`, or is unrestricted |
| `test-cassette-pii` | the selection holds `TestCommittedCassettePIISweep` (for example, through `tests/backends/fixtures/test_cassettes.py` or the `tests/backends/fixtures/` directory), or a cassette or `_cassettes*.py` row matched. `test` and `test-primary` deselect the sweep, so this job is the only place it runs |
| `pyarrow-major-check` | selector reaches its test files (`ci.yml` job steps) |
| `test-cross-platform` | selection holds an `os_sensitive` test outside `tests/e2e/`, which the job ignores. The marker has two sources, and both are read statically: test files (marks and module-level `pytestmark`), and fixture modules' `marks=` in `tests/backends/fixtures/`. Today the second source is `local` and `local_async`, whose marks `fixture_params` attaches to every conformance test parametrized with them. So a selected conformance test whose fixture allowlist contains such a fixture, or is unrestricted, counts |
| `e2e` | selector reaches `tests/e2e/` |
| `examples` | an `examples/**` path outside `examples/notebooks/`, `tests/scripts/run_examples.py`, or a `src/` module an example imports |
| `notebooks` | an `examples/notebooks/**` path, `tests/scripts/run_notebooks.py`, or a `src/` module a code cell imports |
| `package` | a `src/` file added, deleted or renamed (wheel contents); `pyproject.toml` is FULL and so already runs it |
| `coverage-gate` | full lane only |
| `prepare-images` | a job that needs it runs |

**Per-job survival.** Each test job applies its own filter set: paths, `-k`,
`-m`, `--ignore`, `--deselect` and `--stage`. The selector reads that set from
the job's command in `ci.yml` rather than from a copy, and it is today:
- `test` and `test-primary`: `--ignore=tests/scripts`, the PII-sweep
  `--deselect`, and `--stage=1` or `--stage=2`;
- `test-primary-sftp`: the path `tests/backends/conformance/`, `--stage=2` and
  `-k sftp_docker`;
- `test-cross-platform`: `-m os_sensitive` and `--ignore=tests/e2e`. A
  diff touching only `tests/e2e/test_async_streaming_integrity.py`, whose
  module-level `pytestmark` is `os_sensitive`, therefore leaves this job
  nothing to run, and it is skipped.

The selector therefore computes, for each job, the part of the selection that
survives that job's filters:
- **Empty part:** the job is skipped. It is never run with no path arguments,
  because pytest then falls back to `testpaths = ["tests"]` (`pyproject.toml`)
  and silently runs the full suite under a fast-lane name. It is also never run
  with arguments that collect nothing, which exits 5 and turns the job red;
  `ci.yml` records exactly that for `test-primary-sftp` (PR #971).
- **Non-empty part:** passed as explicit node arguments.
- **Sharding:** the fast lane runs these jobs unsharded, one job per
  interpreter leg instead of `--splits 2`, so a small selection cannot leave an
  empty shard.
- **Exit 5 is never read as a pass.** The survival rule is what prevents it, so
  a stage mismatch stays visible instead of being hidden.

A seed per job pins one empty-survival case.

`gate-fast` aggregates like today's `gate`: passed or skipped counts, but
`setup` must succeed, so a selector error can never pass silently.

### D7. Keeping the rules honest

**A rule table drifts, so four independent checks hold it against reality,
none of which selects anything.**

1. **Seed tests.** The PoC's 13 seeds become unit tests of the selector, plus
   seeds for text readers, the D6 job rules, string-named imports, test or
   script modules imported by other tests or scripts, a failure only a
   `*_strict` fixture reaches through a shared fixture module, an example edit
   that breaks a `test_examples.py` assertion, an edit to the PII sweep test
   itself, an edit to a conftest's session-wide hook, a `scripts/` edit that
   selects its own test plus `test_check_traces.py`, one empty-survival case per
   test job (D6, including the e2e-only
   `os_sensitive` edit), and a registry-consumer case (an `azure_replay_hns.py`
   edit that breaks a `tests/backends/azure/` test). They compute
   selections only and run in seconds. Each seed asserts two things:
    - **The selection contains the known failing test.**
    - **Its expected mode, `SELECTED` or `FULL` with its reason.** Containment
      alone passes vacuously under FULL. Under the pilot (layer-1 rows plus mapped
      readers, layers 2–3 absent), a hand mapping of research Appendix B
      puts 11 of the 13 PoC seeds in FULL:
        - both `conftest.py` seeds, `__init__.py` and `pyproject.toml`;
        - five non-leaf `src/` modules (`_path`, `_registry`, `_azure`, `_sftp`
          twice);
        - the `memory.py` fixture module and `fixtures.toml`, since the
          fixture-registry rows are FULL in the pilot.

        The other two are SELECTED: the Azure cassette and `FEATURES.md`.
        Pinning the mode makes a FULL → SELECTED change visible when a layer is
        added, and so is a regression the other way.

    Every non-FULL layer-1 row needs at least one `SELECTED` seed. The Phase 0
    report states how many seeds a narrowing rule decided, not only how many
    passed.
2. **Text-reader freshness.** A check regenerates the static half of the layer-4
   table (D5) and diffs it against the committed copy. A new test that reads
   a file as text then fails in its own PR, instead of turning up only in the
   escape log.
3. **Coverage cross-check**, a drift check under
   [`DRIFT-RULES.md`](../DRIFT-RULES.md). A scheduled `ci-full.yml` job records
   coverage contexts for one full run; for each `src/` file the tests that
   executed it must be a subset of what the selector picks for that file. A
   test outside it is a missing rule. Runtime data checks the rules here and
   never selects, so the testmon portability limit does not apply.
4. **Escape log.** Each full run compares its failures with the fast selection
   for the same head. A failing test the fast lane skipped is an escape. Each
   escape is classified as one of:
    - selector defect;
    - stale or incomplete rule;
    - environment-only failure;
    - nondeterministic failure;
    - failure in a job the selector does not represent;
    - failure only the full coverage gate finds.

    Zero-escape exit criteria count only deterministic, selector-reachable
    escapes (the first two classes). The others are reported, and routed to
    their own owners.

    **A class other than the first two needs evidence**, or a judgment call
    could argue a real miss away:
    - *environment-only*: the same test fails on the base commit in the same
      job, or passes on every other leg;
    - *nondeterministic*: it passes on an unchanged rerun of the same commit;
    - *not represented*: the failing job has no D6 rule;
    - *coverage-only*: no test failed, only the floor.

    An escape without that evidence counts as a selector defect.

**Every fast run is observable.** The selector writes structured output (JSON
artifact and job summary) containing:

- the mode, `SELECTED` or `FULL`, and the FULL reason;
- the changed paths and the class outputs (D4);
- the selected tests and jobs, with the rule behind each;
- the estimated share and, after the run, the actual one;
- the rule-table revision.

Phase 2 and Phase 3 report the fallback rate from this output. A rising rate
is how a fail-open selector that has stopped saving anything gets noticed.

**Ownership and maintenance.** The rule table is code:

- A change to it is reviewed like production code and ships with a seed for
  the path class it adds or changes.
- **New backend or fixture:** a selector unit test asserts that every
  `backends.toml` backend and every `fixtures.toml` id is mapped. It also
  asserts that every file under `tests/backends/fixtures/` either matches a row
  **other than the unmatched catch-all**, or appears in an explicit list of
  deliberately FULL files (the shared-infrastructure row). A new file such as
  `_cassettes_s3.py` that does neither fails the test in the PR that adds it,
  instead of quietly giving up narrowing.
- **No project imports:** the selector uses only the standard library (`ast`,
  `tomllib`) and never imports project modules. Its output is the same on
  every interpreter, and it runs on the primary interpreter in `setup`. Its own
  tests run on the full matrix, so a stdlib difference between versions shows
  up.
- **Parse failure:** a changed file the selector cannot parse runs FULL, with
  that reason recorded.

### D8. Invariants

**Five properties hold in every phase; a change that breaks one is out of scope
for this RFC.**

1. Nothing merges without a successful full run on the final head (D2), the
   ruleset's admin bypass and a tampered workflow being the two stated limits.
2. A selected run never asserts the coverage floor.
3. Fail open: an unplaceable path, a selector error, or a selection over the
   cut-off runs FULL, and the run log says why.
4. Every selected test can be traced to the rule that picked it (`--explain`).
5. A selection depends only on the diff and committed files.

## Roadmap

**Five phases, each with an exit criterion fixed before it starts; Phase 0 can
stop the whole effort.** Nothing that blocks a merge changes before Phase 3's
exit: no branch protection, no `merge-candidate` handling, no lane that
decides. Nothing in Phases 0–2 runs in the PR workflow. Phase 2 adds one
scheduled, non-blocking `ci-full.yml` job, the D7 coverage cross-check, and
Phase 3 adds PR-workflow jobs that only log.

**What Phase 0 measures, per historical PR diff and per seed:**
- selected test count and share;
- estimated wall-clock share (from `.test_durations_pass1`);
- CI jobs triggered (D6);
- the FULL-fallback rate, with its reasons;
- false negatives: seeds and historical failures not selected;
- over-selection: selected tests outside the minimal set a coverage-context
  run would give for the same diff, computed once locally, since D7's
  scheduled job does not exist yet;
- rule-table size, as a maintenance proxy.

The targets for these are written into the Phase 0 plan before the run.

| Phase | Goal | Deliverables | Exit |
| --- | --- | --- | --- |
| **0. Validate** | Decide whether to build, from evidence | Throwaway selector under `sdd/research/` with the pilot rule set, and the precision layers prototyped beside it; extended text-reader inventory; seed run through the PoC driver; replay of historical PR diffs and of past red CI runs, including auxiliary jobs; the metrics above for both rule sets; the core-module list derived (every-backend modules plus modules with import-time effects) | The text-reader table passes D5 layer 4's two-method agreement (runtime union across default and randomised order, plus the static scan including subprocess targets); 0 seed misses, every seed's pinned mode met, and 0 deterministic, selector-reachable historical misses; the saving meets its predefined target. **Stop is judged on the precision rule set**, the target design, if typical diffs still fall back to FULL or select close to the full suite under it. The pilot narrows no `src/` edit by construction (D5), so its fallback rate is reported, not used to stop |
| **1. Pilot** | Production selector with the pilot rule set, local only | ADR for the local part; selector (stdlib only) with the pilot rows, fixture allowlist, per-job flags and structured output; registry allowlist; seed and mapping-completeness unit tests; local fast target. BK-404 stays open until its skill edits land (Open Questions 4) | Seeds and the mapping test green in CI; the fallback rate recorded from the first real rounds |
| **2. Shape** | Use the pilot, then add precision | Fast target used for real rounds; escape log against the later full result, classified; the D7 coverage cross-check as a scheduled `ci-full.yml` job; then layer 2 (hubs, import-time scan, registry consumers), transitive layer 3 and notebook parsing, each added only after the cross-check job is in place and reports no gap | A pilot length fixed beforehand with 0 deterministic, selector-reachable escapes; each precision layer kept only if it lowers the measured share without a cross-check gap; cut-off set by measurement |
| **3. CI shadow** | Validate the CI lane without risk | Fast lane computes and logs its selection while the full lane still runs on every push; escapes compared and classified automatically; fallback rate reported | A shadow period fixed beforehand with 0 deterministic, selector-reachable escapes; time saved and fallback rate measured |
| **4. Finalize** | Switch it on and make it maintainable | ADR amending ADR-0043; `ci.yml` triggers, label clearing, `gate-fast`, `merge-gate` status; the single-poster lint check; branch protection moved to `merge-gate` with the Actions app as expected source; classifier migration with a history replay proving identical class outputs; runbook in `sdd/CI-OPERATIONS.md`; BK-403 closed. ID-266 stays open until its skill edits land (Open Questions 4) | Every row of D2's status-lifecycle table verified on a real PR |

The selection-free speedups (BUG-301, BK-401, BK-400) are a separate track.
They make the full lane cheaper, which every PR still passes at least once.

## Alternatives Considered

**Every rejected option either selects with a mechanism this repo defeats, or
switches lanes on a signal that misses the review loop.**

- **Runtime coverage map (`pytest-testmon`).** Measured and rejected for
  selection (§ Management Summary). Kept as a drift oracle in D7.
- **`pytest-tia`, `pytest-impact`.** Not run. Both are runtime or diff tools
  with one or two releases (audit-022 § H1 PyPI table) and share the blind
  spots D5 layer 1 exists for. Phase 0 can run them through the same driver if
  the rule-based selector misses its exit.
- **Build or package graph (Pants, Bazel).** One library package means one node
  to invalidate (audit-022 § Not proposed).
- **Draft state as the switch.** Rejected: review rounds happen on open PRs
  (Motivation, lesson 2).
- **Full lane on approval.** Approvals here come from bots and one maintainer,
  and a push after approval needs a new approval to reach full.
- **Required `gate` job instead of a status.** Rejected: a skipped required job
  passes protection (D2).
- **Primary interpreter only in the fast lane.** Rejected: loses the
  interpreter-specific reds `/ship` relies on (Motivation, lesson 3).

## Impact

**No public API, runtime behaviour or user documentation changes; the impact is
on CI configuration, contributor tooling and two process records.**

- **Public API / backwards compatibility:** none.
- **CI:** `ci.yml` triggers, `setup`, per-job conditions, a new status. Two
  changes outside the repo: branch protection moves to `merge-gate`, and the
  `merge-candidate` label has to exist.
- **Auto-merge:** `.github/workflows/dependabot-auto-merge.yml` arms
  `gh pr merge --auto`, which waits for the required check. It keeps working
  only because a FULL selection is the full lane (D4). Phase 4 verifies this on
  a Dependabot PR, and the runbook update covers the Dependabot checklist in
  `sdd/CI-OPERATIONS.md`.
- **Tooling:** a selector script, a local hatch target, a registry allowlist in
  `tests/backends/fixtures/registry.py`.
- **Process:** an ADR for the local part (Phase 1) and one amending ADR-0043
  (Phase 4); `sdd/CI-OPERATIONS.md` runbook; a second departure from
  [audit-017](../audits/audit-017-dev-process-gate-topology.md) R3's "one thin
  target", after BK-271's, argued in the Phase 1 ADR.
- **Ripples to carry when built:** the ripple-check row "Test whose subject is
  outside `src/` or `scripts/`" gains the selector's rule table as a second
  place to update; a new path class needs a selector rule as well as a
  `CODE_PAT` entry until Phase 4 merges the two.

## Open Questions

1. **Primary leg tier in the fast lane.** Stage 2 keeps ADR-0043's per-PR
   live-backend guarantee; Stage 1 is cheaper but leaves `_s3.py` and
   `_sftp.py` rounds on moto and in-process SFTP until the full run.
2. **Cut-off threshold and core-module list.** *Answered by Phase 0
   (2026-10-04): no cut-off was set, because the D5 selector stopped first.* The derived
   core-module list has 6 entries: `_capabilities.py`, `_errors.py`,
   `_models.py`, `_path.py` and `_resolution.py`, which every backend reaches,
   and `_info.py`, by import-time effect
   ([report](../research/bk-403-phase-0/report.md), Appendix F).
   A cut-off would have mattered little: the stop came from the FULL rate,
   before any selection reached a threshold.
3. **Name of the local target.**
4. **Skill integration.** This covers three changes:
    - `/ship` and `/fix-pr` running the fast target before round pushes;
    - `/ship` setting `merge-candidate` at its close;
    - `/pr` running the fast target instead of `all` before opening a PR.

    These are out of this RFC's scope by the maintainer's choice, but not
    without an owner. The BK-404 and ID-266 dossiers keep them in scope, so both
    items stay open until the edits land. Until then, the label is set by hand,
    and D1's local fast target is used by hand.
5. **Late failures.** The full run now comes at the close, so a failure the
   selector did not reach shows one round later than today. The escape log
   measures how often.
6. **`verify-tla` stays informational, and that is settled, not open.** The
   `ci.yml` comment above `verify-tla` says it is "Not in the gate below by
   design", citing `sdd/formal/README.md` § Authoring rules (3). A TLA-only
   diff therefore collapses to the full lane (D4) and posts `merge-gate`
   whatever TLC reports. This is listed only so that the revisit tracked by
   ID-150 also reconsiders the poster's job set.
7. **Long-term full-lane trigger.** The label is the pilot mechanism (D1).
   Two alternatives are worth weighing: a merge queue, if the account gains
   one, and an explicit `workflow_dispatch` or comment command. Revisit at the
   Phase 4 ADR.

**Decided while drafting** (maintainer, 2026-10-03): rules plus static graph
over a coverage map; the merge-candidate signal over draft state or approval;
auxiliary jobs get their own path rules rather than always or never running;
the class patterns move into the selector in Phase 4, not Phase 1; running
`hatch run all` before marking a merge candidate is recommended, not required.
From the maintainer's overall review: approval is sought for Phase 0 and a
limited local pilot only. The pilot uses high-confidence rules, and precision
layers are added one at a time.

## References

- [audit-022](../audits/audit-022-gate-speed-strategies.md): findings H1, M1, L1–L3, proposals P1–P7.
- [research-bk-403-testmon-poc.md](../research/research-bk-403-testmon-poc.md): seeds, portability, text readers.
- Dossiers: [BK-403](../backlog/bk-403-test-selector-evaluation.md),
  [BK-404](../backlog/bk-404-selected-tests-hatch-target.md),
  [ID-266](../backlog/id-266-two-speed-ci-gate.md).
- [ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md): tiered CI gate.
- [`DRIFT-RULES.md`](../DRIFT-RULES.md): rules for D7's cross-check.
