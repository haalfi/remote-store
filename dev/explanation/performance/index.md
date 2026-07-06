# Performance

remote-store wraps established Python storage libraries. This page presents measured overhead so you can judge whether the abstraction cost matters for your workloads.

## Overhead at a Glance

The chart below shows remote-store's overhead (%) versus raw SDK calls for each backend. Negative values mean remote-store is *faster* than calling the SDK directly (often due to connection pooling and caching).

Patterns from Docker benchmarks (MinIO, Azurite, OpenSSH):

- **S3**: reads and writes add modest overhead over raw boto3; listing is significantly faster via s3fs connection caching.
- **S3-PyArrow**: reads carry more overhead than the S3 backend (PyArrow C++ data path); writes are comparable. The trade-off is native PyArrow integration — Tier 1 C++ range requests — not raw throughput.
- **Azure** and **SFTP**: per-operation overhead is small relative to network round-trip time for most operations.
- **Local**: all operations are sub-millisecond; overhead versus raw pathlib is measurable but negligible for storage workloads.

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

## Comparative Results

For every operation, the benchmark suite runs the same workload through three interfaces:

1. **remote-store** — the `Backend` / `Store` API
1. **Raw SDK** — direct boto3/paramiko/azure-storage-blob/pathlib calls
1. **fsspec** — s3fs/sshfs/adlfs/fsspec.local

### Sample Results

Results vary by hardware, network, and service version. Generate numbers for your environment with `hatch run bench-report` (summary) or `hatch run bench-report-user` (condensed with verdicts).

For a full per-backend comparison of remote-store against the raw SDK and fsspec, see the Detailed Comparative Tables section on the [Performance page](https://docs.remotestore.dev/stable/explanation/performance/).

## Caveats

- **Docker emulators are not cloud.** Azurite, MinIO, and the local SFTP container approximate real services but have different performance characteristics. Treat these numbers as relative comparisons, not absolute predictions of cloud performance.
- **Listing anomalies.** Some fsspec implementations (s3fs, adlfs) show sub-100us listing times that reflect client-side caching, not real storage-layer performance. `S3Backend` defaults this directory-listing cache off (fresh listings every call), so those sub-100us numbers appear only when the cache is explicitly re-enabled via `client_options={"use_listings_cache": True}`; with the default, the s3fs path issues a fresh listing like raw boto3.
- **Delete overhead.** 2-3x vs raw SDK across all backends is expected from the error-mapping layer and not an optimization target.
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
hatch run bench-report-user               # condensed with verdicts
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
| Write 1MB     | 646us        | 588us (1.1x faster) | 574us (1.1x faster) |
| Read 1MB      | 321us        | 249us (1.3x faster) | 259us (1.2x faster) |
| Exists (hit)  | 55us         | 5us (10.2x faster)  | 4us (14.2x faster)  |
| List 50 files | 661us        | 678us               | 143us (4.6x faster) |
| Delete        | 112us        | 38us (2.9x faster)  | 55us (2.0x faster)  |

### S3 (MinIO)

| Operation     | remote-store | boto3                | s3fs                 |
| ------------- | ------------ | -------------------- | -------------------- |
| Write 1MB     | 19.9ms       | 24.5ms (1.2x slower) | 23.8ms (1.2x slower) |
| Read 1MB      | 9.0ms        | 4.9ms (1.9x faster)  | 6.6ms (1.4x faster)  |
| Exists (hit)  | 1.5ms        | 1.3ms (1.1x faster)  | 1.3ms (1.1x faster)  |
| List 50 files | 168us        | 4.0ms (24.1x slower) | 89us (1.9x faster)   |
| Delete        | 3.1ms        | 1.5ms (2.1x faster)  | 1.7ms (1.9x faster)  |

### S3-PyArrow

| Operation     | remote-store | boto3                |
| ------------- | ------------ | -------------------- |
| Write 1MB     | 31.9ms       | 43.3ms (1.4x slower) |
| Read 1MB      | 11.5ms       | 4.8ms (2.4x faster)  |
| Exists (hit)  | 1.9ms        | 1.3ms (1.5x faster)  |
| List 50 files | 144us        | 4.0ms (27.6x slower) |
| Delete        | 4.5ms        | 1.5ms (3.0x faster)  |

### SFTP

| Operation     | remote-store | paramiko             | sshfs                |
| ------------- | ------------ | -------------------- | -------------------- |
| Write 1MB     | 29.6ms       | 29.5ms               | 14.3ms (2.1x faster) |
| Read 1MB      | 11.8ms       | 10.0ms (1.2x faster) | 7.2ms (1.6x faster)  |
| Exists (hit)  | 779us        | 397us (2.0x faster)  | 652us (1.2x faster)  |
| List 50 files | 2.5ms        | 2.1ms (1.2x faster)  | 3.0ms (1.2x slower)  |
| Delete        | 1.6ms        | 398us (4.1x faster)  | 1.2ms (1.4x faster)  |

### Azure

| Operation     | remote-store | azure-blob           | adlfs                |
| ------------- | ------------ | -------------------- | -------------------- |
| Write 1MB     | 15.6ms       | 14.1ms (1.1x faster) | 17.2ms (1.1x slower) |
| Read 1MB      | 5.7ms        | 5.7ms                | 10.2ms (1.8x slower) |
| Exists (hit)  | 1.7ms        | 1.6ms                | 1.9ms (1.1x slower)  |
| List 50 files | 9.6ms        | 9.1ms (1.1x faster)  | 66us (145.3x faster) |
| Delete        | 1.8ms        | 1.8ms                | 4.0ms (2.2x slower)  |

## See also

- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — feature support per backend
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — decision guide with trade-offs
- [PyArrow Adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — tiered read strategy and S3 direct I/O
