"""BE-033 on every async class on the kernel: a write the kernel stops leaves no caller iterator suspended.

The fake-driver cells in ``tests/_kernel/test_protocol.py`` cover every exit; this
cell holds each conformance fixture on the kernel to the same rule through the
public ``write``, so a real driver cannot opt out of it. Another class is skipped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._kernel.aio_backend import AsyncDriverBackend
from tests.backends.conformance._helpers import _require

if TYPE_CHECKING:
    from remote_store.aio._async_backend import AsyncBackend


class _Chunks:
    """A caller's async content iterator whose second chunk is not bytes, recording ``aclose``."""

    def __init__(self) -> None:
        self._chunks: list[object] = [b"ab", "text", b"cd"]
        self.closed = False

    def __aiter__(self) -> _Chunks:
        return self

    async def __anext__(self) -> object:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.spec("BE-033")
async def test_a_refused_chunk_leaves_the_caller_iterator_closed(async_backend: AsyncBackend) -> None:
    if not isinstance(async_backend, AsyncDriverBackend):
        pytest.skip("BE-033 binds classes on the kernel")
    _require(async_backend, Capability.WRITE)
    content = _Chunks()
    with pytest.raises(TypeError, match="str, not bytes"):
        await async_backend.write("be033-refused-chunk.bin", content)  # type: ignore[arg-type]
    assert content.closed
    assert content._chunks == [b"cd"]  # the kernel stopped at the refused chunk
