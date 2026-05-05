"""SyncBackendAdapter -- bridges sync backends into the async world."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar, TypeVar

from remote_store._capabilities import Capability, CapabilitySet
from remote_store.aio._async_backend import AsyncBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from remote_store._backend import Backend as _SyncBackend
    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._types import AsyncWritableContent

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _materialize(content: AsyncWritableContent) -> bytes:
    """Collect async content into a single ``bytes`` object.

    If *content* is already ``bytes`` it is returned as-is.  Otherwise the
    ``AsyncIterator[bytes]`` is drained into memory.
    """
    if isinstance(content, bytes):
        return content
    chunks: list[bytes] = []
    async for chunk in content:
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# SyncBackendAdapter
# ---------------------------------------------------------------------------


class SyncBackendAdapter(AsyncBackend):
    """Wraps a synchronous :class:`Backend` as an :class:`AsyncBackend`.

    Every blocking call is dispatched to the default executor via
    :func:`asyncio.to_thread`, keeping the event loop responsive.

    Args:
        backend: The synchronous backend instance to wrap.
    """

    # Universal upper bound — the wrapped backend's runtime capabilities() narrows this.
    CAPABILITIES: ClassVar[CapabilitySet] = CapabilitySet(set(Capability))

    def __init__(self, backend: _SyncBackend) -> None:
        self._sync = backend

    # -- Properties (ASYNC-034) --------------------------------------------

    @property
    def name(self) -> str:
        """Backend identifier, forwarded from the wrapped backend."""
        return self._sync.name

    @property
    def capabilities(self) -> CapabilitySet:
        """Capability set, forwarded from the wrapped backend."""
        return self._sync.capabilities

    # -- Sync passthrough (no I/O, no thread) ------------------------------

    def to_key(self, native_path: str) -> str:
        """Convert a native path to a backend-relative key."""
        return self._sync.to_key(native_path)

    def native_path(self, path: str) -> str:
        """Convert a backend-relative key to the native path."""
        return self._sync.native_path(path)

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a resolution plan for *path*."""
        return self._sync.resolve(path)

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the native backend handle."""
        return self._sync.unwrap(type_hint)

    # -- I/O methods (asyncio.to_thread) -----------------------------------

    async def exists(self, path: str) -> bool:
        """Check if a file or folder exists."""
        return await asyncio.to_thread(self._sync.exists, path)

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* is an existing file."""
        return await asyncio.to_thread(self._sync.is_file, path)

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* is an existing folder."""
        return await asyncio.to_thread(self._sync.is_folder, path)

    async def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        Raises:
            InvalidPath: If ``path`` names an existing directory.
            NotFound: If the file does not exist.
        """
        return await asyncio.to_thread(self._sync.read_bytes, path)

    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        Raises:
            InvalidPath: If ``path`` names an existing directory.
            NotFound: If the file does not exist.
        """
        return await asyncio.to_thread(self._sync.get_file_info, path)

    async def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        Raises:
            InvalidPath: If ``path`` names an existing file.
            NotFound: If the folder does not exist.
        """
        return await asyncio.to_thread(self._sync.get_folder_info, path)

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        Raises:
            InvalidPath: If ``src`` names a directory or ``dst`` names an
                existing directory.
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists, ``src != dst``, and
                ``overwrite`` is ``False``.
        """
        await asyncio.to_thread(self._sync.move, src, dst, overwrite=overwrite)

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        Raises:
            InvalidPath: If ``src`` names a directory or ``dst`` names an
                existing directory.
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists, ``src != dst``, and
                ``overwrite`` is ``False``.
        """
        await asyncio.to_thread(self._sync.copy, src, dst, overwrite=overwrite)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        Raises:
            NotFound: If the file is missing and ``missing_ok`` is ``False``.
            InvalidPath: If the path is empty, or if ``path`` names a directory
                (regardless of ``missing_ok``).
        """
        await asyncio.to_thread(self._sync.delete, path, missing_ok=missing_ok)

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        Raises:
            InvalidPath: If ``path`` names an existing file (regardless of
                ``missing_ok`` -- a type mismatch is not a missing file).
            NotFound: If the folder is missing and ``missing_ok`` is ``False``.
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
        """
        await asyncio.to_thread(self._sync.delete_folder, path, recursive=recursive, missing_ok=missing_ok)

    async def check_health(self) -> None:
        """Verify the backend is reachable."""
        await asyncio.to_thread(self._sync.check_health)

    # -- Streaming read (ASYNC-033) ----------------------------------------

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Open a file for reading and yield chunks asynchronously.

        Raises:
            InvalidPath: If ``path`` names an existing directory.
            NotFound: If the file does not exist.
        """
        stream = await asyncio.to_thread(self._sync.read, path)
        try:
            while True:
                chunk = await asyncio.to_thread(stream.read, 65536)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(stream.close)

    # -- Write methods (materialize first) ---------------------------------

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content to a file."""
        raw = await _materialize(content)
        return await asyncio.to_thread(self._sync.write, path, raw, overwrite=overwrite, metadata=metadata)

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content atomically via temp file + rename."""
        raw = await _materialize(content)
        return await asyncio.to_thread(self._sync.write_atomic, path, raw, overwrite=overwrite, metadata=metadata)

    # -- Iterator methods (ASYNC-032) --------------------------------------

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        """List files under *path*."""
        items = await asyncio.to_thread(
            lambda: list(self._sync.list_files(path, recursive=recursive, max_depth=max_depth))
        )
        for item in items:
            yield item

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """List immediate subfolders under *path*."""
        items = await asyncio.to_thread(lambda: list(self._sync.list_folders(path)))
        for item in items:
            yield item

    async def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Match files against a glob pattern."""
        items = await asyncio.to_thread(lambda: list(self._sync.glob(pattern)))
        for item in items:
            yield item

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield both files and folders under *path*."""
        items = await asyncio.to_thread(lambda: list(self._sync.iter_children(path)))
        for item in items:
            yield item

    # -- Lifecycle (ASYNC-035) ---------------------------------------------

    async def aclose(self) -> None:
        """Release resources held by the wrapped backend."""
        await asyncio.to_thread(self._sync.close)
