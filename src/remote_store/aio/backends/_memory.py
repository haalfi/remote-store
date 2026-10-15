"""Async in-memory backend: a driver over the shared tree, zero dependencies, no I/O."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar, Literal, TypeVar

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported, RemoteStoreError
from remote_store._kernel._async.driver import AsyncDriver
from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._path import strip_root
from remote_store._resolution import ResolutionPlan
from remote_store.backends._memory import MemoryBackend
from remote_store.backends._memory_tree import MemoryTree

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from datetime import datetime

    from remote_store._kernel._async._io import Content
    from remote_store._kernel._model import Entry, Op, Page, PutResult

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB})


class AsyncMemoryDriver(AsyncDriver):
    """The async Memory driver: the shared tree's primitives, each under one ``asyncio.Lock``.

    The same tree and the same primitives as ``MemoryDriver``; the lock, the
    stream shape, the ``name`` and the default capabilities (``LAZY_READ``
    here) differ. It declares no ``probe``, inheriting the driver protocol's
    no-op: an in-memory store is always healthy.
    """

    name: str = "async-memory"
    namespace: Literal["flat", "hierarchical"] = "hierarchical"
    parents: Literal["none", "implicit", "explicit"] = "implicit"
    put_is_atomic: bool = True
    close_is_terminal: bool = False

    def __init__(self, capabilities: CapabilitySet = _ALL_CAPABILITIES) -> None:
        """*capabilities* narrows what is declared; the kernel refuses a set the driver cannot back."""
        self.capabilities: CapabilitySet = capabilities
        self._tree = MemoryTree()
        self._lock = asyncio.Lock()

    @property
    def counts(self) -> tuple[int, int]:
        """The number of files and of folders the tree holds.

        Read without the lock: two integers, each changed only inside one
        locked primitive that never awaits, so no read sees a half step.
        """
        return self._tree.file_count, self._tree.folder_count

    # region: required primitives

    async def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        async with self._lock:
            return self._tree.stat(key)

    async def get(self, key: str) -> AsyncIterator[bytes]:
        """The stored bytes as one chunk, copied under the lock."""
        async with self._lock:
            data = bytes(self._tree.file(key).data)
        return _one_chunk(data)

    async def put(
        self,
        key: str,
        content: Content,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        # Materialise the body outside the lock, then swap it in under the lock.
        if isinstance(content, bytes):
            raw = bytearray(content)
        else:
            raw = bytearray()
            async for chunk in content:
                raw.extend(chunk)
        async with self._lock:
            return self._tree.put(key, raw, overwrite=overwrite, metadata=metadata)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._tree.delete(key)

    async def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: object | None = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        # One locked collect and no cursor, so a listing is one snapshot (MEM-025).
        async with self._lock:
            return self._tree.list_page(prefix, delimiter=delimiter)

    async def aclose(self) -> None:
        """Nothing to release; the store stays usable."""

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        # The driver raises only typed errors, so the kernel never asks (MEM-020).
        return RemoteStoreError(f"{type(exc).__name__}: {exc}")

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        return False

    def connection_dead(self, exc: BaseException) -> bool:
        return False

    def unwrap(self, type_hint: type[T]) -> T:
        raise CapabilityNotSupported(
            f"Backend '{self.name}' does not expose native handle of type {type_hint.__name__}.",
            capability="unwrap",
            backend=self.name,
        )

    def native_path(self, key: str) -> str:
        return strip_root(key)

    def to_key(self, native_path: str) -> str:
        return native_path

    def resolve(self, key: str) -> ResolutionPlan:
        return ResolutionPlan(kind=self.name, backend=self.name, key=key, native_path=self.native_path(key), details={})

    # endregion

    # region: optional protocols

    async def open_write(
        self, key: str, *, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> _AsyncMemoryWriteHandle:
        """A buffer in memory that ``commit`` stores at *key* in one locked step.

        Refuses on open what the commit would refuse now; the commit checks
        again under the lock.
        """
        async with self._lock:
            self._tree.check_target(key, overwrite=overwrite)
        return _AsyncMemoryWriteHandle(self, key, overwrite, metadata)

    async def move(self, src: str, dst: str, *, overwrite: bool) -> None:
        async with self._lock:
            self._tree.move(src, dst, overwrite=overwrite)

    async def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        async with self._lock:
            self._tree.copy(src, dst, overwrite=overwrite)

    async def delete_tree(self, key: str) -> None:
        async with self._lock:
            self._tree.delete_tree(key)

    async def remove_folder(self, key: str) -> None:
        async with self._lock:
            self._tree.remove_folder(key)

    async def folder_stats(self, prefix: str) -> tuple[int, int, datetime | None]:
        async with self._lock:
            return self._tree.folder_stats(prefix)

    # endregion


class _AsyncMemoryWriteHandle:
    """The wire temporary of ``open_write``: bytes accumulate in memory, never on disk."""

    __slots__ = ("_buf", "_driver", "_key", "_metadata", "_overwrite")

    def __init__(
        self, driver: AsyncMemoryDriver, key: str, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> None:
        self._driver, self._key, self._overwrite, self._metadata = driver, key, overwrite, metadata
        self._buf = bytearray()

    async def write(self, data: bytes) -> None:
        self._buf.extend(data)

    async def commit(self) -> PutResult:
        return await self._driver.put(self._key, bytes(self._buf), overwrite=self._overwrite, metadata=self._metadata)

    async def abort(self) -> None:
        self._buf.clear()


async def _one_chunk(data: bytes) -> AsyncIterator[bytes]:
    yield data


class AsyncMemoryBackend(AsyncDriverBackend):
    """In-memory async backend: a tree-indexed store on the contract kernel.

    Zero dependencies, no filesystem access, no network. Designed as a
    drop-in async backend for unit testing, interactive exploration, and
    documentation examples.

    Supports all capabilities except ``GLOB``.

    Note:
        ``LAZY_READ`` is included here but absent from ``MemoryBackend``
        (the sync mirror). The sync backend buffers fully in memory; the
        async backend can yield chunks incrementally. The ``mirrors``
        graph edge between the two does not imply capability parity.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ALL_CAPABILITIES
    __mirror__: ClassVar[type[MemoryBackend]] = MemoryBackend
    close_is_terminal: ClassVar[bool] = False

    def __init__(self) -> None:
        # The class's CAPABILITIES is what is declared, so a subclass narrowing it
        # narrows what the store gates on.
        super().__init__(AsyncMemoryDriver(type(self).CAPABILITIES))

    def __repr__(self) -> str:
        driver = self._driver
        assert isinstance(driver, AsyncMemoryDriver)
        files, folders = driver.counts
        return f"AsyncMemoryBackend(files={files}, folders={folders})"
