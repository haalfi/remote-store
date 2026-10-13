"""Spec 051's store tree (TREE-001 to TREE-012), checked against a reference model.

The model is a finite store tuple ``(U, F, I, r, C, name)`` and one predicate
per axiom clause, written from the spec's sections. Two kinds of evidence:

- **Each clause does work.** For every clause, the structure research § 5
  gives for it, and one more per entity kind the § 5 row leaves out, breaks
  that clause and no other; the witnesses W0 to W2 break none. A predicate
  that rejects a witness, or misses a breaking structure of either kind,
  fails here; one wrong only on structures listed nowhere would not.
- **What the axioms give a caller.** Structures drawn by Hypothesis with free
  names (ε, `/` and `a/b` among them) and free kinds are kept only when every
  predicate holds, and their Keys are unique (TREE-010), well shaped
  (TREE-011) and closed under ancestors (TREE-012). Dropping a naming
  predicate lets a collision through, so these depend on the predicates.

Bounds: the model is finite, so TREE-006 is checked on finite structures only;
the infinite cases are proved in ``sdd/formal/lean/StoreAxioms.lean``. No
backend is involved: conformance of each backend's observed tree is BK-436.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

ROOT = "r"


@dataclass
class Store:
    """A store tuple: entities, folders, items, root, containment and names."""

    U: frozenset[str]
    F: frozenset[str]
    I: frozenset[str]  # noqa: E741 - the spec's symbol
    C: frozenset[tuple[str, str]]
    name: Mapping[str, str]
    r: str = ROOT


def _store(
    U: set[str],
    F: set[str],
    I: set[str],  # noqa: E741 - the spec's symbol
    C: set[tuple[str, str]],
    names: Mapping[str, str] | None = None,
) -> Store:
    """Build a store; a non-root entity not named in ``names`` is named by its id, the root ε."""
    name = {x: ("" if x == ROOT else x) for x in U}
    name.update(names or {})
    return Store(frozenset(U), frozenset(F), frozenset(I), frozenset(C), name)


# --- One predicate per clause (spec 051 TREE-001 to TREE-008) ---


def _containers(s: Store, x: str) -> set[str]:
    return {p for (p, c) in s.C if c == x}


def _reachable(s: Store) -> set[str]:
    seen, frontier = {s.r}, [s.r]
    while frontier:
        p = frontier.pop()
        for q, c in s.C:
            if q == p and c not in seen:
                seen.add(c)
                frontier.append(c)
    return seen


CLAUSES: dict[str, Callable[[Store], bool]] = {
    "TREE-001 covering": lambda s: s.U == s.F | s.I,
    "TREE-001 disjoint": lambda s: not (s.F & s.I),
    "TREE-002": lambda s: s.r in s.F,
    "TREE-003": lambda s: all(p in s.F for (p, _) in s.C),
    "TREE-004": lambda s: all(len(_containers(s, x)) <= 1 for x in s.U),
    "TREE-005": lambda s: not _containers(s, s.r),
    "TREE-006": lambda s: _reachable(s) >= s.U,
    "TREE-007 root": lambda s: s.name[s.r] == "",
    "TREE-007 non-empty": lambda s: all(s.name[x] != "" for x in s.U - {s.r}),
    "TREE-007 no slash": lambda s: all("/" not in s.name[x] for x in s.U - {s.r}),
    "TREE-008": lambda s: all(x == y for (p, x) in s.C for (q, y) in s.C if p == q and s.name[x] == s.name[y]),
}


def broken(s: Store) -> set[str]:
    """The clauses ``s`` breaks."""
    return {clause for clause, holds in CLAUSES.items() if not holds(s)}


# --- Key (TREE-009), defined where TREE-004 to TREE-006 hold ---


def chain(s: Store, x: str) -> list[str]:
    """x's chain from the root, walking the one container back (TREE-004, TREE-005, TREE-006)."""
    walk = [x]
    while walk[-1] != s.r:
        (parent,) = _containers(s, walk[-1])
        walk.append(parent)
        assert len(walk) <= len(s.U), f"chain of {x!r} does not reach the root"
    return walk[::-1]


