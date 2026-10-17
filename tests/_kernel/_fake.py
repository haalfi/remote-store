"""A fake driver for the contract kernel, and one runner per runtime.

``FakeStore`` is an in-memory wire. ``make_kernel`` puts a sync or an async
driver face over it, with exactly the optional protocols a cell asks for, and
returns a ``Runner`` whose methods call the kernel the same way in both
runtimes: listings come back as lists, ``read`` as bytes, awaitables awaited.
So every cell runs unchanged against the async kernel and its generated sync
twin.

Native exceptions are the ``Fake*`` classes below; the driver's ``classify``
maps them the way a wire classifier does, so the kernel's choke point, not the
fake, produces every typed error a cell sees.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import io
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from remote_store._capabilities import Capability, CapabilitySet
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
from remote_store._kernel._model import Entry, Op, Page, PutResult
from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend
from remote_store._resolution import ResolutionPlan

RUNTIMES = ("sync", "async")
T0 = datetime(2026, 1, 1, tzinfo=UTC)

_LOOP: asyncio.AbstractEventLoop | None = None


def run_async(awaitable: Any) -> Any:
    """Run *awaitable* on one event loop kept for the process.

    Not ``asyncio.run``: that builds a new loop per call, and on Windows each
    Proactor loop opens a socket pair, so a product of tens of thousands of
    async cells exhausted the socket buffers (WinError 10055) and crashed
    xdist workers.
    """
    global _LOOP  # noqa: PLW0603 - one loop per process, created on first use
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    return _LOOP.run_until_complete(awaitable)


# --- the wire's native exceptions ---------------------------------------------


class FakeWireError(Exception):
    """Base of the fake wire's native exceptions."""


class FakeMissing(FakeWireError):
    """The key is not there (ENOENT)."""


class FakeNotDir(FakeWireError):
    """A path component, or the key itself, is a file (ENOTDIR) on a read, a delete or a listing.

    Typed ``NotFound``, as Local and SFTP type it there.
    """


class FakeParentIsFile(FakeWireError):
    """A write under a file: ENOTDIR on the write path, typed ``InvalidPath`` as Local and SFTP do."""


class FakeIsDir(FakeWireError):
    """The key is a folder (EISDIR)."""


class FakeExists(FakeWireError):
    """The key is taken."""


class FakeNotEmpty(FakeWireError):
    """The folder has children (ENOTEMPTY)."""


class FakeDenied(FakeWireError):
    """Access denied."""


class FakeDown(FakeWireError):
    """The service cannot be reached."""


class FakeOdd(FakeWireError):
    """A shape the classifier does not recognise: maps untyped."""


class FakeContainerGone(FakeWireError):
    """The bucket, container or table is absent."""


_CLASSIFY: dict[type[FakeWireError], type[RemoteStoreError]] = {
    FakeMissing: NotFound,
    FakeNotDir: NotFound,
    FakeParentIsFile: InvalidPath,
    FakeIsDir: InvalidPath,
    FakeExists: AlreadyExists,
    FakeNotEmpty: DirectoryNotEmpty,
    FakeDenied: PermissionDenied,
    FakeDown: BackendUnavailable,
    FakeContainerGone: BackendUnavailable,
}


# --- the wire -----------------------------------------------------------------


@dataclasses.dataclass
class Fault:
    """Raise *exc* (or run *hook*) on the *nth* matching call of *prim*."""

    prim: str
    key: str | None = None
    nth: int = 1
    exc: BaseException | None = None
    hook: Callable[[], None] | None = None
    seen: int = 0


@dataclasses.dataclass
class FileRec:
    data: bytes
    modified_at: datetime = T0
    metadata: dict[str, str] | None = None


