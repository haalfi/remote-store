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

Four properties matter and each is pinned here, because the three beyond
tolerance all fail *silently* — a regression in any of them leaves the tolerance
cells green:

* **The tolerance reaches the caller** (``TestAbsentTableReadsAsAbsentPath``).
* **It costs nothing on the miss path** (``TestTheProbeStaysOffTheHotPath``). The
  inspector call hangs off ``SQLAlchemyError``, so an ordinary miss — which
  raises this module's own ``NotFound`` from a query that *succeeded* — never
  reaches it. That bound is what makes the rule's no-extra-round-trip budget
  survive.
* **A real fault is not mistaken for a missing table**
  (``TestTheCatchStaysNarrow``). This is the branch whose failure mode is the
  dangerous one: reporting ``NotFound`` for a database that is broken rather
  than empty. Widening the catch would look exactly like success.
* **The rule holds across its whole condition space**
  (``TestTheReclassificationOverItsWholeConditionSpace``). Ownership x locality
  x lifecycle x table, generated as a product rather than hand-listed. Three
  review rounds each found the reclassification keyed on the wrong condition
  because the reasoning was argued rather than enumerated; the table answers
  the question by exhaustion, and every reachable cell answers the same way.

``TestADiscardedInMemoryStoreReadsAsEmpty`` documents what used to be the one
residue: dispose an in-memory engine and the deletes tolerated while ``read``
raised, because only the deletes carried the reclassification. BUG-246 closed
that asymmetry by extending the reclassification to every operation BE-021
decides, so a discarded store now reads as an *empty* store throughout — which is
what the withdrawn guard was trying to buy. The guard is still worth its
paragraph there: "was the store discarded" is not decidable from configuration,
and every version of the check made behaviour depend on how the caller spelled
the URL.

``TestEveryOperationReadsTheAbsentTableAsAnAbsentPath`` is the per-operation half
of that, split by the answer BE-021 § Reach owes each group, with ``write``
pinned as the one operation no clause decides.

``TestContainerExistsByConstruction`` records the constructor's two paths. Worth
pinning because it shapes what a caller can encounter, but note what it does
**not** establish: it does not make the rule vacuous here, since a live instance
can be bound to an absent container by dropping the table under it — which is
exactly what the first class does.

**How spec marks are scoped in this module**, since ``check_spec_marks.py``
verifies only that a cited ID *exists* and two rounds found marks that fit
nothing. A mark must be exercised by *some* cell in the scope it is attached to:
a class-level mark by at least one of the class's tests, a method-level mark by
at least one of the method's parametrisations. A mark no cell under it exercises
is removed rather than tolerated — which is why the matrix cell dropped
``BE-013`` (it calls only ``delete``) and why ``TestContainerExistsByConstruction``
carries no ``BE-01x`` at all. ``BE-020`` stays on the matrix cell because half
its parametrisations call ``close()``, and on the class below because two of its
three tests do.

**Coverage bound:** only SQLite runs here. A dropped table raises
``OperationalError`` on SQLite and ``ProgrammingError`` on PostgreSQL and MySQL;
both are ``SQLAlchemyError`` subclasses, so the branch below covers both by
construction, but only the SQLite half is executed.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from remote_store._errors import BackendUnavailable, NotFound
from remote_store._path import RemotePath
from remote_store.backends._sqlalchemy import SQLBlobBackend

if TYPE_CHECKING:
    from pathlib import Path

_TABLE = "remote_store_objects"


def _replace_table_with_incompatible_schema(backend: SQLBlobBackend) -> None:
    """Leave a table of that name in place, but one the delete statement cannot use.

    Produces a genuine driver failure with ``has_table`` still answering yes —
    the state the narrowness branch has to tell apart from a dropped table.
    """
    with backend._engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {_TABLE}"))
        conn.execute(sa.text(f"CREATE TABLE {_TABLE} (unrelated TEXT)"))


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


