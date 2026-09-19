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
- `.github/workflows/drift-guard.yml` header — refresh procedure; the three
  hard non-goals (the workflow never edits `pyproject.toml`, never auto-merges
  a floor/pin, never auto-remediates); and, in the same list, what the floor
  lane does **not** verify and why its legs are advisory — the two a triage run
  needs, because they are why a green `floor-<extra>` job says little.
- `infra/drift-locks/README.md` § Refreshing — the canonical command pair.
- `scripts/drift_check.py` module docstring — subcommand semantics.

**The core rule this skill exists to enforce:** whether a drift is *safe to
accept* is decided per-extra by that extra's **smoke verdict**, never by the
version rows alone. A red smoke means a real regression, a smoke-harness gap, or
a transient that only a re-run on the same pins can settle (step 3); never
refresh an extra whose smoke is red until you have explained why.

**The verdict is in the issue body now**, per extra and per lane, in the "Smoke
verdicts" table, with the `phase` that failed. The run carries the logs behind
it. Do not reconstruct the verdict from job conclusions: the floor lane's legs
exit 0 by design, so a green `floor-<extra>` job says nothing about what that
leg found.

**Two lanes, two questions.** The *newest* lane asks whether the versions we
resolve to still work; the *floor* lane asks whether the floors we declare do.
The floor lane runs on the oldest supported interpreter only and leaves
transitives newest, so a red floor leg is a claim about that combination, not
about the whole old world.

A green smoke means the committed pins were the ones *installed*: the smoke is
pinned to the resolution with a pip constraints file, so the extra's own
packages cannot be quietly moved. **What `-c` does not hold is the plugin
side** — pip is free to backtrack `moto`, `responses` or `vcrpy` onto older
releases that fit, and at the floor it backtracks much further. So a red smoke
is a real regression, a harness gap, or a plugin the resolver dragged backwards;
the `phase` field is what tells them apart without reading logs.

**It does not follow that the drifted package was exercised.** Pin identity and
smoke *reach* are different claims, and reach varies per extra: an `--import-only`
target in `drift_smoke_map.py` may load one dependency and none of the others, so
a green verdict can cover none of what drifted (BUG-250 — `[graph]` is the known
case). Before treating a green verdict as licence, check that the extra's smoke
target can actually load the drifted package; where it cannot, say so and name
whatever real evidence you do have.