class FakeStore:
    """An in-memory tree or key space, with faults and a call log.

    ``parents``: ``"explicit"`` and ``"implicit"`` keep folders as their own
    nodes until ``remove_folder`` or ``delete_tree`` removes them, as Graph and
    Azure HNS do; ``"implicit"`` creates the missing ones on a write, where
    ``"explicit"`` refuses it. ``"none"`` derives folders from keys. ``links`` maps a key to the target
    key; a link resolves through it with ``follow_links``, and is a
    non-folder entry without it.

    ``namespace`` is set by ``make_kernel`` from the driver's. A hierarchical
    wire cannot hold a file where a folder is, nor under a file, so its write
    primitives refuse both; a flat one writes either (BE-008's exemption).
    ``folder_refusal``, when set, is the native shape every primitive raises
    at a folder where it needs a file (a wire's EEXIST, Windows EACCES, an
    unrecognised code), and the shape a write or ``ensure_parents`` raises
    under a file; unset, writes raise ``FakeIsDir`` at a folder and
    ``FakeParentIsFile`` under a file, and reads ``FakeMissing``.
    ``stat_fault``, when set, is asked for every ``stat`` and returns the
    native class to raise for that key, or ``None`` to answer (a POSIX
    ``stat`` raising ENOTDIR under a file, a denial of one key, a dead
    service); unset, ``stat`` answers, ``None`` under a file.
    ``listing_refusal``, when set, is the shape ``list_page`` raises for a
    prefix that is a file or lies under one (POSIX ENOTDIR, Windows WinError
    267, an unrecognised code); unset, ``FakeNotDir`` for a file and
    ``FakeMissing`` under one. ``dst_first`` makes the two-key primitives
    check the destination before the source.
    """

    def __init__(self, *, parents: str = "explicit", page_size: int = 1000) -> None:
        self.parents = parents
        self.namespace = "hierarchical"
        self.folder_refusal: type[FakeWireError] | None = None
        self.stat_fault: Callable[[str], type[FakeWireError] | None] | None = None
        self.listing_refusal: type[FakeWireError] | None = None
        self.dst_first = False
        self.files: dict[str, FileRec] = {}
        self.folders: set[str] = set()
        self.links: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self.faults: list[Fault] = []
        self.container = True
        self.page_size = page_size
        self.range_cap: int | None = None

    # arrangement

    def add(self, *keys: str, data: bytes = b"x", modified_at: datetime = T0) -> FakeStore:
        for key in keys:
            if key.endswith("/"):
                self._mkdirs(key.rstrip("/") + "/_")
                self.folders.add(key.rstrip("/"))
            else:
                self._mkdirs(key)
                self.files[key] = FileRec(data, modified_at)
        return self

    def _mkdirs(self, key: str) -> None:
        if self.parents != "none":
            parts = key.split("/")
            self.folders.update("/".join(parts[:i]) for i in range(1, len(parts)))

    def fault(
        self,
        prim: str,
        exc: BaseException | None = None,
        *,
        key: str | None = None,
        nth: int = 1,
        hook: Callable[[], None] | None = None,
    ) -> FakeStore:
        self.faults.append(Fault(prim, key, nth, exc, hook))
        return self

    def called(self, prim: str | None = None) -> list[tuple[str, str]]:
        return [c for c in self.calls if prim is None or c[0] == prim]

    # internals

    def _hit(self, prim: str, key: str) -> None:
        self.calls.append((prim, key))
        if not self.container:
            raise FakeContainerGone(f"container gone: {key}")
        for fault in self.faults:
            if fault.prim == prim and (fault.key is None or fault.key == key):
                fault.seen += 1
                if fault.seen == fault.nth:
                    if fault.hook is not None:
                        fault.hook()
                    if fault.exc is not None:
                        raise fault.exc

    def _resolve(self, key: str, follow: bool) -> str:
        return self.links.get(key, key) if follow else key

    def kind(self, key: str, follow: bool = True) -> str | None:
        if key in self.links:
            if not follow:
                return "file"
            key = self.links[key]
            if key not in self.files and not self._is_folder(key):
                return None
        if key in self.files:
            return "file"
        return "folder" if self._is_folder(key) else None

    def _is_folder(self, key: str) -> bool:
        if key == "":
            return True
        if key in self.folders:
            return True
        if self.parents != "none":
            return False
        prefix = key + "/"
        return any(k.startswith(prefix) for k in self.files) or any(f.startswith(prefix) for f in self.folders)

    def _under_file(self, key: str) -> bool:
        parts = key.split("/")
        return any("/".join(parts[:i]) in self.files for i in range(1, len(parts)))

    def _entry(self, key: str, follow: bool) -> Entry:
        kind = self.kind(key, follow)
        if kind == "file" and (self._resolve(key, follow) in self.files):
            rec = self.files[self._resolve(key, follow)]
            return Entry(key, "file", len(rec.data), rec.modified_at, metadata=rec.metadata)
        return Entry(key, "folder" if kind == "folder" else "file")

    def _children(self, prefix: str) -> tuple[list[str], list[str]]:
        """Immediate file and folder keys under *prefix* (links counted as files).

        On a flat wire an item ``k`` and a prefix ``k/`` are both listed, as a
        real flat wire lists them: the raw state that decodes to no tree.
        """
        base = prefix + "/" if prefix else ""
        names: set[str] = set()
        folders: set[str] = set()
        for key in [*self.files, *self.links, *self.folders]:
            if not key.startswith(base) or key == prefix:
                continue
            rest = key[len(base) :]
            head = rest.split("/", 1)[0]
            if "/" in rest or key in self.folders:
                folders.add(base + head)
            else:
                names.add(key)
        return sorted(names if self.namespace == "flat" else names - folders), sorted(folders)

    # primitives (sync; the async face awaits nothing)

    def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        self._hit("stat", key)
        if self.stat_fault is not None and (raised := self.stat_fault(key)) is not None:
            raise raised(key)
        # A flat stat is a lookup of the key alone: it finds a raw entry below an item.
        hidden = self.namespace != "flat" and self._under_file(key)
        if hidden or self.kind(key, follow_links) is None:
            return None
        return self._entry(key, follow_links)

    def _not_a_file(self, key: str) -> FakeWireError:
        """What a read, a delete or a two-key source raises for a key that is no file."""
        if self.folder_refusal is not None and not self._under_file(key) and self.kind(key) == "folder":
            return self.folder_refusal(key)
        return FakeMissing(key)

    def get(self, key: str) -> bytes:
        self._hit("get", key)
        target = self._resolve(key, True)
        if target not in self.files:
            raise self._not_a_file(key)
        return self.files[target].data

    def _write_refusal(self, key: str) -> FakeWireError | None:
        """What a hierarchical wire refuses at a write's target: a folder, or a file above it.

        A flat wire refuses neither: BE-008's flat exemption, so a key may
        shadow a prefix or sit under a file.
        """
        if self.namespace == "flat":
            return None
        if self._under_file(key):
            return (self.folder_refusal or FakeParentIsFile)(key)
        if self.kind(key) == "folder":
            return (self.folder_refusal or FakeIsDir)(key)
        return None

    def _transfer_refusal(self, src: str, dst: str, overwrite: bool) -> FakeWireError | None:
        """A two-key primitive's checks, in the wire's order (``dst_first``)."""
        src_refusal = None if src in self.files else self._not_a_file(src)
        dst_refusal = self._write_refusal(dst)
        if dst_refusal is None and dst in self.files and not overwrite:
            dst_refusal = FakeExists(dst)
        first, second = (dst_refusal, src_refusal) if self.dst_first else (src_refusal, dst_refusal)
        return first or second

    def put(self, key: str, data: bytes, *, overwrite: bool, metadata: Any) -> PutResult:
        self._hit("put", key)
        if (refusal := self._write_refusal(key)) is not None:
            raise refusal
        if self.parents == "explicit" and "/" in key and key.rsplit("/", 1)[0] not in self.folders:
            raise FakeMissing(f"no parent: {key}")
        if key in self.files and not overwrite:
            raise FakeExists(key)
        self._mkdirs(key)  # an implicit wire creates the missing folders
        self.files[key] = FileRec(data, T0, dict(metadata) if metadata else None)
        return PutResult(size=len(data))

    def delete(self, key: str) -> None:
        self._hit("delete", key)
        if key in self.links:
            del self.links[key]
            return
        if key not in self.files:
            raise self._not_a_file(key)
        del self.files[key]

    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: Any = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        self._hit("list_page", prefix)
        if prefix and self.parents != "none":
            kind = self.kind(prefix, follow_links)
            if kind == "file":
                raise (self.listing_refusal or FakeNotDir)(prefix)
            if kind is None:
                if self.listing_refusal is not None and self._under_file(prefix):
                    raise self.listing_refusal(prefix)
                raise FakeMissing(prefix)
        if delimiter is None:
            base = prefix + "/" if prefix else ""
            keys = sorted(k for k in [*self.files, *self.links] if k.startswith(base))
            entries = [self._entry(k, follow_links) for k in keys]
            prefixes: list[str] = []
        else:
            names, folders = self._children(self._resolve(prefix, follow_links) if prefix else prefix)
            if prefix and prefix in self.links and follow_links:
                target = self.links[prefix]
                names = [prefix + n[len(target) :] for n in names]
                folders = [prefix + f[len(target) :] for f in folders]
            entries = [self._entry(k, follow_links) for k in names]
            prefixes = folders
        # Byte-lexicographic order, a prefix ``p`` as ``p/``: the flat listing obligation.
        items: list[Entry | str] = sorted(
            [*entries, *prefixes], key=lambda e: e.key if isinstance(e, Entry) else e + "/"
        )
        start = int(cursor or 0)
        size = min(limit or self.page_size, self.page_size)
        chunk = items[start : start + size]
        nxt = start + size if start + size < len(items) and limit is None else None
        return Page(
            entries=tuple(e for e in chunk if isinstance(e, Entry)),
            prefixes=tuple(p for p in chunk if isinstance(p, str)),
            cursor=nxt,
        )

    def probe(self) -> None:
        self._hit("probe", "")

    def close(self) -> None:
        self.calls.append(("close", ""))

    # optional primitives

    def get_range(self, key: str, offset: int, length: int) -> bytes:
        self._hit("get_range", key)
        if key not in self.files:
            raise FakeMissing(key)
        # ``range_cap``: a wire that answers a range with fewer bytes than asked.
        return self.files[key].data[offset : offset + min(length, self.range_cap or length)]

    def move(self, src: str, dst: str, *, overwrite: bool) -> None:
        self._hit("move", src)
        if (refusal := self._transfer_refusal(src, dst, overwrite)) is not None:  # SupportsAtomicMove's obligation
            raise refusal
        self._implicit_parents(dst)
        self.files[dst] = self.files.pop(src)

    def _implicit_parents(self, key: str) -> None:
        if self.parents == "implicit":
            self._mkdirs(key)

    def rename(self, src: str, dst: str, *, replace: bool) -> None:
        self._hit("rename", src)
        # SupportsRename's obligation, as rename(2) and os.replace refuse a folder.
        if (refusal := self._transfer_refusal(src, dst, replace)) is not None:
            raise refusal
        self._implicit_parents(dst)
        self.files[dst] = self.files.pop(src)

    def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        self._hit("copy", src)
        if (refusal := self._transfer_refusal(src, dst, overwrite)) is not None:  # SupportsCopy's obligation
            raise refusal
        rec = self.files[src]
        self._implicit_parents(dst)
        self.files[dst] = FileRec(rec.data, rec.modified_at, rec.metadata)

    def delete_tree(self, key: str) -> None:
        self._hit("delete_tree", key)
        if self.parents == "none":  # a prefix delete: no folder objects, so nothing to refuse
            self.files = {k: v for k, v in self.files.items() if not k.startswith(key + "/")}
            self.links = {k: v for k, v in self.links.items() if not k.startswith(key + "/")}
            return
        kind = self.kind(key, False)
        if kind is None or self._under_file(key):
            raise FakeMissing(key)
        if kind == "file":
            raise FakeNotDir(key)
        prefix = key + "/"
        self.files = {k: v for k, v in self.files.items() if not k.startswith(prefix)}
        self.links = {k: v for k, v in self.links.items() if not k.startswith(prefix)}
        self.folders = {f for f in self.folders if f != key and not f.startswith(prefix)}

    def remove_folder(self, key: str) -> None:
        self._hit("remove_folder", key)
        kind = self.kind(key, False)
        if kind is None or self._under_file(key):
            raise FakeMissing(key)
        if kind == "file":
            raise FakeNotDir(key)
        names, folders = self._children(key)
        if names or folders:
            raise FakeNotEmpty(key)
        self.folders.discard(key)

    def ensure_parents(self, key: str) -> None:
        self._hit("ensure_parents", key)
        if self._under_file(key):
            raise (self.folder_refusal or FakeParentIsFile)(key)
        self._mkdirs(key)

    def folder_stats(self, prefix: str) -> tuple[int, int, datetime | None]:
        self._hit("folder_stats", prefix)
        base = prefix + "/" if prefix else ""
        recs = [r for k, r in self.files.items() if k.startswith(base)]
        latest = max((r.modified_at for r in recs), default=None)
        return len(recs), sum(len(r.data) for r in recs), latest

    def glob(self, pattern: str) -> list[Entry]:
        self._hit("glob", pattern)
        import fnmatch

        return [self._entry(k, True) for k in sorted(self.files) if fnmatch.fnmatchcase(k, pattern.rstrip("/"))]


