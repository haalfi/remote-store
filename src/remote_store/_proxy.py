"""ProxyStore — shared base for Store proxy subclasses.

Centralizes delegation boilerplate, private-attribute coupling, and
``child()`` propagation for proxy wrappers like ``ObservedStore`` and
``CachedStore``.  Subclass ``ProxyStore`` to build custom Store
middleware — override only the methods you want to intercept.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._store import Store

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._capabilities import Capability
    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")


class ProxyStore(Store):
    """Base class for Store proxies that delegate to an inner Store.

    All public ``Store`` methods delegate to ``self._inner`` by default.
    Subclasses override only the methods they intercept and must implement
    ``_wrap_child()`` to control how ``child()`` propagates wrapper behavior.

    ``ObservedStore`` and ``CachedStore`` are built on this base.
    Subclass it to build your own Store middleware.

    Args:
        inner: The Store instance to wrap.

    Example:
        ```python
        from remote_store import ProxyStore, Store

        class LoggingStore(ProxyStore):
            def read_bytes(self, path: str) -> bytes:
                print(f"Reading {path}")
                return self.inner.read_bytes(path)

            def _wrap_child(self, inner_child: Store) -> "LoggingStore":
                return LoggingStore(inner_child)
        ```
    """

    _inner: Store

    def __init__(self, inner: Store) -> None:
        super().__init__(inner._backend, inner._root)
        # Proxy does not own the backend — closing the proxy must not close it.
        self._owns_backend = False
        self._inner = inner

    @property
    def inner(self) -> Store:
        """The wrapped Store instance."""
        return self._inner

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._inner == other._inner
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._inner)

    # ------------------------------------------------------------------
    # child() propagation
    # ------------------------------------------------------------------

    def child(self, subpath: str) -> Store:
        """Return a child store wrapped with the same proxy behavior.

        Delegates to ``_wrap_child()`` which subclasses must implement.
        """
        inner_child = self._inner.child(subpath)
        return self._wrap_child(inner_child)

    def _wrap_child(self, inner_child: Store) -> Store:
        """Wrap an inner child store in a new proxy with the same config.

        Subclasses must override this to construct an appropriate wrapper.

        Raises:
            NotImplementedError: Always — subclasses must provide an
                implementation.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Default delegation — all public Store methods
    # ------------------------------------------------------------------

    # region: reading

    def read(self, path: str) -> BinaryIO:
        return self._inner.read(path)

    def read_bytes(self, path: str) -> bytes:
        return self._inner.read_bytes(path)

    def read_seekable(self, path: str) -> BinaryIO:
        return self._inner.read_seekable(path)

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        return self._inner.read_text(path, encoding=encoding, errors=errors)

    # endregion

    # region: writing

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return self._inner.write(path, content, overwrite=overwrite, metadata=metadata)

    def write_text(
        self,
        path: str,
        text: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return self._inner.write_text(path, text, encoding=encoding, overwrite=overwrite, metadata=metadata)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return self._inner.write_atomic(path, content, overwrite=overwrite, metadata=metadata)

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        with self._inner.open_atomic(path, overwrite=overwrite) as f:
            yield f

    # endregion

    # region: deleting

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._inner.delete(path, missing_ok=missing_ok)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._inner.delete_folder(path, recursive=recursive, missing_ok=missing_ok)

    # endregion

    # region: listing and iteration

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        pattern: str | None = None,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        return self._inner.list_files(path, recursive=recursive, pattern=pattern, max_depth=max_depth)

    def list_folders(
        self, path: str, *, pattern: str | None = None, max_depth: int | None = None
    ) -> Iterator[FolderEntry]:
        return self._inner.list_folders(path, pattern=pattern, max_depth=max_depth)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        return self._inner.iter_children(path)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        return self._inner.glob(pattern)

    # endregion

    # region: file operations

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.move(src, dst, overwrite=overwrite)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._inner.copy(src, dst, overwrite=overwrite)

    # endregion

    # region: metadata

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)

    def is_file(self, path: str) -> bool:
        return self._inner.is_file(path)

    def is_folder(self, path: str) -> bool:
        return self._inner.is_folder(path)

    def get_file_info(self, path: str) -> FileInfo:
        return self._inner.get_file_info(path)

    def get_folder_info(self, path: str, *, max_depth: int | None = None) -> FolderInfo:
        return self._inner.get_folder_info(path, max_depth=max_depth)

    def head(self, path: str) -> WriteResult:
        return self._inner.head(path)

    # endregion

    # region: lifecycle

    def ping(self) -> None:
        self._inner.ping()

    def close(self) -> None:
        self._inner.close()

    # endregion

    # region: interop

    def unwrap(self, type_hint: type[T]) -> T:
        return self._inner.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        return self._inner.native_path(key)

    def resolve(self, key: str) -> ResolutionPlan:
        return self._inner.resolve(key)

    def to_key(self, path: str) -> str:
        return self._inner.to_key(path)

    def supports(self, capability: Capability) -> bool:
        return self._inner.supports(capability)

    # endregion
