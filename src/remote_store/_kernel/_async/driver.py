"""The async driver protocol and its optional protocols.

A driver maps one-to-one onto its wire and carries no path, root, type,
closed or mapping logic: every key an operation hands it is canonical, and
the kernel decides everything the contract states once. The addressing
members (``native_path``, ``resolve``) are the exception: they also receive
a key the key rule refuses, raw, and must stay total for it. Each optional protocol is
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
    """The fourteen primitives and the six declared attributes.

    All fourteen are required: construction refuses a driver that lacks one, or
    inherits this protocol's empty body for one, which would answer ``None``
    instead of acting. ``probe`` alone may be inherited, its body being the
    exemption from probing.

    Two more attributes are optional and read with defaults: ``stream_catch``,
    the exception types a stream from ``get`` raises beyond ``OSError`` and
    ``EOFError``, and ``size_probe``, a ``SEEK_END`` resolver for that stream,
    which only the sync runtime reads, since only its stream seeks.

    ``namespace`` says what the wire can hold and ``stat`` can see: on
    ``"flat"`` the wire would let a key shadow a prefix or sit under a file,
    so the kernel checks before every write that it does neither, and
    ``stat`` is blind to a prefix; on ``"hierarchical"`` neither can happen,
    so every write primitive refuses a folder at its key, or a file above it,
    without changing anything, in whatever shape the wire has; the kernel
    types the refusal. ``parents`` says whether folders are objects. A flat driver with
    folder objects is refused at construction, since its ``stat`` could not
    see them, and so is an explicit one without ``ensure_parents``, which
    could not create a write's parents.
    """

    name: str
    namespace: Literal["flat", "hierarchical"]
    parents: Literal["none", "implicit", "explicit"]
    capabilities: CapabilitySet
    put_is_atomic: bool
    close_is_terminal: bool

    async def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        """The node at *key*, file or folder, or ``None`` when absent.

        On a flat wire it may be a lookup of the key alone, blind to a prefix
        and to whatever lies above the key: where a folder matters the kernel
        finds one there with one ``list_page(limit=1)``. With folder objects
        it returns the folder object at *key*. A miss may also be raised, as
        ``NotFound`` or ``InvalidPath`` (a POSIX ``stat`` below a file raises
        ENOTDIR).

        ``follow_links=False`` is the view of the calls that name the entry at
        their key (``delete``, a ``move`` source, ``delete_folder``): a link is
        then a non-folder entry, whatever it points to.
        """
        ...

    async def get(self, key: str) -> ReadStream:
        """Open the file at *key* for reading.

        Refuses an absent key, or one that is no file, in whatever shape the
        wire has; the kernel types the refusal. The stream ends where the
        client's own read reports the end of data, after any length or
        checksum check the client makes there, never at a byte count the
        driver keeps: a check that fails at the end is then a stream error.
        """
        ...

    async def put(
        self,
        key: str,
        content: Content,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        """Write the file at *key*; refuse an existing one unless *overwrite*.

        The refusal is one step on the wire where the wire has a conditional
        write, never a check followed by the write.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove the file at *key*; a link there is removed itself, never its target.

        Refuses an absent key, or one that is no file, without removing
        anything, in whatever shape the wire has; the kernel types the
        refusal. A wire whose delete succeeds for a missing key checks first.
        """
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

        A *prefix* that is a file, or lies under one, is refused in whatever
        shape the wire has, or lists nothing; the kernel reads a first-page
        refusal its probes confirm as no folder as an empty listing. A flat
        driver owes two more: its keys come in byte-lexicographic order, a
        prefix ``p`` ordered as ``p/``, so an item arrives before every key
        below it; and it answers ``NotFound`` or ``InvalidPath`` only when
        nothing lies under *prefix*, an absent container included, since no
        other call can tell a flat folder from nothing.

        ``follow_links=False`` is ``delete_folder``'s view: a link is a
        non-folder entry, listed as one and never descended into, and a link
        at *prefix* itself is no folder, so the call refuses it or lists
        nothing, never its target's entries. ``delete_folder`` deletes what
        this view lists, with no ``stat`` before the listing.
        """
        ...

    async def probe(self) -> None:
        """Health check; must touch the container.

        The protocol's own body does nothing, and a driver that subclasses the
        protocol without declaring ``probe`` inherits it: that is an exemption
        from probing, which only a store that is always healthy may take.
        """
        return None

    async def aclose(self) -> None:
        """Release the driver's resources.

        Idempotent: the kernel forwards every call, a repeated one included.
        """
        ...

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        """Map a native exception raised in scope *op* to a typed error."""
        ...

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        """Whether *exc* says the bucket, container or table is absent."""
        ...

    def connection_dead(self, exc: BaseException) -> bool:
        """Whether *exc* says the connection is dead.

        Pure inspection of *exc*, no I/O: a ``read`` stream skips the close of
        a stream it condemned, and a failed cleanup is logged with its verdict.
        True only for transport-level death, the socket or session gone, never
        for an error the next request on the same connection survives.
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
        """Promote the temporary to its key.

        Opened without ``overwrite``, a file at the key is refused here, as one
        step on the wire where the wire has a conditional write.
        """
        ...

    async def abort(self) -> None:
        """Discard the temporary; the key is untouched.

        Legal after a failed ``commit`` and idempotent. What it raises the
        kernel logs, never raises: the write's own error stands.
        """
        ...


@runtime_checkable
class AsyncSupportsRangeRead(Protocol):
    """Ranged reads, which serve ``read_seekable``; only the sync runtime has one."""

    async def get_range(self, key: str, offset: int, length: int) -> bytes:
        """Up to *length* bytes of *key* from *offset*."""
        ...


@runtime_checkable
class AsyncSupportsOpenWrite(Protocol):
    """A wire-side temporary for ``write_atomic``, and for ``open_atomic`` in the sync runtime, the only one with it."""

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
        """Move the file *src* to *dst*.

        Refuses an absent *src*, or one that is no file, without changing
        anything, in whatever shape the wire has; the kernel types the refusal.
        On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or
        not, without changing anything. On a flat one the kernel has already
        checked that *dst* is no folder and lies below no file.
        """
        ...


@runtime_checkable
class AsyncSupportsRename(Protocol):
    """A rename; ``rename_replaces`` says whether it may replace *dst* atomically."""

    rename_replaces: bool

    async def rename(self, src: str, dst: str, *, replace: bool) -> None:
        """Rename *src* to *dst*, replacing a file there only when *replace*.

        Refuses an absent *src*, or one that is no file, without changing
        anything, in whatever shape the wire has; the kernel types the refusal.
        On a hierarchical namespace, refuses a folder at *dst*, *replace* or
        not, without changing anything, as ``rename(2)`` and ``os.replace``
        do: the kernel's temp-and-rename write relies on it rather than
        probing first. On a flat one the kernel has already checked that
        *dst* is no folder and lies below no file.
        """
        ...


@runtime_checkable
class AsyncSupportsCopy(Protocol):
    """A copy on the wire."""

    async def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        """Copy the file *src* to *dst*.

        Refuses an absent *src*, or one that is no file, without changing
        anything, in whatever shape the wire has; the kernel types the refusal.
        On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or
        not, without changing anything. On a flat one the kernel has already
        checked that *dst* is no folder and lies below no file.
        """
        ...


@runtime_checkable
class AsyncSupportsDeleteTree(Protocol):
    """A tree delete in one call."""

    async def delete_tree(self, key: str) -> None:
        """Remove the folder at *key* and everything under it.

        Where folder objects exist (``parents`` is not ``"none"``), refuses a
        file, a link (a non-folder entry, never traversed) or an absent key
        without removing anything, and removes a link below *key* as an entry
        without following it. With
        ``parents == "none"`` it removes what lies under the prefix ``key/``
        and leaves a file named by *key* itself.
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
    """Parent creation, called before a write; required when ``parents == "explicit"``."""

    async def ensure_parents(self, key: str) -> None:
        """Create every missing folder above *key*.

        Refuses a file above *key* without creating anything past it, in
        whatever shape the wire has (``os.makedirs`` raises EEXIST); the kernel
        types the refusal. *key* itself is the write's to refuse.
        """
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
