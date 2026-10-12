"""What is at a key, as every kernel call that reads a driver refusal answers it, in both runtimes.

The kernel answers "what is at this key" for every call that needs a file
or a folder there: the probes, the file-shaped reads, the write routes, the
transfers, the listings, ``get_folder_info`` by push-down and by listing,
and ``glob``. Each family below is a cell product over **one shared axis
set**, defined once at the top of this module:

- the driver: ``namespace`` × ``parents``;
- the key's state: absent, absent under an absent folder, a file, an empty
  folder (folder objects only), a folder holding a file, under a file,
  deeper under a file, and a flat key shadowing a prefix (flat only);
- the refusal: the wire's own answer in each native shape where the state
  makes it refuse, or a refusal injected on the family's first primitive
  call whatever the state, so a real folder, a file and a shadowing key are
  asked about too and never only the states where an empty answer is right;
- what ``stat`` does: answers truthfully; raises ENOTDIR (typed
  ``NotFound``), an unrecognised code, or a denial under a file
  (hierarchical only, the under-a-file states only); denies the one key the
  cell is about, ancestors answering; or every ``stat`` meets a dead service.

**Pruning, the one rule:** an axis value is crossed only where it can be
reached. The wire's native shapes only where the state makes the wire
refuse; the under-a-file ``stat`` values only for a key under a file on a
hierarchical namespace; an injected refusal only for a family whose call
reaches a refusable primitive besides ``stat`` (``get_file_info`` and the
probes call only ``stat``, which the ``stat`` axis covers). Transfers take
the native shapes and the ``stat`` axis, not the injection: a two-key
primitive's injected refusal is answered by the same rule as its native one.

``delete_folder`` is not here: ``test_delete_folder.py`` runs it against the
decided formal model over the model's own key states (a key under a file
included) and its enumerated probe space (a raising ``stat`` included).

Each product's expected answer is an oracle written from spec 003 (BE-004
to BE-019, BE-021, BE-024, BE-026, BE-030), reading only the state the cell
built, so a cell fails when the kernel and the rule disagree. The rule, the
axes and the decisions behind them: BE-030 and BK-389's dossier,
§ Condition space and § Re-plan after round 10.
"""

from __future__ import annotations

import functools
import itertools
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from tests._kernel._fake import (
    RUNTIMES,
    FakeDenied,
    FakeDown,
    FakeExists,
    FakeIsDir,
    FakeMissing,
    FakeNotDir,
    FakeOdd,
    FakeStore,
    FakeWireError,
    keys_of,
    make_kernel,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# The shared axis set
# ---------------------------------------------------------------------------

# (namespace, parents); flat with folder objects is refused at construction (BE-030).
DRIVERS = {
    "flat-none": ("flat", "none"),
    "hier-none": ("hierarchical", "none"),
    "hier-implicit": ("hierarchical", "implicit"),
    "hier-explicit": ("hierarchical", "explicit"),
}

# The native shapes a wire refuses in: EISDIR, EEXIST from an exclusive
# create, Windows EACCES or WinError 267, ENOENT, an unrecognised code, a dead service.
SHAPES: dict[str, type[FakeWireError]] = {
    "is-dir": FakeIsDir,
    "exists": FakeExists,
    "denied": FakeDenied,
    "missing": FakeMissing,
    "odd": FakeOdd,
    "down": FakeDown,
}
TYPED: dict[str, type[RemoteStoreError]] = {
    "is-dir": InvalidPath,
    "exists": AlreadyExists,
    "denied": PermissionDenied,
    "missing": NotFound,
    "odd": RemoteStoreError,
    "down": BackendUnavailable,
}

# One key per state. The store always holds the file "f", the source file
# "s", the folders "d" (holding "d/x") and "e" (holding "e/z"); with folder
# objects the empty folder "z"; on a flat namespace the key "g" shadowing the
# prefix "g/" (holding "g/a" and "g/b/c").
KEY = {
    "absent": "n",
    "absent-deep": "n/q",
    "file": "f",
    "empty": "z",
    "folder": "d",
    "under": "f/x",
    "deeper": "f/x/y",
    "shadow": "g",
}
UNDER = ("under", "deeper")
SRC_KEY = {"file": "s", "absent": "m", "folder": "e"}

# What `stat` does. "nf", "odd" and "denied" act on a key under a file; "key"
# denies the cell's own key; "down" fails every stat.
STATS = ("true", "nf", "odd", "denied", "key", "down")
UNDER_STATS: dict[str, type[FakeWireError]] = {"nf": FakeNotDir, "odd": FakeOdd, "denied": FakeDenied}

Expected = type[RemoteStoreError] | str  # an error class, or "ok"


def _states(driver: str) -> list[str]:
    namespace, parents = DRIVERS[driver]
    return [s for s in KEY if not (s == "empty" and parents == "none") and not (s == "shadow" and namespace != "flat")]


def _stats(driver: str, state: str) -> tuple[str, ...]:
    if DRIVERS[driver][0] != "flat" and state in UNDER:
        return STATS
    return ("true", "key", "down")


def _store(driver: str, stat: str, subject: str, shape: str | None = None) -> FakeStore:
    namespace, parents = DRIVERS[driver]
    store = FakeStore(parents=parents).add("f", data=b"F").add("s", data=b"S").add("d/x", "e/z")
    if parents != "none":
        store.add("z/")
    if namespace == "flat":
        store.add("g", "g/a", "g/b/c")
    if shape is not None:
        store.folder_refusal = SHAPES[shape]
        store.listing_refusal = SHAPES[shape]

    def stat_fault(key: str) -> type[FakeWireError] | None:
        if stat == "down":
            return FakeDown
        if stat == "key" and key == subject:
            return FakeDenied
        if stat in UNDER_STATS and store._under_file(key):
            return UNDER_STATS[stat]
        return None

    store.stat_fault = stat_fault
    return store


def _contents(store: FakeStore) -> dict[str, bytes]:
    return {k: r.data for k, r in store.files.items()}


def _settle(call: Callable[[], Any]) -> tuple[Expected, RemoteStoreError | None, Any]:
    try:
        value = call()
    except RemoteStoreError as err:
        return type(err), err, None
    return "ok", None, value


def _may_be_a_folder(cls: type[RemoteStoreError]) -> bool:
    """BE-030's probe set: the refusals that may be a wire's way of meeting the wrong type."""
    return cls in (NotFound, AlreadyExists, PermissionDenied, RemoteStoreError)


def _stat_error(stat: str) -> type[RemoteStoreError]:
    """What a ``stat`` that cannot answer raises, for the "key" and "down" values."""
    return BackendUnavailable if stat == "down" else PermissionDenied


def _known(state: str, stat: str, namespace: str, *, parents_made: bool = False) -> str:
    """What fail-open ``stat`` calls can learn of a key: absent, file, folder, under, or unknown.

    BE-030's *What is at a key*. On a hierarchical namespace a ``stat`` that
    raises is followed by one per ancestor: a file there puts the key under
    a file, an absent one makes the key absent. A flat ``stat`` cannot see a
    prefix, so a miss is followed by one listing; nothing on a flat
    namespace is under a file, and a key shadowing a prefix is its file.
    ``parents_made``: ``ensure_parents`` has created the absent ancestor.
    """
    hier = namespace != "flat"
    if stat == "down":
        return "unknown"
    if stat == "key":
        if not hier:
            return "unknown"
        if state in UNDER:
            return "under"
        if state == "absent-deep" and not parents_made:
            return "absent"
        return "unknown"
    if stat in UNDER_STATS:  # hierarchical, under a file
        return "under"
    return {
        "absent": "absent",
        "absent-deep": "absent",
        "file": "file",
        "shadow": "file",
        "empty": "folder",
        "folder": "folder",
        "under": "under" if hier else "absent",
        "deeper": "under" if hier else "absent",
    }[state]


def _determined(state: str, stat: str, namespace: str, *, parents_made: bool = False) -> str:
    """What a determinant ``stat`` learns: as ``_known``, but a ``None`` or ``NotFound`` is a miss.

    A determinant runs on the success path, so a plain miss is not walked;
    only a ``stat`` that raises gets the ancestors' ``stat`` calls.
    """
    known = _known(state, stat, namespace, parents_made=parents_made)
    if known == "under" and stat in ("true", "nf"):
        return "absent"
    return known


def _refusals(natural: bool, inject: bool) -> list[tuple[str, str | None]]:
    """The refusal axis: ("none", None), the native shapes where met, the injections where reachable."""
    values: list[tuple[str, str | None]] = []
    values += [("natural", s) for s in SHAPES] if natural else [("none", None)]
    if inject:
        values += [("inject", s) for s in SHAPES]
    return values


def _rid(refusal: tuple[str, str | None]) -> str:
    kind, shape = refusal
    return kind if shape is None else f"{kind}_{shape}"


Cell = tuple[str, "Callable[[], None]"]  # an id, and the cell's check bound to its axis values


def _disagreeing(cells: list[Cell]) -> list[str]:
    """Run every cell of a family; each cell that disagreed with the oracle, named.

    A family is one pytest item per runtime, not one per cell, at the
    maintainer's decision (BK-389's dossier, § Re-plan after round 10,
    decision 13): every cell still runs, and a failure lists them all.
    """
    failures = []
    for cell_id, check in cells:
        try:
            check()
        except AssertionError as exc:
            failures.append(f"{cell_id}: {str(exc).splitlines()[0] if str(exc) else 'assertion failed'}")
    return failures


def _report(failures: list[str], cells: list[Cell]) -> str:
    shown = "\n".join(failures[:50])
    return f"{len(failures)} of {len(cells)} cells disagree with the oracle:\n{shown}"


# ---------------------------------------------------------------------------
# The probes: exists, is_file, is_folder (BE-004, BE-005, BE-021)
# ---------------------------------------------------------------------------

PROBES: dict[str, Callable[[Any, str], Any]] = {
    "exists": lambda r, k: r.exists(k),
    "is_file": lambda r, k: r.is_file(k),
    "is_folder": lambda r, k: r.is_folder(k),
}


def _probe_expected(call: str, driver: str, state: str, stat: str) -> Expected | bool:
    """A traversal answer is ``False``; a ``stat`` that cannot answer raises, so a denial stays visible.

    A key shadowing a prefix answers as its file (the flat key wins, as S3 answers today).
    """
    known = _known(state, stat, DRIVERS[driver][0])
    if known == "unknown":
        return _stat_error(stat)
    if call == "exists":
        return known in ("file", "folder")
    return known == ("file" if call == "is_file" else "folder")


def _probe_cells(runtime: str) -> list[Cell]:
    return [
        (f"{call}-{driver}-{state}-stat_{stat}", functools.partial(_check_probe, runtime, call, driver, state, stat))
        for call in PROBES
        for driver in DRIVERS
        for state in _states(driver)
        for stat in _stats(driver, state)
    ]


@pytest.mark.spec("BE-004")
@pytest.mark.spec("BE-005")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_probe_on_each_state(runtime: str) -> None:
    cells = _probe_cells(runtime)
    failures = _disagreeing(cells)
    assert not failures, _report(failures, cells)


def _check_probe(runtime: str, call: str, driver: str, state: str, stat: str) -> None:
    namespace, parents = DRIVERS[driver]
    store = _store(driver, stat, KEY[state])
    run = make_kernel(runtime, store, namespace=namespace, protocols=_base(parents))
    want = _probe_expected(call, driver, state, stat)
    got, err, value = _settle(lambda: PROBES[call](run, KEY[state]))
    if isinstance(want, bool):
        assert got == "ok", err
        assert value is want
    else:
        assert got == want


def _base(parents: str) -> tuple[str, ...]:
    return ("remove_folder", "ensure_parents") if parents != "none" else ()


# ---------------------------------------------------------------------------
# The file-shaped reads (BE-006, BE-007, BE-012, BE-016, BE-021)
# ---------------------------------------------------------------------------


def _read_seekable(run: Any, key: str) -> bytes:
    with run.kernel.read_seekable(key) as stream:
        return bytes(stream.read())


# call -> (call, protocols, sync only, determinant, the primitive an injection refuses)
READ_CALLS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...], bool, bool, str | None]] = {
    "read": (lambda r, k: r.read(k), (), False, False, "get"),
    "read_bytes": (lambda r, k: r.read_bytes(k), (), False, False, "get"),
    "read_seekable-range": (_read_seekable, ("range",), True, True, "get_range"),
    "read_seekable-spool": (_read_seekable, (), True, False, "get"),
    "delete": (lambda r, k: r.delete(k), (), False, False, "delete"),
    "delete-missing_ok": (lambda r, k: r.delete(k, missing_ok=True), (), False, False, "delete"),
    "get_file_info": (lambda r, k: r.get_file_info(k), (), False, True, None),
}


