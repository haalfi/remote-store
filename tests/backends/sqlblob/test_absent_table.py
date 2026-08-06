"""Why BE-012/BE-013's absent-container clause exempts ``SQLBlobBackend``.

The clause says a tolerant delete treats an absent *container* as an absent
path, and it binds a backend whose error mapping already turns an absent
container into the ``NotFound`` family — the family ``missing_ok`` exists to
swallow. Tolerating is then free, and the clause forbids paying a probe to buy
it any other way.

A dropped table lands outside that family. Per SQL-BLOB-050 an
``OperationalError`` maps to ``BackendUnavailable`` and every other
``SQLAlchemyError`` to the base error, and which of the two a dropped table
raises is dialect-specific — SQLite says ``OperationalError`` ("no such table"),
PostgreSQL and MySQL say ``ProgrammingError``. Hence the exemption, and it does
not depend on which one you get: ``missing_ok`` never sees either.

``TestDroppedTableIsNotAMissingPath`` therefore asserts the dialect-independent
property the spec actually claims — the call raises, and what it raises is not a
``NotFound`` that ``missing_ok`` would have swallowed — rather than pinning
SQLite's concrete ``BackendUnavailable``, which would have looked like a
cross-dialect guarantee while testing one dialect. **Coverage bound:** only
SQLite runs here; the ``ProgrammingError`` path on PostgreSQL and MySQL is
argued from SQL-BLOB-050's table, not executed.

``TestContainerExistsByConstruction`` records the *other* fact about this
backend — that the constructor settles the table's existence, creating it
(``create_table=True``) or reflecting it and refusing to construct
(``create_table=False``). Worth pinning because it shapes what a caller can
encounter, but note what it does **not** establish: it does not make the clause
vacuous here. A live instance can be bound to an absent container, which is
precisely what the second class constructs. Nor does "torn down mid-flight
rather than never there" justify the exemption — an S3 bucket deleted under a
running backend is torn down mid-flight too, and the clause tolerates it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

from remote_store._errors import BackendUnavailable, NotFound, RemoteStoreError
from remote_store.backends._sqlalchemy import SQLBlobBackend

if TYPE_CHECKING:
    from pathlib import Path

_TABLE = "remote_store_objects"


@pytest.fixture
def backend(tmp_path: Path):  # noqa: ANN201 -- yields SQLBlobBackend
    """A file-backed SQLBlob store holding one key."""
    instance = SQLBlobBackend(f"sqlite:///{tmp_path / 'store.db'}")
    instance.write("folder/object.txt", b"payload")
    try:
        yield instance
    finally:
        instance.close()


class TestContainerExistsByConstruction:
    """The two constructor paths, which together leave no absent-container case."""

    @pytest.mark.spec("BE-012", "BE-013", "SQL-BLOB-010")
    def test_default_creates_the_table(self, backend: SQLBlobBackend) -> None:
        """``create_table=True`` means the container exists the moment the backend does."""
        assert sa.inspect(backend._engine).has_table(_TABLE)

    @pytest.mark.spec("BE-012", "BE-013", "SQL-BLOB-012")
    def test_reflection_refuses_an_absent_table(self, tmp_path: Path) -> None:
        """``create_table=False`` cannot bind to a table that is not there."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        try:
            with pytest.raises(sa.exc.NoSuchTableError):
                SQLBlobBackend(engine=engine, table_name=_TABLE, create_table=False)
        finally:
            engine.dispose()


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "SQL-BLOB-050")
class TestDroppedTableIsNotAMissingPath:
    """An absent table lands outside `NotFound`, so ``missing_ok`` cannot swallow it."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_still_reports_the_dropped_table(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """Raises, and not with the one error class ``missing_ok`` would have absorbed.

        Asserting ``not NotFound`` rather than the concrete ``BackendUnavailable``
        is deliberate: that is the property the exemption rests on, and it is the
        one that survives the dialect split (see the module docstring). Pinning
        SQLite's concrete class here would read as a cross-dialect guarantee this
        suite does not test.
        """
        with backend._engine.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE {_TABLE}"))
        with pytest.raises(RemoteStoreError) as exc_info:
            call(backend)
        assert not isinstance(exc_info.value, NotFound), (
            f"{op_name}: an absent table must not reach missing_ok's NotFound branch"
        )
        # SQLite raises OperationalError, so this instance lands on
        # BackendUnavailable; other dialects may land on the base error.
        assert isinstance(exc_info.value, BackendUnavailable)
        assert exc_info.value.backend == "sql-blob"
