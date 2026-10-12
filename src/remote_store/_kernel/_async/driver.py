"""The async driver protocol and its optional protocols.

A driver maps one-to-one onto its wire and carries no path, root, type,
closed or mapping logic: every key it receives is canonical, and the
kernel decides everything the contract states once. Each optional protocol is
detected per instance with ``isinstance`` at kernel construction.

``_sync/driver.py`` is generated from this file; edit this one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from datetime import datetime

    from remote_store._capabilities import CapabilitySet
    from remote_store._errors import RemoteStoreError
    from remote_store._kernel._async._io import Content, ReadStream
    from remote_store._kernel._model import Entry, Op, Page, PutResult
    from remote_store._resolution import ResolutionPlan

T = TypeVar("T")


@runtime_checkable
class AsyncDriver(Protocol):
    """The fourteen required primitives and the six declared attributes.

    Two more attributes are optional and read with defaults: ``stream_catch``,
    the exception types a stream from ``get`` raises beyond ``OSError`` and
    ``EOFError``, and ``size_probe``, a ``SEEK_END`` resolver for that stream.
    """

    name: str
    namespace: Literal["flat", "hierarchical"]
    parents: Literal["none", "implicit", "explicit"]
    capabilities: CapabilitySet
    put_is_atomic: bool
    close_is_terminal: bool

    async def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        """The node at *key*, file or folder, or ``None`` when absent.

        ``follow_links=False`` is ``delete_folder``'s view: a link is then a
        non-folder entry, whatever it points to.
        """
        ...

    async def get(self, key: str) -> ReadStream:
        """Open the file at *key* for reading."""
        ...

    async def put(
        self,
        key: str,
        content: Content,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        """Write the file at *key*; refuse an existing one unless *overwrite*."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the file at *key*."""
        ...

    async def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: object | None = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        """One page of what lies under folder *prefix* (``""`` is the root).

        With ``delimiter="/"`` the page holds the immediate files and the
        immediate subfolders as ``prefixes``; with ``None`` it holds every file
        under *prefix*, and the next page is reached through ``cursor``.
        """
        ...

    async def probe(self) -> None:
        """Health check; must touch the container."""
        ...

    async def aclose(self) -> None:
        """Release the driver's resources."""
        ...

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        """Map a native exception raised in scope *op* to a typed error."""
        ...

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        """Whether *exc* says the bucket, container or table is absent."""
        ...

    def connection_dead(self, exc: BaseException) -> bool:
        """Whether *exc* says the connection is dead.

        Pure inspection of *exc*, no I/O: the sync ``read`` stream passes it as
        ``is_fatal`` and skips the close of a stream it condemned.
        """
        ...

    def unwrap(self, type_hint: type[T]) -> T:
        """The native handle, when it is of *type_hint*."""
        ...

    def native_path(self, key: str) -> str:
        """The native address of *key*; total."""
        ...

    def to_key(self, native_path: str) -> str:
        """The key a native address names; total."""
        ...

    def resolve(self, key: str) -> ResolutionPlan:
        """How *key* maps to storage; no I/O."""
        ...


@runtime_checkable
class AsyncWriteHandle(Protocol):
    """A wire-side temporary that becomes the file on ``commit``."""

    async def write(self, data: bytes) -> None:
        """Append *data*."""
        ...

    async def commit(self) -> PutResult:
        """Promote the temporary to its key."""
        ...

    async def abort(self) -> None:
        """Discard the temporary; the key is untouched."""
        ...


@runtime_checkable
class AsyncSupportsRangeRead(Protocol):
    """Ranged reads, which serve ``read_seekable``."""

    async def get_range(self, key: str, offset: int, length: int) -> bytes:
        """Up to *length* bytes of *key* from *offset*."""
        ...


@runtime_checkable
class AsyncSupportsOpenWrite(Protocol):
    """A wire-side temporary, which serves ``write_atomic`` and ``open_atomic``."""

    async def open_write(
        self,
        key: str,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> AsyncWriteHandle:
        """Open a temporary that ``commit`` promotes to *key*."""
        ...


@runtime_checkable
class AsyncSupportsAtomicMove(Protocol):
    """A move the wire performs whole; the kernel never sequences its checks."""

    async def move(self, src: str, dst: str, *, overwrite: bool) -> None:
        """Move the file *src* to *dst*."""
        ...


@runtime_checkable
class AsyncSupportsRename(Protocol):
    """A rename; ``rename_replaces`` says whether it may replace *dst* atomically."""

    rename_replaces: bool

    async def rename(self, src: str, dst: str, *, replace: bool) -> None:
        """Rename *src* to *dst*, replacing a file there only when *replace*.

        Refuses a folder at *dst*, *replace* or not, without changing
        anything, as ``rename(2)`` and ``os.replace`` do: the kernel's
        temp-and-rename write relies on it rather than probing first.
        """
        ...


@runtime_checkable
class AsyncSupportsCopy(Protocol):
    """A copy on the wire."""

    async def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        """Copy the file *src* to *dst*."""
        ...


@runtime_checkable
class AsyncSupportsDeleteTree(Protocol):
    """A tree delete in one call."""

    async def delete_tree(self, key: str) -> None:
        """Remove the folder at *key* and everything under it.

        Refuses a file or an absent key without removing anything.
        """
        ...


@runtime_checkable
class AsyncSupportsRemoveFolder(Protocol):
    """Removal of one empty folder; required with folder objects."""

    async def remove_folder(self, key: str) -> None:
        """Remove the empty folder at *key*.

        Refuses a non-empty folder, a file or an absent key without removing
        it, in one step where the wire has one.
        """
        ...


@runtime_checkable
class AsyncSupportsEnsureParents(Protocol):
    """Parent creation, called before a write when ``parents == "explicit"``."""

    async def ensure_parents(self, key: str) -> None:
        """Create every missing folder above *key*."""
        ...


@runtime_checkable
class AsyncSupportsFolderStats(Protocol):
    """A native aggregate for ``get_folder_info``, the value the kernel would compute."""

    async def folder_stats(self, prefix: str) -> tuple[int, int, datetime | None]:
        """File count, total size and latest known time under *prefix*."""
        ...


@runtime_checkable
class AsyncSupportsGlob(Protocol):
    """Native ``glob``; without it a driver must not declare ``GLOB``."""

    def glob(self, pattern: str) -> AsyncIterator[Entry]:
        """The files matching the canonical *pattern*."""
        ...
