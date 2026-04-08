"""Backend abstract base class — the core contract."""

from __future__ import annotations

import abc
import shutil
import tempfile
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager

    from remote_store._capabilities import CapabilitySet
    from remote_store._models import FileInfo, FolderEntry, FolderInfo
    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")


class _SeekableSpool(tempfile.SpooledTemporaryFile):  # type: ignore[type-arg]
    """SpooledTemporaryFile subclass that exposes ``seekable()``.

    ``SpooledTemporaryFile`` gained ``seekable()`` in Python 3.11.
    This subclass adds it for Python 3.10 compatibility.
    """

    def seekable(self) -> bool:
        return True


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

        Returns ``False`` if any ancestor of *path* is a file (file-as-directory-component),
        as traversal cannot proceed.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if a file or folder exists at *path*. ``False`` if the path
            does not exist or if any ancestor is a file instead of a directory.
        """

    @abc.abstractmethod
    def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file.

        Returns ``False`` if the path does not exist, or if any ancestor of *path*
        is a file (file-as-directory-component).

        Args:
            path: Backend-relative key.

        Returns:
            ``True`` if *path* exists and is a file. ``False`` if the path does not
            exist or if any ancestor is a file instead of a directory.
        """

    @abc.abstractmethod
    def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder.

        Returns ``False`` if the path does not exist, or if any ancestor of *path*
        is a file (file-as-directory-component).

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if *path* exists and is a folder. ``False`` if the path does not
            exist or if any ancestor is a file instead of a directory.
        """

    @abc.abstractmethod
    def read(self, path: str) -> BinaryIO:
        """Open a file for reading and return a binary stream.

        Args:
            path: Backend-relative key.

        Returns:
            A readable binary stream.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* names a directory, not a file.
        """

    @abc.abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        Args:
            path: Backend-relative key.

        Returns:
            The file content.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* names a directory, not a file.
        """

    def read_seekable(self, path: str) -> BinaryIO:
        """Open a file for random-access reading and return a seekable stream.

        The default implementation delegates to ``read()``.  If the returned
        stream is already seekable, it is returned as-is.  Otherwise, the
        stream is spooled into a ``SpooledTemporaryFile`` (up to 8 MB in
        RAM, beyond that on disk) and returned positioned at byte 0.

        Backends MAY override to provide an optimized implementation.
        For example, ``AzureBackend`` returns a range reader that issues
        HTTP Range requests on each ``read()`` call.

        Args:
            path: Backend-relative key.

        Returns:
            A seekable binary stream positioned at byte 0.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* names a directory, not a file.
        """
        stream = self.read(path)
        if stream.seekable():
            return stream
        spool: BinaryIO = _SeekableSpool(max_size=8 * 1024 * 1024)  # type: ignore[assignment]
        try:
            shutil.copyfileobj(stream, spool)
        except BaseException:
            spool.close()
            raise
        finally:
            stream.close()
        spool.seek(0)
        return spool

    @abc.abstractmethod
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
            InvalidPath: If *path* names a directory.
        """

    @abc.abstractmethod
    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically via temp file + rename.

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.

        Raises:
            CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
            InvalidPath: If *path* names a directory.
        """

    @abc.abstractmethod
    def open_atomic(self, path: str, *, overwrite: bool = False) -> AbstractContextManager[BinaryIO]:
        """Yield a writable file object backed by a temporary location.

        On successful exit the temp file is atomically promoted to *path*.
        On exception the temp file is removed and *path* is untouched.

        Args:
            path: Backend-relative key.
            overwrite: If ``False``, raise if file already exists.

        Raises:
            AlreadyExists: If *path* exists and *overwrite* is ``False``.
            InvalidPath: If *path* names a directory.
            CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
        """

    @abc.abstractmethod
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        Args:
            path: Backend-relative key.
            missing_ok: If ``True``, do not raise when the file is absent.

        Raises:
            NotFound: If the file is missing and ``missing_ok`` is ``False``.
            InvalidPath: If *path* names a directory (type mismatch is
                not silenced by *missing_ok*).
        """

    @abc.abstractmethod
    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        Args:
            path: Backend-relative key.
            recursive: If ``True``, delete all contents first.
            missing_ok: If ``True``, do not raise when absent.

        Raises:
            NotFound: If the folder is missing and ``missing_ok`` is ``False``.
            InvalidPath: If *path* names a file, not a folder.
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
        """

    @abc.abstractmethod
    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        """List files under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.
            recursive: If ``True``, include files in all subdirectories.
            max_depth: Optional maximum folder depth to traverse.  When set,
                backends that support native depth limiting prune traversal
                early.  Backends that ignore this parameter still produce
                correct results — the Store applies client-side filtering
                as a safety net.  ``None`` (default) defers to *recursive*.

        Returns:
            An iterator of ``FileInfo`` objects.
        """

    @abc.abstractmethod
    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        """List immediate subfolders under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An iterator of ``FolderEntry`` objects with ``.name`` and ``.path``.
        """

    @abc.abstractmethod
    def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        Args:
            path: Backend-relative key.

        Returns:
            A ``FileInfo`` with size, modification time, etc.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* names a directory, not a file.
        """

    @abc.abstractmethod
    def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            A ``FolderInfo`` with file count, total size, etc.

        Raises:
            NotFound: If the folder does not exist.
            InvalidPath: If *path* names a file, not a folder.
        """

    @abc.abstractmethod
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        When ``src == dst`` the call is a no-op (data preserved).

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` or ``dst`` names a directory.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        When ``src == dst`` the call is a no-op (data preserved).

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` or ``dst`` names a directory.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        """Yield both files and folders under ``path`` in a single pass.

        Files are yielded as ``FileInfo`` objects, folders as
        ``FolderEntry`` objects. The default implementation chains
        ``list_files()`` and ``list_folders()``. Backends that can fetch
        both in a single I/O call should override this for efficiency.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        yield from self.list_files(path)
        yield from self.list_folders(path)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Match files against a glob pattern.

        Non-abstract — backends with native glob support override this
        and add ``Capability.GLOB`` to their capability set.

        Args:
            pattern: Glob pattern (e.g., ``"data/*.csv"``, ``"**/*.txt"``).

        Raises:
            CapabilityNotSupported: If the backend lacks ``GLOB``.
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

        Args:
            native_path: Absolute or backend-native path string.

        Returns:
            Path relative to the backend's root.
        """
        return native_path

    def native_path(self, path: str) -> str:
        """Convert a backend-relative key to the backend-native path.

        The inverse of ``to_key()``. The default implementation is the
        identity function — backends with a native root (bucket, base_path)
        override this to prepend their prefix.

        Args:
            path: Backend-relative key.

        Returns:
            Backend-native path usable with the native handle from ``unwrap()``.
        """
        return path

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` describing how *path* maps to storage.

        Pure introspection -- no I/O is performed.  Backends override this
        to populate ``details`` with backend-specific context.

        Args:
            path: Backend-relative key.

        Returns:
            A frozen ``ResolutionPlan`` with ``kind``, ``backend``,
            ``key``, ``native_path``, and ``details``.
        """
        from remote_store._resolution import ResolutionPlan as _RP

        return _RP(
            kind=self.name,
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={},
        )

    def check_health(self) -> None:  # noqa: B027
        """Verify the backend is reachable and credentials are valid.

        The default implementation is a no-op (always succeeds). Backends
        override this to perform a lightweight, non-destructive connectivity
        check using the cheapest possible read-only operation.

        Raises:
            PermissionDenied: If credentials are invalid.
            NotFound: If the bucket, container, or root path does not exist.
            BackendUnavailable: If the backend cannot be reached.
        """

    def close(self) -> None:  # noqa: B027
        """Release resources. Default is a no-op."""

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the native backend handle if it matches the requested type.

        Args:
            type_hint: The expected type (e.g., ``fsspec.AbstractFileSystem``).

        Raises:
            CapabilityNotSupported: If backend cannot provide the requested type.
        """
        raise CapabilityNotSupported(
            f"Backend '{self.name}' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )
