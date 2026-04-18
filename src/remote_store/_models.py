"""Immutable metadata and identity models.

``FileInfo``, ``FolderEntry``, and ``FolderInfo`` all satisfy the
``PathEntry`` protocol, enabling uniform iteration over mixed results.
"""

from __future__ import annotations

import dataclasses
import re
import typing
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from remote_store._path import RemotePath

_HEX_RE = re.compile(r"^[0-9a-f]+$")


@typing.runtime_checkable
class PathEntry(typing.Protocol):
    """Shared interface for listing results -- every entry has a name and path."""

    @property
    def name(self) -> str:
        """Entry name (final path component)."""

    @property
    def path(self) -> RemotePath:
        """Normalized remote path."""


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
        # Normalize first, then validate — catches whitespace-only input.
        object.__setattr__(self, "algorithm", self.algorithm.strip().lower())
        if not self.algorithm:
            msg = "algorithm must not be empty"
            raise ValueError(msg)
        normalized = self.value.strip().lower()
        if not normalized:
            msg = "value must not be empty"
            raise ValueError(msg)
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
        metadata: User-supplied key/value metadata echoed from the backend (WR-012).
        extra: Backend-specific metadata.
    """

    path: RemotePath
    name: str
    size: int
    modified_at: datetime
    digest: ContentDigest | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: Mapping[str, str] | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FileInfo):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)


@dataclasses.dataclass(frozen=True)
class WriteResult:
    """Immutable snapshot of a completed write operation.

    Returned by ``Store.write()``, ``Store.write_text()``, and
    ``Store.write_atomic()``.

    Attributes:
        path: Normalised written path, store-relative (WR-002).
        size: Bytes written (WR-003).
        source: Provenance of the optional fields — ``"native"`` when the
            backend populated them from its write response,
            ``"basic"`` when derived locally, ``"sidecar"`` when
            constructed by ``Store.head()`` (WR-004, WR-006).
        digest: Verified content digest — either a client-computed hash
            from ``ext.write`` helpers (WR-014) or a backend-echoed
            content hash from the write response (e.g., Azure
            ``content_md5`` surfaced as ``ContentDigest("md5", …)``).
            ``None`` on the default write path for all v1 backends.
        etag: Opaque backend change tag; semantics vary by backend.
        version_id: Immutable backend version identifier; ``None`` when
            the backend does not version objects.
        last_modified: Server timestamp from the write response; ``None``
            when the backend's write response omits it.
        metadata: Echo of user metadata stored with the object (WR-012).
    """

    path: RemotePath
    size: int
    source: Literal["native", "basic", "sidecar"] = "basic"
    digest: ContentDigest | None = None
    etag: str | None = None
    version_id: str | None = None
    last_modified: datetime | None = None
    metadata: Mapping[str, str] | None = None


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
