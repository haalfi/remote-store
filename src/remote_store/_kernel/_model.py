"""Records a driver hands the kernel, and the operation scopes it classifies by."""

from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Literal

from remote_store._models import _UNKNOWN_MODIFIED_AT

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from remote_store._models import ContentDigest


class Op(enum.Enum):
    """What asked: the public operation, or one of the kernel's internal scopes.

    ``classify(exc, op=..., key=...)`` receives it so a driver can type the same
    wire error differently by scope, and the kernel's absent-container
    answers are decided per value.
    """

    EXISTS = "exists"
    IS_FILE = "is_file"
    IS_FOLDER = "is_folder"
    READ = "read"
    READ_BYTES = "read_bytes"
    READ_SEEKABLE = "read_seekable"
    WRITE = "write"
    WRITE_ATOMIC = "write_atomic"
    OPEN_ATOMIC = "open_atomic"
    DELETE = "delete"
    DELETE_FOLDER = "delete_folder"
    LIST_FILES = "list_files"
    LIST_FOLDERS = "list_folders"
    ITER_CHILDREN = "iter_children"
    GLOB = "glob"
    GET_FILE_INFO = "get_file_info"
    GET_FOLDER_INFO = "get_folder_info"
    MOVE = "move"
    COPY = "copy"
    CLOSE = "close"
    PROBE = "probe"
    IDENTITY = "identity"
    MONITOR = "monitor"


@dataclasses.dataclass(frozen=True)
class Entry:
    """One node as the driver's wire reports it.

    ``key`` is canonical when the driver reports what the kernel gave it; a key
    stored by another tool may not be, and the kernel omits such an entry from
    every listing.
    """

    key: str
    kind: Literal["file", "folder"]
    size: int = 0
    modified_at: datetime = _UNKNOWN_MODIFIED_AT
    digest: ContentDigest | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: Mapping[str, str] | None = None
    extra: dict[str, object] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Page:
    """Whatever one ``list_page`` call returns.

    ``prefixes`` are folder keys without a trailing ``/``. ``cursor`` is
    ``None`` on the last page.
    """

    entries: tuple[Entry, ...] = ()
    prefixes: tuple[str, ...] = ()
    cursor: object | None = None


@dataclasses.dataclass(frozen=True)
class PutResult:
    """What a write reports, without its path: the kernel builds the path.

    The kernel builds ``WriteResult.path`` from the canonical key before the
    driver commits, so a driver never constructs a path that could fail after
    the bytes land.
    """

    size: int
    source: Literal["native", "basic"] = "basic"
    digest: ContentDigest | None = None
    etag: str | None = None
    version_id: str | None = None
    last_modified: datetime | None = None
    metadata: Mapping[str, str] | None = None
