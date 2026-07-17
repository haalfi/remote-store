# Performance

remote-store wraps established Python storage libraries. This page presents the **measured** overhead of that wrapper and the levers to test it against your own workload. It does not tell you whether the overhead is acceptable — that depends on your call volume, latency budget, and alternatives, so it is your call, not the library's.

The overhead is a **fixed per-operation cost**. Its size in isolation is what the numbers below report; whether it is worth paying is a function of how much of your total time is spent in storage calls versus network round-trips. As network round-trip time grows, a fixed per-op cost shrinks as a *share* of total time (see [What Happens Under Real Latency](#what-happens-under-real-latency)). To measure it for your own hardware and latency, use the levers in [Running Benchmarks](#running-benchmarks) — the `hatch run bench-*` commands and the four `--network-profile` profiles.

## Overhead at a Glance

The chart below shows remote-store's overhead (%) versus raw SDK calls for each backend. Negative values mean remote-store is *faster* than calling the SDK directly (often due to connection pooling and caching).

Patterns from Docker benchmarks (MinIO, Azurite, OpenSSH):

- **S3**: reads and writes add modest overhead over raw boto3; listing is significantly faster via s3fs connection caching.
- **S3-PyArrow**: reads carry more overhead than the S3 backend (PyArrow C++ data path); writes are comparable. The trade-off is native PyArrow integration — Tier 1 C++ range requests — not raw throughput.
- **Azure** and **SFTP**: per-operation overhead is a fixed cost added on top of each call; as a share of total time it shrinks as network round-trip time grows (quantified in the next section).
- **Local**: all operations are sub-millisecond; overhead versus raw pathlib is a fixed sub-millisecond cost per call. Whether that registers depends on your call volume and how much of your latency budget is local I/O.

Regenerate numbers for your own hardware with `hatch run bench-report` (see [Running Benchmarks](#running-benchmarks)).

## What Happens Under Real Latency

Under realistic network round-trip times (20–100 ms), overhead as a percentage shrinks. For example, a 1 ms overhead on a 100 ms round trip is 1%.

The benchmark suite simulates latency using [Toxiproxy](https://github.com/Shopify/toxiproxy) with four named profiles:

| Profile  | Latency | Jitter | Simulates              |
| -------- | ------- | ------ | ---------------------- |
| `clean`  | 0 ms    | 0 ms   | Baseline (passthrough) |
| `rtt20`  | 20 ms   | 7 ms   | Same-region cloud      |
| `rtt50`  | 50 ms   | 17 ms  | Cross-region           |
| `rtt100` | 100 ms  | 33 ms  | Cross-continent        |

## Throughput by File Size

How throughput scales with file size, comparing remote-store to raw SDK:

At larger file sizes, throughput converges as the fixed per-operation overhead is amortized across more bytes.

## S3 vs S3-PyArrow

Both S3 backends connect to the same service. S3 uses s3fs (Python), S3-PyArrow uses PyArrow's C++ `S3FileSystem` for data-path operations. The chart below compares their absolute latencies:

S3-PyArrow reads are slower for sequential workloads because the C++ data path adds connection management and metadata overhead per call. The S3-PyArrow backend's advantage is native [PyArrow integration](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — Tier 1 Parquet column pruning, I/O coalescing, and GIL-free reads. For sequential byte streaming, the regular S3 backend is faster.

## Practical Takeaways

These follow from the numbers above. Whether the overhead is acceptable for *your* workload is still your call — measure it (see [Running Benchmarks](#running-benchmarks)).

- **Overhead is per operation, not per byte.** It shows up across many small calls (exists, metadata, small reads/writes, listings) and fades on larger transfers, where it is spread across more bytes.
- **As round-trip time grows, the fixed cost is a smaller share of each call.** At 20–100 ms RTT a per-operation cost of a few milliseconds or less is a low fraction of total call time (1 ms on a 100 ms round trip is 1%).
- **Workload shape drives the impact.** The same fixed cost is a large share of a sub-millisecond local `exists` and a small share of a 100 MB transfer, so call-heavy patterns feel it more than bulk I/O.
- **Throughput converges with file size.** Larger files approach raw-SDK throughput as the fixed per-operation cost is amortized across more bytes.
- **Measure, then reduce call count where it matters.** Benchmark your own workload with `hatch run bench-*` and the `--network-profile` profiles; batch or cache calls if the per-operation cost dominates your access pattern.

## Comparative Results

For every operation, the benchmark suite runs the same workload through three interfaces:

1. **remote-store** — the `Backend` / `Store` API
1. **Raw SDK** — direct boto3/paramiko/azure-storage-blob/pathlib calls
1. **fsspec** — s3fs/sshfs/adlfs/fsspec.local

### Sample Results

Results vary by hardware, network, and service version. Generate numbers for your environment with `hatch run bench-report` (summary) or `hatch run bench-report-user` (condensed, with magnitude bands).

For a full per-backend comparison of remote-store against the raw SDK and fsspec, see the Detailed Comparative Tables section on the [Performance page](https://docs.remotestore.dev/stable/explanation/performance/).

## Caveats

- **Docker emulators are not cloud.** Azurite, MinIO, and the local SFTP container approximate real services but have different performance characteristics. Treat these numbers as relative comparisons, not absolute predictions of cloud performance.
- **Listing anomalies.** Some fsspec implementations (s3fs, adlfs) show sub-100us listing times that reflect client-side caching, not real storage-layer performance. `S3Backend` defaults this directory-listing cache off (fresh listings every call), so those sub-100us numbers appear only when the cache is explicitly re-enabled via `client_options={"use_listings_cache": True}`; with the default, the s3fs path issues a fresh listing like raw boto3.
- **Delete overhead.** 2-3x vs raw SDK across all backends is expected from the error-mapping layer and not an optimization target.
- **SFTP write throughput is an emulator artifact.** On the Docker OpenSSH container, a 1MB SFTP write takes hundreds of milliseconds — far slower than the same write via `sshfs` or against a real server — because the paramiko transport issues many small, unpipelined SFTP write packets over the local container. remote-store and raw paramiko land within a few percent of each other on that row, so the *overhead* the chart reports is right; the absolute SFTP write throughput is not representative of a tuned or cloud SFTP endpoint. Measure your own server with `hatch run bench-cloud`.
- **Streaming reads keep memory constant** regardless of file size.

## Methodology

Benchmarks use [pytest-benchmark](https://pytest-benchmark.readthedocs.io/) with Docker-hosted services (MinIO for S3, Azurite for Azure, OpenSSH for SFTP). Each test runs in an isolated environment — fresh buckets, containers, and directories are created per test fixture and cleaned up after.

| Metric                | How                         | Where                  |
| --------------------- | --------------------------- | ---------------------- |
| **Throughput** (MB/s) | payload_bytes / mean_time   | Write, read, roundtrip |
| **TTFB** (ms)         | Time to write/read 1KB file | Protocol overhead      |
| **Latency** (ms)      | Mean operation time         | Exists, delete, list   |
| **Memory** (MB)       | tracemalloc peak            | Large-file read/write  |
| **Listing speed**     | Time to list N files        | 50, 200, 1k, 10k files |

## Running Benchmarks

```
# Start Docker services
docker compose -f infra/docker-compose.yml up -d --wait

# Quick tier (~2 min/backend)
hatch run bench

# Standard tier (~5 min/backend)
hatch run bench-standard

# Full tier (~20-30 min/backend)
hatch run bench-full

# With simulated latency (single profile)
hatch run bench -- --backend s3-latency,sftp-latency,azure-latency --network-profile rtt50

# Latency matrix (runs rtt20, rtt50, rtt100 sequentially, ~8 min/profile)
hatch run bench-latency-matrix

# Save results as JSON
hatch run bench-save

# Reports
hatch run bench-report                    # summary table
hatch run bench-report-user               # condensed, with magnitude bands
hatch run bench-report-comparative        # remote-store vs raw SDK vs fsspec
hatch run bench-charts                    # generate SVG charts

# Stop services
docker compose -f infra/docker-compose.yml down -v
```

For cloud benchmarks, set the appropriate environment variables (see `benchmarks/README.md` for the full reference table) and use `--infra cloud`.

## Detailed Comparative Tables

Per-backend tables comparing remote-store, raw SDK, and fsspec for each operation. Generated with `hatch run bench-report-comparative-md`.

### Local

| Operation     | remote-store | pathlib             | fsspec              |
| ------------- | ------------ | ------------------- | ------------------- |
| Write 1MB     | 455us        | 732us (1.6x slower) | 347us (1.3x faster) |
| Read 1MB      | 140us        | 64us (2.2x faster)  | 67us (2.1x faster)  |
| Exists (hit)  | 75us         | 10us (7.5x faster)  | 7us (10.7x faster)  |
| List 50 files | 1.0ms        | 1.3ms (1.3x slower) | 106us (9.7x faster) |
| Delete        | 104us        | 28us (3.7x faster)  | 24us (4.3x faster)  |

### S3 (MinIO)

| Operation     | remote-store | boto3                | s3fs                |
| ------------- | ------------ | -------------------- | ------------------- |
| Write 1MB     | 10.8ms       | 8.3ms (1.3x faster)  | 9.0ms (1.2x faster) |
| Read 1MB      | 5.4ms        | 3.3ms (1.7x faster)  | 5.5ms               |
| Exists (hit)  | 2.0ms        | 1.9ms (1.1x faster)  | 2.1ms               |
| List 50 files | 372us        | 8.5ms (22.9x slower) | 176us (2.1x faster) |
| Delete        | 4.7ms        | 2.5ms (1.9x faster)  | 2.3ms (2.1x faster) |

### S3-PyArrow

| Operation     | remote-store | boto3               |
| ------------- | ------------ | ------------------- |
| Write 1MB     | 12.9ms       | 8.5ms (1.5x faster) |
| Read 1MB      | 7.0ms        | 3.0ms (2.3x faster) |
| Exists (hit)  | 2.0ms        | 2.0ms               |
| List 50 files | 8.9ms        | 8.8ms               |
| Delete        | 4.8ms        | 2.3ms (2.0x faster) |

### SFTP

| Operation     | remote-store | paramiko            | sshfs                 |
| ------------- | ------------ | ------------------- | --------------------- |
| Write 1MB     | 887ms        | 885ms               | 17.8ms (50.0x faster) |
| Read 1MB      | 51.4ms       | 50.0ms              | 14.6ms (3.5x faster)  |
| Exists (hit)  | 705us        | 352us (2.0x faster) | 787us (1.1x slower)   |
| List 50 files | 3.9ms        | 3.4ms (1.2x faster) | 4.0ms                 |
| Delete        | 1.4ms        | 366us (3.8x faster) | 1.4ms                 |

### Azure

| Operation     | remote-store | azure-blob           | adlfs                 |
| ------------- | ------------ | -------------------- | --------------------- |
| Write 1MB     | 10.8ms       | 11.1ms               | 16.3ms (1.5x slower)  |
| Read 1MB      | 5.8ms        | 6.0ms                | 12.3ms (2.1x slower)  |
| Exists (hit)  | 2.3ms        | 2.3ms                | 2.4ms                 |
| List 50 files | 19.1ms       | 29.6ms (1.6x slower) | 167us (114.5x faster) |
| Delete        | 2.6ms        | 2.4ms (1.1x faster)  | 7.4ms (2.8x slower)   |

## See also

- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — feature support per backend
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — decision guide with trade-offs
- [PyArrow Adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — tiered read strategy and S3 direct I/O
