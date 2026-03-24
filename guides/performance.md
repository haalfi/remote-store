# Performance

remote-store wraps established Python storage libraries. The abstraction adds
measurable overhead for fast local operations, but for remote backends under
realistic network latency, the cost is typically small relative to network and
service time.

## Overhead at a Glance

The chart below shows remote-store's overhead (%) versus raw SDK calls for
each backend. Negative values mean remote-store is *faster* than calling
the SDK directly (often due to connection pooling and caching).

![Abstraction overhead by backend](img/benchmarks/overhead.svg)

**Verdicts from Docker benchmarks** (MinIO, Azurite, OpenSSH):

- **S3**: Writes are 1.2x *faster* than raw boto3 (connection reuse). Reads
  +22%, exists negligible, listing 18x faster (s3fs cache). Delete +2x
  (error-mapping layer).
- **Azure**: Writes 1.2x *faster* than raw azure-blob. Reads, exists, delete
  all within noise.
- **SFTP**: Writes +7%, reads +8%. Metadata ops show higher relative overhead
  (exists +133%) but absolute latencies are sub-millisecond.
- **Local**: Sub-millisecond for all operations. Higher relative overhead on
  metadata (exists: 63us vs 6us) but absolute cost is negligible.

## What Happens Under Real Latency

Under realistic network round-trip times (20--100ms), the abstraction overhead
collapses into the noise. A 1ms overhead on a 100ms round trip is 1% — invisible.

![Overhead vs network latency](img/benchmarks/overhead-vs-rtt.svg)

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

At larger file sizes, throughput converges — the per-operation overhead is
amortized across more bytes.

## Comparative Results

For every operation, the benchmark suite runs the same workload through three
interfaces:

1. **remote-store** — the `Backend` / `Store` API
2. **Raw SDK** — direct boto3/paramiko/azure-storage-blob/pathlib calls
3. **fsspec** — s3fs/sshfs/adlfs/fsspec.local

### Sample Results

Results vary by hardware and network. The following were measured on Windows 11
(Intel Core Ultra 7 265K, Python 3.13) with Docker Desktop running locally. All
values are **mean** latency from `pytest-benchmark`.

| Operation | [Local](backends/local.md) | [S3](backends/s3.md) (MinIO) | [S3-PyArrow](backends/s3-pyarrow.md) | [SFTP](backends/sftp.md) | [Azure](backends/azure.md) (Azurite) |
|-----------|-------|------------|------------|------|-----------------|
| Write 1KB | 0.26ms | 5.3ms | 36.2ms | 3.8ms | 5.0ms |
| Write 64KB | 0.26ms | 6.2ms | 66.5ms* | 4.9ms | 22.6ms* |
| Write 1MB | 0.48ms | 20.1ms | 31.6ms | 24.7ms | 13.7ms |
| Read 1KB | 0.09ms | 1.5ms | 1.7ms | 3.0ms | 2.0ms |
| Read 64KB | 0.09ms | 1.8ms | 2.2ms | 3.3ms | 2.3ms |
| Read 1MB | 0.32ms | 5.9ms | 11.4ms | 13.5ms | 5.8ms |
| Exists (hit) | 0.06ms | 1.4ms | 1.5ms | 0.86ms | 1.7ms |
| Exists (miss) | 0.07ms | 2.5ms | 2.9ms | 1.1ms | 3.5ms |
| List 50 files | 0.70ms | 0.24ms | 0.32ms | 2.8ms | 11.4ms |
| List 1000 files | 10.2ms | 1.5ms | 1.3ms | 16.2ms | 145ms |
| Delete | 0.11ms | 3.4ms | 4.7ms | 0.99ms | 1.8ms |
| TTFB write | 0.26ms | 8.4ms | 19.7ms | 7.2ms | 7.6ms |
| TTFB read | 0.11ms | 3.1ms | 1.9ms | 2.5ms | 2.2ms |
| TTFB exists | 0.06ms | 1.4ms | 1.4ms | 1.1ms | 1.8ms |

*\* 64KB write values for S3-PyArrow and Azure are outlier-skewed (high
variance, stddev > mean). The medians are monotonic. This is a
Dockerized-service cold-start artifact, not real non-monotonic performance.*

Generate this table from your own saved results with `hatch run bench-report`.
For a condensed view with verdicts, use `hatch run bench-report-user`.

## Caveats

- **Docker emulators are not cloud.** Azurite, MinIO, and the local SFTP
  container approximate real services but have different performance
  characteristics. Treat these numbers as relative comparisons, not
  absolute predictions of cloud performance.
- **Listing anomalies.** Some fsspec implementations (s3fs, adlfs) show
  sub-100us listing times that reflect client-side caching, not real
  storage-layer performance. Similarly, raw boto3 listing without caching
  is slower than remote-store's cached s3fs path.
- **Delete overhead.** 2--3x vs raw SDK across all backends is expected
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

# With simulated latency
hatch run bench -- --backend s3-latency,sftp-latency,azure-latency --network-profile rtt50

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