@pytest.mark.spec("BE-021", "SQL-BLOB-050")
class TestTheCatchStaysNarrow:
    """A driver failure on a *live* table keeps its mapping, unreclassified."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_driver_error_with_the_table_present_still_maps(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The failure mode this guards is reporting ``NotFound`` for a broken database.

        Everything else in this module asserts that a ``SQLAlchemyError`` becomes
        a missing path. This asserts the converse — that it does so *only* when
        the table is really gone — which is the half a widened catch would break
        while leaving the tolerance cells green.

        Nothing is mocked: the table is replaced with one that has no ``key``
        column, so the real statement fails with a real ``OperationalError``
        while ``has_table`` truthfully answers yes. That is the exact state the
        branch discriminates on, produced rather than simulated.
        """
        _replace_table_with_incompatible_schema(backend)
        with pytest.raises(BackendUnavailable) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob", op_name

    def test_a_failed_inspection_leaves_the_original_error_standing(self, backend: SQLBlobBackend) -> None:
        """``_table_is_absent`` fails closed, so an unanswerable probe reclassifies nothing.

        The table really is gone here, so the tolerance *would* fire — but the
        inspection cannot run, and the conservative answer keeps the operation's
        own error rather than inventing a verdict from a probe that failed.
        """
        _drop_table(backend)
        with (
            patch(
                "sqlalchemy.inspect",
                side_effect=sa.exc.OperationalError("inspect", {}, Exception("cannot inspect")),
            ),
            pytest.raises(BackendUnavailable),
        ):
            backend.delete("folder/object.txt", missing_ok=True)


