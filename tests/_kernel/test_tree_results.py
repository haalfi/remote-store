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

**The Memory column.** Beside the fake's four shapes, every family also runs
against the first real driver on the kernel: ``MemoryBackend`` in the sync
runtime and ``AsyncMemoryBackend`` in the async one, a hierarchical driver
with implicit parents over the shared ``MemoryTree``. Its tree is seeded
through the kernel's own ``write`` and ``delete`` (an empty folder is a
file written and deleted, its folder persisting, BE-031), and checked
against the fake's ``hier-implicit`` tree before the cell runs, so both
columns answer the same expectation tables over the same tree. Memory holds
only what decodes to a tree, a hierarchical encoding, so every state here
applies to it. The raw state is read from the tree itself, never through the
kernel. Memory's optional protocols are fixed, so it takes one route per
call: a route it cannot take is named in ``MEMORY_SKIPS`` with the reason,
and ``test_memory_presents_the_protocols_its_column_assumes`` checks that the
reasons still describe the drivers.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store.aio.backends import AsyncMemoryBackend, AsyncMemoryDriver
from remote_store.backends import MemoryBackend, MemoryDriver
from remote_store.backends._memory_tree import DirNode
from remote_store.drivers import (
    AsyncSupportsAtomicMove,
    AsyncSupportsCopy,
    AsyncSupportsDeleteTree,
    AsyncSupportsEnsureParents,
    AsyncSupportsFolderStats,
    AsyncSupportsGlob,
    AsyncSupportsOpenWrite,
    AsyncSupportsRangeRead,
    AsyncSupportsRemoveFolder,
    AsyncSupportsRename,
    SupportsAtomicMove,
    SupportsCopy,
    SupportsDeleteTree,
    SupportsEnsureParents,
    SupportsFolderStats,
    SupportsGlob,
    SupportsOpenWrite,
    SupportsRangeRead,
    SupportsRemoveFolder,
    SupportsRename,
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
from tests._kernel._fake import ALL_PROTOCOLS, RUNTIMES, FakeStore, Runner, keys_of, make_kernel

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

# The tree every cell starts from: its files, and its empty folders where folder objects exist.
TREE_FILES: dict[str, bytes] = {"f": b"F", "s": b"S", "d/x": b"X", "d/s/t": b"T", "e/z": b"Z"}
TREE_EMPTY_FOLDERS = ("z", "y", "h/i", "u/v")

# ---------------------------------------------------------------------------
# The columns: the fake's driver shapes, and the Memory drivers
# ---------------------------------------------------------------------------

MEMORY = "memory"
COLUMNS: dict[str, tuple[str, str]] = {**DRIVERS, MEMORY: ("hierarchical", "implicit")}

# The optional protocols both Memory drivers present, by the fake's protocol names.
MEMORY_PROTOCOLS = frozenset({"open_write", "atomic_move", "copy", "delete_tree", "remove_folder", "folder_stats"})
# Each route Memory cannot take, by route name, and why: its protocols are fixed, so it takes one
# route per call. A route absent here runs on Memory.
MEMORY_SKIPS: dict[str, str] = {
    "read_seekable-range": "presents no get_range: its read_seekable spools",
    "write_atomic-handle": "put is atomic, which the kernel takes before open_write",
    "write_atomic-rename": "put is atomic and it presents no rename: write_atomic puts",
    "open_atomic-spool-put": "presents open_write: open_atomic writes through its handle",
    "open_atomic-spool-rename": "presents open_write: open_atomic writes through its handle",
    "get_folder_info-listing": "presents folder_stats: get_folder_info pushes down",
    "glob": "presents no glob and declares no GLOB",
    "delete_folder-t0": "presents delete_tree: a recursive delete_folder never walks",
    "move-rename": "presents an atomic move, which the kernel takes before a rename",
    "move-displace": "presents an atomic move, which the kernel takes before a rename",
    "move-copy-delete": "presents an atomic move, which the kernel takes before copy-then-delete",
}

# The fake's protocol names -> the Supports* protocol the kernel detects, per runtime.
_SYNC_PROTOCOLS: dict[str, type] = {
    "range": SupportsRangeRead,
    "open_write": SupportsOpenWrite,
    "atomic_move": SupportsAtomicMove,
    "rename": SupportsRename,
    "copy": SupportsCopy,
    "delete_tree": SupportsDeleteTree,
    "remove_folder": SupportsRemoveFolder,
    "ensure_parents": SupportsEnsureParents,
    "folder_stats": SupportsFolderStats,
    "glob": SupportsGlob,
}
_ASYNC_PROTOCOLS: dict[str, type] = {
    "range": AsyncSupportsRangeRead,
    "open_write": AsyncSupportsOpenWrite,
    "atomic_move": AsyncSupportsAtomicMove,
    "rename": AsyncSupportsRename,
    "copy": AsyncSupportsCopy,
    "delete_tree": AsyncSupportsDeleteTree,
    "remove_folder": AsyncSupportsRemoveFolder,
    "ensure_parents": AsyncSupportsEnsureParents,
    "folder_stats": AsyncSupportsFolderStats,
    "glob": AsyncSupportsGlob,
}


def _columns(route: str) -> list[str]:
    """The columns a route runs in: every fake shape, and Memory unless it cannot take the route."""
    return [c for c in COLUMNS if c != MEMORY or route not in MEMORY_SKIPS]


class _World:
    """One cell's store: the runner that calls the kernel, and the raw state read without the kernel."""

    def __init__(self, run: Runner) -> None:
        self.run = run

    def contents(self) -> dict[str, bytes]:
        raise NotImplementedError

    def folders(self) -> set[str]:
        raise NotImplementedError

    def open_handles(self) -> list[Any]:
        raise NotImplementedError


class _FakeWorld(_World):
    def __init__(self, run: Runner, store: FakeStore) -> None:
        super().__init__(run)
        self.store = store

    def contents(self) -> dict[str, bytes]:
        return contents(self.store)

    def folders(self) -> set[str]:
        return set(self.store.folders)

    def open_handles(self) -> list[Any]:
        return [h for h in self.store.handles if h.state == "open"]  # type: ignore[attr-defined]


class _MemoryWorld(_World):
    """A Memory backend; its raw state is the driver's ``MemoryTree``, walked directly."""

    def __init__(self, run: Runner, driver: MemoryDriver | AsyncMemoryDriver) -> None:
        super().__init__(run)
        self.driver = driver

    def _walk(self) -> tuple[dict[str, bytes], set[str]]:
        files: dict[str, bytes] = {}
        folders: set[str] = set()
        stack: list[tuple[str, DirNode]] = [("", self.driver._tree.root)]
        while stack:
            base, node = stack.pop()
            for name, child in node.children.items():
                key = f"{base}/{name}" if base else name
                if isinstance(child, DirNode):
                    folders.add(key)
                    stack.append((key, child))
                else:
                    files[key] = bytes(child.data)
        return files, folders

    def contents(self) -> dict[str, bytes]:
        return self._walk()[0]

    def folders(self) -> set[str]:
        return self._walk()[1]

    def open_handles(self) -> list[Any]:
        return []  # Memory's handle is a buffer, holding nothing once dropped


def _tree(parents: str) -> FakeStore:
    store = FakeStore(parents=parents)
    for key, data in TREE_FILES.items():
        store.add(key, data=data)
    if parents != "none":
        store.add(*(f"{k}/" for k in TREE_EMPTY_FOLDERS))
    return store


def _memory(runtime: str) -> _MemoryWorld:
    """A Memory backend of *runtime* holding the tree, seeded through the kernel's public writes."""
    backend: MemoryBackend | AsyncMemoryBackend = MemoryBackend() if runtime == "sync" else AsyncMemoryBackend()
    driver = backend._driver
    assert isinstance(driver, (MemoryDriver, AsyncMemoryDriver))
    run = Runner(runtime, backend, None, driver)  # type: ignore[arg-type]
    for key, data in TREE_FILES.items():
        run.write(key, data)
    for folder in TREE_EMPTY_FOLDERS:
        run.write(f"{folder}/_", b"")  # a folder persists once its last file is deleted (BE-031)
        run.delete(f"{folder}/_")
    world = _MemoryWorld(run, driver)
    fake = _tree(COLUMNS[MEMORY][1])
    assert (world.contents(), world.folders()) == (contents(fake), fake.folders), "seeded tree is the fake's"
    return world


def _build(
    runtime: str,
    column: str,
    protocols: tuple[str, ...] = (),
    *,
    put_is_atomic: bool = False,
    rename_replaces: bool = True,
) -> _World:
    """The cell's store in *column*; a fake presents *protocols*, Memory its own (``MEMORY_SKIPS``)."""
    if column == MEMORY:
        return _memory(runtime)
    namespace, parents = DRIVERS[column]
    store = _tree(parents)
    run = make_kernel(
        runtime,
        store,
        namespace=namespace,
        protocols=base_protocols(parents) + protocols,
        put_is_atomic=put_is_atomic,
        rename_replaces=rename_replaces,
    )
    return _FakeWorld(run, store)


def _states(column: str) -> list[str]:
    parents = COLUMNS[column][1]
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


def _check_probe(runtime: str, call: str, column: str, state: str) -> None:
    key, _, row = STATES[state]
    world = _build(runtime, column)
    before = world.contents()
    got, err, value = settle(lambda: PROBES[call](world.run, key))
    assert got == "ok", err
    assert value is PROBE_ROWS[row][call]
    assert world.contents() == before


@pytest.mark.spec("BE-004")
@pytest.mark.spec("BE-005")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_probe_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{column}-{state}", functools.partial(_check_probe, runtime, call, column, state))
        for call in PROBES
        for column in _columns(call)
        for state in _states(column)
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


def _check_read(runtime: str, call: str, column: str, state: str) -> None:
    fn, protocols, _, item = READS[call]
    key, _, row = STATES[state]
    world = _build(runtime, column, protocols)
    before = world.contents()
    got, err, value = settle(lambda: fn(world.run, key))
    assert got == READ_ROWS[row], err
    if err is None:
        assert value == item
    else:
        assert err.path == key
    assert world.contents() == before


@pytest.mark.spec("BE-006")
@pytest.mark.spec("BE-007")
@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-016")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_read_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{column}-{state}", functools.partial(_check_read, runtime, call, column, state))
        for call, (_, _, sync_only, _) in READS.items()
        if runtime == "sync" or not sync_only
        for column in _columns(call)
        for state in _states(column)
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


