# RFC-0019: Two-speed test gate with a rule-based selector

## Status

Draft, 2026-10-03. Tracked as **BK-403**; it also sets the design for BK-404
(local target) and ID-266 (CI lane). Nothing below is built.

**Decision sought: approve Phase 0 and a limited local pilot.** The target
architecture below is the direction, not a build order. Branch protection,
`merge-candidate` handling and every blocking CI change wait until Phase 3's
exit (§ Roadmap). Phase 0 decides whether anything is built at all.

## Management Summary

**The full gate is removed from intermediate iteration pushes, but stays
mandatory for the exact head that is meant to merge.** Those pushes run only
the tests a change can reach. Today both gates run everything on every push. The selector that picks the tests is a committed
rule set, not a runtime coverage map, and it runs the full suite whenever it
cannot place a change.

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
  (audit-022 § M1, `list_workflow_runs` on its head branch). Most pushes in a
  `/ship` loop are review rounds on an open PR, so a trigger based on draft
  state would not reach them.

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
| CI fast | `opened`, `synchronize`, `reopened` | lint, typecheck, selected tests on every interpreter | — |
| CI full | `merge-candidate` label added | today's `ci.yml` | yes |
| Post-merge | master push | `ci.yml` full, `ci-full.yml` | yes |

The local fast target is the gate for every round push. `hatch run all` keeps
its meaning as the full local check; running it before marking a merge
candidate catches a red full run locally instead of in CI, but the CI full lane
is the enforced barrier.

### D2. The merge barrier is a commit status only the full lane posts

**Branch protection requires a status that a successful full run posts on the
PR's head commit; no other path can produce it.** A required *job* is not
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
- **Maintainer override:** someone with write access can still post the
  status by hand. That is an explicit, audited override, the same class as an
  admin bypass of branch protection, and is not a path the design relies on.

**Status lifecycle.** The status is posted by the full lane's final job. That
job depends on every other full-lane job and runs after they finish
(`if: ${{ !cancelled() }}`). It posts `success` only when all of them passed,
`failure` otherwise, and nothing when the run is cancelled. Each row below is a
Phase 4 exit check:

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
| Fork PR push | Fast lane runs; label clearing and status posting are skipped; no repository mutation is attempted |

### D3. Lane mechanics in `ci.yml`

**`setup` decides the lane from the event, and clearing the label on push makes
"add the label" the single action that requests a full run.**

- **Triggers:** `pull_request` with `types: [opened, synchronize, reopened,
  labeled]`. A `labeled` event for any other label runs nothing beyond `setup`,
  and must not cancel anything (next bullet).
- **Clearing:** on `synchronize`, `setup` removes `merge-candidate` if set
  (`pull-requests: write`). Events caused by `GITHUB_TOKEN` start no workflow,
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
  hooks only), both lanes run the same jobs. That run counts as full and posts
  `merge-gate` directly, so a docs PR needs no label.
- **The non-code classification fails toward code.** Because a non-code run
  posts `merge-gate`, a misclassification is a merge-barrier defect, not a
  slowdown.
  - No source, test, configuration, dependency, generated or workflow path may
    classify as non-code.
  - An error in the classifier itself selects the code class and the full
    lane.
  - The class outputs are recorded in the same structured output as the
    selection (D7).
  - Phase 4's classifier migration carries this as a test: the history replay
    must show identical class outputs, and any path that changes class blocks
    the migration.
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
| **Pilot** (Phase 1) | Layer 1's FULL rows, test-file rows, cassette rows, fixture-id rows and `scripts/<x>.py` → its direct test; a **leaf backend module** → its backends' fixture allowlist and `tests/backends/<backend>/` | FULL: any other `src/` module, any backend module that is not a leaf, and any path the text-reader inventory lists as read as text |
| **Precision** (Phase 2, one at a time) | Layer 2 with hub resolution and the import-time scan; layer 3 through transitive helper edges; layer 4's mapped readers; notebook import parsing for D6 | — |

**A leaf backend module** is a backend source in `backends.toml` that meets
two conditions:

- **No other `src/` module imports it,** at any level, including function-local
  imports.
- **Every test file that imports it lies under `tests/backends/<backend>/`**
  for one of the backends that list it.

