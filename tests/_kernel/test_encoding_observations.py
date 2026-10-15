"""What a driver observes of an encoding, and how the kernel answers from it (BE-032 A.3, A.4, A.8), in both runtimes.

The second of A.10's two generated suites: encoding property × raw state ×
refusal shape × what the error-path probe does.

- **Encoding property:** ``namespace`` × ``parents`` (``_cells.DRIVERS``).
- **Raw state:** the tree's rows (an item, a folder holding a file, an empty
  folder where folder objects exist, nothing, nothing below an absent
  folder, a key through an item), a folder holding a stored key BE-030
  omits (``w/b\\c``) and one holding only such a key, the root for the
  listings, a link to a folder on a hierarchical wire, and on a flat wire
  the state that decodes to no tree: an item ``g`` with raw entries below
  ``g/``, the raw entry ``g/a`` below it, the prefix ``g/b`` below it, and a
  folder ``p`` whose listing returns the item ``p/g`` and the prefix
  ``p/g/`` on one page (with ``p/g.t`` between them in byte order).
- **Refusal shape:** none (the wire answers as its raw state makes it), or
  one injected on the call's primitive: the probe set (``NotFound``,
  ``InvalidPath``, ``AlreadyExists``, ``PermissionDenied``, untyped) and
  ``BackendUnavailable``, outside it.
- **What the probes do** (every ``stat`` and every ``list_page(limit=1)``):
  answer; raise a miss (``NotFound``, ``InvalidPath``); raise a non-miss in
  the probe set (``PermissionDenied``, untyped); raise ``BackendUnavailable``;
  or deny only the ``stat`` of the cell's own key(s), ancestors answering;
  or, in a transfer, deny only the source's ``stat``; or, where a probe
  listing can run (a flat driver, ``delete_folder``), let
  ``stat`` answer and have the listing raise a miss, a denial or
  ``BackendUnavailable``, or come back empty as if the prefix was emptied
  under the call. With an injected refusal the probes misbehave only after
  it fired, so a determinant run before the call answers truthfully and only
  the error-path probes are tested; without one they misbehave from the
  start, so every determinant is tested failing closed (A.8 rule 3).

The oracle is A.8's per-call tables and rules 1 to 4, A.3's listing and
flat-folder rules and A.4's flat write checks, written as ``_get_row``,
``_put_row``, ``_parents_row``, ``_first_page_empty``, ``_df_row``,
``_df_flat_tree_row`` and ``_df_empty``. It reads the raw state through
``_Raw``, a model of what one ``stat`` or one ``list_page`` of the encoding
observes, never through the kernel. The implementation choices the kernel
made where Appendix A is silent are part of the oracle, each marked where it
is used: a hierarchical ``stat`` that raises a non-miss in the probe set is
followed by the ancestors' ``stat`` calls, an ancestor that cannot answer
being skipped; a listing of the root reads only a miss as empty; ``delete``
and a ``move`` source probe without following a link. Where the kernel
disagrees with the oracle, the cells are declared in ``DEVIATIONS`` with
the clause, and must keep failing exactly so until the kernel is changed.

Not crossed here: ``glob`` (``test_condition_space.py``; it applies no A.3),
the displace-and-restore ``move`` route (its synthesised retry of a missed
file is ``test_kernel.py``'s; its A.5 answers are ``test_tree_results.py``'s),
and a link at a write or a listing key (A.7, which the fake's links do not
model past ``stat``). A ``get_folder_info`` push-down over a state whose
listing omits a key is not crossed: BE-032 A.8 obliges the driver's
``folder_stats`` to omit what the listing omits, which the fake's does not,
so such a cell would test the fake.

**No Memory column.** The Memory drivers, the first real ones on the kernel,
run in ``test_tree_results.py`` and not here, because none of this suite's
axes reaches them past what that suite already asserts. Their tree raises only
typed errors and never faults (the one native exception, content ``put``
cannot read, is not a tree state), so no refusal shape can be injected and no probe can
misbehave: the refusal axis is ``none`` and the probe axis ``answers`` only.
They are hierarchical with implicit parents and hold only what is written
through the kernel, whose key rule refuses a backslash, so the states with a
key BE-030 omits, the flat states that decode to no tree and the link do not
apply. What is left, an item, a folder, an empty folder, nothing and a key
through an item, is A.5's rows, which ``test_tree_results.py`` asserts against
both Memory drivers; repeating them here would add cells that test nothing new.
"""

from __future__ import annotations

