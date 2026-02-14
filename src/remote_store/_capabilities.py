"""Capability enum and CapabilitySet."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from remote_store._errors import CapabilityNotSupported

if TYPE_CHECKING:
    from collections.abc import Iterator


class Capability(enum.Enum):
    """Operations a backend may support."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    MOVE = "move"
    COPY = "copy"
    ATOMIC_WRITE = "atomic_write"
    GLOB = "glob"
    RECURSIVE_LIST = "recursive_list"
    METADATA = "metadata"


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
            raise CapabilityNotSupported(
                f"Capability '{cap.value}' is not supported",
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
