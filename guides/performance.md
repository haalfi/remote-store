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
# Quick run (excludes slow tests)
hatch run bench

# Full run (includes 10MB, 100MB payloads and 10k listing)
hatch run bench-full

# Save results as JSON
hatch run bench-save

# Compare against last saved run
hatch run bench-compare

# Run against real cloud services
hatch run bench-cloud
```

### Sample Results

Results will vary by hardware and network. Here is what to expect from a
local Docker run:

| Operation | Local | S3 (MinIO) | SFTP | Azure (Azurite) |
|-----------|-------|------------|------|-----------------|
| Write 1KB | ~0.2ms | ~5ms | ~10ms | ~8ms |
| Read 1KB | ~0.05ms | ~3ms | ~8ms | ~6ms |
| Exists (hit) | ~0.02ms | ~2ms | ~5ms | ~4ms |
| List 50 files | ~0.7ms | ~5ms | ~15ms | ~10ms |
| TTFB write | ~0.2ms | ~5ms | ~12ms | ~8ms |

**Key observations:**

- Local backend is 10-100x faster than network backends (expected).
- SFTP has the highest TTFB due to SSH handshake overhead.
- remote-store adds minimal overhead vs raw SDK for most operations.
  Run `hatch run bench` to measure the exact overhead in your environment.
- Streaming reads keep memory constant regardless of file size.

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
