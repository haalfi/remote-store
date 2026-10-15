"""The kernel's gates and its construction, as cell products over their own axes, in both runtimes.

What a key resolves to is not here: A.10's two generated suites hold it,
``test_tree_results.py`` (A.5) and ``test_encoding_observations.py`` (A.3,
A.4, A.8). What stays is what no key resolves:

- ``glob`` names no key, so it crosses only the driver and a refusal of the
  glob call before its first match (BE-021's listing bound; A.3 does not
  apply to it);
- the capability gates, declared against presented, across the closed
  guard and the key rule (BE-011, BE-024, BE-030, WR-010);
- construction: ``namespace`` against ``parents``, and the protocols folder
  objects need (A.2, BE-009, BE-031).
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
)
from tests._kernel._cells import DRIVERS, SHAPES, TYPED, Expected, base_protocols, settle
from tests._kernel._fake import RUNTIMES, FakeStore, keys_of, make_kernel

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# glob: the listing bound before its first match
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-024")
@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("driver", list(DRIVERS))
@pytest.mark.parametrize("shape", [None, *SHAPES])
def test_a_glob_refused_before_its_first_match(runtime: str, driver: str, shape: str | None) -> None:
    # A glob names no key, so only the listing bound applies: a NotFound before
    # the first match is an empty result, any other refusal propagates.
    namespace, parents = DRIVERS[driver]
    store = FakeStore(parents=parents).add("f", "d/x", "e/z")
    if shape is not None:
        store.fault("glob", SHAPES[shape]("d/*"))
    run = make_kernel(runtime, store, namespace=namespace, protocols=(*base_protocols(parents), "glob"))
    got, err, listed = settle(lambda: keys_of(run.glob("d/*")))
    if shape is None:
        assert listed == ["d/x"]
    elif TYPED[shape] is NotFound:
        assert listed == []
    else:
        assert got == TYPED[shape], err
        assert err is not None
        assert err.path == "d/*"


# ---------------------------------------------------------------------------
# Capability gates, declared against presented
# ---------------------------------------------------------------------------

BASE_CAPS = (Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE)
META = {"k": "v"}


def _open_atomic(run: Any, key: str) -> None:
    with run.kernel.open_atomic(key) as stream:
        stream.write(b"N")


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
            "valid": lambda r: _open_atomic(r, "n"),
            "root": lambda r: _open_atomic(r, ""),
            "refused": lambda r: _open_atomic(r, "/n"),
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
    got, _, _ = settle(lambda: calls[key](run))
    assert got == want
    if want in (CapabilityNotSupported, BackendUnavailable, InvalidPath):
        assert store.calls == []  # refused before the wire


# ---------------------------------------------------------------------------
# Construction: namespace against parents, and the protocols folder objects need
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-009")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(
    ("namespace", "parents", "makes_parents"),
    list(itertools.product(("flat", "hierarchical"), ("none", "implicit", "explicit"), (True, False))),
)
def test_a_driver_whose_declarations_its_protocols_cannot_back_is_refused(
    runtime: str, namespace: str, parents: str, makes_parents: bool
) -> None:
    # A.2: a flat stat cannot see a folder object, so nothing could type one at a key;
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
        built = build()
        assert built.kernel.capabilities is built.driver.capabilities
