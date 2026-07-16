# Research: Benchmark Overhead Story — Reproducible Run of Record + User-Decides Framing (ID-230)

**Date:** 2026-07-16
**Backlog items:** ID-230 (Benchmark overhead story: reproducible run of record + user-decides framing)
**Status:** Implementation plan — ready for design decisions
**Predecessor:** [research-benchmark-suite-v2.md](research-benchmark-suite-v2.md) (ID-103, shipped) · governance half shipped as BK-309

---

## 1. Problem Statement

ID-230 is purpose-2 of the benchmark-suite rework. Purpose-1 (governance: give
the suite a scheduled home that gates correctness and flags regressions) shipped
as BK-309 / `benchmark.yml`. Purpose-2 is the **published overhead story** the
suite exists to support, and today it fails on two independent counts.

**Framing principle (the spine of this item).** The suite answers *"what is the
overhead?"* It must not answer *"is it acceptable?"* — acceptability depends on
the reader's workload, latency budget, and alternatives, so only the reader can
decide. The suite's job is to hand over the data and the levers to test it
against their own workload, not to hand down a verdict.

Two failures, both concrete:

1. **Data-freshness.** The only checked-in numbers rest on a single stale run:
   `benchmarks/results/comparative.md` is stamped `2026-04-12 … Windows`
   (`benchmarks/results/comparative.md:1-2`) — a laptop, three months old at
   time of writing. The four SVG charts in `docs-src/explanation/performance.md`
   derive from `.benchmarks/` JSON that is **not committed** (`benchmarks/charts.py`
   defaults `--dir .benchmarks`, `benchmarks/charts.py:492`), so they cannot be
   reproduced, diffed, or trusted. There is no path from "what's in the repo" to
   "the numbers on the docs site".

