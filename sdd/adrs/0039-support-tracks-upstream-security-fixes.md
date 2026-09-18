# ADR-0039: A Python Version Is Supported While Upstream Still Fixes It

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

The published dependency policy's Rule 8 adopted [SPEC 0](https://scientific-python.org/specs/spec-0000/)
and promised support for at least three years after a Python version's release.
Read the way SPEC 0 intends, that licensed dropping two interpreters the day it
shipped: 3.10 was past three years and 3.11 followed a year later. Nothing
decided either way. `requires-python = ">=3.10"` and the five
`Programming Language :: Python` classifiers stood because nobody had revisited
them, and a reader could not tell that from a deliberate choice to be generous.

**The window was the wrong one, not the decision.** The line that matters to a
user is the one upstream draws: CPython publishes source-only security releases
for five years after a version's first release, and a version still receiving
them is one people are reasonably still running. Dropping a version that
upstream is still fixing strands users for our convenience. SPEC 0's three years
is a floor beneath that, not a schedule to follow to the letter.

### The measured inputs

Each figure below names the command or query it came from, run before the
sentence was written.

**Release and support-end dates.** `www.python.org` and
`devguide.python.org` were unreachable from the environment this was gathered
in, so the source is each version's **release-schedule PEP**, fetched from
`raw.githubusercontent.com/python/peps/main/peps/pep-0<n>.rst`. Every one of the
five carries the same lifetime — "security updates (source only) will be
released until 5 years after the release of x.y.0 final", except PEP 745
(3.14), which spells the number "five" — and gives the end as a month, so the
exact day is `final + 5 years`:

| Version | PEP | `x.y.0 final` | Security support ends | Standing on 2026-09-17 |
|---|---|---|---|---|
| 3.10 | 619 | 2021-10-04 | 2026-10-04 | 17 days left |
| 3.11 | 664 | 2022-10-24 | 2027-10-24 | 402 days |
| 3.12 | 693 | 2023-10-02 | 2028-10-02 | 746 days |
| 3.13 | 719 | 2024-10-07 | 2029-10-07 | 1116 days |
| 3.14 | 745 | 2025-10-07 | 2030-10-07 | 1481 days |

So **nothing is past its window**, and only 3.10 is close. Under the three-year
reading, 3.10 and 3.11 were both past and 3.12 was fifteen days out.

**No declared dependency has dropped 3.10.** Gathered 2026-09-16 from PyPI's
JSON API over every direct dependency of every user-facing extra: the current
release of each floor carries `requires_python` between `>=3.7` and `>=3.10`,
and `dagster` is the only one with an upper bound (`<3.15`). Supporting 3.10 is
therefore not notional — a user on it can resolve every extra.

**One floor exists only for 3.10.** `pyproject.toml`'s
`toml = ["tomli>=1.1.0; python_version < '3.11'"]`, marker-gated because
`tomllib` is stdlib from 3.11. It becomes dead code on a 3.11 floor.

**What the two oldest legs cost CI.** From the Actions API
(`/runs/{id}/jobs?filter=latest`), job duration as
`completed_at − started_at`, skipped jobs excluded. The legs are read from
`ci.yml`'s `setup` job and `.python-version` (3.13): 3.10 is three jobs
(`typecheck` plus two `test` shards — it carries the typecheck job as
`MIN_PYTHON`, so the two legs are not like-for-like) and 3.11 is two.

| Workflow | Runs measured | 3.10 | 3.11 | Run total | Share |
|---|---|---|---|---|---|
| `ci.yml` | 35254023596, 35011027743, 34848524875 | 5.94 min | 4.92 min | 52.02 job-min | 20.9% |
| `ci-full.yml` | 35266446011, 35254023571, 35203315474 | 8.27 min | 7.43 min | 37.78 job-min | 41.6% |

Those are runner-occupancy job-minutes rather than time a contributor waits:
both matrices fan out fully in parallel. In `ci.yml` the legs are **never** the
longest job — `test-primary` is, at 3.80 to 3.95 min against the slowest 3.10
job's 2.57 to 2.80 — so removing them would cut job-minutes and almost no
wall-clock. In `ci-full.yml` a 3.10 or 3.11 job **is** the longest job in all
three runs, so dropping 3.10 shortens that workflow by about 0.92 min of a
8.74 min mean, after which `test-full (3.14)` at ~7.4 min becomes the bound.

Four caveats the figures carry rather than shed: billable minutes are
unavailable on a public repository (`get_workflow_run_usage` returns
`total_ms: 0` for every job, so only a per-run `run_duration_ms` exists and it
cannot be apportioned); two of the three newest `master` pushes were docs-only
with the whole matrix skipped, so the `ci.yml` runs used are two to three days
older than the newest; caches were warm in all eight runs; and
`test-full (3.10)` ranges 7.15 to 9.18 min across runs under runner contention,
so its mean is not a property of the interpreter.

One effect is **unmeasured** and recorded as a hypothesis rather than a finding:
on a `master` push both workflows fire together, 29 concurrent jobs against the
20-slot cap [ADR-0032](0032-tiered-ci-gate-with-full-matrix-backstop.md) works
under, and critical-path jobs queued 2.87 to 2.98 min in the contended run
against 0.32 to 1.23 min in an uncontended one. Freeing seven slots would
shorten that wait; by how much would need a trial run.

## Decision

**A Python version is supported for as long as CPython ships security fixes for
it.** That is the promise Rule 8 now publishes, with SPEC 0's three-year window
named as the ecosystem floor beneath it so a reader can see where ours sits
relative to the schedule their other dependencies follow. Ours is the longer of
the two, and the rule promises a floor rather than a ceiling: we may support a
version past the end of its security support, and will not support one for less.

**3.11, 3.12, 3.13 and 3.14 stay**, because none is near its window and no
declared dependency has dropped even 3.10.

**3.10 goes when upstream stops fixing it**, which § The measured inputs puts at
2026-10-04 (five years after its 2021-10-04 release, per PEP 619). That drop is BK-380's, not this record's: raising `requires-python`
moves every spelling of the supported set, is a breaking change, and takes its
own change. Until it lands the position is this decision rather than inertia,
which is the whole point of writing it down.

**The window is derived, not remembered.** `scripts/python_support.py` holds the
release dates and the arithmetic, the classifiers decide the set,
`scripts/gen_python_support.py` draws the chart the policy page publishes, and
`scripts/drift_report.py` reports each interpreter's standing on the weekly
drift-guard issue. A crossing licenses a drop; it never requires one.

**Revisit at the next minor release**, or when the weekly report shows a
crossing, whichever comes first.

## Consequences

The promise gets longer, which is a widening rather than a break: no user loses
a version they had. It also commits CI to five interpreters for longer than SPEC
0 would have, at the job-minute cost measured above — cheap in `ci.yml`, where
the legs are never the critical path, and real in `ci-full.yml`, where the
oldest leg is the longest job.

[ADR-0032](0032-tiered-ci-gate-with-full-matrix-backstop.md) names the
interpreter set twice and is **not** superseded here, because the set does not
change. BK-380 will supersede it.

The three-year figure survives in one place and for one reason: the chart marks
it, so a reader can see both windows at once. Nothing decides on it.
