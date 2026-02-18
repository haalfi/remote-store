"""Local filesystem backend — stdlib-only reference implementation."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, InvalidPath, NotFound, PermissionDenied
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

_ALL_CAPABILITIES = CapabilitySet(set(Capability))


class LocalBackend(Backend):
    """Local filesystem backend using only the Python standard library.

    :param root: Absolute path to the root directory on the local filesystem.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # region: path safety
    def _resolve(self, path: str) -> Path:
        """Resolve a relative path to an absolute path within root.

        Safety: ``.resolve()`` follows symlinks to their real target, and
        ``relative_to(self._root)`` then rejects any path that escapes the
        root — including symlinks pointing outside it.

        :raises InvalidPath: If the resolved path escapes the root.
        """
        resolved = (self._root / path).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise InvalidPath(f"Path escapes root directory: {path}", path=path, backend=self.name) from None
        return resolved

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

    # endregion

    # region: helpers
    @staticmethod
    def _read_content(content: WritableContent) -> bytes:
        if isinstance(content, bytes):
            return content
        return content.read()

    def _stat_to_fileinfo(self, path: str, full: Path) -> FileInfo:
        st = full.stat()
        return FileInfo(
            path=RemotePath(path),
            name=full.name,
            size=st.st_size,
            modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )

    # endregion

    # region: BE-004 through BE-005: existence checks
    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def is_file(self, path: str) -> bool:
        return self._resolve(path).is_file()

    def is_folder(self, path: str) -> bool:
        return self._resolve(path).is_dir()

    # endregion

    # region: BE-006 through BE-007: read operations
    def read(self, path: str) -> BinaryIO:
        full = self._resolve(path)
        try:
            return io.BytesIO(full.read_bytes())
        except FileNotFoundError:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def read_bytes(self, path: str) -> bytes:
        full = self._resolve(path)
        try:
            return full.read_bytes()
        except FileNotFoundError:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    # endregion

    # region: BE-008 through BE-011: write operations
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        full = self._resolve(path)
        if not overwrite and full.exists():
            raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            data = self._read_content(content)
            full.write_bytes(data)
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        full = self._resolve(path)
        if not overwrite and full.exists():
            raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            data = self._read_content(content)
            fd, tmp_path = tempfile.mkstemp(dir=str(full.parent))
            try:
                os.write(fd, data)
                os.close(fd)
                os.replace(tmp_path, str(full))
            except BaseException:
                os.close(fd) if not self._is_fd_closed(fd) else None
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    @staticmethod
    def _is_fd_closed(fd: int) -> bool:
        try:
            os.fstat(fd)
        except OSError:
            return True
        return False

    # endregion

    # region: BE-012 through BE-013: delete operations
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        full = self._resolve(path)
        try:
            full.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        full = self._resolve(path)
        if not full.exists():
            if not missing_ok:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            return
        if not full.is_dir():
            raise NotFound(f"Not a folder: {path}", path=path, backend=self.name)
        try:
            if recursive:
                shutil.rmtree(str(full))
            else:
                full.rmdir()
        except OSError as exc:
            import errno

            if exc.errno in (errno.ENOTEMPTY, 145):
                raise NotFound(f"Folder not empty: {path}", path=path, backend=self.name) from None
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None

    # endregion

    # region: BE-014 through BE-017: listing and metadata
    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        full = self._resolve(path)
        if not full.is_dir():
            return
        if recursive:
            for item in full.rglob("*"):
                if item.is_file():
                    rel = self.to_key(str(item))
                    yield self._stat_to_fileinfo(rel, item)
        else:
            for item in full.iterdir():
                if item.is_file():
                    rel = self.to_key(str(item))
                    yield self._stat_to_fileinfo(rel, item)

    def list_folders(self, path: str) -> Iterator[str]:
        full = self._resolve(path)
        if not full.is_dir():
            return
        for item in full.iterdir():
            if item.is_dir():
                yield item.name

    def get_file_info(self, path: str) -> FileInfo:
        full = self._resolve(path)
        if not full.is_file():
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)
        return self._stat_to_fileinfo(path, full)

    def get_folder_info(self, path: str) -> FolderInfo:
        full = self._resolve(path)
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
            path=RemotePath(path),
            file_count=file_count,
            total_size=total_size,
            modified_at=modified_at,
        )

    # endregion

    # region: BE-018 through BE-019: move and copy
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_full = self._resolve(src)
        dst_full = self._resolve(dst)
        if not src_full.exists():
            raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
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
        if not overwrite and dst_full.exists():
            raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        try:
            dst_full.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_full), str(dst_full))
        except PermissionError:
            raise PermissionDenied(f"Permission denied: {src} -> {dst}", path=src, backend=self.name) from None

    # endregion
