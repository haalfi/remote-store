# Async Store

Use `remote_store.aio` to access any backend with `async`/`await`. The
async API mirrors the synchronous `Store` — same methods, same errors,
same capability model — so existing knowledge transfers directly.

## Quick start

```python
import asyncio
from remote_store.aio import AsyncStore
from remote_store.backends import LocalBackend

async def main():
    async with AsyncStore(LocalBackend(root="/data"), root_path="reports") as store:
        await store.write("summary.txt", b"Q1 results", overwrite=True)
        data = await store.read_bytes("summary.txt")
        print(data.decode())

asyncio.run(main())
```

Any sync `Backend` (Local, S3, SFTP, Azure, Memory) is auto-wrapped via
`SyncBackendAdapter`, which delegates each call to the default executor
through `asyncio.to_thread()`. No code changes needed on the backend side.

For backends with native async SDK support, use the dedicated async backend
class for true non-blocking I/O — see [Native async backends](#native-async-backends).

## Streaming reads

`AsyncStore.read()` returns an `AsyncIterator[bytes]` (not `BinaryIO`),
because Python has no standard async file-like protocol. Consume it with
`async for`:

```python
async for chunk in store.read("large-file.bin"):
    process(chunk)  # 64 KB chunks by default
```

For small files, `read_bytes()` and `read_text()` load the full content
into memory in a single call:

```python
text = await store.read_text("config.yaml")
```

## Writing with async iterators

`write()` and `write_atomic()` accept `bytes` or `AsyncIterator[bytes]`:

```python
async def generate_report():
    yield b"header\n"
    yield b"row1\n"
    yield b"row2\n"

await store.write("report.csv", generate_report())
```

## Child stores

`child()` is synchronous (no I/O) and returns a new `AsyncStore` scoped
to a subfolder. The child shares the parent's backend:

```python
reports = store.child("2024/q1")
await reports.write("summary.txt", b"data")
# Visible at <root>/2024/q1/summary.txt
```

## Use with FastAPI

```python
from fastapi import FastAPI, UploadFile
from remote_store.aio import AsyncStore
from remote_store.backends import S3Backend

app = FastAPI()
store = AsyncStore(S3Backend(bucket="uploads", anon=False))

@app.post("/upload/{filename}")
async def upload(filename: str, file: UploadFile):
    data = await file.read()
    await store.write(filename, data, overwrite=True)
    return {"stored": filename}

@app.get("/download/{filename}")
async def download(filename: str):
    from starlette.responses import StreamingResponse
    return StreamingResponse(store.read(filename))
```

## Native async backends

`SyncBackendAdapter` runs sync backends in a thread pool — good enough for
many workloads, but each call still blocks a thread. Native async backends
use the cloud SDK's async clients directly, avoiding thread-pool overhead.

### AsyncAzureBackend

```python
from remote_store.aio import AsyncStore, AsyncAzureBackend

backend = AsyncAzureBackend(
    container="my-container",
    account_name="myaccount",
    account_key="...",
)
async with AsyncStore(backend, root_path="data") as store:
    await store.write("report.csv", b"col1,col2\n1,2", overwrite=True)
```

`AsyncAzureBackend` supports both plain Blob Storage and ADLS Gen2
(HNS-enabled) accounts. HNS is detected automatically on first I/O.
The constructor accepts the same credential parameters as the sync
`AzureBackend`.

Install the async Azure extras:

```bash
pip install "remote-store[azure]"
```

No additional dependencies are needed — the Azure SDK's async clients
(`azure.storage.blob.aio`, `azure.storage.filedatalake.aio`) are
included in the same packages as the sync clients.

## Health check

`ping()` verifies that the backend is reachable and credentials are valid:

```python
await store.ping()  # raises BackendUnavailable on failure
```

Native async backends (like `AsyncAzureBackend`) perform a lightweight
async probe. Wrapped sync backends delegate through `asyncio.to_thread()`.

## Context manager

Use `async with` for automatic cleanup:

```python
async with AsyncStore(backend) as store:
    await store.write("file.txt", b"data")
# backend resources released here
```

Child stores do not close the parent's backend — only the owning store
calls `aclose()` on exit.

## Limitations

- **`read_seekable()` and `open_atomic()` are not available** in the async
  API. Use `read_bytes()` + `io.BytesIO()` if you need a seekable stream,
  or `write_atomic()` for single-shot atomic writes.
- **`SyncBackendAdapter` materializes listing iterators** in memory
  (`list_files`, `list_folders`, `glob`). For very large directories this
  may use more memory than the sync API. Native async backends stream
  without materialisation.
- **`asyncio` only** — trio and anyio are not supported.

## See also

- [API reference](api/aio.md) — `AsyncStore`, `AsyncBackend`, `AsyncAzureBackend`, `SyncBackendAdapter`
- [Azure Backend](backends/azure.md) — sync Azure backend configuration and usage
- [Health Check](health-check.md) — `ping()` and `check_health()` details
- [Concurrency](concurrency.md) — thread safety, atomicity, and `overwrite=False` semantics
- [Example: Async Store](examples/async-store.md) — runnable async demo
