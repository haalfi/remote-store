"""Helpers shared across conformance topic files.

The capability-filter parametrise decorator is the primary gating
mechanism (TEST-005); a fixture lacking a required capability is absent
from the test session entirely. ``_require`` here is retained as a
defensive runtime gate for tests whose finer-grained capability needs
diverge from the class-level filter -- it is a no-op whenever the
parametrise filter already excluded the fixture.

``_skip_flat_namespace`` and the ``_FLAT_NAMESPACE_BACKENDS`` /
``_NO_SELF_OP_BACKENDS`` sets gate on backend identity, not capability.
TEST-005 routes identity-based runtime checks through ``pytest.skip``
inside the test body, not the parametrise filter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability

if TYPE_CHECKING:
    from remote_store._backend import Backend


# Backends with a flat / virtual namespace -- no real directory entries.
# Update this set when adding a new flat-namespace backend.
_FLAT_NAMESPACE_BACKENDS = frozenset({"s3", "s3-pyarrow", "azure", "http", "sql-blob"})

# Backends that do not yet handle self-copy / self-move correctly.
_NO_SELF_OP_BACKENDS = frozenset({"azure", "http"})


def _require(backend: Backend, *caps: Capability) -> None:
    """Skip the test if the backend lacks any of the given capabilities.

    Defensive runtime fallback. Tests should prefer the class-level
    capability filter via ``fixture_params(*caps)`` -- this helper
    only fires when a test inside a coarsely-filtered class needs a
    stricter capability than its siblings.
    """
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")


def _seed(backend: Backend, files: dict[str, bytes]) -> None:
    """Write multiple files into the backend."""
    for path, data in files.items():
        backend.write(path, data)


def _skip_flat_namespace(backend: Backend, reason: str = "flat-namespace backend") -> None:
    """Skip the test for backends without real directory entries.

    Identity-based gate (TEST-005 routes identity checks through
    ``pytest.skip`` rather than the parametrise filter).
    """
    if backend.name in _FLAT_NAMESPACE_BACKENDS:
        pytest.skip(reason)


def _do_op(backend: Backend, op: str, src: str, dst: str, **kw: Any) -> None:
    """Invoke ``backend.<op>(src, dst, **kw)``."""
    getattr(backend, op)(src, dst, **kw)


_MOVE_COPY_PARAMS = [
    pytest.param("move", Capability.MOVE, id="move"),
    pytest.param("copy", Capability.COPY, id="copy"),
]
