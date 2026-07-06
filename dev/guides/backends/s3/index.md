# S3 Backend

The S3 backend stores files on Amazon S3 or any S3-compatible service (MinIO, DigitalOcean Spaces, etc.).

## Installation

```
pip install "remote-store[s3]"
```

## Usage

```
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "s3": BackendConfig(
            type="s3",
            options={
                "bucket": "my-bucket",
                "key": "AWS_ACCESS_KEY_ID",
                "secret": "AWS_SECRET_ACCESS_KEY",
                "endpoint_url": "https://s3.amazonaws.com",
            },
        ),
    },
    stores={"data": StoreProfile(backend="s3", root_path="data")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write("report.csv", b"col1,col2\n1,2\n")
```

## Options

| Option           | Type   | Description                                                      |
| ---------------- | ------ | ---------------------------------------------------------------- |
| `bucket`         | `str`  | S3 bucket name (required)                                        |
| `key`            | `str`  | AWS access key ID                                                |
| `secret`         | `str`  | AWS secret access key                                            |
| `region_name`    | `str`  | AWS region name                                                  |
| `endpoint_url`   | `str`  | Custom endpoint for S3-compatible services                       |
| `tls_ca_bundle`  | `str`  | Path to a PEM CA bundle file for custom/self-signed certificates |
| `client_options` | `dict` | Additional options passed to s3fs                                |

## Custom TLS Certificates

Use `tls_ca_bundle` when connecting to S3-compatible services with custom or self-signed certificates (e.g., on-premises MinIO):

```
backend = S3Backend(
    bucket="my-bucket",
    endpoint_url="https://minio.internal:9000",
    tls_ca_bundle="/etc/ssl/certs/internal-ca.pem",
)
```

Or via config:

```
backends:
  minio:
    type: s3
    options:
      bucket: my-bucket
      endpoint_url: https://minio.internal:9000
      tls_ca_bundle: /etc/ssl/certs/internal-ca.pem
```

If `tls_ca_bundle` is not set, the following environment variables are checked in order (first non-empty value wins):

| Priority | Env var              | Standard |
| -------- | -------------------- | -------- |
| 1        | `AWS_CA_BUNDLE`      | boto3    |
| 2        | `REQUESTS_CA_BUNDLE` | requests |
| 3        | `SSL_CERT_FILE`      | OpenSSL  |

The path is validated at construction time — a `ValueError` is raised immediately if the file does not exist.

This replaces the previous workaround of passing `client_options={"client_kwargs": {"verify": "/path/to/ca.pem"}}`.

## Botocore Client Tuning

Anything beyond the first-class options above (proxies, timeouts, retry mode, S3 addressing style, pool sizes, custom `User-Agent`, …) is configured by passing a `config_kwargs` dict inside `client_options`. The dict is forwarded to `aiobotocore.config.AioConfig(**config_kwargs)`, so every keyword the underlying `botocore.config.Config` accepts is available.

Why `config_kwargs`, not `client_kwargs['config']`