def key(s: Store, x: str) -> str:
    """Key(x): the names along x's chain, the root excluded, joined by ``/``."""
    return "/".join(s.name[y] for y in chain(s, x)[1:])


# --- Research § 5: one structure per clause, breaking that clause only ---

ROWS: dict[str, Store] = {
    "TREE-001 disjoint": _store({ROOT, "x"}, {ROOT, "x"}, {"x"}, {(ROOT, "x")}),
    "TREE-001 covering": _store({ROOT, "x"}, {ROOT}, set(), {(ROOT, "x")}),
    "TREE-002": _store({ROOT}, set(), {ROOT}, set()),
    "TREE-003": _store({ROOT, "x", "y"}, {ROOT}, {"x", "y"}, {(ROOT, "x"), ("x", "y")}),
    "TREE-004": _store(
        {ROOT, "a", "b", "x"},
        {ROOT, "a", "b"},
        {"x"},
        {(ROOT, "a"), (ROOT, "b"), ("a", "x"), ("b", "x")},
    ),
    "TREE-005": _store({ROOT, "p"}, {ROOT, "p"}, set(), {(ROOT, "p"), ("p", ROOT)}),
    "TREE-006": _store({ROOT, "g1", "g2"}, {ROOT, "g1", "g2"}, set(), {("g1", "g2"), ("g2", "g1")}),
    "TREE-007 root": _store({ROOT}, {ROOT}, set(), set(), {ROOT: "z"}),
    "TREE-007 non-empty": _store({ROOT, "x"}, {ROOT}, {"x"}, {(ROOT, "x")}, {"x": ""}),
    "TREE-007 no slash": _store(
        {ROOT, "w", "a", "b"},
        {ROOT, "w", "a", "b"},
        set(),
        {(ROOT, "w"), (ROOT, "a"), ("a", "b")},
        {"w": "a/b", "a": "a", "b": "b"},
    ),
    "TREE-008": _store({ROOT, "x", "y"}, {ROOT}, {"x", "y"}, {(ROOT, "x"), (ROOT, "y")}, {"x": "n", "y": "n"}),
}

# The § 5 rows break each clause with one entity kind; these break it with the
# other. Each entry: the one clause it breaks, and the structure.
KIND_ROWS: dict[str, tuple[str, Store]] = {
    "TREE-003 item holds a folder": (
        "TREE-003",
        _store({ROOT, "x", "y"}, {ROOT, "y"}, {"x"}, {(ROOT, "x"), ("x", "y")}),
    ),
    "TREE-004 folder with two containers": (
        "TREE-004",
        _store({ROOT, "a", "b", "x"}, {ROOT, "a", "b", "x"}, set(), {(ROOT, "a"), (ROOT, "b"), ("a", "x"), ("b", "x")}),
    ),
    "TREE-007 folder named empty": (
        "TREE-007 non-empty",
        _store({ROOT, "x"}, {ROOT, "x"}, set(), {(ROOT, "x")}, {"x": ""}),
    ),
    "TREE-007 item named with a slash": (
        "TREE-007 no slash",
        _store(
            {ROOT, "w", "a", "b"},
            {ROOT, "a"},
            {"w", "b"},
            {(ROOT, "w"), (ROOT, "a"), ("a", "b")},
            {"w": "a/b", "a": "a", "b": "b"},
        ),
    ),
    "TREE-008 folder and item share a name": (
        "TREE-008",
        _store({ROOT, "a", "b"}, {ROOT, "a"}, {"b"}, {(ROOT, "a"), (ROOT, "b")}, {"a": "n", "b": "n"}),
    ),
    "TREE-008 two folders share a name": (
        "TREE-008",
        _store({ROOT, "a", "b"}, {ROOT, "a", "b"}, set(), {(ROOT, "a"), (ROOT, "b")}, {"a": "n", "b": "n"}),
    ),
}

WITNESSES: dict[str, Store] = {
    "W0": _store({ROOT}, {ROOT}, set(), set()),
    "W1": _store({ROOT, "d", "f"}, {ROOT, "d"}, {"f"}, {(ROOT, "d"), ("d", "f")}),
    "W2": _store({ROOT, "d", "e", "f"}, {ROOT, "d", "e"}, {"f"}, {(ROOT, "d"), ("d", "e"), ("d", "f")}),
}


