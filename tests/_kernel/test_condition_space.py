"""Two conditions the kernel decides, generated as cell products in both runtimes.

**A key's type at a call that needs a file.** Every route a call can take
(``write``; ``write_atomic`` by atomic put, wire temporary, temp and rename;
``open_atomic`` by wire temporary and by spool; ``move`` by atomic move,
replacing rename, displace and restore, copy then delete; ``copy``; the
file-shaped reads), crossed with the driver's ``namespace`` and ``parents``,
the state at each key, ``overwrite``, the native shape in which the wire
refuses a folder, and for a two-key call the order in which the wire checks
its keys. **Capability gates.** Each gated operation, crossed with whether the
capability is declared, whether the driver's protocols back it, the close
posture and the key class.

Each product's expected answer is an oracle written from the rule, not from
the code, so a cell fails when the two disagree. The rule, its axes and who
decides each part (the kernel's probes or a driver obligation) are stated in
BK-389's dossier, § Condition space, and in spec 003 BE-030.
"""

from __future__ import annotations

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
    RemoteStoreError,
)
from tests._kernel._fake import (
    RUNTIMES,
    FakeDenied,
    FakeDown,
    FakeExists,
    FakeIsDir,
    FakeMissing,
    FakeOdd,
    FakeStore,
    FakeWireError,
    make_kernel,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# (namespace, parents); flat with folder objects is refused at construction (BE-030).
DRIVERS = {
    "flat-none": ("flat", "none"),
    "hier-none": ("hierarchical", "none"),
    "hier-implicit": ("hierarchical", "implicit"),
    "hier-explicit": ("hierarchical", "explicit"),
}

# How a wire refuses a folder where it needs a file: EISDIR, EEXIST from an
# exclusive create, Windows EACCES, ENOENT, an unrecognised code, a dead service.
SHAPES: dict[str, type[FakeWireError]] = {
    "is-dir": FakeIsDir,
    "exists": FakeExists,
    "denied": FakeDenied,
    "missing": FakeMissing,
    "odd": FakeOdd,
    "down": FakeDown,
}

# One key per state. "d" is a folder (an object with folder objects, a prefix
# without them), "f/x" lies under the file "f".
KEY = {"absent": "n", "file": "f", "folder": "d", "under": "f/x"}
SRC_KEY = {"file": "s", "absent": "m", "folder": "e"}

Expected = type[RemoteStoreError] | str  # an error class, or "ok"


def _store(parents: str, shape: str) -> FakeStore:
    store = FakeStore(parents=parents).add("f", data=b"F").add("s", data=b"S").add("d/x", "e/z")
    store.folder_refusal = SHAPES[shape]
    return store


def _base(parents: str) -> tuple[str, ...]:
    return ("remove_folder", "ensure_parents") if parents != "none" else ()


def _contents(store: FakeStore) -> dict[str, bytes]:
    return {k: r.data for k, r in store.files.items()}


def _settle(call: Callable[[], Any]) -> tuple[Expected, RemoteStoreError | None]:
    try:
        call()
    except RemoteStoreError as err:
        return type(err), err
    return "ok", None


# ---------------------------------------------------------------------------
# Product A: a single-key write onto each state, by every route
# ---------------------------------------------------------------------------


def _open_atomic(run: Any, key: str, overwrite: bool) -> None:
    with run.kernel.open_atomic(key, overwrite=overwrite) as stream:
        stream.write(b"N")


# route -> (call, protocols, put_is_atomic, sync only, stats the target first when overwrite=False)
WRITE_ROUTES: dict[str, tuple[Callable[[Any, str, bool], Any], tuple[str, ...], bool, bool, bool]] = {
    "write": (lambda r, k, o: r.write(k, b"N", overwrite=o), (), False, False, False),
    "write_atomic-put": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), (), True, False, False),
    "write_atomic-handle": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), ("open_write",), False, False, False),
    "write_atomic-rename": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), ("rename",), False, False, True),
    "open_atomic-handle": (_open_atomic, ("open_write",), False, True, False),
    "open_atomic-spool": (_open_atomic, ("rename",), False, True, True),
}


def _write_expected(namespace: str, state: str, overwrite: bool, shape: str, prestat: bool) -> Expected:
    """BE-008's order, with its flat exemption, as BE-030 states it for the kernel."""
    flat = namespace == "flat"
    if state == "absent":
        return "ok"
    if state == "file":
        return "ok" if overwrite else AlreadyExists
    if state == "under":
        return "ok" if flat else InvalidPath
    # A folder: a flat namespace writes a key that shadows a prefix. A hierarchical
    # wire refuses it in its own shape and the kernel types it, unless the shape
    # says nothing about the key (a dead service) and no stat came first.
    if flat:
        return "ok"
    if prestat and not overwrite:
        return InvalidPath
    return BackendUnavailable if shape == "down" else InvalidPath


