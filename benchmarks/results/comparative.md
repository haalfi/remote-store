<!-- Generated 2026-03-07 09:59 UTC -->
<!-- Hardware: Intel(R) Core(TM) Ultra 7 265K, Python 3.13.11, Windows -->

### Local

| Operation | remote-store | pathlib | fsspec |
|-----------|-------:|-------:|-------:|
| Write 1MB | 473us | 481us | 404us (1.2x faster) |
| Read 1MB | 311us | 248us (1.3x faster) | 247us (1.3x faster) |
| Exists (hit) | 55us | 5us (10.1x faster) | 4us (13.8x faster) |
| List 50 files | 659us | 666us | 146us (4.5x faster) |
| Delete | 106us | 49us (2.2x faster) | 66us (1.6x faster) |

### S3 (MinIO)

| Operation | remote-store | boto3 | s3fs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 18.7ms | 31.6ms (1.7x slower) | 17.4ms (1.1x faster) |
| Read 1MB | 6.4ms | 5.3ms (1.2x faster) | 6.7ms (1.1x slower) |
| Exists (hit) | 1.4ms | 1.3ms (1.1x faster) | 1.4ms |
| List 50 files | 256us | 4.5ms (17.6x slower) | 112us (2.3x faster) |
| Delete | 3.3ms | 1.6ms (2.1x faster) | 1.8ms (1.9x faster) |

### SFTP

| Operation | remote-store | paramiko | sshfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 26.2ms | 24.3ms (1.1x faster) | 13.5ms (1.9x faster) |
| Read 1MB | 12.1ms | 12.8ms (1.1x slower) | 8.2ms (1.5x faster) |
| Exists (hit) | 841us | 381us (2.2x faster) | 691us (1.2x faster) |
| List 50 files | 2.5ms | 2.0ms (1.3x faster) | 3.3ms (1.3x slower) |
| Delete | 1.1ms | 384us (3.0x faster) | 1.3ms (1.1x slower) |

### Azure

| Operation | remote-store | azure-blob | adlfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 13.0ms | 14.9ms (1.1x slower) | 17.1ms (1.3x slower) |
| Read 1MB | 5.7ms | 5.9ms | 10.6ms (1.8x slower) |
| Exists (hit) | 1.7ms | 1.7ms | 1.8ms (1.1x slower) |
| List 50 files | 10.5ms | 8.7ms (1.2x faster) | 83us (126.6x faster) |
| Delete | 1.7ms | 1.7ms | 4.4ms (2.7x slower) |
