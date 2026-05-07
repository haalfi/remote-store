"""``local`` fixture: LocalBackend rooted in a per-instance tempdir.

Stage 1, real-local. Carries ``pytest.mark.os_sensitive`` so LocalBackend
conformance is included in macOS/Windows CI runs that filter on that
marker.
"""

from __future__ import annotations

import tempfile

import pytest

from remote_store.backends._local import LocalBackend
from tests.backends.fixtures.registry import BackendFixture, register

_TMPDIRS: dict[int, tempfile.TemporaryDirectory[str]] = {}


def _factory() -> LocalBackend:
    tmp = tempfile.TemporaryDirectory()
    backend = LocalBackend(root=tmp.name)
    _TMPDIRS[id(backend)] = tmp
    return backend


def _cleanup(backend: LocalBackend) -> None:
    tmp = _TMPDIRS.pop(id(backend), None)
    if tmp is not None:
        tmp.cleanup()


register(
    BackendFixture(
        name="local",
        backend="local",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(LocalBackend.CAPABILITIES),
        is_async=False,
        cleanup=_cleanup,
        marks=(pytest.mark.os_sensitive,),
    )
)
