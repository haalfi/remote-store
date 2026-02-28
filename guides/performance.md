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

| Operation | Local | S3 (MinIO) | SFTP | Azure (Azurite) |
|-----------|-------|------------|------|-----------------|
| Write 1KB | 0.32ms | 6.2ms | 4.1ms | 5.5ms |
| Write 1MB | 0.50ms | 18.4ms | 24.4ms | 15.6ms |
| Read 1KB | 0.08ms | 1.6ms | 2.8ms | 2.2ms |
| Read 1MB | 0.39ms | 5.9ms | 12.7ms | 6.0ms |
| Exists (hit) | 0.06ms | 1.6ms | 0.82ms | 1.7ms |
| List 50 files | 0.67ms | 0.22ms | 2.6ms | 12.8ms |
| List 1000 files | 10.3ms | 1.7ms | 16.6ms | 162ms |
| Delete | 0.10ms | 3.5ms | 0.86ms | 1.6ms |
| TTFB write | 0.38ms | 9.8ms | 6.0ms | 7.8ms |
| TTFB read | 0.13ms | 3.4ms | 1.9ms | 2.0ms |

Generate this table from your own saved results with `hatch run bench-report`.

**Key observations:**

- Local backend is 20-80x faster than network backends (expected).
- S3 (MinIO) has the highest TTFB write (~10ms) due to multipart upload setup.
- SFTP read latency scales steeply with file size (2.8ms at 1KB, 12.7ms at 1MB).
- Azure listing is slowest (12.8ms for 50 files, 162ms for 1000) -- Azurite
  emulation overhead.
- S3 listing is faster than local for flat directories (pagination is efficient).
- remote-store adds minimal overhead vs raw SDK for most operations.
  Run `hatch run bench` to measure the exact overhead in your environment.
- Streaming reads keep memory constant regardless of file size.

## How remote-store Compares

For every comparative operation, the benchmark suite runs the same workload
through remote-store, the raw SDK, and the fsspec equivalent. Key findings:

- **vs raw SDK:** Overhead is typically under 5% for data-path operations
  and under 10% for metadata. The abstraction cost is negligible vs network
  latency for all remote backends.
- **vs fsspec:** remote-store is consistently faster. The gap is largest for
  S3 writes (s3fs multipart overhead) and Azure listing (adlfs directory
  emulation). See the full comparison on the
  [docs site](https://haalfi.github.io/remote-store/performance/).

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