import functools
import logging
import re
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._kernel._model import Page
from tests._kernel._cells import (
    DRIVERS,
    MISS,
    PROBE_SET,
    SHAPES,
    TYPED,
    Cell,
    Expected,
    ancestors,
    base_protocols,
    contents,
    disagreeing,
    report,
    settle,
)
from tests._kernel._fake import (
    RUNTIMES,
    FakeDenied,
    FakeDown,
    FakeIsDir,
    FakeMissing,
    FakeOdd,
    FakeStore,
    FakeWireError,
    keys_of,
    make_kernel,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ITEM, FOLDER, NOTHING = "Item", "Folder", "Nothing"
STANDS = "the refusal stands"

# ---------------------------------------------------------------------------
# The raw states
# ---------------------------------------------------------------------------

FILES: dict[str, bytes] = {
    "f": b"F",
    "s": b"S",
    "d/x": b"X",
    "e/z": b"Z",
    "w/a": b"A",
    "w/b\\c": b"BB",  # a stored key BE-030 omits (BK-399's case)
    "v/b\\c": b"VVV",
}
# A flat wire's raw entries that decode to no tree: an item with entries below it.
FLAT_FILES: dict[str, bytes] = {
    "g": b"G",
    "g/a": b"ga",
    "g/b/c": b"gbc",
    "p/g": b"1",
    "p/g.t": b"22",  # sorts between p/g and p/g/
    "p/g/a": b"333",
    "p/g/b/c": b"4444",
    "p/h": b"55555",
}
EMPTY_FOLDERS = ("z",)  # with folder objects only (A.6)
LINKS = {"l": "d"}  # a link to a folder, on a hierarchical wire

ALL, OBJECTS, FLAT, HIER = "all", "objects", "flat", "hier"
# state -> (key, the drivers that can hold it)
STATES: dict[str, tuple[str, str]] = {
    "root": ("", ALL),
    "nothing": ("n", ALL),
    "nothing-deep": ("n/q", ALL),
    "item": ("f", ALL),
    "folder": ("d", ALL),
    "empty": ("z", OBJECTS),
    "through": ("f/x", ALL),
    "holds-omitted": ("w", ALL),
    "holds-only-omitted": ("v", ALL),
    "item-over-prefix": ("g", FLAT),
    "below-item": ("g/a", FLAT),
    "prefix-below-item": ("g/b", FLAT),
    "holds-item-over-prefix": ("p", FLAT),
    "link": ("l", HIER),
}


def _states(driver: str, *, exclude: tuple[str, ...] = ()) -> list[str]:
    namespace, parents = DRIVERS[driver]
    ok = {ALL: True, OBJECTS: parents != "none", FLAT: namespace == "flat", HIER: namespace != "flat"}
    return [s for s, (_, where) in STATES.items() if ok[where] and s not in exclude]


KEYED = ("root",)  # the root is a folder; only the listings name it
NO_LINK = ("root", "link")

# ---------------------------------------------------------------------------
# What the probes do
# ---------------------------------------------------------------------------

# mode -> (what every stat does, what every list_page(limit=1) does): raise that native class,
# "key" (only the cell's own keys' stat is denied), "first" (only the first subject's stat, a
# transfer's source, is denied), "empty" (an empty page, as after the prefix
# was emptied under the call), or None (answer as the raw state is).
MODE_EFFECTS: dict[str, tuple[type[FakeWireError] | str | None, type[FakeWireError] | str | None]] = {
    "answers": (None, None),
    "miss_nf": (FakeMissing, FakeMissing),
    "miss_ip": (FakeIsDir, FakeIsDir),
    "denied": (FakeDenied, FakeDenied),
    "odd": (FakeOdd, FakeOdd),
    "down": (FakeDown, FakeDown),
    "key_denied": ("key", None),
    "src_denied": ("first", None),
    "list_miss": (None, FakeMissing),
    "list_denied": (None, FakeDenied),
    "list_down": (None, FakeDown),
    "list_empty": (None, "empty"),
}
# A probe listing runs only on a flat driver, or in delete_folder; elsewhere these modes are unreachable.
LIST_ONLY = ("list_miss", "list_denied", "list_down", "list_empty")
# Only the first subject's stat is denied, the source of a transfer; elsewhere it is key_denied again.
TRANSFER_ONLY = ("src_denied",)
MODES = tuple(MODE_EFFECTS)
NATIVE_TYPED: dict[object, type[RemoteStoreError]] = {
    FakeMissing: NotFound,
    FakeIsDir: InvalidPath,
    FakeDenied: PermissionDenied,
    FakeOdd: RemoteStoreError,
    FakeDown: BackendUnavailable,
}


class _Wire(FakeStore):
    """The fake wire, whose probes misbehave by *mode* once armed.

    ``stat`` and ``list_page(limit=1)`` are the probe calls: the second is
    how the kernel asks whether a folder is empty or a flat prefix holds
    anything, and no call's own listing asks for one entry, except
    ``delete_folder``'s first listing without folder objects, which the
    oracle reads as such.
    """

    def __init__(self, *, parents: str, page_size: int = 1000) -> None:
        super().__init__(parents=parents, page_size=page_size)
        self.mode = "answers"
        self.subjects: frozenset[str] = frozenset()
        self.first: str | None = None
        self.lying = False
        self.stat_fault = self._stat_fault

    def arm(self) -> None:
        self.lying = True

    def _stat_fault(self, key: str) -> type[FakeWireError] | None:
        effect = MODE_EFFECTS[self.mode][0] if self.lying else None
        if effect == "key":
            return FakeDenied if key in self.subjects else None
        if effect == "first":
            return FakeDenied if key == self.first else None
        return effect  # type: ignore[return-value]

    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: Any = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Any:
        effect = MODE_EFFECTS[self.mode][1] if self.lying and limit == 1 else None
        if effect is not None:
            self.calls.append(("list_page", prefix))
            if effect == "empty":
                return Page(entries=(), prefixes=(), cursor=None)
            raise effect(prefix)  # type: ignore[operator]
        return super().list_page(prefix, delimiter=delimiter, cursor=cursor, limit=limit, follow_links=follow_links)


def _wire(driver: str, *, page_size: int = 1000, link: bool = False) -> _Wire:
    namespace, parents = DRIVERS[driver]
    store = _Wire(parents=parents, page_size=page_size)
    for key, data in FILES.items():
        store.add(key, data=data)
    if namespace == "flat":
        for key, data in FLAT_FILES.items():
            store.add(key, data=data)
    if parents != "none":
        store.add(*(f"{k}/" for k in EMPTY_FOLDERS))
    if link:
        store.links.update(LINKS)
    return store


# ---------------------------------------------------------------------------
# The oracle: what one driver call observes of the raw state
# ---------------------------------------------------------------------------


def _listable(key: str) -> bool:
    # The raw states hold one kind of key BE-030 omits: one with a backslash.
    return "\\" not in key


class _Raw:
    """What one ``stat`` or one ``list_page(k, limit=1)`` of the encoding observes.

    A hierarchical ``stat`` sees an item or a folder, and nothing below an
    item; a flat one sees an item, at any key, and never a folder. A
    listing with folder objects refuses a key that is no folder.
    """

    def __init__(self, driver: str, *, link: bool = False) -> None:
        namespace, self.parents = DRIVERS[driver]
        self.flat = namespace == "flat"
        self.files = dict(FILES) | (dict(FLAT_FILES) if self.flat else {})
        self.links = dict(LINKS) if link else {}
        objects: set[str] = set()
        if self.parents != "none":
            objects.update(EMPTY_FOLDERS)
            for key in self.files:
                objects.update(ancestors(key))
        self.objects = objects

    def without(self, keys: set[str]) -> _Raw:
        """This state after *keys* were deleted; folder objects persist (BE-031)."""
        copy = object.__new__(_Raw)
        copy.__dict__.update(self.__dict__)
        copy.files = {k: v for k, v in self.files.items() if k not in keys}
        return copy

    def with_parents(self, key: str) -> _Raw:
        """This state after ``ensure_parents(key)`` made *key*'s missing folders (folder objects only)."""
        copy = object.__new__(_Raw)
        copy.__dict__.update(self.__dict__)
        copy.objects = self.objects | set(ancestors(key))
        return copy

    def through(self, key: str) -> bool:
        return any(a in self.files for a in ancestors(key))

    def stat(self, key: str, follow: bool = True) -> str | None:
        if key in self.links:
            if not follow:
                return "file"
            key = self.links[key]
        if self.flat:
            return "file" if key in self.files else None
        if self.through(key):
            return None
        if key in self.files:
            return "file"
        if key in self.objects:
            return "folder"
        if self.parents == "none" and any(f.startswith(key + "/") for f in self.files):
            return "folder"
        return None

    def holds(self, key: str) -> bool | type[RemoteStoreError]:
        """``list_page(k, limit=1)``: whether anything lies below *key*, or the listing's refusal."""
        if not self.flat and self.parents != "none" and key and self.stat(key) != "folder":
            return NotFound
        key = self.links.get(key, key)
        base = key + "/" if key else ""
        return any(x.startswith(base) for x in [*self.files, *self.objects])

    def under(self, key: str) -> list[str]:
        base = key + "/" if key else ""
        return [x for x in self.files if x.startswith(base)]

    def below_an_item(self, key: str, within: list[str]) -> bool:
        """A.3: a flat listing omits a key below an item it listed."""
        return self.flat and any(y != key and key.startswith(y + "/") for y in within)


class _Sim:
    """The cell's wire as the oracle sees it: the raw state, the probe mode, the injection.

    Mirrors ``_Wire``'s arming: the probes misbehave from the start without
    an injected refusal, and after it fired with one.
    """

    def __init__(self, raw: _Raw, mode: str, subjects: tuple[str, ...], inject: tuple[str, type] | None) -> None:
        self.raw, self.mode, self.subjects = raw, mode, subjects
        self.inject = inject
        self.lying = inject is None

    def fire(self, prim: str) -> type[RemoteStoreError] | None:
        if self.inject is not None and self.inject[0] == prim:
            cls = self.inject[1]
            self.inject = None
            self.lying = True
            return cls
        return None

    def stat(self, key: str, follow: bool = True) -> str | None | type[RemoteStoreError]:
        effect = MODE_EFFECTS[self.mode][0] if self.lying else None
        if effect == "key":
            return PermissionDenied if key in self.subjects else self.raw.stat(key, follow)
        if effect == "first":
            return PermissionDenied if key == self.subjects[0] else self.raw.stat(key, follow)
        return self.raw.stat(key, follow) if effect is None else NATIVE_TYPED[effect]

    def holds(self, key: str) -> bool | type[RemoteStoreError]:
        effect = MODE_EFFECTS[self.mode][1] if self.lying else None
        if effect == "empty":
            return False
        return self.raw.holds(key) if effect is None else NATIVE_TYPED[effect]


def _err(obs: object) -> bool:
    return isinstance(obs, type)


def _above(sim: _Sim, key: str) -> str | None:
    """Implementation choice: a hierarchical key's ancestors, shallowest first.

    An item among them puts the key through an item; a missing one makes
    it absent; one that cannot answer is skipped. ``None``: no conclusion.
    """
    for ancestor in ancestors(key):
        seen = sim.stat(ancestor)
        if _err(seen):
            if seen in MISS:
                return "absent"
            continue
        if seen is None:
            return "absent"
        if seen == "file":
            return "through"
    return None


def _node(sim: _Sim, key: str, *, follow: bool = True, folders: bool = True) -> str | type[RemoteStoreError]:
    """The row one key's probes conclude, or the error of a probe that cannot answer.

    A.8: a hierarchical ``stat`` sees an item or a folder, and a miss is
    ``None``, a ``NotFound`` or an ``InvalidPath``. A flat ``stat`` sees an
    item, and a miss is followed (where the call needs a folder) by
    ``list_page(k, limit=1)``, whose ``NotFound`` or ``InvalidPath`` is an
    empty listing by the flat listing obligation.
    """
    seen = sim.stat(key, follow)
    if seen == "file":
        return ITEM
    if seen == "folder":
        return FOLDER
    if seen is None or seen in MISS:
        if not sim.raw.flat or not folders:
            return NOTHING
        held = sim.holds(key)
        if _err(held):
            return NOTHING if held in MISS else held  # type: ignore[return-value]
        return FOLDER if held else NOTHING
    if not sim.raw.flat and seen in PROBE_SET and _above(sim, key) is not None:
        return NOTHING  # implementation choice: the ancestors answered for the key
    return seen  # type: ignore[return-value]


# A.8's per-call tables. Each answers after a refusal in the probe set: STANDS, or the
# A.5 result of the row the probes conclude where the call must refuse there (rule 4).


def _get_row(sim: _Sim, key: str, *, entry: bool) -> str | type[RemoteStoreError]:
    """``get``, ``delete``, a transfer's source: an item stands, a folder ``InvalidPath``, nothing ``NotFound``.

    *entry*: ``delete`` and a ``move`` source name the entry, so the
    ``stat`` does not follow a link (A.7; the kernel's stated choice).
    """
    node = _node(sim, key, follow=not entry)
    if _err(node) or node == ITEM:
        return STANDS  # a probe that cannot answer fails open; an item is a success row
    return InvalidPath if node == FOLDER else NotFound


def _put_row(sim: _Sim, key: str, overwrite: bool) -> str | type[RemoteStoreError]:
    """A write primitive at *key*: a folder or an item above is ``InvalidPath``.

    An item without overwrite is ``AlreadyExists``. Flat: A.4's checks ran
    first, so only the item is left to find.
    """
    seen = sim.stat(key)
    if sim.raw.flat:
        return AlreadyExists if seen == "file" and not overwrite else STANDS
    if seen == "folder":
        return InvalidPath
    if seen == "file":
        return STANDS if overwrite else AlreadyExists
    if seen is None or seen in PROBE_SET:  # a miss, or (implementation choice) a non-miss: the ancestors
        return InvalidPath if _above(sim, key) == "through" else STANDS
    return STANDS


def _parents_row(sim: _Sim, key: str) -> str | type[RemoteStoreError]:
    """``ensure_parents``: an item among the ancestors is ``InvalidPath``."""
    return InvalidPath if _above(sim, key) == "through" else STANDS


def _first_page_empty(sim: _Sim, key: str, refusal: type[RemoteStoreError], *, follow: bool = True) -> bool:
    """A listing's first page: whether its refusal reads as an empty listing.

    Flat: a ``NotFound`` or ``InvalidPath`` does (the flat listing
    obligation), nothing else. Hierarchical: a refusal in the probe set
    does unless ``stat(k)`` sees a folder or cannot answer. The root
    (implementation choice): a miss does, nothing else, and no ``stat``.
    """
    if not key or sim.raw.flat:
        return refusal in MISS
    if refusal not in PROBE_SET:
        return False
    node = _node(sim, key, follow=follow)
    return not _err(node) and node != FOLDER


def _df_row(sim: _Sim, key: str, *, remove: bool) -> str | type[RemoteStoreError]:
    """``remove_folder`` (*remove*) and ``delete_tree`` with folder objects, hierarchical."""
    node = _node(sim, key, follow=False)
    if _err(node):
        return STANDS
    if node == ITEM:
        return InvalidPath
    if node == NOTHING:
        return NotFound
    if remove:
        held = sim.holds(key)
        if held is True:
            return DirectoryNotEmpty
    return STANDS


def _df_flat_tree_row(sim: _Sim, key: str) -> str | type[RemoteStoreError]:
    """``delete_tree`` without folder objects: ``list_page(k, limit=1)`` first, ``stat(k)`` after an empty one.

    The listing's ``NotFound`` or ``InvalidPath`` is an empty listing on a
    flat wire (the flat listing obligation, which binds only flat drivers);
    on a hierarchical one it is a probe that cannot answer.
    """
    held = sim.holds(key)
    if _err(held):
        if not (sim.raw.flat and held in MISS):
            return STANDS
    elif held:
        return STANDS
    node = _node(sim, key, follow=False, folders=False)
    if _err(node):
        return STANDS
    return {ITEM: InvalidPath, NOTHING: NotFound}.get(node, STANDS)  # type: ignore[call-overload]


def _df_empty(sim: _Sim, key: str) -> type[RemoteStoreError]:
    """After an empty listing without folder objects: an item ``InvalidPath``, anything else ``NotFound``.

    Hierarchical only; on a flat wire A.3's ``stat`` already ruled an item
    out. The ``stat`` fails open.
    """
    if not sim.raw.flat and _node(sim, key, follow=False) == ITEM:
        return InvalidPath
    return NotFound


def _answer(refusal: type[RemoteStoreError], row: str | type[RemoteStoreError]) -> type[RemoteStoreError]:
    """Rule 4: the row's result replaces a refusal in the probe set; anything else passes unprobed."""
    if refusal not in PROBE_SET or row == STANDS:
        return refusal
    return row  # type: ignore[return-value]


def _a4(sim: _Sim, key: str) -> tuple[type[RemoteStoreError], str] | None:
    """A.4's flat write checks, determinants that fail closed: one ``stat`` per ancestor, one ``list_page``.

    The answer, and the key its error names: a check that cannot answer
    names the key it was asked about, an ancestor's ``stat`` its ancestor.
    """
    for ancestor in ancestors(key):
        seen = sim.stat(ancestor)
        if _err(seen):
            if seen in MISS:
                continue
            return seen, ancestor  # type: ignore[return-value]
        if seen == "file":
            return InvalidPath, key
    held = sim.holds(key)
    if _err(held):
        return None if held in MISS else (held, key)  # type: ignore[return-value]
    return (InvalidPath, key) if held else None


# ---------------------------------------------------------------------------
# The cell harness
# ---------------------------------------------------------------------------


class _Omissions(logging.Handler):
    """The omission records the kernel logs (BE-030, A.3)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.counts: list[int] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if " omitted " in message:
            self.counts.append(int(message.split(" omitted ", 1)[1].split(" ", 1)[0]))


def _logged(call: Callable[[], Any]) -> tuple[tuple[Expected, RemoteStoreError | None, Any], list[int]]:
    logger = logging.getLogger("remote_store._kernel")
    handler = _Omissions()
    logger.addHandler(handler)
    try:
        return settle(call), handler.counts
    finally:
        logger.removeHandler(handler)


def _refusals(prims: tuple[str, ...]) -> list[tuple[str, str] | None]:
    """None, then each shape on each primitive the call reaches."""
    return [None, *((prim, shape) for prim in prims for shape in SHAPES)]


def _modes(refusal: tuple[str, str] | None, *, lists: bool, transfer: bool = False) -> tuple[str, ...]:
    """What the probes do, where it can be reached.

    A refusal outside the probe set is never probed; a probe listing runs
    only where *lists* (a flat driver, or ``delete_folder``); a denial of the
    source's ``stat`` alone only in a *transfer*.
    """
    if refusal is not None and refusal[1] == "down":
        return ("answers",)
    return tuple(m for m in MODES if (lists or m not in LIST_ONLY) and (transfer or m not in TRANSFER_ONLY))


def _lists(driver: str) -> bool:
    return DRIVERS[driver][0] == "flat"


def _arm(
    store: _Wire,
    mode: str,
    subjects: tuple[str, ...],
    refusal: tuple[str, str] | None,
    fault_key: str | None,
) -> None:
    store.mode = mode
    store.subjects = frozenset(subjects)
    store.first = subjects[0] if subjects else None
    if refusal is None:
        store.lying = True
        return
    prim, shape = refusal
    store.fault(prim, SHAPES[shape](fault_key or prim), key=fault_key, hook=store.arm)


def _sim(
    driver: str, mode: str, subjects: tuple[str, ...], refusal: tuple[str, str] | None, *, link: bool = False
) -> _Sim:
    inject = None if refusal is None else (refusal[0], TYPED[refusal[1]])
    return _Sim(_Raw(driver, link=link), mode, subjects, inject)


def _rid(refusal: tuple[str, str] | None) -> str:
    return "none" if refusal is None else f"{refusal[0]}_{refusal[1]}"


# Where the kernel disagrees with Appendix A: reported, not fixed here, since the kernel is not
# this suite's to change. Each entry is (the cells, by id; the kernel's answer there, by the
# failure's ``_vs`` message; the clause). A cell it matches must fail exactly so, and an entry that
# matches no failing cell is stale and fails its family: fixing the kernel means deleting it.
DEVIATIONS: tuple[tuple[str, str, str], ...] = ()


def _vs(got: Expected, want: Expected, err: RemoteStoreError | None) -> str:
    def name(answer: Expected) -> str:
        return answer if isinstance(answer, str) else answer.__name__

    return f"kernel {name(got)}, oracle {name(want)}: {err} "


def _failures(cells: list[Cell]) -> list[str]:
    """Each cell that disagrees with the oracle other than as a declared deviation, and each stale deviation."""
    failures = [tuple(f.split(": ", 1)) for f in disagreeing(cells)]

    def declared(cell_id: str, message: str, deviation: tuple[str, str, str]) -> bool:
        return bool(re.search(deviation[0], cell_id) and re.search(deviation[1], message))

    problems = [f"{i}: {m}" for i, m in failures if not any(declared(i, m, d) for d in DEVIATIONS)]
    ids = [cell_id for cell_id, _ in cells]
    for deviation in DEVIATIONS:
        reached = any(re.search(deviation[0], i) for i in ids)
        if reached and not any(declared(i, m, deviation) for i, m in failures):
            problems.append(f"stale deviation, the kernel now agrees: {deviation[2]}")
    return problems


def _caused_by(err: RemoteStoreError, refusal: tuple[str, str] | None, store: _Wire) -> None:
    """A replaced refusal is chained: the answer is raised from the driver's own refusal.

    Only once that refusal fired (``store.lying``): before it, a determinant answers on its own.
    """
    if refusal is not None and store.lying and type(err) is not TYPED[refusal[1]]:
        assert type(err.__cause__) is TYPED[refusal[1]], f"{type(err).__name__} not raised from the refusal"


# ---------------------------------------------------------------------------
# probe: exists, is_file, is_folder (determinants only: A.8 rule 1)
# ---------------------------------------------------------------------------

PROBES: dict[str, Callable[[Any, str], Any]] = {
    "exists": lambda r, k: r.exists(k),
    "is_file": lambda r, k: r.is_file(k),
    "is_folder": lambda r, k: r.is_folder(k),
}


def _probe_oracle(call: str, sim: _Sim, key: str) -> tuple[Expected, Any]:
    node = _node(sim, key, folders=call != "is_file")
    if _err(node):
        return node, None  # type: ignore[return-value]
    if call == "exists":
        return "ok", node in (ITEM, FOLDER)
    return "ok", node == (ITEM if call == "is_file" else FOLDER)


def _check_probe(runtime: str, call: str, driver: str, state: str, mode: str) -> None:
    namespace, parents = DRIVERS[driver]
    key = STATES[state][0]
    link = state == "link"
    store = _wire(driver, link=link)
    _arm(store, mode, (key,), None, None)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents))
    want, value = _probe_oracle(call, _sim(driver, mode, (key,), None, link=link), key)
    before = contents(store)
    got, err, answered = settle(lambda: PROBES[call](run, key))
    assert got == want, _vs(got, want, err)
    if err is None:
        assert answered is value
    else:
        assert err.path == key
    assert contents(store) == before


@pytest.mark.spec("BE-004")
@pytest.mark.spec("BE-005")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_probe_is_a_determinant_over_every_raw_state(runtime: str) -> None:
    cells = [
        (f"{call}-{driver}-{state}-{mode}", functools.partial(_check_probe, runtime, call, driver, state, mode))
        for call in PROBES
        for driver in DRIVERS
        for state in _states(driver, exclude=KEYED)
        for mode in _modes(None, lists=_lists(driver))
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# read-file and delete-file: read, read_bytes, read_seekable, get_file_info, delete
# ---------------------------------------------------------------------------


def _read_seekable(run: Any, key: str) -> bytes:
    with run.kernel.read_seekable(key) as stream:
        return bytes(stream.read())


def _file_info(run: Any, key: str) -> tuple[str, int]:
    info = run.get_file_info(key)
    return str(info.path), info.size


# call -> (call, protocols, sync only, the primitives a refusal is injected on)
READS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...], bool, tuple[str, ...]]] = {
    "read": (lambda r, k: r.read(k), (), False, ("get",)),
    "read_bytes": (lambda r, k: r.read_bytes(k), (), False, ("get",)),
    "read_seekable-spool": (_read_seekable, (), True, ("get",)),
    "read_seekable-range": (_read_seekable, ("range",), True, ("get_range",)),
    "get_file_info": (_file_info, (), False, ()),
    "delete": (lambda r, k: r.delete(k), (), False, ("delete",)),
    "delete-missing_ok": (lambda r, k: r.delete(k, missing_ok=True), (), False, ("delete",)),
}


def _read_oracle(call: str, sim: _Sim, key: str) -> tuple[Expected, Any]:
    raw = sim.raw
    target = raw.links.get(key, key)
    if call in ("get_file_info", "read_seekable-range"):
        # Determinants: get_file_info, and a ranged read_seekable's stat (A.8 rule 1).
        node = _node(sim, key)
        if _err(node):
            return node, None  # type: ignore[return-value]
        if node != ITEM:
            return (InvalidPath if node == FOLDER else NotFound), None
        if call == "get_file_info":
            return "ok", (key, len(raw.files[target]))
        refused = sim.fire("get_range")
        return (refused, None) if refused is not None else ("ok", raw.files[target])
    deleting = call.startswith("delete")
    refusal = sim.fire("delete" if deleting else "get")
    if refusal is None:
        if (key in raw.links or key in raw.files) if deleting else target in raw.files:
            return "ok", (None if deleting else raw.files[target])
        refusal = NotFound  # the wire's own refusal: ENOENT
    answer = _answer(refusal, _get_row(sim, key, entry=deleting) if refusal in PROBE_SET else STANDS)
    if call == "delete-missing_ok" and answer is NotFound:
        return "ok", "absorbed"
    return answer, None


def _check_read(runtime: str, call: str, driver: str, state: str, refusal: tuple[str, str] | None, mode: str) -> None:
    fn, protocols, _, _ = READS[call]
    namespace, parents = DRIVERS[driver]
    key = STATES[state][0]
    link = state == "link"
    store = _wire(driver, link=link)
    _arm(store, mode, (key,), refusal, key)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols)
    want, value = _read_oracle(call, _sim(driver, mode, (key,), refusal, link=link), key)
    before = contents(store)
    got, err, answered = settle(lambda: fn(run, key))
    assert got == want, _vs(got, want, err)
    if err is not None:
        assert err.path == key
        _caused_by(err, refusal, store)
        assert contents(store) == before
    elif call.startswith("delete"):
        removed = {key} if value is None else set()
        assert contents(store) == {k: v for k, v in before.items() if k not in removed}
    else:
        assert answered == value
        assert contents(store) == before


@pytest.mark.spec("BE-006")
@pytest.mark.spec("BE-007")
@pytest.mark.spec("BE-012")
@pytest.mark.spec("BE-016")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_read_or_delete_answers_its_refusals_by_the_get_and_delete_rows(runtime: str) -> None:
    cells = [
        (
            f"{call}-{driver}-{state}-{_rid(refusal)}-{mode}",
            functools.partial(_check_read, runtime, call, driver, state, refusal, mode),
        )
        for call, (_, _, sync_only, prims) in READS.items()
        if runtime == "sync" or not sync_only
        for driver in DRIVERS
        for state in _states(driver, exclude=KEYED)
        for refusal in _refusals(prims)
        for mode in _modes(refusal, lists=_lists(driver))
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# write-file: write, write_atomic and open_atomic, with A.4's flat checks
# ---------------------------------------------------------------------------


def _open_atomic(run: Any, key: str, overwrite: bool) -> None:
    with run.kernel.open_atomic(key, overwrite=overwrite) as stream:
        stream.write(b"N")


# route -> (call, protocols, put_is_atomic, sync only, the primitives in call order)
WRITES: dict[str, tuple[Callable[[Any, str, bool], Any], tuple[str, ...], bool, bool, tuple[str, ...]]] = {
    "write": (lambda r, k, o: r.write(k, b"N", overwrite=o), (), False, False, ("put",)),
    "write_atomic-put": (lambda r, k, o: r.write_atomic(k, b"N", overwrite=o), (), True, False, ("put",)),
    "write_atomic-handle": (
        lambda r, k, o: r.write_atomic(k, b"N", overwrite=o),
        ("open_write",),
        False,
        False,
        ("open_write", "handle.commit"),
    ),
    "write_atomic-rename": (
        lambda r, k, o: r.write_atomic(k, b"N", overwrite=o),
        ("rename",),
        False,
        False,
        ("put", "rename"),
    ),
    "open_atomic-handle": (_open_atomic, ("open_write",), False, True, ("open_write", "handle.commit")),
}


def _wire_put_refusal(raw: _Raw, key: str, overwrite: bool) -> type[RemoteStoreError] | None:
    """What a wire's write refuses natively: a hierarchical folder or item above, and an item without overwrite."""
    if not raw.flat and (raw.through(key) or raw.stat(key) == "folder"):
        return InvalidPath  # EISDIR, or ENOTDIR on the write path
    if key in raw.files and not overwrite:
        return AlreadyExists
    return None


def _write_oracle(route: str, sim: _Sim, key: str, overwrite: bool) -> tuple[Expected, str]:
    """The answer, and the key its error names."""
    if sim.raw.flat:
        checked = _a4(sim, key)
        if checked is not None:
            return checked
    return _write_after_checks(route, sim, key, overwrite), key


def _write_after_checks(route: str, sim: _Sim, key: str, overwrite: bool) -> Expected:
    raw = sim.raw
    prims = WRITES[route][4]
    if not raw.flat and raw.parents == "explicit" and "/" in key:
        refused = sim.fire("ensure_parents") or (InvalidPath if raw.through(key) else None)
        if refused is not None:
            return _answer(refused, _parents_row(sim, key) if refused in PROBE_SET else STANDS)
        sim.raw = raw = raw.with_parents(key)  # the probes that follow see the folders it made
    if route == "write_atomic-rename" and not overwrite:
        # The write target's determinant stat (A.8 rule 1): it fails closed.
        seen = sim.stat(key)
        if seen == "file":
            return AlreadyExists
        if seen == "folder":
            return InvalidPath
        if _err(seen) and seen not in MISS:
            if raw.flat or seen not in PROBE_SET:
                return seen  # type: ignore[return-value]
            above = _above(sim, key)  # implementation choice: the ancestors
            if above == "through":
                return InvalidPath
            if above is None:
                return seen  # type: ignore[return-value]
    for prim in prims:
        refused = sim.fire(prim) or _wire_write_refusal(route, prim, raw, key, overwrite)
        if refused is not None:
            return _answer(refused, _put_row(sim, key, overwrite) if refused in PROBE_SET else STANDS)
    return "ok"


def _wire_write_refusal(route: str, prim: str, raw: _Raw, key: str, overwrite: bool) -> type[RemoteStoreError] | None:
    """What one primitive of a write route refuses natively."""
    if prim == "open_write":
        return None  # the wire refuses at commit
    if route == "write_atomic-rename" and prim == "put":
        # The temporary, a sibling of the key, with overwrite: refused only through an item.
        return InvalidPath if not raw.flat and raw.through(key) else None
    return _wire_put_refusal(raw, key, overwrite)


def _write_states(driver: str) -> list[str]:
    return _states(driver, exclude=NO_LINK)


def _write_refusals(route: str, driver: str, key: str) -> list[tuple[str, str] | None]:
    prims = WRITES[route][4]
    if DRIVERS[driver][1] == "explicit" and "/" in key:
        prims = ("ensure_parents", *prims)
    return _refusals(prims)


def _check_write(
    runtime: str, route: str, driver: str, state: str, overwrite: bool, refusal: tuple[str, str] | None, mode: str
) -> None:
    call, protocols, put_is_atomic, _, _ = WRITES[route]
    namespace, parents = DRIVERS[driver]
    key = STATES[state][0]
    store = _wire(driver)
    # The rename route's put and rename name the temporary, whose key is random; each is its only call.
    fault_key = None if route == "write_atomic-rename" else key
    _arm(store, mode, (key,), refusal, fault_key)
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols, put_is_atomic=put_is_atomic
    )
    want, names = _write_oracle(route, _sim(driver, mode, (key,), refusal), key, overwrite)
    before = contents(store)
    got, err, _ = settle(lambda: call(run, key, overwrite))
    assert got == want, _vs(got, want, err)
    if err is None:
        after = contents(store)
        assert after[key] == b"N"
        assert {k: v for k, v in after.items() if k != key} == {k: v for k, v in before.items() if k != key}
    else:
        assert err.path == names
        _caused_by(err, refusal, store)
        assert contents(store) == before  # nothing written, no temporary left
    assert all(h.state != "open" for h in store.handles)  # type: ignore[attr-defined]


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-009")
@pytest.mark.spec("BE-010")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_write_answers_its_refusals_by_the_write_rows_and_checks_a_flat_key_first(runtime: str) -> None:
    cells = [
        (
            f"{route}-{driver}-{state}-ow{int(overwrite)}-{_rid(refusal)}-{mode}",
            functools.partial(_check_write, runtime, route, driver, state, overwrite, refusal, mode),
        )
        for route, (_, _, _, sync_only, _) in WRITES.items()
        if runtime == "sync" or not sync_only
        for driver in DRIVERS
        for state in _write_states(driver)
        for overwrite in (False, True)
        for refusal in _write_refusals(route, driver, STATES[state][0])
        for mode in _modes(refusal, lists=_lists(driver))
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# transfer: move and copy, the source as get and the destination as put
# ---------------------------------------------------------------------------

# route -> (op, protocols, the primitive a refusal is injected on)
TRANSFERS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "move-atomic": ("move", ("atomic_move",), "move"),
    "move-rename": ("move", ("rename",), "rename"),
    "move-copy-delete": ("move", ("copy",), "copy"),
    "copy": ("copy", ("copy",), "copy"),
}
# source state -> (key, the drivers that can hold it)
SOURCES: dict[str, tuple[str, str]] = {
    "item": ("s", ALL),
    "folder": ("e", ALL),
    "nothing": ("m", ALL),
    "below-item": ("g/a", FLAT),
    "link": ("l", HIER),
}


