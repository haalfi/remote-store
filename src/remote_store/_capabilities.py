"""Capability enum and CapabilitySet."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator


class Capability(enum.Enum):
    """Operations a backend may support.

    Most values gate one or more ``Store`` methods; some are quality
    flags that inform callers about backend behaviour without gating a
    specific method (see ``ATOMIC_MOVE``, ``SEEKABLE_READ``, ``LAZY_READ``).
    Use ``Store.supports()`` to query at runtime.

    Values:

    *Core I/O*

    - ``READ`` -- Stream or bulk-read file content.
      Gates ``Store.read()`` and ``Store.read_bytes()``.
    - ``WRITE`` -- Create or overwrite files.
      Gates ``Store.write()``.
    - ``DELETE`` -- Remove files and folders.
      Gates ``Store.delete()`` and ``Store.delete_folder()``.

    *Navigation*

    - ``LIST`` -- Enumerate files and subfolders.
      Gates ``Store.list_files()`` and ``Store.list_folders()``.
    - ``GLOB`` -- Native pattern matching against file paths.
      Gates ``Store.glob()``. Not all backends support this — use
      ``ext.glob.glob_files()`` as a portable fallback.

    *File operations*

    - ``MOVE`` -- Rename or relocate a file within the same backend.
      Gates ``Store.move()``.
    - ``COPY`` -- Duplicate a file within the same backend.
      Gates ``Store.copy()``.

    *Atomic variants*

    - ``ATOMIC_WRITE`` -- Write via temp-file-and-rename so readers never
      see partial content. Gates ``Store.write_atomic()`` and
      ``Store.open_atomic()``.
    - ``ATOMIC_MOVE`` -- Quality flag: ``move()`` is guaranteed atomic
      under concurrent access (e.g. Local via ``os.rename``, Memory under
      lock, SQL in a transaction). Does **not** gate a method — call
      ``store.supports(Capability.ATOMIC_MOVE)`` before relying on
      atomic rename semantics. Backends that implement move as
      copy-then-delete (e.g. S3, Azure non-HNS) do not declare this
      capability.

    *Metadata*

    - ``METADATA`` -- Retrieve file or folder metadata.
      Gates ``Store.get_file_info()`` and ``Store.get_folder_info()``.
    - ``USER_METADATA`` -- Store user-supplied key/value pairs alongside
      a file. Strict gate on the ``metadata=`` kwarg in
      ``Store.write()``, ``Store.write_text()``, and
      ``Store.write_atomic()``: passing a non-empty mapping to a backend
      that does not declare this capability raises
      ``CapabilityNotSupported`` before any I/O.
      ``metadata=None`` and ``metadata={}`` are always allowed.

    *Quality flags*

    - ``SEEKABLE_READ`` -- ``Store.read()`` always returns a seekable
      stream (``stream.seekable()`` is ``True``).  Backends that
      declare this capability return seekable streams from both
      ``read()`` and ``read_seekable()`` with zero overhead.
      Backends without this capability still support
      ``read_seekable()`` via an optimized override or spool fallback.
    - ``LAZY_READ`` -- ``read()`` fetches data lazily on demand from the
      native source rather than loading the entire file into memory before
      returning.  Backends that pre-load the full file contents (e.g.
      in-memory backends, SQL blob stores) do **not** declare this flag.
      Callers can use ``store.supports(Capability.LAZY_READ)`` to know
      whether partial reads avoid loading the entire file.
      See also: spec SIO-009 in ``sdd/specs/006-streaming-io.md``.
    - ``WRITE_RESULT_NATIVE`` -- Quality flag: the backend populates the
      rich fields of the returned ``WriteResult`` (``etag``,
      ``last_modified``, ``version_id``, and where applicable
      ``digest``) directly from its write response.  Does **not** gate
      any method — ``Store.write*()`` works on every backend.
      Backends without this flag return a ``WriteResult`` with only
      ``path`` and ``size`` populated (``source == "basic"``).
      Use ``store.supports(Capability.WRITE_RESULT_NATIVE)`` to decide
      whether to call ``Store.head()`` after a write if you need the
      full metadata set.
    """

    # Core I/O
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    # Navigation
    LIST = "list"
    GLOB = "glob"
    # File operations
    MOVE = "move"
    COPY = "copy"
    # Atomic variants
    ATOMIC_WRITE = "atomic_write"
    ATOMIC_MOVE = "atomic_move"
    # Metadata
    METADATA = "metadata"
    USER_METADATA = "user_metadata"
    # Quality flags
    SEEKABLE_READ = "seekable_read"
    LAZY_READ = "lazy_read"
    WRITE_RESULT_NATIVE = "write_result_native"


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
