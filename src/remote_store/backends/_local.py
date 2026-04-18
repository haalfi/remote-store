"""Local filesystem backend — stdlib-only reference implementation."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from remote_store._backend import _COPY_BUFSIZE, Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound, PermissionDenied
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.WRITE_RESULT_NATIVE, Capability.USER_METADATA})

log = logging.getLogger(__name__)


class LocalBackend(Backend):
    """Local filesystem backend using only the Python standard library.

    ``move()`` uses ``shutil.move``, which calls ``os.rename`` for
    same-filesystem moves (atomic) but falls back to copy-then-delete
    for cross-filesystem moves (not atomic).  ``ATOMIC_MOVE`` is
    declared because within-root moves are always same-filesystem.

    Args:
        root: Absolute path to the root directory on the local filesystem.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    # region: properties

    @property
    def name(self) -> str:
        return "local"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # endregion

    # region: public methods

    def check_health(self) -> None:
        if not self._root.exists():
            raise NotFound(
                f"Root directory not found: {self._root}",
                path=str(self._root),
                backend=self.name,
            )
        if not os.access(self._root, os.R_OK):
            raise PermissionDenied(
                f"Root directory not readable: {self._root}",
                path=str(self._root),
                backend=self.name,
            )

    def to_key(self, native_path: str) -> str:
        root_str = str(self._root)
        # Normalize the input to use forward slashes for comparison
        normalized = native_path.replace("\\", "/")
        root_prefix = root_str.replace("\\", "/")
        if normalized.startswith(root_prefix + "/"):
            return normalized[len(root_prefix) + 1 :]
        if normalized == root_prefix:
            return ""
        return native_path

    def native_path(self, path: str) -> str:
        root_str = str(self._root).replace("\\", "/")
        if path:
            return f"{root_str}/{path}"
        return root_str

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with local filesystem details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="local"`` and ``details`` containing
            ``root`` and ``absolute_path``.
        """
        from remote_store._resolution import ResolutionPlan as _RP

        return _RP(
            kind="local",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "root": str(self._root),
                "absolute_path": str(self._root / path) if path else str(self._root),
            },
        )

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def is_file(self, path: str) -> bool:
        return self._resolve(path).is_file()

    def is_folder(self, path: str) -> bool:
        return self._resolve(path).is_dir()

    def read(self, path: str) -> BinaryIO:
        full = self._resolve(path)
        try:
            return open(str(full), "rb")  # noqa: SIM115
        except FileNotFoundError:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except IsADirectoryError:
            raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
        except PermissionError:
            # Windows raises PermissionError (not IsADirectoryError) for directories
            if full.is_dir():
                raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def read_bytes(self, path: str) -> bytes:
        full = self._resolve(path)
        try:
            return full.read_bytes()
        except FileNotFoundError:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except IsADirectoryError:
            raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
        except PermissionError:
            # Windows raises PermissionError (not IsADirectoryError) for directories
            if full.is_dir():
                raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        full = self._resolve(path)
        if full.is_dir():
            raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name)
        if not overwrite and full.exists():
            raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                full.write_bytes(content)
                size = len(content)
            else:
                with open(str(full), "wb") as f:
                    shutil.copyfileobj(content, f, _COPY_BUFSIZE)
                size = full.stat().st_size
        except IsADirectoryError:
            raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name) from None
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        return WriteResult(path=RemotePath(path), size=size, source="basic")

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        full = self._resolve(path)
        if full.is_dir():
            raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name)
        if not overwrite and full.exists():
            raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=str(full.parent))
            try:
                with os.fdopen(fd, "wb") as f:
                    if isinstance(content, bytes):
                        f.write(content)
                        size = len(content)
                    else:
                        shutil.copyfileobj(content, f, _COPY_BUFSIZE)
                        size = os.path.getsize(tmp_path)
                os.replace(tmp_path, str(full))
            except BaseException:
                with contextlib.suppress(OSError):
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                raise
        except IsADirectoryError:
            raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name) from None
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        return WriteResult(path=RemotePath(path), size=size, source="basic")

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        full = self._resolve(path)
        if full.is_dir():
            raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name)
        if not overwrite and full.exists():
            raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=str(full.parent))
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

        try:
            with os.fdopen(fd, "wb") as f:
                yield f
            try:
                os.replace(tmp_path, str(full))
            except IsADirectoryError:
                raise InvalidPath(
                    f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name
                ) from None
            except PermissionError:
                raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except BaseException:
            with contextlib.suppress(OSError):
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            raise

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        full = self._resolve(path)
        try:
            full.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except IsADirectoryError:
            raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
        except PermissionError:
            # Windows raises PermissionError (not IsADirectoryError) for directories
            if full.is_dir():
                raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name) from None
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        full = self._resolve(path)
        if not full.exists():
            if not missing_ok:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            return
        if not full.is_dir():
            raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)
        try:
            if recursive:
                shutil.rmtree(str(full))
            else:
                full.rmdir()
        except OSError as exc:
            import errno

            if exc.errno in (errno.ENOTEMPTY, 145):
                raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name) from None
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        for item in self._root.glob(pattern):
            if item.is_file():
                try:
                    item.resolve().relative_to(self._root)
                except ValueError:
                    continue  # skip paths that escape root
                rel = self.to_key(str(item))
                yield self._stat_to_fileinfo(rel, item)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        full = self._resolve(path)
        if not full.is_dir():
            return
        if recursive and max_depth is not None:
            for dirpath, dirnames, filenames in os.walk(full):
                depth = len(Path(dirpath).relative_to(full).parts)
                if depth > max_depth:
                    dirnames.clear()
                    continue
                for fname in filenames:
                    item = Path(dirpath) / fname
                    rel = self.to_key(str(item))
                    yield self._stat_to_fileinfo(rel, item)
                if depth == max_depth:
                    dirnames.clear()
        elif recursive:
            for item in full.rglob("*"):
                if item.is_file():
                    rel = self.to_key(str(item))
                    yield self._stat_to_fileinfo(rel, item)
        else:
            for item in full.iterdir():
                if item.is_file():
                    rel = self.to_key(str(item))
                    yield self._stat_to_fileinfo(rel, item)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        full = self._resolve(path)
        if not full.is_dir():
            return
        for item in full.iterdir():
            if item.is_dir():
                rel = self.to_key(str(item))
                yield FolderEntry(path=RemotePath(rel), name=item.name)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        full = self._resolve(path)
        if not full.is_dir():
            return
        for item in full.iterdir():
            if item.is_file():
                rel = self.to_key(str(item))
                yield self._stat_to_fileinfo(rel, item)
            elif item.is_dir():
                rel = self.to_key(str(item))
                yield FolderEntry(path=RemotePath(rel), name=item.name)

    def get_file_info(self, path: str) -> FileInfo:
        full = self._resolve(path)
        if full.is_dir():
            raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name)
        if not full.is_file():
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)
        return self._stat_to_fileinfo(path, full)

    def get_folder_info(self, path: str) -> FolderInfo:
        full = self._resolve(path)
        if full.is_file():
            raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)
        if not full.is_dir():
            raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
        file_count = 0
        total_size = 0
        latest_mtime: float | None = None
        for item in full.rglob("*"):
            if item.is_file():
                file_count += 1
                st = item.stat()
                total_size += st.st_size
                if latest_mtime is None or st.st_mtime > latest_mtime:
                    latest_mtime = st.st_mtime
        modified_at = datetime.fromtimestamp(latest_mtime, tz=timezone.utc) if latest_mtime is not None else None
        return FolderInfo(
            path=RemotePath.from_backend_path(path),
            file_count=file_count,
            total_size=total_size,
            modified_at=modified_at,
        )

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_full = self._resolve(src)
        dst_full = self._resolve(dst)
        if not src_full.exists():
            raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
        if src_full.is_dir():
            raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)
        if dst_full.is_dir():
            raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
        if src_full == dst_full:
            return  # self-move is a no-op
        if not overwrite and dst_full.exists():
            raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        try:
            dst_full.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_full), str(dst_full))
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {src} -> {dst}", path=src, backend=self.name) from None

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_full = self._resolve(src)
        dst_full = self._resolve(dst)
        if not src_full.exists():
            raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
        if src_full.is_dir():
            raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)
        if dst_full.is_dir():
            raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
        if src_full == dst_full:
            return  # self-copy is a no-op
        if not overwrite and dst_full.exists():
            raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        try:
            dst_full.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_full), str(dst_full))
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {src} -> {dst}", path=src, backend=self.name) from None

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return f"LocalBackend(root={str(self._root)!r})"

    # endregion

    # region: private helpers

    def _resolve(self, path: str) -> Path:
        """Resolve a relative path to an absolute path within root.

        Safety: ``.resolve()`` follows symlinks to their real target, and
        ``relative_to(self._root)`` then rejects any path that escapes the
        root — including symlinks pointing outside it.

        Raises:
            InvalidPath: If the resolved path escapes the root.
        """
        resolved = (self._root / path).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise InvalidPath(f"Path escapes root directory: {path}", path=path, backend=self.name) from None
        return resolved

    def _stat_to_fileinfo(self, path: str, full: Path) -> FileInfo:
        st = full.stat()
        return FileInfo(
            path=RemotePath(path),
            name=full.name,
            size=st.st_size,
            modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )

    # endregion