def _sources(driver: str) -> list[str]:
    namespace = DRIVERS[driver][0]
    return [s for s, (_, where) in SOURCES.items() if where == ALL or (where == FLAT) == (namespace == "flat")]


def _transfer_oracle(
    route: str, sim: _Sim, src: str, dst: str, overwrite: bool, dst_first: bool
) -> tuple[Expected, str | None]:
    """BE-018's order: the source as ``get``, then the destination as ``put`` (A.8's ``move``, ``copy`` row).

    The second value is the key the error names, ``None`` where either may.
    """
    raw = sim.raw
    op, _, prim = TRANSFERS[route]
    entry = op == "move"  # a move source names the entry (A.7)

    def source() -> tuple[Expected, str] | None:
        # The transfer source check, a determinant (A.8 rule 1): it fails closed.
        node = _node(sim, src, follow=not entry)
        if _err(node):
            return node, src  # type: ignore[return-value]
        if node != ITEM:
            return (InvalidPath if node == FOLDER else NotFound), src
        return None

    checked = raw.flat or raw.parents == "explicit"
    if checked and (early := source()) is not None:
        return early
    if raw.flat:
        checked = _a4(sim, dst)
        if checked is not None:
            return checked
    elif raw.parents == "explicit" and "/" in dst:
        if raw.through(dst):
            return _answer(InvalidPath, _parents_row(sim, dst)), dst
        sim.raw = raw = raw.with_parents(dst)
    if route == "move-rename":
        if not checked and (early := source()) is not None:
            return early
        seen = sim.stat(dst)  # the write target's determinant stat
        if seen == "folder":
            return InvalidPath, dst
        if seen == "file" and not overwrite:
            return AlreadyExists, dst
        if _err(seen) and seen not in MISS:
            above = _above(sim, dst) if not raw.flat and seen in PROBE_SET else None
            if above == "through":
                return InvalidPath, dst
            if above is None:
                return seen, dst  # type: ignore[return-value]
    refused = sim.fire(prim)
    if refused is None:
        src_refusal = None if src in raw.files else NotFound
        dst_refusal = _wire_put_refusal(raw, dst, overwrite)
        first, second = (dst_refusal, src_refusal) if dst_first else (src_refusal, dst_refusal)
        refused = first or second
    if refused is None:
        return "ok", None
    if refused not in PROBE_SET:
        return refused, None
    # The source as get, and the destination only when the source is an item (A.8): a source
    # probe that cannot answer leaves the refusal standing (rule 3), since a folder at the
    # destination must not outrank a source that may be absent (BE-018).
    node = _node(sim, src, follow=not entry)
    if _err(node):
        # Only the destination can be taken, so a standing AlreadyExists names it.
        return refused, (dst if refused is AlreadyExists else None)
    if node != ITEM:
        return (InvalidPath if node == FOLDER else NotFound), src
    row = _put_row(sim, dst, overwrite)
    return (refused, None) if row == STANDS else (row, dst)  # type: ignore[return-value]


def _transfer_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for route, (_, _, prim) in TRANSFERS.items():
        for driver in DRIVERS:
            for src in _sources(driver):
                for dst in _write_states(driver):
                    if SOURCES[src][0] == STATES[dst][0]:
                        continue  # a self-operation is decided on the keys (BK-301), not by these rows
                    for overwrite in (False, True):
                        for refusal in _refusals((prim,)):
                            if src == "link" and refusal is None:
                                continue  # the fake cannot move a link entry; injected cells only
                            # The wire's key order matters only where both keys refuse.
                            orders = (False, True) if refusal is None and src != "item" else (False,)
                            for dst_first in orders:
                                for mode in _modes(refusal, lists=_lists(driver), transfer=True):
                                    cells.append(
                                        (
                                            f"{route}-{driver}-src_{src}-dst_{dst}-ow{int(overwrite)}"
                                            f"-{_rid(refusal)}-{mode}{'-dst_first' if dst_first else ''}",
                                            functools.partial(
                                                _check_transfer,
                                                runtime,
                                                route,
                                                driver,
                                                src,
                                                dst,
                                                overwrite,
                                                refusal,
                                                mode,
                                                dst_first,
                                            ),
                                        )
                                    )
    return cells


def _check_transfer(
    runtime: str,
    route: str,
    driver: str,
    src_state: str,
    dst_state: str,
    overwrite: bool,
    refusal: tuple[str, str] | None,
    mode: str,
    dst_first: bool,
) -> None:
    op, protocols, _ = TRANSFERS[route]
    namespace, parents = DRIVERS[driver]
    src, dst = SOURCES[src_state][0], STATES[dst_state][0]
    link = src_state == "link"
    store = _wire(driver, link=link)
    store.dst_first = dst_first
    _arm(store, mode, (src, dst), refusal, src)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols)
    want, names = _transfer_oracle(
        route, _sim(driver, mode, (src, dst), refusal, link=link), src, dst, overwrite, dst_first
    )
    before = contents(store)
    got, err, _ = settle(lambda: getattr(run, op)(src, dst, overwrite=overwrite))
    assert got == want, _vs(got, want, err)
    if err is None:
        after = contents(store)
        assert after[dst] == before[src]
        assert (src in after) == (op == "copy")
        untouched = (src, dst)
        assert {k: v for k, v in after.items() if k not in untouched} == {
            k: v for k, v in before.items() if k not in untouched
        }
        return
    named = (src, dst) if names is None else (names,)
    assert err.path in named, f"names {err.path!r}, oracle {' or '.join(map(repr, named))}"
    _caused_by(err, refusal, store)
    assert contents(store) == before


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_transfer_answers_its_refusals_by_the_source_then_the_destination(runtime: str) -> None:
    cells = _transfer_cells(runtime)
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# folder-read: the listings and get_folder_info; A.3's flat stat and omissions
# ---------------------------------------------------------------------------