def _write_cells() -> list[Any]:
    cells = []
    for runtime, route, driver, state, overwrite in itertools.product(
        RUNTIMES, WRITE_ROUTES, DRIVERS, KEY, (False, True)
    ):
        if WRITE_ROUTES[route][3] and runtime != "sync":
            continue
        shapes = SHAPES if state == "folder" and DRIVERS[driver][0] != "flat" else ("is-dir",)
        for shape in shapes:
            cells.append(
                pytest.param(
                    runtime,
                    route,
                    driver,
                    state,
                    overwrite,
                    shape,
                    id="-".join((runtime, route, driver, state, f"ow{int(overwrite)}", shape)),
                )
            )
    return cells


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-010")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize(("runtime", "route", "driver", "state", "overwrite", "shape"), _write_cells())
def test_a_write_onto_each_state_by_every_route(
    runtime: str, route: str, driver: str, state: str, overwrite: bool, shape: str
) -> None:
    call, protocols, put_is_atomic, _, prestat = WRITE_ROUTES[route]
    namespace, parents = DRIVERS[driver]
    store = _store(parents, shape)
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=_base(parents) + protocols, put_is_atomic=put_is_atomic
    )
    key = KEY[state]
    before = _contents(store)
    want = _write_expected(namespace, state, overwrite, shape, prestat)
    got, err = _settle(lambda: call(run, key, overwrite))
    assert got == want
    if err is None:
        assert store.files[key].data == b"N"
        assert {k: v for k, v in _contents(store).items() if k != key} == {k: v for k, v in before.items() if k != key}
    else:
        if want is not BackendUnavailable:
            assert err.path == key
        assert _contents(store) == before  # nothing written, no temporary left
    assert all(h.state != "open" for h in store.handles)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Product B: move and copy, the source and the destination each in every state
# ---------------------------------------------------------------------------

# route -> (op, protocols, rename_replaces)
TRANSFER_ROUTES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "move-atomic": ("move", ("atomic_move",), True),
    "move-rename": ("move", ("rename",), True),
    "move-displace": ("move", ("rename",), False),
    "move-copy-delete": ("move", ("copy",), True),
    "copy": ("copy", ("copy",), True),
}


def _wire_first_refusal(namespace: str, src: str, dst: str, overwrite: bool, shape: str, dst_first: bool) -> str | None:
    """The native refusal a two-key primitive raises first, by the fake wire's rules."""
    src_ref = {"file": None, "absent": "missing", "folder": shape}[src]
    dst_ref = None
    if namespace != "flat" and dst == "folder":
        dst_ref = shape
    elif namespace != "flat" and dst == "under":
        dst_ref = "parent-is-file"
    elif dst == "file" and not overwrite:
        dst_ref = "exists"
    first, second = (dst_ref, src_ref) if dst_first else (src_ref, dst_ref)
    return first or second


def _transfer_expected(
    route: str, namespace: str, parents: str, src: str, dst: str, overwrite: bool, shape: str, dst_first: bool
) -> tuple[Expected, str | None]:
    """BE-018's order: the source's state first, then the destination's, as BE-030 states it.

    A refusal that says nothing about either key (a dead service) passes
    through, unless a determinant check of the kernel's answered first.
    """
    flat = namespace == "flat"
    renames = route in ("move-rename", "move-displace")
    src_first = renames or parents == "explicit"  # the kernel confirms the source before any write
    # The determinants the kernel runs before the wire is reached.
    if src_first and src == "absent":
        return NotFound, "m"
    if src_first and src == "folder":
        return InvalidPath, "e"
    if parents == "explicit" and dst == "under":  # ensure_parents refuses first
        return InvalidPath, "f/x"
    if renames and src == "file" and not flat and dst == "folder":
        return InvalidPath, "d"
    if renames and src == "file" and dst == "file" and not overwrite:
        return AlreadyExists, "f"
    if _wire_first_refusal(namespace, src, dst, overwrite, shape, dst_first) == "down":
        return BackendUnavailable, None
    if src == "absent":
        return NotFound, "m"
    if src == "folder":
        return InvalidPath, "e"
    if not flat and dst in ("folder", "under"):
        return InvalidPath, KEY[dst]
    if dst == "file" and not overwrite:
        return AlreadyExists, "f"
    return "ok", None


def _transfer_cells() -> list[Any]:
    cells = []
    for runtime, route, driver, src, dst, overwrite, dst_first in itertools.product(
        RUNTIMES, TRANSFER_ROUTES, DRIVERS, SRC_KEY, KEY, (False, True), (False, True)
    ):
        namespace = DRIVERS[driver][0]
        folder_hit = src == "folder" or (dst == "folder" and namespace != "flat")
        for shape in SHAPES if folder_hit else ("is-dir",):
            cells.append(
                pytest.param(
                    runtime,
                    route,
                    driver,
                    src,
                    dst,
                    overwrite,
                    dst_first,
                    shape,
                    id="-".join(
                        (
                            runtime,
                            route,
                            driver,
                            f"src_{src}",
                            f"dst_{dst}",
                            f"ow{int(overwrite)}",
                            "dst_first" if dst_first else "src_first",
                            shape,
                        )
                    ),
                )
            )
    return cells


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize(
    ("runtime", "route", "driver", "src", "dst", "overwrite", "dst_first", "shape"), _transfer_cells()
)
def test_a_transfer_between_each_pair_of_states_by_every_route(
    runtime: str, route: str, driver: str, src: str, dst: str, overwrite: bool, dst_first: bool, shape: str
) -> None:
    op, protocols, rename_replaces = TRANSFER_ROUTES[route]
    namespace, parents = DRIVERS[driver]
    store = _store(parents, shape)
    store.dst_first = dst_first
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=_base(parents) + protocols, rename_replaces=rename_replaces
    )
    src_key, dst_key = SRC_KEY[src], KEY[dst]
    before = _contents(store)
    want, want_path = _transfer_expected(route, namespace, parents, src, dst, overwrite, shape, dst_first)
    got, err = _settle(lambda: getattr(run, op)(src_key, dst_key, overwrite=overwrite))
    assert got == want
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
# Product C: the file-shaped reads on each state
# ---------------------------------------------------------------------------


