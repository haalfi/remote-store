"""PyArrow FileSystem adapter — wraps any Store into a [pyarrow.fs.PyFileSystem](https://arrow.apache.org/docs/python/generated/pyarrow.fs.PyFileSystem.html).

Install with ``pip install "remote-store[arrow]"``.

Usage:

```python
from remote_store.ext.arrow import pyarrow_fs

fs = pyarrow_fs(store)
pq.write_table(table, "data.parquet", filesystem=fs)
```
"""

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
from typing import TYPE_CHECKING, Any, BinaryIO, cast  # noqa: TCH003 — runtime ref needed for CodeQL

try:
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.fs as pafs  # type: ignore[import-untyped]
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "PyArrow is required for the arrow extension. Install it with: pip install 'remote-store[arrow]'"
    ) from _exc

from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from remote_store._store import Store

log = logging.getLogger(__name__)

__all__ = ["StoreFileSystemHandler", "pyarrow_fs"]

# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

_ERROR_MAP: list[tuple[type[RemoteStoreError], type[Exception]]] = [
    (NotFound, FileNotFoundError),
    (AlreadyExists, FileExistsError),
    (PermissionDenied, PermissionError),
    (InvalidPath, ValueError),
    (CapabilityNotSupported, NotImplementedError),
    # DirectoryNotEmpty, BackendUnavailable, and base RemoteStoreError → OSError
]


@contextlib.contextmanager
def _map_errors() -> Any:  # noqa: ANN401
    """Translate ``RemoteStoreError`` subtypes to standard Python exceptions."""
    try:
        yield
    except RemoteStoreError as exc:
        for rs_type, py_type in _ERROR_MAP:
            if isinstance(exc, rs_type):
                raise py_type(str(exc)) from exc
        raise OSError(str(exc)) from exc


# ---------------------------------------------------------------------------
# _StoreSink — writable buffer that flushes to Store on close()
# ---------------------------------------------------------------------------


class _StoreSink(io.RawIOBase):
    """Writable buffer that accumulates data and writes to a Store on close.

    Uses ``SpooledTemporaryFile`` for transparent in-memory-to-disk promotion.
    """

    def __init__(self, store: Store, path: str, spill_threshold: int) -> None:
        self._store = store
        self._path = path
        self._buf: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
            max_size=spill_threshold
        )

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def write(self, data: bytes | bytearray | memoryview) -> int:  # type: ignore[override]
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self._buf.write(data)

    def tell(self) -> int:
        return self._buf.tell()

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._buf.seek(0)
            with _map_errors():
                self._store.write(self._path, cast(BinaryIO, self._buf), overwrite=True)  # noqa: TC006
        finally:
            with contextlib.suppress(Exception):
                self._buf.close()
            super().close()


# ---------------------------------------------------------------------------
# StoreFileSystemHandler
# ---------------------------------------------------------------------------


def _normalize(path: str) -> str:
    """Strip leading/trailing slashes, collapse separators, resolve ``.`` and ``..``."""
    # Also handle backslashes for Windows paths leaked by callers.
    path = path.replace("\\", "/")
    resolved: list[str] = []
    for p in path.split("/"):
        if not p or p == ".":
            continue
        if p == "..":
            if resolved:
                resolved.pop()
            continue
        resolved.append(p)
    return "/".join(resolved)


