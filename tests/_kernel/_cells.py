"""Shared machinery of the generated kernel suites: driver shapes, refusal shapes, and the cell runner.

A generated suite is one pytest item per family and runtime. The item builds
every cell of its family, runs each, and fails listing every cell that
disagreed with its oracle, so a family is fast and a failure names them all
(BK-389's dossier, § Re-plan after round 10, decision 13).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from tests._kernel._fake import (
    FakeDenied,
    FakeDown,
    FakeExists,
    FakeIsDir,
    FakeMissing,
    FakeOdd,
    FakeStore,
    FakeWireError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# (namespace, parents): every shape the kernel constructs over. Flat with folder
# objects is refused at construction (A.2), which test_condition_space.py checks.
DRIVERS: dict[str, tuple[str, str]] = {
    "flat-none": ("flat", "none"),
    "hier-none": ("hierarchical", "none"),
    "hier-implicit": ("hierarchical", "implicit"),
    "hier-explicit": ("hierarchical", "explicit"),
}

# A refusal's native shape, and what the fake's classifier types it as. The first
# five are A.8's probe set; BackendUnavailable is a shape outside it.
SHAPES: dict[str, type[FakeWireError]] = {
    "missing": FakeMissing,
    "is-dir": FakeIsDir,
    "exists": FakeExists,
    "denied": FakeDenied,
    "odd": FakeOdd,
    "down": FakeDown,
}
TYPED: dict[str, type[RemoteStoreError]] = {
    "missing": NotFound,
    "is-dir": InvalidPath,
    "exists": AlreadyExists,
    "denied": PermissionDenied,
    "odd": RemoteStoreError,
    "down": BackendUnavailable,
}
PROBE_SET: tuple[type[RemoteStoreError], ...] = (
    NotFound,
    InvalidPath,
    AlreadyExists,
    PermissionDenied,
    RemoteStoreError,
)
MISS: tuple[type[RemoteStoreError], ...] = (NotFound, InvalidPath)

Expected = type[RemoteStoreError] | str  # an error class, or "ok"
Cell = tuple[str, "Callable[[], None]"]  # an id, and the cell's check bound to its axis values


def base_protocols(parents: str) -> tuple[str, ...]:
    """What a driver with folder objects must present; nothing without them."""
    return ("remove_folder", "ensure_parents") if parents != "none" else ()


def settle(call: Callable[[], Any]) -> tuple[Expected, RemoteStoreError | None, Any]:
    """Run *call*: ``("ok", None, value)``, or the mapped error's class, the error and ``None``."""
    try:
        value = call()
    except RemoteStoreError as err:
        return type(err), err, None
    return "ok", None, value


def contents(store: FakeStore) -> dict[str, bytes]:
    """Every stored file's bytes, by raw key."""
    return {k: r.data for k, r in store.files.items()}


def ancestors(key: str) -> list[str]:
    """The slash-aligned ancestors of *key*, shallowest first."""
    parts = key.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def disagreeing(cells: list[Cell]) -> list[str]:
    """Run every cell of a family; each cell that disagreed with the oracle, named.

    An exception other than an assertion is a disagreement too, reported with
    its type, so one broken cell never hides the rest of the family.
    """
    assert cells, "a family generated no cells"
    failures = []
    for cell_id, check in cells:
        try:
            check()
        except AssertionError as exc:
            failures.append(f"{cell_id}: {str(exc).splitlines()[0] if str(exc) else 'assertion failed'}")
        except Exception as exc:  # noqa: BLE001 - reported as the cell's disagreement
            failures.append(f"{cell_id}: raised {type(exc).__name__}: {exc}")
    return failures


def report(failures: list[str], cells: list[Cell]) -> str:
    shown = "\n".join(failures[:60])
    return f"{len(failures)} of {len(cells)} cells disagree with the oracle:\n{shown}"