2. **Framing.** The reporting editorialises acceptability on the reader's behalf.
   `report.py`'s `_verdict()` classifies each op as
   `Favorable / Negligible / Moderate / Visible` (`benchmarks/report.py:400-420`),
   and the docs lead with the same value-judgements ("measurable but negligible",
   `docs-src/explanation/performance.md:25`; "overhead … is small … for most
   workloads", `README.md:230`). "Negligible" and "Favorable" are verdicts on
   whether the cost is worth paying — the reader's call, not the suite's.

**This is a data-freshness + framing item, not new tooling.** The machinery
(chart generator, comparative renderer, verdict scaffolding) stays; we change
what feeds it and how it speaks.

---

## 2. Current State (evidence)

| Concern | Where | Finding |
|---------|-------|---------|
| Stale comparative data | `benchmarks/results/comparative.md:1-3` | Single 2026-04-12 Windows laptop run; `<!-- doc: repo-only -->` but embedded into the published guide via `--8<--` (`docs-src/explanation/performance.md:163`). |
| Uncommitted chart source | `benchmarks/charts.py:487-527` | Charts read `.benchmarks/*.json` (gitignored runtime dir). The four committed SVGs (`docs-src/img/benchmarks/`) have no committed source — not reproducible. |
| RTT chart needs multi-profile data | `benchmarks/charts.py:473-485,536-540` | `overhead-vs-rtt.svg` is built from `_load_profile_data()` across several profile JSONs (`clean/rtt20/rtt50/rtt100`), produced only by `bench-latency-matrix` (`benchmarks/run_latency_matrix.py:19-20`). |
| Scheduled run omits both | `.github/workflows/benchmark.yml:52-121` | The run of record BK-309 produces starts minio/azurite/sftp and runs the tiered suite at **`clean` profile only**; it uploads `bench.json` + text reports, but **runs no latency matrix** and **generates neither `comparative.md` nor the SVG charts**. |
| No toxiproxy in the CI backend action | `.github/actions/start-backends/action.yml` | No toxiproxy service; the `-latency` backends have nothing to proxy through in CI, so latency profiles cannot run there as-is. |
| Verdict vocabulary editorialises | `benchmarks/report.py:400-420,449-454,580-582` | `_verdict()` + `--user` output label acceptability, not magnitude. |
| Docs echo the verdict | `docs-src/explanation/performance.md:1-28`, `README.md:228-230` | Lead-in prose asserts overhead is "negligible"/"small … for most workloads". |

---

## 3. Key Design Decisions

### 3.1 The run of record cannot be "just wire it to `benchmark.yml`" as written

The backlog says *"wire the run of record to [BK-309's scheduled workflow] rather
than a laptop."* That is the right source in spirit — a documented Linux/Docker
runner beats a Windows laptop — but the workflow **as it exists today produces
neither the latency-matrix data nor the checked-in artifacts (`comparative.md`,
4 charts) that purpose-2 needs.** Two gaps must close before the wiring is real:

- **Latency matrix.** `overhead-vs-rtt.svg` — the "killer chart" of the v2
  reframe (`research-benchmark-suite-v2.md:161-166`) and the mechanical heart of
  "overhead shrinks as latency grows" — requires `rtt20/rtt50/rtt100` runs.
  `benchmark.yml` runs `clean` only and `start-backends` has no toxiproxy. So the
  workflow must gain a toxiproxy service + a latency-matrix step, **or** the RTT
  chart is regenerated from a separate, documented `bench-latency-matrix` run and
  that provenance is recorded.
- **Artifact generation.** The workflow uploads `bench.json` and text reports but
  never runs `report.py --comparative --markdown` or `python -m benchmarks.charts`.
  Regenerating `comparative.md` + the SVGs is a manual post-processing step on the
  downloaded artifact today.

**Recommendation.** Keep the human in the loop for the *commit* (charts + data are
reviewable diffs, not auto-pushed), but make the *run* one documented command
path. Concretely: extend `benchmark.yml` (or add a `workflow_dispatch`-only
`benchmark-run-of-record` job) that (a) starts toxiproxy alongside the Docker
backends, (b) runs the `standard` tier at `clean` + the three RTT profiles,
(c) runs `report.py --comparative --markdown` and `benchmarks.charts`, and
(d) uploads the regenerated `comparative.md`, the four SVGs, **and the slimmed
source JSONs** as a single `run-of-record` artifact. A maintainer downloads that
artifact and commits it. This makes the run of record reproducible-by-workflow
without giving CI push rights to docs.

### 3.2 Commit the source JSON, slimmed and deterministic (scope point 2)

Charts and comparative tables must be reproducible and diffable from the repo.
The generators read a narrow slice of pytest-benchmark JSON:

- `charts.py` reads `benchmarks[].params.payload` + `benchmarks[].stats.mean`,
  and derives `(backend, target)` from `params.bench_target` via
  `_parse_backend_and_target` (`benchmarks/report.py:266-274`); only the operation
  prefix comes from the benchmark `name` (`_test_name`, used in
  `_extract_throughput`, `benchmarks/charts.py:113-133`). So `params` — not just
  `params.payload` — is load-bearing: the slim must retain `bench_target` too.
- `report.py --comparative` reads means + `machine_info` for the provenance
  header (`benchmarks/report.py:503-506,664`).
- `overhead-vs-rtt` needs **one JSON per network profile**
  (`benchmarks/charts.py:473-485`).

**Recommendation.** Commit a **slimmed, multi-file set** under
`benchmarks/results/run-of-record/` — `clean.json` (feeds `comparative.md`,
`overhead.svg`, `throughput.svg`, `s3-comparison.svg`) plus `rtt20.json`,
`rtt50.json`, `rtt100.json` (feed `overhead-vs-rtt.svg`). Slim each to
`name` / `params` / `stats.mean` **plus the top-level `network_profile` key**,
and retain top-level `machine_info` for provenance, keeping files small and
reviewable.

**The run-of-record recipe deliberately diverges from the
`baseline/local-baseline.json` recipe** (`benchmarks/README.md:282-286`): the
baseline is a single clean-profile file that never touches the RTT chart, so it
can drop `network_profile`; the run-of-record set **must not**. `charts.py`
groups profiles by an *in-file* key, not the filename:

- `_load_profile_data()` reads the **top-level `network_profile`** field, and
  defaults to `"clean"` when the key is absent (`benchmarks/charts.py:482`). That
  field is injected at run time by `conftest.py:168-169`. If the slimming step
  strips it, all four files collapse to `"clean"`, `overhead_by_profile` ends up
  with `< 2` profiles, and `chart_overhead_vs_rtt()` renders the "need clean + at
  least one latency profile" **placeholder** instead of the real chart
  (`benchmarks/charts.py:248-273`). The filenames are cosmetic.
- For any non-clean profile the chart looks up the **`-latency` backend variant**
  (`bk = _LATENCY_VARIANT[base]`, `benchmarks/charts.py:231`), so the rtt* files
  must contain benchmarks named for `s3-latency` / `sftp-latency` /
  `azure-latency`, **not** the base `s3` / `sftp` / `azure`. A run that merely
  wraps the base backends in a toxiproxy RTT will produce base-named benchmarks,
  the `_LATENCY_VARIANT` lookup will miss, and those series drop silently.

Add a regeneration path — `hatch run bench-charts --dir
benchmarks/results/run-of-record --file benchmarks/results/run-of-record/clean.json`
and `report.py --comparative --markdown --file
benchmarks/results/run-of-record/clean.json` — and document both the commands
**and the three invariants below** in `benchmarks/README.md`, so the next person
does not copy the baseline slimming recipe verbatim and ship a placeholder.

The `--file` on `bench-charts` is **required, not cosmetic**: the three
single-file charts (`overhead`/`throughput`/`s3-comparison`) are built from
`main()`'s `baseline_file`, which without `--file` is `files[-1]` — the
alphabetically **last** of the run-of-record set, i.e. `rtt50.json`, not
`clean.json` (`benchmarks/charts.py:519-523`). Those charts key on the base-name
`COMPARATIVE_BACKENDS = ["s3", "s3-pyarrow", "sftp", "azure"]`
(`benchmarks/charts.py:39`), but an rtt file contains only `-latency` entries, so
`_build_comparative_table` finds nothing and each chart hits its
"No comparative data found" early return (`benchmarks/charts.py:147-149,330-332,
420-422`) — a third silent-failure mode, blank chart, no error. See §3.5 for the
build-time assertions that enforce all three invariants.

### 3.3 Recast the verdict vocabulary: magnitude, not judgement (scope point 3)

`_verdict()` answers "is it worth it?". Recast it to answer only "how big is the
delta, and in which direction?" — leaving acceptability to the reader.

| Today (value-judgement) | Recast (neutral magnitude + factual direction) |
|-------------------------|------------------------------------------------|
| `Favorable` (faster ⇒ "good") | Report direction as a fact: **faster** / **slower**, never as praise. |
| `Negligible` (⇒ "don't worry") | **Sub-ms** / **<10%** — a size band, no reassurance. |
| `Moderate` | **10–50%** band — unchanged size, drop the implied comfort. |
| `Visible` | **>50%** band — unchanged size, drop the implied warning. |

Proposal: rename `_verdict()` → `_magnitude()` returning a size band on `|delta|`
(`sub-ms` when `<1ms` absolute, else `<10% / 10–50% / >50%`) paired with a factual
`faster`/`slower` direction. Example output line recast:

```
S3 Write 1MB: 20.1ms vs 31.6ms raw → 36% faster       (was: Favorable)
S3 Exists:    1.4ms  vs 1.3ms  raw → +8% (sub-ms)      (was: Negligible)
```

**This is a deliberate behavior change, not a relabel — own it.** The current
bands are *not* pure percentage bands: they interleave a percentage test with a
5 ms absolute floor (`Moderate` = `≤50% OR <5ms`; `Visible` = `>50% AND ≥5ms`,
`report.py:407-408,418-420`). The proposed `sub-ms / <10% / 10–50% / >50%` scale
drops the 5 ms component entirely, so boundary cases genuinely change class — a
60%-but-3 ms delta is `Moderate` today and `>50%` under the recast. That is a
good simplification (a magnitude descriptor should describe the delta's size, not
gate it behind a second absolute threshold), but the plan must state it as a
band redesign, and the tests must **assert the moved boundaries**, not just
substitute the new strings.

Locations to change together: `_verdict()` body + docstring table
(`report.py:400-420`), the `--user` print (`report.py:449-454`), the `--user`
help string (`report.py:580-582`), and `tests/scripts/test_bench_report.py` —
whose updates must cover the specific 5 ms-floor cases that change class (e.g. a
`>50% & <5ms` delta: `Moderate`→`>50%`), not only the renamed labels. Keep the
scaffolding — same call sites, new vocabulary.

### 3.4 Reframe the docs to present, not judge (scope point 3)

- `docs-src/explanation/performance.md`: lead with the numbers and the
  **mechanism** — "overhead is a fixed per-op cost; as network round-trip grows,
  it shrinks as a share of total time" (already half-present at lines 30-35, make
  it the lede). Replace "measurable but negligible" (`:25`) with the measured
  local delta and the note that sub-ms costs are irrelevant only *if* the
  reader's workload is network-bound — their call. Point at the levers
  (`hatch run bench-*`, the four `--network-profile` profiles) so readers test it
  against their own workload.