def _check_write(runtime: str, route: str, column: str, state: str, overwrite: bool) -> None:
    call, protocols, put_is_atomic, _ = WRITES[route]
    key, _, row = STATES[state]
    world = _build(runtime, column, protocols, put_is_atomic=put_is_atomic)
    run = world.run
    before = world.contents()
    got, err, _ = settle(lambda: call(run, key, overwrite))
    assert got == _write_row(row, overwrite), err
    if err is None:
        after = world.contents()
        assert after[key] == b"N"
        assert {k: v for k, v in after.items() if k != key} == {k: v for k, v in before.items() if k != key}
        assert all(run.is_folder(a) for a in ancestors(key)), "a written key's parents exist"
    else:
        assert err.path == key
        assert world.contents() == before  # nothing written, no temporary left
    assert not world.open_handles()


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-009")
@pytest.mark.spec("BE-010")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_write_answers_its_rows_column_by_every_route(runtime: str) -> None:
    cells = [
        (
            f"{route}-{column}-{state}-ow{int(overwrite)}",
            functools.partial(_check_write, runtime, route, column, state, overwrite),
        )
        for route, (_, _, _, sync_only) in WRITES.items()
        if runtime == "sync" or not sync_only
        for column in _columns(route)
        for state in _states(column)
        for overwrite in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# delete-file: delete, with and without missing_ok
# ---------------------------------------------------------------------------


def _check_delete(runtime: str, column: str, state: str, missing_ok: bool) -> None:
    key, _, row = STATES[state]
    world = _build(runtime, column)
    before = world.contents()
    # A.5: removed; InvalidPath, which outranks missing_ok (BE-021); NotFound, which missing_ok turns into success.
    want: Expected = {ITEM: "ok", FOLDER: InvalidPath}.get(row, "ok" if missing_ok else NotFound)
    got, err, _ = settle(lambda: world.run.delete(key, missing_ok=missing_ok))
    assert got == want, err
    if err is not None:
        assert err.path == key
    removed = {key} if row == ITEM else set()
    assert world.contents() == {k: v for k, v in before.items() if k not in removed}


@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_delete_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (
            f"delete-{column}-{state}-m{int(missing_ok)}",
            functools.partial(_check_delete, runtime, column, state, missing_ok),
        )
        for column in _columns("delete")
        for state in _states(column)
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


def _check_listing(runtime: str, call: str, column: str, state: str) -> None:
    fn, protocols = LISTINGS[call]
    key, _, row = STATES[state]
    world = _build(runtime, column, protocols)
    before = world.contents()
    want, value = _listing_row(call, state, row)
    got, err, listed = settle(lambda: fn(world.run, key))
    assert got == want, err
    if err is None:
        assert listed == value
    else:
        assert err.path == key
    assert world.contents() == before


@pytest.mark.spec("BE-014")
@pytest.mark.spec("BE-015")
@pytest.mark.spec("BE-017")
@pytest.mark.spec("BE-024")
@pytest.mark.spec("BE-026")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_read_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (f"{call}-{column}-{state}", functools.partial(_check_listing, runtime, call, column, state))
        for call in LISTINGS
        for column in _columns(call)
        for state in _states(column)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# delete-folder: recursive or not, with and without delete_tree and missing_ok
# ---------------------------------------------------------------------------


def _check_delete_folder(runtime: str, column: str, state: str, recursive: bool, tree: bool, missing_ok: bool) -> None:
    key, _, row = STATES[state]
    world = _build(runtime, column, ("delete_tree",) if tree else ())
    run = world.run
    before, folders_before = world.contents(), world.folders()
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
        assert world.contents() == {k: v for k, v in before.items() if not k.startswith(below)}
        assert not run.exists(key)
        return
    if err is not None:
        assert err.path == key
    assert world.contents() == before
    assert world.folders() == folders_before


@pytest.mark.spec("BE-013")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_delete_answers_its_rows_column(runtime: str) -> None:
    cells = [
        (
            f"delete_folder-{column}-{state}-r{int(recursive)}-t{int(tree)}-m{int(missing_ok)}",
            functools.partial(_check_delete_folder, runtime, column, state, recursive, tree, missing_ok),
        )
        for tree in (False, True)
        for column in _columns(f"delete_folder-t{int(tree)}")
        for state in _states(column)
        for recursive in (False, True)
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


def _check_transfer(runtime: str, route: str, column: str, src_state: str, dst_state: str, overwrite: bool) -> None:
    op, protocols, rename_replaces = TRANSFERS[route]
    _, src, src_row = STATES[src_state]
    dst, _, dst_row = STATES[dst_state]
    world = _build(runtime, column, protocols, rename_replaces=rename_replaces)
    run = world.run
    before = world.contents()
    want, names = _transfer_row(src_row, dst_row, overwrite)
    got, err, _ = settle(lambda: getattr(run, op)(src, dst, overwrite=overwrite))
    assert got == want, err
    if err is None:
        after = world.contents()
        assert after[dst] == b"S"
        assert ("s" in after) == (op == "copy")
        untouched = ("s", dst)
        assert {k: v for k, v in after.items() if k not in untouched} == {
            k: v for k, v in before.items() if k not in untouched
        }  # nothing parked or left behind
        assert all(run.is_folder(a) for a in ancestors(dst)), "a written key's parents exist"
    else:
        assert err.path == (src if names == "src" else dst)
        assert world.contents() == before


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_transfer_answers_its_rows_columns_by_every_route(runtime: str) -> None:
    cells = [
        (
            f"{route}-{column}-src_{src}-dst_{dst}-ow{int(overwrite)}",
            functools.partial(_check_transfer, runtime, route, column, src, dst, overwrite),
        )
        for route in TRANSFERS
        for column in _columns(route)
        for src in _states(column)
        for dst in _states(column)
        for overwrite in (False, True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# The Memory column's assumptions
# ---------------------------------------------------------------------------

ROUTES = frozenset({*PROBES, *READS, *WRITES, "delete", *LISTINGS, "delete_folder-t0", "delete_folder-t1", *TRANSFERS})
# Each route's optional protocols, where the family's table states them.
ROUTE_PROTOCOLS: dict[str, tuple[str, ...]] = {
    **{call: protocols for call, (_, protocols, _, _) in READS.items()},
    **{route: protocols for route, (_, protocols, _, _) in WRITES.items()},
    **{call: protocols for call, (_, protocols) in LISTINGS.items()},
    **{route: protocols for route, (_, protocols, _) in TRANSFERS.items()},
    "delete_folder-t1": ("delete_tree",),
}


@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_memory_presents_the_protocols_its_column_assumes(runtime: str) -> None:
    """``MEMORY_SKIPS`` is true of the drivers: their shape, protocols and atomic put are what it assumes."""
    driver = MemoryDriver() if runtime == "sync" else AsyncMemoryDriver()
    detect = _SYNC_PROTOCOLS if runtime == "sync" else _ASYNC_PROTOCOLS
    assert set(detect) == set(ALL_PROTOCOLS)
    presented = {name for name, proto in detect.items() if isinstance(driver, proto)}
    assert presented == MEMORY_PROTOCOLS
    assert (driver.namespace, driver.parents) == COLUMNS[MEMORY]
    assert driver.put_is_atomic is True
    assert not driver.capabilities.supports(Capability.GLOB)
    # Every skip names a route of a family, and every route Memory runs needs only what it presents.
    assert set(MEMORY_SKIPS) <= ROUTES, sorted(set(MEMORY_SKIPS) - ROUTES)
    runs = {r: p for r, p in ROUTE_PROTOCOLS.items() if r not in MEMORY_SKIPS}
    assert all(set(p) <= MEMORY_PROTOCOLS for p in runs.values()), runs
