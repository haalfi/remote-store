"""Async backend test doubles for ``AsyncBackendSyncAdapter`` coverage.

These doubles are deliberately narrow: they exist so the failure paths in
spec block ASYNC-080 … ASYNC-093 — especially timeouts, cancellation, and
verbatim error propagation — are reachable without patching third-party
internals (``sdd/TESTING.md`` Rule 6).

- :class:`_HangingAsyncBackend` never returns from any I/O method. Every
  coroutine awaits an :class:`asyncio.Event` that never gets set, so the
  adapter's drain / close / cancellation paths can be exercised
  deterministically.
- :class:`_RaisingAsyncBackend` raises a preconfigured exception from every
  I/O method (and optionally from ``aclose``). Useful for driving
  verbatim error propagation and mid-stream failure tests.

Both classes are concrete :class:`AsyncBackend` subclasses so they can be
passed to :class:`AsyncBackendSyncAdapter` unchanged once it lands
(see ADR-0025). They are intended for unit-test use only and deliberately
declare no capabilities beyond what the individual tests need.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import NotFound
from remote_store.aio._async_backend import AsyncBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remote_store._models import FileInfo, FolderEntry, FolderInfo
    from remote_store.aio._types import AsyncWritableContent

T = TypeVar("T")

# Default capability set for the doubles: everything needed to exercise the
# adapter's translation table (ASYNC-084). Individual tests may pass a
# narrower set via the constructor.
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
    """AsyncBackend whose every I/O coroutine blocks forever.

    Used to exercise:

    - ASYNC-088: ``close(timeout=...)`` bounded-join warning path.
    - ASYNC-090: hung-iterator shutdown path.
    - Cancellation surfacing via ``Future.cancel()`` /
      ``asyncio.Task.cancel()``.

    The hang is implemented with an ``asyncio.Event`` that is never set.
    Tests that need the hang to release deliberately may call
    :meth:`release` to unblock every suspended coroutine.
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
        self._aclose_called = False

    def _get_event(self) -> asyncio.Event:
        # Lazily created because the event must bind to the loop that
        # eventually awaits it, which is the adapter's private loop.
        if self._event is None:
            self._event = asyncio.Event()
        return self._event

    def release(self) -> None:
        """Unblock every suspended coroutine (test-only helper)."""
        event = self._event
        if event is not None:
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

    async def write(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        await self._hang()

    async def write_atomic(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        await self._hang()

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
        self._aclose_called = True
        await self._hang()


class _RaisingAsyncBackend(AsyncBackend):
    """AsyncBackend whose every I/O coroutine raises a preconfigured error.

    Used to exercise:

    - ASYNC-087: verbatim error propagation (type, attributes, traceback).
    - ASYNC-090: mid-stream ``__anext__`` raise.
    - ASYNC-091: ``BinaryIO`` mid-write surfacing.
    - ASYNC-093: ``check_health()`` connectivity-error passthrough.

    The default error is :class:`NotFound` (a realistic mapped error);
    tests that need a different type pass ``error=`` at construction.
    If ``aclose_error`` is provided, ``aclose()`` raises it (for
    ASYNC-088 / ASYNC-090 shutdown-drain coverage); otherwise ``aclose()``
    is a no-op.
    """

    def __init__(
        self,
        *,
        error: BaseException | None = None,
        aclose_error: BaseException | None = None,
        stream_chunks_before_raise: int = 0,
        capabilities: CapabilitySet | None = None,
        name: str = "raising-async",
    ) -> None:
        self._name = name
        self._capabilities = capabilities if capabilities is not None else _ALL_ADAPTER_CAPABILITIES
        self._error: BaseException = error if error is not None else NotFound("missing", path="/")
        self._aclose_error = aclose_error
        self._stream_chunks_before_raise = stream_chunks_before_raise
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
        for _ in range(self._stream_chunks_before_raise):
            yield b"x"
        self._raise()

    async def read_bytes(self, path: str) -> bytes:
        self._raise()
        return b""  # pragma: no cover

    async def write(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        self._raise()

    async def write_atomic(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        self._raise()

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
        for _ in range(self._stream_chunks_before_raise):
            # No FileInfo available here without extra plumbing; tests
            # driving the list-iterator mid-stream case should provide a
            # custom subclass. The raise-on-first-pull path is the
            # dominant use case.
            raise AssertionError("list_files pre-raise yields unsupported; use 0")  # pragma: no cover
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