def _aggregate(run: Any, key: str) -> tuple[int, int]:
    info = run.get_folder_info(key)
    return info.file_count, info.total_size


# call -> (call, protocols, the primitive a refusal is injected on)
LISTINGS: dict[str, tuple[Callable[[Any, str], Any], tuple[str, ...], str]] = {
    "list_files": (lambda r, k: keys_of(r.list_files(k)), (), "list_page"),
    "list_files-recursive": (lambda r, k: keys_of(r.list_files(k, recursive=True)), (), "list_page"),
    "list_folders": (lambda r, k: keys_of(r.list_folders(k)), (), "list_page"),
    "iter_children": (lambda r, k: keys_of(r.iter_children(k)), (), "list_page"),
    "get_folder_info-listing": (_aggregate, (), "list_page"),
    "get_folder_info-push_down": (_aggregate, ("folder_stats",), "folder_stats"),
}


def _listed(raw: _Raw, key: str, call: str) -> tuple[Any, int]:
    """What a listing of *key* yields as the tree has it, and how many listed keys it omits (A.3, BE-030)."""
    keys = raw.under(key)
    if call == "list_files-recursive" or call.startswith("get_folder_info"):
        kept = sorted(x for x in keys if _listable(x) and not raw.below_an_item(x, keys))
        if call.startswith("get_folder_info"):
            return (len(kept), sum(len(raw.files[x]) for x in kept)), len(keys) - len(kept)
        return kept, len(keys) - len(kept)
    base = key + "/" if key else ""
    files = sorted(x for x in keys if "/" not in x[len(base) :])
    folders = {base + x[len(base) :].split("/")[0] for x in keys if "/" in x[len(base) :]}
    folders |= {o for o in raw.objects if o.startswith(base) and o != key and "/" not in o[len(base) :]}
    kept_files = [x for x in files if _listable(x)]
    # A.3: a prefix of the name of an item the same page returns lies below that item.
    kept_folders = sorted(p for p in folders if _listable(p) and not (raw.flat and p in files))
    file_gaps, folder_gaps = len(files) - len(kept_files), len(folders) - len(kept_folders)
    if call == "list_files":
        return kept_files, file_gaps
    if call == "list_folders":
        return kept_folders, folder_gaps
    return sorted(kept_files + kept_folders), file_gaps + folder_gaps


