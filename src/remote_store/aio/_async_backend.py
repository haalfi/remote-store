"""AsyncBackend abstract base class -- the async core contract."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, TypeVar

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType

    from remote_store._capabilities import CapabilitySet
    from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._types import AsyncWritableContent

T = TypeVar("T")


class AsyncBackend(abc.ABC):
    """Abstract base class for all async storage backends.

    Every backend must implement all abstract methods. Backend-native
    exceptions must never leak -- they must be mapped to ``remote_store`` errors.
    """

    # region: context-manager

    async def __aenter__(self) -> AsyncBackend:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # endregion

    # region: abstract-properties

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this backend type (e.g. ``'local'``, ``'s3'``)."""

    @property
    @abc.abstractmethod
    def capabilities(self) -> CapabilitySet:
        """Declared capabilities of this backend."""

    # endregion

    # region: abstract-async-methods

    @abc.abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file or folder exists. Never raises ``NotFound``.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if a file or folder exists at *path*.
        """

    @abc.abstractmethod
    async def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file.

        Args:
            path: Backend-relative key.

        Returns:
            ``True`` if *path* exists and is a file.
        """

    @abc.abstractmethod
    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if *path* exists and is a folder.
        """

    @abc.abstractmethod
    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Open a file for reading and return an async iterator of byte chunks.

        Args:
            path: Backend-relative key.

        Returns:
            An async iterator yielding byte chunks.

        Raises:
            NotFound: If the file does not exist.
        """
        if False:  # pragma: no cover
            yield

    @abc.abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        Args:
            path: Backend-relative key.

        Returns:
            The file content.

        Raises:
            NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content to a file.

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.
            metadata: Optional user-defined string metadata.

        Returns:
            A ``WriteResult`` with size, path, and optional native fields.

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content atomically via temp file + rename.

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.
            metadata: Optional user-defined string metadata.

        Returns:
            A ``WriteResult`` with size, path, and optional native fields.

        Raises:
            CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        Args:
            path: Backend-relative key.
            missing_ok: If ``True``, do not raise when the file is absent.

        Raises:
            NotFound: If the file is missing and ``missing_ok`` is ``False``.
        """

    @abc.abstractmethod
    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        Args:
            path: Backend-relative key.
            recursive: If ``True``, delete all contents first.
            missing_ok: If ``True``, do not raise when absent.

        Raises:
            NotFound: If the folder is missing and ``missing_ok`` is ``False``.
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
        """

    @abc.abstractmethod
    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        """List files under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.
            recursive: If ``True``, include files in all subdirectories.
            max_depth: Optional maximum folder depth to traverse.  When set,
                backends that support native depth limiting prune traversal
                early.  Backends that ignore this parameter still produce
                correct results -- the Store applies client-side filtering
                as a safety net.  ``None`` (default) defers to *recursive*.

        Returns:
            An async iterator of ``FileInfo`` objects.
        """
        if False:  # pragma: no cover
            yield

    @abc.abstractmethod
    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """List immediate subfolders under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FolderEntry`` objects with ``.name`` and ``.path``.
        """
        if False:  # pragma: no cover
            yield

    @abc.abstractmethod
    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        Args:
            path: Backend-relative key.

        Returns:
            A ``FileInfo`` with size, modification time, etc.

        Raises:
            NotFound: If the file does not exist.
        """

    @abc.abstractmethod
    async def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            A ``FolderInfo`` with file count, total size, etc.

        Raises:
            NotFound: If the folder does not exist.
        """

    @abc.abstractmethod
    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    @abc.abstractmethod
    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """

    # endregion

    # region: concrete-async-methods

    async def aclose(self) -> None:  # noqa: B027
        """Release resources. Default is a no-op."""

    async def check_health(self) -> None:  # noqa: B027
        """Verify the backend is reachable and credentials are valid.

        The default implementation is a no-op (always succeeds). Backends
        override this to perform a lightweight, non-destructive connectivity
        check using the cheapest possible read-only operation.

        Raises:
            PermissionDenied: If credentials are invalid.
            NotFound: If the bucket, container, or root path does not exist.
            BackendUnavailable: If the backend cannot be reached.
        """

    async def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Match files against a glob pattern.

        Non-abstract -- backends with native glob support override this
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
        if False:  # pragma: no cover
            yield

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield both files and folders under ``path`` in a single pass.

        Files are yielded as ``FileInfo`` objects, folders as
        ``FolderEntry`` objects. The default implementation chains
        ``list_files()`` and ``list_folders()``. Backends that can fetch
        both in a single I/O call should override this for efficiency.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        async for info in self.list_files(path):
            yield info
        async for entry in self.list_folders(path):
            yield entry

    # endregion

    # region: concrete-sync-methods

    def to_key(self, native_path: str) -> str:
        """Convert a backend-native path to a backend-relative key.

        Strips the backend's own root/prefix from the path. The default
        implementation is the identity function -- backends with a native
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
        identity function -- backends with a native root (bucket, base_path)
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

    # endregion
