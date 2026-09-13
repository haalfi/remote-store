# ext.transfer

## transfer

Transfer operations -- upload, download, and cross-store transfer.

All functions stream data and never load full files into memory. An optional `on_progress` callback fires per chunk with the byte count.

Example

```
from remote_store.ext.transfer import upload, download, transfer

upload(store, "local/file.txt", "remote/key.txt", overwrite=True)
download(store, "remote/key.txt", "local/file.txt", overwrite=True)
transfer(src_store, "src.txt", dst_store, "dst.txt", overwrite=True)
```

### upload

```
upload(
    store: Store,
    local_path: str | PathLike[str],
    remote_path: str,
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None
```

Upload a local file to a Store.

Opens the local file in binary read mode and streams it to the Store via `store.write()`. The full file is never loaded into memory.

Parameters:

- **`store`** (`Store`) – The Store to write to.
- **`local_path`** (`str | PathLike[str]`) – Path to the local file.
- **`remote_path`** (`str`) – Destination key in the Store.
- **`overwrite`** (`bool`, default: `False` ) – Forwarded to store.write().
- **`on_progress`** (`Callable[[int], None] | None`, default: `None` ) – Called per read with the byte count (not cumulative).

Returns:

- `None` – None

Raises:

- `FileNotFoundError` – If local_path does not exist.

### download

```
download(
    store: Store,
    remote_path: str,
    local_path: str | PathLike[str],
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None
```

Download a file from a Store to a local path.

Reads the remote file in 1 MiB chunks and writes each chunk to the local file. The full file is never loaded into memory.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`remote_path`** (`str`) – Key to read from the Store.
- **`local_path`** (`str | PathLike[str]`) – Destination path on the local filesystem.
- **`overwrite`** (`bool`, default: `False` ) – If False (default) and local_path exists, raises FileExistsError.
- **`on_progress`** (`Callable[[int], None] | None`, default: `None` ) – Called per read with the byte count (not cumulative).

Returns:

- `None` – None

Raises:

- `FileExistsError` – If local_path exists and overwrite is False.

### transfer

```
transfer(
    src_store: Store,
    src_path: str,
    dst_store: Store,
    dst_path: str,
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None
```

Transfer a file from one Store to another.

Reads the source file and streams it to the destination via `dst_store.write()`. The full file is never loaded into memory.

Parameters:

- **`src_store`** (`Store`) – The Store to read from.
- **`src_path`** (`str`) – Key to read from src_store.
- **`dst_store`** (`Store`) – The Store to write to (may be the same as src_store).
- **`dst_path`** (`str`) – Destination key in dst_store.
- **`overwrite`** (`bool`, default: `False` ) – Forwarded to dst_store.write().
- **`on_progress`** (`Callable[[int], None] | None`, default: `None` ) – Called per read with the byte count (not cumulative).

Returns:

- `None` – None

## See also

- [Transfer Operations](https://docs.remotestore.dev/stable/guides/transfer-operations/index.md) — guide to upload, download, and cross-store transfer
- [Transfer Operations example](https://docs.remotestore.dev/stable/tutorial/examples/transfer-operations/index.md) — transfer operations in action