class StoreFileSystemHandler(pafs.FileSystemHandler):  # type: ignore[misc]
    """``pyarrow.fs.FileSystemHandler`` backed by a ``Store``.

    Args:
        store: The Store to expose as a PyArrow filesystem.
        materialization_threshold: Max file size (bytes) for Tier 2 full-file
            materialization in ``open_input_file``. Default 64 MB.
        write_spill_threshold: Max in-memory buffer size (bytes) for
            ``_StoreSink`` before spilling to disk. Default 64 MB.

    **Thread safety:** The handler itself holds no shared mutable state. PyArrow's
    C++ layer may call handler methods from background threads (with the GIL
    acquired). Thread safety therefore depends on the backend: ``MemoryBackend``
    uses a lock (safe), ``LocalBackend`` relies on OS file semantics (safe),
    cloud backends use thread-safe HTTP clients (safe). If using a custom backend,
    ensure its methods are safe under concurrent calls.
    """

    def __init__(
        self,
        store: Store,
        materialization_threshold: int = 64 * 1024 * 1024,
        write_spill_threshold: int = 64 * 1024 * 1024,
    ) -> None:
        self._store = store
        self._materialization_threshold = materialization_threshold
        self._write_spill_threshold = write_spill_threshold

        # Tier 1 probing: check if the backend exposes a native PyArrow FS.
        # The bound method reference is captured at construction time for
        # performance (no attribute lookup per read).  This is safe because
        # Store is effectively immutable after construction — it has no public
        # API to change _root or _backend.
        self._native_fs: pafs.FileSystem | None = None
        self._native_path_fn: Callable[[str], str] | None = None
        try:
            native_fs = store.unwrap(pafs.FileSystem)
            if isinstance(native_fs, pafs.FileSystem):
                self._native_fs = native_fs
                self._native_path_fn = store.native_path
        except (CapabilityNotSupported, TypeError, OSError) as _exc:
            # Tier 1 probe for optional native PyArrow backend (capability-probe
            # pattern per ADR-0008). Catches CapabilityNotSupported (backend lacks
            # unwrap), TypeError (wrong type_hint), and OSError (S3/cloud backend
            # initialization failures). All disable Tier 1 gracefully; reads fall
            # through to Tier 2/3.
            log.debug("Tier 1 probe failed, falling back to Tier 2/3: %s", _exc)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StoreFileSystemHandler):
            return self._store == other._store
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        if isinstance(other, StoreFileSystemHandler):
            return self._store != other._store
        return NotImplemented

    # region: identity (PA-003, PA-006)
    def get_type_name(self) -> str:
        return "remote-store"

    @staticmethod
    def normalize_path(path: str) -> str:
        return _normalize(path)

    # endregion

    # region: file info (PA-007, PA-008)
    def get_file_info(self, paths: list[str]) -> list[pafs.FileInfo]:
        results: list[pafs.FileInfo] = []
        for raw_path in paths:
            path = _normalize(raw_path)
            try:
                with _map_errors():
                    # Optimistic: try get_file_info first (1 RPC for files)
                    info = self._store.get_file_info(path)
                    results.append(
                        pafs.FileInfo(
                            path,
                            type=pafs.FileType.File,
                            size=info.size,
                            mtime=info.modified_at,
                        )
                    )
            except (FileNotFoundError, ValueError):
                # ValueError: InvalidPath mapped by _map_errors (e.g. root/empty path)
                # Not a file — check if it's a folder (2nd RPC only for dirs/not-found)
                try:
                    with _map_errors():
                        if self._store.is_folder(path):
                            results.append(pafs.FileInfo(path, type=pafs.FileType.Directory))
                        else:
                            results.append(pafs.FileInfo(path, type=pafs.FileType.NotFound))
                except FileNotFoundError:
                    results.append(pafs.FileInfo(path, type=pafs.FileType.NotFound))
        return results

    def get_file_info_selector(self, selector: Any) -> list[pafs.FileInfo]:  # noqa: ANN401
        base_dir = _normalize(selector.base_dir)
        recursive: bool = selector.recursive
        allow_not_found: bool = selector.allow_not_found

        results: list[pafs.FileInfo] = []
        try:
            with _map_errors():
                # Step 1: list files
                for fi in self._store.list_files(base_dir, recursive=recursive):
                    file_path = str(fi.path)
                    results.append(
                        pafs.FileInfo(
                            file_path,
                            type=pafs.FileType.File,
                            size=fi.size,
                            mtime=fi.modified_at,
                        )
                    )

                if recursive:
                    # Recursive: synthetic directory entries from file paths
                    seen_dirs: set[str] = set()
                    base_prefix = f"{base_dir}/" if base_dir else ""
                    for info in results:
                        parts = info.path.split("/")
                        # Build ancestor paths that are strict descendants of base_dir
                        for i in range(1, len(parts)):
                            prefix = "/".join(parts[:i])
                            if prefix != base_dir and prefix.startswith(base_prefix) and prefix not in seen_dirs:
                                seen_dirs.add(prefix)
                    for dir_path in sorted(seen_dirs):
                        results.append(pafs.FileInfo(dir_path, type=pafs.FileType.Directory))
                else:
                    # Non-recursive: list immediate subfolders
                    for entry in self._store.list_folders(base_dir):
                        results.append(pafs.FileInfo(str(entry.path), type=pafs.FileType.Directory))

        except FileNotFoundError:
            if not allow_not_found:
                raise
            return []

        # PA-008 step 4: if base_dir doesn't exist, handle allow_not_found
        if not results and base_dir:
            with _map_errors():
                if not self._store.exists(base_dir):
                    if allow_not_found:
                        return []
                    raise FileNotFoundError(f"Directory not found: {base_dir!r}")

        return results

    # endregion

    # region: read operations (PA-009, PA-010)
    def open_input_stream(self, path: str) -> Any:  # noqa: ANN401
        path = _normalize(path)
        with _map_errors():
            stream = self._store.read(path)
            # NOTE: Subsequent reads from PythonFile bypass _map_errors(), so
            # mid-read RemoteStoreError from cloud streams would leak unmapped.
            # Currently inert for open_input_stream: cloud backends' read()
            # streams are forward-only. open_input_file uses read_seekable()
            # which wraps in _ErrorMappingStream for Azure range reads.
            try:
                return pa.PythonFile(stream, mode="r")
            except Exception:  # pragma: no cover
                stream.close()
                raise

    def open_input_file(self, path: str) -> Any:  # noqa: ANN401
        path = _normalize(path)

        # Tier 1: native fast path — bypass Store I/O entirely.
        # The native PyArrow FS raises standard exceptions (FileNotFoundError,
        # OSError), so no _map_errors() translation is needed.
        if self._native_fs is not None and self._native_path_fn is not None:
            return self._native_fs.open_input_file(self._native_path_fn(path))

        with _map_errors():
            info = self._store.get_file_info(path)

            if info.size <= self._materialization_threshold:
                # Tier 2: full-file materialization → BufferReader
                data = self._store.read_bytes(path)
                return pa.BufferReader(pa.py_buffer(data))

            # Tier 3: seekable streaming via PythonFile for large files.
            # read_seekable() returns a backend-optimized seekable stream:
            # zero-copy passthrough on Local/S3/SFTP, HTTP Range reader on
            # Azure, SpooledTemporaryFile fallback on HTTP.
            stream = self._store.read_seekable(path)
            try:
                return pa.PythonFile(stream, mode="r")
            except Exception:  # pragma: no cover
                stream.close()
                raise

    # endregion

    # region: write operations (PA-011, PA-012)
    def open_output_stream(self, path: str, metadata: Any = None) -> Any:  # noqa: ANN401
        path = _normalize(path)
        sink = _StoreSink(self._store, path, self._write_spill_threshold)
        return pa.PythonFile(sink, mode="w")

    def open_append_stream(self, path: str, metadata: Any = None) -> Any:  # noqa: ANN401
        raise NotImplementedError("Append is not supported by remote-store backends")

    # endregion

    # region: delete and directory operations (PA-013 through PA-015)
    def delete_file(self, path: str) -> None:
        path = _normalize(path)
        with _map_errors():
            self._store.delete(path, missing_ok=False)

    def create_dir(self, path: str, recursive: bool = True) -> None:
        # No-op: directories are virtual / created implicitly on write.
        pass

    def delete_dir(self, path: str) -> None:
        path = _normalize(path)
        if not path:
            raise NotImplementedError("Deleting the root directory is not supported")
        with _map_errors():
            self._store.delete_folder(path, recursive=True, missing_ok=False)

    def delete_dir_contents(self, path: str, *, missing_dir_ok: bool = False) -> None:
        path = _normalize(path)
        if not path:
            raise NotImplementedError("Deleting all root directory contents is not supported (safety guard)")
        try:
            with _map_errors():
                # Check existence first — some backends return empty for non-existent dirs
                if not self._store.is_folder(path):
                    raise FileNotFoundError(f"Directory not found: {path!r}")
                # Delete all files
                for fi in list(self._store.list_files(path)):
                    self._store.delete(str(fi.path), missing_ok=True)
                # Delete subfolders recursively
                for entry in list(self._store.list_folders(path)):
                    self._store.delete_folder(str(entry.path), recursive=True, missing_ok=True)
        except FileNotFoundError:
            if not missing_dir_ok:
                raise

    def delete_root_dir_contents(self) -> None:
        raise NotImplementedError("Deleting all root directory contents is not supported (safety guard)")

    # endregion

    # region: move and copy (PA-017, PA-018)
    def move(self, src: str, dest: str) -> None:
        src, dest = _normalize(src), _normalize(dest)
        with _map_errors():
            self._store.move(src, dest, overwrite=True)

    def copy_file(self, src: str, dest: str) -> None:
        src, dest = _normalize(src), _normalize(dest)
        with _map_errors():
            self._store.copy(src, dest, overwrite=True)

    # endregion


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def pyarrow_fs(
    store: Store,
    *,
    materialization_threshold: int = 64 * 1024 * 1024,
    write_spill_threshold: int = 64 * 1024 * 1024,
) -> pafs.PyFileSystem:
    """Create a ``pyarrow.fs.PyFileSystem`` backed by *store*.

    Args:
        store: The Store to expose.
        materialization_threshold: See ``StoreFileSystemHandler``.
        write_spill_threshold: See ``StoreFileSystemHandler``.
    """
    handler = StoreFileSystemHandler(
        store,
        materialization_threshold=materialization_threshold,
        write_spill_threshold=write_spill_threshold,
    )
    return pafs.PyFileSystem(handler)
