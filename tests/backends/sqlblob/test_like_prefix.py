"""SQL-BLOB-061: folder prefixes match literally, never as ``LIKE`` patterns (BL-011).

Every seed below differs from a sibling only where ``LIKE`` would generalise:
``_`` (any one character), ``%`` (any run), ASCII case (SQLite's ``LIKE`` folds
it), ``\\`` (the escape character itself) and ``[`` (a character class on SQL
Server only). Each operation that narrows by a folder prefix must see only the
folder it was given.

SQLite's ``LIKE`` has no ``[`` class, so the ``[`` seeds cannot fail on any
database this suite runs: they guard that escaping ``[`` stays harmless here.
What pins the ``[`` escape itself is ``test_escape_like``.
"""

from __future__ import annotations

import itertools
import warnings
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._glob import pattern_to_regex
from remote_store._models import FileInfo
from remote_store._path import RemotePath
from remote_store.backends._sqlalchemy import SQLBlobBackend, _escape_like, _glob_suffix_clause

if TYPE_CHECKING:
    from collections.abc import Iterator

SEEDS = (
    "a_b/x.txt",
    "axb/y.txt",
    "a%/z.txt",
    "aQQ/w.txt",
    "A_B/c.txt",
    "Up/u.txt",
    "up/l.txt",
    "a\\b/s.txt",
    "ab/t.txt",
    "ax/v.txt",  # what an unescaped `\` would reach for the probe `a\x`
    "a[xy]/k.txt",
)


@pytest.fixture
def backend() -> Iterator[SQLBlobBackend]:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    b = SQLBlobBackend(engine=engine)
    for key in SEEDS:
        b.write(key, key.encode())
    yield b
    b.close()
    engine.dispose()


def _keys(b: SQLBlobBackend) -> set[str]:
    """Raw stored keys; ``RemotePath`` would render ``\\`` as ``/``."""
    with b.unwrap(sa.Engine).connect() as conn:
        return {row[0] for row in conn.execute(sa.select(b._table.c.key))}


def _names(items: Iterator[object]) -> set[str]:
    return {item.name for item in items}  # type: ignore[attr-defined]


