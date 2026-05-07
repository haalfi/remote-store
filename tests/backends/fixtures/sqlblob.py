"""``sqlblob`` fixture: SQLBlobBackend over an in-memory SQLite database.

Stage 1, real-local. SQLite is in-process; no Docker or external service
required. The factory skips when SQLAlchemy is not importable, which
happens in installs that omit the ``sql`` extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _factory() -> Backend:
    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend
    except ImportError:
        pytest.skip("sqlalchemy not installed")
    return SQLBlobBackend(url="sqlite:///:memory:")


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend
    except ImportError:
        return frozenset()
    return frozenset(SQLBlobBackend.CAPABILITIES)


register(
    BackendFixture(
        name="sqlblob",
        backend="sqlblob",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
    )
)
