"""AsyncBackendSyncAdapter -- bridges async backends into the sync world.

Implements the sync :class:`Backend` ABC by delegating to an
:class:`AsyncBackend` running on a private event loop in a dedicated
background thread.  Mirror of
:class:`remote_store.aio.SyncBackendAdapter` (ADR-0012); decision record
for this direction is ADR-0025, invariants pinned in spec 029
§ AsyncBackendSyncAdapter (ASYNC-080..093).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import functools
import io
import logging
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, TypeVar, cast, runtime_checkable

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Iterator, Mapping
    from contextlib import AbstractContextManager
    from types import TracebackType

    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent
    from remote_store.aio._async_backend import AsyncBackend

T = TypeVar("T")

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable message stems (spec 029 § AsyncBackendSyncAdapter)
# ---------------------------------------------------------------------------

_RUNNING_LOOP_MSG = "AsyncBackendSyncAdapter cannot be called from a running event loop; use AsyncStore instead."
_CLOSED_MSG = "AsyncBackendSyncAdapter is closed"
_CLOSE_TIMEOUT_MSG = "AsyncBackendSyncAdapter close timed out"

# Buffer size used when streaming a sync ``BinaryIO`` into the async backend.
_WRITE_CHUNK_SIZE = 64 * 1024

# Upper bound for in-memory spooling in ``open_atomic``; beyond this the
# spool rolls over to an on-disk temp file before flushing to write_atomic.
_OPEN_ATOMIC_SPOOL_MAX = 8 * 1024 * 1024


@runtime_checkable
class _SyncSafeHandleProvider(Protocol):
    """Opt-in protocol a wrapped async backend may implement to expose a
    sync-safe native handle through :meth:`AsyncBackendSyncAdapter.unwrap`.

    Mirrors ``SyncBackendAdapter.unwrap``'s exemption for wrappers that
    provide a synchronous handle (spec 029 § ASYNC-086).
    """

    def sync_safe_unwrap(self, type_hint: type[Any]) -> Any:
        """Return a sync-safe native handle for *type_hint*."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# AsyncBackendSyncAdapter
# ---------------------------------------------------------------------------


