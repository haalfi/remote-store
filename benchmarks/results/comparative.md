<!-- Generated 2026-07-16 18:11 UTC -->
<!-- Hardware: AMD EPYC 7763 64-Core Processor, Python 3.13.14, Linux -->
<!-- doc: repo-only -->

### Local

| Operation | remote-store | pathlib | fsspec |
|-----------|-------:|-------:|-------:|
| Write 1MB | 455us | 732us (1.6x slower) | 347us (1.3x faster) |
| Read 1MB | 140us | 64us (2.2x faster) | 67us (2.1x faster) |
| Exists (hit) | 75us | 10us (7.5x faster) | 7us (10.7x faster) |
| List 50 files | 1.0ms | 1.3ms (1.3x slower) | 106us (9.7x faster) |
| Delete | 104us | 28us (3.7x faster) | 24us (4.3x faster) |

### S3 (MinIO)

| Operation | remote-store | boto3 | s3fs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 10.8ms | 8.3ms (1.3x faster) | 9.0ms (1.2x faster) |
| Read 1MB | 5.4ms | 3.3ms (1.7x faster) | 5.5ms |
| Exists (hit) | 2.0ms | 1.9ms (1.1x faster) | 2.1ms |
| List 50 files | 372us | 8.5ms (22.9x slower) | 176us (2.1x faster) |
| Delete | 4.7ms | 2.5ms (1.9x faster) | 2.3ms (2.1x faster) |

### S3-PyArrow

| Operation | remote-store | boto3 |
|-----------|-------:|-------:|
| Write 1MB | 12.9ms | 8.5ms (1.5x faster) |
| Read 1MB | 7.0ms | 3.0ms (2.3x faster) |
| Exists (hit) | 2.0ms | 2.0ms |
| List 50 files | 8.9ms | 8.8ms |
| Delete | 4.8ms | 2.3ms (2.0x faster) |

### SFTP

| Operation | remote-store | paramiko | sshfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 887ms | 885ms | 17.8ms (50.0x faster) |
| Read 1MB | 51.4ms | 50.0ms | 14.6ms (3.5x faster) |
| Exists (hit) | 705us | 352us (2.0x faster) | 787us (1.1x slower) |
| List 50 files | 3.9ms | 3.4ms (1.2x faster) | 4.0ms |
| Delete | 1.4ms | 366us (3.8x faster) | 1.4ms |

### Azure

| Operation | remote-store | azure-blob | adlfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 10.8ms | 11.1ms | 16.3ms (1.5x slower) |
| Read 1MB | 5.8ms | 6.0ms | 12.3ms (2.1x slower) |
| Exists (hit) | 2.3ms | 2.3ms | 2.4ms |
| List 50 files | 19.1ms | 29.6ms (1.6x slower) | 167us (114.5x faster) |
| Delete | 2.6ms | 2.4ms (1.1x faster) | 7.4ms (2.8x slower) |
