"""ResolutionPlan — frozen introspection result for key-to-location resolution."""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolutionPlan:
    """Describes how a key maps to its storage location.

    Returned by ``Backend.resolve()`` and ``Store.resolve()``. The plan
    captures the resolution strategy, backend identity, resolved key,
    native path, and backend-specific context -- all without performing
    any I/O.

    ``details`` is wrapped in ``types.MappingProxyType`` via
    ``__post_init__`` to prevent accidental mutation at runtime.

    Args:
        kind: Resolution strategy identifier (e.g. ``"local"``,
            ``"s3"``, ``"azure"``).
        backend: Human-readable backend identifier (typically
            ``Backend.name``).
        key: The resolved key (store-relative after
            ``Store.resolve()``, backend-relative after
            ``Backend.resolve()``).
        native_path: Backend-native location string (same as
            ``Backend.native_path()`` output).
        details: Backend-specific resolution context.  Immutable at
            runtime.  Values should be JSON-serializable primitives.
    """

    kind: str
    backend: str
    key: str
    native_path: str
    details: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", types.MappingProxyType(self.details))
