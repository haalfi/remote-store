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

Runs against real cloud services. Set environment variables first:

```bash
# S3
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export BENCH_S3_BUCKET=my-bench-bucket

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

Runs the S3-family lanes (`s3`, `s3-boto3`) against an in-process
[moto](https://github.com/getmoto/moto) server. No Docker, no credentials, no
network: the server is started for the session and torn down after.

```bash
hatch run bench-moto -- --backend s3,s3-boto3
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

Read listing/metadata numbers with the cache in mind: s3fs serves repeated
`list_*` / `iter_children` calls from an in-process directory cache (fast, but
can be stale), whereas the boto3 lane issues a fresh `list_objects_v2` every
time (slower, always current). The benchmark surfaces that trade-off rather than
a pure speed verdict.

For a **cache-neutral** comparison, the `s3-nocache` lane is the s3fs
`S3Backend` built with `client_options={"use_listings_cache": False}` (the
ID-201 override): it issues a fresh listing every call, like the boto3 lane.
So `--backend s3-nocache,s3-boto3` isolates the listing *mechanism* (s3fs/
aiobotocore vs. boto3) with neither side cached, while `--backend s3,s3-nocache`
shows what the dircache is worth. Note the raw `s3fs` comparative target is
*not* cache-disabled — it represents s3fs as typically used.

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
| `hatch run bench-report-user` | Condensed report with verdicts | User-facing overview |
| `hatch run bench-charts` | Generate SVG charts from saved JSON | Docs charts |

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