GitHub reads via `gh` CLI; writes (PR) via the configured GitHub MCP server,
falling back to `gh` for GraphQL-only flows. Repo: `haalfi/remote-store`.
Two `gh` paths do not work from a sandboxed session, and both are policy, not
transient — switch tool, do not retry: job logs (`gh run view --log-failed`
fetches from a results host outside `api.github.com`, denied like the artifact
host in step 7; the MCP server's `get_job_logs` serves the same log through the
API) and workflow dispatch (`gh workflow run` gets 403 because the session token
lacks `actions: write`; the MCP server's `actions_run_trigger` dispatches).

## Steps

1. **Locate the issue.** If `$ARGUMENTS` is an issue number, use it. Otherwise
   find the single open rolling issue by title prefix (it carries no label):
   `gh issue list --repo haalfi/remote-store --state open --search '[drift-guard] in:title'`.
   None open → drift has cleared, nothing to do; stop and say so.

2. **Parse the body.** Extract: the drifted extras and their per-package
   `baseline → resolved` rows, the **Smoke verdicts** table, the **Floor lane**
   and **Isolated install failed** sections if present, the **Support windows**
   table, the **Conda feedstock** verdict, the **Clear** list, and the
   **Last run** URL. The body is regenerated
   every run and auto-closes on clear — never edit it.

3. **Classify each verdict (load-bearing).** Read the per-lane verdict and its
   `phase` from the body, not from job conclusions — a floor leg exits 0
   whatever it found.

   **Newest lane**, per drifted extra:
   - **pass** → smoke passed against the fresh resolution. Refreshable, if the
     target reaches the drifted package — see the reach caveat above.
   - **fail, phase `install-extra` or `import-extra`** → the extra could not
     stand up **alone**, and the phase does not say which of two reasons. Read
     the traceback:
     - **A module that is not declared anywhere** (`ModuleNotFoundError` for a
       package absent from the extra's own list) → an under-declared extra, not
       a version finding: it arrives from somewhere else in every environment
       that has ever run the suite. Propose a `pyproject.toml` declaration fix
       (ask first — never open a backlog item unilaterally); do not refresh the
       lock, which would record a resolution that does not work by itself.
     - **A declared package that fails to import against a newly resolved
       transitive** (BUG-287's shape at the top of the range: `pyarrow` against
       a `numpy` that moved) → a version finding, and one this lane exists to
       report. Treat it as a red smoke: classify below, do not refresh.
   - **fail, phase `smoke`** → do NOT refresh yet. Fetch the failed step
     (`gh run view --repo haalfi/remote-store --job <jobId> --log-failed`) and
     classify:
     - **Real regression** — a drifted dep actually broke backend/ext behaviour.
       This is a bug, not a baseline event: surface it, propose a backlog item
       (ask first), and leave the lock alone so the issue keeps flagging it.
       If the bug is pre-existing rather than caused by the bump, add a row to
       `infra/drift-locks/KNOWN-FINDINGS.md` under lane `newest` so the next run
       reports it as known; the leg stays red either way.
     - **Smoke-harness gap** — the failure is the smoke env's fault, not the
       dependency's (e.g. a test needs an extra the smoke env doesn't install,
       so it errors with `ModuleNotFoundError` regardless of the bump; or pip
       backtracked a plugin onto a release too old for the suite). Fix the
       harness (`drift_smoke_map.py` target or the composite action's
       plugin-install list), not the lock. Refresh only after it is genuinely
       green.
     - **Transient** — the failure is not attributable to what drifted: it
       lands after the phase the drifted package takes part in (a timeout at
       auth after a successful key exchange, with only `cryptography` bumped),
       and an earlier run smoked the identical pins green (check the package's
       PyPI release date against the last green run). That is an argument, not
       a verdict: re-run, and refresh only on the re-run's green conclusion.
       Re-run the **full matrix** (see the cancelled case below for why), and
       reconstruct from the re-run's body — it may carry rows the first run
       did not.
   - **fail, phase `install-plugins`** → a harness gap by construction. The
     extra installed and imported; the smoke's own plugins could not join it.
     Fix the plugin list, never the lock.

   **Floor lane.** A floor finding is never a lock event — no lock exists for
   that lane. It is a decision about a published range:
   - **`Floor installs, then breaks`, and the reason is a *warning*** → the
     smoke inherits `filterwarnings = error`, so a floor that only deprecates
     against current transitives fails its leg while a user at those versions
     sees nothing. Still a finding — a deprecation at the floor is a floor
     about to break — but it is a candidate for raising rather than a break
     today, and it is the one class where the reason text, not the phase,
     decides. Do not quieten the lane: a floor smoke weaker than the suite it
     borrows retires the signal early.
   - **`Floor installs, then breaks`** → the floor is too low. Propose raising
     it to the oldest release that works, priced by
     [`CONTRIBUTING.md` § When to bump](../../../CONTRIBUTING.md#when-to-bump)
     — a raise excluding only releases 2+ years past their own release is a
     patch, anything younger is breaking and takes the migration path. Then add
     or remove the row in `infra/drift-locks/KNOWN-FINDINGS.md` to match.
   - **`Floor does not install`** → same decision, one step earlier. Raise it,
     or record in the register why it stands.
   - **`Test plugins cannot coexist with the floor`** → a harness gap, not a
     finding about the floor. Fix the plugin list.
   - **Marked `_Known_`** → it is in the register with an owner. The review date
     is now read by code: past it the row stops silencing and the finding is
     reported as new again, with the owner still named and "review date passed"
     beside it. So a row saying that is the mechanism asking you to re-read the
     rationale, not a row to extend on sight.

   **cancelled** → inconclusive (fail-fast neighbour or concurrency). Re-run
   before trusting it, as `workflow_dispatch` with `extra=all` and `lane=all`,
   **not** the single leg: a single-extra or single-lane dispatch re-renders the
   rolling issue body from that slice and drops every other row, which is the
   reconstruction source step 7 depends on (BUG-282). Until that lands, a
   single-leg re-run is acceptable only after you have saved the current body —
   or use `dry_run: true`, which renders the body into the job summary and
   leaves the issue untouched.

   **Support windows.** Not a lane, not a refresh, and **never** something this
   skill acts on by itself. A row here is a **decision to take or re-affirm**:

   - **`N days left`** → nothing to do. The number is there so the next release
     does not meet the date by surprise.
   - **`N days past, unregistered`** → CPython has stopped shipping security
     fixes for that interpreter and nobody has decided about it, so it is
     holding the issue open. Two answers, and both are the maintainer's: **drop
     the version**, which is a breaking change moving every spelling of the
     supported set (the ripple-check's **Supported interpreter set** row
     enumerates them and
     [`CONTRIBUTING.md` § When to bump](../../../CONTRIBUTING.md#when-to-bump)
     prices it); or **keep it and register the decision**, by adding a row to
     `infra/drift-locks/PYTHON-SUPPORT.md` with an owner, a rationale and a
     `Review by`. Propose and ask; never edit `pyproject.toml` or add a register
     row unilaterally.
   - **`known, <owner>, review by <date>`** → decided already. Read the item or
     ADR the row names as its `Owner` — printed in that cell — for what was
     decided and why, before re-opening it.
     [ADR-0039](../../../sdd/adrs/0039-support-tracks-upstream-security-fixes.md)
     is where the window itself comes from and takes no position on any
     particular version, so it is not a substitute for the owner the row names.
   - **`review date passed`** → the row has stopped silencing. Re-affirm the
     decision or drop the version; extending the date without re-reading the
     rationale is what the enforcement exists to prevent.

   **Conda feedstock.** Not a lane, not a refresh, and never acted on
   unilaterally by this skill — neither the feedstock pull request a difference
   needs nor a row accepting one. The section says whether the recipe
   conda-forge publishes still matches the generated copy this repo committed at
   the tag its version names.

   **The body prints prose, not a status token.** Read the verdict from the
   first sentence: "carries exactly what this repo committed" is `match`,
   "**differs from what this repo committed**" is `drift`, "carries a change
   merged after that version was tagged" is `ahead-of-tag`, "names a version
   this repo published no generated copy for" is `no-baseline`, "**could not be
   found at the path this repo publishes to**" is `missing`, "could not be
   fetched" is `unreachable`, and "**could not be checked, and the fault is on
   this side**" is `error`.

   **A "release behind" paragraph is not one of those verdicts.** It renders
   *beside* whichever verdict applies, because trailing is an orthogonal fact
   rather than a status: a channel a release behind can still carry exactly
   what we published for the version it is on. Read the verdict sentence first
   and the trailing paragraph second — acting on the trailing sentence alone
   will tell you there is nothing to do on a run that is holding the issue
   open. Catching the channel up is the release checklist's, never this skill's.

   - **`match`, `ahead-of-tag`** → nothing to do. The second means the published
     copy carries a change merged after that tag was cut, which is what a
     release's own copy-out looks like.
   - **A drift marked _registered_** → the published body is the exact one a row
     in `infra/drift-locks/FEEDSTOCK-DIVERGENCE.md` accepts, because that
     difference is one nobody intends to revert (a conda-forge migrator, or the
     maintainer-list flow). It holds nothing open. Rows are keyed on the body's
     fingerprint, so this marking disappears the moment anything else changes on
     the far side — and a row whose `Review by` has passed stops silencing.
     Both are the mechanism asking you to re-read the rationale, not a date to
     extend on sight.
   - **`no-baseline`, `unreachable`** → this run could not compare the two. Not
     a finding, and not a clean bill either: they stop the issue closing and
     nothing else. `no-baseline` on a version tagged before this watch existed
     is expected and ends at the next copy-out.
   - **`drift`** → the channel serves something other than what we published for
     that version. **The remedy is a pull request against the feedstock**, per
     [`sdd/CONDA-FORGE.md`](../../../sdd/CONDA-FORGE.md) — copy
     `packaging/conda-forge/feedstock/recipe.yaml` across and, when the version
     is unchanged, increment `build.number` there, or the metadata-only fix does
     not reach users. Never *resolve* it by editing our recipe: our side is the
     authority, so a change here would be inventing a difference rather than
     resolving one. Registering it here is the other legitimate answer, and not
     an exception to that: a row records that the difference stands, it does not
     change what we publish. Propose and ask; this skill neither opens that PR
     nor writes that row.
   - **`missing`** → a 404 on the path we fetch, which is **two** different
     findings and the section cannot tell them apart. Either the feedstock moved
     or renamed `recipe/recipe.yaml`, which is a pull request there, or the URL
     this repo fetches is stale, which is `FEEDSTOCK_URL` in
     `scripts/drift_feedstock.py` and a fix *here*. Open the feedstock and look
     before assuming the first — "never edit this repo" is the rule for a
     `drift`, not for a watch pointed at the wrong place.
   - **`error`** → the fault is on **our** side, not conda-forge's: usually a
     tag that will not resolve. Read the run log rather than the feedstock.

   **A crossing licenses a drop; it never requires one.** Rule 8 promises a
   floor, not a ceiling, so "the window closed" is not by itself a reason to
   drop anything. And a crossing renders on every run while *forcing an update*
   only on an unnarrowed one, so a narrowed dispatch showing an unregistered
   crossing is not evidence the issue was going to be rewritten from that slice.
   It **is** evidence the issue was going to stay open: a narrowed run may not
   close over an unowned crossing either, so it answers `leave` and the next
   scheduled run decides. Read a narrowed dispatch as "real and undecided",
   never as "inert".

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
    resolves clean. When nothing was held, the user can close it promptly after
    merge by re-resolving via
    `gh workflow run drift-guard.yml --repo haalfi/remote-store` (the workflow is
    on `master`, so dispatch resolves fine). A held extra still drifts against
    its old lock, so that run re-renders the issue with the held section instead
    of closing it; the issue closes only once the hold is lifted and refreshed.

## Rules

- Per-extra gating is non-negotiable: green smoke is the licence to refresh.
- A floor finding is never refreshed away. The floor lane writes no lock, so
  there is nothing to refresh — the only answers are raise the floor, fix the
  harness, or record the decision in `infra/drift-locks/KNOWN-FINDINGS.md`.
- A finding that will recur until someone fixes it gets a row in that register,
  in **either** lane. Without one it is reported as new every Monday, and a
  reader who sees the same rows weekly stops reading them. A row changes what
  the issue presents as news; it never changes whether a leg goes red. **A row
  expires**: past its `Review by` it stops silencing, in both registers.
- A **Support windows** row is never refreshed, never registered unilaterally,
  and never acted on by this skill. It is the maintainer's decision — drop the
  interpreter, or record why it stays — and this skill's job is to present it
  with the options and the cost.
- This skill prepares the refresh (locks, docs, any harness fix) and stops at a
  pushed branch; the user opens the PR via `/pr`. It never edits
  `pyproject.toml` floors, never merges, and never closes the rolling issue by hand.