# --- driver faces ---------------------------------------------------------------

ALL_PROTOCOLS = (
    "range",
    "open_write",
    "atomic_move",
    "rename",
    "copy",
    "delete_tree",
    "remove_folder",
    "ensure_parents",
    "folder_stats",
    "glob",
)


class _Handle:
    def __init__(self, store: FakeStore, key: str, overwrite: bool, metadata: Any) -> None:
        self.store, self.key, self.overwrite, self.metadata = store, key, overwrite, metadata
        self.buf = bytearray()
        self.state = "open"
        store.handles.append(self)  # type: ignore[attr-defined]

    def write(self, data: bytes) -> None:
        self.store._hit("handle.write", self.key)
        self.buf += data

    def commit(self) -> PutResult:
        self.store._hit("handle.commit", self.key)
        result = self.store.put(self.key, bytes(self.buf), overwrite=self.overwrite, metadata=self.metadata)
        self.state = "committed"
        return result

    def abort(self) -> None:
        self.store._hit("handle.abort", self.key)
        self.state = "aborted"


class _SyncBase:
    """The required primitives over a ``FakeStore``, sync."""

    def __init__(
        self,
        store: FakeStore,
        *,
        name: str,
        namespace: str,
        parents: str,
        caps: CapabilitySet,
        put_is_atomic: bool,
        close_is_terminal: bool,
        rename_replaces: bool,
    ) -> None:
        self.store = store
        self.name = name
        self.namespace = namespace
        self.parents = parents
        self.capabilities = caps
        self.put_is_atomic = put_is_atomic
        self.close_is_terminal = close_is_terminal
        self.rename_replaces = rename_replaces
        self.stream_catch: tuple[type[Exception], ...] = (FakeWireError,)
        self.classified: list[tuple[str, Op, str]] = []

    def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        return _flat_stat(self, self.store.stat(key, follow_links=follow_links))

    def get(self, key: str) -> Any:
        return _FaultyStream(self.store, key, self.store.get(key))

    def put(self, key: str, content: Any, *, overwrite: bool, metadata: Any) -> PutResult:
        data = content if isinstance(content, bytes) else content.read()
        return self.store.put(key, data, overwrite=overwrite, metadata=metadata)

    def delete(self, key: str) -> None:
        self.store.delete(key)

    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: Any = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        return self.store.list_page(prefix, delimiter=delimiter, cursor=cursor, limit=limit, follow_links=follow_links)

    def probe(self) -> None:
        self.store.probe()

    def close(self) -> None:
        self.store.close()

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        self.classified.append((type(exc).__name__, op, key))
        cls = _CLASSIFY.get(type(exc), RemoteStoreError)  # type: ignore[arg-type]
        return cls(str(exc))

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        return isinstance(exc, FakeContainerGone)

    def connection_dead(self, exc: BaseException) -> bool:
        return isinstance(exc, FakeDown)

    def unwrap(self, type_hint: type[Any]) -> Any:
        if type_hint is FakeStore:
            return self.store
        # BE-022's refusal, which the kernel passes through untouched.
        raise CapabilityNotSupported(f"no native handle of type {type_hint.__name__}", capability="unwrap")

    def native_path(self, key: str) -> str:
        return f"fake://{key}"

    def to_key(self, native_path: str) -> str:
        return native_path.removeprefix("fake://")

    def resolve(self, key: str) -> ResolutionPlan:
        return ResolutionPlan(kind="fake", backend=self.name, key=key, native_path=f"plan:{key}", details={})