def _read_seekable(run: Any, key: str) -> bytes:
    with run.kernel.read_seekable(key) as stream:
        return bytes(stream.read())


# call -> (call, protocols, sync only, decided by a determinant stat)
READ_CALLS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...], bool, bool]] = {
    "read": (lambda r, k: r.read(k), (), False, False),
    "read_bytes": (lambda r, k: r.read_bytes(k), (), False, False),
    "read_seekable-range": (_read_seekable, ("range",), True, True),
    "read_seekable-spool": (_read_seekable, (), True, False),
    "delete": (lambda r, k: r.delete(k), (), False, False),
    "delete-missing_ok": (lambda r, k: r.delete(k, missing_ok=True), (), False, False),
    "get_file_info": (lambda r, k: r.get_file_info(k), (), False, True),
}


def _read_expected(call: str, state: str, shape: str, determinant: bool) -> Expected:
    """BE-021: a folder is the wrong type on every backend, and outranks ``missing_ok``."""
    if state == "file":
        return "ok"
    if state in ("absent", "under"):
        return "ok" if call == "delete-missing_ok" else NotFound
    if not determinant and shape == "down":
        return BackendUnavailable
    return InvalidPath


def _read_cells() -> list[Any]:
    cells = []
    for runtime, call, driver, state in itertools.product(RUNTIMES, READ_CALLS, DRIVERS, KEY):
        if READ_CALLS[call][2] and runtime != "sync":
            continue
        for shape in SHAPES if state == "folder" else ("is-dir",):
            cells.append(
                pytest.param(runtime, call, driver, state, shape, id=f"{runtime}-{call}-{driver}-{state}-{shape}")
            )
    return cells


@pytest.mark.spec("BE-006")
@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-016")
@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(("runtime", "call", "driver", "state", "shape"), _read_cells())
def test_a_file_shaped_read_on_each_state(runtime: str, call: str, driver: str, state: str, shape: str) -> None:
    fn, protocols, _, determinant = READ_CALLS[call]
    namespace, parents = DRIVERS[driver]
    store = _store(parents, shape)
    run = make_kernel(runtime, store, namespace=namespace, protocols=_base(parents) + protocols)
    key = KEY[state]
    before = _contents(store)
    got, err = _settle(lambda: fn(run, key))
    assert got == _read_expected(call, state, shape, determinant)
    if err is not None and got is not BackendUnavailable:
        assert err.path == key
    if not (call.startswith("delete") and got == "ok" and state == "file"):
        assert _contents(store) == before


# ---------------------------------------------------------------------------
# Product D: capability gates, declared against presented
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
    for runtime, op, declared, backed, closed in itertools.product(
        RUNTIMES, GATED, (True, False), (True, False), (False, True)
    ):
        _, _, _, sync_only, calls = GATED[op]
        if (sync_only and runtime != "sync") or (op.endswith("-metadata") and not backed):
            continue
        for key in calls:
            cells.append(
                pytest.param(
                    runtime,
                    op,
                    declared,
                    backed,
                    closed,
                    key,
                    id="-".join(
                        (
                            runtime,
                            op,
                            "declared" if declared else "undeclared",
                            "backed" if backed else "unbacked",
                            "closed" if closed else "open",
                            key,
                        )
                    ),
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
    got, _ = _settle(lambda: calls[key](run))
    assert got == want
    if want in (CapabilityNotSupported, BackendUnavailable, InvalidPath):
        assert store.calls == []  # refused before the wire


# ---------------------------------------------------------------------------
# Construction: namespace against parents
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(
    ("namespace", "parents"), list(itertools.product(("flat", "hierarchical"), ("none", "implicit", "explicit")))
)
def test_a_flat_driver_with_folder_objects_is_refused(runtime: str, namespace: str, parents: str) -> None:
    # A flat stat cannot see a folder object, so nothing could type one at a key.
    store = FakeStore(parents=parents)
    protocols = ("remove_folder",) if parents != "none" else ()

    def build() -> Any:
        return make_kernel(runtime, store, namespace=namespace, protocols=protocols)

    if namespace == "flat" and parents != "none":
        with pytest.raises(ValueError, match="flat"):
            build()
    else:
        build()
