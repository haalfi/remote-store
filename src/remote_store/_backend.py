"""Backend abstract base class — the core contract."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager

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
        """Check if a file or folder exists. Never raises ``NotFound``.

        :param path: Backend-relative key, or ``""`` for the root.
        :returns: ``True`` if a file or folder exists at *path*.
        """

    @abc.abstractmethod
    def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file.

        :param path: Backend-relative key.
        :returns: ``True`` if *path* exists and is a file.
        """

    @abc.abstractmethod
    def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder.

        :param path: Backend-relative key, or ``""`` for the root.
        :returns: ``True`` if *path* exists and is a folder.
        """

    @abc.abstractmethod
    def read(self, path: str) -> BinaryIO:
        """Open a file for reading and return a binary stream.

        :param path: Backend-relative key.
        :returns: A readable binary stream.
        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        :param path: Backend-relative key.
        :returns: The file content.
        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        :param path: Backend-relative key.
        :param content: Data to write.
        :param overwrite: If ``False``, raise if file already exists.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically via temp file + rename.

        :param path: Backend-relative key.
        :param content: Data to write.
        :param overwrite: If ``False``, raise if file already exists.
        :raises CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def open_atomic(self, path: str, *, overwrite: bool = False) -> AbstractContextManager[BinaryIO]:
        """Yield a writable file object backed by a temporary location.

        On successful exit the temp file is atomically promoted to *path*.
        On exception the temp file is removed and *path* is untouched.

        :param path: Backend-relative key.
        :param overwrite: If ``False``, raise if file already exists.
        :raises AlreadyExists: If *path* exists and *overwrite* is ``False``.
        :raises CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
        """

    @abc.abstractmethod
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        :param path: Backend-relative key.
        :param missing_ok: If ``True``, do not raise when the file is absent.
        :raises NotFound: If the file is missing and ``missing_ok`` is ``False``.
        """

    @abc.abstractmethod
    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        :param path: Backend-relative key.
        :param recursive: If ``True``, delete all contents first.
        :param missing_ok: If ``True``, do not raise when absent.
        :raises NotFound: If the folder is missing and ``missing_ok`` is ``False``.
        :raises DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
        """

    @abc.abstractmethod
    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        """List files under ``path``.

        :param path: Backend-relative folder key, or ``""`` for the root.
        :param recursive: If ``True``, include files in all subdirectories.
        :returns: An iterator of ``FileInfo`` objects.
        """

    @abc.abstractmethod
    def list_folders(self, path: str) -> Iterator[str]:
        """List immediate subfolder names under ``path``.

        :param path: Backend-relative folder key, or ``""`` for the root.
        :returns: An iterator of subfolder name strings.
        """

    @abc.abstractmethod
    def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        :param path: Backend-relative key.
        :returns: A ``FileInfo`` with size, modification time, etc.
        :raises NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        :param path: Backend-relative folder key, or ``""`` for the root.
        :returns: A ``FolderInfo`` with file count, total size, etc.
        :raises NotFound: If the folder does not exist.
        """

    @abc.abstractmethod
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        :param src: Backend-relative source key.
        :param dst: Backend-relative destination key.
        :param overwrite: If ``True``, replace any existing file at *dst*.
        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        :param src: Backend-relative source key.
        :param dst: Backend-relative destination key.
        :param overwrite: If ``True``, replace any existing file at *dst*.
        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Match files against a glob pattern.

        Non-abstract — backends with native glob support override this
        and add ``Capability.GLOB`` to their capability set.

        :param pattern: Glob pattern (e.g., ``"data/*.csv"``, ``"**/*.txt"``).
        :raises CapabilityNotSupported: If the backend lacks ``GLOB``.
        """
        raise CapabilityNotSupported(
            f"Backend '{self.name}' does not support glob."
            " Use list_files(pattern=...) for name filtering"
            " or ext.glob.glob_files() for full glob.",
            capability="glob",
            backend=self.name,
        )

    def to_key(self, native_path: str) -> str:
        """Convert a backend-native path to a backend-relative key.

        Strips the backend's own root/prefix from the path. The default
        implementation is the identity function — backends with a native
        root (filesystem path, bucket prefix, base_path) override this.

        :param native_path: Absolute or backend-native path string.
        :returns: Path relative to the backend's root.
        """
        return native_path

    def native_path(self, path: str) -> str:
        """Convert a backend-relative key to the backend-native path.

        The inverse of ``to_key()``. The default implementation is the
        identity function — backends with a native root (bucket, base_path)
        override this to prepend their prefix.

        :param path: Backend-relative key.
        :returns: Backend-native path usable with the native handle from
            ``unwrap()``.
        """
        return path

    def check_health(self) -> None:  # noqa: B027
        """Verify the backend is reachable and credentials are valid.

        The default implementation is a no-op (always succeeds). Backends
        override this to perform a lightweight, non-destructive connectivity
        check using the cheapest possible read-only operation.

        :raises PermissionDenied: If credentials are invalid.
        :raises NotFound: If the bucket, container, or root path does not exist.
        :raises BackendUnavailable: If the backend cannot be reached.
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
