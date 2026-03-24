# Research: Benchmark Suite v2 — User-Decision Framing

**Date:** 2026-03-24
**Backlog:** ID-103 (new)
**Status:** Proposed
**Scope:** Redesign benchmark reporting and expand Toxiproxy coverage to reframe
the suite around user adoption decisions rather than maintainer diagnostics.

---

## 1. Problem Statement

The current benchmark suite is strong at measuring raw operation cost across
backends. It is weaker at answering the actual user question:

> "What am I paying for abstraction, and when does that overhead disappear
> relative to network/storage latency?"

Specific gaps:

1. **No README signal.** The README mentions nothing about performance. Users
   who care (most, for a storage abstraction) have no indication the project
   even thinks about it.
2. **Toxiproxy covers only Azure.** S3 and SFTP have no latency simulation,
   so the suite cannot show overhead collapsing under realistic RTT.
3. **Tables only, no charts.** The performance guide has raw tables. A chart
   showing "overhead vs RTT" communicates in one glance what tables cannot.
4. **Maintainer framing.** The performance guide opens with "remote-store
   includes a comprehensive benchmark suite" — maintainer language. Users want
   to know: should I worry about overhead?
5. **No "worth it?" verdict.** Users must interpret raw numbers themselves.

## 2. Design Decisions

### What this plan is NOT

This is NOT a rewrite of the benchmark test suite. The current tests measure
the right primitives. The changes are:

- **Toxiproxy expansion** (infra + fixtures)
- **Better reporting** (new chart generation, reframed docs)
- **README addition** (one paragraph + link)
- **Selective benchmark additions** (seekable, cache — only where real gaps exist)

### Scope boundaries

| In scope | Out of scope |
|----------|--------------|
| Toxiproxy for S3 + SFTP | Concurrency benchmarks (separate project) |
| 4 named network profiles | Cold/warm tracking (impractical) |
| Chart generation script | Interactive/JS charts |
| Performance guide reframe | New "workflow" benchmarks |
| README one-paragraph addition | README chart |
| "Worth it?" verdicts in reports | Feature-cost benchmarks (except seekable + cache) |
| `seekable_read()` benchmark | OTel/atomic/glob cost benchmarks (noise-level deltas) |
| Cache hit/miss benchmark | Restructuring test files into "families" |

### Why NOT restructure into 3 benchmark families

The proposal to split into "overhead / workload / network" families is a
**presentation concern, not a structural one.** The current test files
(`test_throughput.py`, `test_metadata.py`, etc.) organize by operation type,
which is correct for pytest. The "family" framing belongs in reporting and
docs, not in test file layout.

### Why NOT add most "feature cost" benchmarks

Most feature costs (atomic write, error mapping, path validation, OTel hooks)
are **dominated by underlying I/O**. The delta is one syscall or one function
call — ~50µs locally, invisible on network. Measuring them produces noise,
not signal.

Exceptions worth measuring:
- **`seekable_read()`** — real spill cost (temp file materialization)
- **Cache hit/miss** — real I/O skip

### Why NOT add workflow benchmarks

"Ingest 10,000 × 4 KB files" sounds realistic but is still synthetic. Under
Toxiproxy (10k × 100ms RTT = 17 min for one workload), runtime explodes. The
insight over extrapolating from primitive ops is marginal. The current suite
already covers 50/1k/10k listings and 1KB–100MB throughput.

---

## 3. Implementation Plan

### Phase 1: Toxiproxy expansion

**Goal:** Enable latency simulation for all Docker backends.

#### 1a. Docker infrastructure

Update `benchmarks/infra/docker-compose.yml`:

- Add `minio` proxy: toxiproxy listens on 19000, forwards to minio:9000
- Add `sftp` proxy: toxiproxy listens on 12222, forwards to sftp:2222
- Keep existing `azurite` proxy (10001 → azurite:10000)
- Update `toxiproxy.json` with all three proxy definitions

#### 1b. Toxiproxy module

Extend `benchmarks/_toxiproxy.py`:

- Support multiple proxy names (not just `"azurite"`)
- Add named profiles:
  - `clean` — no toxics (baseline)
  - `rtt20` — 20ms latency, 7ms jitter
  - `rtt50` — 50ms latency, 17ms jitter
  - `rtt100` — 100ms latency, 33ms jitter
- Add `apply_profile(proxy_name, profile_name)` function
- Add `clear_all_toxics(proxy_name)` function
- Keep existing `set_latency()` / `clear_latency()` as low-level API