def _flat_stat(driver: _SyncBase, entry: Entry | None) -> Entry | None:
    # A flat wire's stat is a HEAD on the key: it never sees a prefix as a folder.
    if driver.namespace == "flat" and entry is not None and entry.kind == "folder":
        return None
    return entry


class NonBlockingRaw(io.RawIOBase):
    """A caller's non-blocking raw stream: ``readinto`` answers ``b"ab"``, ``None`` (no data yet), ``b"c"``.

    Its own unsized ``read()`` is ``readall``, which stops at the ``None`` and answers ``b"ab"``.
    """

    def __init__(self) -> None:
        self._answers: list[bytes | None] = [b"ab", None, b"c"]

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes | None:
        # io.RawIOBase.read takes its size positionally only; this one also takes size=.
        return super().read(size)

    def readinto(self, buffer: Any) -> int | None:  # type: ignore[override]
        answer = self._answers.pop(0) if self._answers else b""
        if answer is None:
            return None
        buffer[: len(answer)] = answer
        return len(answer)


class _FaultyStream(io.BytesIO):
    """A read stream that raises an injected fault from ``stream.read``."""

    def __init__(self, store: FakeStore, key: str, data: bytes) -> None:
        super().__init__(data)
        self._store, self._key = store, key

    def read(self, size: int | None = -1) -> bytes:
        self._store._hit("stream.read", self._key)
        return super().read(size)

    def readinto(self, buffer: Any) -> int:
        self._store._hit("stream.read", self._key)
        return super().readinto(buffer)

    def close(self) -> None:
        if not self.closed and not getattr(self, "_finalising", False):
            self._store.calls.append(("stream.close", self._key))
        super().close()

    def __del__(self) -> None:
        # IOBase closes an unclosed stream at GC; only an explicit close is logged.
        self._finalising = True
        super().__del__()