# Folder -> the only file it holds. Each folder has at least one sibling that a
# metacharacter, case or escape reading of the prefix would also reach on
# SQLite; `bracket` is the exception (see the module docstring).
FOLDERS = [
    pytest.param("a_b", "x.txt", id="underscore"),
    pytest.param("a%", "z.txt", id="percent"),
    pytest.param("Up", "u.txt", id="case"),
    pytest.param("a\\b", "s.txt", id="backslash"),
    pytest.param("a[xy]", "k.txt", id="bracket"),  # SQLite no-op guard; reaches ax/ only on SQL Server
]


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.parametrize(
    ("literal", "escaped"),
    [
        pytest.param("a_b", "a\\_b", id="underscore"),
        pytest.param("a%", "a\\%", id="percent"),
        pytest.param("a\\b", "a\\\\b", id="escape_char_first"),
        # SQL Server reads `[...]` as a character class; escaped, every LIKE reads it literally.
        pytest.param("a[xy]", "a\\[xy]", id="bracket"),
        pytest.param("a\\_[", "a\\\\\\_\\[", id="combined"),
    ],
)
def test_escape_like(literal: str, escaped: str) -> None:
    assert _escape_like(literal) == escaped


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-027")
@pytest.mark.parametrize(("folder", "only"), FOLDERS)
def test_list_files(backend: SQLBlobBackend, folder: str, only: str) -> None:
    assert _names(backend.list_files(folder, recursive=True)) == {only}


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-028")
def test_list_folders(backend: SQLBlobBackend) -> None:
    backend.write("p_q/in/x.txt", b"1")
    backend.write("pXq/out/y.txt", b"1")
    backend.write("P_Q/out2/z.txt", b"1")
    assert _names(backend.list_folders("p_q")) == {"in"}


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.parametrize(("folder", "only"), FOLDERS)
def test_iter_children(backend: SQLBlobBackend, folder: str, only: str) -> None:
    children = list(backend.iter_children(folder))
    assert all(isinstance(c, FileInfo) for c in children)
    assert _names(iter(children)) == {only}


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-030")
@pytest.mark.parametrize(("folder", "only"), FOLDERS)
def test_get_folder_info(backend: SQLBlobBackend, folder: str, only: str) -> None:
    info = backend.get_folder_info(folder)
    assert info.file_count == 1
    assert info.total_size == len(f"{folder}/{only}".encode())


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-026")
@pytest.mark.parametrize("probe", ["aXb", "a_q", "a%%", "UP", "uP", "a\\x"])
def test_folder_probes_reject_lookalikes(backend: SQLBlobBackend, probe: str) -> None:
    """No folder exists at *probe*; only a ``LIKE`` reading finds one."""
    assert backend.is_folder(probe) is False
    assert backend.exists(probe) is False


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-025")
@pytest.mark.parametrize(("folder", "only"), FOLDERS)
def test_delete_folder_recursive_keeps_siblings(backend: SQLBlobBackend, folder: str, only: str) -> None:
    backend.delete_folder(folder, recursive=True)
    assert _keys(backend) == set(SEEDS) - {f"{folder}/{only}"}


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-025")
@pytest.mark.parametrize("probe", ["aXb", "UP", "a\\x"])
def test_delete_folder_on_lookalike_is_not_found(backend: SQLBlobBackend, probe: str) -> None:
    """A sibling's children must not make *probe* a non-empty folder."""
    with pytest.raises(NotFound):
        backend.delete_folder(probe)
    backend.delete_folder(probe, recursive=True, missing_ok=True)
    assert _keys(backend) == set(SEEDS)


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-029")
@pytest.mark.parametrize("probe", ["aXb", "UP"])
def test_wrong_type_probe_ignores_lookalikes(backend: SQLBlobBackend, probe: str) -> None:
    """``get_file_info`` on a missing key is ``NotFound``, not a folder-shaped ``InvalidPath``."""
    with pytest.raises(NotFound) as exc_info:
        backend.get_file_info(probe)
    assert not isinstance(exc_info.value, InvalidPath)


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_non_recursive_still_sees_its_own_children(backend: SQLBlobBackend) -> None:
    """Guard: the narrowed predicate still finds a real folder."""
    with pytest.raises(DirectoryNotEmpty):
        backend.delete_folder("a_b")


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-012")
def test_prefix_follows_the_key_columns_collation() -> None:
    """A user table may declare ``key COLLATE NOCASE``: folder probes must then agree with ``is_file``.

    ``substr(key, ...) = :prefix`` would compare with BINARY, since a function
    result carries no collation, and answer ``is_folder("UP") is False`` while
    ``is_file("UP/X.TXT") is True``.
    """
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE nocase (key TEXT COLLATE NOCASE PRIMARY KEY, data BLOB NOT NULL)"))
    b = SQLBlobBackend(engine=engine, table_name="nocase", create_table=False)
    try:
        b.write("up/x.txt", b"1")
        b.write("upXb/y.txt", b"1")
        assert b.is_file("UP/X.TXT") is True
        assert b.is_folder("UP") is True
        assert [f.name for f in b.list_files("UP")] == ["x.txt"]
        assert b.is_folder("UP_B") is False  # `_` stays literal under NOCASE too
    finally:
        # A leaked connection's ResourceWarning would fail the next test instead.
        b.close()
        engine.dispose()


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.parametrize(("folder", "only"), [p for p in FOLDERS if p.id != "case"])
def test_escape_alone_keeps_metacharacters_literal(backend: SQLBlobBackend, folder: str, only: str) -> None:
    """The branch every non-SQLite dialect takes: escaped ``LIKE``, no ``=`` clause.

    On SQLite the ``=`` clause alone already rejects these siblings, so without
    this cell the escaping is unpinned. Case is left out: off SQLite it is that
    database's ``LIKE`` rule, which no fixture here exercises.
    """
    backend.delete("A_B/c.txt")  # case twin of a_b; SQLite's LIKE would fold it in
    backend._is_sqlite = False
    assert _names(backend.list_files(folder, recursive=True)) == {only}
    backend.delete_folder(folder, recursive=True)
    assert _keys(backend) == set(SEEDS) - {f"{folder}/{only}", "A_B/c.txt"}


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.parametrize("probe", ["a_q", "a%%", "a\\x"])  # no case probes: SQLite's LIKE folds case here
def test_escape_alone_rejects_lookalike_probes(backend: SQLBlobBackend, probe: str) -> None:
    """The non-SQLite branch must not find a folder a metacharacter reading would invent.

    ``a\\x`` is the escape-character probe: unescaped, ``a\\x/%`` reads as
    ``ax/%`` and reaches the seeded ``ax/v.txt``. On SQLite the ``=`` clause
    would reject that by itself, which is why the probe lives on this branch.
    """
    backend._is_sqlite = False
    assert backend.is_folder(probe) is False
    with pytest.raises(NotFound):
        backend.delete_folder(probe)