def _read_expected(call: str, driver: str, state: str, refusal: tuple[str, str | None], stat: str) -> Expected:
    """BE-021: a folder is the wrong type on every backend and outranks ``missing_ok``.

    A determinant (``get_file_info``, a ranged ``read_seekable``) answers from
    the key's state; a ``stat`` that cannot answer is its failure. Elsewhere
    the driver's refusal is typed by fail-open probes: a folder answers
    ``InvalidPath``, and otherwise the refusal stands.
    """
    _, _, _, determinant, _ = READ_CALLS[call]
    known = _known(state, stat, DRIVERS[driver][0])
    kind, shape = refusal
    if determinant:
        if known == "unknown":
            return _stat_error(stat)
        if known == "folder":
            return InvalidPath
        if known in ("absent", "under"):
            return NotFound
        return TYPED[shape] if kind == "inject" and shape is not None else "ok"
    if kind == "inject" and shape is not None:
        err = TYPED[shape]
    elif state in ("file", "shadow"):
        return "ok"
    elif state in ("folder", "empty"):
        err = TYPED[shape] if shape is not None else InvalidPath
    else:
        err = NotFound
    if _may_be_a_folder(err) and known == "folder":
        return InvalidPath
    if call == "delete-missing_ok" and err is NotFound:
        return "ok"
    return err


def _read_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for call, (_, _, sync_only, _, prim) in READ_CALLS.items():
        if sync_only and runtime != "sync":
            continue
        for driver in DRIVERS:
            for state in _states(driver):
                natural = state in ("folder", "empty") and prim is not None and prim != "get_range"
                for refusal in _refusals(natural, prim is not None):
                    for stat in _stats(driver, state):
                        cells.append(
                            (
                                f"{call}-{driver}-{state}-{_rid(refusal)}-stat_{stat}",
                                functools.partial(_check_read, runtime, call, driver, state, refusal, stat),
                            )
                        )
    return cells


@pytest.mark.spec("BE-006")
@pytest.mark.spec("BE-007")
@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-016")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_shaped_read_on_each_state(runtime: str) -> None:
    cells = _read_cells(runtime)
    failures = _disagreeing(cells)
    assert not failures, _report(failures, cells)