class AsyncBackendSyncAdapter(Backend):
    """Wraps an :class:`AsyncBackend` as a synchronous :class:`Backend`.

    One private ``asyncio`` event loop per adapter instance, running on
    a dedicated daemon thread for the adapter's lifetime.  Sync methods
    submit coroutines via :func:`asyncio.run_coroutine_threadsafe` and
    block on the returned :class:`concurrent.futures.Future`.

    Construction does not enter the wrapped backend's async context
    manager -- callers that need ``__aenter__`` semantics should use
    :class:`remote_store.aio.AsyncStore` directly.

    Args:
        async_backend: The async backend instance to wrap.

    See [ADR-0025](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0025-async-to-sync-backend-adapter.md)
    and [spec 029](https://github.com/haalfi/remote-store/blob/master/sdd/specs/029-async-store-backend-api.md)
    § AsyncBackendSyncAdapter for the full behaviour contract.
    """

    def __init__(self, async_backend: AsyncBackend) -> None:
        # Lazy import keeps the core module free of an unconditional
        # ``aio/`` dependency (ADR-0025 § Module placement).
        from remote_store.aio._async_backend import AsyncBackend as _AsyncBackend

        if not isinstance(async_backend, _AsyncBackend):
            raise TypeError(
                f"AsyncBackendSyncAdapter expects an AsyncBackend instance, got {type(async_backend).__name__}"
            )

        self._async_backend = async_backend
        self._closed = False
        self._close_lock = threading.Lock()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"AsyncBackendSyncAdapter-{id(self):x}",
            daemon=True,
        )
        self._thread.start()

    # -- Private loop thread ------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            with contextlib.suppress(Exception):  # pragma: no cover -- best-effort teardown
                self._loop.close()

    # -- Guards (ASYNC-082, ASYNC-083) --------------------------------------

    def _guard(self) -> None:
        """Check every blocking call for closed state and running-loop."""
        # _closed is read without the lock: it is written exactly once (False→True)
        # under _close_lock, so a racing reader either sees False (safe to proceed)
        # or True (fast-fail).  No torn write is possible on a bool.
        if self._closed:
            raise RuntimeError(_CLOSED_MSG)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError(_RUNNING_LOOP_MSG)

    # -- Submit/block helper ------------------------------------------------

    def _submit(self, coro: Any) -> Any:
        """Submit *coro* to the private loop and block on the result.

        Blocks indefinitely until the coroutine completes or raises.
        There is no per-call timeout: timeout responsibility belongs to
        the wrapped ``AsyncBackend`` (e.g. ``asyncio.wait_for`` inside
        the coroutine, or SDK session-level timeouts).  The adapter's
        ``close(timeout=…)`` provides a global shutdown bound; there is
        no per-operation equivalent.
        """
        # Caller built *coro* before the guard runs (Python evaluates the
        # argument first); on either failure path we close it explicitly so
        # CPython does not emit "coroutine was never awaited" RuntimeWarning.
        try:
            self._guard()
        except BaseException:
            coro.close()
            raise
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError:
            # Loop was stopped between _guard() and here (close() raced us).
            # Re-raise with the canonical stem so ASYNC-083 callers see a
            # stable message rather than asyncio's internal phrasing.
            coro.close()
            raise RuntimeError(_CLOSED_MSG) from None
        return future.result()

    # -- Properties ---------------------------------------------------------

    @property
    def name(self) -> str:
        """Backend identifier, forwarded from the wrapped async backend."""
        return self._async_backend.name

    @functools.cached_property
    def capabilities(self) -> CapabilitySet:
        """Capabilities with ASYNC-084 translation applied.

        ``SEEKABLE_READ`` is masked off unconditionally — the chunk-pull
        stream this adapter returns is forward-only.

        ``WRITE_RESULT_NATIVE`` and ``USER_METADATA`` are masked off until
        the async ABC grows a ``metadata=`` parameter (Step 3c).  Without
        masking, the Store layer would allow non-empty ``metadata=`` through
        (WR-010 gate passes), but the adapter has no forwarding target and
        would silently drop the metadata — a WR-012 violation.
        """
        _MASKED = {Capability.SEEKABLE_READ, Capability.WRITE_RESULT_NATIVE, Capability.USER_METADATA}
        inner = self._async_backend.capabilities
        return CapabilitySet({cap for cap in inner if cap not in _MASKED})

    # -- Non-I/O passthrough (no loop, no thread) ---------------------------

    def to_key(self, native_path: str) -> str:
        return self._async_backend.to_key(native_path)

    def native_path(self, path: str) -> str:
        return self._async_backend.native_path(path)

    def resolve(self, path: str) -> ResolutionPlan:
        return self._async_backend.resolve(path)

    def unwrap(self, type_hint: type[T]) -> T:
        """Return a sync-safe native handle if the wrapped backend provides one.

        By default raises :class:`~remote_store._errors.CapabilityNotSupported`
        because async-SDK handles are bound to the adapter's private event loop
        and cannot be used safely from the caller's thread.

        Wrapped backends that can expose a sync-safe handle should implement
        :class:`_SyncSafeHandleProvider` and return it from
        :meth:`~_SyncSafeHandleProvider.sync_safe_unwrap`
        (spec 029 § ASYNC-086).

        Args:
            type_hint: The type of handle to retrieve; passed through to
                :meth:`~_SyncSafeHandleProvider.sync_safe_unwrap` for backends
                that support the exemption.

        Returns:
            A sync-safe handle of the type requested via *type_hint*.

        Raises:
            CapabilityNotSupported: If the wrapped backend does not implement
                :class:`_SyncSafeHandleProvider`.

        Example:
            ```python
            class _SafeBackend(AsyncBackend, _SyncSafeHandleProvider):
                def sync_safe_unwrap(self, type_hint):
                    return self._sync_client

            adapter = AsyncBackendSyncAdapter(_SafeBackend())
            client = adapter.unwrap(SyncClient)
            ```
        """
        if isinstance(self._async_backend, _SyncSafeHandleProvider):
            return self._async_backend.sync_safe_unwrap(type_hint)  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend '{self.name}' is an async-native backend bridged through "
            f"AsyncBackendSyncAdapter; native handles of type "
            f"{type_hint.__name__} are bound to the adapter's private event "
            f"loop and cannot be used safely from sync code. "
            f"Construct an AsyncStore to access the native async handle.",
            capability="unwrap",
            backend=self.name,
        )

    # -- I/O scalars (ASYNC-087) --------------------------------------------

    def exists(self, path: str) -> bool:
        return bool(self._submit(self._async_backend.exists(path)))

    def is_file(self, path: str) -> bool:
        return bool(self._submit(self._async_backend.is_file(path)))

    def is_folder(self, path: str) -> bool:
        return bool(self._submit(self._async_backend.is_folder(path)))

    def read_bytes(self, path: str) -> bytes:
        result = self._submit(self._async_backend.read_bytes(path))
        return bytes(result)

    def get_file_info(self, path: str) -> FileInfo:
        return self._submit(self._async_backend.get_file_info(path))  # type: ignore[no-any-return]

    def get_folder_info(self, path: str) -> FolderInfo:
        return self._submit(self._async_backend.get_folder_info(path))  # type: ignore[no-any-return]

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._submit(self._async_backend.move(src, dst, overwrite=overwrite))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._submit(self._async_backend.copy(src, dst, overwrite=overwrite))

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._submit(self._async_backend.delete(path, missing_ok=missing_ok))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._submit(self._async_backend.delete_folder(path, recursive=recursive, missing_ok=missing_ok))

    def check_health(self) -> None:
        """Submit a connectivity probe to the wrapped async backend.

        Not a no-op: the probe is forwarded to the wrapped
        :class:`~remote_store.aio.AsyncBackend`, and any connectivity error
        it raises reaches the sync caller unchanged (spec 029 § ASYNC-093).

        Returns:
            ``None`` on success.

        Raises:
            BackendUnavailable: Or another backend-specific error if the
                wrapped backend's health check fails.
            RuntimeError: If the adapter is closed or called from a running
                event loop.

        Example:
            ```python
            try:
                adapter.check_health()
            except BackendUnavailable:
                ...  # handle connectivity failure
            ```
        """
        self._submit(self._async_backend.check_health())

    # -- Streaming read (ASYNC-080, ASYNC-081) ------------------------------

    def read(self, path: str) -> BinaryIO:
        """Open *path* for reading and return a forward-only chunk-pull stream.

        The returned stream pulls one async chunk per ``read()`` call; the
        file is never fully materialised in memory.  At most one
        ``__anext__`` is in-flight at a time (spec 029 § ASYNC-081).

        The stream is forward-only: ``seekable()`` returns ``False`` and no
        ``seek`` / ``tell`` / ``fileno`` methods are exposed.  Closing via
        the context manager or ``close()`` submits ``aclose()`` on the
        underlying async iterator so backend resources are released promptly.

        Args:
            path: Backend-relative key of the file to read.

        Returns:
            A forward-only :class:`io.RawIOBase` stream over the file
            contents.

        Raises:
            RuntimeError: If the adapter is closed or called from a running
                event loop.
            NotFound: If *path* does not exist (propagated verbatim from the
                wrapped backend).

        Example:
            ```python
            with adapter.read("data/report.csv") as stream:
                header = stream.read(512)
            ```
        """
        self._guard()
        async_gen = cast("AsyncGenerator[bytes, None]", self._async_backend.read(path))
        return _ChunkPullReader(self, async_gen)  # type: ignore[return-value]

    # -- Listing iterators (ASYNC-080) --------------------------------------

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        self._guard()
        async_iter = self._async_backend.list_files(
            path,
            recursive=recursive,
            max_depth=max_depth,
        ).__aiter__()
        return _AsyncIteratorBridge(self, async_iter)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        self._guard()
        async_iter = self._async_backend.list_folders(path).__aiter__()
        return _AsyncIteratorBridge(self, async_iter)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        self._guard()
        async_iter = self._async_backend.glob(pattern).__aiter__()
        return _AsyncIteratorBridge(self, async_iter)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        self._guard()
        async_iter = self._async_backend.iter_children(path).__aiter__()
        return _AsyncIteratorBridge(self, async_iter)

    # -- Writes (ASYNC-091) -------------------------------------------------

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        from remote_store._models import WriteResult
        from remote_store._path import RemotePath

        # USER_METADATA is masked in capabilities() so the Store-layer WR-010
        # gate rejects non-empty metadata= before reaching here.  Callers that
        # bypass the Store and call the adapter directly still get a clean error
        # rather than a silent drop (defense-in-depth, ADR-0026 adapter masking).
        if metadata:
            raise CapabilityNotSupported(
                "AsyncBackendSyncAdapter does not support user metadata (Step 3c pending); "
                "pass metadata= through a Store instead.",
                capability="USER_METADATA",
                backend=self.name,
            )
        if isinstance(content, (bytes, bytearray, memoryview)):
            raw = bytes(content)
            self._submit(self._async_backend.write(path, raw, overwrite=overwrite))
            size = len(raw)
        else:
            counter = _CountingBinaryIO(content)
            async_iter = _binaryio_to_async_iter(counter)  # type: ignore[arg-type]
            self._submit(self._async_backend.write(path, async_iter, overwrite=overwrite))
            size = counter.count
        return WriteResult(path=RemotePath(path), size=size, source="basic")

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        from remote_store._models import WriteResult
        from remote_store._path import RemotePath

        # Same defense-in-depth guard as write() above.
        if metadata:
            raise CapabilityNotSupported(
                "AsyncBackendSyncAdapter does not support user metadata (Step 3c pending); "
                "pass metadata= through a Store instead.",
                capability="USER_METADATA",
                backend=self.name,
            )
        if isinstance(content, (bytes, bytearray, memoryview)):
            raw = bytes(content)
            self._submit(self._async_backend.write_atomic(path, raw, overwrite=overwrite))
            size = len(raw)
        else:
            counter = _CountingBinaryIO(content)
            async_iter = _binaryio_to_async_iter(counter)  # type: ignore[arg-type]
            self._submit(self._async_backend.write_atomic(path, async_iter, overwrite=overwrite))
            size = counter.count
        return WriteResult(path=RemotePath(path), size=size, source="basic")

    # -- open_atomic synthesis (ASYNC-085) ----------------------------------

    def open_atomic(self, path: str, *, overwrite: bool = False) -> AbstractContextManager[BinaryIO]:
        self._guard()
        return _SpoolAndFlush(self, path, overwrite=overwrite)

    # -- Lifecycle (ASYNC-088, ASYNC-092) -----------------------------------

    def close(self, timeout: float | None = 30.0) -> None:
        """Drain in-flight work, stop the loop, and join the daemon thread.

        Drain order: submit ``aclose`` on the wrapped backend → loop-drain
        in-flight tasks (repeating while new tasks appear, see below) → stop
        the private loop → join the daemon thread.

        The drain step repeats :func:`_drain_tasks` until the private loop is
        quiet, **narrowing** (not eliminating) the window where a caller that
        passed :meth:`_guard` *before* the closed flag was set can still submit
        a coroutine.  Each pass snapshots outstanding tasks and waits for them;
        new tasks that arrive between snapshot and completion trigger another
        pass.  A residual TOCTOU gap remains: a thread that passes
        :meth:`_guard` after the final empty-snapshot check but before the loop
        is stopped will have its coroutine silently discarded when the loop
        stops — eliminating this gap would require serialising all submits
        against a shutdown lock.

        If *timeout* expires before the loop is drained, a single ``WARNING``
        record is emitted (message stem
        ``"AsyncBackendSyncAdapter close timed out"``) and the daemon thread
        is left for process-exit reaping.  Idempotent: subsequent calls are
        no-ops.

        Args:
            timeout: Maximum seconds to wait for in-flight work to finish and
                the background thread to join.  ``None`` means wait
                indefinitely.  Defaults to ``30.0``.
        """
        with self._close_lock:
            if self._closed:
                return
            self._closed = True

        deadline: float | None = None if timeout is None else time.monotonic() + timeout

        def _remaining() -> float | None:
            return None if deadline is None else max(0.0, deadline - time.monotonic())

        # 1. Submit aclose -- swallow any raise (ASYNC-090 bullet 3).
        aclose_fut: concurrent.futures.Future[Any] | None
        aclose_coro = self._async_backend.aclose()
        try:
            aclose_fut = asyncio.run_coroutine_threadsafe(aclose_coro, self._loop)
        except RuntimeError:
            # Loop already stopped (shouldn't happen with a fresh adapter).
            aclose_coro.close()
            aclose_fut = None

        if aclose_fut is not None:
            try:
                aclose_fut.result(timeout=_remaining())
            except concurrent.futures.TimeoutError:
                pass  # reported below via drain outcome
            except Exception:  # noqa: BLE001
                log.warning(
                    "AsyncBackendSyncAdapter: wrapped aclose() raised during shutdown",
                    exc_info=True,
                )

        # 2. Loop-drain: after _closed flips, a coroutine that passed _guard()
        # before the flip can still be submitted.  Re-run _drain_tasks until
        # the loop goes quiet or the deadline expires.
        drain_timed_out = False
        while True:
            rem = _remaining()
            if rem is not None and rem <= 0:
                drain_timed_out = True
                break
            # If the loop already has no pending tasks, we're done.
            if not _snapshot_tasks(self._loop):
                break
            drain_fut: concurrent.futures.Future[None] | None
            drain_coro = _drain_tasks()
            try:
                drain_fut = asyncio.run_coroutine_threadsafe(drain_coro, self._loop)
            except RuntimeError:
                drain_coro.close()
                break
            try:
                drain_fut.result(timeout=_remaining())
            except concurrent.futures.TimeoutError:
                drain_timed_out = True
                break
            except Exception:  # noqa: BLE001
                log.warning(
                    "AsyncBackendSyncAdapter: task drain raised during shutdown",
                    exc_info=True,
                )
                break

        # 3. Stop the loop.
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._loop.stop)

        # 4. Join the thread.
        self._thread.join(timeout=_remaining())

        if drain_timed_out or self._thread.is_alive():
            # _snapshot_tasks iterates asyncio.all_tasks() under a try/except
            # RuntimeError that covers "Set changed size during iteration" if
            # the loop thread is still running -- best-effort is acceptable.
            unfinished = _snapshot_tasks(self._loop)
            log.warning(
                "%s after %s seconds; %d unfinished task(s): %r",
                _CLOSE_TIMEOUT_MSG,
                timeout,
                len(unfinished),
                unfinished,
            )

    def __enter__(self) -> AsyncBackendSyncAdapter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Chunk-pull read stream (ASYNC-080, ASYNC-081)