Both are checked statically when the selection is made. The second condition
is not cosmetic: backend modules are imported directly well outside their own
folders, for example in `tests/test_store.py`, `tests/ext/`,
`tests/scripts/test_gen_features.py`, `tests/aio/` and `tests/e2e/` (a Grep for
`remote_store.backends._` over `tests/`). The first condition matters because
`backends.toml` names a module under one backend while other backends use it
too: `_s3_base.py` is listed under `s3` only, but `_s3_pyarrow` and
`_s3_boto3` import it. A module that fails either condition runs FULL in the
pilot.

**The pilot is only as safe as the text-reader inventory.** Sending listed
paths to FULL does nothing for a reader the inventory has missed. Research
Appendix D records that the inventory is incomplete for readers of `tests/` and
`scripts/` files. Completing it is therefore a Phase 0 exit criterion, not a
precision layer that can be deferred.

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
   | Any other `conftest.py` | every test under its directory |
   | A `src/` module that is a backend source, or that a backend source reaches (layer 3) | none of its own; layers 2 and 3 |
   | Other `src/**/*.py` | none of its own; layer 2 |
   | `tests/**/test_*.py` | that file |
   | Cassettes under `tests/**/cassettes/<backend>/` | that backend's replay tests and the PII sweep |
   | `tests/backends/fixtures/_cassettes*.py` | `tests/backends/fixtures/`, the replay fixtures' conformance, and the `test-cassette-pii` job |
   | `tests/backends/fixtures/<id>.py`, where `<id>` is a `[fixture.<id>]` key in `fixtures.toml` | conformance limited to fixture `<id>`, and `tests/backends/fixtures/` |
   | `fixtures.toml` | conformance limited to the fixture ids whose block changed (both versions parsed), and `tests/backends/fixtures/`; FULL if it does not parse |
   | `examples/notebooks/**` | no tests; the `notebooks` job |
   | Other `examples/**` | no tests; the `examples` job |
   | `tests/scripts/run_examples.py`, `tests/scripts/run_notebooks.py` | the `examples` or `notebooks` job, plus layers 2 and 4 for tests that import or read them |
   | `scripts/<x>.py` | `tests/scripts/test_<x>.py` |
   | Generated artifacts (`FEATURES.md`, graph data) | their generator and check tests |
   | Anything unmatched | FULL |

2. **Static import graph.** An `ast`-built reverse graph from each `src/`
   module to the test files that depend on it. Its edge rule:
   - **Every import counts**: module-level, function-local (most `_flat_ns`
     uses are lazy, e.g. `_s3_base.py`, `_azure.py`, `_sftp.py`) and inside
     `TYPE_CHECKING`, which over-selects slightly rather than miss.
   - **`src/` → `src/` edges are followed transitively**, and so are edges
     through `tests/` helper modules.
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
4. **Text readers.** A generated table maps source globs to the tests that read
   them as text, for `src/`, `tests/` and `scripts/` alike. It extends
   `sdd/research/bk-403-testmon-poc/srcreads.py`, which covered `src/` only, to readers of
   `tests/` and `scripts/` files. Examples: `test_large_payload_guard.py`
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
| `test-cassette-pii` | a cassette or `_cassettes*.py` row in layer 1 |
| `pyarrow-major-check` | selector reaches its test files (`ci.yml` job steps) |
| `test-cross-platform` | selection holds an `os_sensitive` test. The marker has two sources, and both are read statically: test files (marks and module-level `pytestmark`), and fixture modules' `marks=` in `tests/backends/fixtures/`. Today the second source is `local` and `local_async`, whose marks `fixture_params` attaches to every conformance test parametrized with them. So a selected conformance test whose fixture allowlist contains such a fixture, or is unrestricted, counts |
| `e2e` | selector reaches `tests/e2e/` |
| `examples` | an `examples/**` path outside `examples/notebooks/`, `tests/scripts/run_examples.py`, or a `src/` module an example imports |
| `notebooks` | an `examples/notebooks/**` path, `tests/scripts/run_notebooks.py`, or a `src/` module a code cell imports |
| `package` | a `src/` file added, deleted or renamed (wheel contents); `pyproject.toml` is FULL and so already runs it |
| `coverage-gate` | full lane only |
| `prepare-images` | a job that needs it runs |

`gate-fast` aggregates like today's `gate`: passed or skipped counts, but
`setup` must succeed, so a selector error can never pass silently.