def _check_read(runtime: str, call: str, driver: str, state: str, refusal: tuple[str, str | None], stat: str) -> None:
    fn, protocols, _, _, prim = READ_CALLS[call]
    namespace, parents = DRIVERS[driver]
    kind, shape = refusal
    key = KEY[state]
    store = _store(driver, stat, key, shape if kind == "natural" else None)
    if kind == "inject" and shape is not None and prim is not None:
        store.fault(prim, SHAPES[shape](key))
    run = make_kernel(runtime, store, namespace=namespace, protocols=_base(parents) + protocols)
    before = _contents(store)
    want = _read_expected(call, driver, state, refusal, stat)
    got, err, value = _settle(lambda: fn(run, key))
    assert got == want, err
    if err is not None and got is not BackendUnavailable:
        assert err.path == key
    if got == "ok" and call.startswith("read"):
        assert value == before[key]
    if not (call.startswith("delete") and got == "ok" and state in ("file", "shadow")):
        assert _contents(store) == before


# ---------------------------------------------------------------------------
# A single-key write onto each state, by every route (BE-008 to BE-011)
# ---------------------------------------------------------------------------


def _open_atomic(run: Any, key: str, overwrite: bool) -> None:
    with run.kernel.open_atomic(key, overwrite=overwrite) as stream:
        stream.write(b"N")


# route -> (call, protocols, put_is_atomic, sync only, stats the target first without overwrite, injected primitive)
WRITE_ROUTES: dict[str, tuple[Callable[[Any, str, bool], Any], tuple[str, ...], bool, bool, bool, str]] = {
    "write": (lambda r, k, o: r.write(k, b"N", overwrite=o), (), False, False, False, "put"),
    "write_atomic-put": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), (), True, False, False, "put"),
    "write_atomic-handle": (
        lambda r, k, o: r.write_atomic(k, b"N", overwrite=o),
        ("open_write",),
        False,
        False,
        False,
        "open_write",
    ),
    "write_atomic-rename": (
        lambda r, k, o: r.write_atomic(k, b"N", overwrite=o),
        ("rename",),
        False,
        False,
        True,
        "put",
    ),
    "open_atomic-handle": (_open_atomic, ("open_write",), False, True, False, "open_write"),
    "open_atomic-spool": (_open_atomic, ("rename",), False, True, True, "put"),
}

FOLDERISH = ("folder", "empty")


def _write_expected(
    route: str, driver: str, state: str, overwrite: bool, refusal: tuple[str, str | None], stat: str
) -> Expected:
    """BE-008's order with its flat exemption, as BE-030 states it for the kernel.

    A hierarchical wire refuses a folder at the key, or a file above it, in
    its own shape; fail-open probes type the refusal ``InvalidPath``, and a
    refusal they cannot type stands. A flat namespace writes either. Where
    the kernel stats the target first, that ``stat`` decides: a file is
    ``AlreadyExists``, a folder or a file above ``InvalidPath``, a miss
    goes on, and a ``stat`` that cannot answer fails the write.
    """
    namespace, parents = DRIVERS[driver]
    hier = namespace != "flat"
    kind, shape = refusal
    key = KEY[state]
    wire_folder = TYPED[shape] if kind == "natural" and shape is not None else InvalidPath
    made = parents == "explicit" and "/" in key and state == "absent-deep"
    known = _known(state, stat, namespace, parents_made=made)

    def typed(err: type[RemoteStoreError]) -> Expected:
        if hier and _may_be_a_folder(err) and known in ("folder", "under"):
            return InvalidPath
        return err

    if parents == "explicit" and "/" in key and state in UNDER:
        return typed(wire_folder)  # ensure_parents meets the file above
    if WRITE_ROUTES[route][4] and not overwrite:
        if hier:
            seen = _determined(state, stat, namespace, parents_made=made)
        else:  # a flat target is a stat alone: a prefix is not seen
            seen = "unknown" if stat in ("key", "down") else ("file" if state in ("file", "shadow") else "absent")
        if seen == "unknown":
            return _stat_error(stat)
        if seen == "file":
            return AlreadyExists
        if seen in ("folder", "under"):
            return InvalidPath
    if kind == "inject" and shape is not None:
        return typed(TYPED[shape])
    if hier and state in FOLDERISH + UNDER:
        return typed(wire_folder)
    if state in ("file", "shadow") and not overwrite:
        return AlreadyExists
    return "ok"


def _write_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for route, (_, _, _, sync_only, _, _) in WRITE_ROUTES.items():
        if sync_only and runtime != "sync":
            continue
        for driver in DRIVERS:
            for overwrite in (False, True):
                for state in _states(driver):
                    natural = state in FOLDERISH + UNDER and DRIVERS[driver][0] != "flat"
                    for refusal in _refusals(natural, True):
                        for stat in _stats(driver, state):
                            cells.append(
                                (
                                    f"{route}-{driver}-{state}-ow{int(overwrite)}-{_rid(refusal)}-stat_{stat}",
                                    functools.partial(
                                        _check_write, runtime, route, driver, state, overwrite, refusal, stat
                                    ),
                                )
                            )
    return cells


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-009")
@pytest.mark.spec("BE-010")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_write_onto_each_state_by_every_route(runtime: str) -> None:
    cells = _write_cells(runtime)
    failures = _disagreeing(cells)
    assert not failures, _report(failures, cells)


