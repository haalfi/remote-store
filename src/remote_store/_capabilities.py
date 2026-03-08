"""Capability enum and CapabilitySet."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator


class Capability(enum.Enum):
    """Operations a backend may support.

    Each value gates one or more :class:`~remote_store.Store` methods.
    Use :meth:`Store.supports` to query at runtime.

    .. attribute:: READ

       Stream or bulk-read file content.
       Gates :meth:`~remote_store.Store.read` and
       :meth:`~remote_store.Store.read_bytes`.

    .. attribute:: WRITE

       Create or overwrite files.
       Gates :meth:`~remote_store.Store.write`.

    .. attribute:: DELETE

       Remove files and folders.
       Gates :meth:`~remote_store.Store.delete` and
       :meth:`~remote_store.Store.delete_folder`.

    .. attribute:: LIST

       Enumerate files and subfolders.
       Gates :meth:`~remote_store.Store.list_files` and
       :meth:`~remote_store.Store.list_folders`.

    .. attribute:: MOVE

       Rename or relocate a file within the same backend.
       Gates :meth:`~remote_store.Store.move`.

    .. attribute:: COPY

       Duplicate a file within the same backend.
       Gates :meth:`~remote_store.Store.copy`.

    .. attribute:: ATOMIC_WRITE

       Write via temp-file-and-rename so readers never see partial content.
       Gates :meth:`~remote_store.Store.write_atomic` and
       :meth:`~remote_store.Store.open_atomic`.

    .. attribute:: METADATA

       Retrieve file or folder metadata.
       Gates :meth:`~remote_store.Store.get_file_info` and
       :meth:`~remote_store.Store.get_folder_info`.

    .. attribute:: GLOB

       Native pattern matching against file paths.
       Gates :meth:`~remote_store.Store.glob`.
       Not all backends support this -- use
       :func:`~remote_store.ext.glob.glob_files` as a portable fallback.
    """

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    MOVE = "move"
    COPY = "copy"
    ATOMIC_WRITE = "atomic_write"
    METADATA = "metadata"
    GLOB = "glob"


class CapabilitySet:
    """Immutable set of capabilities declared by a backend.

    :param capabilities: The set of supported capabilities.
    """

    __slots__ = ("_caps",)
    _caps: frozenset[Capability]

    def __init__(self, capabilities: set[Capability]) -> None:
        object.__setattr__(self, "_caps", frozenset(capabilities))

    def supports(self, cap: Capability) -> bool:
        """Check whether a capability is supported."""
        return cap in self._caps

    def require(self, cap: Capability, *, backend: str = "") -> None:
        """Raise if a capability is not supported.

        :raises CapabilityNotSupported: If the capability is missing.
        """
        if cap not in self._caps:
            supported = sorted(c.value for c in self._caps)
            raise CapabilityNotSupported(
                f"Capability '{cap.value}' is not supported. Supported: {supported}",
                capability=cap.value,
                backend=backend or None,
            )

    def __contains__(self, cap: object) -> bool:
        return cap in self._caps

    def __iter__(self) -> Iterator[Capability]:
        return iter(self._caps)

    def __len__(self) -> int:
        return len(self._caps)

    def __repr__(self) -> str:
        names = sorted(c.name for c in self._caps)
        return f"CapabilitySet({{{', '.join(names)}}})"

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("CapabilitySet is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CapabilitySet is immutable")