_SYNC_OPTIONAL: dict[str, dict[str, Callable[..., Any]]] = {
    "range": {"get_range": lambda self, key, offset, length: self.store.get_range(key, offset, length)},
    "open_write": {
        "open_write": lambda self, key, *, overwrite, metadata: (
            self.store._hit("open_write", key) or _Handle(self.store, key, overwrite, metadata)
        )
    },
    "atomic_move": {"move": lambda self, src, dst, *, overwrite: self.store.move(src, dst, overwrite=overwrite)},
    "rename": {"rename": lambda self, src, dst, *, replace: self.store.rename(src, dst, replace=replace)},
    "copy": {"copy": lambda self, src, dst, *, overwrite: self.store.copy(src, dst, overwrite=overwrite)},
    "delete_tree": {"delete_tree": lambda self, key: self.store.delete_tree(key)},
    "remove_folder": {"remove_folder": lambda self, key: self.store.remove_folder(key)},
    "ensure_parents": {"ensure_parents": lambda self, key: self.store.ensure_parents(key)},
    "folder_stats": {"folder_stats": lambda self, prefix: self.store.folder_stats(prefix)},
    "glob": {"glob": lambda self, pattern: iter(self.store.glob(pattern))},
}


class _AsyncFaultyStream:
    """The async read stream: two-byte chunks, each read a fault point; a close is logged once."""

    def __init__(self, store: FakeStore, key: str, data: bytes) -> None:
        self._store, self._key, self._data = store, key, data
        self._pos = 0
        self.closed = False

    def __aiter__(self) -> _AsyncFaultyStream:
        return self

    async def __anext__(self) -> bytes:
        self._store._hit("stream.read", self._key)
        chunk = self._data[self._pos : self._pos + 2]
        if not chunk:
            raise StopAsyncIteration
        self._pos += len(chunk)
        return chunk

    async def aclose(self) -> None:
        if not self.closed:
            self._store.calls.append(("stream.close", self._key))
        self.closed = True


