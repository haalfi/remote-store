"""What a key resolves to, as every keyed kernel call answers it (BE-032 A.5), in both runtimes.

The first of A.10's two generated suites: tree state × key × family. Each
cell builds a store that decodes to a tree, so every driver call answers
truthfully and nothing is injected; calls one operation of one family on one
key; and requires A.5's cell for the row that key resolves to:

- ``Item``;
- ``Folder``: holding a file, and where folder objects exist (A.6) also
  empty and holding only an empty folder;
- ``Nothing``: at the top level, and below a folder that is not there;
- ``Nothing`` with the path through an item, one and two levels down.

Every driver shape the kernel constructs over is crossed: ``namespace`` ×
``parents`` (flat with folder objects is refused at construction, which
``test_condition_space.py`` checks), and per family the optional protocols
that choose its route. The families and their operations are A.5's first
table. The oracle reads only the cell's row and A.5's second table.

A.3's stated flat limit, that keyed and folder families trust a flat
encoding instead of answering A.5's last row, changes no cell here: over a
store that decodes to a tree nothing lies below an item, so a flat ``stat``
and listing of ``f/x`` see nothing, which is that row's answer anyway. The
raw states where the limit shows are ``test_encoding_observations.py``'s.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from tests._kernel._cells import (
    DRIVERS,
    Cell,
    Expected,
    ancestors,
    base_protocols,
    contents,
    disagreeing,
    report,
    settle,
)
from tests._kernel._fake import RUNTIMES, FakeStore, keys_of, make_kernel

if TYPE_CHECKING:
    from collections.abc import Callable

ITEM, FOLDER, NOTHING, THROUGH = "Item", "Folder", "Nothing", "Nothing, path through an item"

# state -> (the key, a transfer's source key in the same state, the A.5 row it resolves to)
STATES: dict[str, tuple[str, str, str]] = {
    "item": ("f", "s", ITEM),
    "folder": ("d", "e", FOLDER),
    "folder-of-empty": ("h", "u", FOLDER),
    "empty": ("z", "y", FOLDER),
    "nothing": ("n", "m", NOTHING),
    "nothing-deep": ("n/q", "m/q", NOTHING),
    "through": ("f/x", "s/x", THROUGH),
    "through-deep": ("f/x/y", "s/x/y", THROUGH),
}
OBJECTS_ONLY = ("folder-of-empty", "empty")  # an empty folder exists only with folder objects (A.6)
HOLDS_ENTRIES = ("folder", "folder-of-empty")


def _tree(parents: str) -> FakeStore:
    store = FakeStore(parents=parents)
    store.add("f", data=b"F").add("s", data=b"S").add("d/x", data=b"X").add("d/s/t", data=b"T").add("e/z", data=b"Z")
    if parents != "none":
        store.add("z/", "y/", "h/i/", "u/v/")
    return store


def _states(driver: str) -> list[str]:
    parents = DRIVERS[driver][1]
    return [s for s in STATES if parents != "none" or s not in OBJECTS_ONLY]


def _failures(cells: list[Cell]) -> list[str]:
    """Each cell of a family that disagrees with A.5; a family must generate cells."""
    return disagreeing(cells)


# ---------------------------------------------------------------------------
# probe: exists, is_file, is_folder
# ---------------------------------------------------------------------------

PROBES: dict[str, Callable[[Any, str], Any]] = {
    "exists": lambda r, k: r.exists(k),
    "is_file": lambda r, k: r.is_file(k),
    "is_folder": lambda r, k: r.is_folder(k),
}
# A.5: T / T / F, T / F / T, F / F / F, F / F / F
PROBE_ROWS: dict[str, dict[str, bool]] = {
    ITEM: {"exists": True, "is_file": True, "is_folder": False},
    FOLDER: {"exists": True, "is_file": False, "is_folder": True},
    NOTHING: {"exists": False, "is_file": False, "is_folder": False},
    THROUGH: {"exists": False, "is_file": False, "is_folder": False},
}


def _check_probe(runtime: str, call: str, driver: str, state: str) -> None:
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents))
    before = contents(store)
    got, err, value = settle(lambda: PROBES[call](run, key))
    assert got == "ok", err
    assert value is PROBE_ROWS[row][call]
    assert contents(store) == before


@pytest.mark.spec("BE-004")
@pytest.mark.spec("BE-005")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_probe_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{driver}-{state}", functools.partial(_check_probe, runtime, call, driver, state))
        for call in PROBES
        for driver in DRIVERS
        for state in _states(driver)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# read-file: read, read_bytes, read_seekable, get_file_info
# ---------------------------------------------------------------------------


def _read_seekable(run: Any, key: str) -> bytes:
    with run.kernel.read_seekable(key) as stream:
        return bytes(stream.read())


def _file_info(run: Any, key: str) -> tuple[str, int]:
    info = run.get_file_info(key)
    return str(info.path), info.size


# call -> (call, protocols, sync only, the item's answer)
READS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...], bool, Any]] = {
    "read": (lambda r, k: r.read(k), (), False, b"F"),
    "read_bytes": (lambda r, k: r.read_bytes(k), (), False, b"F"),
    "read_seekable-range": (_read_seekable, ("range",), True, b"F"),
    "read_seekable-spool": (_read_seekable, (), True, b"F"),
    "get_file_info": (_file_info, (), False, ("f", 1)),
}
READ_ROWS: dict[str, Expected] = {ITEM: "ok", FOLDER: InvalidPath, NOTHING: NotFound, THROUGH: NotFound}


def _check_read(runtime: str, call: str, driver: str, state: str) -> None:
    fn, protocols, _, item = READS[call]
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols)
    before = contents(store)
    got, err, value = settle(lambda: fn(run, key))
    assert got == READ_ROWS[row], err
    if err is None:
        assert value == item
    else:
        assert err.path == key
    assert contents(store) == before


@pytest.mark.spec("BE-006")
@pytest.mark.spec("BE-007")
@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-016")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_read_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{driver}-{state}", functools.partial(_check_read, runtime, call, driver, state))
        for call, (_, _, sync_only, _) in READS.items()
        if runtime == "sync" or not sync_only
        for driver in DRIVERS
        for state in _states(driver)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# write-file: write, write_atomic and open_atomic, by every route
# ---------------------------------------------------------------------------


def _open_atomic(run: Any, key: str, overwrite: bool) -> None:
    with run.kernel.open_atomic(key, overwrite=overwrite) as stream:
        stream.write(b"N")


# route -> (call, protocols, put_is_atomic, sync only)
WRITES: dict[str, tuple[Callable[[Any, str, bool], Any], tuple[str, ...], bool, bool]] = {
    "write": (lambda r, k, o: r.write(k, b"N", overwrite=o), (), False, False),
    "write_atomic-put": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), (), True, False),
    "write_atomic-handle": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), ("open_write",), False, False),
    "write_atomic-rename": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), ("rename",), False, False),
    "open_atomic-handle": (_open_atomic, ("open_write",), False, True),
    "open_atomic-spool-put": (_open_atomic, (), True, True),
    "open_atomic-spool-rename": (_open_atomic, ("rename",), False, True),
}


def _write_row(row: str, overwrite: bool) -> Expected:
    """A.5: replaced, or AlreadyExists without overwrite; InvalidPath; written, parents created; InvalidPath."""
    return {
        ITEM: "ok" if overwrite else AlreadyExists,
        FOLDER: InvalidPath,
        NOTHING: "ok",
        THROUGH: InvalidPath,
    }[row]


def _check_write(runtime: str, route: str, driver: str, state: str, overwrite: bool) -> None:
    call, protocols, put_is_atomic, _ = WRITES[route]
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols, put_is_atomic=put_is_atomic
    )
    before = contents(store)
    got, err, _ = settle(lambda: call(run, key, overwrite))
    assert got == _write_row(row, overwrite), err
    if err is None:
        after = contents(store)
        assert after[key] == b"N"
        assert {k: v for k, v in after.items() if k != key} == {k: v for k, v in before.items() if k != key}
        assert all(run.is_folder(a) for a in ancestors(key)), "a written key's parents exist"
    else:
        assert err.path == key
        assert contents(store) == before  # nothing written, no temporary left
    assert all(h.state != "open" for h in store.handles)  # type: ignore[attr-defined]


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-009")
@pytest.mark.spec("BE-010")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_write_answers_its_rows_column_by_every_route(runtime: str) -> None:
    cells = [
        (
            f"{route}-{driver}-{state}-ow{int(overwrite)}",
            functools.partial(_check_write, runtime, route, driver, state, overwrite),
        )
        for route, (_, _, _, sync_only) in WRITES.items()
        if runtime == "sync" or not sync_only
        for driver in DRIVERS
        for state in _states(driver)
        for overwrite in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# delete-file: delete, with and without missing_ok
# ---------------------------------------------------------------------------


def _check_delete(runtime: str, driver: str, state: str, missing_ok: bool) -> None:
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents))
    before = contents(store)
    # A.5: removed; InvalidPath, which outranks missing_ok (BE-021); NotFound, which missing_ok turns into success.
    want: Expected = {ITEM: "ok", FOLDER: InvalidPath}.get(row, "ok" if missing_ok else NotFound)
    got, err, _ = settle(lambda: run.delete(key, missing_ok=missing_ok))
    assert got == want, err
    if err is not None:
        assert err.path == key
    removed = {key} if row == ITEM else set()
    assert contents(store) == {k: v for k, v in before.items() if k not in removed}


@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_delete_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (
            f"delete-{driver}-{state}-m{int(missing_ok)}",
            functools.partial(_check_delete, runtime, driver, state, missing_ok),
        )
        for driver in DRIVERS
        for state in _states(driver)
        for missing_ok in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# folder-read: the listings, get_folder_info by listing and by push-down, glob
# ---------------------------------------------------------------------------


def _aggregate(run: Any, key: str) -> tuple[int, int]:
    info = run.get_folder_info(key)
    return info.file_count, info.total_size


# call -> (call, protocols)
LISTINGS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...]]] = {
    "list_files": (lambda r, k: keys_of(r.list_files(k)), ()),
    "list_files-recursive": (lambda r, k: keys_of(r.list_files(k, recursive=True)), ()),
    "list_folders": (lambda r, k: keys_of(r.list_folders(k)), ()),
    "iter_children": (lambda r, k: keys_of(r.iter_children(k)), ()),
    "get_folder_info-listing": (_aggregate, ()),
    "get_folder_info-push_down": (_aggregate, ("folder_stats",)),
    # Over its pattern's literal prefix: one-character names directly below the key.
    "glob": (lambda r, k: keys_of(r.glob(f"{k}/?")), ("glob",)),
}
# A.5's "its children", per folder state; an aggregate is (file_count, total_size).
CHILDREN: dict[str, dict[str, Any]] = {
    "folder": {
        "list_files": ["d/x"],
        "list_files-recursive": ["d/s/t", "d/x"],
        "list_folders": ["d/s"],
        "iter_children": ["d/s", "d/x"],
        "aggregate": (2, 2),
        "glob": ["d/x"],
    },
    "folder-of-empty": {
        "list_files": [],
        "list_files-recursive": [],
        "list_folders": ["h/i"],
        "iter_children": ["h/i"],
        "aggregate": (0, 0),
        "glob": [],
    },
    "empty": {
        "list_files": [],
        "list_files-recursive": [],
        "list_folders": [],
        "iter_children": [],
        "aggregate": (0, 0),
        "glob": [],
    },
}


def _listing_row(call: str, state: str, row: str) -> tuple[Expected, Any]:
    """A.5: an item and nothing hold nothing; a folder its children. BE-017 types an empty aggregate."""
    aggregate = call.startswith("get_folder_info")
    if row == FOLDER:
        return "ok", CHILDREN[state]["aggregate" if aggregate else call]
    if not aggregate:
        return "ok", []
    return (InvalidPath if row == ITEM else NotFound), None


def _check_listing(runtime: str, call: str, driver: str, state: str) -> None:
    fn, protocols = LISTINGS[call]
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols)
    before = contents(store)
    want, value = _listing_row(call, state, row)
    got, err, listed = settle(lambda: fn(run, key))
    assert got == want, err
    if err is None:
        assert listed == value
    else:
        assert err.path == key
    assert contents(store) == before


@pytest.mark.spec("BE-014")
@pytest.mark.spec("BE-015")
@pytest.mark.spec("BE-017")
@pytest.mark.spec("BE-024")
@pytest.mark.spec("BE-026")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_read_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{driver}-{state}", functools.partial(_check_listing, runtime, call, driver, state))
        for call in LISTINGS
        for driver in DRIVERS
        for state in _states(driver)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# delete-folder: recursive or not, with and without delete_tree and missing_ok
# ---------------------------------------------------------------------------


def _check_delete_folder(runtime: str, driver: str, state: str, recursive: bool, tree: bool, missing_ok: bool) -> None:
    namespace, parents = DRIVERS[driver]
    key, _, row = STATES[state]
    store = _tree(parents)
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=base_protocols(parents) + (("delete_tree",) if tree else ())
    )
    before, folders_before = contents(store), set(store.folders)
    # A.5: InvalidPath; removed, or DirectoryNotEmpty; NotFound, which missing_ok turns into success.
    if row == ITEM:
        want: Expected = InvalidPath
    elif row == FOLDER:
        want = DirectoryNotEmpty if not recursive and state in HOLDS_ENTRIES else "ok"
    else:
        want = "ok" if missing_ok else NotFound
    got, err, _ = settle(lambda: run.delete_folder(key, recursive=recursive, missing_ok=missing_ok))
    assert got == want, err
    if got == "ok" and row == FOLDER:
        below = key + "/"
        assert contents(store) == {k: v for k, v in before.items() if not k.startswith(below)}
        assert not run.exists(key)
        return
    if err is not None:
        assert err.path == key
    assert contents(store) == before
    assert store.folders == folders_before


@pytest.mark.spec("BE-013")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_delete_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (
            f"delete_folder-{driver}-{state}-r{int(recursive)}-t{int(tree)}-m{int(missing_ok)}",
            functools.partial(_check_delete_folder, runtime, driver, state, recursive, tree, missing_ok),
        )
        for driver in DRIVERS
        for state in _states(driver)
        for recursive in (False, True)
        for tree in (False, True)
        for missing_ok in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# transfer: move and copy by every route, the source and the destination each in every state
# ---------------------------------------------------------------------------

# route -> (op, protocols, rename_replaces)
TRANSFERS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "move-atomic": ("move", ("atomic_move",), True),
    "move-rename": ("move", ("rename",), True),
    "move-displace": ("move", ("rename",), False),
    "move-copy-delete": ("move", ("copy",), True),
    "copy": ("copy", ("copy",), True),
}


def _transfer_row(src_row: str, dst_row: str, overwrite: bool) -> tuple[Expected, str | None]:
    """A.5's transfer: the source as read-file, then the destination as write-file (BE-018's order).

    The second value names the key the error carries: ``"src"`` or ``"dst"``.
    """
    if src_row != ITEM:
        return READ_ROWS[src_row], "src"
    want = _write_row(dst_row, overwrite)
    return want, (None if want == "ok" else "dst")


def _check_transfer(runtime: str, route: str, driver: str, src_state: str, dst_state: str, overwrite: bool) -> None:
    op, protocols, rename_replaces = TRANSFERS[route]
    namespace, parents = DRIVERS[driver]
    _, src, src_row = STATES[src_state]
    dst, _, dst_row = STATES[dst_state]
    store = _tree(parents)
    run = make_kernel(
        runtime,
        store,
        namespace=namespace,
        protocols=base_protocols(parents) + protocols,
        rename_replaces=rename_replaces,
    )
    before = contents(store)
    want, names = _transfer_row(src_row, dst_row, overwrite)
    got, err, _ = settle(lambda: getattr(run, op)(src, dst, overwrite=overwrite))
    assert got == want, err
    if err is None:
        after = contents(store)
        assert after[dst] == b"S"
        assert ("s" in after) == (op == "copy")
        untouched = ("s", dst)
        assert {k: v for k, v in after.items() if k not in untouched} == {
            k: v for k, v in before.items() if k not in untouched
        }  # nothing parked or left behind
        assert all(run.is_folder(a) for a in ancestors(dst)), "a written key's parents exist"
    else:
        assert err.path == (src if names == "src" else dst)
        assert contents(store) == before


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_transfer_answers_its_rows_columns_by_every_route(runtime: str) -> None:
    cells = [
        (
            f"{route}-{driver}-src_{src}-dst_{dst}-ow{int(overwrite)}",
            functools.partial(_check_transfer, runtime, route, driver, src, dst, overwrite),
        )
        for route in TRANSFERS
        for driver in DRIVERS
        for src in _states(driver)
        for dst in _states(driver)
        for overwrite in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)