### D7. Keeping the rules honest

**A rule table drifts, so three independent checks hold it against reality,
none of which selects anything.**

1. **Seed tests.** The PoC's 13 seeds, plus seeds for text readers and the D6
   job rules, become unit tests of the selector. Each asserts that the
   selection *contains* the known failing test. They compute selections only
   and run in seconds.
2. **Coverage cross-check**, a drift check under
   [`DRIFT-RULES.md`](../DRIFT-RULES.md). A scheduled `ci-full.yml` job records
   coverage contexts for one full run; for each `src/` file the tests that
   executed it must be a subset of what the selector picks for that file. A
   test outside it is a missing rule. Runtime data checks the rules here and
   never selects, so the testmon portability limit does not apply.
3. **Escape log.** Each full run compares its failures with the fast selection
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
  `backends.toml` backend and every `fixtures.toml` id is mapped, and that
  every file under `tests/backends/fixtures/` matches a layer-1 row. Adding
  one without a rule fails that test, in the PR that adds it.
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

1. Nothing merges without a successful full run on the final head (D2).
2. A selected run never asserts the coverage floor.
3. Fail open: an unplaceable path, a selector error, or a selection over the
   cut-off runs FULL, and the run log says why.
4. Every selected test can be traced to the rule that picked it (`--explain`).
5. A selection depends only on the diff and committed files.

## Roadmap

**Five phases, each with an exit criterion fixed before it starts; Phase 0 can
stop the whole effort.** Nothing that blocks a merge changes before Phase 3's
exit: no branch protection, no `merge-candidate` handling, no lane that
decides. Phases 0–2 are local only. Phase 3 adds CI jobs that only log.

**What Phase 0 measures, per historical PR diff and per seed:**
- selected test count and share;
- estimated wall-clock share (from `.test_durations_pass1`);
- CI jobs triggered (D6);
- the FULL-fallback rate, with its reasons;
- false negatives: seeds and historical failures not selected;
- over-selection: selected tests outside the D7 cross-check's minimal set for
  the same diff;
- rule-table size, as a maintenance proxy.

The targets for these are written into the Phase 0 plan before the run.

| Phase | Goal | Deliverables | Exit |
| --- | --- | --- | --- |
| **0. Validate** | Decide whether to build, from evidence | Throwaway selector under `sdd/research/` with the pilot rule set, and the precision layers prototyped beside it; extended text-reader inventory; seed run through the PoC driver; replay of historical PR diffs and of past red CI runs, including auxiliary jobs; the metrics above for both rule sets; the core-module list derived (every-backend modules plus modules with import-time effects) | The text-reader inventory is complete for `src/`, `tests/` and `scripts/` readers, re-run to the same result; 0 seed misses and 0 deterministic, selector-reachable historical misses; the pilot's estimated wall-clock saving meets its predefined target. **Stop** if typical diffs fall back to FULL or select close to the full suite |
| **1. Pilot** | Production selector with the pilot rule set, local only | ADR for the local part; selector (stdlib only) with the pilot rows, fixture allowlist, per-job flags and structured output; registry allowlist; seed and mapping-completeness unit tests; local fast target. BK-404 stays open until its skill edits land (Open Questions 4) | Seeds and the mapping test green in CI; the fallback rate recorded from the first real rounds |
| **2. Shape** | Use the pilot, then add precision | Fast target used for real rounds; escape log against the later full result, classified; then layer 2 (hubs, import-time scan), transitive layer 3, mapped layer 4 and notebook parsing, each added only after the cross-check job is in place and reports no gap | A pilot length fixed beforehand with 0 deterministic, selector-reachable escapes; each precision layer kept only if it lowers the measured share without a cross-check gap; cut-off set by measurement |
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
- **CI:** `ci.yml` triggers, `setup`, per-job conditions, a new status; branch
  protection settings (outside the repo) move to `merge-gate`.
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
2. **Cut-off threshold and core-module list.** Set from Phase 0 data, not
   chosen here.
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
6. **`verify-tla` is not in `gate`'s `needs`** (`ci.yml` `gate` job), so a red
   TLA check does not block merge today. Confirm that is intended before the
   Phase 4 ADR, since D4's lane collapse covers TLA-only diffs.
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