- `README.md:230`: replace "small … for most workloads" with the mechanism +
  link, no acceptability claim.
- Keep every table and chart; only the framing prose and the embedded
  `comparative.md` numbers change.

### 3.5 Build-time assertions (guard the silent-failure modes)

The chart generators degrade **silently** — no error, just a wrong or blank SVG —
whenever their input is shaped wrong (§3.2). Before committing the regenerated
charts, assert all three invariants so a bad run of record fails loudly instead
of shipping a placeholder:

1. **Profile key present** (guards `overhead-vs-rtt`). Each committed rtt file's
   top-level `network_profile` equals its intended profile (`rtt20.json` ⇒
   `"rtt20"`, …) and `clean.json` ⇒ `"clean"` (or omits the key). Equivalent
   check: `_load_profile_data()` over the committed set returns ≥ 2 distinct
   profiles including `"clean"`; otherwise `chart_overhead_vs_rtt()` renders its
   `< 2`-profile placeholder (`charts.py:248-273`).
2. **Latency files use `-latency` variants** (guards `overhead-vs-rtt`). Each rtt
   file contains benchmark `name`s for `s3-latency` / `sftp-latency` /
   `azure-latency` (i.e. the run used `--backend
   s3-latency,sftp-latency,azure-latency`, as `bench-latency-matrix` does,
   `benchmarks/run_latency_matrix.py:20`), so the `_LATENCY_VARIANT` lookup at
   `charts.py:231` hits.