def _check_write(
    runtime: str, route: str, driver: str, state: str, overwrite: bool, refusal: tuple[str, str | None], stat: str
) -> None:
    call, protocols, put_is_atomic, _, _, prim = WRITE_ROUTES[route]
    namespace, parents = DRIVERS[driver]
    kind, shape = refusal
    key = KEY[state]
    store = _store(driver, stat, key, shape if kind == "natural" else None)
    if kind == "inject" and shape is not None:
        store.fault(prim, SHAPES[shape](key))
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=_base(parents) + protocols, put_is_atomic=put_is_atomic
    )
    before = _contents(store)
    want = _write_expected(route, driver, state, overwrite, refusal, stat)
    got, err, _ = _settle(lambda: call(run, key, overwrite))
    assert got == want, err
    if err is None:
        assert store.files[key].data == b"N"
        assert {k: v for k, v in _contents(store).items() if k != key} == {k: v for k, v in before.items() if k != key}
    else:
        if want is not BackendUnavailable:
            assert err.path == key
        assert _contents(store) == before  # nothing written, no temporary left
    assert all(h.state != "open" for h in store.handles)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# move and copy, the source and the destination each in every state (BE-018, BE-019)
# ---------------------------------------------------------------------------

# route -> (op, protocols, rename_replaces)
TRANSFER_ROUTES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "move-atomic": ("move", ("atomic_move",), True),
    "move-rename": ("move", ("rename",), True),
    "move-displace": ("move", ("rename",), False),
    "move-copy-delete": ("move", ("copy",), True),
    "copy": ("copy", ("copy",), True),
}


def _transfer_expected(
    route: str, driver: str, src: str, dst: str, overwrite: bool, shape: str, dst_first: bool, stat: str
) -> tuple[Expected, str | None]:
    """BE-018's order: the source's state first, then the destination's, as BE-030 states it.

    The kernel confirms the source before any write on a rename route or an
    explicit-parents driver; a rename route stats the destination as a write
    target. Otherwise the wire answers, in its own key order and shape, and
    fail-open probes re-answer a refusal from the keys' states. A refusal
    the probes cannot type stands, naming the destination only when it can
    only be the destination's.
    """
    namespace, parents = DRIVERS[driver]
    hier = namespace != "flat"
    renames = route in ("move-rename", "move-displace")
    dkey = KEY[dst]
    src_known = "unknown" if stat == "down" else src
    made = parents == "explicit" and "/" in dkey and dst == "absent-deep"
    dst_known = _known(dst, stat, namespace, parents_made=made)
    wire_cls = TYPED[shape]

    def dst_typed(err: type[RemoteStoreError]) -> bool:
        return hier and _may_be_a_folder(err) and dst_known in ("folder", "under")

    if renames or parents == "explicit":
        if src_known == "unknown":
            return BackendUnavailable, None
        if src == "absent":
            return NotFound, "m"
        if src == "folder":
            return InvalidPath, "e"
    if parents == "explicit" and "/" in dkey and dst in UNDER:  # ensure_parents meets the file above
        if dst_typed(wire_cls):
            return InvalidPath, dkey
        return wire_cls, (None if wire_cls is BackendUnavailable else dkey)
    if renames:
        if hier:
            seen = _determined(dst, stat, namespace, parents_made=made)
        else:
            seen = "unknown" if stat in ("key", "down") else ("file" if dst in ("file", "shadow") else "absent")
        if seen == "unknown":
            return _stat_error(stat), (None if stat == "down" else dkey)
        if seen in ("folder", "under"):
            return InvalidPath, dkey
        if seen == "file":
            return ("ok", None) if overwrite else (AlreadyExists, dkey)
        # A miss: the rename meets what the stat did not see.
        if hier and dst in FOLDERISH + UNDER:
            if wire_cls is BackendUnavailable:
                return BackendUnavailable, None
            if dst_typed(wire_cls) or wire_cls is InvalidPath:
                return InvalidPath, dkey
            return wire_cls, dkey
        return "ok", None
    src_ref = {"file": None, "absent": NotFound, "folder": wire_cls}[src]
    dst_ref: type[RemoteStoreError] | None = None
    if hier and dst in FOLDERISH + UNDER:
        dst_ref = wire_cls
    elif dst in ("file", "shadow") and not overwrite:
        dst_ref = AlreadyExists
    first, second = (dst_ref, src_ref) if dst_first else (src_ref, dst_ref)
    err = first or second
    if err is None:
        return "ok", None
    if not (_may_be_a_folder(err) or err is InvalidPath):
        return err, None
    if src_known == "absent":
        return NotFound, "m"
    if src_known == "folder":
        return InvalidPath, "e"
    if dst_typed(err):
        return InvalidPath, dkey
    if err is AlreadyExists or (src_known == "file" and err in (NotFound, InvalidPath)):
        return err, dkey
    return err, SRC_KEY[src]