# Spec IDs are written out, not derived: the spec-mark gate reads markers statically.
_CLAUSE_PARAMS = [
    pytest.param("TREE-001 covering", marks=pytest.mark.spec("TREE-001"), id="TREE-001 covering"),
    pytest.param("TREE-001 disjoint", marks=pytest.mark.spec("TREE-001"), id="TREE-001 disjoint"),
    pytest.param("TREE-002", marks=pytest.mark.spec("TREE-002"), id="TREE-002"),
    pytest.param("TREE-003", marks=pytest.mark.spec("TREE-003"), id="TREE-003"),
    pytest.param("TREE-004", marks=pytest.mark.spec("TREE-004"), id="TREE-004"),
    pytest.param("TREE-005", marks=pytest.mark.spec("TREE-005"), id="TREE-005"),
    pytest.param("TREE-006", marks=pytest.mark.spec("TREE-006"), id="TREE-006"),
    pytest.param("TREE-007 root", marks=pytest.mark.spec("TREE-007"), id="TREE-007 root"),
    pytest.param("TREE-007 non-empty", marks=pytest.mark.spec("TREE-007"), id="TREE-007 non-empty"),
    pytest.param("TREE-007 no slash", marks=pytest.mark.spec("TREE-007"), id="TREE-007 no slash"),
    pytest.param("TREE-008", marks=pytest.mark.spec("TREE-008"), id="TREE-008"),
]


def test_clause_params_cover_every_clause() -> None:
    """Meta-test, no spec section: the written-out parameters name every clause the model checks, and no other."""
    named = [p.values[0] for p in _CLAUSE_PARAMS]
    assert len(named) == len(set(named))
    assert set(named) == set(CLAUSES)


@pytest.mark.parametrize("clause", _CLAUSE_PARAMS)
def test_each_clause_is_broken_alone_by_its_row(clause: str) -> None:
    """Research § 5's structure for a clause breaks that clause and no other."""
    assert broken(ROWS[clause]) == {clause}


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            "TREE-003 item holds a folder", marks=pytest.mark.spec("TREE-003"), id="TREE-003 item holds a folder"
        ),
        pytest.param(
            "TREE-004 folder with two containers",
            marks=pytest.mark.spec("TREE-004"),
            id="TREE-004 folder with two containers",
        ),
        pytest.param(
            "TREE-007 folder named empty", marks=pytest.mark.spec("TREE-007"), id="TREE-007 folder named empty"
        ),
        pytest.param(
            "TREE-007 item named with a slash",
            marks=pytest.mark.spec("TREE-007"),
            id="TREE-007 item named with a slash",
        ),
        pytest.param(
            "TREE-008 folder and item share a name",
            marks=pytest.mark.spec("TREE-008"),
            id="TREE-008 folder and item share a name",
        ),
        pytest.param(
            "TREE-008 two folders share a name",
            marks=pytest.mark.spec("TREE-008"),
            id="TREE-008 two folders share a name",
        ),
    ],
)
def test_each_clause_is_broken_by_the_other_entity_kind(row: str) -> None:
    """A structure breaking the clause with the kind its § 5 row leaves out breaks that clause and no other."""
    clause, s = KIND_ROWS[row]
    assert broken(s) == {clause}


@pytest.mark.parametrize("witness", list(WITNESSES))
@pytest.mark.parametrize("clause", _CLAUSE_PARAMS)
def test_witnesses_satisfy_every_clause(clause: str, witness: str) -> None:
    """W0 to W2 satisfy every clause, so the clauses are consistent."""
    assert clause not in broken(WITNESSES[witness])


@pytest.mark.spec("TREE-009")
@pytest.mark.parametrize(
    ("witness", "keys"),
    [
        ("W0", {ROOT: ""}),
        ("W1", {ROOT: "", "d": "d", "f": "d/f"}),
        ("W2", {ROOT: "", "d": "d", "e": "d/e", "f": "d/f"}),
    ],
)
def test_key_joins_names_along_the_chain(witness: str, keys: dict[str, str]) -> None:
    """Key is the names along the chain, root excluded, joined by ``/``; Key(r) is ε (research § 5)."""
    s = WITNESSES[witness]
    assert {x: key(s, x) for x in s.U} == keys


