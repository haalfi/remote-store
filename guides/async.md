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
  API (Phase 1). Use `read_bytes()` + `io.BytesIO()` if you need a
  seekable stream, or `write_atomic()` for single-shot atomic writes.
- **`SyncBackendAdapter` materializes listing iterators** in memory
  (`list_files`, `list_folders`, `glob`). For very large directories this
  may use more memory than the sync API. Native async backends (Phase 2)
  will stream without materialisation.
- **`asyncio` only** — trio and anyio are not supported in Phase 1.

## See also

- [API reference](api/aio.md) — `AsyncStore`, `AsyncBackend`, `SyncBackendAdapter`
- [Concurrency](concurrency.md) — thread safety, atomicity, and `overwrite=False` semantics
- [Example: Async Store](examples/async-store.md) — runnable async demo