def _listing_oracle(call: str, sim: _Sim, key: str) -> tuple[Expected, Any, int]:
    raw = sim.raw
    aggregate = call.startswith("get_folder_info")
    if raw.flat and key:
        # A.3's stat before a flat folder operation: a determinant, success included.
        seen = sim.stat(key)
        if _err(seen) and seen not in MISS:
            return seen, None, 0  # type: ignore[return-value]
        if seen == "file":
            return (InvalidPath, None, 0) if aggregate else ("ok", [], 0)
    refused = sim.fire(LISTINGS[call][2])
    if refused is None and call != "get_folder_info-push_down" and not raw.flat and raw.parents != "none" and key:
        refused = NotFound if raw.stat(key) != "folder" else None  # a wire with folder objects lists only a folder
    if refused is not None and not _first_page_empty(sim, key, refused):
        return refused, None, 0
    value, omitted = (((0, 0) if aggregate else []), 0) if refused is not None else _listed(raw, key, call)
    if aggregate and value[0] == 0 and key:
        # BE-017 types an empty aggregate: a determinant with folder objects, fail-open without.
        # On a flat namespace A.3's stat already ruled out an item. On the listing route the
        # aggregation listing itself answers whether anything lies under the prefix (a refused
        # first page reads as empty, by the flat listing obligation); only the push-down asks
        # the probe listing, with _node's flat reading of it.
        if raw.flat and call != "get_folder_info-push_down":
            node = FOLDER if refused is None and omitted else NOTHING
        elif raw.flat:
            held = sim.holds(key)
            node = (NOTHING if held in MISS else held) if _err(held) else (FOLDER if held else NOTHING)
        else:
            node = _node(sim, key)
        if _err(node):
            if raw.parents != "none":
                return node, None, 0  # type: ignore[return-value]
            node = NOTHING
        if node == ITEM:
            return InvalidPath, None, 0
        if node != FOLDER:
            return NotFound, None, 0
    return "ok", value, omitted