3. **Single-file charts built from `clean`** (guards `overhead` / `throughput` /
   `s3-comparison`). `bench-charts` must run with `--file …/clean.json`; without
   it `main()` picks `files[-1]` = `rtt50.json`, whose `-latency`-only entries
   miss the base-name `COMPARATIVE_BACKENDS`, and the three charts hit their
   "No comparative data found" early return (`charts.py:147-149,330-332,420-422`).
   Assert the three base charts are non-empty (or that the baseline file the run
   used carried `network_profile == "clean"`/absent).

Cheapest home for these is the regeneration doc plus a guard in the slimming
script (fail if any invariant is violated); optionally a `test_charts.py` case
asserting the committed set yields real charts, not the placeholder/early-return
branches.

---

## 4. Implementation Plan

Three workstreams, mapping 1:1 to the backlog's scope points. W1 and W2 are
coupled (the run produces the data we commit); W3 is independent prose/label work
and can land in parallel.

### W1 — Produce one documented Linux/Docker run of record (scope 1)

1. Extend the scheduled workflow (or add a `workflow_dispatch` run-of-record job)
   to start **toxiproxy** with the Docker backends and run `standard` tier at
   `clean` (base backends) **plus `rtt20/rtt50/rtt100` on the `-latency` backend
   variants** — `--backend s3-latency,sftp-latency,azure-latency`, the set
   `bench-latency-matrix` already uses (§3.1, §3.5 assertion 2). Confirm
   `infra/docker-compose.yml` already defines the toxiproxy proxies (it does —
   v2/ID-103); the gap is the CI `start-backends` action, not compose.
2. In the same job, regenerate `comparative.md` (`report.py --comparative
   --markdown --file …/clean.json`) and the four SVGs (`bench-charts … --file
   …/clean.json`) from the run, and confirm the regenerated charts are real —
   RTT chart not the placeholder, base charts not empty — before uploading
   (all three §3.5 assertions).
3. Upload `comparative.md`, the four SVGs, and the slimmed JSON set — each rtt
   file retaining its top-level `network_profile` (§3.2, §3.5 assertion 1) — as
   one `run-of-record` artifact.

### W2 — Commit the run of record and make it reproducible (scope 2)

4. Commit the slimmed multi-profile JSON set under
   `benchmarks/results/run-of-record/` (§3.2).
5. Regenerate and commit `benchmarks/results/comparative.md` (now Linux/Docker,
   fresh stamp) and the four SVGs in `docs-src/img/benchmarks/` from that data.
6. Document the regeneration commands in `benchmarks/README.md` (§ Continuous
   Benchmarking / a new "Run of record" subsection) so the outputs are
   rebuildable from committed inputs — **including the two §3.5 invariants and
   the note that this slimming recipe diverges from the baseline recipe by
   keeping `network_profile`**, so the next person does not copy the baseline
   verbatim.

### W3 — Reframe reporting and docs to present, not judge (scope 3)

7. Recast `report.py` verdict → magnitude vocabulary (§3.3); update
   `tests/scripts/test_bench_report.py`.
8. Reframe `docs-src/explanation/performance.md` lede + caveats and `README.md`
   performance paragraph (§3.4).
9. Update any prose that quotes the old verdict words (ripple, §5).

---

## 5. Ripple Check

Per `sdd/CLAUDE-REFERENCE.md` (this touches docs, benchmarks, and reporting
vocabulary — not backends/errors/capabilities/versions, so no spec/FEATURES
ripple).

- **Regenerated artifacts:** `benchmarks/results/comparative.md`,
  `docs-src/img/benchmarks/{overhead,overhead-vs-rtt,throughput,s3-comparison}.svg`,
  new `benchmarks/results/run-of-record/*.json`.
