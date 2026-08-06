"""Why BE-012/BE-013's absent-container clause is vacuous for ``SQLBlobBackend``.

BUG-243 decided that a tolerant delete treats an absent *container* as an absent
path. On S3 and Azure that rule has teeth, because those backends bind their
container lazily: a typo'd bucket name produces a perfectly constructible
backend whose every call meets a 404.

``SQLBlobBackend`` cannot reach that state. Its container is a table, and the
constructor settles the table's existence before returning — it creates it
(``create_table=True``, the default) or reflects it and refuses to construct
(``create_table=False``). There is no "constructed but bound to nothing", so the
clause has no case to govern here.

The one way to produce a table-less live backend is to drop the table out from
under it, which is a store torn down mid-flight rather than a path that was
never there. BE-021's transport row governs that, and the third test pins it: it
stays ``BackendUnavailable``, and ``missing_ok`` does **not** convert it into a
silent success. That is the substantive half of the decision — the exemption is
asserted, not merely asserted-about-in-prose, so a later change that widens the
tolerance to swallow a dropped table fails here.
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
