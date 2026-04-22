"""Fixtures for async API tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store.aio import AsyncBackend, AsyncMemoryBackend, AsyncStore, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store.aio._types import AsyncWritableContent


@pytest.fixture(params=["native", "adapted"], ids=["native", "adapted"])
def async_backend(request: pytest.FixtureRequest) -> AsyncMemoryBackend | SyncBackendAdapter:
    """Async backend -- both native AsyncMemoryBackend and adapted sync MemoryBackend."""
    if request.param == "native":
        return AsyncMemoryBackend()
    return SyncBackendAdapter(MemoryBackend())


@pytest.fixture
def async_store(async_backend: AsyncMemoryBackend | SyncBackendAdapter) -> AsyncStore:
    """AsyncStore backed by dual-parameterized backend."""
    return AsyncStore(async_backend, root_path="data")


@pytest.fixture
def native_memory() -> AsyncMemoryBackend:
    """Native AsyncMemoryBackend (for memory-specific tests)."""
    return AsyncMemoryBackend()


@pytest.fixture
def native_store(native_memory: AsyncMemoryBackend) -> AsyncStore:
    """AsyncStore with native AsyncMemoryBackend."""
    return AsyncStore(native_memory, root_path="data")


class RestrictedAsyncBackend(AsyncBackend):
    """Async backend wrapper that excludes specific capabilities for testing.

    Inherits from ``AsyncBackend`` and delegates all operations to the inner
    backend, overriding only ``capabilities`` to return a restricted
    ``CapabilitySet`` starting from the inner backend's declared capabilities.
    """

    def __init__(self, backend: AsyncBackend, exclude: set[Capability]) -> None:
        self._inner = backend
        self._caps = CapabilitySet(set(backend.capabilities) - exclude)

    @property
    def capabilities(self) -> CapabilitySet:
        return self._caps

    @property
    def name(self) -> str:
        return self._inner.name

    async def exists(self, path: str) -> bool:
        return await self._inner.exists(path)

    async def is_file(self, path: str) -> bool:
        return await self._inner.is_file(path)

    async def is_folder(self, path: str) -> bool:
        return await self._inner.is_folder(path)

    async def read(self, path: str) -> AsyncIterator[bytes]:
        async for chunk in self._inner.read(path):
            yield chunk

    async def read_bytes(self, path: str) -> bytes:
        return await self._inner.read_bytes(path)

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return await self._inner.write(path, content, overwrite=overwrite, metadata=metadata)

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return await self._inner.write_atomic(path, content, overwrite=overwrite, metadata=metadata)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        await self._inner.delete(path, missing_ok=missing_ok)

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        await self._inner.delete_folder(path, recursive=recursive, missing_ok=missing_ok)

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        async for info in self._inner.list_files(path, recursive=recursive, max_depth=max_depth):
            yield info

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        async for entry in self._inner.list_folders(path):
            yield entry

    async def get_file_info(self, path: str) -> FileInfo:
        return await self._inner.get_file_info(path)

    async def get_folder_info(self, path: str) -> FolderInfo:
        return await self._inner.get_folder_info(path)

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        await self._inner.move(src, dst, overwrite=overwrite)

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        await self._inner.copy(src, dst, overwrite=overwrite)
