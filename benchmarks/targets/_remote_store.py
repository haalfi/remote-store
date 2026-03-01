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
        self._backend.write(path, data, overwrite=True)

    def read(self, path: str) -> bytes:
        return self._backend.read_bytes(path)

    def exists(self, path: str) -> bool:
        return self._backend.exists(path)

    def delete(self, path: str) -> None:
        self._backend.delete(path)

    def list_files(self, prefix: str) -> list[str]:
        return [fi.path for fi in self._backend.list_files(prefix)]

    def invalidate_cache(self) -> None:
        fs = getattr(self._backend, "_fs", None)
        if fs is not None and hasattr(fs, "invalidate_cache"):
            fs.invalidate_cache()

    def close(self) -> None:
        self._backend.close()