- **Code/tests:** `benchmarks/report.py` (`_verdict`→`_magnitude`, `--user`
  output + help), `tests/scripts/test_bench_report.py` (label assertions **plus
  the moved 5 ms-floor boundary cases**, §3.3). `benchmarks/charts.py` needs no
  code change (it reads means, not labels), but consider a `test_charts.py` guard
  that the committed run-of-record set yields a real RTT chart, not the
  placeholder branch (§3.5). Add the slimming/guard script if one is introduced.
- **Docs prose:** `docs-src/explanation/performance.md`, `README.md`. Grep the
  repo for `Negligible|Favorable|worth it|negligible` before committing — the
  vocabulary leaks into prose (`README.md:230`, `performance.md:25`).
- **Runbook:** `sdd/CI-OPERATIONS.md:167-168` currently says the data-freshness
  follow-up "is tracked as ID-230"; on completion, update it to describe the
  run-of-record job and where its artifact lands (if W1 changes `benchmark.yml`,
  also refresh the `benchmark.yml` runbook section at `:144-179`).
- **Dev commands:** if a `bench-run-of-record` / regeneration script is added,
  register it in `pyproject.toml` `[tool.hatch.envs.default.scripts]` and list it
  in `benchmarks/README.md`.
- **CHANGELOG:** ID-230 audience includes `user.site` → a CHANGELOG entry **is
  required** (per `sdd/traces/_schema.yml` derived rule). The published overhead
  numbers and framing are user-facing.
- **Backlog/trace:** on implementation, move ID-230 to `BACKLOG-DONE.md`, author
  `sdd/traces/id-230-benchmark-overhead-story.yml`, and (if promoted) bump the ID
  bookkeeping per the completing-work procedure.

---

## 6. Scope, Effort, and What's Out

| Workstream | Files | Effort |
|-----------|-------|--------|
| W1 run of record | `.github/workflows/benchmark.yml`, `.github/actions/start-backends/action.yml`, `pyproject.toml` | Medium (CI iteration + a real Docker run) |
| W2 commit + reproduce | `benchmarks/results/run-of-record/*.json`, `comparative.md`, 4 SVGs, `benchmarks/README.md` | Small–Medium |
| W3 reframe | `benchmarks/report.py`, `tests/scripts/test_bench_report.py`, `performance.md`, `README.md` | Small |

Overall **M**, matching the backlog estimate.

**Out of scope** (keep the machinery, per the item):
- No new benchmarks, no new chart types, no test-suite restructuring.
- No change to the regression gate or baseline mechanism (BK-309's job).
- No auto-commit of docs from CI (artifact → human review → commit).
- No cloud (non-Docker) run of record — Docker emulators remain the documented
  source, with the existing "emulators are not cloud" caveat
  (`performance.md:91-94`) retained.

---

## 7. Open Questions

1. **Where does the run of record actually execute?** Extend the weekly
   `benchmark.yml` (adds toxiproxy + latency matrix to every run, +CI minutes), or
   a separate `workflow_dispatch`-only job invoked when refreshing the docs?
   Recommendation: the latter — the weekly job's purpose is the correctness/
   regression gate, and loading it with a full latency matrix every Monday is cost
   for no gate value. Decide before W1.
2. **Slim vs. full JSON commit.** Slimmed (§3.2) keeps diffs readable but drops
   stddev/rounds; full JSON is heavier but complete. Recommendation: slimmed —
   but note the run-of-record slimming **diverges** from the baseline recipe by
   keeping the top-level `network_profile` key per file (§3.2), without which the
   RTT chart silently falls back to a placeholder.
3. **Magnitude bands are a deliberate redesign, not a relabel.** §3.3 proposes
   `sub-ms / <10% / 10–50% / >50%`, which drops the current bands' 5 ms absolute
   floor (`report.py:407-408,418-420`). That *moves* boundary cases (a `>50% &
   <5ms` delta reclassifies), so it is a behavior change to own and test, not a
   string swap. Decide whether the simplification is wanted; if yes, assert the
   moved boundaries in `test_bench_report.py` (§3.3).

---

## See also

- `research-benchmark-suite-v2.md` — the v2 reframe this completes (Phase 3 =
  the framing this item finishes; charts/verdicts machinery = Phase 2).
- `benchmarks/results/comparative.md` — the stale artifact to regenerate.
- `docs-src/explanation/performance.md` — the guide to reframe + its embedded
  tables/charts.
- `benchmarks/report.py` — verdict → magnitude recast site.
- `.github/workflows/benchmark.yml` — BK-309 scheduled home; W1's extension point.
- `sdd/CI-OPERATIONS.md` §`benchmark.yml` — runbook to update on completion.
