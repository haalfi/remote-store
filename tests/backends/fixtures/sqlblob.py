"""``sqlblob`` fixture: SQLBlobBackend over an in-memory SQLite database.

Stage 1, real-local. SQLite is in-process; no Docker or external service
required. The factory skips when SQLAlchemy is not importable, which
happens in installs that omit the ``sql`` extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _make_factory(reject_write_under_file_ancestor: bool):
    def _factory() -> Backend:
        try:
            from remote_store.backends._sqlalchemy import SQLBlobBackend
        except ImportError:
            pytest.skip("sqlalchemy not installed")
        return SQLBlobBackend(
            url="sqlite:///:memory:",
            reject_write_under_file_ancestor=reject_write_under_file_ancestor,
        )

    return _factory


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend
    except ImportError:
        return frozenset()
    return frozenset(SQLBlobBackend.CAPABILITIES)


for _name in ("sqlblob", "sqlblob_strict"):
    _meta = load_fixture(_name)
    register(
        BackendFixture(
            factory=_make_factory(_meta.rejects_write_under_file_ancestor),
            capabilities=_capabilities(),
            cleanup=_cleanup,
            **_meta.to_kwargs(),
        )
    )
