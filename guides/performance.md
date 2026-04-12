# Performance

remote-store wraps established Python storage libraries. This page presents
measured overhead so you can judge whether the abstraction cost matters for
your workloads.

## Overhead at a Glance

The chart below shows remote-store's overhead (%) versus raw SDK calls for
each backend. Negative values mean remote-store is *faster* than calling
the SDK directly (often due to connection pooling and caching).

![Abstraction overhead by backend](img/benchmarks/overhead.svg)

Patterns from Docker benchmarks (MinIO, Azurite, OpenSSH):

- **S3**: reads and writes add modest overhead over raw boto3; listing is
  significantly faster via s3fs connection caching.
- **S3-PyArrow**: reads carry more overhead than the S3 backend (PyArrow C++
  data path); writes are comparable. The trade-off is native PyArrow integration
  — Tier 1 C++ range requests — not raw throughput.
- **Azure** and **SFTP**: per-operation overhead is small relative to network
  round-trip time for most operations.
- **Local**: all operations are sub-millisecond; overhead versus raw pathlib is
  measurable but negligible for storage workloads.

Regenerate numbers for your own hardware with `hatch run bench-report`
(see [Running Benchmarks](#running-benchmarks)).

## What Happens Under Real Latency

Under realistic network round-trip times (20–100 ms), overhead as a percentage
shrinks. For example, a 1 ms overhead on a 100 ms round trip is 1%.

![Overhead vs RTT](img/benchmarks/overhead-vs-rtt.svg)

The benchmark suite simulates latency using [Toxiproxy](https://github.com/Shopify/toxiproxy)
with four named profiles:

| Profile | Latency | Jitter | Simulates |
|---------|---------|--------|-----------|
| `clean` | 0 ms | 0 ms | Baseline (passthrough) |
| `rtt20` | 20 ms | 7 ms | Same-region cloud |
| `rtt50` | 50 ms | 17 ms | Cross-region |
| `rtt100` | 100 ms | 33 ms | Cross-continent |

## Throughput by File Size

How throughput scales with file size, comparing remote-store to raw SDK:

![Throughput by file size](img/benchmarks/throughput.svg)

At larger file sizes, throughput converges as the fixed per-operation overhead
is amortized across more bytes.

## S3 vs S3-PyArrow

Both S3 backends connect to the same service. S3 uses s3fs (Python), S3-PyArrow
uses PyArrow's C++ `S3FileSystem` for data-path operations. The chart below
compares their absolute latencies:

![S3 vs S3-PyArrow](img/benchmarks/s3-comparison.svg)

S3-PyArrow reads are slower for sequential workloads because the C++ data path
adds connection management and metadata overhead per call. The S3-PyArrow
backend's advantage is native [PyArrow integration](pyarrow-adapter.md) — Tier 1
Parquet column pruning, I/O coalescing, and GIL-free reads. For sequential
byte streaming, the regular S3 backend is faster.

## Comparative Results

For every operation, the benchmark suite runs the same workload through three
interfaces:

1. **remote-store** — the `Backend` / `Store` API
2. **Raw SDK** — direct boto3/paramiko/azure-storage-blob/pathlib calls
3. **fsspec** — s3fs/sshfs/adlfs/fsspec.local

### Sample Results

Results vary by hardware, network, and service version. Generate numbers for
your environment with `hatch run bench-report` (summary) or
`hatch run bench-report-user` (condensed with verdicts).

For a full per-backend comparison of remote-store against the raw SDK and
fsspec, see the Detailed Comparative Tables section on the
[Performance page](https://docs.remotestore.dev/stable/performance/).

## Caveats

- **Docker emulators are not cloud.** Azurite, MinIO, and the local SFTP
  container approximate real services but have different performance
  characteristics. Treat these numbers as relative comparisons, not
  absolute predictions of cloud performance.
- **Listing anomalies.** Some fsspec implementations (s3fs, adlfs) show
  sub-100us listing times that reflect client-side caching, not real
  storage-layer performance. Similarly, raw boto3 listing without caching
  is slower than remote-store's cached s3fs path.
- **Delete overhead.** 2-3x vs raw SDK across all backends is expected
  from the error-mapping layer and not an optimization target.
- **Streaming reads keep memory constant** regardless of file size.

## Methodology

Benchmarks use [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
with Docker-hosted services (MinIO for S3, Azurite for Azure, OpenSSH for
SFTP). Each test runs in an isolated environment — fresh buckets, containers,
and directories are created per test fixture and cleaned up after.

| Metric | How | Where |
|--------|-----|-------|
| **Throughput** (MB/s) | payload_bytes / mean_time | Write, read, roundtrip |
| **TTFB** (ms) | Time to write/read 1KB file | Protocol overhead |
| **Latency** (ms) | Mean operation time | Exists, delete, list |
| **Memory** (MB) | tracemalloc peak | Large-file read/write |
| **Listing speed** | Time to list N files | 50, 200, 1k, 10k files |

## Running Benchmarks

```bash
# Start Docker services
docker compose -f benchmarks/infra/docker-compose.yml up -d --wait

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
docker compose -f benchmarks/infra/docker-compose.yml down -v
```

For cloud benchmarks, set the appropriate environment variables (see
`benchmarks/README.md` for the full reference table) and use `--infra cloud`.

## See also

- [Capabilities Matrix](capabilities-matrix.md) — feature support per backend
- [Choosing a Backend](choosing-a-backend.md) — decision guide with trade-offs
- [PyArrow Adapter](pyarrow-adapter.md) — tiered read strategy and S3 direct I/O
