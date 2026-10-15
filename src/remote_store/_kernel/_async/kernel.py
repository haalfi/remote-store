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
import enum
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
    PermissionDenied,
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
from remote_store._kernel._model import Entry, Op
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult, _known_modified_at
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType
    from typing import TypeVar

    from remote_store._capabilities import CapabilitySet
    from remote_store._kernel._async.driver import AsyncDriver
    from remote_store._kernel._model import Page, PutResult
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
    if driver.namespace == "flat" and driver.parents != "none":
        # A flat stat cannot see a folder object, so nothing could type one at a key (BE-030).
        msg = f"driver {driver.name!r} is flat but has folder objects (parents={driver.parents!r})"
        raise ValueError(msg)
    if driver.parents == "explicit" and not isinstance(driver, AsyncSupportsEnsureParents):
        # BE-009: a write creates its parents, and an explicit wire cannot without it.
        msg = f"driver {driver.name!r} has explicit parents but no ensure_parents"
        raise ValueError(msg)
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
    movers = (AsyncSupportsAtomicMove, AsyncSupportsRename, AsyncSupportsCopy)
    if caps.supports(Capability.MOVE) and not isinstance(driver, movers):
        msg = f"driver {driver.name!r} declares MOVE without a move, a rename or a copy"
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


def _in_probe_set(err: RemoteStoreError) -> bool:
    """Whether a refusal may say something about the key: the probe set.

    ``NotFound``, ``InvalidPath``, ``AlreadyExists``, ``PermissionDenied`` and
    an untyped refusal: a wire's ENOTDIR, EISDIR or Windows denial may arrive as
    any of them. A dead service, a lock or a non-empty folder says nothing.
    """
    return type(err) is RemoteStoreError or isinstance(err, (NotFound, InvalidPath, AlreadyExists, PermissionDenied))


class _State(enum.Enum):
    """What ``_state`` finds at a key: the tree's ``Item``, ``Folder`` or ``Nothing``."""

    ABSENT = "absent"  # Nothing
    FILE = "file"  # Item
    FOLDER = "folder"  # Folder
    UNDER_FILE = "under a file"  # Nothing, the path through an item; hierarchical only
    UNKNOWN = "unknown"  # a stat that could not answer; its error rides along


@dataclasses.dataclass(frozen=True)
class _Seen:
    state: _State
    entry: Entry | None = None  # the stat's entry, for FILE and FOLDER where it answered
    error: RemoteStoreError | None = None  # the stat's error, for UNKNOWN
    above: str | None = None  # the file ancestor, for UNDER_FILE


class _Omitted:
    """Counts listed keys a listing omits, and logs them once per listing.

    Two kinds: a key the key rule refuses or rewrites, and on a flat
    namespace a key below an item the listing returned, which decodes to no
    tree.
    """

    # BE-030's omission, and A.3 of spec 003 § The store tree.

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
                "%s: omitted %d listed key(s) under %r that the key rule refuses or rewrites,"
                " or that lie below a listed file, e.g. %r",
                self._name,
                self._count,
                self._where,
                self._first,
            )


class _Shadows:
    """A flat listing's keys below an item it returned, which A.3 omits.

    A flat driver lists in byte-lexicographic order, so an item ``k`` arrives
    before every key below ``k/``, and every key between the two starts with
    ``k`` and a byte that sorts before ``/``. So the items whose keys may still
    be followed by keys below them form a stack, and that stack is all the
    state needed: no buffer of the listing. A prefix ``p`` orders as ``p/``.
    Inactive on a hierarchical namespace, which cannot hold the state.
    """

    __slots__ = ("_active", "_open")

    def __init__(self, active: bool) -> None:
        self._active = active
        self._open: list[str] = []

    def below(self, files: list[str], prefixes: list[str]) -> set[str]:
        """The keys of one page to omit: files by key, prefixes by key with a trailing ``/``."""
        if not self._active:
            return set()
        order = sorted([(f, True) for f in files] + [(p + "/", False) for p in prefixes])
        out: set[str] = set()
        for key, item in order:
            while self._open:
                top = self._open[-1]
                if key.startswith(top) and len(key) > len(top) and key[len(top)] <= "/":
                    break
                self._open.pop()
            if self._open and key.startswith(self._open[-1] + "/"):
                out.add(key)
            elif item:
                self._open.append(key)
        return out


class _FirstPageRefused(Exception):
    """A refusal of a listing's first page, carried out of a paged loop to the caller that answers it."""

    def __init__(self, err: RemoteStoreError) -> None:
        super().__init__(str(err))
        self.err = err


