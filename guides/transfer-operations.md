# Transfer Operations

The `ext.transfer` module provides three functions for moving data between
local files and Stores, or between two Stores: `upload`, `download`, and
`transfer`.

All functions stream data -- no file is ever fully loaded into memory.
An optional `on_progress` callback fires per chunk with the byte count.
No extra dependencies are required -- the module is pure Python and always
available.

## Quick Start

```python
from remote_store import Store, upload, download, transfer
from remote_store.backends import MemoryBackend

store = Store(backend=MemoryBackend())

# Upload a local file to the store
upload(store, "local/report.csv", "reports/report.csv")

# Download a remote file to a local path
download(store, "reports/report.csv", "local/copy.csv")

# Transfer between two stores
other = Store(backend=MemoryBackend())
transfer(store, "reports/report.csv", other, "archive/report.csv")
```

## upload

```python
upload(store, local_path, remote_path, *, overwrite=False, on_progress=None) -> None
```

Opens the local file in binary read mode and streams it to the Store
via `store.write()`. The file is never fully loaded into memory.

- `overwrite=True`: overwrite an existing remote file.
- `on_progress`: callback receiving the byte count per read (not cumulative).

Raises `FileNotFoundError` if the local file does not exist. This check
happens before any Store interaction.

```python
upload(store, "/data/input.csv", "input.csv", overwrite=True)
```

## download

```python
download(store, remote_path, local_path, *, overwrite=False, on_progress=None) -> None
```

Reads the remote file in 1 MiB chunks and writes each chunk to a local file.

- `overwrite=True`: overwrite an existing local file.
- `on_progress`: callback receiving the byte count per chunk written (not cumulative).

Raises `FileExistsError` if the local file already exists and `overwrite` is
`False`. This check happens before calling `store.read()`.

The remote stream is always closed, even if an error occurs.

```python
download(store, "reports/output.csv", "/tmp/output.csv")
```

## transfer

```python
transfer(src_store, src_path, dst_store, dst_path, *, overwrite=False, on_progress=None) -> None
```

Reads the source file and streams it directly to the destination via
`dst_store.write()`. The source and destination stores may be the same
instance.

- `overwrite=True`: overwrite an existing file in the destination store.
- `on_progress`: callback receiving the byte count per read (not cumulative).

The source stream is always closed, even if an error occurs.

```python
transfer(s3_store, "data/file.csv", sftp_store, "inbox/file.csv", overwrite=True)
```

## Progress Tracking

All three functions accept an `on_progress` callback. It receives the number
of bytes processed in each chunk (not a cumulative total):

```python
total = 0

def track(n: int) -> None:
    global total
    total += n
    print(f"{total} bytes transferred")

upload(store, "big_file.bin", "big_file.bin", on_progress=track)
```

## Error Handling

- **Local file errors** use stdlib exceptions: `FileNotFoundError` (upload)
  and `FileExistsError` (download).
- **Remote errors** use `RemoteStoreError` subtypes (`NotFound`,
  `AlreadyExists`, `CapabilityNotSupported`, etc.).
- `CapabilityNotSupported` always propagates immediately.

## Works with Store.child()

All transfer functions operate through the public Store API. They work
correctly with `Store.child()`, capability gating, and path rebasing:

```python
store = Store(backend=MemoryBackend())
reports = store.child("reports")

upload(reports, "local/q1.csv", "q1.csv")
# File is at "reports/q1.csv" in the root store
```