# ---------------------------------------------------------------------------


class _ChunkPullReader(io.RawIOBase):
    """Forward-only sync stream pumping chunks out of an async generator.

    Subclasses :class:`io.RawIOBase` to inherit standard ``BinaryIO``
    semantics: ``closed`` property managed by :class:`io.IOBase`, ``flush()``,
    ``readline()``, and the context-manager protocol.

    Only forward reads are supported: ``seekable()`` returns ``False`` and no
    ``seek`` / ``tell`` / ``fileno`` are exposed (spec 029 § ASYNC-081,
    ADR-0025 § Bridged read streams).
    """

    def __init__(self, adapter: AsyncBackendSyncAdapter, async_iter: AsyncGenerator[bytes, None]) -> None:
        super().__init__()
        self._adapter = adapter
        self._iter = async_iter
        self._buf = b""
        self._eof = False
        self._closed_on_error = False

    # region: read surface

    def readinto(self, b: bytearray | memoryview) -> int | None:  # type: ignore[override]
        """Fill *b* with up to ``len(b)`` bytes; return the number written.

        At most one async chunk is pulled per call (or the already-buffered
        remainder is consumed), matching ``io.RawIOBase``'s documented
        "at most one underlying system call" contract.  Callers that need a
        full buffer should wrap this stream in ``io.BufferedReader``.
        """
        if self.closed:
            if not self._closed_on_error:
                raise ValueError("I/O operation on closed file.")
            return 0
        size = len(b)
        if size == 0:
            return 0
        # Serve from the pre-read buffer before issuing a new async pull.
        if not self._buf and not self._eof:
            chunk = self._pull_chunk()
            if chunk is not None:
                self._buf = chunk
        take = min(size, len(self._buf))
        b[:take] = self._buf[:take]
        self._buf = self._buf[take:]
        return take

    def read(self, size: int = -1) -> bytes:
        """Read and return up to *size* bytes, or all remaining if *size* == -1."""
        if self.closed:
            if not self._closed_on_error:
                raise ValueError("I/O operation on closed file.")
            return b""
        if size == 0:
            return b""
        if size is None or size < 0:
            chunks: list[bytes] = []
            if self._buf:
                chunks.append(self._buf)
                self._buf = b""
            while not self._eof:
                chunk = self._pull_chunk()
                if chunk is None:
                    break
                chunks.append(chunk)
            return b"".join(chunks)

        out = bytearray()
        while len(out) < size:
            if self._buf:
                take = min(size - len(out), len(self._buf))
                out.extend(self._buf[:take])
                self._buf = self._buf[take:]
                continue
            if self._eof:
                break
            chunk = self._pull_chunk()
            if chunk is None:
                break
            self._buf = chunk
        return bytes(out)

    def _pull_chunk(self) -> bytes | None:
        """Submit one ``__anext__`` to the adapter's loop and block.

        Returns the next chunk, or ``None`` at EOF.  Any exception from
        the async iterator propagates verbatim (ASYNC-087).
        """
        if self._eof:
            return None
        self._adapter._guard()
        coro = self._iter.__anext__()
        try:
            fut: concurrent.futures.Future[bytes] = asyncio.run_coroutine_threadsafe(coro, self._adapter._loop)
        except RuntimeError:
            # Loop stopped between _guard() and here (close() raced us).
            coro.close()
            self._eof = True
            self.close()
            raise RuntimeError(_CLOSED_MSG) from None
        try:
            chunk = fut.result()
        except StopAsyncIteration:
            self._eof = True
            return None
        except BaseException:
            # Closed-on-error state: aclose the iterator, then mark done.
            self._eof = True
            self._closed_on_error = True
            with contextlib.suppress(Exception):
                self.close()
            raise
        return chunk

    # endregion

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        """Close the stream and release the underlying async iterator.

        Submits ``aclose()`` on the async generator so that backend
        ``finally`` blocks run even when the caller abandons the stream
        early.  Idempotent.  Best-effort: if the adapter's private loop has
        already stopped, the ``aclose()`` submission is silently skipped.

        Returns:
            ``None``

        Example:
            ```python
            stream = adapter.read("data.bin")
            stream.read(16)
            stream.close()  # releases backend resources
            ```
        """
        if self.closed:
            return
        coro = self._iter.aclose()
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._adapter._loop)
        except RuntimeError:
            # Loop already stopped (adapter closed concurrently) -- best effort.
            coro.close()
        else:
            try:
                fut.result()
            except Exception:  # noqa: BLE001
                log.debug("AsyncBackendSyncAdapter: stream aclose raised", exc_info=True)
        super().close()  # sets self.closed = True via io.IOBase