def _transfer_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for route in TRANSFER_ROUTES:
        for driver, (namespace, parents) in DRIVERS.items():
            # A route that confirms the source first answers a non-file source before
            # the destination or the wire is reached, so neither is crossed there.
            src_first = route in ("move-rename", "move-displace") or parents == "explicit"
            for src in SRC_KEY:
                answered_early = src_first and src != "file"
                for overwrite in (False, True):
                    for dst_first in (False, True):
                        if dst_first and (src_first or src == "file"):
                            continue  # the wire never meets a refused source, so its key order cannot matter
                        for dst in ["absent"] if answered_early else _states(driver):
                            refused = (src == "folder" and not src_first) or (
                                dst in FOLDERISH + UNDER and namespace != "flat"
                            )
                            stats = ("true", "down") if answered_early else _stats(driver, dst)
                            for shape in SHAPES if refused else ("is-dir",):
                                for stat in stats:
                                    order = "dst_first" if dst_first else "src_first"
                                    cells.append(
                                        (
                                            f"{route}-{driver}-src_{src}-dst_{dst}-ow{int(overwrite)}-{order}"
                                            f"-{shape}-stat_{stat}",
                                            functools.partial(
                                                _check_transfer,
                                                runtime,
                                                route,
                                                driver,
                                                src,
                                                dst,
                                                overwrite,
                                                dst_first,
                                                shape,
                                                stat,
                                            ),
                                        )
                                    )
    return cells


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_transfer_between_each_pair_of_states_by_every_route(runtime: str) -> None:
    cells = _transfer_cells(runtime)
    failures = _disagreeing(cells)
    assert not failures, _report(failures, cells)


def _check_transfer(
    runtime: str, route: str, driver: str, src: str, dst: str, overwrite: bool, dst_first: bool, shape: str, stat: str
) -> None:
    op, protocols, rename_replaces = TRANSFER_ROUTES[route]
    namespace, parents = DRIVERS[driver]
    src_key, dst_key = SRC_KEY[src], KEY[dst]
    store = _store(driver, stat, dst_key, shape)
    store.dst_first = dst_first
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=_base(parents) + protocols, rename_replaces=rename_replaces
    )
    before = _contents(store)
    want, want_path = _transfer_expected(route, driver, src, dst, overwrite, shape, dst_first, stat)
    got, err, _ = _settle(lambda: getattr(run, op)(src_key, dst_key, overwrite=overwrite))
    assert got == want, err
    if err is None:
        after = _contents(store)
        assert after[dst_key] == b"S"
        assert ("s" in after) == (op == "copy")
        assert {k: v for k, v in after.items() if k not in ("s", dst_key)} == {
            k: v for k, v in before.items() if k not in ("s", dst_key)
        }  # nothing parked or left behind
    else:
        if want_path is not None:
            assert err.path == want_path
        assert _contents(store) == before


# ---------------------------------------------------------------------------
# The folder-shaped calls: the listings, get_folder_info by listing and by push-down, glob
# ---------------------------------------------------------------------------

LIST_CALLS: dict[str, Callable[[Any, str], Any]] = {
    "list_files": lambda r, k: keys_of(r.list_files(k)),
    "list_files-recursive": lambda r, k: keys_of(r.list_files(k, recursive=True)),
    "list_folders": lambda r, k: keys_of(r.list_folders(k)),
    "iter_children": lambda r, k: keys_of(r.iter_children(k)),
    "get_folder_info-listing": lambda r, k: r.get_folder_info(k).file_count,
    "get_folder_info-push_down": lambda r, k: r.get_folder_info(k).file_count,
}

# What each call yields for the states that hold something.
LISTED: dict[str, dict[str, Any]] = {
    "folder": {
        "list_files": ["d/x"],
        "list_files-recursive": ["d/x"],
        "list_folders": [],
        "iter_children": ["d/x"],
        "get_folder_info": 1,
    },
    "shadow": {
        "list_files": ["g/a"],
        "list_files-recursive": ["g/a", "g/b/c"],
        "list_folders": ["g/b"],
        "iter_children": ["g/a", "g/b"],
        "get_folder_info": 2,
    },
}


def _list_expected(
    call: str, driver: str, state: str, refusal: tuple[str, str | None], stat: str
) -> tuple[Expected, Any]:
    """BE-014, BE-015, BE-026: a non-folder lists nothing; BE-017 types the empty aggregate.

    A refusal before the first page is an empty listing when it is a
    ``NotFound`` or ``InvalidPath``, or when it is in the probe set and
    fail-open probes find no folder: nothing, a file, or a file above, on a
    hierarchical namespace. On a flat namespace a file at the prefix rules
    out nothing below it, so such a refusal propagates, as it does for a
    folder or a key the probes cannot answer. The push-down answers by the
    same rule. Then an empty aggregate is typed: fail-open without folder
    objects, by a determinant ``stat`` with them.
    """
    namespace, parents = DRIVERS[driver]
    hier = namespace != "flat"
    kind, shape = refusal
    aggregate = call.startswith("get_folder_info")
    known = _known(state, stat, namespace)
    err: type[RemoteStoreError] | None = None
    if kind in ("inject", "natural") and shape is not None:
        err = TYPED[shape]
    elif parents != "none" and not call.endswith("push_down") and state in ("absent", "absent-deep"):
        err = NotFound
    emptied = False
    if err is not None:
        if err in (NotFound, InvalidPath) or (hier and _may_be_a_folder(err) and known in ("absent", "file", "under")):
            emptied = True
        else:
            return err, None
    listed = {} if emptied else LISTED.get(state, {})
    if not aggregate:
        return "ok", listed.get(call, [])
    count = listed.get("get_folder_info", 0)
    if count:
        return "ok", count
    if parents == "none":
        if known == "file":
            return InvalidPath, None
        return ("ok", 0) if known == "folder" else (NotFound, None)
    if known == "unknown":
        return _stat_error(stat), None
    if known == "file":
        return InvalidPath, None
    return ("ok", 0) if known == "folder" else (NotFound, None)


