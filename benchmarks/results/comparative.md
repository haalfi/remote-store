<!-- Generated 2026-07-19 14:02 UTC -->
<!-- Hardware: AMD EPYC 9V74 80-Core Processor, Python 3.13.14, Linux -->
<!-- doc: repo-only -->

### Local

| Operation | remote-store | pathlib | fsspec |
|-----------|-------:|-------:|-------:|
| Write 1MB | 383us | 685us (1.8x slower) | 455us (1.2x slower) |
| Read 1MB | 135us | 74us (1.8x faster) | 77us (1.7x faster) |
| Exists (hit) | 62us | 10us (6.4x faster) | 7us (8.9x faster) |
| List 50 files | 953us | 1.2ms (1.3x slower) | 105us (9.1x faster) |
| Delete | 80us | 24us (3.3x faster) | 23us (3.5x faster) |

### S3 (MinIO)

| Operation | remote-store | boto3 | s3fs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 12.5ms | 9.3ms (1.3x faster) | 10.6ms (1.2x faster) |
| Read 1MB | 5.7ms | 3.1ms (1.8x faster) | 5.5ms |
| Exists (hit) | 2.2ms | 1.9ms (1.1x faster) | 2.0ms (1.1x faster) |
| List 50 files | 302us | 7.7ms (25.6x slower) | 123us (2.5x faster) |
| Delete | 4.6ms | 2.2ms (2.1x faster) | 2.3ms (2.0x faster) |

### S3-PyArrow

| Operation | remote-store | boto3 |
|-----------|-------:|-------:|
| Write 1MB | 14.3ms | 9.4ms (1.5x faster) |
| Read 1MB | 6.8ms | 3.1ms (2.2x faster) |
| Exists (hit) | 2.0ms | 2.1ms (1.1x slower) |
| List 50 files | 8.5ms | 7.7ms (1.1x faster) |
| Delete | 4.9ms | 2.1ms (2.3x faster) |

### SFTP

| Operation | remote-store | paramiko | sshfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 890ms | 890ms | 14.6ms (61.0x faster) |
| Read 1MB | 48.6ms | 46.6ms | 11.2ms (4.3x faster) |
| Exists (hit) | 294us | 297us | 662us (2.3x slower) |
| List 50 files | 3.4ms | 3.2ms (1.1x faster) | 3.8ms (1.1x slower) |
| Delete | 329us | 329us | 1.3ms (3.8x slower) |

### Azure

| Operation | remote-store | azure-blob | adlfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 10.9ms | 11.0ms | 15.5ms (1.4x slower) |
| Read 1MB | 5.7ms | 5.8ms | 12.4ms (2.2x slower) |
| Exists (hit) | 2.6ms | 2.5ms | 2.5ms |
| List 50 files | 18.6ms | 29.9ms (1.6x slower) | 162us (114.9x faster) |
| Delete | 2.5ms | 2.6ms | 8.2ms (3.3x slower) |