def _check_listing(
    runtime: str, call: str, driver: str, state: str, refusal: tuple[str, str] | None, mode: str, page_size: int
) -> None:
    fn, protocols, _ = LISTINGS[call]
    namespace, parents = DRIVERS[driver]
    key = STATES[state][0]
    store = _wire(driver, page_size=page_size)
    _arm(store, mode, (key,), refusal, key)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents) + protocols)
    want, value, omitted = _listing_oracle(call, _sim(driver, mode, (key,), refusal), key)
    before = contents(store)
    (got, err, listed), logged = _logged(lambda: fn(run, key))
    assert got == want, _vs(got, want, err)
    if err is None:
        assert listed == value
        assert logged == ([omitted] if omitted else []), "each omission is logged, once per listing"
    else:
        assert err.path == key
    assert contents(store) == before


def _listing_cells(runtime: str) -> list[Cell]:
    cells: list[Cell] = []
    for call, (_, _, prim) in LISTINGS.items():
        for driver in DRIVERS:
            raw = _Raw(driver)
            for state in _states(driver, exclude=("link",)):
                key = STATES[state][0]
                if call.endswith("push_down") and _listed(raw, key, "get_folder_info")[1]:
                    continue  # A.8's obligation on the driver's aggregate, not the kernel's
                for refusal in _refusals((prim,)):
                    for mode in _modes(refusal, lists=_lists(driver)):
                        # More than one page only where nothing misbehaves: A.3 across page bounds.
                        sizes = (1000, 1) if refusal is None and mode == "answers" else (1000,)
                        for page_size in sizes:
                            cells.append(
                                (
                                    f"{call}-{driver}-{state or 'root'}-{_rid(refusal)}-{mode}-page{page_size}",
                                    functools.partial(
                                        _check_listing, runtime, call, driver, state, refusal, mode, page_size
                                    ),
                                )
                            )
    return cells


@pytest.mark.spec("BE-014")
@pytest.mark.spec("BE-015")
@pytest.mark.spec("BE-017")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-026")
@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_read_omits_what_decodes_to_no_tree_and_answers_its_first_page_refusal(runtime: str) -> None:
    cells = _listing_cells(runtime)
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# delete-folder: BE-031's sequence, with A.8's remove_folder, delete_tree and first-listing rows
# ---------------------------------------------------------------------------


def _df_prims(parents: str, recursive: bool, tree: bool) -> tuple[str, ...]:
    if parents == "none":
        return ("list_page", "delete_tree") if recursive and tree else ("list_page",)
    if not recursive:
        return ("remove_folder",)
    return ("delete_tree",) if tree else ("list_page", "remove_folder")


