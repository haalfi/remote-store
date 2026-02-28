# Performance

remote-store includes a comprehensive benchmark suite that measures throughput,
latency, and memory usage across all backends. The suite also compares
remote-store against raw SDK calls and fsspec implementations.

## Methodology

Benchmarks use [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
with Docker-hosted services (MinIO for S3, Azurite for Azure, OpenSSH for SFTP).
Each test runs in an isolated environment -- fresh buckets, containers, and
directories are created per test fixture and cleaned up after.

### What We Measure

| Metric | How | Where |
|--------|-----|-------|
| **Throughput** (MB/s) | payload_bytes / mean_time | Write, read, roundtrip |
| **TTFB** (ms) | Time to write/read 1KB file | Protocol overhead |
| **Latency** (ms) | Mean operation time | Exists, delete, list |
| **Memory** (MB) | tracemalloc peak | Large-file read/write |
| **Listing speed** | Time to list N files | 50, 200, 1k, 10k files |

### Comparative Benchmarks

For operations where comparison is meaningful (write, read, exists, list, delete),
the suite runs the same operation through three interfaces:

1. **remote-store** -- the `Backend` API
2. **Raw SDK** -- direct boto3/paramiko/azure-storage-blob/pathlib calls
3. **fsspec** -- s3fs/sshfs/adlfs/fsspec.local

This quantifies the overhead remote-store adds on top of each SDK.

## Running Benchmarks

### Prerequisites

```bash
# Install benchmark dependencies
pip install remote-store[bench]

# Start Docker services
docker compose -f benchmarks/infra/docker-compose.yml up -d
```

### Commands

```bash
# Quick tier (~2 min/backend)
hatch run bench

# Standard tier (~5 min/backend, adds 10MB payload + deep hierarchy)
hatch run bench-standard

# Full tier (~20-30 min/backend, adds 100MB payload + 10k listing)
hatch run bench-full

# Filter to specific backends
hatch run bench -- --backend s3,sftp

# Save results as JSON
hatch run bench-save

# Compare against last saved run
hatch run bench-compare

# Run against real cloud services
hatch run bench-cloud

# Summary report from saved results
hatch run bench-report

# Comparative report (remote-store vs raw SDK vs fsspec)
hatch run bench-report-comparative

# Compare latest vs previous saved run
hatch run bench-report-compare

# Machine-readable JSON output
hatch run bench-report-json
```

### Sample Results

Results will vary by hardware and network. The following numbers were
measured on Windows 11 (Intel Core Ultra 7 265K, Python 3.13) with
Docker Desktop (MinIO, Azurite, OpenSSH) running locally. All values are
**mean** latency from `pytest-benchmark`.

| Operation | Local | S3 (MinIO) | S3-PyArrow | SFTP | Azure (Azurite) |
|-----------|-------|------------|------------|------|-----------------|
| Write 1KB | 0.26ms | 5.3ms | 36.2ms | 3.8ms | 5.0ms |
| Write 64KB | 0.26ms | 6.2ms | 66.5ms | 4.9ms | 22.6ms |
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

Generate this table from your own saved results with `hatch run bench-report`.

**Key observations:**

- Local backend is 20-100x faster than network backends (expected).
- S3-PyArrow writes are slow at small sizes (36ms for 1KB) due to PyArrow's
  single-part upload overhead. At 1MB the gap narrows (31.6ms vs 20.1ms for S3).
- S3-PyArrow reads are competitive with S3 (1.7ms vs 1.5ms at 1KB, 11.4ms vs
  5.9ms at 1MB) -- the RFC-0003 `BufferedReader` removal keeps overhead modest.
- SFTP read latency scales steeply with file size (3.0ms at 1KB, 13.5ms at 1MB).
- Azure listing is slowest (11.4ms for 50 files, 145ms for 1000) -- Azurite
  emulation overhead.
- S3 listing is faster than local for flat directories (pagination is efficient).
- Streaming reads keep memory constant regardless of file size.

## How remote-store Compares

For every comparative operation, the benchmark suite runs the same workload
through remote-store, the raw SDK, and the fsspec equivalent. Measured findings
from Docker benchmarks (MinIO, Azurite, OpenSSH):

- **Azure: near-zero overhead** -- remote-store matches the raw azure-blob SDK
  within measurement noise for writes, reads, and exists. adlfs is 1.9x slower
  for reads and 2.2x slower for deletes.
- **S3: competitive or faster for writes** -- Write 1MB is 1.5x faster than raw
  boto3 (20ms vs 30ms, likely due to s3fs connection pooling). Read overhead is
  ~15% (5.9ms vs 5.1ms). Exists within noise (1.4ms vs 1.3ms).
- **SFTP: moderate overhead** -- ~5% for writes and ~8% for reads vs raw
  paramiko. Metadata ops show ~2x overhead from error-mapping stat calls
  (exists 859us vs 413us, delete 988us vs 422us).
- **Local: expected abstraction cost** -- ~20% I/O overhead vs bare pathlib
  (484us vs 404us for Write 1MB). Metadata ops show higher relative overhead
  (exists 55us vs 5us), but absolute latencies are sub-millisecond.
- **Caveats:** listing anomalies exist in the comparative data -- some fsspec
  implementations (s3fs at 67us, adlfs at 83us for 50 files) show sub-100us
  listing times that likely reflect client-side caching in the test harness,
  not real-world performance (see ID-032). Delete overhead is 2-3x vs raw SDK
  across all backends, likely from error-mapping overhead on the delete path.

Regenerate for your hardware:

```bash
docker compose -f benchmarks/infra/docker-compose.yml up -d --wait
hatch run bench-save
hatch run bench-report-comparative-md
```

## Analyzing Results

Saved benchmark results (JSON) live in `.benchmarks/`. The
`examples/notebooks/benchmark_analysis.ipynb` notebook loads these files and
produces charts:

- **Throughput by backend**: bar chart comparing remote-store vs raw SDK vs fsspec
- **Throughput vs file size**: line chart showing scaling behavior
- **Listing latency vs file count**: bar chart at 50, 200, 1000 files
- **Peak memory vs file size**: scatter plot from tracemalloc data

## Reproducing

```bash
# 1. Start services
docker compose -f benchmarks/infra/docker-compose.yml up -d

# 2. Run and save
hatch run bench-save

# 3. Make changes

# 4. Run and compare
hatch run bench-compare

# 5. Stop services
docker compose -f benchmarks/infra/docker-compose.yml down -v
```

For cloud benchmarks, set the appropriate environment variables (see
`benchmarks/README.md` for the full reference table) and use `--infra cloud`.
