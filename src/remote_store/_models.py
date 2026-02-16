"""Immutable metadata and identity models."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from remote_store._path import RemotePath


@dataclasses.dataclass(frozen=True, eq=False)
class FileInfo:
    """Immutable snapshot of file metadata.

    :param path: Normalized remote path.
    :param name: File name (final path component).
    :param size: File size in bytes.
    :param modified_at: Last modification time.
    :param checksum: Optional checksum (e.g. ETag, MD5).
    :param content_type: Optional MIME type.
    :param extra: Backend-specific metadata.
    """

    path: RemotePath
    name: str
    size: int
    modified_at: datetime
    checksum: str | None = None
    content_type: str | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FileInfo):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True, eq=False)
class FolderInfo:
    """Aggregated folder metadata.

    :param path: Normalized remote path.
    :param file_count: Number of files in the folder.
    :param total_size: Total size of all files in bytes.
    :param modified_at: Optional last modification time.
    :param extra: Backend-specific metadata.
    """

    path: RemotePath
    file_count: int
    total_size: int
    modified_at: datetime | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FolderInfo):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True, eq=False)
class RemoteFile:
    """Immutable value object identifying a remote file.

    :param path: Normalized remote path.
    """

    path: RemotePath

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RemoteFile):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True, eq=False)
class RemoteFolder:
    """Immutable value object identifying a remote folder.

    :param path: Normalized remote path.
    """

    path: RemotePath

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RemoteFolder):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)
