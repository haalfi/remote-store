"""Store — the primary user-facing abstraction."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, BinaryIO

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

    from remote_store._backend import Backend
    from remote_store._models import FileInfo, FolderInfo
    from remote_store._types import WritableContent


class Store:
    """A logical remote folder scoped to a root path.

    All path arguments are validated and prefixed with ``root_path``
    before being delegated to the backend.

    :param backend: The backend to delegate I/O to.
    :param root_path: Path prefix for all operations (may be empty).
    """

    def __init__(self, backend: Backend, root_path: str = "") -> None:
        self._backend = backend
        self._root = str(RemotePath(root_path)) if root_path else ""

    def __repr__(self) -> str:
        return f"Store(backend={self._backend.name!r}, root_path={self._root!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Store):
            return self._backend is other._backend and self._root == other._root
        return NotImplemented

    def __hash__(self) -> int:
        return hash((id(self._backend), self._root))

    def close(self) -> None:
        """Close the underlying backend, releasing any held resources."""
        self._backend.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _full_path(self, path: str) -> str:
        """Resolve a path that may be empty (store root) or a relative subpath."""
        if not path:
            if self._root:
                return self._root
            return ""
        validated = RemotePath(path)
        if self._root:
            return f"{self._root}/{validated}"
        return str(validated)

    def _require_file_path(self, path: str) -> str:
        """Resolve a path that must be non-empty (file-targeted operations)."""
        if not path:
            raise InvalidPath("Path must not be empty for file operations", path=path)
        return self._full_path(path)

    def _strip_root(self, backend_rel: str) -> str:
        """Strip ``root_path`` prefix from a backend-relative path.

        :returns: Store-relative key.
        :raises InvalidPath: If the path does not start with ``root_path``.
        """
        if not self._root:
            return backend_rel
        if backend_rel == self._root:
            return ""
        prefix = self._root + "/"
        if backend_rel.startswith(prefix):
            return backend_rel[len(prefix) :]
        raise InvalidPath(
            f"Path {backend_rel!r} is not under store root {self._root!r}",
            path=backend_rel,
        )

    def _rebase_file_info(self, info: FileInfo) -> FileInfo:
        """Return a copy of *info* with its path rebased to store-relative."""
        rel = self._strip_root(str(info.path))
        if rel == str(info.path):
            return info
        return dataclasses.replace(info, path=RemotePath(rel))

    def _rebase_folder_info(self, info: FolderInfo) -> FolderInfo:
        """Return a copy of *info* with its path rebased to store-relative."""
        rel = self._strip_root(str(info.path))
        if rel == str(info.path):
            return info
        return dataclasses.replace(info, path=RemotePath(rel))

    def to_key(self, path: str) -> str:
        """Convert an absolute or backend-native path to a store-relative key.

        Composes ``backend.to_key()`` (strips the backend's native root) with
        store-root stripping (removes ``root_path`` prefix).

        :param path: Absolute, backend-native, or backend-relative path.
        :returns: Key relative to this store's ``root_path``.
        :raises InvalidPath: If the path does not belong to this store.
        """
        backend_rel = self._backend.to_key(path)
        return self._strip_root(backend_rel)

    def supports(self, capability: Capability) -> bool:
        """Check whether the backend supports a capability."""
        return self._backend.capabilities.supports(capability)

    def exists(self, path: str) -> bool:
        """Check if a file or folder exists."""
        return self._backend.exists(self._full_path(path))

    def is_file(self, path: str) -> bool:
        """Check if path is an existing file."""
        return self._backend.is_file(self._full_path(path))

    def is_folder(self, path: str) -> bool:
        """Check if path is an existing folder."""
        return self._backend.is_folder(self._full_path(path))

    def read(self, path: str) -> BinaryIO:
        """Open a file for reading.

        :raises NotFound: If the file does not exist.
        """
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read(self._require_file_path(path))

    def read_bytes(self, path: str) -> bytes:
        """Read full file content as bytes.

        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.
        """
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_bytes(self._require_file_path(path))

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        self._backend.capabilities.require(Capability.WRITE, backend=self._backend.name)
        self._backend.write(self._require_file_path(path), content, overwrite=overwrite)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically.

        :raises CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        self._backend.capabilities.require(Capability.ATOMIC_WRITE, backend=self._backend.name)
        self._backend.write_atomic(self._require_file_path(path), content, overwrite=overwrite)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        :raises NotFound: If the file is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        self._backend.capabilities.require(Capability.DELETE, backend=self._backend.name)
        self._backend.delete(self._require_file_path(path), missing_ok=missing_ok)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        :raises NotFound: If the folder is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty (cannot delete the store root).
        """
        if not path:
            raise InvalidPath("Cannot delete the store root", path=path)
        self._backend.capabilities.require(Capability.DELETE, backend=self._backend.name)
        self._backend.delete_folder(self._full_path(path), recursive=recursive, missing_ok=missing_ok)

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        """List files under path.

        Returned ``FileInfo.path`` values are store-relative keys (``root_path``
        is stripped), so they can be fed directly back into other Store methods.

        :param recursive: Include files in all subdirectories.
        """
        self._backend.capabilities.require(Capability.LIST, backend=self._backend.name)
        for info in self._backend.list_files(self._full_path(path), recursive=recursive):
            yield self._rebase_file_info(info)

    def list_folders(self, path: str) -> Iterator[str]:
        """List immediate subfolder names."""
        self._backend.capabilities.require(Capability.LIST, backend=self._backend.name)
        return self._backend.list_folders(self._full_path(path))

    def get_file_info(self, path: str) -> FileInfo:
        """Get file metadata.

        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.
        """
        self._backend.capabilities.require(Capability.METADATA, backend=self._backend.name)
        info = self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    def get_folder_info(self, path: str) -> FolderInfo:
        """Get folder metadata.

        :raises NotFound: If the folder does not exist.
        """
        self._backend.capabilities.require(Capability.METADATA, backend=self._backend.name)
        info = self._backend.get_folder_info(self._full_path(path))
        return self._rebase_folder_info(info)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move/rename a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.
        """
        self._backend.capabilities.require(Capability.MOVE, backend=self._backend.name)
        self._backend.move(self._require_file_path(src), self._require_file_path(dst), overwrite=overwrite)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.
        """
        self._backend.capabilities.require(Capability.COPY, backend=self._backend.name)
        self._backend.copy(self._require_file_path(src), self._require_file_path(dst), overwrite=overwrite)
