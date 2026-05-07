"""Async ``local`` fixture: SyncBackendAdapter wrapping LocalBackend.

Stage 1, real-local, ``is_async=True``. Carries
``pytest.mark.os_sensitive`` because the underlying LocalBackend
exercises real filesystem semantics.

The fixture creates a per-instance tempdir for the LocalBackend root
and tears it down on cleanup. Test pollution between parametrize
iterations is impossible because each ``factory()`` call returns a
fresh adapter wrapping a fresh LocalBackend over its own tempdir.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

import pytest

from remote_store.aio import SyncBackendAdapter
from remote_store.backends._local import LocalBackend
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_TMPDIRS: dict[int, tempfile.TemporaryDirectory[str]] = {}


def _factory() -> AsyncBackend:
    tmp = tempfile.TemporaryDirectory()
    inner = LocalBackend(root=tmp.name)
    adapter = SyncBackendAdapter(inner)
    _TMPDIRS[id(adapter)] = tmp
    return adapter


def _cleanup(backend: AsyncBackend) -> None:
    tmp = _TMPDIRS.pop(id(backend), None)
    if tmp is not None:
        tmp.cleanup()


register(
    BackendFixture(
        name="local_async_adapted",
        backend="local",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(LocalBackend.CAPABILITIES),
        is_async=True,
        cleanup=_cleanup,
        marks=(pytest.mark.os_sensitive,),
    )
)