@pytest.mark.spec("BE-012", "BE-013", "BE-020", "BE-021")
class TestADiscardedInMemoryStoreReadsAsEmpty:
    """Disposing an in-memory engine leaves an empty store, and every operation says so.

    Recorded because it is the one place the rule produces an answer that reads
    oddly, and because a guard against it shipped briefly and was withdrawn.

    Disposing an in-memory SQLite engine destroys the data, so the next statement
    opens a *different, empty* database. Every operation the contract decides now
    agrees about that — the deletes tolerate, the probes answer ``False``, the
    listings come back empty and the reads raise ``NotFound``. Only the deletes
    did until BUG-246, and the asymmetry that left was never a defect in this
    clause: it was the reclassification reaching two operations instead of
    thirteen.

    The withdrawn guard is worth a sentence, since three review rounds went into
    it. "Was the store discarded" is not decidable from configuration: keyed on
    ``close()`` it broke two live stores, keyed additionally on an in-memory URL
    it still missed the URI-form spellings, and it could never see an owner
    disposing a *borrowed* engine, which touches this object not at all. Each
    version made behaviour depend on URL spelling rather than on the store.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "sqlite:///:memory:",
            "sqlite://",
            "sqlite:///file::memory:?uri=true",
            "sqlite:///file:memdb1?mode=memory&cache=shared&uri=true",
        ],
        ids=["memory", "bare", "uri-anonymous", "uri-named-shared"],
    )
    def test_every_in_memory_spelling_answers_the_same(self, url: str) -> None:
        """All four in-memory spellings, so the answer cannot depend on the URL.

        The withdrawn guard covered the first two and not the last two, which is
        precisely the failure mode: a caller who spells an in-memory database
        the URI way got different delete semantics from one who did not.
        """
        instance = SQLBlobBackend(url)
        try:
            instance.write("folder/object.txt", b"payload")
            instance.close()
            assert instance.delete("folder/object.txt", missing_ok=True) is None
            assert instance.delete_folder("folder", recursive=True, missing_ok=True) is None
        finally:
            # The deletes above reopen a connection on the disposed engine. Close
            # again so the pool releases it here rather than at a GC point, which
            # on 3.13+ surfaces as an unraisable attributed to an unrelated test.
            instance.close()

    def test_a_borrowed_engine_disposed_by_its_owner_answers_the_same(self) -> None:
        """No call reaches this object, so no guard here could ever have seen it.

        The case that showed the detection was not merely incomplete but
        unavailable: the owner disposes the engine directly, and the backend
        learns of it only by failing.
        """
        engine = sa.create_engine("sqlite:///:memory:")
        try:
            instance = SQLBlobBackend(engine=engine)
            instance.write("folder/object.txt", b"payload")
            engine.dispose()
            assert instance.delete("folder/object.txt", missing_ok=True) is None
        finally:
            engine.dispose()

    def test_every_operation_now_agrees_the_store_is_empty(self) -> None:
        """The residue this class documented is gone: the deletes no longer answer alone.

        This cell used to pin the asymmetry — a tolerant delete returning while
        ``read_bytes`` raised ``BackendUnavailable`` — as the visible marker for
        BUG-246. Closing that item is what turns it into its converse, so the
        assertions flip rather than the cell being deleted: a discarded in-memory
        store now reads as an *empty* store from every operation, which is the
        outcome the withdrawn guard was trying to buy and could not.
        """
        instance = SQLBlobBackend("sqlite:///:memory:")
        try:
            instance.write("folder/object.txt", b"payload")
            instance.close()
            assert instance.delete("folder/object.txt", missing_ok=True) is None
            assert instance.exists("folder/object.txt") is False
            assert list(instance.list_files("folder")) == []
            with pytest.raises(NotFound):
                instance.read_bytes("folder/object.txt")
        finally:
            instance.close()


_PROBE_OPS = [
    ("exists", lambda b: b.exists("folder/object.txt")),
    ("exists-folder", lambda b: b.exists("folder")),
    ("is_file", lambda b: b.is_file("folder/object.txt")),
    ("is_folder", lambda b: b.is_folder("folder")),
]

_NOT_FOUND_OPS = [
    ("read", lambda b: b.read("folder/object.txt")),
    ("read_bytes", lambda b: b.read_bytes("folder/object.txt")),
    ("get_file_info", lambda b: b.get_file_info("folder/object.txt")),
    ("get_folder_info", lambda b: b.get_folder_info("folder")),
    ("move", lambda b: b.move("folder/object.txt", "folder/moved.txt")),
    ("copy", lambda b: b.copy("folder/object.txt", "folder/copied.txt")),
    ("move-onto-itself", lambda b: b.move("folder/object.txt", "folder/object.txt")),
    ("copy-onto-itself", lambda b: b.copy("folder/object.txt", "folder/object.txt")),
]

_LISTING_OPS = [
    ("list_files", lambda b: list(b.list_files("folder"))),
    ("list_files-recursive", lambda b: list(b.list_files("", recursive=True))),
    ("list_folders", lambda b: list(b.list_folders("folder"))),
    ("iter_children", lambda b: list(b.iter_children("folder"))),
    ("glob", lambda b: list(b.glob("**/*.txt"))),
]


@pytest.mark.spec("BE-004", "BE-005", "BE-021", "SQL-BLOB-050")
class TestEveryOperationReadsTheAbsentTableAsAnAbsentPath:
    """BE-021 § Reach, operation by operation, against a dropped table.

    The two deletes were brought to the clause by BUG-243 and are covered by
    ``TestAbsentTableReadsAsAbsentPath`` above. This class covers the rest, and
    the split by *answer* is the clause's own: probes answer ``False`` (BE-004,
    BE-005), the file-shaped operations take the canonical ``NotFound`` row, and
    the listings come back empty because an absent container holds nothing.

    Measured before the fix, all of these raised ``BackendUnavailable`` — the
    widest divergence BE-021's § Known divergences recorded, and the reason a
    caller could not tell a store that is *gone* from one that is *broken*.
    """

    @pytest.mark.parametrize(("op_name", "call"), _PROBE_OPS, ids=[n for n, _ in _PROBE_OPS])
    def test_probe_answers_false(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """BE-004 and BE-005 forbid these from raising at all, on any backend."""
        _drop_table(backend)
        assert call(backend) is False, f"{op_name} must answer False against an absent table"

    @pytest.mark.parametrize(("op_name", "call"), _NOT_FOUND_OPS, ids=[n for n, _ in _NOT_FOUND_OPS])
    def test_file_shaped_operation_raises_not_found(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The canonical table's "operation on a non-existent path" row.

        ``move``/``copy`` appear twice because the same-source-and-destination
        branch is a separate code path with its own source check, and a fix
        applied to one body leaves the other raising.
        """
        _drop_table(backend)
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob", op_name

    @pytest.mark.parametrize(("op_name", "call"), _LISTING_OPS, ids=[n for n, _ in _LISTING_OPS])
    def test_listing_comes_back_empty(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """An absent container holds nothing, so the listing is empty rather than an error.

        These are generators, so the suppression has to sit inside the generator
        body: a context manager wrapped around the call that *returns* the
        generator is not entered until the first ``next()``.
        """
        _drop_table(backend)
        assert call(backend) == [], f"{op_name} must yield nothing against an absent table"

    @pytest.mark.spec("BE-029", "BE-021")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_the_root_aggregates_to_empty_rather_than_raising(self, backend: SQLBlobBackend, root: str) -> None:
        """BE-029's root row outranks the canonical ``NotFound`` row, absent table included.

        The root is "a folder that always exists" and ``get_folder_info`` on it
        "aggregates the whole store (never ``NotFound``)" — stated without a
        carve-out for the container being gone. So a store whose table has been
        dropped aggregates to an empty one, which is also what an *empty* table
        answers, and the two agree rather than splitting at the root.

        Both spellings, because BE-029 binds them as the same path and a
        root test keyed on ``""`` alone would miss a backend that only
        short-circuits the one spelling.
        """
        _drop_table(backend)
        info = backend.get_folder_info(root)
        assert info.file_count == 0
        assert info.total_size == 0
        assert info.modified_at is None
        # The path is what makes the two spellings distinguishable at all: the
        # three fields above are spelling-independent, so without this the
        # parametrisation cannot fail in one leg and pass in the other, which is
        # the whole reason the docstring gives for having two legs.
        assert info.path == RemotePath.from_backend_path(root)

    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_the_root_answers_the_same_on_an_empty_table(self, backend: SQLBlobBackend, root: str) -> None:
        """The control: an absent table is indistinguishable from an empty one at the root.

        Compared **field by field, explicitly**. ``FolderInfo.__eq__`` is
        path-only, so ``absent == empty`` would be a tautology here — both sides
        are ``get_folder_info(root)`` for the same root — and would assert
        nothing about the counts this cell exists to compare. An earlier version
        of this cell did exactly that and was weaker than the plain count
        assertion it replaced.
        """
        backend.delete("folder/object.txt")
        empty = backend.get_folder_info(root)
        _drop_table(backend)
        absent = backend.get_folder_info(root)
        assert (absent.path, absent.file_count, absent.total_size, absent.modified_at) == (
            empty.path,
            empty.file_count,
            empty.total_size,
            empty.modified_at,
        ), "an absent table must answer the root exactly as an empty one does"

    @pytest.mark.spec("BE-021")
    def test_write_still_reports_a_backend_failure(self, backend: SQLBlobBackend) -> None:
        """The one operation deliberately left alone, so the omission is visible.

        BE-021 § Reach declines ``write``: no clause of the contract decides what
        a write owes against an absent container, which leaves a backend free to
        answer its own way. Treating a vanished table as a configuration failure
        rather than a missing file is that answer here, and this cell is what
        stops a later sweep "finishing the job" without a spec change.
        """
        _drop_table(backend)
        with pytest.raises(BackendUnavailable):
            backend.write("folder/object.txt", b"payload", overwrite=True)


@pytest.mark.spec("BE-021", "SQL-BLOB-050")
class TestTheWiderCatchStaysNarrow:
    """The narrowness branch, re-asserted on the operations this change reached.

    ``TestTheCatchStaysNarrow`` above covers the two deletes. The reclassification
    sits at seventeen call sites in all — the two deletes plus the fifteen this
    change added — and a widened catch at any one of them reports a *broken*
    database as a missing path, silently, since every cell in the class above
    would stay green.

    The root branch of ``get_folder_info`` is the one that needs saying: it is
    the only site whose tolerance is unconditional rather than keyed on
    ``missing_ok``, so it is the one where a widened catch has nothing else
    holding it back. ``test_a_broken_table_still_raises_at_the_root`` below is
    its cell.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [*_PROBE_OPS, *_NOT_FOUND_OPS, *_LISTING_OPS],
        ids=[n for n, _ in (*_PROBE_OPS, *_NOT_FOUND_OPS, *_LISTING_OPS)],
    )
    def test_driver_error_with_the_table_present_still_maps(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """A real statement failure against a real table, produced rather than mocked."""
        _replace_table_with_incompatible_schema(backend)
        with pytest.raises(BackendUnavailable) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob", op_name

    @pytest.mark.spec("BE-021", "BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_a_broken_table_still_raises_at_the_root(self, backend: SQLBlobBackend, root: str) -> None:
        """The root tolerance is keyed on the table being *absent*, not on any failure.

        ``get_folder_info`` at the root is the one site that tolerates
        unconditionally — every other tolerant site is gated by ``missing_ok`` or
        answers ``False`` — so it is the one where widening the catch has nothing
        else holding it back. A store whose table is *damaged* must still report
        a backend failure rather than aggregating to an empty store, which is the
        answer that would quietly tell a caller their data is gone.
        """
        _replace_table_with_incompatible_schema(backend)
        with pytest.raises(BackendUnavailable) as exc_info:
            backend.get_folder_info(root)
        assert exc_info.value.backend == "sql-blob"


@pytest.mark.spec("BE-021")
class TestTheProbeStaysOffTheHotPathEverywhereElseToo:
    """The no-extra-round-trip budget, on the newly reclassified operations.

    The clause forbids spending a round trip to tell an absent container from an
    absent path, and the tolerance cells pass just as happily with the inspector
    running on every miss. Only a call count keeps the budget honest, and it has
    to be asserted per call site: this change added fifteen of them, and one
    placed outside ``_map_errors`` would inspect on every ordinary miss while
    every other cell in this module stayed green. The eight below are the sites
    reachable with an ordinary miss on a live table; ``read``, ``list_folders``,
    ``glob`` and the four ``move``/``copy`` source sites are not covered here,
    which is a stated bound rather than a claim of completeness.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("exists", lambda b: b.exists("folder/absent.txt")),
            ("is_file", lambda b: b.is_file("folder/absent.txt")),
            ("is_folder", lambda b: b.is_folder("absent")),
            ("read_bytes", lambda b: b.read_bytes("folder/absent.txt")),
            ("get_file_info", lambda b: b.get_file_info("folder/absent.txt")),
            ("get_folder_info", lambda b: b.get_folder_info("absent")),
            ("list_files", lambda b: list(b.list_files("absent"))),
            ("iter_children", lambda b: list(b.iter_children("absent"))),
        ],
        ids=[
            "exists",
            "is_file",
            "is_folder",
            "read_bytes",
            "get_file_info",
            "get_folder_info",
            "list_files",
            "iter_children",
        ],
    )
    def test_ordinary_miss_never_inspects_the_table(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """A miss on a live table raises from a query that *succeeded*, so the branch is never entered."""
        with (
            patch.object(
                SQLBlobBackend,
                "_table_is_absent",
                autospec=True,
                side_effect=AssertionError(f"{op_name}: inspected the table on an ordinary miss"),
            ) as probe,
            contextlib.suppress(NotFound),
        ):
            call(backend)
        assert probe.call_count == 0, op_name


class TestTheReclassificationOverItsWholeConditionSpace:
    """Every reachable state of the reclassification, as a truth table.

    Three review rounds each found this keyed on the wrong condition, and each
    time the fix was argued rather than enumerated — so each time a reviewer
    found a state the argument had not considered. The condition space is small
    and finite, so this closes it by exhaustion instead: ownership (owned /
    borrowed) x locality (in-memory / file) x lifecycle (open / closed) x table
    (present / dropped).

    **Every reachable state answers the same way**, and that uniformity is the
    result rather than a coincidence. Earlier versions carved out a state — the
    discarded in-memory store — and each carve-out was either wrong or
    undetectable; withdrawing it left a rule with no exceptions, which is the
    only shape this table can state exhaustively. A dropped table is tolerated
    under ``missing_ok`` wherever the statement can reach a database at all.

    Two cells are unreachable rather than untested, and saying which matters:
    disposing an owned in-memory engine *is* what discards the table, so
    "closed, owned, in-memory" cannot be paired with either table state
    meaningfully — the store is new and empty whichever was requested. Both are
    covered by ``TestADiscardedInMemoryStoreReadsAsEmpty`` instead, which is
    where the residue and its BUG-246 link are documented.
    """

    @pytest.mark.parametrize("owned", [True, False], ids=["owned", "borrowed"])
    @pytest.mark.parametrize("in_memory", [True, False], ids=["memory", "file"])
    @pytest.mark.parametrize("close_first", [True, False], ids=["closed", "open"])
    @pytest.mark.parametrize("drop_table", [True, False], ids=["dropped", "present"])
    # BE-012 only: this cell exercises ``delete``. ``delete_folder`` (BE-013) is
    # covered over the same axes by the classes above; running the whole product
    # twice would double the cell count to re-assert one shared code path.
    @pytest.mark.spec("BE-012", "BE-020", "BE-021")
    def test_tolerant_delete_over_the_matrix(
        self,
        tmp_path: Path,
        owned: bool,
        in_memory: bool,
        close_first: bool,
        drop_table: bool,
    ) -> None:
        """One operation, every state: ``delete(missing_ok=True)`` on an absent key.

        Parametrised on the axes themselves rather than on a hand-written list
        of tuples, so the product is generated and no coordinate can be omitted
        or mislabelled by hand — an earlier hand-listed version had a row whose
        id disagreed with its coordinates and a guard for a row that was not
        there.
        """
        url = "sqlite:///:memory:" if in_memory else f"sqlite:///{tmp_path / 'matrix.db'}"
        engine = None if owned else sa.create_engine(url)
        backend = SQLBlobBackend(url) if owned else SQLBlobBackend(engine=engine)
        try:
            backend.write("folder/object.txt", b"payload")
            if close_first:
                backend.close()
            if drop_table and not (in_memory and close_first):
                # An in-memory store that has been closed is already empty; there
                # is nothing left to drop, and the DROP would fail on a fresh db.
                _drop_table(backend)
            assert backend.delete("folder/absent.txt", missing_ok=True) is None
        finally:
            backend.close()
            if engine is not None:
                engine.dispose()


class TestContainerExistsByConstruction:
    """The two constructor paths, recorded for what a caller can encounter.

    No BE-012 / BE-013 mark here: neither cell calls a delete. They record how a
    caller reaches the absent-container state at all, which is context for the
    rule rather than a test of it.
    """

    @pytest.mark.spec("SQL-BLOB-010")
    def test_default_creates_the_table(self, backend: SQLBlobBackend) -> None:
        """``create_table=True`` means the container exists the moment the backend does."""
        assert sa.inspect(backend._engine).has_table(_TABLE)

    @pytest.mark.spec("SQL-BLOB-012")
    def test_reflection_refuses_an_absent_table(self, tmp_path: Path) -> None:
        """``create_table=False`` cannot bind to a table that is not there."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        try:
            with pytest.raises(sa.exc.NoSuchTableError):
                SQLBlobBackend(engine=engine, table_name=_TABLE, create_table=False)
        finally:
            engine.dispose()