def _list_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for call in LIST_CALLS:
        for driver, (_, parents) in DRIVERS.items():
            for state in _states(driver):
                # Only a wire with folder objects refuses to list a file, or a key under one.
                natural = parents != "none" and state in ("file", *UNDER) and not call.endswith("push_down")
                for refusal in _refusals(natural, True):
                    for stat in _stats(driver, state):
                        cells.append(
                            (
                                f"{call}-{driver}-{state}-{_rid(refusal)}-stat_{stat}",
                                functools.partial(_check_listing, runtime, call, driver, state, refusal, stat),
                            )
                        )
    return cells


@pytest.mark.spec("BE-014")
@pytest.mark.spec("BE-015")
@pytest.mark.spec("BE-017")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-026")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_shaped_call_on_each_state(runtime: str) -> None:
    cells = _list_cells(runtime)
    failures = _disagreeing(cells)
    assert not failures, _report(failures, cells)


def _check_listing(
    runtime: str, call: str, driver: str, state: str, refusal: tuple[str, str | None], stat: str
) -> None:
    namespace, parents = DRIVERS[driver]
    kind, shape = refusal
    key = KEY[state]
    store = _store(driver, stat, key)
    if kind == "natural" and shape is not None:
        store.listing_refusal = SHAPES[shape]
    push_down = call.endswith("push_down")
    if kind == "inject" and shape is not None:
        store.fault("folder_stats" if push_down else "list_page", SHAPES[shape](key))
    protocols = _base(parents) + (("folder_stats",) if push_down else ())
    run = make_kernel(runtime, store, namespace=namespace, protocols=protocols)
    want, value = _list_expected(call, driver, state, refusal, stat)
    got, err, listed = _settle(lambda: LIST_CALLS[call](run, key))
    assert got == want, err
    if got == "ok":
        assert listed == value
    elif got is not BackendUnavailable:
        assert err is not None
        assert err.path == key


@pytest.mark.spec("BE-024")
@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("driver", list(DRIVERS))
@pytest.mark.parametrize("refusal", [("none", None), *(("inject", s) for s in SHAPES)], ids=_rid)
def test_a_glob_refused_before_its_first_match(runtime: str, driver: str, refusal: tuple[str, str | None]) -> None:
    # A glob names no key, so only the listing bound applies: a NotFound before
    # the first match is an empty result, any other refusal propagates.
    namespace, parents = DRIVERS[driver]
    _, shape = refusal
    store = _store(driver, "true", "")
    if shape is not None:
        store.fault("glob", SHAPES[shape]("d/*"))
    run = make_kernel(runtime, store, namespace=namespace, protocols=(*_base(parents), "glob"))
    got, err, listed = _settle(lambda: keys_of(run.glob("d/*")))
    if shape is None:
        assert listed == ["d/x"]
    elif TYPED[shape] is NotFound:
        assert listed == []
    else:
        assert got == TYPED[shape], err


# ---------------------------------------------------------------------------
# Capability gates, declared against presented
# ---------------------------------------------------------------------------

BASE_CAPS = (Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE)
META = {"k": "v"}

