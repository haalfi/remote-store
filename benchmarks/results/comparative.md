<!-- Generated 2026-02-28 from Docker benchmarks (MinIO, Azurite, OpenSSH) -->
<!-- Hardware: Intel(R) Core(TM) Ultra 7 265K, Python 3.13.11, Windows -->
<!-- NOTE: Listing numbers below pre-date the ID-032 cache-invalidation fix. -->
<!-- Re-run benchmarks to get updated numbers without fsspec caching bias. -->

### Local

| Operation | remote-store | pathlib | fsspec |
|-----------|-------:|-------:|-------:|
| Write 1MB | 484us | 404us (1.2x faster) | 764us (1.6x slower) |
| Read 1MB | 321us | 259us (1.2x faster) | 253us (1.3x faster) |
| Exists (hit) | 55us | 5us (10.2x faster) | 4us (14.1x faster) |
| List 50 files | 702us | 702us | 155us (4.5x faster) |
| Delete | 106us | 49us (2.2x faster) | 49us (2.2x faster) |

### S3 (MinIO)

| Operation | remote-store | boto3 | s3fs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 20.1ms | 30.4ms (1.5x slower) | 21.2ms (1.1x slower) |
| Read 1MB | 5.9ms | 5.1ms (1.2x faster) | 7.0ms (1.2x slower) |
| Exists (hit) | 1.4ms | 1.3ms | 1.3ms |
| List 50 files | 239us | 4.4ms (18.4x slower)* | 67us (3.5x faster)** |
| Delete | 3.4ms | 1.5ms (2.2x faster) | 1.6ms (2.1x faster) |

### SFTP

| Operation | remote-store | paramiko | sshfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 24.7ms | 23.6ms | 15.2ms (1.6x faster) |
| Read 1MB | 13.5ms | 12.5ms (1.1x faster) | 7.5ms (1.8x faster) |
| Exists (hit) | 859us | 413us (2.1x faster) | 699us (1.2x faster) |
| List 50 files | 2.8ms | 2.2ms (1.3x faster) | 3.1ms (1.1x slower) |
| Delete | 988us | 422us (2.3x faster) | 1.2ms (1.2x slower) |

### Azure

| Operation | remote-store | azure-blob | adlfs |
|-----------|-------:|-------:|-------:|
| Write 1MB | 13.7ms | 13.7ms | 16.9ms (1.2x slower) |
| Read 1MB | 5.8ms | 5.9ms | 10.8ms (1.9x slower) |
| Exists (hit) | 1.7ms | 1.7ms | 1.9ms (1.2x slower) |
| List 50 files | 11.4ms | 9.5ms (1.2x faster) | 83us (137.8x faster)** |
| Delete | 1.8ms | 1.8ms | 4.0ms (2.2x slower) |

---

*Listing numbers above pre-date the ID-032 cache-invalidation fix.
Re-run benchmarks to get updated numbers without fsspec caching bias.*
