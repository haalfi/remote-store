"""Capability enum and CapabilitySet."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator


class Capability(enum.Enum):
    """Operations a backend may support.

    Each value gates one or more ``Store`` methods.
    Use ``Store.supports()`` to query at runtime.

    Values:

    - ``READ`` -- Stream or bulk-read file content.
      Gates ``Store.read()`` and ``Store.read_bytes()``.
    - ``WRITE`` -- Create or overwrite files.
      Gates ``Store.write()``.
    - ``DELETE`` -- Remove files and folders.
      Gates ``Store.delete()`` and ``Store.delete_folder()``.
    - ``LIST`` -- Enumerate files and subfolders.
      Gates ``Store.list_files()`` and ``Store.list_folders()``.
    - ``MOVE`` -- Rename or relocate a file within the same backend.
      Gates ``Store.move()``.
    - ``COPY`` -- Duplicate a file within the same backend.
      Gates ``Store.copy()``.
    - ``ATOMIC_WRITE`` -- Write via temp-file-and-rename so readers never
      see partial content. Gates ``Store.write_atomic()`` and
      ``Store.open_atomic()``.
    - ``METADATA`` -- Retrieve file or folder metadata.
      Gates ``Store.get_file_info()`` and ``Store.get_folder_info()``.
    - ``GLOB`` -- Native pattern matching against file paths.
      Gates ``Store.glob()``. Not all backends support this -- use
      ``ext.glob.glob_files()`` as a portable fallback.
    - ``SEEKABLE_READ`` -- ``Store.read()`` always returns a seekable
      stream (``stream.seekable()`` is ``True``).  Backends that
      declare this capability return seekable streams from both
      ``read()`` and ``read_seekable()`` with zero overhead.
      Backends without this capability still support
      ``read_seekable()`` via an optimized override or spool fallback.
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
    SEEKABLE_READ = "seekable_read"


class CapabilitySet:
    """Immutable set of capabilities declared by a backend.

    Args:
        capabilities: The set of supported capabilities.
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

        Raises:
            CapabilityNotSupported: If the capability is missing.
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
