"""Transfer operations -- upload, download, and cross-store transfer.

All functions stream data and never load full files into memory.
An optional ``on_progress`` callback fires per chunk with the byte count.

Usage:

```python
from remote_store.ext.transfer import upload, download, transfer

upload(store, "local/file.txt", "remote/key.txt", overwrite=True)
download(store, "remote/key.txt", "local/file.txt", overwrite=True)
transfer(src_store, "src.txt", dst_store, "dst.txt", overwrite=True)
```
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, cast

from remote_store.ext.streams import ProgressReader

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO

    from remote_store._store import Store

__all__ = ["download", "transfer", "upload"]

_DOWNLOAD_CHUNK_SIZE = 1_048_576  # 1 MiB


def upload(
    store: Store,
    local_path: str | os.PathLike[str],
    remote_path: str,
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Upload a local file to a Store.

    Opens the local file in binary read mode and streams it to the Store
    via ``store.write()``. The full file is never loaded into memory.

    Args:
        store: The Store to write to.
        local_path: Path to the local file.
        remote_path: Destination key in the Store.
        overwrite: Forwarded to ``store.write()``.
        on_progress: Called per read with the byte count (not cumulative).

    Returns:
        None

    Raises:
        FileNotFoundError: If *local_path* does not exist.
    """
    path = os.fspath(local_path)
    log.debug("upload %r -> %r", path, remote_path, extra={"op": "upload", "path": remote_path})
    with open(path, "rb") as fh:
        source: BinaryIO = fh
        if on_progress is not None:
            source = cast("BinaryIO", ProgressReader(fh, on_progress))
        store.write(remote_path, source, overwrite=overwrite)


def download(
    store: Store,
    remote_path: str,
    local_path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Download a file from a Store to a local path.

    Reads the remote file in 1 MiB chunks and writes each chunk to the
    local file. The full file is never loaded into memory.

    Args:
        store: The Store to read from.
        remote_path: Key to read from the Store.
        local_path: Destination path on the local filesystem.
        overwrite: If ``False`` (default) and *local_path* exists,
            raises ``FileExistsError``.
        on_progress: Called per chunk written with the byte count
            (not cumulative).

    Returns:
        None

    Raises:
        FileExistsError: If *local_path* exists and *overwrite* is False.
    """
    dest = os.fspath(local_path)
    log.debug("download %r -> %r", remote_path, dest, extra={"op": "download", "path": remote_path})
    if not overwrite and os.path.exists(dest):
        raise FileExistsError(f"Local file already exists: {dest}")

    stream = store.read(remote_path)
    try:
        with open(dest, "wb") as fh:
            while True:
                chunk = stream.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                fh.write(chunk)
                if on_progress is not None:
                    on_progress(len(chunk))
    finally:
        stream.close()


def transfer(
    src_store: Store,
    src_path: str,
    dst_store: Store,
    dst_path: str,
    *,
    overwrite: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Transfer a file from one Store to another.

    Reads the source file and streams it to the destination via
    ``dst_store.write()``. The full file is never loaded into memory.

    Args:
        src_store: The Store to read from.
        src_path: Key to read from *src_store*.
        dst_store: The Store to write to (may be the same as *src_store*).
        dst_path: Destination key in *dst_store*.
        overwrite: Forwarded to ``dst_store.write()``.
        on_progress: Called per read with the byte count (not cumulative).

    Returns:
        None
    """
    log.debug("transfer %r -> %r", src_path, dst_path, extra={"op": "transfer", "path": src_path})
    stream = src_store.read(src_path)
    try:
        source: BinaryIO = stream
        if on_progress is not None:
            source = cast("BinaryIO", ProgressReader(stream, on_progress))
        dst_store.write(dst_path, source, overwrite=overwrite)
    finally:
        stream.close()
