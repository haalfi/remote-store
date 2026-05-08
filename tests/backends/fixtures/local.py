"""``local`` fixture: LocalBackend rooted in a per-instance tempdir.

Stage 1, real-local. Carries ``pytest.mark.os_sensitive`` so LocalBackend
conformance is included in macOS/Windows CI runs that filter on that
marker.
"""

from __future__ import annotations

import tempfile

import pytest

from remote_store.backends._local import LocalBackend
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

_meta = load_fixture("local")
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
        factory=_factory,
        capabilities=frozenset(LocalBackend.CAPABILITIES),
        cleanup=_cleanup,
        marks=(pytest.mark.os_sensitive,),
        **_meta.to_kwargs(),
    )
)
