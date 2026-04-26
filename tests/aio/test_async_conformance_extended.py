"""Extended conformance tests for the async backend contract.

Mirrors ``tests/backends/test_conformance_extended.py`` for the async side.
The fixture ``async_backend`` is parametrized across all backends that have
explicit directory entries:

* ``AsyncMemoryBackend`` — native async implementation with ``_DirNode`` objects.
* ``SyncBackendAdapter(MemoryBackend())`` — adapter wrapping the sync reference.
* ``SyncBackendAdapter(LocalBackend())`` — adapter over a real filesystem.

Flat-namespace backends (S3, Azure Blob, HTTP, SQL-blob) have no real directory
entries and are excluded from error-fidelity tests.

Spec coverage: ASYNC-012 (delete contract — directory-path case).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath
from remote_store.aio import AsyncMemoryBackend, SyncBackendAdapter
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from pathlib import Path

    from remote_store.aio._async_backend import AsyncBackend


@pytest.fixture(
    params=[
        "native-memory",
        "adapted-memory",
        pytest.param("adapted-local", marks=pytest.mark.os_sensitive),
    ],
    ids=["native-memory", "adapted-memory", "adapted-local"],
)
def async_backend(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncBackend:
    """Async backend parametrized over native and adapted hierarchical implementations."""
    if request.param == "native-memory":
        return AsyncMemoryBackend()
    if request.param == "adapted-memory":
        return SyncBackendAdapter(MemoryBackend())
    return SyncBackendAdapter(LocalBackend(root=str(tmp_path)))


# ---------------------------------------------------------------------------
# Delete error fidelity — directory-path type check (ASYNC-012 / BE-012)
# ---------------------------------------------------------------------------


@pytest.mark.spec("ASYNC-012")
class TestDeleteErrorFidelity:
    """``delete(dir_path)`` raises ``InvalidPath`` regardless of ``missing_ok``.

    Mirrors ``test_conformance_extended.py::TestDeleteErrorFidelity``.
    The ``missing_ok`` flag tolerates a *missing file*, not a type mismatch —
    a directory path must raise ``InvalidPath`` unconditionally (BE-012,
    Dafny: ``Delete: IsDir → InvalidPath`` unconditionally).
    """

    async def test_delete_on_directory_raises_invalid_path(self, async_backend: AsyncBackend) -> None:
        await async_backend.write("ddir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir"):
            await async_backend.delete("ddir")

    async def test_delete_on_directory_missing_ok_still_raises(self, async_backend: AsyncBackend) -> None:
        await async_backend.write("ddir2/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir2"):
            await async_backend.delete("ddir2", missing_ok=True)
        assert await async_backend.exists("ddir2/file.txt"), "child silently deleted"