# op -> (capability, protocols that back it, extra declared capabilities, sync only, {key class: call})
GATED: dict[str, tuple[Capability, tuple[str, ...], tuple[Capability, ...], bool, dict[str, Callable[[Any], Any]]]] = {
    "glob": (
        Capability.GLOB,
        ("glob",),
        (),
        False,
        {
            "valid": lambda r: r.glob("d/*"),
            "root": lambda r: r.glob(""),
            "refused": lambda r: r.glob("/d/*"),
        },
    ),
    "write_atomic": (
        Capability.ATOMIC_WRITE,
        ("open_write",),
        (),
        False,
        {
            "valid": lambda r: r.write_atomic("n", b"N"),
            "root": lambda r: r.write_atomic("", b"N"),
            "refused": lambda r: r.write_atomic("/n", b"N"),
        },
    ),
    "open_atomic": (
        Capability.ATOMIC_WRITE,
        ("open_write",),
        (),
        True,
        {
            "valid": lambda r: _open_atomic(r, "n", False),
            "root": lambda r: _open_atomic(r, "", False),
            "refused": lambda r: _open_atomic(r, "/n", False),
        },
    ),
    "move": (
        Capability.MOVE,
        ("atomic_move",),
        (),
        False,
        {
            "valid": lambda r: r.move("f", "n"),
            "root": lambda r: r.move("f", ""),
            "refused": lambda r: r.move("f", "/n"),
            "self": lambda r: r.move("f", "f"),
        },
    ),
    "copy": (
        Capability.COPY,
        ("copy",),
        (),
        False,
        {
            "valid": lambda r: r.copy("f", "n"),
            "root": lambda r: r.copy("f", ""),
            "refused": lambda r: r.copy("f", "/n"),
            "self": lambda r: r.copy("f", "f"),
        },
    ),
    # WR-010's strict gate: no protocol backs USER_METADATA, so "backed" is moot.
    "write-metadata": (
        Capability.USER_METADATA,
        (),
        (),
        False,
        {
            "valid": lambda r: r.write("n", b"N", metadata=META),
            "root": lambda r: r.write("", b"N", metadata=META),
            "refused": lambda r: r.write("/n", b"N", metadata=META),
        },
    ),
    "write_atomic-metadata": (
        Capability.USER_METADATA,
        ("open_write",),
        (Capability.ATOMIC_WRITE,),
        False,
        {
            "valid": lambda r: r.write_atomic("n", b"N", metadata=META),
            "root": lambda r: r.write_atomic("", b"N", metadata=META),
            "refused": lambda r: r.write_atomic("/n", b"N", metadata=META),
        },
    ),
}


def _gate_expected(op: str, declared: bool, backed: bool, closed: bool, key: str) -> Expected:
    """A declared capability decides; the gate ranks per BE-030."""
    metadata = op.endswith("-metadata")
    if declared and not backed and not metadata:
        return "construction"
    if not declared and not metadata:
        return CapabilityNotSupported  # ahead of the closed guard and the key rule
    if closed:
        return BackendUnavailable
    if key == "refused":
        return InvalidPath
    if key == "root":
        return "ok" if op == "glob" else InvalidPath  # a root pattern names a folder: no file
    if not declared:
        return CapabilityNotSupported  # WR-010: after the root refusal, before any I/O
    return "ok"


def _gate_cells() -> list[Any]:
    cells = []
    # Nested, not itertools.product: a product over str and bool axes types every name str | bool.
    for runtime, op in itertools.product(RUNTIMES, GATED):
        for declared, backed, closed in itertools.product((True, False), (True, False), (False, True)):
            _, _, _, sync_only, calls = GATED[op]
            if (sync_only and runtime != "sync") or (op.endswith("-metadata") and not backed):
                continue
            for key in calls:
                posture = ("declared" if declared else "undeclared", "backed" if backed else "unbacked")
                cells.append(
                    pytest.param(
                        runtime,
                        op,
                        declared,
                        backed,
                        closed,
                        key,
                        id="-".join((runtime, op, *posture, "closed" if closed else "open", key)),
                    )
                )
    return cells


@pytest.mark.spec("BE-011")
@pytest.mark.spec("BE-024")
@pytest.mark.spec("BE-030")
@pytest.mark.spec("WR-010")
@pytest.mark.parametrize(("runtime", "op", "declared", "backed", "closed", "key"), _gate_cells())
def test_each_capability_gate_against_declaration_backing_posture_and_key(
    runtime: str, op: str, declared: bool, backed: bool, closed: bool, key: str
) -> None:
    capability, protocols, extra, _, calls = GATED[op]
    caps = BASE_CAPS + extra + ((capability,) if declared else ())
    want = _gate_expected(op, declared, backed, closed, key)
    store = FakeStore(parents="none").add("f", "d/a")

    def build() -> Any:
        return make_kernel(runtime, store, protocols=protocols if backed else (), caps=caps, close_is_terminal=True)

    if want == "construction":
        with pytest.raises(ValueError, match=capability.name):
            build()
        return
    run = build()
    if closed:
        run.close()
    store.calls.clear()
    got, _, _ = _settle(lambda: calls[key](run))
    assert got == want
    if want in (CapabilityNotSupported, BackendUnavailable, InvalidPath):
        assert store.calls == []  # refused before the wire


# ---------------------------------------------------------------------------
# Construction: namespace against parents, and the protocols folder objects need
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-009")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(
    ("namespace", "parents", "makes_parents"),
    list(itertools.product(("flat", "hierarchical"), ("none", "implicit", "explicit"), (True, False))),
)
def test_a_driver_whose_declarations_its_protocols_cannot_back_is_refused(
    runtime: str, namespace: str, parents: str, makes_parents: bool
) -> None:
    # A flat stat cannot see a folder object, so nothing could type one at a key;
    # an explicit driver without ensure_parents could not create BE-009's parents.
    store = FakeStore(parents=parents)
    protocols = (("remove_folder",) if parents != "none" else ()) + (("ensure_parents",) if makes_parents else ())

    def build() -> Any:
        return make_kernel(runtime, store, namespace=namespace, protocols=protocols, exact=True)

    if namespace == "flat" and parents != "none":
        with pytest.raises(ValueError, match="flat"):
            build()
    elif parents == "explicit" and not makes_parents:
        with pytest.raises(ValueError, match="ensure_parents"):
            build()
    else:
        build()
