# RFC-0019 Phase 0 plan (BK-403)
<!-- doc: repo-only -->

**The targets and stop criterion below were fixed by the maintainer on
2026-10-04, before any replay ran** (RFC-0019 § Roadmap: "The targets for these
are written into the Phase 0 plan before the run"). They are not revised after
the run; a result that misses one is reported as a miss.

Throwaway research under `sdd/research/`; nothing here is wired into `ci.yml`,
`pyproject.toml` scripts or skills (maintainer approval, 2026-10-04: Phase 0
only).

## Populations

- **H, historical PR diffs.** Every squash-merged PR commit on master's first
  parent from 2026-07-04 up to and including `d306e0223` (#1072) whose diff
  matches `ci.yml` `CODE_PAT`: 106 of 182 PRs, 41 of them touching `src/`
  (`python sdd/research/bk-403-phase-0/count_code_prs.py 2026-07-04
  d306e0223`, which runs `git log --first-parent d306e0223 --since=2026-07-04`
  and `git diff --name-only <sha>^ <sha>` per PR). The diff is the final head
  against its base, i.e. the largest cumulative diff the PR's pushes had; an
  earlier push's diff is a subset, so the saving measured here is a lower
  bound for round pushes. Non-code PRs run no tests in either lane (D4) and are
  excluded from every share.
- **R, past red CI runs.** `ci.yml` `pull_request` runs with conclusion
  `failure` whose logs are still retrievable (`gh run list --workflow ci.yml
  --status failure`; 194 PR-event runs listed back to 2026-04-02, log
  retention decides how many are usable). For each: the failing jobs (auxiliary
  jobs included) and failing test node ids from `gh run view --log-failed`,
  replayed against the diff from the run's merge base to its head SHA.
- **S, seeds.** The PoC's 13 seeds plus the D7 additions, each with a pinned
  mode (`SELECTED` or `FULL` + reason).

## Selector variants

- **Pilot:** every layer-1 row plus layer 4's mapped readers; layers 2 and 3
  absent (D5 table, "Pilot").
- **Precision:** pilot plus layer 2 (hub resolution, import-time scan, string
  imports, registry consumers), transitive layer 3, notebook import parsing.

Both static, stdlib only, reading every file from the commit under test
(`git cat-file`), never from the working tree. **The rule tables are frozen
(committed) before the H and R replays run.**

## Metric definitions

Per H diff and per seed, for both variants:

| Metric | Definition |
| --- | --- |
| Selected share | selected Stage-1 test count / total; FULL counts as 100%. Per-file counts from one `pytest --collect-only --stage=1` on the current tree; a file absent today gets the median per-file count |
| Wall-clock share | sum of `.test_durations_pass1` over the selection / its total; tests missing from the file (7,612 entries are present, `len(json.load(...))`) get their file's mean, else the global median |
| CI jobs triggered | `code`-gated jobs that run per D6, out of the 15 `ci.yml` counts |
| FULL-fallback rate | share of H diffs whose result is FULL, broken down by reason |
| False negatives | seeds whose known failing test is not selected or whose pinned mode is not met; R failures in a selector-reachable job whose test is not selected, classified per D7 § Escape log |
| Over-selection | for SELECTED `src/`-touching diffs: selected tests / tests a coverage-context run (`--cov-context=test`, one local full Stage-1 run) executed in any changed `src/` file, plus changed test files themselves |
| Rule-table size | layer-1 rows, core-module list entries, layer-4 table entries |

## Targets (fixed 2026-10-04)

Typical = median over H. Judged on the **precision** variant; the pilot's
figures are reported only (RFC § Roadmap, Phase 0 exit: the pilot narrows no
`src/` edit by construction).

| Metric | Target (precision variant) | Kind |
| --- | --- | --- |
| Wall-clock share | median ≤ 50% | hard, stop input |
| Selected share | — | report only: wall-clock is the cost D5's cut-off uses |
| CI jobs triggered | — | report only; feeds the cut-off (Open Question 2) |
| FULL-fallback rate | ≤ 30% of H | target; above 50% is a stop |
| False negatives | 0 seed misses, every pinned mode met, 0 deterministic selector-reachable R misses | hard (RFC exit) |
| Over-selection | — | report only, median ratio |
| Rule-table size | flag if layer-1 > 25 rows or core list > 15 modules | soft caps, flag not stop |

**Miss policy.** Rules are frozen before the replay. A miss is fixed by a
general rule plus a new seed, and the replay is rerun. The exit is judged on
the rerun; the frozen-table miss count is reported beside it as a rule-health
figure.

**Stop criterion.** Stop if, under the precision variant, the median
wall-clock share exceeds 50% or the FULL-fallback rate exceeds 50% ("typical
diffs still fall back to FULL"). A FULL rate between 30% and 50% is reported as
a missed target, not a stop.

**Build** requires every Phase 0 exit criterion: the reader inventory passes
two-method agreement, 0 seed misses with every pinned mode met, 0
deterministic selector-reachable historical misses after the rerun, and the
wall-clock target met.

## Exit work besides the replay

1. Text-reader inventory over `src/`, `tests/`, `scripts/` `.py` files: the
   runtime scan (extended `srcreads.py`) in default and randomised order,
   unioned, against a static scan; every one-method reader investigated.
2. Core-module list: modules every backend source reaches (layer 2) and
   modules with import-time effects beyond definitions (AST scan).
3. Class-pattern audit (D4): every literal path in the five `*_PAT` patterns
   is tracked; every tracked file a test reads falls in a class whose jobs run
   that test.
4. Seed run through the PoC driver with the selector in place of testmon.
