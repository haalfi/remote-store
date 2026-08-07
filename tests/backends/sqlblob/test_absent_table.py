"""``SQLBlobBackend`` under BE-012/BE-013's absent-container rule.

The table is this backend's container, so a dropped table is the SQL spelling of
a deleted bucket, and the rule binds it like every other flat-namespace backend:
``missing_ok=True`` returns cleanly, ``missing_ok=False`` raises ``NotFound``.

Getting there took three refuted attempts at *exempting* it, which is why the
exemption is gone rather than reworded. Each attempt tried to derive a general
scope criterion, and each was circular or false — the last one keyed on whether
a backend's mapping already turns an absent container into ``NotFound``, which
BE-021's own canonical table requires of every backend anyway. Complying costs
one inspector call on an already-failed statement, so there was nothing left for
a criterion to buy.

Two properties matter and both are pinned here:

* **The tolerance reaches the caller** (``TestAbsentTableReadsAsAbsentPath``).
* **It costs nothing on the miss path** (``TestTheProbeStaysOffTheHotPath``). The
  inspector call hangs off ``SQLAlchemyError``, so an ordinary miss — which
  raises this module's own ``NotFound`` from a query that *succeeded* — never
  reaches it. That bound is what makes the rule's no-extra-round-trip budget
  survive, and asserting the tolerance without asserting the cost would let a
  future simplification move the probe onto every miss and stay green.

``TestContainerExistsByConstruction`` records the constructor's two paths. Worth
pinning because it shapes what a caller can encounter, but note what it does
**not** establish: it does not make the rule vacuous here, since a live instance
can be bound to an absent container by dropping the table under it — which is
exactly what the first class does.

**Coverage bound:** only SQLite runs here. A dropped table raises
``OperationalError`` on SQLite and ``ProgrammingError`` on PostgreSQL and MySQL;
both are ``SQLAlchemyError`` subclasses, so the branch below covers both by
construction, but only the SQLite half is executed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from remote_store._errors import NotFound
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


def _drop_table(backend: SQLBlobBackend) -> None:
    with backend._engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {_TABLE}"))


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "SQL-BLOB-024", "SQL-BLOB-025")
class TestAbsentTableReadsAsAbsentPath:
    """A dropped table is a missing path, not a failed statement."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_returns_cleanly(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        _drop_table(backend)
        assert call(backend) is None, f"{op_name} must tolerate an absent table under missing_ok"

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt")),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_strict_delete_raises_not_found(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """Without ``missing_ok`` the same dropped table is a plain ``NotFound``.

        The tolerance belongs to ``missing_ok``, not to the dropped table: a
        backend that merely stopped raising on the driver error would pass the
        cells above and silently turn a strict delete into a no-op.
        """
        _drop_table(backend)
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob"


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestTheProbeStaysOffTheHotPath:
    """The inspector call is charged to failed statements only, never to a miss."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/absent.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("absent", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_ordinary_miss_never_inspects_the_table(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """An absent *path* on a present table must not spend the extra round trip.

        The contract budgets one probe per miss and forbids paying another to
        tell an absent container from an absent path. This backend honours that
        by hanging the inspection off ``SQLAlchemyError``: an ordinary miss
        raises from a query that succeeded, so the branch is never entered.
        Asserting the call count is the only way to keep that true — the
        tolerance tests above pass just as happily with the probe on every miss.
        """
        with patch.object(
            SQLBlobBackend,
            "_table_is_absent",
            autospec=True,
            side_effect=AssertionError(f"{op_name}: inspected the table on an ordinary miss"),
        ) as probe:
            assert call(backend) is None
        assert probe.call_count == 0


class TestContainerExistsByConstruction:
    """The two constructor paths, recorded for what a caller can encounter."""

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
