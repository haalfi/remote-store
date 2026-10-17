"""The async contract kernel: the shared core plus the async ``read``.

``AsyncDriverBackend`` is ``AsyncBackend`` over an ``AsyncDriver``. The only
member whose shape is the runtime's own is ``read``, an async iterator of
chunks; everything else is ``_async.kernel._AsyncKernelCore``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._kernel._async import _io
from remote_store._kernel._async.kernel import _AsyncKernelCore
from remote_store._kernel._model import Op
from remote_store.aio._async_backend import AsyncBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class AsyncDriverBackend(_AsyncKernelCore, AsyncBackend):
    """``AsyncBackend`` implemented once, over an async driver.

    Construct it with a built driver, usually from the ``__init__`` of a
    subclass that builds its own.

    Args:
        driver: The built driver.

    Raises:
        ValueError: If the driver's declarations are not backed by its
            protocols, it is flat and has folder objects, it has explicit
            parents and no ``ensure_parents``, it has folder objects and no
            ``remove_folder``, the class's own ``close_is_terminal``
            differs from the driver's, or a primitive is missing or, other
            than ``probe``, is the protocol's own body.
    """

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Chunks of the file at *path*, mapped as the sync stream maps its reads.

        The caught set is the sync ``_ErrorMappingStream``'s, ``OSError``,
        ``EOFError`` and the driver's ``stream_catch``, so a stream error is
        typed alike in both runtimes; outside it an exception propagates, as
        it does there. A caught error the driver's ``connection_dead``
        condemns skips the stream's close, as the sync stream's ``is_fatal``
        does, so no second wait falls on a dead connection.
        """
        key, stream = await self._open(path, Op.READ)
        caught = (OSError, EOFError, *tuple(getattr(self._driver, "stream_catch", ())))
        chunks = stream.__aiter__()
        condemned = False
        try:
            while True:
                try:
                    chunk = await chunks.__anext__()
                except StopAsyncIteration:
                    return
                except caught as exc:
                    # Unguarded, as the sync stream calls is_fatal: a predicate that
                    # raises is a driver bug, and its error propagates.
                    condemned = bool(self._driver.connection_dead(exc))
                    raise self._mapped(exc, Op.READ, key) from exc
                yield chunk
        finally:
            if not condemned:
                await _io.close_stream(stream)
