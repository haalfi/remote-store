# Benchmark Suite
<!-- doc: repo-only -->

Performance benchmarks for remote-store backends, comparing remote-store,
raw SDK calls, and fsspec implementations.

## Prerequisites

- **Docker** with the Compose plugin (`docker compose`)
- **Hatch** (`pip install hatch`)

## Quick Start

```bash
# Start Docker services and wait for health checks to pass
docker compose -f infra/docker-compose.yml up -d --wait

# Run quick-tier benchmarks (~2 min/backend)
hatch run bench

# Run only a specific backend
hatch run bench -- --backend local

# Save results for later comparison
hatch run bench-save

# Compare against previous run
hatch run bench-compare

# Generate comparative report (remote-store vs raw SDK vs fsspec)
hatch run bench-report-comparative
```

## Backend Matrix

| Backend | Docker Service | Remote-Store | Raw SDK | fsspec |
|---------|---------------|-------------|---------|--------|
| Local | - | LocalBackend | pathlib | fsspec.local |
| S3 | MinIO :19100 | S3Backend | boto3 | s3fs |
| S3 (no cache) | MinIO :19100 | S3Backend (`use_listings_cache=False`) | - | - |
| S3-boto3 | MinIO :19100 | S3Boto3Backend | boto3 | - |
| S3-PyArrow | MinIO :19100 | S3PyArrowBackend | - | - |
| SFTP | OpenSSH :2222 | SFTPBackend | paramiko | sshfs |
| Azure | Azurite :10000 | AzureBackend | azure-storage-blob | adlfs |
| S3 (latency) | Toxiproxy :19000 → MinIO | S3Backend | - | - |
| SFTP (latency) | Toxiproxy :12222 → SFTP | SFTPBackend | - | - |
| Azure (latency) | Toxiproxy :10001 → Azurite | AzureBackend | - | - |

## Scenarios

### Comparative (remote-store vs raw SDK vs fsspec)
- **Write throughput** — bytes payloads (1KB, 64KB, 1MB, 10MB, 100MB)
- **Read throughput** — bytes payloads
- **Exists** — hit and miss
- **List files** — flat (50 and 1000 files)
- **Delete** — single file

### Remote-store only
- **TTFB** — time-to-first-byte (protocol overhead)
- **Stream write/read** — BinaryIO interface
- **Roundtrip** — write + read
- **Copy/move** — single file and across subtrees
- **Directory scale** — 200-file hierarchy listing, folder ops
- **Large file** — 10MB+ with memory tracking (tracemalloc)
- **Per-folder stats** — iterate folders + get_folder_info
- **Deep hierarchy** — 5 levels, branching factor 5

## Docker vs Cloud

### Docker mode (default)

Uses local Docker containers. No credentials needed.

```bash
docker compose -f infra/docker-compose.yml up -d --wait
hatch run bench
```

To stop and clean up Docker services afterwards:

```bash
docker compose -f infra/docker-compose.yml down -v
```

### Cloud mode

Runs against real cloud services.

**S3 family (`s3`, `s3-nocache`, `s3-boto3`)** reuses the Stage-3 live-test
wiring: credentials come from a local `.env` (loaded via
`load_dotenv(override=False)`, only in cloud mode), and the run is gated on the
`RS_TEST_LIVE_S3=1` opt-in — the same `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` the `s3_live` fixture uses. Each
S3 test provisions an ephemeral `rs-conformance-bench-<id>` bucket (matching the
`s3_live` IAM policy, which scopes `CreateBucket` to `rs-conformance-*`) and
deletes it on teardown. Set `BENCH_S3_BUCKET` only if you have a dedicated
pre-existing bucket to reuse instead.

```bash
# S3: put AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION in .env, then:
RS_TEST_LIVE_S3=1 hatch run bench-cloud -- --backend s3,s3-nocache,s3-boto3

# Azure
export AZURE_STORAGE_CONNECTION_STRING=...
export BENCH_AZURE_CONTAINER=my-bench-container

# SFTP
export BENCH_SFTP_HOST=sftp.example.com
export BENCH_SFTP_PORT=22
export BENCH_SFTP_USER=benchuser
export BENCH_SFTP_KEY_FILE=~/.ssh/id_rsa

hatch run bench-cloud
```

### moto mode (S3 family only)

Runs the S3-family lanes (`s3`, `s3-nocache`, `s3-boto3`) against an in-process
[moto](https://github.com/getmoto/moto) server. No Docker, no credentials, no
network: the server is started for the session and torn down after.

```bash
hatch run bench-moto -- --backend s3,s3-nocache,s3-boto3
```

**What it measures, and what it does not.** moto is a loopback-HTTP mock, so
these numbers isolate **client-library overhead** (s3fs/aiobotocore layering vs.
plain boto3, plus the s3fs directory cache) — they are **not** real-world
throughput. Use moto for the cheap, deterministic library-cost floor; use Docker
(MinIO) and cloud for numbers that include real network and storage behaviour.
`sftp` / `azure` / `s3-pyarrow` are skipped in moto mode.

### The `s3` vs `s3-boto3` comparison

`s3` is the s3fs-backed `S3Backend`; `s3-boto3` is the boto3-direct
`S3Boto3Backend` (the ID-202 lane). Both run through the same Store API
(`remote_store` target), so a `--backend s3,s3-boto3` run isolates the
**transport** difference, Store API held constant.

Read listing/metadata numbers with the cache in mind: with the s3fs directory
cache enabled, repeated `list_*` / `iter_children` calls are served from an
in-process cache (fast, but can be stale), whereas a fresh listing issues a
`list_objects_v2` every time (slower, always current). The benchmark surfaces
that trade-off rather than a pure speed verdict.

`S3Backend` defaults the dircache **off** (BK-257), so the benchmark fixes each
lane explicitly: the `s3` lane opts the cache back ON
(`client_options={"use_listings_cache": True}`) to represent the cached path,
while the `s3-nocache` lane forces it OFF — matching both the default and the
boto3 lane's fresh-every-call behaviour. So `--backend s3-nocache,s3-boto3`
isolates the listing *mechanism* (s3fs/aiobotocore vs. boto3) with neither side
cached, while `--backend s3,s3-nocache` shows what the dircache is worth. Note
the raw `s3fs` comparative target is *not* cache-disabled — it represents s3fs
as typically used.

## Speed Tiers

| Tier | Marker | What's included | Time/backend (Docker) | Time/backend (Cloud) |
|------|--------|-----------------|----------------------|---------------------|
| **quick** | (default) | 1KB, 64KB, 1MB payloads; 50-file list; basic ops | ~2 min | ~5 min |
| **standard** | `@pytest.mark.standard` | + 10MB payload; 1000-file list, deep hierarchy, per-folder stats | ~5 min | ~15 min |
| **full** | `@pytest.mark.full` | + 100MB payload; 10k-file list | ~20-30 min | ~60+ min |

Selection expressions:

- Quick: `-m "not standard and not full"` (default for `hatch run bench`)
- Standard: `-m "not full"` (`hatch run bench-standard`)
- Full: no filter (`hatch run bench-full`)

## Backend Filtering

Use `--backend` to restrict benchmarks to specific backends. This **deselects**
tests (no fixture setup or connection attempts for excluded backends).

```bash
# Only run local backend benchmarks
hatch run bench -- --backend local

# Run S3 and SFTP only
hatch run bench -- --backend s3,sftp

# Combine with standard tier
hatch run bench-standard -- --backend s3,s3-pyarrow
```

## Latency Simulation (Toxiproxy)

Toxiproxy sits in front of all three network backends, enabling simulated
network latency. Use the `--network-profile` flag to apply a named profile:

| Profile | Latency | Jitter | Use case |
|---------|---------|--------|----------|
| `clean` | 0 ms | 0 ms | Baseline (passthrough) |
| `rtt20` | 20 ms | 7 ms | Same-region cloud |
| `rtt50` | 50 ms | 17 ms | Cross-region |
| `rtt100` | 100 ms | 33 ms | Cross-continent |

```bash
# Run S3 with 50ms simulated latency
hatch run bench -- --backend s3-latency --network-profile rtt50

# Run all latency backends with 100ms
hatch run bench -- --backend s3-latency,sftp-latency,azure-latency --network-profile rtt100
```

The `-latency` backend variants connect through Toxiproxy. The non-latency
variants connect directly. Both can run in the same session.

The legacy `--latency <ms>` flag still works for Azure-only backward
compatibility but `--network-profile` is preferred.

## Timeout Watchdog

Each test has a timeout watchdog (default: 60s docker, 120s cloud). Override
with `--bench-timeout`:

```bash
hatch run bench -- --bench-timeout 30
hatch run bench-cloud -- --bench-timeout 300
```

**Latency runs need adjusted settings.** Pedantic benchmarks (delete, move)
pre-create a pool of files and run one operation per round. The default pool
size is 200, which is excessive under simulated latency. Use `--pool-size`
to reduce rounds, and raise the timeout to 120s:

```bash
hatch run bench -- --backend s3-latency --network-profile rtt50 \
  --pool-size=20 --bench-timeout 120
```

## Commands

| Command | What runs | Use case |
|---------|-----------|----------|
| `hatch run bench` | Quick tier (default) | Fast feedback |
| `hatch run bench-standard` | Quick + standard tier | Moderate testing |
| `hatch run bench-full` | All tiers | Pre-release, CI |
| `hatch run bench-save` | Quick + save JSON | Track regressions |
| `hatch run bench-save-standard` | Standard + save JSON | Wider regression check |
| `hatch run bench-save-full` | Full + save JSON | Complete data |
| `hatch run bench-compare` | Compare saved runs | Before/after |
| `hatch run bench-cloud` | Quick on real infra | Cloud perf testing |
| `hatch run bench-cloud-standard` | Standard on real infra | Cloud deep testing |
| `hatch run bench-moto` | Quick on in-process moto (S3 family) | Library-overhead floor, no Docker |
| `hatch run bench-moto-standard` | Standard on in-process moto (S3 family) | Wider library-overhead profile |
| `hatch run bench-report` | Summary table from saved JSON | Quick overview |
| `hatch run bench-report-compare` | Latest vs previous saved run | Spot regressions |
| `hatch run bench-report-json` | Machine-readable JSON | CI / scripting |
| `hatch run bench-report-comparative` | remote-store vs SDK vs fsspec | Overhead analysis |
| `hatch run bench-report-comparative-md` | Same, as Markdown to file | Docs generation |
| `hatch run bench-report-user` | Condensed report: delta + magnitude band | User-facing overview |
| `hatch run bench-charts` | Generate SVG charts from saved JSON | Docs charts |
| `hatch run bench-regression -- --file <run.json>` | Compare a run against the committed baseline | Regression gate |
| `hatch run bench-run-of-record -- <raw.json>...` | Slim raw runs into the run of record + guard the chart invariants | Publish overhead story |

## Continuous Benchmarking (CI)

The suite runs in [`.github/workflows/benchmark.yml`](../.github/workflows/benchmark.yml)
on a weekly `schedule` and via `workflow_dispatch` (with a `quick`/`standard`/`full`
tier input). It is deliberately **not** wired into PR/push CI: benchmark timing on
shared runners is noisy, and gating merges on it would flake. Two things are checked:

1. **Correctness gate.** The suite must execute green. A benchmark that errors or
   leaks a resource fails the job — this is what catches suite rot (e.g. BUG-228,
   a file-handle leak that went undetected precisely because nothing ran the
   benchmarks).
2. **Regression flag.** A fresh run is compared against the committed baseline
   ([`baseline/local-baseline.json`](baseline/local-baseline.json)) with
   `report.py --regression`. The comparison covers **every** `remote_store`
   operation present in both the run and the baseline — not just the
   `SUMMARY_ROWS` display set — so large-payload, streaming, and copy/move paths
   are gated, not only the summary write/list ops. An operation is flagged when
   its mean exceeds `baseline × threshold` (default `2.0`) **and** the baseline
   is at least `--min-abs` seconds (default `500us` in CI). The floor keeps
   sub-millisecond ops — where machine-to-machine variance dwarfs any real signal
   — reported but out of the pass/fail decision, so in practice the gate bites on
   the larger ops (writes, large payloads, listings) where an algorithmic
   regression actually shows. Only the **local** backend has a committed
   baseline, so only local ops are gated; Docker-backend cells run for
   correctness and land in the uploaded artifacts but are not timing-gated.

Regenerate the baseline from a green run: `pytest benchmarks/ --backend local
-m "not standard and not full" --benchmark-json=run.json`, then keep only
`name` / `params` / `stats.mean` per entry (the committed file is slimmed to
those fields to stay small). The scheduled run uploads the full run JSON and
text reports as `benchmark-results` artifacts (90-day retention).

### Run of record (published overhead story)

The numbers and charts on the [performance guide](../docs-src/explanation/performance.md)
are regenerated from a committed, diffable **run of record** —
`benchmarks/results/run-of-record/{clean,rtt20,rtt50,rtt100}.json` — so the
charts and `comparative.md` can be rebuilt from inputs in the repo (ID-230).

**Producing a fresh run of record (the reproducible path).** Dispatch
`benchmark.yml` with the **`run_of_record`** input checked. That job brings up
the full compose stack (Toxiproxy in front of the network backends), runs the
`clean` profile at the `standard` tier plus the `rtt20/rtt50/rtt100` matrix on
the `-latency` backends, regenerates `comparative.md` + the five SVGs, and
uploads them with the slimmed JSON as the **`run-of-record`** artifact. Download
that artifact and commit its files — CI never pushes to docs.

**Regenerating locally (or re-slimming a raw run).** With the compose stack up:

```bash
# 1. Run the clean + RTT matrix, capturing raw JSON per profile. These flags
#    MUST match the run-of-record job in .github/workflows/benchmark.yml — run
#    verbatim without them and the RTT loop trips the per-test watchdog:
#      * --bench-timeout=300 — standard-tier 10MB SFTP writes (~50s over
#        pytest-benchmark's rounds) flirt with the default 60s watchdog and can
#        trip a late KeyboardInterrupt that aborts the session.
#      * clean -k drops the s3fs/sshfs 10MB cells (no run-of-record chart plots
#        fsspec at 10MB). adlfs stays in — BUG-233 fixed its 10MB raw-bytes write.
#      * RTT -k restricts to the five overhead ops the chart reads; the pedantic
#        copy/move/streaming RS-only tests under latency otherwise exceed the
#        watchdog and trip the same fatal interrupt.
pytest benchmarks/ --benchmark-json=clean-raw.json \
  --backend local,s3,s3-pyarrow,sftp,azure -m "not full" --bench-timeout=300 \
  -k "not (10MB and (s3fs or sshfs))"
for p in rtt20 rtt50 rtt100; do
  pytest benchmarks/ --benchmark-json="$p-raw.json" \
    --backend s3-latency,sftp-latency,azure-latency --network-profile "$p" \
    --pool-size=20 --bench-timeout=300 -m "not standard and not full" \
    -k "test_write_bytes or test_read_bytes or test_exists_hit or test_list_files or (test_delete and not folder)"
done

# 2. Slim to the committed shape AND assert the three chart invariants below.
hatch run bench-run-of-record -- clean-raw.json rtt20-raw.json rtt50-raw.json rtt100-raw.json

# 3. Regenerate comparative.md + the five charts from the slimmed set.
python -m benchmarks.report --comparative --markdown \
  --file benchmarks/results/run-of-record/clean.json \
  --output benchmarks/results/comparative.md
python -m benchmarks.charts \
  --dir benchmarks/results/run-of-record \
  --file benchmarks/results/run-of-record/clean.json \
  --output-dir docs-src/img/benchmarks

# Re-guard the committed set at any time (no slimming):
hatch run bench-run-of-record -- --check-only
```

**Three invariants the slim/guard step enforces** — each guards a *silent*
failure mode where a wrong-shaped run ships a blank or placeholder chart with no
error:

1. **Profiles present.** The set carries `clean` plus at least one latency
   profile, so the two RTT charts (`overhead-vs-rtt.svg` and
   `overhead-decomposition.svg`) have `>= 2` profiles and do not render their
   placeholder.
2. **Latency files carry both sides of the ratio.** Each rtt file carries
   `s3-latency` / `sftp-latency` / `azure-latency` benchmarks for *both* the
   `remote_store` target and its paired raw SDK target, so `charts.py`'s
   `_LATENCY_VARIANT` lookup hits and the RTT charts (which subtract raw from
   remote_store) have both operands. A run that proxied the *base* backends, or
   captured only one side of the ratio, drops the series silently.
3. **Clean file carries the base comparative backends, both sides.** `s3` /
   `s3-pyarrow` / `sftp` / `azure` must have `remote_store` **and** paired
   raw-SDK data for the overhead ops, so the three single-file charts read a real
   remote_store cell (and its raw divisor) instead of blanking or omitting a
   backend. `bench-charts` must be run `--file …/clean.json`; without it it
   builds them from `files[-1]` (an rtt file) and blanks them.

**This slimming deliberately diverges from the baseline recipe above.** The
baseline is a single clean-profile file that never feeds the RTT chart, so it
drops the top-level `network_profile` key. The run of record **keeps it** per
file: `charts.py` groups profiles by that *in-file* field, not the filename.
Strip it and every file collapses to `clean`, and the RTT chart silently falls
back to its placeholder. `slim_run_of_record.py` retains `network_profile` +
`machine_info` for exactly this reason — do not copy the baseline recipe.

## Environment Variables

Local-infra host/port/credential defaults live in [`infra/.env`](../infra/.env)
(the single source of truth shared by docker-compose, Python conftests, and
CI workflows). Any value can be overridden for a single invocation by
exporting the same name in the shell, e.g.
`MINIO_HOST_PORT=12345 hatch run bench`.

Benchmark-specific knobs not in `infra/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCH_AZURE_MAX_CONCURRENCY` | 1 | Azure max concurrency |
| `BENCH_LARGE_FILE_MB` | 10 | Large-file test size (MB) |
| `BENCH_S3_BUCKET` | — | Cloud S3 bucket |
| `BENCH_AZURE_CONTAINER` | — | Cloud Azure container |
| `BENCH_SFTP_KEY_FILE` | — | Cloud SFTP key file |

## Adding a New Comparison Target

1. Create a class implementing `BenchTarget` in `benchmarks/targets/`:
   ```python
   from benchmarks.targets._protocol import BenchTarget

   class MyTarget(BenchTarget):
       @property
       def label(self) -> str:
           return "my_target"

       def write(self, path: str, data: bytes) -> None: ...
       def read(self, path: str) -> bytes: ...
       def exists(self, path: str) -> bool: ...
       def delete(self, path: str) -> None: ...
       def list_files(self, prefix: str) -> list[str]: ...
   ```

2. Add a `pytest.param` entry in `conftest.py:_build_target_params()`.

3. Wire up creation/cleanup in the `bench_target` fixture.

## File Structure

```
benchmarks/
  __init__.py
  conftest.py                    # fixtures, hooks, CLI, payload, cleanup
  targets/
    __init__.py
    _protocol.py                 # BenchTarget ABC
    _remote_store.py             # wraps Backend
    _raw_sdk.py                  # Boto3Raw, AzureBlobRaw, ParamikoRaw, PathLibRaw
    _fsspec.py                   # S3fs, Adlfs, Sshfs, LocalFsspec
  test_ttfb.py                   # remote-store only
  test_throughput.py              # comparative (write/read bytes)
  test_metadata.py                # comparative (exists) + RS-only (get_file_info)
  test_listing.py                 # comparative (flat) + RS-only (dir-scale, deep)
  test_destructive.py             # comparative (delete) + RS-only (copy, move)
  test_large_file.py              # remote-store only (memory tracking)
  _toxiproxy.py                    # Toxiproxy helpers, profiles, connection strings
  report.py                        # summary table generator (bench-report)
  results/
    comparative.md               # generated comparative data (checked in)
  README.md
```

The Docker compose stack and Toxiproxy configuration live at the
top-level [`infra/`](../infra/) — shared between benchmarks and the
test suite. Ports and credentials come from [`infra/.env`](../infra/.env).