# ---------------------------------------------------------------------------
# Async-iterator → sync-iterator bridge (ASYNC-080)
# ---------------------------------------------------------------------------


class _AsyncIteratorBridge:
    """Sync :class:`Iterator` pulling one item per ``__anext__`` call.

    Used for ``list_files``, ``list_folders``, ``glob``, and
    ``iter_children`` (spec 029 § ASYNC-080).  Preserves streaming --
    the full listing is never materialised in memory.

    A best-effort ``__del__`` submits ``aclose()`` fire-and-forget when the
    iterator is GC'd before exhaustion, so backend resources are not silently
    leaked when callers break out of a ``for`` loop early.

    Note:
        The ``__del__`` clean-up is only effective when the wrapped
        ``_iter`` is an *async generator* (i.e. exposes ``aclose()``).
        Plain ``AsyncIterator`` objects built from a class with only
        ``__aiter__``/``__anext__`` have no ``aclose``; the
        :func:`contextlib.suppress` in ``__del__`` swallows the resulting
        ``AttributeError`` silently.  All async backends in this package
        use async generators for listing, so the guarantee holds in
        practice.
    """

    __slots__ = ("_adapter", "_iter", "_done")

    def __init__(self, adapter: AsyncBackendSyncAdapter, async_iter: AsyncIterator[Any]) -> None:
        self._adapter = adapter
        self._iter = async_iter
        self._done = False

    def __iter__(self) -> _AsyncIteratorBridge:
        return self

    def __next__(self) -> Any:
        if self._done:
            raise StopIteration
        self._adapter._guard()
        coro: Any = self._iter.__anext__()
        try:
            fut: concurrent.futures.Future[Any] = asyncio.run_coroutine_threadsafe(coro, self._adapter._loop)
        except RuntimeError:
            # Loop stopped between _guard() and here (close() raced us).
            coro.close()
            self._done = True
            raise RuntimeError(_CLOSED_MSG) from None
        try:
            return fut.result()
        except StopAsyncIteration:
            self._done = True
            raise StopIteration from None
        except BaseException:
            self._done = True
            raise

    def _aclose_best_effort(self) -> None:
        """Submit a fire-and-forget ``aclose()`` to the adapter's event loop.

        Returns immediately; the coroutine is not awaited.  Safe to call from
        any thread, including the GC thread.  Uses ``getattr`` guards to stay
        safe if ``__init__`` did not complete or the adapter is being collected
        concurrently.
        """
        if getattr(self, "_done", True):
            return
        loop = getattr(getattr(self, "_adapter", None), "_loop", None)
        if loop is None or not loop.is_running():
            return
        coro = None
        try:
            coro = self._iter.aclose()  # type: ignore[attr-defined]
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:  # noqa: BLE001
            if coro is not None:
                with contextlib.suppress(Exception):
                    coro.close()

    def __del__(self) -> None:
        """Best-effort cleanup when GC'd before exhaustion."""
        self._aclose_best_effort()