def _df_oracle(sim: _Sim, key: str, recursive: bool, tree: bool, missing_ok: bool) -> tuple[Expected, set[str]]:
    """The answer, and the raw keys removed."""
    raw = sim.raw
    under = raw.under(key)

    def answered(answer: type[RemoteStoreError]) -> tuple[Expected, set[str]]:
        return ("ok" if missing_ok and answer is NotFound else answer), set()

    if raw.flat:
        # A.3: a flat listing of k/ cannot see an item k, so stat(k) first, a determinant.
        seen = sim.stat(key)
        if _err(seen) and seen not in MISS:
            return seen, set()  # type: ignore[return-value]
        if seen == "file":
            return InvalidPath, set()
    if raw.parents == "none":
        if not recursive or tree:
            refused = sim.fire("list_page")
            held: bool | type[RemoteStoreError] = False
            if refused is None:
                held = sim.holds(key)  # list_page(k, limit=1): the call's own first listing
                if _err(held):
                    refused = held  # type: ignore[assignment]
            if refused is not None:
                if not _first_page_empty(sim, key, refused, follow=False):
                    return refused, set()
                held = False
            if not held:
                return answered(_df_empty(sim, key))
            if not recursive:
                return DirectoryNotEmpty, set()
            refused = sim.fire("delete_tree")
            if refused is None:
                return "ok", set(under)  # the wire's prefix delete removes the omitted keys too
            return answered(_answer(refused, _df_flat_tree_row(sim, key) if refused in PROBE_SET else STANDS))
        refused = sim.fire("list_page")
        if refused is not None:
            if not _first_page_empty(sim, key, refused, follow=False):
                return refused, set()
            return answered(_df_empty(sim, key))
        if not under:
            return answered(_df_empty(sim, key))
        left = {x for x in under if not _listable(x) or raw.below_an_item(x, under)}
        return (DirectoryNotEmpty if left else "ok"), set(under) - left
    seen_kind = raw.stat(key, follow=False)
    if not recursive:
        refused = sim.fire("remove_folder")
        if refused is None:
            if seen_kind != "folder":
                refused = NotFound  # the wire's ENOENT or ENOTDIR
            elif raw.holds(key):
                return DirectoryNotEmpty, set()  # outside the probe set: unprobed
            else:
                return "ok", set()
        return answered(_answer(refused, _df_row(sim, key, remove=True) if refused in PROBE_SET else STANDS))
    if tree:
        refused = sim.fire("delete_tree") or (NotFound if seen_kind != "folder" else None)
        if refused is None:
            return "ok", set(under)
        return answered(_answer(refused, _df_row(sim, key, remove=False) if refused in PROBE_SET else STANDS))
    refused = sim.fire("list_page") or (NotFound if seen_kind != "folder" else None)
    if refused is not None:
        # The walk's first listing of key: the operation's first page (A.9), read through its rows.
        return answered(_answer(refused, _df_row(sim, key, remove=False) if refused in PROBE_SET else STANDS))
    left = {x for x in under if not _listable(x)}  # never handed to the driver (BE-030)
    removed = set(under) - left
    # key's remove_folder last: a key left behind makes it refuse, outside the probe set.
    refused = sim.fire("remove_folder") or (DirectoryNotEmpty if left else None)
    if refused is None:
        return "ok", removed
    sim.raw = sim.raw.without(removed)  # its probes see the walk's deletions
    return answered(_answer(refused, _df_row(sim, key, remove=True) if refused in PROBE_SET else STANDS))[0], removed


def _check_delete_folder(
    runtime: str,
    driver: str,
    state: str,
    recursive: bool,
    tree: bool,
    missing_ok: bool,
    refusal: tuple[str, str] | None,
    mode: str,
) -> None:
    namespace, parents = DRIVERS[driver]
    key = STATES[state][0]
    store = _wire(driver)
    _arm(store, mode, (key,), refusal, key)
    run = make_kernel(
        runtime, store, namespace=namespace, protocols=base_protocols(parents) + (("delete_tree",) if tree else ())
    )
    want, removed = _df_oracle(_sim(driver, mode, (key,), refusal), key, recursive, tree, missing_ok)
    before = contents(store)
    got, err, _ = settle(lambda: run.delete_folder(key, recursive=recursive, missing_ok=missing_ok))
    assert got == want, _vs(got, want, err)
    if err is not None:
        assert err.path == key
    assert contents(store) == {k: v for k, v in before.items() if k not in removed}


@pytest.mark.spec("BE-013")
@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_folder_delete_answers_its_refusals_by_its_rows_and_leaves_what_a_listing_omits(runtime: str) -> None:
    cells = [
        (
            f"delete_folder-{driver}-{state}-r{int(recursive)}-t{int(tree)}-m{int(missing_ok)}-{_rid(refusal)}-{mode}",
            functools.partial(_check_delete_folder, runtime, driver, state, recursive, tree, missing_ok, refusal, mode),
        )
        for driver in DRIVERS
        for state in _states(driver, exclude=NO_LINK)
        for recursive in (False, True)
        for tree in (False, True)
        for missing_ok in (False, True)
        for refusal in _refusals(_df_prims(DRIVERS[driver][1], recursive, tree))
        for mode in _modes(refusal, lists=True)
    ]
    failures = _failures(cells)
    assert not failures, report(failures, cells)


# ---------------------------------------------------------------------------
# A.9: after the operation's first page a refusal propagates
# ---------------------------------------------------------------------------

LATER_PAGE_CALLS: dict[str, Callable[[Any, str], Any]] = {
    "list_files": lambda r, k: r.list_files(k),
    "list_files-recursive": lambda r, k: r.list_files(k, recursive=True),
    "list_folders": lambda r, k: r.list_folders(k),
    "iter_children": lambda r, k: r.iter_children(k),
    "get_folder_info": lambda r, k: r.get_folder_info(k),
}


@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("driver", list(DRIVERS))
@pytest.mark.parametrize("call", list(LATER_PAGE_CALLS))
@pytest.mark.parametrize("shape", list(SHAPES))
def test_a_refusal_after_the_first_page_propagates_unprobed(runtime: str, driver: str, call: str, shape: str) -> None:
    namespace, parents = DRIVERS[driver]
    store = FakeStore(parents=parents, page_size=1).add("k/a", "k/b/c", "k/d")
    store.fault("list_page", SHAPES[shape]("changed under the scan"), key="k", nth=2)
    run = make_kernel(runtime, store, namespace=namespace, protocols=base_protocols(parents))
    with pytest.raises(TYPED[shape], match="changed under the scan") as caught:
        LATER_PAGE_CALLS[call](run, "k")
    assert type(caught.value) is TYPED[shape]
    assert store.calls[-1] == ("list_page", "k"), "a later page's refusal is not probed"


# entry kind -> (the primitive, its key) in a walk of "k" over k/a, k/s/b
WALK_ENTRIES: dict[str, tuple[str, str]] = {
    "file-delete": ("delete", "k/a"),
    "subfolder-listing": ("list_page", "k/s"),
    "subfolder-remove": ("remove_folder", "k/s"),
}


@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("parents", ["implicit", "explicit"])
@pytest.mark.parametrize("entry", list(WALK_ENTRIES))
@pytest.mark.parametrize("shape", list(SHAPES))
def test_a_walk_tolerates_an_entry_gone_and_propagates_any_other_refusal_unprobed(
    runtime: str, parents: str, entry: str, shape: str
) -> None:
    store = FakeStore(parents=parents).add("k/a", "k/s/b")
    prim, entry_key = WALK_ENTRIES[entry]

    def gone() -> None:  # a NotFound reports an entry already gone, so it is gone
        if shape == "missing":
            if prim == "delete":
                store.files.pop(entry_key)
            elif prim == "remove_folder":
                store.folders.discard(entry_key)
            else:
                store.files.pop("k/s/b")
                store.folders.discard(entry_key)

    store.fault(prim, SHAPES[shape](f"refused {entry_key}"), key=entry_key, hook=gone)
    run = make_kernel(runtime, store, protocols=("remove_folder", "ensure_parents"))
    if shape == "missing":
        run.delete_folder("k", recursive=True)
        assert store.files == {}
        assert not run.exists("k")
        return
    with pytest.raises(TYPED[shape], match="refused") as caught:
        run.delete_folder("k", recursive=True, missing_ok=True)
    assert type(caught.value) is TYPED[shape]
    assert store.called("stat") == [], "an entry's refusal is not probed"
    assert "k" in store.folders


@pytest.mark.spec("BE-031")
@pytest.mark.spec("BE-032")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("namespace", ["flat", "hierarchical"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_a_walk_without_folder_objects_propagates_a_later_pages_refusal(
    runtime: str, namespace: str, shape: str
) -> None:
    store = FakeStore(parents="none", page_size=1).add("k/a", "k/b", "k/c")
    store.fault("list_page", SHAPES[shape]("changed under the scan"), key="k", nth=2)
    run = make_kernel(runtime, store, namespace=namespace, protocols=())
    with pytest.raises(TYPED[shape], match="changed under the scan"):
        run.delete_folder("k", recursive=True, missing_ok=True)
    assert sorted(store.files) == ["k/a", "k/b", "k/c"]
