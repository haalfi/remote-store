"""Immutable metadata and identity models.

``FileInfo``, ``FolderEntry``, and ``FolderInfo`` all satisfy the
``PathEntry`` protocol, enabling uniform iteration over mixed results.
"""

from __future__ import annotations

import dataclasses
import re
import typing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from remote_store._path import RemotePath

_HEX_RE = re.compile(r"^[0-9a-f]+$")


@typing.runtime_checkable
class PathEntry(typing.Protocol):
    """Shared interface for listing results -- every entry has a name and path."""

    @property
    def name(self) -> str:
        """Entry name (final path component)."""
        ...

    @property
    def path(self) -> RemotePath:
        """Normalized remote path."""
        ...


@dataclasses.dataclass(frozen=True)
class ContentDigest:
    """Verified content digest with known algorithm.

    Both ``algorithm`` and ``value`` are normalized to lowercase on
    construction.

    Attributes:
        algorithm: Hash algorithm name, always lowercase (e.g., ``"sha256"``).
        value: Lowercase hex-encoded digest, no prefix, no separators.
    """

    algorithm: str
    value: str

    def __post_init__(self) -> None:
        if not self.algorithm:
            msg = "algorithm must not be empty"
            raise ValueError(msg)
        if not self.value:
            msg = "value must not be empty"
            raise ValueError(msg)
        # Normalize to lowercase.
        object.__setattr__(self, "algorithm", self.algorithm.strip().lower())
        normalized = self.value.strip().lower()
        if not _HEX_RE.match(normalized):
            msg = f"value must be hexadecimal, got {self.value!r}"
            raise ValueError(msg)
        object.__setattr__(self, "value", normalized)


@dataclasses.dataclass(frozen=True, eq=False)
class FileInfo:
    """Immutable snapshot of file metadata.

    Satisfies the ``PathEntry`` protocol.

    Attributes:
        path: Normalized remote path.
        name: File name (final path component).
        size: File size in bytes.
        modified_at: Last modification time.
        digest: Verified content digest with known algorithm.
        etag: Opaque backend-provided tag for change detection.
        content_type: Optional MIME type.
        extra: Backend-specific metadata.
    """

    path: RemotePath
    name: str
    size: int
    modified_at: datetime
    digest: ContentDigest | None = None
    etag: str | None = None
    content_type: str | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FileInfo):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True, eq=False)
class FolderEntry:
    """Immutable folder identity returned by listing operations.

    Satisfies the ``PathEntry`` protocol.

    Attributes:
        path: Normalized remote path.
        name: Folder name (final path component).
    """

    path: RemotePath
    name: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FolderEntry):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True, eq=False)
class FolderInfo:
    """Aggregated folder metadata.

    Satisfies the ``PathEntry`` protocol.

    Attributes:
        path: Normalized remote path.
        file_count: Number of files in the folder.
        total_size: Total size of all files in bytes.
        modified_at: Optional last modification time.
        extra: Backend-specific metadata.
    """

    path: RemotePath
    file_count: int
    total_size: int
    modified_at: datetime | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)

    @property
    def name(self) -> str:
        """Folder name (final path component).

        Unlike ``FileInfo`` and ``FolderEntry``, which store ``name``
        as a constructor field, this is a derived property (``self.path.name``)
        to avoid redundancy and keep ``name`` in sync with ``path``.
        """
        return self.path.name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FolderInfo):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)
