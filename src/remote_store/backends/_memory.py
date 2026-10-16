"""In-memory backend: a driver over a tree, zero dependencies, no I/O."""

from __future__ import annotations

import io
import threading
from typing import TYPE_CHECKING, BinaryIO, ClassVar, Literal, TypeVar

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported, RemoteStoreError
from remote_store._kernel._sync.driver import Driver
from remote_store._kernel.backend import DriverBackend
from remote_store._path import strip_root
from remote_store._resolution import ResolutionPlan
from remote_store.backends._memory_tree import MemoryTree

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from remote_store._kernel._model import Entry, Op, Page, PutResult
    from remote_store._kernel._sync._io import Content

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB, Capability.LAZY_READ})


class MemoryDriver(Driver):
    """The sync Memory driver: the tree's primitives, each under one ``threading.Lock``.

    The contract kernel validates and normalises every key before it reaches
    a primitive, decides the root and types every refusal; the driver only
    reads and changes the tree. It declares no ``probe``, inheriting the
    driver protocol's no-op: an in-memory store is always healthy.

    Optional protocols: ``open_write`` (a buffer in memory, so ``open_atomic``
    never spills to disk), an atomic ``move``, ``copy``, ``delete_tree``,
    ``remove_folder`` and ``folder_stats``.
    """

    name: str = "memory"
    namespace: Literal["flat", "hierarchical"] = "hierarchical"
    parents: Literal["none", "implicit", "explicit"] = "implicit"
    put_is_atomic: bool = True
    close_is_terminal: bool = False

    def __init__(self, capabilities: CapabilitySet = _ALL_CAPABILITIES) -> None:
        """*capabilities* narrows what is declared; construction refuses a set the protocols cannot back."""
        self.capabilities: CapabilitySet = capabilities
        self._tree = MemoryTree()
        self._lock = threading.Lock()

    @property
    def counts(self) -> tuple[int, int]:
        """The number of files and of folders the tree holds.

        Read without the lock, which is not reentrant: ``repr`` reads these, and a
        debugger may call it from a thread paused inside a locked step. So under
        concurrent writers a read may show a step in progress (the two counts out
        of step with each other); it is a display figure, not a snapshot.
        """
        return self._tree.file_count, self._tree.folder_count

    # region: required primitives

    def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        with self._lock:
            return self._tree.stat(key)

    def get(self, key: str) -> BinaryIO:
        """A stream over a copy of the stored bytes: the value materialises in memory."""
        with self._lock:
            data = bytes(self._tree.file(key).data)
        return io.BytesIO(data)

    def put(
        self,
        key: str,
        content: Content,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        # Buffer the whole body outside the lock, then swap it in under the lock.
        raw = bytearray(content) if isinstance(content, bytes) else _drain(content)
        with self._lock:
            return self._tree.put(key, raw, overwrite=overwrite, metadata=metadata)

    def delete(self, key: str) -> None:
        with self._lock:
            self._tree.delete(key)

    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: object | None = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        # One locked collect and no cursor, so a listing is one snapshot (MEM-025).
        with self._lock:
            return self._tree.list_page(prefix, delimiter=delimiter)

    def close(self) -> None:
        """Nothing to release; the store stays usable."""

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        # The tree raises only typed errors; the kernel asks only about content put cannot read (MEM-020).
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

    def open_write(self, key: str, *, overwrite: bool, metadata: Mapping[str, str] | None) -> _MemoryWriteHandle:
        """A buffer in memory that ``commit`` stores at *key* in one locked step.

        Refuses on open what the commit would refuse now, so ``open_atomic``
        fails before its body runs; the commit checks again under the lock.
        """
        with self._lock:
            self._tree.check_target(key, overwrite=overwrite)
        return _MemoryWriteHandle(self, key, overwrite, metadata)

    def move(self, src: str, dst: str, *, overwrite: bool) -> None:
        with self._lock:
            self._tree.move(src, dst, overwrite=overwrite)

    def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        with self._lock:
            self._tree.copy(src, dst, overwrite=overwrite)

    def delete_tree(self, key: str) -> None:
        with self._lock:
            self._tree.delete_tree(key)

    def remove_folder(self, key: str) -> None:
        with self._lock:
            self._tree.remove_folder(key)

    def folder_stats(self, prefix: str) -> tuple[int, int, datetime | None]:
        with self._lock:
            return self._tree.folder_stats(prefix)

    # endregion


class _MemoryWriteHandle:
    """The wire temporary of ``open_write``: bytes accumulate in memory, never on disk."""

    __slots__ = ("_buf", "_driver", "_key", "_metadata", "_overwrite")

    def __init__(self, driver: MemoryDriver, key: str, overwrite: bool, metadata: Mapping[str, str] | None) -> None:
        self._driver, self._key, self._overwrite, self._metadata = driver, key, overwrite, metadata
        self._buf = bytearray()

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    def commit(self) -> PutResult:
        return self._driver.put(self._key, bytes(self._buf), overwrite=self._overwrite, metadata=self._metadata)

    def abort(self) -> None:
        self._buf.clear()


def _drain(content: BinaryIO) -> bytearray:
    raw = bytearray()
    while chunk := content.read(65536):
        raw.extend(chunk)
    return raw


class MemoryBackend(DriverBackend):
    """In-memory backend: a tree-indexed store on the contract kernel.

    Zero dependencies, no filesystem access, no network. Designed as a
    drop-in backend for unit testing, interactive exploration, and
    documentation examples.

    All capabilities except ``GLOB`` and ``LAZY_READ`` are supported. Every
    primitive runs under the backend's one lock, so ``write``,
    ``write_atomic``, ``move`` and ``copy`` are atomic with respect to
    concurrent callers in the same process (``ATOMIC_MOVE`` is advertised).
    Reads materialise the value: a stream wraps a copy of the stored bytes.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ALL_CAPABILITIES
    close_is_terminal: ClassVar[bool] = False

    def __init__(self) -> None:
        # The class's CAPABILITIES is what is declared, so a subclass narrowing it
        # narrows what the store gates on.
        super().__init__(MemoryDriver(type(self).CAPABILITIES))

    def __repr__(self) -> str:
        driver = self._driver
        assert isinstance(driver, MemoryDriver)
        files, folders = driver.counts
        return f"MemoryBackend(files={files}, folders={folders})"