#### 1c. Conftest fixtures

Update `benchmarks/conftest.py`:

- Add `--network-profile` CLI flag: `clean|rtt20|rtt50|rtt100` (default: clean)
- Add `s3-latency` and `sftp-latency` backend params (parallel to existing
  `azure-latency`)
- Apply selected profile to all `-latency` backends at session start
- Clear toxics at session end

#### 1d. Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCH_TOXIPROXY_HOST` | 127.0.0.1 | Toxiproxy API host |
| `BENCH_TOXIPROXY_API_PORT` | 8474 | Toxiproxy API port |
| `BENCH_MINIO_PROXY_PORT` | 19000 | Proxied MinIO port |
| `BENCH_SFTP_PROXY_PORT` | 12222 | Proxied SFTP port |
| `BENCH_AZURITE_PROXY_PORT` | 10001 | Proxied Azurite port (existing) |

#### 1e. Verification

- Run existing comparative tests with `--backend s3-latency --network-profile rtt50`
- Confirm latency is visible in results (write 1MB should show ~50ms+ increase)
- Run with `--network-profile clean` to confirm baseline matches direct connection

### Phase 2: Reporting and charts

**Goal:** Generate user-facing charts from benchmark data + add "worth it?" verdicts.

#### 2a. Chart generation script

Create `benchmarks/charts.py` (or extend `report.py`):

- Reads `.benchmarks/` JSON files (same source as `report.py`)
- Generates SVG charts via matplotlib to `docs-src/img/benchmarks/`
- Add `hatch run bench-charts` command

**Charts to generate (3 total):**

1. **Overhead % by backend** — grouped bar chart
   - X-axis: operation (write 1MB, read 1MB, exists, list 50, delete)
   - Bars: overhead % vs raw SDK
   - Groups: one color per backend (S3, Azure, SFTP, Local)
   - This answers: "what am I paying?"

2. **Overhead vs RTT** — line chart *(requires Phase 1 data)*
   - X-axis: network profile (0ms, 20ms, 50ms, 100ms)
   - Y-axis: overhead %
   - Lines: one per operation category (I/O ops, metadata ops)
   - This is the killer chart — shows overhead collapsing under latency

3. **Throughput by file size** — line chart
   - X-axis: file size (1KB, 64KB, 1MB, 10MB)
   - Y-axis: MB/s
   - Lines: remote-store vs raw SDK, one chart per backend
   - Shows where remote-store converges with raw SDK

**Chart style:** clean, minimal, no gridlines clutter. Match the project's
visual identity. SVG for crisp rendering in docs.

#### 2b. "Worth it?" verdicts

Extend `report.py` comparative output to append a verdict per backend/op:

| Verdict | Criteria |
|---------|----------|
| **Negligible** | delta <10% or <1ms absolute |
| **Moderate** | 10–50% but <5ms absolute |
| **Visible** | >50% and >5ms absolute |
| **Favorable** | remote-store faster than raw SDK |

Example output line:
```
S3 Write 1MB: 20.1ms vs 31.6ms raw → Favorable (remote-store 1.6x faster)
S3 Exists:    1.4ms vs 1.3ms raw   → Negligible (+0.1ms, +8%)
```

#### 2c. User-facing report command

Add `hatch run bench-report-user` that produces a condensed summary:

- One table per backend with verdicts
- Bottom-line statement per backend
- No maintainer detail (stddev, rounds, etc.)

### Phase 3: README and performance guide reframe

**Goal:** Surface performance story where users look first.

#### 3a. README addition

Add a "Performance" section after Quick Start (before Extensions/Features).
Approximately 3 lines of prose + link. Content:

> remote-store adds minimal overhead on top of the native SDKs it wraps. For
> network backends (S3, Azure, SFTP), writes and reads are typically within
> 5–15% of raw SDK calls; under realistic network latency, the abstraction
> cost becomes negligible. See the
> [performance guide](https://docs.remotestore.dev/stable/performance/) for
> comparative benchmarks, methodology, and overhead analysis.

No tables, no charts in README. Just the story + link.

#### 3b. Performance guide reframe

Restructure `guides/performance.md`:

**Current structure:**
1. Methodology
2. What We Measure (table)
3. Comparative Benchmarks (explanation)
4. Running Benchmarks (commands)
5. Sample Results (table)
6. How remote-store Compares (prose)
7. Analyzing Results
8. Reproducing

**New structure:**
1. **Lead paragraph** — answer the user's question upfront:
   "remote-store wraps established Python storage libraries. The abstraction
   adds measurable overhead for fast local operations, but for remote backends
   under realistic network latency, the cost is typically small relative to
   network and service time."
2. **Overhead at a glance** — the overhead % chart (from 2a)
3. **What happens under real latency** — the overhead vs RTT chart (from 2a),
   with 2–3 sentences explaining the takeaway
4. **Comparative results** — existing tables (keep, they're good for detail)
5. **Throughput by file size** — chart (from 2a)
6. **Caveats** — existing emulator/caching notes (keep, move here)
7. **Methodology** — condensed (move down, users care less)
8. **Running benchmarks yourself** — existing commands (move to end)
9. **See also** — existing links

The key change: **lead with the answer, not the methodology.**

### Phase 4: Selective benchmark additions

**Goal:** Fill the two real gaps in measurement coverage.

#### 4a. Seekable read benchmark

Add to `test_throughput.py` or new `test_seekable.py`:

- `Store.read_seekable()` on backends with different seek strategies
- Measure: open cost, first seek latency, repeated random seeks, peak memory
- Compare: native seekable (local, S3-PyArrow) vs Azure `_AzureRangeReader` vs spool path (HTTP)
- This is directly relevant given the recent ID-102 work (`Store.read_seekable()`, `_AzureRangeReader`)

#### 4b. Cache hit/miss benchmark

Add to `test_throughput.py` or new `test_cache.py`:

- Read same file with/without `CachedStore`
- Cold read (miss) vs warm read (hit)
- Measure: read latency, I/O eliminated
- This demonstrates real feature value

---

## 4. Backlog item

```
- [ ] **ID-103 — Benchmark suite v2: user-decision framing**
  Expand Toxiproxy to all Docker backends, generate overhead charts,
  reframe performance guide for user decisions, add README performance
  section.
  - Research: [research-benchmark-suite-v2.md](research/research-benchmark-suite-v2.md)
  - Phase 1: Toxiproxy expansion (docker-compose, fixtures, profiles)
  - Phase 2: Chart generation + "worth it?" verdicts in reporting
  - Phase 3: README section + performance guide reframe
  - Phase 4: seekable_read() + cache hit/miss benchmarks
```

## 5. Dependencies

- Phase 1 has no dependencies (can start immediately)
- Phase 2 chart #2 (overhead vs RTT) requires Phase 1 data
- Phase 2 charts #1 and #3 can use existing benchmark data
- Phase 3 can start in parallel with Phase 2 (prose doesn't need charts)
- Phase 4 is independent of all other phases

## 6. Estimated scope

| Phase | Files touched | New code | Effort |
|-------|--------------|----------|--------|
| 1 | docker-compose.yml, toxiproxy.json, _toxiproxy.py, conftest.py | ~150 lines | Medium |
| 2 | charts.py (new), report.py, pyproject.toml | ~200 lines | Medium |
| 3 | README.md, guides/performance.md, docs-src/performance.md | ~50 lines net | Small |
| 4 | test_seekable.py or test_throughput.py, test_cache.py | ~100 lines | Small |

Total: ~500 lines of new/changed code. No test suite restructuring.

## 7. What was explicitly rejected

| Idea | Reason |
|------|--------|
| Restructure tests into 3 "families" | Presentation concern, not structural |
| 10 workload benchmarks | Synthetic, runtime explosion under latency |
| Feature-cost benchmarks (OTel, atomic, glob) | Noise-level deltas |
| Cold/warm explicit tracking | Impractical to enforce, marginal value |
| Concurrency benchmarks | Separate project, sync API |
| 8 network profiles | 4 is enough to make the point |
| Interactive/JS charts | Adds weight, doesn't work in README/PyPI |
| Mermaid for benchmark charts | xychart-beta too limited for grouped bars |
| Chart in README | Too much for first impression; prose + link suffices |
| Tier A/B/C comparison classification | Already handled by existing caveats |

## See also

- [Performance guide](../../guides/performance.md) — current user-facing docs
- [Comparative results](../../benchmarks/results/comparative.md) — current baseline
- [Toxiproxy module](../../benchmarks/_toxiproxy.py) — existing latency simulation
- [Benchmark README](../../benchmarks/README.md) — current suite documentation