class _Choke:
    """The choke point: a native exception leaving the block is mapped once.

    A ``RemoteStoreError`` keeps its type; anything else goes through the
    driver's ``classify``. ``path``, ``backend`` and a blank message are then
    filled, and an absent container reads as an absent path where the
    kernel decides it. A ``BaseException`` that is not an ``Exception``
    passes untouched. The end of an iteration does not: raised by a driver
    call it is a native error like any other, so the one iteration step
    that may end on it (``glob``'s) catches it inside the block.
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
        if exc is None or not isinstance(exc, Exception):
            return False
        err = self._core._mapped(exc, self._op, self._key)
        if err is exc:
            return False
        raise err from exc


class _AsyncKernelCore:
    """The backend surface both runtimes share, over a driver.

    Args:
        driver: A built driver; each public class builds its own.

    Raises:
        ValueError: If the driver's declarations are not backed by its
            protocols, it is flat and has folder objects, it has explicit
            parents and no ``ensure_parents``, it has folder objects and no
            ``remove_folder``, or the class's own ``close_is_terminal``
            differs from the driver's.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        _check_construction(driver)
        # The class's own close_is_terminal is what callers and the conformance
        # lanes read; the guard reads the driver's. They must be one answer.
        declared = getattr(type(self), "close_is_terminal", driver.close_is_terminal)
        if declared != driver.close_is_terminal:
            msg = (
                f"{type(self).__name__}.close_is_terminal is {declared}, but driver {driver.name!r}"
                f" declares close_is_terminal={driver.close_is_terminal}"
            )
            raise ValueError(msg)
        self._driver = driver
        self._flat = driver.namespace == "flat"
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
        # A typed error is the driver's own answer and passes untouched (RFC-0017 D2).
        typed = isinstance(exc, RemoteStoreError)
        if not typed and op not in _CLASSIFY_DECIDES and not isinstance(err, NotFound) and self._absent(exc, op):
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

    async def _state(self, op: Op, key: str, *, walk: bool, folders: bool = True, follow_links: bool = True) -> _Seen:
        """What *key* resolves to: the one answer every probe of a key reads.

        A ``stat`` that answers decides. A miss (``None``, or a ``NotFound`` or
        ``InvalidPath``, as a POSIX ``stat`` under a file raises ENOTDIR) is
        followed on a flat driver by one ``list_page(limit=1)``, since a flat
        ``stat`` cannot see a folder (unless *folders* is false: ``is_file``
        and a write target need no folder); that listing's ``NotFound`` or
        ``InvalidPath`` is an empty listing, by the flat listing obligation,
        so nothing is there. On a hierarchical driver a miss is followed, when
        *walk*, by the ancestors' ``stat`` calls, and so is, whether or not
        *walk*, a ``stat`` raising another refusal in the probe set: an item
        above makes the key's path pass through an item, and an absent
        ancestor makes the key absent. Anything else, a flat listing that
        cannot answer included, is ``UNKNOWN``, carrying the error, which a
        determinant raises and an error-path probe reads as no answer. A flat
        namespace never walks: a key below an item is its own key (A.3's
        stated limit). *follow_links* is the key's own ``stat``: ``False``
        for the calls that name the entry at the key (A.7).
        """
        hier = not self._flat
        try:
            entry = await self._stat(op, key, follow_links=follow_links)
        except (NotFound, InvalidPath):
            entry = None
        except RemoteStoreError as err:
            if hier and _in_probe_set(err):
                return await self._above(op, key, err)
            return _Seen(_State.UNKNOWN, error=err)
        if entry is not None:
            return _Seen(_State.FILE if entry.kind == "file" else _State.FOLDER, entry=entry)
        if not hier:
            return await self._flat_folder(op, key) if folders else _Seen(_State.ABSENT)
        return await self._above(op, key, None) if walk else _Seen(_State.ABSENT)

    async def _flat_folder(self, op: Op, key: str) -> _Seen:
        """Whether a flat *key* with no item holds anything: one ``list_page(limit=1)``.

        Its ``NotFound`` or ``InvalidPath`` is an empty listing, by the flat
        listing obligation, so nothing is there; any other refusal is the
        unknown answer.
        """
        try:
            with self._choke(op, key):
                page = await self._driver.list_page(key, delimiter="/", limit=1)
        except (NotFound, InvalidPath):
            return _Seen(_State.ABSENT)
        except RemoteStoreError as err:
            return _Seen(_State.UNKNOWN, error=err)
        return _Seen(_State.FOLDER if page.entries or page.prefixes else _State.ABSENT)

    async def _above(self, op: Op, key: str, err: RemoteStoreError | None) -> _Seen:
        """A hierarchical key's ancestors, shallowest first, each ``stat`` fail-open.

        A file among them puts *key* under a file; an absent one makes *key*
        absent, since nothing below it can exist. A folder or an ancestor that
        cannot answer goes on to the next. Past the last one *key* is absent
        when its own ``stat`` missed, and ``UNKNOWN`` with that ``stat``'s
        error *err* when it raised.
        """
        for ancestor in _keys.ancestors(key):
            try:
                entry = await self._stat(op, ancestor)
            except (NotFound, InvalidPath):
                entry = None
            except RemoteStoreError:
                continue
            if entry is None:
                return _Seen(_State.ABSENT)
            if entry.kind == "file":
                return _Seen(_State.UNDER_FILE, above=ancestor)
        return _Seen(_State.ABSENT) if err is None else _Seen(_State.UNKNOWN, error=err)

    async def _file_entry(self, op: Op, key: str, *, follow_links: bool = True) -> Entry:
        """A determinant file key: the file's entry, or the error its state answers.

        *follow_links* is false for a ``move`` source, which names the entry at
        the key, so a link there is the item moved (A.7).
        """
        seen = await self._state(op, key, walk=False, follow_links=follow_links)
        if seen.error is not None:
            raise seen.error
        if seen.state is _State.FOLDER:
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name)
        if seen.entry is None or seen.state is not _State.FILE:
            raise NotFound(f"Not found: {key}", path=key, backend=self.name)
        return seen.entry

    def _under_file(self, seen: _Seen, key: str) -> InvalidPath:
        return InvalidPath(f"An ancestor of the path is a file: {seen.above}", path=key, backend=self.name)

    # The error-path probes below are A.8's per-call tables (spec 003 § The store
    # tree). Each runs only after a refusal in the probe set, fails open (a probe
    # that cannot answer leaves the refusal standing), and replaces the refusal
    # only on a row where the call must refuse: rule 4.

    async def _read_refused(self, err: RemoteStoreError, op: Op, key: str, *, entry: bool = False) -> None:
        """After a ``get`` or ``delete`` refusal: an item stands, a folder is ``InvalidPath``, nothing ``NotFound``.

        *entry*: the call names the entry at the key (``delete``, a ``move``
        source), so its ``stat`` does not follow a link (A.7).
        """
        if not _in_probe_set(err):
            return
        seen = await self._state(op, key, walk=False, follow_links=not entry)
        if seen.state is _State.FOLDER:
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name) from err
        if seen.state in (_State.ABSENT, _State.UNDER_FILE) and not isinstance(err, NotFound):
            raise NotFound(f"Not found: {key}", path=key, backend=self.name) from err

    async def _write_refused(self, err: RemoteStoreError, op: Op, key: str, overwrite: bool) -> None:
        """After a write primitive's refusal at *key*: the row there answers, or the refusal stands.

        Hierarchical: ``stat(k)``, then on a miss the ancestors'; a folder or an
        item above is ``InvalidPath``, an item without *overwrite*
        ``AlreadyExists``. Flat: A.4's checks ran first, so only an item
        without *overwrite* is left to find.
        """
        if not _in_probe_set(err):
            return
        seen = await self._state(op, key, walk=not self._flat, folders=not self._flat)
        if seen.state is _State.FOLDER:
            raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name) from err
        if seen.state is _State.UNDER_FILE:
            raise self._under_file(seen, key) from err
        if seen.state is _State.FILE and not overwrite and not isinstance(err, AlreadyExists):
            raise AlreadyExists(f"Already exists: {key}", path=key, backend=self.name) from err

    async def _parents_refused(self, err: RemoteStoreError, op: Op, key: str) -> None:
        """After ``ensure_parents`` refused: an item among the ancestors is ``InvalidPath``, naming it."""
        if not _in_probe_set(err):
            return
        seen = await self._above(op, key, None)
        if seen.state is _State.UNDER_FILE:
            raise self._under_file(seen, key) from err

    async def _holds_nothing(self, err: RemoteStoreError, op: Op, key: str, *, follow_links: bool = True) -> bool:
        """Whether a listing's or an aggregate's first refusal reads as an empty listing.

        The root is a folder, so only a ``NotFound`` or ``InvalidPath`` there,
        an absent container's, holds nothing. Flat: a ``NotFound`` or
        ``InvalidPath`` does, by the flat listing obligation, and nothing else.
        Hierarchical: a refusal in the probe set does unless ``stat(k)`` sees a
        folder, since a listing of a folder must not read as empty (rule 4).
        """
        if not key or self._flat:
            return isinstance(err, (NotFound, InvalidPath))
        if not _in_probe_set(err):
            return False
        seen = await self._state(op, key, walk=False, follow_links=follow_links)
        return seen.state in (_State.ABSENT, _State.FILE, _State.UNDER_FILE)

    async def _flat_item(self, op: Op, key: str) -> bool:
        """A.3's determinant before a flat folder operation: whether *key* is an item.

        A flat listing of ``k/`` cannot see an item ``k``, so the folder
        operation calls ``stat`` on it first, success included, and fails closed.
        """
        if not self._flat or not key:
            return False
        try:
            entry = await self._stat(op, key)
        except (NotFound, InvalidPath):
            return False
        return entry is not None and entry.kind == "file"

    async def _write_target(self, op: Op, key: str) -> Entry | None:
        """A write target's determinant: the entry there, ``None`` for a miss.

        A ``stat`` alone, so on a flat namespace a key may shadow a prefix. A
        file above the key, which a raising ``stat`` lets ``_state`` find, is
        ``InvalidPath``; a ``stat`` that cannot answer fails the call.
        """
        # BE-008's flat exemption, as BE-030 states it for the kernel.
        seen = await self._state(op, key, walk=False, folders=False)
        if seen.error is not None:
            raise seen.error
        if seen.state is _State.UNDER_FILE:
            raise self._under_file(seen, key)
        return seen.entry

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

        A refusal before the operation's first page is an empty listing when
        ``_holds_nothing`` reads it so (A.8's first-page rows), and otherwise
        stands. After the first page, a refusal reports a change under the
        scan and propagates (A.9). The bound is keyed on the page, never on
        what the operation yielded from it.
        """
        cursor: object | None = None
        seen = False
        while True:
            try:
                with self._choke(op, key):
                    page = await self._driver.list_page(key, delimiter=delimiter, cursor=cursor)
            except RemoteStoreError as err:
                if seen or not await self._holds_nothing(err, op, key):
                    raise
                return
            seen = True
            yield page
            cursor = page.cursor
            if cursor is None:
                return

    # endregion

    # region: probes (BE-004, BE-005, BE-029)

    async def _node(self, op: Op, path: str, *, folders: bool = True) -> _State:
        # The probes are determinants (A.8 rule 1): absent and under a file answer False,
        # and a key whose stat, or on a flat driver whose folder listing, could not
        # answer raises that error, a denial in the probe set included, unless a
        # hierarchical ancestor walk resolves it (`_state`).
        # `folders=False` (is_file) needs no listing probe: a stat sees every file.
        seen = await self._state(op, self._key(path), walk=False, folders=folders)
        if seen.error is not None:
            raise seen.error
        return seen.state

    async def exists(self, path: str) -> bool:
        """Whether a file or folder exists at *path*; the root always does."""
        self._guard()
        if not self._key(path):
            return True
        return await self._node(Op.EXISTS, path) in (_State.FILE, _State.FOLDER)

    async def is_file(self, path: str) -> bool:
        """Whether *path* is an existing file; never for the root."""
        self._guard()
        if not self._key(path):
            return False
        return await self._node(Op.IS_FILE, path, folders=False) is _State.FILE

    async def is_folder(self, path: str) -> bool:
        """Whether *path* is an existing folder; always for the root."""
        self._guard()
        if not self._key(path):
            return True
        return await self._node(Op.IS_FOLDER, path) is _State.FOLDER

    # endregion

    # region: file-shaped operations

    async def _open(self, path: str, op: Op) -> tuple[str, _io.ReadStream]:
        """Open *path* for a read: guards, the key rule, ``get``, the wrong-type probe."""
        self._guard()
        key = self._file_key(path)
        try:
            with self._choke(op, key):
                stream = await self._driver.get(key)
        except RemoteStoreError as err:
            await self._read_refused(err, op, key)
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
        return self._file_info(await self._file_entry(Op.GET_FILE_INFO, key))

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Remove the file at *path*; type mismatch outranks *missing_ok*."""
        self._guard()
        key = self._file_key(path)
        try:
            with self._choke(Op.DELETE, key):
                await self._driver.delete(key)
        except RemoteStoreError as err:
            try:
                await self._read_refused(err, Op.DELETE, key, entry=True)
            except NotFound:
                if missing_ok:
                    return
                raise
            if missing_ok and isinstance(err, NotFound):
                return
            raise

    # endregion

    # region: writes

    async def _prepare_write(self, op: Op, key: str) -> None:
        """A.4's checks on a flat namespace, then the parents an explicit driver needs.

        A flat wire writes below an item, or an item over a folder, so the
        kernel refuses both first: one ``stat`` per ancestor and one
        ``list_page(k, limit=1)``. They decide the result, so they fail
        closed: only a ``None``, ``NotFound`` or
        ``InvalidPath`` is a miss, and an empty listing no folder. Neither is
        race-free. A hierarchical wire refuses both itself, and the kernel
        types its refusal.
        """
        if self._flat:
            for ancestor in _keys.ancestors(key):
                try:
                    entry = await self._stat(op, ancestor)
                except (NotFound, InvalidPath):
                    entry = None
                if entry is not None and entry.kind == "file":
                    raise InvalidPath(f"An ancestor of the path is a file: {ancestor}", path=key, backend=self.name)
            try:
                with self._choke(op, key):
                    page = await self._driver.list_page(key, delimiter="/", limit=1)
            except (NotFound, InvalidPath):
                return  # the flat listing obligation: nothing lies under the prefix
            if page.entries or page.prefixes:
                raise InvalidPath(f"Is a folder, not a file: {key}", path=key, backend=self.name)
            return
        if self._parents_maker is not None and "/" in key:
            try:
                with self._choke(op, key):
                    await self._parents_maker.ensure_parents(key)
            except RemoteStoreError as err:
                # An item above the key, refused in the wire's shape (os.makedirs: EEXIST).
                await self._parents_refused(err, op, key)
                raise

    async def _put(
        self,
        op: Op,
        key: str,
        content: _io.Content,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
        *,
        at: str | None = None,
    ) -> PutResult:
        """``put`` to *at* (default *key*); every error names the caller's *key*."""
        try:
            with self._choke(op, key):
                return await self._driver.put(at or key, content, overwrite=overwrite, metadata=metadata)
        except RemoteStoreError as err:
            await self._write_refused(err, op, key, overwrite)
            raise

    def _require(self, capability: Capability, key: str, what: str) -> None:
        # A declared capability decides, not the protocols behind it (BE-011, BE-024,
        # BE-030); construction already refuses a declaration its protocols cannot back.
        if not self.capabilities.supports(capability):
            raise CapabilityNotSupported(
                f"Backend '{self.name}' {what}", path=key, backend=self.name, capability=capability.value
            )

    def _require_metadata(self, metadata: Mapping[str, str] | None, key: str) -> None:
        # WR-010's strict gate, before any I/O; an empty mapping is a no-op.
        if metadata:
            self._require(Capability.USER_METADATA, key, "does not store user metadata")

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
        self._require_metadata(metadata, key)
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
        # Capability data, not a live operation: ahead of the closed guard and
        # the key rule, as glob's is (BE-030).
        self._require(Capability.ATOMIC_WRITE, path, "cannot write atomically")
        self._guard()
        key = self._write_key(path)
        self._require_metadata(metadata, key)
        target = RemotePath(key)
        await self._prepare_write(Op.WRITE_ATOMIC, key)
        if self._driver.put_is_atomic:
            result = await self._put(Op.WRITE_ATOMIC, key, content, overwrite, metadata)
        elif self._open_write is not None:
            result = await self._write_through_handle(Op.WRITE_ATOMIC, key, content, overwrite, metadata)
        else:
            result = await self._write_temp_and_rename(key, content, overwrite, metadata)
        return _write_result(target, result)

    async def _write_through_handle(
        self, op: Op, key: str, content: _io.Content, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> PutResult:
        assert self._open_write is not None
        try:
            with self._choke(op, key):
                handle = await self._open_write.open_write(key, overwrite=overwrite, metadata=metadata)
        except RemoteStoreError as err:
            await self._write_refused(err, op, key, overwrite)
            raise
        try:
            with self._choke(op, key):
                await _io.feed(handle, content)
                return await handle.commit()
        except BaseException as err:
            with contextlib.suppress(Exception):
                await handle.abort()
            if isinstance(err, RemoteStoreError):
                await self._write_refused(err, op, key, overwrite)
            raise

    async def _write_temp_and_rename(
        self, key: str, content: _io.Content, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> PutResult:
        assert self._rename is not None
        op = Op.WRITE_ATOMIC
        if not overwrite:
            existing = await self._write_target(op, key)
            if existing is not None:
                raise self._occupied(existing, key)
        temp = _temp_key(key)
        try:
            result = await self._put(op, key, content, True, metadata, at=temp)
            # replace=overwrite: a file written after the check above is refused,
            # never silently replaced.
            try:
                with self._choke(op, key):
                    await self._rename.rename(temp, key, replace=overwrite)
            except RemoteStoreError as err:
                await self._write_refused(err, op, key, overwrite)
                raise
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
        await self._file_entry(op, key, follow_links=op is not Op.MOVE)

    async def _transfer(self, op: Op, src: str, dst: str, overwrite: bool) -> None:
        # The declared capability decides, ahead of the closed guard and the key
        # rule, as for write_atomic (BE-030); construction guarantees a means behind it.
        if op is Op.COPY:
            self._require(Capability.COPY, src, "cannot copy")
        else:
            self._require(Capability.MOVE, src, "cannot move")
        self._guard()
        # BE-018: a root source first, then a root destination, both ahead of the
        # source-existence check, and decided from the key.
        source = self._file_key(src)
        target = self._write_key(dst)
        if source == target:
            # BK-301: a self-operation is decided on the canonical keys.
            await self._require_file(op, source)
            return
        # The source's NotFound outranks the destination's preconditions (BE-018), so
        # the source is confirmed before A.4's flat checks or parent creation can
        # answer or act for the destination.
        source_checked = self._flat or self._parents_maker is not None
        if source_checked:
            await self._require_file(op, source)
        await self._prepare_write(op, target)
        if op is Op.COPY:
            await self._copy(op, source, target, overwrite)
        elif self._atomic_move is not None:
            try:
                with self._choke(op, source):
                    await self._atomic_move.move(source, target, overwrite=overwrite)
            except RemoteStoreError as err:
                await self._transfer_refused(err, op, source, target, overwrite)
                raise
        elif self._rename is not None:
            await self._rename_into(source, target, overwrite, source_checked=source_checked)
        else:
            await self._copy(op, source, target, overwrite)
            with self._choke(op, source):
                await self._driver.delete(source)

    async def _transfer_refused(self, err: RemoteStoreError, op: Op, source: str, target: str, overwrite: bool) -> None:
        """Answer a two-key call's refusal from the keys' rows, the source's first (A.8).

        The wire may check either key first, and ``classify`` saw only the
        source, so the choke point named it. The source is probed as a ``get``
        (a ``move`` source names the entry, so without following a link): an
        absent source is ``NotFound`` and a folder there ``InvalidPath``, both
        naming the source. Only a source confirmed an item sends the probe on
        to the destination, as a write primitive's target; a source probe that
        cannot answer leaves the refusal standing, since a folder at the
        destination must not outrank a source that may be absent.
        Otherwise the refusal stands, naming the destination when it
        can only be the destination's: an ``AlreadyExists``, or a ``NotFound``
        or ``InvalidPath`` with the source confirmed a file.
        """
        # BE-018: the source's NotFound outranks the destination's preconditions.
        if not _in_probe_set(err):
            return
        seen = (await self._state(op, source, walk=False, follow_links=op is not Op.MOVE)).state
        if seen in (_State.ABSENT, _State.UNDER_FILE):
            if isinstance(err, NotFound):
                err.path = source
                return
            raise NotFound(f"Not found: {source}", path=source, backend=self.name) from err
        if seen is _State.FOLDER:
            raise InvalidPath(f"Is a folder, not a file: {source}", path=source, backend=self.name) from err
        if seen is not _State.FILE:
            # The source probe could not answer, so the refusal stands (rule 3); only
            # the destination can be taken.
            if isinstance(err, AlreadyExists):
                err.path = target
            return
        await self._write_refused(err, op, target, overwrite)
        if isinstance(err, (AlreadyExists, NotFound, InvalidPath)):
            err.path = target

    async def _copy(self, op: Op, source: str, target: str, overwrite: bool) -> None:
        assert self._copier is not None
        try:
            with self._choke(op, source):
                await self._copier.copy(source, target, overwrite=overwrite)
        except RemoteStoreError as err:
            await self._transfer_refused(err, op, source, target, overwrite)
            raise

    async def _rename_source(self, source: str, target: str, *, replace: bool) -> None:
        assert self._rename is not None
        try:
            with self._choke(Op.MOVE, source):
                await self._rename.rename(source, target, replace=replace)
        except RemoteStoreError as err:
            # A key that changed under the move after its checks.
            await self._transfer_refused(err, Op.MOVE, source, target, replace)
            raise

    async def _rename_into(self, source: str, target: str, overwrite: bool, *, source_checked: bool) -> None:
        assert self._rename is not None
        op = Op.MOVE
        if not source_checked:
            await self._require_file(op, source)
        existing = await self._write_target(op, target)
        if existing is not None and (existing.kind == "folder" or not overwrite):
            raise self._occupied(existing, target)
        if self._rename.rename_replaces:
            # replace=overwrite, not "a file was seen": with overwrite a file the
            # check missed (a race, or a stat that answered NotFound) is replaced.
            await self._rename_source(source, target, replace=overwrite)
            return
        if existing is None:
            try:
                await self._rename_source(source, target, replace=False)
                return
            except AlreadyExists:
                if not overwrite:
                    raise
            # A file the check missed, under overwrite: displaced like a seen one.
        # Displace and restore: a rename that cannot replace moves the old file
        # aside, and puts it back when the move itself fails.
        parked = _temp_key(target)
        try:
            with self._choke(op, target):
                await self._rename.rename(target, parked, replace=False)
        except NotFound:
            # The file to displace is gone already, so the destination is free.
            await self._rename_source(source, target, replace=False)
            return
        try:
            await self._rename_source(source, target, replace=False)
        except BaseException:
            try:
                await self._rename.rename(parked, target, replace=False)
            except Exception as restore:  # noqa: BLE001 - the move's own error is the one raised
                _log.warning(
                    "%s: move to %r failed and the displaced file could not be put back; it lies at %r: %s",
                    self.name,
                    target,
                    parked,
                    restore,
                )
            raise
        try:
            with self._choke(op, parked):
                await self._driver.delete(parked)
        except RemoteStoreError as err:
            _log.warning("%s: moved %r but could not remove the displaced %r: %s", self.name, source, parked, err)

    # endregion

    # region: listings (BE-014, BE-015, BE-026, BE-024)

    @staticmethod
    def _below(page: Page, shadows: _Shadows) -> set[str]:
        """A page's keys below an item the listing returned (A.3), a prefix as ``p/``.

        The shadows read every key of the page, a kind the listing does not
        yield included, since the order they track spans both.
        """
        files = [e.key for e in page.entries if e.kind == "file"]
        return shadows.below(files, list(page.prefixes))

    @staticmethod
    def _files_of(page: Page, below: set[str], omitted: _Omitted) -> list[Entry]:
        """A page's files as the tree has them; each omitted one is noted for the log.

        Omitted: a key the key rule refuses or rewrites, and on a flat
        namespace a key below an item this listing returned.
        """
        out: list[Entry] = []
        for entry in page.entries:
            if entry.kind != "file":
                continue
            if entry.key in below or not _keys.listable(entry.key):
                omitted.note(entry.key)
            else:
                out.append(entry)
        return out

    @staticmethod
    def _folders_of(page: Page, below: set[str], seen: set[str], omitted: _Omitted) -> list[FolderEntry]:
        """A page's folders not yet yielded, as the tree has them; omissions noted as for files.

        A listed folder entry is a folder key like a prefix, and a prefix
        shadowed by an item of its name lies below that item.
        """
        out = []
        for folder in [*page.prefixes, *(e.key for e in page.entries if e.kind == "folder")]:
            if folder + "/" in below or not _keys.listable(folder):
                omitted.note(folder)
                continue
            if folder in seen:
                continue
            seen.add(folder)
            out.append(FolderEntry(path=RemotePath(folder), name=_keys.name(folder)))
        return out

    async def _listed_files(self, op: Op, key: str, recursive: bool, omitted: _Omitted) -> AsyncIterator[Entry]:
        shadows = _Shadows(self._flat)
        async for page in self._pages(op, key, None if recursive else "/"):
            for entry in self._files_of(page, self._below(page, shadows), omitted):
                yield entry

    async def list_files(
        self, path: str, *, recursive: bool = False, max_depth: int | None = None
    ) -> AsyncIterator[FileInfo]:
        """Files under *path*; recursive is one ``delimiter=None`` walk (decision 7)."""
        self._guard()
        key = self._key(path)
        if await self._flat_item(Op.LIST_FILES, key):
            return  # an item holds nothing (A.3, A.5)
        omitted = _Omitted(self.name, key)
        try:
            async for entry in self._listed_files(Op.LIST_FILES, key, recursive, omitted):
                if recursive and not within_depth(key, entry.key, max_depth):
                    continue
                yield self._file_info(entry)
        finally:
            # A caller that stops early, or an error, still gets the omission logged.
            omitted.log()

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """Immediate subfolders of *path*."""
        self._guard()
        key = self._key(path)
        if await self._flat_item(Op.LIST_FOLDERS, key):
            return
        omitted = _Omitted(self.name, key)
        shadows = _Shadows(self._flat)
        seen: set[str] = set()
        try:
            async for page in self._pages(Op.LIST_FOLDERS, key, "/"):
                for folder in self._folders_of(page, self._below(page, shadows), seen, omitted):
                    yield folder
        finally:
            omitted.log()

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Files and immediate subfolders of *path*, in one listing pass."""
        self._guard()
        key = self._key(path)
        if await self._flat_item(Op.ITER_CHILDREN, key):
            return
        omitted = _Omitted(self.name, key)
        shadows = _Shadows(self._flat)
        seen: set[str] = set()
        try:
            async for page in self._pages(Op.ITER_CHILDREN, key, "/"):
                below = self._below(page, shadows)
                for entry in self._files_of(page, below, omitted):
                    yield self._file_info(entry)
                for folder in self._folders_of(page, below, seen, omitted):
                    yield folder
        finally:
            omitted.log()

    async def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Files matching *pattern*, refused and normalised by the pattern rule."""
        globber = self._globber
        if globber is None or not self.capabilities.supports(Capability.GLOB):
            # Capability data, so ahead of the closed guard (BE-030 § glob); the
            # declaration decides, as BE-024 states.
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
        try:
            # A driver may fail on the call itself, before its iterator yields.
            with self._choke(Op.GLOB, canon):
                matches = globber.glob(canon).__aiter__()
        except NotFound:
            return  # the listing bound: nothing has been yielded yet
        seen = False
        try:
            while True:
                entry: Entry | None = None
                try:
                    with self._choke(Op.GLOB, canon):
                        try:
                            entry = await matches.__anext__()
                        except StopAsyncIteration:
                            entry = None
                except NotFound:
                    # The listing bound, at the granularity a glob iterator exposes.
                    if seen:
                        raise
                    break
                if entry is None:
                    break
                seen = True
                if entry.kind != "file":
                    continue
                if not _keys.listable(entry.key):
                    omitted.note(entry.key)
                    continue
                yield self._file_info(entry)
        finally:
            omitted.log()

    # endregion

    # region: get_folder_info (BE-017)

    async def get_folder_info(self, path: str) -> FolderInfo:
        """The folder's aggregate, by push-down or over a listing."""
        self._guard()
        key = self._key(path)
        op = Op.GET_FOLDER_INFO
        if await self._flat_item(op, key):
            # A.3: an item is no folder, whatever raw entries lie below it.
            raise InvalidPath(f"Is a file, not a folder: {key}", path=key, backend=self.name)
        if self._stats is not None:
            try:
                with self._choke(op, key):
                    count, size, latest = await self._stats.folder_stats(key)
            except RemoteStoreError as err:
                # The push-down's refusal answers as the listing's first page would.
                if not await self._holds_nothing(err, op, key):
                    raise
                count, size, latest = 0, 0, None
            latest = None if latest is None else _known_modified_at(latest)
        else:
            tally = FolderTally()
            omitted = _Omitted(self.name, key)
            try:
                async for entry in self._listed_files(op, key, True, omitted):
                    tally.add(entry)
            finally:
                omitted.log()
            count, size, latest = tally.count, tally.size, tally.latest
        if count == 0 and key:
            # An empty aggregate is a folder, a file or nothing. Without folder
            # objects this is the error path's type probe, fail-open; with them an
            # empty folder exists, so the stat is the determinant and fails closed
            # (BE-021's fail-open is a property of the call site).
            # On a flat namespace A.3's stat already ruled out an item, so only the
            # listing that tells a folder of omitted keys from nothing is left.
            seen = await (self._flat_folder(op, key) if self._flat else self._state(op, key, walk=False))
            if seen.error is not None and self._driver.parents != "none":
                raise seen.error
            if seen.state is _State.FILE:
                raise InvalidPath(f"Is a file, not a folder: {key}", path=key, backend=self.name)
            if seen.state is not _State.FOLDER:
                raise NotFound(f"Not found: {key}", path=key, backend=self.name)
        return FolderInfo(path=RemotePath.from_backend_path(key), file_count=count, total_size=size, modified_at=latest)

    # endregion

    # region: delete_folder (BE-031; spec 003 § The store tree, A.5's delete-folder column)

    def _df_error(self, cls: type[RemoteStoreError], key: str) -> RemoteStoreError:
        messages = {
            NotFound: "Not found",
            InvalidPath: "Not a folder",
            DirectoryNotEmpty: "Folder is not empty",
        }
        return cls(f"{messages.get(cls, 'Refused')}: {key}", path=key, backend=self.name)

    async def _df_list(
        self,
        key: str,
        delimiter: str | None,
        limit: int | None,
        *,
        first: bool = False,
        mark_first: bool = False,
    ) -> tuple[list[str], list[str]]:
        """Raw keys under *key*, in listing order: files (and links), and folders. Unfiltered on purpose.

        A probe must see every entry, the omitted ones included, or it would
        call a folder holding only those empty. With *first*, a refusal of the
        first page is read as A.8's first-page rows (``_holds_nothing``). With
        *mark_first*, it is raised as ``_FirstPageRefused`` for the caller to
        answer. On a later page a refusal reports a change under the scan and
        propagates as itself (A.9).
        """
        files: list[str] = []
        folders: list[str] = []
        cursor: object | None = None
        page_one = True
        while True:
            try:
                with self._choke(Op.DELETE_FOLDER, key):
                    page = await self._driver.list_page(
                        key, delimiter=delimiter, cursor=cursor, limit=limit, follow_links=False
                    )
            except RemoteStoreError as err:
                if first and page_one and await self._holds_nothing(err, Op.DELETE_FOLDER, key, follow_links=False):
                    return [], []
                if mark_first and page_one:
                    raise _FirstPageRefused(err) from err
                raise
            page_one = False
            files += [e.key for e in page.entries if e.kind == "file"]
            folders += [e.key for e in page.entries if e.kind == "folder"]
            folders += list(page.prefixes)
            cursor = page.cursor
            if cursor is None or limit is not None:
                return files, folders

    def _df_answer(self, err: RemoteStoreError, answer: RemoteStoreError, missing_ok: bool) -> None:
        """Raise *answer* (*err* itself when the refusal stands), unless ``missing_ok`` absorbs a ``NotFound``."""
        if missing_ok and isinstance(answer, NotFound):
            return
        if answer is err:
            raise err
        raise answer from err

    async def _df_refused(self, err: RemoteStoreError, key: str, missing_ok: bool, *, remove: bool) -> None:
        """A refusal of *key*'s ``remove_folder`` (*remove*), its ``delete_tree``, or the walk's first listing.

        A.8's hierarchical rows: ``stat(k)`` not following a link (the call
        names the entry, A.7); an item is ``InvalidPath`` and a miss
        ``NotFound``. For ``remove_folder`` a folder gets one
        ``list_page(k, limit=1)``, and a non-empty one is
        ``DirectoryNotEmpty``. An empty folder, a folder for the other calls,
        or a probe that cannot answer leaves the refusal standing (rule 4).
        """
        answer = err
        if _in_probe_set(err):
            seen = await self._state(Op.DELETE_FOLDER, key, walk=False, follow_links=False)
            if seen.state is _State.FILE:
                answer = self._df_error(InvalidPath, key)
            elif seen.state in (_State.ABSENT, _State.UNDER_FILE):
                answer = self._df_error(NotFound, key)
            elif seen.state is _State.FOLDER and remove:
                with contextlib.suppress(RemoteStoreError):
                    files, folders = await self._df_list(key, "/", 1)
                    if files or folders:
                        answer = self._df_error(DirectoryNotEmpty, key)
        self._df_answer(err, answer, missing_ok)

    async def _df_prefix_refused(self, err: RemoteStoreError, key: str, missing_ok: bool) -> None:
        """A ``delete_tree`` refusal without folder objects: A.8's flat ``delete_tree`` row.

        ``list_page(k, limit=1)`` first: anything listed leaves the refusal
        standing. After an empty listing, ``stat(k)``: an item is
        ``InvalidPath`` and a miss ``NotFound``. A probe that cannot answer
        leaves the refusal standing.
        """
        answer = err
        if _in_probe_set(err):
            with contextlib.suppress(RemoteStoreError):
                # On a flat namespace a miss of the probe's listing is an empty listing, by the
                # flat listing obligation; elsewhere it is a probe that cannot answer.
                files, folders = await self._df_list(key, None, 1, first=self._flat)
                if not files and not folders:
                    seen = await self._state(Op.DELETE_FOLDER, key, walk=False, folders=False, follow_links=False)
                    if seen.state is _State.FILE:
                        answer = self._df_error(InvalidPath, key)
                    elif seen.state in (_State.ABSENT, _State.UNDER_FILE):
                        answer = self._df_error(NotFound, key)
        self._df_answer(err, answer, missing_ok)

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
                await self._df_refused(err, key, missing_ok, remove=True)
            return None
        if self._tree is not None:
            try:
                with self._choke(Op.DELETE_FOLDER, key):
                    await self._tree.delete_tree(key)
            except RemoteStoreError as err:
                await self._df_refused(err, key, missing_ok, remove=False)
            return None
        return await self._df_walk(key, missing_ok, remover)

    async def _df_walk(self, key: str, missing_ok: bool, remover: AsyncSupportsRemoveFolder) -> None:
        files: list[str] = []
        folders: list[str] = []
        stack = [key]
        while stack:
            current = stack.pop()
            try:
                found_files, found_folders = await self._df_list(current, "/", None, mark_first=current == key)
            except _FirstPageRefused as refused:
                # The operation's first page, read through A.5 (A.9).
                return await self._df_refused(refused.err, key, missing_ok, remove=False)
            except RemoteStoreError as err:
                if current != key and isinstance(err, NotFound):
                    continue  # the subfolder is gone already
                raise  # after the operation's first page a refusal propagates (A.9)
            # A key BE-030 omits is never handed to the driver. It stays, so the
            # remove_folder of the folder holding it refuses with DirectoryNotEmpty:
            # below key that refusal propagates, and at key it answers through
            # remove_folder's row.
            files += [f for f in found_files if _keys.listable(f)]
            listable = [f for f in found_folders if _keys.listable(f)]
            folders += listable
            stack += listable
        for file in files:
            try:
                with self._choke(Op.DELETE_FOLDER, file):
                    await self._driver.delete(file)
            except NotFound:
                continue  # gone already
        for folder in sorted(folders, key=lambda f: -f.count("/")):
            try:
                with self._choke(Op.DELETE_FOLDER, folder):
                    await remover.remove_folder(folder)
            except NotFound:
                continue
        try:
            with self._choke(Op.DELETE_FOLDER, key):
                await remover.remove_folder(key)
        except RemoteStoreError as err:
            await self._df_refused(err, key, missing_ok, remove=True)
        return None

    async def _df_none(self, key: str, recursive: bool, missing_ok: bool) -> None:
        """Without folder objects: list first, ``stat`` only after an empty listing.

        On a flat namespace A.3's ``stat`` comes first instead, since a listing
        of ``k/`` cannot see an item ``k``: an item is ``InvalidPath`` and
        nothing is removed, whatever raw entries lie below it.
        """
        if await self._flat_item(Op.DELETE_FOLDER, key):
            raise self._df_error(InvalidPath, key)
        if not recursive:
            files, folders = await self._df_list(key, "/", 1, first=True)
            if files or folders:
                raise self._df_error(DirectoryNotEmpty, key)
            return await self._df_empty(key, missing_ok)
        if self._tree is not None:
            files, _ = await self._df_list(key, None, 1, first=True)
            if not files:
                return await self._df_empty(key, missing_ok)
            try:
                with self._choke(Op.DELETE_FOLDER, key):
                    await self._tree.delete_tree(key)
            except RemoteStoreError as err:
                await self._df_prefix_refused(err, key, missing_ok)
            return None
        files, _ = await self._df_list(key, None, None, first=True)
        if not files:
            return await self._df_empty(key, missing_ok)
        # A listing never hands the driver a key it omits: one BE-030 refuses, or
        # one below a listed item (A.3). It stays, and keeps the folder non-empty.
        below = _Shadows(self._flat).below(files, [])
        left = False
        for file in files:
            if file in below or not _keys.listable(file):
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
        """After an empty listing: an item is ``InvalidPath``, anything else ``NotFound``.

        On a flat namespace A.3's ``stat`` already ruled an item out. The
        ``stat`` fails open: one that cannot answer leaves ``NotFound``.
        """
        if not self._flat:
            seen = await self._state(Op.DELETE_FOLDER, key, walk=False, follow_links=False)
            if seen.state is _State.FILE:
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
