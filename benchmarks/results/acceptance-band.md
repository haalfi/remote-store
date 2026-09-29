# Retirement acceptance band
<!-- doc: repo-only -->

The benchmark condition a class must meet before it is deleted in favour of
its replacement: RFC-0017 D8 step 3, condition (b). It binds the PR that
retires `S3Backend` and `S3PyArrowBackend` (D3 step 2) and the PR that replaces
the hand-written sync `AzureBackend` with the generated sync driver (D3 step 4).
This file states the rule; it holds no results.

## The rule

**Every cell's replacement median is at most 10% or 1 ms slower than the
retiring class's median, whichever allowance is larger.** A cell is one
operation at one payload size (or one sweep point, for the two scripts below)
on one backend pair. With `r` the retiring class's median and `n` the
replacement's, a cell passes when `n - r <= max(0.10 * r, 1 ms)`. Faster is
always inside the band.

- **Paired, in one session.** Both classes run in the same invocation on the
  same runner against the same service, so hardware and service noise hit both
  sides. Medians, not means: `pytest-benchmark` reports both, and the two
  standalone scripts already compute `statistics.median`.
- **The benchmarks are the four RFC-0017 D8 names.**
  `benchmarks/test_throughput.py` and `benchmarks/test_seekable.py` take one
  run with both lanes selected (`--backend <retiring>,<replacement>`). A cell
  there is a test measuring one of the two classes: every `bench_backend`
  test, and the `bench_target` tests (`test_write_bytes`, `test_read_bytes`)
  only at their remote-store target. Their raw-SDK and fsspec targets measure
  neither class and are not cells. The two standalone
  scripts construct one class each, `bench_pyarrow_tier1.py` the retiring
  `S3PyArrowBackend` and `bench_azure_pyarrow.py` the retiring `AzureBackend`
  (`rg -n 'S3PyArrowBackend\(|AzureBackend\(' benchmarks/bench_*.py`). The
  retiring PR therefore owes those two a backend parameter first, so both
  classes run in one invocation.
- **The retiring PR also owes a lane for a replacement that has none.** The
  `azure` lane in `benchmarks/conftest.py` builds `AzureBackend`, so the
  generated sync Azure driver needs its own `bench_backend` and
  `bench_target` lane before step 4's run. `s3-boto3` already has one.
- **The paired run is taken at a commit where both classes exist**, inside
  the retiring PR and before its deletion commit, because that PR registers
  the replacement under the same type string and deletes the retiring
  class. The PR records that commit.
- **The reference lane is the retiring class as users get it by default, on
  a clean network.** Three lanes follow:
  - `S3Backend`'s reference is `s3-nocache`, which is cache-off in both
    fixtures; `S3Backend`'s listing cache is off by default
    (`_DEFAULT_USE_LISTINGS_CACHE = False` in `_s3_base.py`).
  - `S3PyArrowBackend`'s reference is `s3-pyarrow`.
  - `AzureBackend`'s reference is `azure`.

  The `s3` lane is not a second reference. In `bench_backend` it builds the
  same cache-off `S3Backend`, and in `bench_target` it opts the cache back on
  (`conftest.py`), an opt-in. The `*-latency` lanes are out of scope, being a
  simulated network that neither replacement has a lane for.
- **The retiring class is compared at its best tier.** For S3 that is
  `S3PyArrowBackend` read through `bench_pyarrow_tier1.py`'s Tier 1, since
  the replacement loses that probe (RFC-0017 D4). The replacement is compared
  at the tier `ext.arrow` then serves it.
- **One cell outside the band blocks the deletion.** The run is not repeated
  until it passes; a failing cell is either fixed in the replacement or
  reported to the maintainer, who decides whether the regression is accepted,
  and that decision is written into the retiring PR.
- **The PR records the table**: per cell, `r`, `n`, the allowance, and pass or
  fail, with the command that produced it.

## Why these two thresholds

Both are the boundaries `benchmarks/report.py`'s `_magnitude` already uses:
its `<10%` band, and the 1 ms floor below which it treats a percentage as
noise. That function describes a delta and disclaims acceptability; this file
is where acceptability is decided, for this one purpose.

## Why not the run of record

`run-of-record/` cannot be the reference. Its files are slimmed to
`stats.mean` alone, with no dispersion, and `clean.json` carries no
`s3-boto3` lane, the S3 replacement, in either fixture. This command counts
each cell's lane, `bench_backend` or `bench_target`'s first element; it
prints only `local`, `s3`, `s3-pyarrow`, `sftp` and `azure`, and `{'mean'}`:

```bash
python -c "import json,collections;d=json.load(open('benchmarks/results/run-of-record/clean.json'));print(collections.Counter(b['params'].get('bench_backend') or b['params']['bench_target'][0] for b in d['benchmarks']));print(set(k for b in d['benchmarks'] for k in b['stats']))"
```

It also runs on hardware a retirement PR does not share. The paired run
removes all three problems.
