"""Why BE-012/BE-013's absent-container clause exempts ``SQLBlobBackend``.

The clause says a tolerant delete treats an absent *container* as an absent
path, and it binds backends whose response already carries the fact that the
container is gone — S3's ``NoSuchBucket``, Azure's ``ContainerNotFound``. That
is what makes tolerating free, and the clause forbids paying a round trip to
learn it.

A dropped table gives ``SQLBlobBackend`` no such signal: it arrives as a
dialect-specific ``OperationalError`` / ``ProgrammingError`` with no portable
code, so telling it from any other database failure needs an extra ``has_table``
inspection — the round trip the clause forbids. Hence the exemption, and
``TestDroppedTableIsNotAMissingPath`` pins what it means: ``BackendUnavailable``
stands, and ``missing_ok`` does **not** convert it into a silent success. A
later change that widens the tolerance to swallow a dropped table fails there.

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

from remote_store._errors import BackendUnavailable
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
    """A table dropped mid-life is a torn-down store, and ``missing_ok`` does not cover it."""

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
        with backend._engine.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE {_TABLE}"))
        with pytest.raises(BackendUnavailable) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob"
