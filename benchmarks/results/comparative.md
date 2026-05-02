<!-- Generated 2026-04-12 14:54 UTC -->
<!-- Hardware: Intel(R) Core(TM) Ultra 7 265K, Python 3.13.11, Windows -->
<!-- doc: repo-only -->

### Local

| Operation | remote-store | pathlib | fsspec |
|-----------|-------:|-------:|-------:|
| Write 1MB | 646us | 588us (1.1x faster) | 574us (1.1x faster) |
| Read 1MB | 321us | 249us (1.3x faster) | 259us (1.2x faster) |
| Exists (hit) | 55us | 5us (10.2x faster) | 4us (14.2x faster) |
| List 50 files | 661us | 678us | 143us (4.6x faster) |
| Delete | 112us | 38us (2.9x faster) | 55us (2.0x faster) |

### S3 (MinIO)

| Operation | remote-store | boto3 | s3fs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 19.9ms | 24.5ms (1.2x slower) | 23.8ms (1.2x slower) |
| Read 1MB | 9.0ms | 4.9ms (1.9x faster) | 6.6ms (1.4x faster) |
| Exists (hit) | 1.5ms | 1.3ms (1.1x faster) | 1.3ms (1.1x faster) |
| List 50 files | 168us | 4.0ms (24.1x slower) | 89us (1.9x faster) |
| Delete | 3.1ms | 1.5ms (2.1x faster) | 1.7ms (1.9x faster) |

### S3-PyArrow

| Operation | remote-store | boto3 |
|-----------|-------:|-------:|
| Write 1MB | 31.9ms | 43.3ms (1.4x slower) |
| Read 1MB | 11.5ms | 4.8ms (2.4x faster) |
| Exists (hit) | 1.9ms | 1.3ms (1.5x faster) |
| List 50 files | 144us | 4.0ms (27.6x slower) |
| Delete | 4.5ms | 1.5ms (3.0x faster) |

### SFTP

| Operation | remote-store | paramiko | sshfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 29.6ms | 29.5ms | 14.3ms (2.1x faster) |
| Read 1MB | 11.8ms | 10.0ms (1.2x faster) | 7.2ms (1.6x faster) |
| Exists (hit) | 779us | 397us (2.0x faster) | 652us (1.2x faster) |
| List 50 files | 2.5ms | 2.1ms (1.2x faster) | 3.0ms (1.2x slower) |
| Delete | 1.6ms | 398us (4.1x faster) | 1.2ms (1.4x faster) |

### Azure

| Operation | remote-store | azure-blob | adlfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 15.6ms | 14.1ms (1.1x faster) | 17.2ms (1.1x slower) |
| Read 1MB | 5.7ms | 5.7ms | 10.2ms (1.8x slower) |
| Exists (hit) | 1.7ms | 1.6ms | 1.9ms (1.1x slower) |
| List 50 files | 9.6ms | 9.1ms (1.1x faster) | 66us (145.3x faster) |
| Delete | 1.8ms | 1.8ms | 4.0ms (2.2x slower) |