@pytest.mark.spec("TREE-009")
def test_key_ignores_the_root_name() -> None:
    """Key(r) is the empty join and never uses name(r) (TREE-009)."""
    s = _store({ROOT, "d"}, {ROOT, "d"}, set(), {(ROOT, "d")}, {ROOT: "z"})
    assert (key(s, ROOT), key(s, "d")) == ("", "d")


@pytest.mark.parametrize(
    "clause",
    [
        pytest.param("TREE-007 non-empty", marks=pytest.mark.spec("TREE-007"), id="TREE-007 non-empty"),
        pytest.param("TREE-007 no slash", marks=pytest.mark.spec("TREE-007"), id="TREE-007 no slash"),
        pytest.param("TREE-008", marks=pytest.mark.spec("TREE-008"), id="TREE-008"),
    ],
)
def test_key_collision_follows_from_each_naming_clause_broken(clause: str) -> None:
    """Breaking TREE-007's name clauses or TREE-008 gives two entities one Key: TREE-010 needs them (research § 5)."""
    s = ROWS[clause]
    keys = [key(s, x) for x in s.U]
    assert len(set(keys)) < len(keys)


# --- Structures drawn by Hypothesis ---

# Free names, the invalid ones included; "." and "\\" are ordinary names here (spec 004 governs input).
_NAMES = st.sampled_from(["", "/", "a/b", "a", "b", "c", ".", "\\"])
# The filter is the point: what is kept depends on the predicates, so heavy filtering is expected.
_FILTERED = settings(suppress_health_check=[HealthCheck.filter_too_much])


@st.composite
def _stores(draw: st.DrawFn) -> Store:
    """Each entity under an earlier one, with a free kind and name; kept only if every predicate holds.

    Placing each entity under an earlier one gives TREE-004 to TREE-006 by
    construction; the kinds and names are free, so TREE-003, TREE-007 and
    TREE-008 decide what is kept.
    """
    U, F, I, C, names = {ROOT}, {ROOT}, set(), set(), {ROOT: ""}  # noqa: E741
    placed = [ROOT]
    for i in range(draw(st.integers(0, 5))):
        x = f"e{i}"
        U.add(x)
        C.add((draw(st.sampled_from(placed)), x))
        names[x] = draw(_NAMES)
        (F if draw(st.booleans()) else I).add(x)
        placed.append(x)
    s = _store(U, F, I, C, names)
    assume(broken(s) == set())
    return s


@pytest.mark.pbt
@pytest.mark.spec("TREE-010")
@_FILTERED
@given(_stores())
def test_keys_are_unique(s: Store) -> None:
    """Two entities with one Key are one entity (TREE-010)."""
    keys = [key(s, x) for x in s.U]
    assert len(set(keys)) == len(keys)


@pytest.mark.pbt
@pytest.mark.spec("TREE-011")
@_FILTERED
@given(_stores())
def test_key_shape(s: Store) -> None:
    """Key is ε only for the root; any other is non-empty with no leading, trailing or doubled ``/`` (TREE-011)."""
    for x in s.U:
        k = key(s, x)
        assert (k == "") == (x == s.r)
        if x != s.r:
            assert not k.startswith("/")
            assert not k.endswith("/")
            assert "//" not in k


@pytest.mark.pbt
@pytest.mark.spec("TREE-012")
@_FILTERED
@given(_stores())
def test_prefix_closure(s: Store) -> None:
    """Every whole-name prefix of a Key is the Key of a folder on the chain other than x; items sit last (TREE-012)."""
    by_key = {key(s, x): x for x in s.U}
    for x in s.U - {s.r}:
        segments = key(s, x).split("/")
        on_chain = chain(s, x)
        for i in range(1, len(segments)):
            ancestor = by_key["/".join(segments[:i])]
            assert ancestor in s.F
            assert ancestor in on_chain
        assert all(y in s.F for y in on_chain[:-1])
