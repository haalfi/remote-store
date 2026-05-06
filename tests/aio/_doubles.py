"""Async backend test doubles for ``AsyncBackendSyncAdapter`` coverage.

These doubles exist so the adapter's failure paths — timeouts,
cancellation, verbatim error propagation, mid-stream iterator failure —
are reachable without patching third-party internals
(``sdd/TESTING.md`` Rule 6). The authoritative invariants they help
exercise live in spec 029 § AsyncBackendSyncAdapter.

- ``_HangingAsyncBackend`` never returns from any I/O method.
  Every coroutine awaits an ``asyncio.Event`` that never gets set,
  so the adapter's drain / close / cancellation paths can be exercised
  deterministically.
- ``_RaisingAsyncBackend`` raises a preconfigured exception from
  every I/O method (and optionally from ``aclose``), for driving
  verbatim error propagation and mid-stream failure tests.

Both classes are concrete ``AsyncBackend`` subclasses so they can
be passed to ``AsyncBackendSyncAdapter`` unchanged once it lands
(see ADR-0025). Intended for unit-test use only.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import NotFound
from remote_store.aio._async_backend import AsyncBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store.aio._types import AsyncWritableContent

# Default capability set for the doubles: every real ``Capability``
# enum member, so the adapter's translation table (spec 029
# § ASYNC-084) can be exercised in full. ``SEEKABLE_READ`` is
# deliberately included even though the adapter masks it off — that
# masking is precisely what ASYNC-084 tests assert. Individual tests
# may pass a narrower set via the constructor.
_ALL_ADAPTER_CAPABILITIES = CapabilitySet(
    {
        Capability.READ,
        Capability.WRITE,
        Capability.DELETE,
        Capability.LIST,
        Capability.GLOB,
        Capability.MOVE,
        Capability.COPY,
        Capability.ATOMIC_WRITE,
        Capability.ATOMIC_MOVE,
        Capability.METADATA,
        Capability.SEEKABLE_READ,
        Capability.LAZY_READ,
    }
)


class _HangingAsyncBackend(AsyncBackend):
    """AsyncBackend whose I/O methods block indefinitely on first await.

    Primary use cases are the adapter's bounded-join / hung-iterator /
    cancellation paths in spec 029 § AsyncBackendSyncAdapter — tests
    that need to observe the adapter's behaviour while the wrapped
    backend never makes progress.

    Note on async generators: :meth:`read`, :meth:`list_files`, and
    :meth:`list_folders` are declared ``async def ... -> AsyncIterator``
    with a reachable ``yield`` inside a guarded branch, so calling them
    returns an async generator synchronously; the hang fires on the
    first ``__anext__``, not at call site.

    The hang is implemented with an :class:`asyncio.Event` that is
    never set. Tests that need the hang to release deliberately call
    :meth:`release`.

    ``asyncio.Event`` is not thread-safe, and the event lazily binds to
    the loop that first awaits it — which for
    ``AsyncBackendSyncAdapter`` coverage is the adapter's private loop
    on its background thread. To allow cross-thread release, tests call
    :meth:`bind_loop` with the adapter's private loop before calling
    :meth:`release`; :meth:`release` then uses
    ``loop.call_soon_threadsafe`` to set the event on the owning loop.
    When no loop has been bound (single-threaded tests running the
    double directly), :meth:`release` falls back to ``event.set()``.

    Precondition for :meth:`release`: at least one coroutine must have
    begun awaiting the event (e.g. the hang-method has been scheduled
    onto the bound loop and reached ``self._get_event().wait()``).
    Calling :meth:`release` before any coroutine awaits is a no-op and
    will not wake a subsequently scheduled coroutine.
    """

    def __init__(
        self,
        *,
        capabilities: CapabilitySet | None = None,
        name: str = "hanging-async",
    ) -> None:
        self._name = name
        self._capabilities = capabilities if capabilities is not None else _ALL_ADAPTER_CAPABILITIES
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.aclose_called = False

    def _get_event(self) -> asyncio.Event:
        # Lazily created because the event must bind to the loop that
        # eventually awaits it, which is the adapter's private loop.
        if self._event is None:
            self._event = asyncio.Event()
        return self._event

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the loop the event is bound to for thread-safe release.

        Test helper called from the adapter-owning thread once the
        adapter's private loop is available (e.g. immediately after
        adapter construction in fixtures).
        """
        self._loop = loop

    def release(self) -> None:
        """Unblock every suspended coroutine (test-only helper).

        Thread-safe when :meth:`bind_loop` has been called with the
        loop that owns the event; otherwise falls back to a direct
        ``event.set()`` for same-thread tests.
        """
        event = self._event
        if event is None:
            return
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(event.set)
        else:
            event.set()

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> CapabilitySet:
        return self._capabilities

    async def _hang(self) -> None:
        await self._get_event().wait()

    async def exists(self, path: str) -> bool:
        await self._hang()
        return False  # pragma: no cover -- unreachable unless released

    async def is_file(self, path: str) -> bool:
        await self._hang()
        return False  # pragma: no cover

    async def is_folder(self, path: str) -> bool:
        await self._hang()
        return False  # pragma: no cover

    async def read(self, path: str) -> AsyncIterator[bytes]:
        await self._hang()
        if False:  # pragma: no cover
            yield b""

    async def read_bytes(self, path: str) -> bytes:
        await self._hang()
        return b""  # pragma: no cover

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        await self._hang()
        raise AssertionError("unreachable")  # pragma: no cover

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        await self._hang()
        raise AssertionError("unreachable")  # pragma: no cover

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        await self._hang()

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        await self._hang()

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        await self._hang()
        if False:  # pragma: no cover
            yield

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        await self._hang()
        if False:  # pragma: no cover
            yield

    async def get_file_info(self, path: str) -> FileInfo:
        await self._hang()
        raise AssertionError("unreachable")  # pragma: no cover

    async def get_folder_info(self, path: str) -> FolderInfo:
        await self._hang()
        raise AssertionError("unreachable")  # pragma: no cover

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        await self._hang()

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        await self._hang()

    async def check_health(self) -> None:
        await self._hang()

    async def aclose(self) -> None:
        self.aclose_called = True
        await self._hang()


