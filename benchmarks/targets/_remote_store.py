"""BenchTarget adapter wrapping a remote-store Backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from benchmarks.targets._protocol import BenchTarget

if TYPE_CHECKING:
    from remote_store._backend import Backend


class RemoteStoreTarget(BenchTarget):
    """Thin adapter: remote-store Backend -> BenchTarget."""

    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    @property
    def label(self) -> str:
        return "remote_store"

    def write(self, path: str, data: bytes) -> None:
        self._backend.write(path, data)

    def read(self, path: str) -> bytes:
        return self._backend.read_bytes(path)

    def exists(self, path: str) -> bool:
        return self._backend.exists(path)

    def delete(self, path: str) -> None:
        self._backend.delete(path)

    def list_files(self, prefix: str) -> list[str]:
        return list(self._backend.list_files(prefix))

    def close(self) -> None:
        self._backend.close()