_TOKENS = ("a", "/", "*", "**", "**/", "?", "[ab]", "[!a]", "[", "]")
_KEY_CHARS = "ab/[]\n"


@pytest.mark.spec("SQL-BLOB-033")
def test_glob_suffix_clause_never_excludes_a_match() -> None:
    """The SQL suffix clause selects a superset of the keys the glob regex accepts.

    The real clause runs against SQLite, so this pins the SQL ``glob()`` issues,
    not a Python model of it. Enumerated rather than sampled: every pattern of
    up to three tokens against every key of up to four characters, so ``**/``
    (which matches zero directories), classes, stray brackets and the trailing
    newline the regex's ``$`` admits meet each other in every order.
    """
    patterns = {"".join(p) for n in range(1, 4) for p in itertools.product(_TOKENS, repeat=n)}
    keys = ["".join(k) for n in range(1, 5) for k in itertools.product(_KEY_CHARS, repeat=n)]
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    table = sa.Table("k", sa.MetaData(), sa.Column("key", sa.Text, primary_key=True))
    table.metadata.create_all(engine)
    misses: list[tuple[str, str]] = []
    with engine.begin() as conn:
        conn.execute(table.insert(), [{"key": k} for k in keys])
        for pattern in sorted(patterns):
            try:
                with warnings.catch_warnings():
                    # "[[ab]" compiles with re's possible-nested-set FutureWarning
                    warnings.simplefilter("ignore", FutureWarning)
                    rx = pattern_to_regex(pattern)
            except ValueError:
                continue  # not a glob pattern_to_regex accepts; glob() raises the same way
            clause = _glob_suffix_clause(table.c.key, pattern)
            if clause is None:
                continue
            selected = {row[0] for row in conn.execute(sa.select(table.c.key).where(clause))}
            misses.extend((pattern, k) for k in keys if rx.match(k) and k not in selected)
    engine.dispose()
    assert misses == []


GLOBS = [
    pytest.param("**/*.csv", {"a.csv", "d/b.csv"}, id="double_star_root"),
    pytest.param("**/a.csv", {"a.csv"}, id="double_star_literal_tail"),
    pytest.param("*.txt", {"t.txt\n"}, id="trailing_newline_admitted_by_regex"),
    pytest.param("*_b/x.txt", {"a_b/x.txt"}, id="underscore_in_tail"),
    pytest.param("*\\b/s.txt", {"a\\b/s.txt"}, id="backslash_in_tail"),
    pytest.param("a_b/*", {"a_b/x.txt"}, id="underscore_literal"),
    pytest.param("[]k]x", {"kx"}, id="bracket_class"),
    pytest.param("Up/*", {"Up/u.txt"}, id="case"),
]


@pytest.mark.spec("SQL-BLOB-061")
@pytest.mark.spec("SQL-BLOB-033")
@pytest.mark.parametrize("sqlite_dialect", [True, False], ids=["sqlite", "other_dialect"])
@pytest.mark.parametrize(("pattern", "expected"), GLOBS)
def test_glob_is_dialect_independent(
    backend: SQLBlobBackend, sqlite_dialect: bool, pattern: str, expected: set[str]
) -> None:
    """The SQL narrowing never drops a key the glob regex would keep, on any dialect branch."""
    for key in ("a.csv", "d/b.csv", "kx", "k]x", "A_B/x.txt", "aXb/x.txt", "t.txt\n"):
        backend.write(key, b"1")
    backend._is_sqlite = sqlite_dialect
    assert {str(f.path) for f in backend.glob(pattern)} == {str(RemotePath(k)) for k in expected}
