# Benchmark Suite

Performance benchmarks for remote-store backends, comparing remote-store,
raw SDK calls, and fsspec implementations.

## Quick Start

```bash
# Start Docker services
docker compose -f benchmarks/infra/docker-compose.yml up -d

# Run benchmarks (excludes slow tests)
hatch run bench

# Save results for later comparison
hatch run bench-save

# Compare against previous run
hatch run bench-compare
```

## Backend Matrix

| Backend | Docker Service | Remote-Store | Raw SDK | fsspec |
|---------|---------------|-------------|---------|--------|
| Local | - | LocalBackend | pathlib | fsspec.local |
| S3 | MinIO :9000 | S3Backend | boto3 | s3fs |
| S3-PyArrow | MinIO :9000 | S3PyArrowBackend | - | - |
| SFTP | OpenSSH :2222 | SFTPBackend | paramiko | sshfs |
| Azure | Azurite :10000 | AzureBackend | azure-storage-blob | adlfs |

## Scenarios

### Comparative (remote-store vs raw SDK vs fsspec)
- **Write throughput** -- bytes payloads (1KB, 64KB, 1MB, 10MB, 100MB)
- **Read throughput** -- bytes payloads
- **Exists** -- hit and miss
- **List files** -- flat (50 and 1000 files)
- **Delete** -- single file

### Remote-store only
- **TTFB** -- time-to-first-byte (protocol overhead)
- **Stream write/read** -- BinaryIO interface
- **Roundtrip** -- write + read
- **Copy/move** -- single file and across subtrees
- **Directory scale** -- 200-file hierarchy listing, folder ops
- **Large file** -- 10MB+ with memory tracking (tracemalloc)
- **Per-folder stats** -- iterate folders + get_folder_info
- **Deep hierarchy** -- 5 levels, branching factor 5

## Docker vs Cloud

### Docker mode (default)

Uses local Docker containers. No credentials needed.

```bash
docker compose -f benchmarks/infra/docker-compose.yml up -d
hatch run bench
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

## Fast vs Full Runs

| Command | What runs | Use case |
|---------|-----------|----------|
| `hatch run bench` | All non-slow tests | Quick feedback |
| `hatch run bench-full` | All tests including slow | Pre-release, CI |
| `hatch run bench-save` | Non-slow + save JSON | Track regressions |
| `hatch run bench-compare` | Compare saved runs | Before/after |
| `hatch run bench-cloud` | Non-slow on real infra | Cloud perf testing |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCH_MINIO_HOST` | 127.0.0.1 | MinIO host |
| `BENCH_MINIO_PORT` | 9000 | MinIO port |
| `BENCH_MINIO_ACCESS_KEY` | minioadmin | MinIO access key |
| `BENCH_MINIO_SECRET_KEY` | minioadmin | MinIO secret key |
| `BENCH_AZURITE_HOST` | 127.0.0.1 | Azurite host |
| `BENCH_AZURITE_PORT` | 10000 | Azurite Blob port |
| `BENCH_SFTP_HOST` | 127.0.0.1 | SFTP host |
| `BENCH_SFTP_PORT` | 2222 | SFTP port |
| `BENCH_SFTP_USER` | benchuser | SFTP username |
| `BENCH_SFTP_PASS` | benchpass | SFTP password |
| `BENCH_LARGE_FILE_MB` | 10 | Large-file test size (MB) |
| `BENCH_S3_BUCKET` | - | Cloud S3 bucket |
| `BENCH_AZURE_CONTAINER` | - | Cloud Azure container |
| `BENCH_SFTP_KEY_FILE` | - | Cloud SFTP key file |

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
  infra/
    docker-compose.yml
  README.md
```