`s3fs.S3FileSystem.set_session` always passes `config=AioConfig(**self.config_kwargs)` to `aiobotocore.create_client()`. Setting `client_kwargs['config']` in addition would duplicate the `config=` keyword and raise `TypeError: got multiple values for keyword argument 'config'`. The [S3 backend spec](https://docs.remotestore.dev/stable/explanation/design/specs/008-s3-backend/#s3-026) pins the routing: every `Config` option flows through `client_options['config_kwargs']`, and a pre-built Config in `client_kwargs` is rejected with a clear `ValueError`.

### Disabling inherited HTTP proxies

Required when the host has `HTTP_PROXY` / `HTTPS_PROXY` set in the environment but the S3 endpoint is reachable directly (typical for on-premises MinIO):

```
backend = S3Backend(
    bucket="my-bucket",
    endpoint_url="https://s3.internal:9000",
    client_options={
        "config_kwargs": {
            "proxies": {"http": None, "https": None},
        },
    },
)
```

### Pointing at a corporate proxy

```
backend = S3Backend(
    bucket="my-bucket",
    client_options={
        "config_kwargs": {
            "proxies": {
                "http": "http://proxy.corp:3128",
                "https": "http://proxy.corp:3128",
            },
        },
    },
)
```

### Retry policy

Prefer the first-class `retry=RetryPolicy(...)` argument — it is portable across backends and applied via the same merge path:

```
backend = S3Backend(
    bucket="my-bucket",
    retry=RetryPolicy(max_attempts=5),
)
```

When you need `mode="adaptive"` or other botocore-specific retry knobs, pass them through `config_kwargs.retries` and **do not** also pass `retry=RetryPolicy(...)`: `RetryPolicy` replaces the entire `retries` dict (matching `botocore.Config.merge` semantics), so any caller-supplied `mode` / non-`max_attempts` fields are lost. Pick one channel:

```
backend = S3Backend(
    bucket="my-bucket",
    client_options={
        "config_kwargs": {
            "retries": {"max_attempts": 5, "mode": "adaptive"},
        },
    },
)
```

### Connect / read timeouts

```
backend = S3Backend(
    bucket="my-bucket",
    client_options={
        "config_kwargs": {
            "connect_timeout": 3.0,
            "read_timeout": 10.0,
        },
    },
)
```

### MinIO-style path addressing

Required for endpoints that do not support virtual-host-style bucket addressing (most on-premises MinIO deployments):

```
backend = S3Backend(
    bucket="my-bucket",
    endpoint_url="https://minio.internal:9000",
    key="AKIA...",
    secret="...",
    client_options={
        "config_kwargs": {
            "s3": {"addressing_style": "path"},
        },
    },
)
```

### Putting it together

A realistic on-premises MinIO configuration combining the pieces above (custom CA bundle continues to come from `tls_ca_bundle=` / env vars, [Custom TLS Certificates](#custom-tls-certificates)):

```
backend = S3Backend(
    bucket="my-bucket",
    endpoint_url="https://s3.internal:9000",
    key="AKIA...",
    secret="...",
    retry=RetryPolicy(max_attempts=5),
    client_options={
        "config_kwargs": {
            "connect_timeout": 3.0,
            "read_timeout": 10.0,
            "s3": {"addressing_style": "path"},
            "proxies": {"http": None, "https": None},
        },
    },
)
```

## File Metadata

`get_file_info()` and `list_files()` return `FileInfo` objects with the following fields populated by the S3 backend:

| Field    | Source                 | Notes                                                                                   |
| -------- | ---------------------- | --------------------------------------------------------------------------------------- |
| `etag`   | `ETag` response header | Double-quotes stripped; lowercased. Example: `"abc123"` → `abc123`.                     |
| `digest` | —                      | Always `None`; S3 checksums require `ChecksumMode: ENABLED` (not requested by default). |

## Write Results

The S3 backend declares `WRITE_RESULT_NATIVE` and `USER_METADATA`. Write operations return a [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md) with `digest`, `etag`, and `last_modified` populated from the upload response — contrast with reads, where `digest` is always `None` (see the File Metadata table above).

Pass `metadata=` to store custom string key-value pairs as S3 object metadata. They round-trip through `get_file_info()` in `FileInfo.metadata`.

## Listing Strategies and Performance

S3 listing behavior differs sharply between shallow and recursive traversals. Understanding these trade-offs is critical for large buckets.

### Shallow Listing (Non-Recursive)

Use `list_files(path, recursive=False)` or `iter_children(path)` to list only direct children:

```
# List direct children only
for entry in store.iter_children("data/"):
    print(entry.name)  # Files and folders one level deep
```

**Characteristics:**

- Single S3 `ListObjectsV2` API call (or paginated requests if >1000 entries)
- O(n) cost where n = direct children count
- **Flat cost per call**, not dependent on bucket size
- Suitable for folder-first navigation (e.g., building a file browser UI)

### Recursive Listing (Flat Stream)

Use `list_files(path, recursive=True)` to fetch all files under a prefix:

```
# Stream all files under a prefix, regardless of depth
for file_info in store.list_files("data/", recursive=True):
    process(file_info)
```

**Why flat streaming wins:**

- Internally uses S3's `ListObjectsV2` pagination with a prefix, not delimiter-based folder traversal
- Single logical stream; S3 SDK handles pagination transparently
- O(n) cost where n = total objects in the prefix tree
- Avoids the O(n_folders) × (API calls + parsing overhead) of delimiter-based iteration

**If you need all objects under a prefix, use `recursive=True`:**

```
# ✓ Single flat stream (optimal)
for file in store.list_files("data/", recursive=True):
    process(file)
```

**Do not implement folder-by-folder traversal:**

```
# ❌ This makes one API call per folder level
def traverse_folders(prefix):
    for folder in list_folders(prefix):  # Calls ListObjectsV2 with delimiter=/
        yield from list_files(folder, recursive=False)
        yield from traverse_folders(folder)  # Recursive calls per subfolder
```

The traversal approach costs O(n_folders) API calls, even with few total files.

### Streaming Over Parallelization

For large buckets, use a **single sequential flat stream**, not parallel folder traversal:

```
# ✓ Single flat stream (optimal for large buckets)
for file in store.list_files("data/", recursive=True):
    process(file)
```

**Why not parallelize folder traversal:**

```
# ❌ Avoid parallel folder enumeration
from concurrent.futures import ThreadPoolExecutor

def parallel_traverse(prefix, executor):
    # Spawning threads per folder creates:
    # - O(n_folders) concurrent requests (thundering herd)
    # - Earlier rate-limiting hits (S3 per-partition limits)
    # - Thread pool overhead
    # - Loss of connection pooling benefits
```

**Flat streams are superior:**

- Single sequential `ListObjectsV2` respects S3's request pipelining
- Reuses pooled connections across paginated responses
- No thread overhead for what is already a streaming operation
- More predictable latency and throughput

On large buckets with thousands of folders, a flat stream is **orders of magnitude faster** than parallel traversal.

### Performance

See the [performance guide](https://docs.remotestore.dev/stable/explanation/performance/#comparative-results) for benchmark results. Listing is dominated by S3 API round-trip latency, not file count. Connection pooling is automatic; successive calls reuse connections.

### Directory-listing cache (off by default)

The S3 backend disables the underlying s3fs directory-listing cache by default, so every listing call reflects the current state of the bucket.

s3fs caches directory listings in a cache that **never expires**: once a prefix has been listed, s3fs serves later listings of that prefix from memory until the process restarts. For a single reader that never writes, that saves a round trip on repeated listings. But for any store shared by more than one writer — two processes, two `Store` instances, or another tool writing to the same bucket — a write made elsewhere is then **permanently invisible** to a reader that has already listed the prefix. Fresh listings cost one bounded round trip; the default favours correctness.

Re-enable the cache when you have a single-writer (or read-only) workload and want to avoid repeated listing round trips:

```
backend = S3Backend(
    bucket="my-bucket",
    client_options={"use_listings_cache": True},
)
```

`client_options["use_listings_cache"]` takes precedence over the default, so passing `True` restores the s3fs caching behaviour (and `False` is a harmless no-op). The [`ext.cache`](https://docs.remotestore.dev/stable/guides/cache/index.md) extension is the portable, backend-agnostic alternative when you want caching with explicit invalidation.

### Data Lake Pattern (Few Root Folders, Deep Nesting)

If you have few root-level folders (e.g., `/bronze`, `/silver`, `/gold`) with deeply nested structures:

**To explore the structure:**

```
# ✓ Shallow listing to see root tiers
for folder in store.list_folders(""):  # bronze/, silver/, gold/
    print(folder.name)
```

**To process a specific tier incrementally:**

```
# ✓ Depth-limited listing to explore one branch without full recursion
for file in store.list_files("bronze", max_depth=3):
    # Gets files up to 3 levels deep under bronze/
    process(file)
```

**Only if you need all files across all depths:**

```
# ✓ Full recursive listing (streaming, memory-efficient despite size)
for file in store.list_files("bronze", recursive=True):
    process(file)
```

**Characteristics:**

- `max_depth=0`: Direct children only (equivalent to non-recursive)
- `max_depth=1`: One level of nesting
- `max_depth=None` (default): Defers to `recursive` parameter (non-recursive by default)
- Cost on S3: Full recursive `ListObjectsV2` listing (O(n_total) API cost); client-side depth filter reduces the yielded result set. Local/SFTP/Memory backends prune natively.
- Streaming, memory-efficient (unlike loading entire tree)

**Use case:** Incremental exploration, tier-by-tier processing, or when you know the data structure depth in advance.

### Recommendations

- **Shallow listing (non-recursive):** Interactive UI, folder browsers, or when you only need direct children.
- **Depth-limited listing (max_depth=N):** Data lake patterns with known structure depth. Explore incrementally without full recursion.
- **Recursive listing (full tree):** Data processing, backups, or scanning entire prefix. Streaming operation, memory-efficient despite size.
- **Pattern matching:** Use `glob(pattern)` (internally uses flat stream with filtering) rather than custom folder traversal.
- **Note:** Do not parallelize any listing — single flat streams are already optimal.

## Capabilities

Supports all capabilities except `ATOMIC_MOVE`. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

## Caveats

- **`move()` is not atomic.** S3 has no native rename operation. `move()` is implemented as copy + delete. If the process crashes between the two steps, both source and destination will exist.
- **`overwrite=False` has a TOCTOU race.** The exists-check and write are separate API calls. Concurrent writers can both pass the check and overwrite each other.

See the [Concurrency and Atomicity Guarantees](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) guide for details and workarounds.

## See also

- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)
- [S3 backend example](https://docs.remotestore.dev/stable/tutorial/examples/s3-backend/index.md)
- [S3 listing strategies example](https://docs.remotestore.dev/stable/tutorial/examples/s3-listing-strategies/index.md) — demonstrates shallow, recursive, and filtering techniques
- [Performance guide](https://docs.remotestore.dev/stable/explanation/performance/index.md) — benchmark data and overhead analysis

## API Reference

## S3Backend

```
S3Backend(
    bucket: str,
    *,
    endpoint_url: str | None = None,
    key: str | Secret | None = None,
    secret: str | Secret | None = None,
    region_name: str | None = None,
    tls_ca_bundle: str | None = None,
    client_options: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,
    reject_write_under_file_ancestor: bool = False,
)
```

Bases: `_S3Base`

S3-compatible object storage backend using s3fs.

`move()` is implemented as a server-side copy followed by a delete. This is non-atomic: a crash or network error between the two steps may leave both source and destination present. `ATOMIC_MOVE` is not declared.

Parameters:

- **`bucket`** (`str`) – S3 bucket name (required, non-empty).
- **`endpoint_url`** (`str | None`, default: `None` ) – Custom endpoint URL (e.g. for MinIO).
- **`key`** (`str | Secret | None`, default: `None` ) – AWS access key ID.
- **`secret`** (`str | Secret | None`, default: `None` ) – AWS secret access key.
- **`region_name`** (`str | None`, default: `None` ) – AWS region name.
- **`tls_ca_bundle`** (`str | None`, default: `None` ) – Path to a PEM CA bundle file. Falls back to AWS_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE.
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to s3fs.
- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / open_atomic / move / copy HEAD each slash-aligned ancestor of the target path and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. Default False: each nested-path write otherwise pays one HEAD per ancestor; paths without slashes short-circuit.