def _async_of(fn: Callable[..., Any]) -> Callable[..., Any]:
    async def method(self: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(self, *args, **kwargs)

    return method


class _AsyncHandle:
    def __init__(self, inner: _Handle) -> None:
        self.inner = inner

    async def write(self, data: bytes) -> None:
        self.inner.write(data)

    async def commit(self) -> PutResult:
        return self.inner.commit()

    async def abort(self) -> None:
        self.inner.abort()


class _AsyncBase(_SyncBase):
    async def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:  # type: ignore[override]
        return _flat_stat(self, self.store.stat(key, follow_links=follow_links))

    async def get(self, key: str) -> AsyncIterator[bytes]:  # type: ignore[override]
        return _AsyncFaultyStream(self.store, key, self.store.get(key))

    async def put(self, key: str, content: Any, *, overwrite: bool, metadata: Any) -> PutResult:  # type: ignore[override]
        data = content if isinstance(content, bytes) else b"".join([c async for c in content])
        return self.store.put(key, data, overwrite=overwrite, metadata=metadata)

    async def delete(self, key: str) -> None:  # type: ignore[override]
        self.store.delete(key)

    async def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: Any = None,  # type: ignore[override]
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        return self.store.list_page(prefix, delimiter=delimiter, cursor=cursor, limit=limit, follow_links=follow_links)

    async def probe(self) -> None:  # type: ignore[override]
        self.store.probe()

    async def aclose(self) -> None:
        self.store.close()


def _async_optional(name: str) -> dict[str, Callable[..., Any]]:
    if name == "glob":

        async def glob(self: Any, pattern: str) -> AsyncIterator[Entry]:
            for entry in self.store.glob(pattern):
                yield entry

        return {"glob": glob}
    if name == "open_write":

        async def open_write(self: Any, key: str, *, overwrite: bool, metadata: Any) -> _AsyncHandle:
            self.store._hit("open_write", key)
            return _AsyncHandle(_Handle(self.store, key, overwrite, metadata))

        return {"open_write": open_write}
    return {k: _async_of(v) for k, v in _SYNC_OPTIONAL[name].items()}


# --- the kernel under test, and how a cell calls it ---------------------------------


def _backed(protocols: tuple[str, ...], *, put_is_atomic: bool, rename_replaces: bool) -> set[Capability]:
    """The capabilities a driver presenting *protocols* declares.

    Always ``READ``, ``WRITE``, ``LIST``, ``DELETE`` and ``USER_METADATA``
    (the fake stores metadata); then each capability a presented protocol, or
    ``put_is_atomic``, backs.
    """
    caps = {Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE, Capability.USER_METADATA}
    replaces = "rename" in protocols and rename_replaces
    if put_is_atomic or "open_write" in protocols or replaces:
        caps.add(Capability.ATOMIC_WRITE)
    if "glob" in protocols:
        caps.add(Capability.GLOB)
    if "copy" in protocols:
        caps.add(Capability.COPY)
    if {"atomic_move", "rename", "copy"} & set(protocols):
        caps.add(Capability.MOVE)
    return caps


def make_kernel(
    runtime: str,
    store: FakeStore | None = None,
    *,
    protocols: tuple[str, ...] | None = None,
    namespace: str = "hierarchical",
    caps: tuple[Capability, ...] = (),
    put_is_atomic: bool = False,
    close_is_terminal: bool = False,
    rename_replaces: bool = True,
    exact: bool = False,
) -> Runner:
    """A kernel of *runtime* over a fake driver presenting *protocols*.

    Defaults: every optional protocol, less ``remove_folder`` on a
    ``parents == "none"`` store (where the kernel never calls it); the
    store's ``parents``; and the capabilities those protocols back
    (``_backed``), as a well-formed driver declares them. *caps*, when
    given, is declared exactly instead. An explicit-parents store always
    gets ``ensure_parents``, which construction requires, unless *exact*.
    """
    store = store or FakeStore()
    store.handles = []  # type: ignore[attr-defined]
    store.namespace = namespace
    if protocols is None:
        protocols = tuple(p for p in ALL_PROTOCOLS if p != "remove_folder" or store.parents != "none")
    if store.parents == "explicit" and "ensure_parents" not in protocols and not exact:
        protocols = (*protocols, "ensure_parents")
    base: type[_SyncBase] = _SyncBase if runtime == "sync" else _AsyncBase
    members: dict[str, Any] = {}
    for proto in protocols:
        members.update(_SYNC_OPTIONAL[proto] if runtime == "sync" else _async_optional(proto))
    cls = type(f"Fake{runtime.title()}Driver", (base,), members)
    capset = CapabilitySet(
        set(caps) or _backed(protocols, put_is_atomic=put_is_atomic, rename_replaces=rename_replaces)
    )
    driver = cls(
        store,
        name="fake",
        namespace=namespace,
        parents=store.parents,
        caps=capset,
        put_is_atomic=put_is_atomic,
        close_is_terminal=close_is_terminal,
        rename_replaces=rename_replaces,
    )
    base_cls = DriverBackend if runtime == "sync" else AsyncDriverBackend
    # A class on the kernel declares the driver's close posture as its own ClassVar.
    kernel_cls = type(f"Fake{runtime.title()}Kernel", (base_cls,), {"close_is_terminal": close_is_terminal})
    kernel = kernel_cls(driver)
    return Runner(runtime, kernel, store, driver)


class Runner:
    """Calls a kernel of either runtime and returns plain values."""

    def __init__(self, runtime: str, kernel: Any, store: FakeStore, driver: Any) -> None:
        self.runtime, self.kernel, self.store, self.driver = runtime, kernel, store, driver

    def close(self) -> None:
        if self.runtime == "sync":
            self.kernel.close()
        else:
            run_async(self.kernel.aclose())

    def __getattr__(self, name: str) -> Callable[..., Any]:
        method = getattr(self.kernel, name)
        if not callable(method):
            return method  # type: ignore[no-any-return]
        if name in ("native_path", "to_key", "resolve", "unwrap"):
            return method  # type: ignore[no-any-return]

        def call(*args: Any, **kwargs: Any) -> Any:
            result = method(*args, **kwargs)
            return _settle(result, name)

        return call

    def read(self, path: str) -> bytes:
        if self.runtime == "sync":
            with self.kernel.read(path) as stream:
                return bytes(stream.read())

        async def collect() -> bytes:
            return b"".join([chunk async for chunk in self.kernel.read(path)])

        return run_async(collect())

    def write(self, path: str, data: bytes, **kwargs: Any) -> Any:
        if self.runtime == "sync":
            return self.kernel.write(path, data, **kwargs)
        return run_async(self.kernel.write(path, data, **kwargs))


def _settle(result: Any, name: str) -> Any:
    if inspect.isasyncgen(result):

        async def collect() -> list[Any]:
            return [item async for item in result]

        return run_async(collect())
    if inspect.iscoroutine(result):
        return run_async(result)
    if isinstance(result, Iterator):
        return list(result)
    return result


def keys_of(items: list[Any]) -> list[str]:
    """The sorted paths of listed ``FileInfo`` / ``FolderEntry`` items."""
    return sorted(str(item.path) for item in items)