# ---------------------------------------------------------------------------
# Byte-counting BinaryIO wrapper (write path size tracking)
# ---------------------------------------------------------------------------


class _CountingBinaryIO:
    """Wraps a BinaryIO and counts bytes read — used to populate WriteResult.size."""

    __slots__ = ("_stream", "count")

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream
        self.count: int = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        self.count += len(chunk)
        return chunk


# ---------------------------------------------------------------------------
# Sync ``BinaryIO`` → ``AsyncIterator[bytes]`` bridge (write path)
# ---------------------------------------------------------------------------


async def _binaryio_to_async_iter(stream: BinaryIO) -> AsyncIterator[bytes]:
    """Pump chunks out of a blocking ``BinaryIO`` via ``asyncio.to_thread``.

    Single-chunk in-flight: at most one pending ``to_thread`` at a time,
    no parallel pre-read.  The caller's blocking file object never
    stalls the adapter's private event loop.
    """
    while True:
        chunk = await asyncio.to_thread(stream.read, _WRITE_CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


# ---------------------------------------------------------------------------
# ``open_atomic`` context manager (ASYNC-085)
# ---------------------------------------------------------------------------


class _SpoolAndFlush:
    """``open_atomic`` synthesis over :class:`tempfile.SpooledTemporaryFile`.

    Clean exit rewinds the spool and submits it to the wrapped backend's
    ``write_atomic``.  On exception, the spool is dropped and the
    destination path is untouched -- the capability gate fires on
    flush, not on entry (spec 029 § ASYNC-085).
    """

    __slots__ = ("_adapter", "_path", "_overwrite", "_spool")

    def __init__(self, adapter: AsyncBackendSyncAdapter, path: str, *, overwrite: bool) -> None:
        self._adapter = adapter
        self._path = path
        self._overwrite = overwrite
        self._spool: tempfile.SpooledTemporaryFile[bytes] | None = None

    def __enter__(self) -> BinaryIO:
        self._spool = tempfile.SpooledTemporaryFile(max_size=_OPEN_ATOMIC_SPOOL_MAX)
        return self._spool  # type: ignore[return-value]

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        spool = self._spool
        self._spool = None
        if spool is None:
            return
        try:
            if exc_type is not None:
                return
            spool.seek(0)
            self._adapter.write_atomic(self._path, spool, overwrite=self._overwrite)  # type: ignore[arg-type]
        finally:
            with contextlib.suppress(Exception):
                spool.close()


# ---------------------------------------------------------------------------
# Loop helpers
# ---------------------------------------------------------------------------


async def _drain_tasks() -> None:
    """Wait for every task on the current loop except the caller itself."""
    current = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _snapshot_tasks(loop: asyncio.AbstractEventLoop) -> list[str]:
    """Return ``repr()`` strings for any tasks still outstanding on *loop*."""
    try:
        tasks = asyncio.all_tasks(loop)
    except RuntimeError:
        return []
    return [repr(t) for t in tasks if not t.done()]


__all__ = ["AsyncBackendSyncAdapter"]
