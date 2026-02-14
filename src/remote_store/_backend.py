"""Backend abstract base class — the core contract."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._capabilities import CapabilitySet
    from remote_store._models import FileInfo, FolderInfo
    from remote_store._types import WritableContent

T = TypeVar("T")


class Backend(abc.ABC):
    """Abstract base class for all storage backends.

    Every backend must implement all abstract methods. Backend-native
    exceptions must never leak — they must be mapped to ``remote_store`` errors.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this backend type (e.g. ``'local'``, ``'s3'``)."""

    @property
    @abc.abstractmethod
    def capabilities(self) -> CapabilitySet:
        """Declared capabilities of this backend."""

    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file or folder exists. Never raises ``NotFound``."""

    @abc.abstractmethod
    def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file."""

    @abc.abstractmethod
    def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder."""

    @abc.abstractmethod
    def read(self, path: str) -> BinaryIO:
        """Open a file for reading and return a binary stream.

        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        :param overwrite: If ``False``, raise if file already exists.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically via temp file + rename.

        :raises CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        :raises NotFound: If the file is missing and ``missing_ok`` is ``False``.
        """

    @abc.abstractmethod
    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        :raises NotFound: If the folder is missing and ``missing_ok`` is ``False``.
        """

    @abc.abstractmethod
    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        """List files under ``path``.

        :param recursive: If ``True``, include files in all subdirectories.
        """

    @abc.abstractmethod
    def list_folders(self, path: str) -> Iterator[str]:
        """List immediate subfolder names under ``path``."""

    @abc.abstractmethod
    def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        :raises NotFound: If the folder does not exist.
        """

    @abc.abstractmethod
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move/rename a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    def close(self) -> None:  # noqa: B027
        """Release resources. Default is a no-op."""

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the native backend handle if it matches the requested type.

        :param type_hint: The expected type (e.g., ``fsspec.AbstractFileSystem``).
        :raises CapabilityNotSupported: If backend cannot provide the requested type.
        """
        raise CapabilityNotSupported(
            f"Backend '{self.name}' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )
