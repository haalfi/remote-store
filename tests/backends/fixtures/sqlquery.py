"""``sqlquery`` fixture: SQLQueryBackend over an in-memory SQLite database.

Stage 1, real-local. SQLite is in-process; no Docker or external service
required. The factory skips when SQLAlchemy or PyArrow is not importable,
which happens in installs that omit the ``sql`` / ``sql-query`` extras.

Registered by BK-340. Before it, ``SQLQueryBackend`` had no registry entry, so
**no** conformance cell executed against it — not the capability-gated ones,
not the ungated ones — and every cross-backend invariant was asserted for it by
nobody. That is how BK-324's root-spelling defect survived: a source-wide sweep
found the sites in the reachable backends, and this one was invisible to the
tests and therefore to the sweep.

Empty query mapping
-------------------
The factory registers **no** queries. That is deliberate, not a placeholder.
Every conformance fixture starts from an empty store and several cells assert
the empty-store answer directly (``test_get_folder_info_on_empty_root_does_not_raise``
asserts ``file_count == 0``; ``test_root_is_a_folder``'s docstring names the
empty store as the harder case for a flat namespace). A pre-seeded mapping
would fail them.

Nothing is lost by the choice: the content-bearing cells all seed through
``backend.write`` and are therefore WRITE-gated, so a read-only backend cannot
reach them whatever its starting state. Content-level behaviour (read, glob,
listing with keys registered) is covered per-backend in
``tests/backends/sqlquery/test_config.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("sqlquery")


def _factory() -> Backend:
    try:
        from remote_store.backends._sqlalchemy import SQLQueryBackend
    except ImportError:
        pytest.skip("sqlalchemy not installed")
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow not installed (sql-query extra)")
    # ``url=`` (not ``engine=``) so the backend owns the engine and ``close()``
    # disposes it — the teardown channel ``TestFixtureCleanupContract`` requires
    # of any fixture whose backend overrides ``Backend.close``.
    return SQLQueryBackend(url="sqlite:///:memory:")


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._sqlalchemy import SQLQueryBackend
    except ImportError:
        return frozenset()
    return frozenset(SQLQueryBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
