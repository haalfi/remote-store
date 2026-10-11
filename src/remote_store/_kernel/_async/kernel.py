"""The async contract kernel's core: every member both runtimes share.

``_AsyncKernelCore`` implements the ``AsyncBackend`` surface over an
``AsyncDriver`` and owns, once, what the design assigns to the kernel: the
key rule, the root and closed guards, the error-mapping choke point,
the absent-container answers, the wrong-type probes, the listing bound, the
write, move and copy syntheses and the ``delete_folder`` sequence.
``AsyncDriverBackend`` adds ``read``, the one member whose shape is the
runtime's own.

``_sync/kernel.py`` is generated from this file by
``scripts/gen_sync_kernel.py``; edit this one, then regenerate.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import uuid
from typing import TYPE_CHECKING, Literal

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._kernel import _keys
from remote_store._kernel._aggregate import FolderTally, within_depth
from remote_store._kernel._async import _io
from remote_store._kernel._async.driver import (
    AsyncSupportsAtomicMove,
    AsyncSupportsCopy,
    AsyncSupportsDeleteTree,
    AsyncSupportsEnsureParents,
    AsyncSupportsFolderStats,
    AsyncSupportsGlob,
    AsyncSupportsOpenWrite,
    AsyncSupportsRangeRead,
    AsyncSupportsRemoveFolder,
    AsyncSupportsRename,
)
from remote_store._kernel._model import Op
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult, _known_modified_at
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType
    from typing import TypeVar

    from remote_store._capabilities import CapabilitySet
    from remote_store._kernel._async.driver import AsyncDriver
    from remote_store._kernel._model import Entry, Page, PutResult
    from remote_store._resolution import ResolutionPlan

    T = TypeVar("T")

_log = logging.getLogger("remote_store._kernel")

# Operations whose absent-container answer is not the kernel's to decide:
# BE-021 § Reach declines `write`, and the identity scopes stay the driver's
# (ADR-0038). Every other operation reads an absent container as an absent path.
_CLASSIFY_DECIDES = frozenset({Op.WRITE, Op.WRITE_ATOMIC, Op.OPEN_ATOMIC, Op.PROBE, Op.IDENTITY, Op.MONITOR, Op.CLOSE})


def _check_construction(driver: AsyncDriver) -> None:
    """Refuse a driver whose declarations its protocols cannot back.

    Construction is not an operation, so this raises ``ValueError``, not a
    mapped error; wrapping construction is deferred to D3 step 3 (OQ5).
    """
    if driver.parents != "none" and not isinstance(driver, AsyncSupportsRemoveFolder):
        msg = f"driver {driver.name!r} has folder objects (parents={driver.parents!r}) but no remove_folder"
        raise ValueError(msg)
    caps = driver.capabilities
    replaces = isinstance(driver, AsyncSupportsRename) and driver.rename_replaces
    if caps.supports(Capability.ATOMIC_MOVE) and not (isinstance(driver, AsyncSupportsAtomicMove) or replaces):
        msg = f"driver {driver.name!r} declares ATOMIC_MOVE without an atomic move or a replacing rename"
        raise ValueError(msg)
    if caps.supports(Capability.ATOMIC_WRITE) and not (
        driver.put_is_atomic or isinstance(driver, AsyncSupportsOpenWrite) or replaces
    ):
        msg = f"driver {driver.name!r} declares ATOMIC_WRITE without an atomic put, open_write or a replacing rename"
        raise ValueError(msg)
    if caps.supports(Capability.GLOB) and not isinstance(driver, AsyncSupportsGlob):
        msg = f"driver {driver.name!r} declares GLOB without glob"
        raise ValueError(msg)
    if caps.supports(Capability.COPY) and not isinstance(driver, AsyncSupportsCopy):
        msg = f"driver {driver.name!r} declares COPY without copy"
        raise ValueError(msg)


def _temp_key(key: str) -> str:
    """A hidden sibling of *key* for a temp-and-promote or a displaced file."""
    parent, leaf = _keys.parent(key), _keys.name(key)
    temp = f".{leaf}.rs-{uuid.uuid4().hex[:12]}.tmp"
    return f"{parent}/{temp}" if parent else temp


def _write_result(target: RemotePath, result: PutResult) -> WriteResult:
    return WriteResult(
        path=target,
        size=result.size,
        source=result.source,
        digest=result.digest,
        etag=result.etag,
        version_id=result.version_id,
        last_modified=result.last_modified,
        metadata=result.metadata,
    )


class _Omitted:
    """Counts listed keys the key rule omits, and logs them once per listing."""

    __slots__ = ("_count", "_first", "_name", "_where")

    def __init__(self, name: str, where: str) -> None:
        self._name, self._where = name, where
        self._count = 0
        self._first = ""

    def note(self, key: str) -> None:
        if not self._count:
            self._first = key
        self._count += 1

    def log(self) -> None:
        if self._count:
            _log.warning(
                "%s: omitted %d listed key(s) under %r that the key rule refuses or rewrites, e.g. %r",
                self._name,
                self._count,
                self._where,
                self._first,
            )


class _Choke:
    """The choke point: a native exception leaving the block is mapped once.

    A ``RemoteStoreError`` keeps its type; anything else goes through the
    driver's ``classify``. ``path``, ``backend`` and a blank message are then
    filled, and an absent container reads as an absent path where the
    kernel decides it. A ``BaseException``
    that is not an ``Exception``, and the end of an iteration, pass untouched.
    """

    __slots__ = ("_core", "_key", "_op")

    def __init__(self, core: _AsyncKernelCore, op: Op, key: str) -> None:
        self._core, self._op, self._key = core, op, key

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if exc is None or not isinstance(exc, Exception) or isinstance(exc, StopAsyncIteration):
            return False
        err = self._core._mapped(exc, self._op, self._key)
        if err is exc:
            return False
        raise err from exc


class _AsyncKernelCore:
    """The backend surface both runtimes share, over a driver.

    Args:
        driver: A built driver; each public class builds its own.
        reject_write_under_file_ancestor: Opt in to the file-ancestor walk
            before a write or a ``move``/``copy`` destination; off by
            default, as on every flat-namespace class today.

    Raises:
        ValueError: If the driver's declarations are not backed by its
            protocols, or it has folder objects and no ``remove_folder``.
    """

    def __init__(self, driver: AsyncDriver, *, reject_write_under_file_ancestor: bool = False) -> None:
        _check_construction(driver)
        self._driver = driver
        self._reject_under_file = reject_write_under_file_ancestor
        self._closed = False
        d = driver
        self._range: AsyncSupportsRangeRead | None = d if isinstance(d, AsyncSupportsRangeRead) else None
        self._open_write: AsyncSupportsOpenWrite | None = d if isinstance(d, AsyncSupportsOpenWrite) else None
        self._atomic_move: AsyncSupportsAtomicMove | None = d if isinstance(d, AsyncSupportsAtomicMove) else None
        self._rename: AsyncSupportsRename | None = d if isinstance(d, AsyncSupportsRename) else None
        self._copier: AsyncSupportsCopy | None = d if isinstance(d, AsyncSupportsCopy) else None
        self._tree: AsyncSupportsDeleteTree | None = d if isinstance(d, AsyncSupportsDeleteTree) else None
        self._remover: AsyncSupportsRemoveFolder | None = d if isinstance(d, AsyncSupportsRemoveFolder) else None
        self._parents_maker: AsyncSupportsEnsureParents | None = (
            d if isinstance(d, AsyncSupportsEnsureParents) and d.parents == "explicit" else None
        )
        self._stats: AsyncSupportsFolderStats | None = d if isinstance(d, AsyncSupportsFolderStats) else None
        self._globber: AsyncSupportsGlob | None = d if isinstance(d, AsyncSupportsGlob) else None

    # region: identity and addressing (forwarded; no closed guard, never raising for the key)

    @property
    def name(self) -> str:
        """The driver's name, which every mapped error carries as ``backend``."""
        return self._driver.name

    @property
    def capabilities(self) -> CapabilitySet:
        """The driver's declared capabilities; the kernel adds none."""
        return self._driver.capabilities

    def unwrap(self, type_hint: type[T]) -> T:
        """The driver's native handle."""
        return self._driver.unwrap(type_hint)

    def _address_key(self, path: str) -> str:
        # BE-030: a valid key is normalised; a refused one reaches the driver raw.
        return path if _keys.refusal(path) is not None else _keys.canonical(path)

    def native_path(self, path: str) -> str:
        """The native address of *path*: a valid key normalised, a refused one raw."""
        return self._driver.native_path(self._address_key(path))

    def to_key(self, native_path: str) -> str:
        """Forwarded unchanged: its input is an address, not a key."""
        return self._driver.to_key(native_path)

    def resolve(self, path: str) -> ResolutionPlan:
        """The driver's plan for *path*, keyed by the caller's spelling."""
        plan = self._driver.resolve(self._address_key(path))
        return dataclasses.replace(plan, key=path, native_path=self.native_path(path))

    # endregion

    # region: guards and the choke point

    def _choke(self, op: Op, key: str) -> _Choke:
        return _Choke(self, op, key)

    def _absent(self, exc: BaseException, op: Op) -> bool:
        try:
            return bool(self._driver.container_absent(exc, op=op))
        except Exception:  # noqa: BLE001 - a predicate that cannot answer says no
            return False

    def _mapped(self, exc: Exception, op: Op, key: str) -> RemoteStoreError:
        """Type *exc* once, and guarantee its ``path``, ``backend`` and message."""
        err: RemoteStoreError
        if isinstance(exc, RemoteStoreError):
            err = exc
        else:
            try:
                err = self._driver.classify(exc, op=op, key=key)
            except Exception as failure:  # noqa: BLE001 - the choke point must not leak a classifier's own error
                err = RemoteStoreError(
                    f"{type(exc).__name__} during {op.value}; classify raised {type(failure).__name__}: {failure}"
                )
            if not isinstance(err, RemoteStoreError):
                err = RemoteStoreError(f"{type(exc).__name__} during {op.value}")
        if op not in _CLASSIFY_DECIDES and not isinstance(err, NotFound) and self._absent(exc, op):
            err = NotFound(f"Not found (container absent): {key}", path=key, backend=self.name)
        if err.path is None:
            err.path = key
        if err.backend is None:
            err.backend = self.name
        if not (err.args and str(err.args[0])):
            err.args = (f"{type(exc).__name__} during {op.value}",)
        return err

    def _guard(self) -> None:
        # BE-020: only a terminal close posture refuses use after close.
        if self._closed and self._driver.close_is_terminal:
            raise BackendUnavailable(f"Backend '{self.name}' is closed", backend=self.name)

    def _key(self, path: str) -> str:
        why = _keys.refusal(path)
        if why is not None:
            raise InvalidPath(why, path=path, backend=self.name)
        return _keys.canonical(path)

    def _file_key(self, path: str) -> str:
        key = self._key(path)
        if not key:
            raise InvalidPath("The store root is a folder, not a file", path=path, backend=self.name)
        return key

    def _write_key(self, path: str) -> str:
        key = self._key(path)
        if not key:
            raise InvalidPath("Cannot write to the store root", path=path, backend=self.name)
        return key

    # endregion

    # region: probes and helpers

    async def _stat(self, op: Op, key: str, *, follow_links: bool = True) -> Entry | None:
        """A determinant ``stat``: its failure is the operation's failure."""
        with self._choke(op, key):
            return await self._driver.stat(key, follow_links=follow_links)

    async def _stat_open(self, op: Op, key: str) -> Entry | None:
        """An error-path ``stat``: fail-open, so a raising probe reads as no answer."""
        try:
            return await self._stat(op, key)
        except RemoteStoreError:
            return None

    async def _folder_is_wrong_type(self, err: RemoteStoreError, op: Op, key: str) -> None:
        """After a ``NotFound`` from a file-shaped call: a folder there is ``InvalidPath``."""
        entry = await self._stat_open(op, key)
        if entry is not None and entry.kind == "folder":
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name) from err

    def _file_info(self, entry: Entry) -> FileInfo:
        return FileInfo(
            path=RemotePath(entry.key),
            name=_keys.name(entry.key),
            size=entry.size,
            modified_at=entry.modified_at,
            digest=entry.digest,
            etag=entry.etag,
            content_type=entry.content_type,
            metadata=entry.metadata,
            extra=dict(entry.extra),
        )

    async def _pages(self, op: Op, key: str, delimiter: str | None) -> AsyncIterator[Page]:
        """Every page of a listing, with the first-page bound.

        A ``NotFound`` or ``InvalidPath`` before the operation's first page is
        an empty listing: an absent container, an absent prefix or a non-folder
        holds nothing. After it, the same error reports a change under the
        scan and propagates. The bound is keyed on the page, never on what the
        operation yielded from it.
        """
        cursor: object | None = None
        seen = False
        while True:
            try:
                with self._choke(op, key):
                    page = await self._driver.list_page(key, delimiter=delimiter, cursor=cursor)
            except (NotFound, InvalidPath):
                if seen:
                    raise
                return
            seen = True
            yield page
            cursor = page.cursor
            if cursor is None:
                return

    # endregion

    # region: probes (BE-004, BE-005, BE-029)

    async def _node(self, op: Op, path: str) -> Entry | None:
        # BE-021: the three probes return False on a traversal error rather than raise.
        self._guard()
        key = self._key(path)
        try:
            return await self._stat(op, key)
        except (NotFound, InvalidPath):
            return None

    async def exists(self, path: str) -> bool:
        """Whether a file or folder exists at *path*; the root always does."""
        self._guard()
        if not self._key(path):
            return True
        return await self._node(Op.EXISTS, path) is not None

    async def is_file(self, path: str) -> bool:
        """Whether *path* is an existing file; never for the root."""
        self._guard()
        if not self._key(path):
            return False
        entry = await self._node(Op.IS_FILE, path)
        return entry is not None and entry.kind == "file"

    async def is_folder(self, path: str) -> bool:
        """Whether *path* is an existing folder; always for the root."""
        self._guard()
        if not self._key(path):
            return True
        entry = await self._node(Op.IS_FOLDER, path)
        return entry is not None and entry.kind == "folder"

    # endregion

    # region: file-shaped operations

    async def _open(self, path: str, op: Op) -> tuple[str, _io.ReadStream]:
        """Open *path* for a read: guards, the key rule, ``get``, the wrong-type probe."""
        self._guard()
        key = self._file_key(path)
        try:
            with self._choke(op, key):
                stream = await self._driver.get(key)
        except NotFound as err:
            await self._folder_is_wrong_type(err, op, key)
            raise
        return key, stream

    async def read_bytes(self, path: str) -> bytes:
        """The whole content of the file at *path*."""
        key, stream = await self._open(path, Op.READ_BYTES)
        with self._choke(Op.READ_BYTES, key):
            return await _io.read_all(stream)

    async def get_file_info(self, path: str) -> FileInfo:
        """The file's metadata; a folder is ``InvalidPath``, absence ``NotFound``."""
        self._guard()
        key = self._file_key(path)
        entry = await self._stat(Op.GET_FILE_INFO, key)
        if entry is None:
            raise NotFound(f"Not found: {key}", path=key, backend=self.name)
        if entry.kind != "file":
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name)
        return self._file_info(entry)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Remove the file at *path*; type mismatch outranks *missing_ok*."""
        self._guard()
        key = self._file_key(path)
        try:
            with self._choke(Op.DELETE, key):
                await self._driver.delete(key)
        except NotFound as err:
            await self._folder_is_wrong_type(err, Op.DELETE, key)
            if missing_ok:
                return
            raise

    # endregion

    # region: writes

    async def _prepare_write(self, op: Op, key: str) -> None:
        """The opt-in file-ancestor walk, then the parents an explicit driver needs."""
        if self._reject_under_file:
            for ancestor in _keys.ancestors(key):
                # BUG-292's policy: only a confirmed miss is "no ancestor".
                try:
                    entry = await self._stat(op, ancestor)
                except NotFound:
                    entry = None
                if entry is not None and entry.kind == "file":
                    raise InvalidPath(f"An ancestor of the path is a file: {ancestor}", path=key, backend=self.name)
        if self._parents_maker is not None and "/" in key:
            with self._choke(op, key):
                await self._parents_maker.ensure_parents(key)

    async def _put(
        self, op: Op, key: str, content: _io.Content, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> PutResult:
        try:
            with self._choke(op, key):
                return await self._driver.put(key, content, overwrite=overwrite, metadata=metadata)
        except NotFound as err:
            await self._folder_is_wrong_type(err, op, key)
            raise

    async def write(
        self,
        path: str,
        content: _io.Content,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write the file at *path*; the root is refused before any transfer."""
        self._guard()
        key = self._write_key(path)
        target = RemotePath(key)  # built before the driver commits (BE-030 step 5)
        await self._prepare_write(Op.WRITE, key)
        return _write_result(target, await self._put(Op.WRITE, key, content, overwrite, metadata))

    async def write_atomic(
        self,
        path: str,
        content: _io.Content,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write atomically: ``put`` where it is atomic, else a wire temporary, else temp and rename."""
        self._guard()
        key = self._write_key(path)
        target = RemotePath(key)
        await self._prepare_write(Op.WRITE_ATOMIC, key)
        if self._driver.put_is_atomic:
            result = await self._put(Op.WRITE_ATOMIC, key, content, overwrite, metadata)
        elif self._open_write is not None:
            result = await self._write_through_handle(Op.WRITE_ATOMIC, key, content, overwrite, metadata)
        elif self._rename is not None and self._rename.rename_replaces:
            result = await self._write_temp_and_rename(key, content, overwrite, metadata)
        else:
            raise CapabilityNotSupported(
                f"Backend '{self.name}' cannot write atomically",
                path=key,
                backend=self.name,
                capability=Capability.ATOMIC_WRITE.value,
            )
        return _write_result(target, result)

    async def _write_through_handle(
        self, op: Op, key: str, content: _io.Content, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> PutResult:
        assert self._open_write is not None
        with self._choke(op, key):
            handle = await self._open_write.open_write(key, overwrite=overwrite, metadata=metadata)
        try:
            with self._choke(op, key):
                await _io.feed(handle, content)
                return await handle.commit()
        except BaseException:
            with contextlib.suppress(Exception):
                await handle.abort()
            raise

    async def _write_temp_and_rename(
        self, key: str, content: _io.Content, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> PutResult:
        assert self._rename is not None
        op = Op.WRITE_ATOMIC
        if not overwrite:
            existing = await self._stat(op, key)
            if existing is not None:
                raise self._occupied(existing, key)
        temp = _temp_key(key)
        try:
            result = await self._put(op, temp, content, True, metadata)
            # replace=overwrite: a file written after the check above is refused,
            # never silently replaced.
            with self._choke(op, key):
                await self._rename.rename(temp, key, replace=overwrite)
        except BaseException:
            # A failed put can leave a partial temporary on some wires.
            with contextlib.suppress(Exception):
                await self._driver.delete(temp)
            raise
        return result

    def _occupied(self, entry: Entry, key: str) -> RemoteStoreError:
        if entry.kind == "folder":
            return InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name)
        return AlreadyExists(f"Already exists: {key}", path=key, backend=self.name)

    # endregion

    # region: move and copy (BE-018, BE-019)

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move a file: forwarded whole, by rename, or as copy-then-delete."""
        await self._transfer(Op.MOVE, src, dst, overwrite)

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file through the driver's copy."""
        await self._transfer(Op.COPY, src, dst, overwrite)

    async def _require_file(self, op: Op, key: str) -> None:
        entry = await self._stat(op, key)
        if entry is None:
            raise NotFound(f"Not found: {key}", path=key, backend=self.name)
        if entry.kind != "file":
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name)

    async def _transfer(self, op: Op, src: str, dst: str, overwrite: bool) -> None:
        self._guard()
        # BE-018: a root source first, then a root destination, both ahead of the
        # source-existence check, and decided from the key.
        source = self._file_key(src)
        target = self._write_key(dst)
        if source == target:
            # BK-301: a self-operation is decided on the canonical keys.
            await self._require_file(op, source)
            return
        if op is Op.COPY and self._copier is None:
            raise CapabilityNotSupported(
                f"Backend '{self.name}' cannot copy", path=source, backend=self.name, capability="copy"
            )
        # The source's NotFound outranks the destination's preconditions (BE-018), so
        # the source is confirmed before the ancestor walk or parent creation can
        # answer or act for the destination.
        source_checked = self._reject_under_file or self._parents_maker is not None
        if source_checked:
            await self._require_file(op, source)
        await self._prepare_write(op, target)
        if op is Op.COPY:
            await self._copy(op, source, target, overwrite)
        elif self._atomic_move is not None:
            try:
                with self._choke(op, source):
                    await self._atomic_move.move(source, target, overwrite=overwrite)
            except NotFound as err:
                await self._folder_is_wrong_type(err, op, source)
                raise
            except AlreadyExists as err:
                await self._destination_is_wrong_type(err, op, target)
                raise
        elif self._rename is not None:
            await self._rename_into(source, target, overwrite, source_checked=source_checked)
        elif self._copier is not None:
            await self._copy(op, source, target, overwrite)
            with self._choke(op, source):
                await self._driver.delete(source)
        else:
            raise CapabilityNotSupported(
                f"Backend '{self.name}' cannot move", path=source, backend=self.name, capability="move"
            )

    async def _destination_is_wrong_type(self, err: RemoteStoreError, op: Op, key: str) -> None:
        entry = await self._stat_open(op, key)
        if entry is not None and entry.kind == "folder":
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name) from err

    async def _copy(self, op: Op, source: str, target: str, overwrite: bool) -> None:
        assert self._copier is not None
        try:
            with self._choke(op, source):
                await self._copier.copy(source, target, overwrite=overwrite)
        except NotFound as err:
            await self._folder_is_wrong_type(err, op, source)
            raise
        except AlreadyExists as err:
            await self._destination_is_wrong_type(err, op, target)
            raise

    async def _rename_into(self, source: str, target: str, overwrite: bool, *, source_checked: bool) -> None:
        assert self._rename is not None
        op = Op.MOVE
        if not source_checked:
            await self._require_file(op, source)
        existing = await self._stat(op, target)
        if existing is not None and (existing.kind == "folder" or not overwrite):
            raise self._occupied(existing, target)
        if existing is None or self._rename.rename_replaces:
            with self._choke(op, source):
                await self._rename.rename(source, target, replace=existing is not None)
            return
        # Displace and restore: a rename that cannot replace moves the old file
        # aside, and puts it back when the move itself fails.
        parked = _temp_key(target)
        with self._choke(op, target):
            await self._rename.rename(target, parked, replace=False)
        try:
            with self._choke(op, source):
                await self._rename.rename(source, target, replace=False)
        except BaseException:
            with contextlib.suppress(Exception):
                await self._rename.rename(parked, target, replace=False)
            raise
        try:
            with self._choke(op, parked):
                await self._driver.delete(parked)
        except RemoteStoreError as err:
            _log.warning("%s: moved %r but could not remove the displaced %r: %s", self.name, source, parked, err)

    # endregion

    # region: listings (BE-014, BE-015, BE-026, BE-024)

    async def _listed_files(self, op: Op, key: str, recursive: bool, omitted: _Omitted) -> AsyncIterator[Entry]:
        async for page in self._pages(op, key, None if recursive else "/"):
            for entry in page.entries:
                if entry.kind != "file":
                    continue
                if not _keys.listable(entry.key):
                    omitted.note(entry.key)
                    continue
                yield entry

    async def list_files(
        self, path: str, *, recursive: bool = False, max_depth: int | None = None
    ) -> AsyncIterator[FileInfo]:
        """Files under *path*; recursive is one ``delimiter=None`` walk (decision 7)."""
        self._guard()
        key = self._key(path)
        omitted = _Omitted(self.name, key)
        async for entry in self._listed_files(Op.LIST_FILES, key, recursive, omitted):
            if recursive and not within_depth(key, entry.key, max_depth):
                continue
            yield self._file_info(entry)
        omitted.log()

    def _folders_of(self, page: Page, seen: set[str], omitted: _Omitted) -> list[FolderEntry]:
        keys = [*page.prefixes, *(e.key for e in page.entries if e.kind == "folder")]
        out = []
        for folder in keys:
            if not _keys.listable(folder):
                omitted.note(folder)
                continue
            if folder in seen:
                continue
            seen.add(folder)
            out.append(FolderEntry(path=RemotePath(folder), name=_keys.name(folder)))
        return out

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """Immediate subfolders of *path*."""
        self._guard()
        key = self._key(path)
        omitted = _Omitted(self.name, key)
        seen: set[str] = set()
        async for page in self._pages(Op.LIST_FOLDERS, key, "/"):
            for folder in self._folders_of(page, seen, omitted):
                yield folder
        omitted.log()

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Files and immediate subfolders of *path*, in one listing pass."""
        self._guard()
        key = self._key(path)
        omitted = _Omitted(self.name, key)
        seen: set[str] = set()
        async for page in self._pages(Op.ITER_CHILDREN, key, "/"):
            for entry in page.entries:
                if entry.kind != "file":
                    continue
                if not _keys.listable(entry.key):
                    omitted.note(entry.key)
                    continue
                yield self._file_info(entry)
            for folder in self._folders_of(page, seen, omitted):
                yield folder
        omitted.log()

    async def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Files matching *pattern*, refused and normalised by the pattern rule."""
        globber = self._globber
        if globber is None:
            # Capability data, so ahead of the closed guard (BE-030 § glob).
            raise CapabilityNotSupported(
                f"Backend '{self.name}' does not support glob."
                " Use list_files(pattern=...) for name filtering"
                " or ext.glob.glob_files() for full glob.",
                capability="glob",
                backend=self.name,
            )
        self._guard()
        why = _keys.pattern_refusal(pattern)
        if why is not None:
            raise InvalidPath(why, path=pattern, backend=self.name)
        canon = _keys.canonical_pattern(pattern)
        if not canon:
            return  # the root is a folder, and glob yields only files
        omitted = _Omitted(self.name, canon)
        matches = globber.glob(canon).__aiter__()
        seen = False
        while True:
            try:
                with self._choke(Op.GLOB, canon):
                    entry = await matches.__anext__()
            except StopAsyncIteration:
                break
            except NotFound:
                # The listing bound, at the granularity a glob iterator exposes.
                if seen:
                    raise
                break
            seen = True
            if entry.kind != "file":
                continue
            if not _keys.listable(entry.key):
                omitted.note(entry.key)
                continue
            yield self._file_info(entry)
        omitted.log()

    # endregion

    # region: get_folder_info (BE-017)

    async def get_folder_info(self, path: str) -> FolderInfo:
        """The folder's aggregate, by push-down or over a listing."""
        self._guard()
        key = self._key(path)
        op = Op.GET_FOLDER_INFO
        if self._stats is not None:
            try:
                with self._choke(op, key):
                    count, size, latest = await self._stats.folder_stats(key)
            except NotFound:
                count, size, latest = 0, 0, None
            latest = None if latest is None else _known_modified_at(latest)
        else:
            tally = FolderTally()
            omitted = _Omitted(self.name, key)
            async for entry in self._listed_files(op, key, True, omitted):
                tally.add(entry)
            omitted.log()
            count, size, latest = tally.count, tally.size, tally.latest
        if count == 0 and key:
            # The error path: an empty aggregate is a folder, a file or nothing.
            node = await self._stat_open(op, key)
            if node is None:
                raise NotFound(f"Not found: {key}", path=key, backend=self.name)
            if node.kind == "file":
                raise InvalidPath(f"Is a file, not a folder: {key}", path=key, backend=self.name)
        return FolderInfo(path=RemotePath.from_backend_path(key), file_count=count, total_size=size, modified_at=latest)

    # endregion

    # region: delete_folder (BE-031)

    def _df_error(self, cls: type[RemoteStoreError], key: str) -> RemoteStoreError:
        messages = {
            NotFound: "Not found",
            InvalidPath: "Not a folder",
            DirectoryNotEmpty: "Folder is not empty",
        }
        return cls(f"{messages.get(cls, 'Refused')}: {key}", path=key, backend=self.name)

    async def _df_kind(self, key: str) -> str | None:
        entry = await self._stat(Op.DELETE_FOLDER, key, follow_links=False)
        return None if entry is None else entry.kind

    async def _df_list(self, key: str, delimiter: str | None, limit: int | None) -> tuple[list[str], list[str]]:
        """Raw keys under *key*: files (and links), and folders. Unfiltered on purpose.

        A probe must see every entry, the omitted ones included, or it
        would call a folder holding only those empty.
        """
        files: list[str] = []
        folders: list[str] = []
        cursor: object | None = None
        while True:
            with self._choke(Op.DELETE_FOLDER, key):
                page = await self._driver.list_page(
                    key, delimiter=delimiter, cursor=cursor, limit=limit, follow_links=False
                )
            files += [e.key for e in page.entries if e.kind == "file"]
            folders += [e.key for e in page.entries if e.kind == "folder"]
            folders += list(page.prefixes)
            cursor = page.cursor
            if cursor is None or limit is not None:
                return files, folders

    @staticmethod
    def _probe_wanted(err: RemoteStoreError) -> bool:
        # Only a typed NotFound or an untyped refusal says something about the key.
        return type(err) is NotFound or type(err) is RemoteStoreError

    async def _df_error_path(
        self,
        err: RemoteStoreError,
        key: str,
        missing_ok: bool,
        *,
        listing_arm: bool,
        on_way: bool = False,
        file_op: bool = False,
    ) -> None:
        """The probe rule for a refusal *err* on *key*.

        ``on_way``: a call inside the walk on an entry under the deleted key.
        ``file_op``: the refused call was the walk's ``delete``, for which a
        file is the right type.
        """
        if not self._probe_wanted(err):
            raise err
        try:
            kind = await self._df_kind(key)
        except RemoteStoreError as probe_err:
            return self._df_stands(err, missing_ok, probe_err)
        if kind is None:
            if missing_ok or on_way:
                return None
            raise self._df_error(NotFound, key) from err
        if kind == "file":
            if file_op:
                return self._df_stands(err, missing_ok, None)
            raise self._df_error(InvalidPath, key) from err
        if listing_arm:
            try:
                files, folders = await self._df_list(key, "/", 1)
            except RemoteStoreError as probe_err:
                return self._df_stands(err, missing_ok, probe_err)
            if files or folders:
                raise self._df_error(DirectoryNotEmpty, key) from err
        return self._df_stands(err, missing_ok, None)

    @staticmethod
    def _df_stands(err: RemoteStoreError, missing_ok: bool, probe_err: RemoteStoreError | None) -> None:
        """The probes did not replace the refusal: it stands, ``missing_ok`` applying to a NotFound.

        A ``NotFound`` on the walk's way never gets here, since the walk tolerates
        it before the probe rule, so only the caller's ``missing_ok``
        applies. ``missing_ok`` is ``False`` for every call on the way.
        """
        if type(err) is NotFound and missing_ok:
            return
        if probe_err is not None:
            raise err from probe_err
        raise err

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Remove the folder at *path* by the kernel's sequence; the root is refused first."""
        self._guard()
        key = self._key(path)
        if not key:
            raise InvalidPath("Cannot delete the store root", path=path, backend=self.name)
        if self._driver.parents == "none":
            return await self._df_none(key, recursive, missing_ok)
        remover = self._remover
        assert remover is not None  # construction requires it with folder objects
        if not recursive:
            try:
                with self._choke(Op.DELETE_FOLDER, key):
                    await remover.remove_folder(key)
            except RemoteStoreError as err:
                await self._df_error_path(err, key, missing_ok, listing_arm=True)
            return None
        if self._tree is not None:
            try:
                with self._choke(Op.DELETE_FOLDER, key):
                    await self._tree.delete_tree(key)
            except RemoteStoreError as err:
                await self._df_error_path(err, key, missing_ok, listing_arm=False)
            return None
        return await self._df_walk(key, missing_ok, remover)

    async def _df_walk(self, key: str, missing_ok: bool, remover: AsyncSupportsRemoveFolder) -> None:
        files: list[str] = []
        folders: list[str] = []
        stack = [key]
        while stack:
            current = stack.pop()
            try:
                found_files, found_folders = await self._df_list(current, "/", None)
            except RemoteStoreError as err:
                if current == key:
                    return await self._df_error_path(err, key, missing_ok, listing_arm=True)
                if type(err) is NotFound:
                    continue
                await self._df_error_path(err, current, False, listing_arm=True, on_way=True)
                continue
            # A key the rule refuses is never handed to the driver (BE-030); it
            # stays, and the final remove_folder answers DirectoryNotEmpty for it.
            files += [f for f in found_files if _keys.listable(f)]
            listable = [f for f in found_folders if _keys.listable(f)]
            folders += listable
            stack += listable
        for file in files:
            try:
                with self._choke(Op.DELETE_FOLDER, file):
                    await self._driver.delete(file)
            except RemoteStoreError as err:
                if type(err) is NotFound:
                    continue
                await self._df_error_path(err, file, False, listing_arm=True, on_way=True, file_op=True)
        for folder in sorted(folders, key=lambda f: -f.count("/")):
            try:
                with self._choke(Op.DELETE_FOLDER, folder):
                    await remover.remove_folder(folder)
            except RemoteStoreError as err:
                if type(err) is NotFound:
                    continue
                await self._df_error_path(err, folder, False, listing_arm=True, on_way=True)
        try:
            with self._choke(Op.DELETE_FOLDER, key):
                await remover.remove_folder(key)
        except RemoteStoreError as err:
            await self._df_error_path(err, key, missing_ok, listing_arm=True)
        return None

    async def _df_listing(self, key: str, delimiter: str | None, limit: int | None) -> tuple[list[str], list[str]]:
        # The determinant fails closed, but a NotFound is an empty listing: an
        # absent prefix or an absent container holds nothing (BE-013).
        try:
            return await self._df_list(key, delimiter, limit)
        except NotFound:
            return [], []

    async def _df_none(self, key: str, recursive: bool, missing_ok: bool) -> None:
        if not recursive:
            files, folders = await self._df_listing(key, "/", 1)
            if files or folders:
                raise self._df_error(DirectoryNotEmpty, key)
            return await self._df_empty(key, missing_ok)
        if self._tree is not None:
            files, _ = await self._df_listing(key, None, 1)
            if not files:
                return await self._df_empty(key, missing_ok)
            with self._choke(Op.DELETE_FOLDER, key):
                await self._tree.delete_tree(key)
            return None
        files, _ = await self._df_listing(key, None, None)
        if not files:
            return await self._df_empty(key, missing_ok)
        left = False
        for file in files:
            if not _keys.listable(file):
                # Never handed to the driver (BE-030); it keeps the prefix alive.
                left = True
                continue
            try:
                with self._choke(Op.DELETE_FOLDER, file):
                    await self._driver.delete(file)
            except NotFound:
                continue
        if left:
            raise self._df_error(DirectoryNotEmpty, key)
        return None

    async def _df_empty(self, key: str, missing_ok: bool) -> None:
        # After an empty listing the stat fails open: a raising stat leaves NotFound.
        try:
            kind = await self._df_kind(key)
        except RemoteStoreError:
            kind = None
        if kind == "file":
            raise self._df_error(InvalidPath, key)
        if missing_ok:
            return
        raise self._df_error(NotFound, key)

    # endregion

    # region: lifecycle

    async def check_health(self) -> None:
        """The driver's ``probe()``, under the probe scope."""
        self._guard()
        with self._choke(Op.PROBE, ""):
            await self._driver.probe()

    async def aclose(self) -> None:
        """Close the driver; a terminal posture refuses use from this point."""
        self._closed = True
        with self._choke(Op.CLOSE, ""):
            await self._driver.aclose()

    # endregion