class _RaisingAsyncBackend(AsyncBackend):
    """AsyncBackend that raises a preconfigured error from every I/O method.

    Primary use cases are the adapter's verbatim-error-propagation and
    mid-stream-failure paths in spec 029 § AsyncBackendSyncAdapter —
    tests that need to drive a specific exception through the adapter's
    ``Future``-based bridge.

    The default error is :class:`NotFound` (a realistic mapped error);
    tests that need a different type pass ``error=`` at construction.
    If ``aclose_error`` is provided, ``aclose()`` raises it (for
    shutdown-drain coverage); otherwise ``aclose()`` is a no-op.

    ``read_chunks_before_raise`` controls only the byte-stream iterator
    returned from :meth:`read`: with a positive value, :meth:`read`
    yields N dummy chunks before raising, which drives mid-stream
    byte-stream failure tests. The listing iterators (``list_files`` /
    ``list_folders``) always raise on first pull — they cannot yield
    ``FileInfo`` / ``FolderEntry`` without extra plumbing, and
    mid-stream listing failure tests should subclass this double.
    """

    def __init__(
        self,
        *,
        error: BaseException | None = None,
        aclose_error: BaseException | None = None,
        read_chunks_before_raise: int = 0,
        capabilities: CapabilitySet | None = None,
        name: str = "raising-async",
    ) -> None:
        self._name = name
        self._capabilities = capabilities if capabilities is not None else _ALL_ADAPTER_CAPABILITIES
        self._error: BaseException = error if error is not None else NotFound("missing", path="/")
        self._aclose_error = aclose_error
        self._read_chunks_before_raise = read_chunks_before_raise
        self.aclose_called = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> CapabilitySet:
        return self._capabilities

    def _raise(self) -> None:
        raise self._error

    async def exists(self, path: str) -> bool:
        self._raise()
        return False  # pragma: no cover

    async def is_file(self, path: str) -> bool:
        self._raise()
        return False  # pragma: no cover

    async def is_folder(self, path: str) -> bool:
        self._raise()
        return False  # pragma: no cover

    async def read(self, path: str) -> AsyncIterator[bytes]:
        # Yield N dummy chunks before raising so tests can drive
        # mid-stream failures (ASYNC-090) without a second double.
        for _ in range(self._read_chunks_before_raise):
            yield b"x"
        self._raise()

    async def read_bytes(self, path: str) -> bytes:
        self._raise()
        return b""  # pragma: no cover

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        self._raise()
        raise AssertionError("unreachable")  # pragma: no cover

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        self._raise()
        raise AssertionError("unreachable")  # pragma: no cover

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._raise()

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._raise()

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        # Raises on first pull unconditionally: we cannot yield
        # FileInfo here without plumbing. Tests that need a
        # mid-stream listing failure should subclass this double.
        self._raise()
        if False:  # pragma: no cover
            yield

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        self._raise()
        if False:  # pragma: no cover
            yield

    async def get_file_info(self, path: str) -> FileInfo:
        self._raise()
        raise AssertionError("unreachable")  # pragma: no cover

    async def get_folder_info(self, path: str) -> FolderInfo:
        self._raise()
        raise AssertionError("unreachable")  # pragma: no cover

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._raise()

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._raise()

    async def check_health(self) -> None:
        self._raise()

    async def aclose(self) -> None:
        self.aclose_called = True
        if self._aclose_error is not None:
            raise self._aclose_error


__all__ = ["_HangingAsyncBackend", "_RaisingAsyncBackend"]
