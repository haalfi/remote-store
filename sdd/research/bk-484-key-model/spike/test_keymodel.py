"""Property tests for the claims of research-key-model.md. Each test names its §."""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from keymodel import (
    Config,
    Reject,
    Store,
    axiom_violations,
    child_resolve,
    child_view,
    in_l_core,
    join,
    last,
    nu,
    parent,
    prefix,
    resolve,
    segments,
    walk,
)

settings.register_profile("spike", max_examples=2000, deadline=None)
settings.load_profile("spike")

NFC_E = "é"
NFD_E = "é"

# Small pools so collisions, navigation and edge cases are frequent.
TOKENS = ["a", "b", "A", "c", ".", "..", "", "CON", "a..b", ".hidden", NFC_E, NFD_E, "x\\y", "\\", "n\0"]
token = st.one_of(st.sampled_from(TOKENS), st.text(min_size=1, max_size=3))
raw = st.lists(token, max_size=7).flatmap(
    lambda ts: st.lists(st.sampled_from(["/", "\\"]), min_size=len(ts), max_size=len(ts)).map(
        lambda seps: "".join(t + s for t, s in zip(ts, seps, strict=True))
    )
)

WINDOWSISH = Config(native_backslash=True, segment_ok=lambda s: s.upper() != "CON" and ":" not in s)
configs = st.sampled_from(
    [
        Config(),
        Config(backslash_separator=False),
        WINDOWSISH,
        Config(max_bytes=12),
        Config(norm=lambda s: unicodedata.normalize("NFD", s)),
    ]
)
child_roots = st.sampled_from(["", "a", "a/b", "A/c"])


def ok(v: object) -> bool:
    return not isinstance(v, Reject)


# --- § 3.5 examples table ------------------------------------------------


@pytest.mark.parametrize(
    ("inp", "want"),
    [
        ("a/b", "a/b"),
        ("a//b", "a/b"),
        ("/a/b/", "a/b"),
        ("a/./b", "a/b"),
        ("a/c/../b", "a/b"),
        ("", ""),
        ("/", ""),
        (".", ""),
        ("a/..", ""),
        ("a..b", "a..b"),
        (".hidden", ".hidden"),
        ("CON/../a", "a"),
        ("..", Reject("escape")),
        ("/..", Reject("escape")),
        ("a/../..", Reject("escape")),
        ("CON", Reject("tier")),
        ("a/CON", Reject("tier")),
        ("A/b", "A/b"),
        ("a\\b", "a/b"),
        ("a\\.\\b", "a/b"),
    ],
)
def test_examples_table(inp: str, want: object) -> None:
    assert nu(inp, WINDOWSISH) == want


def test_backslash_opted_out_is_rejected() -> None:
    assert nu("a\\b", Config(backslash_separator=False)) == Reject("input")


@pytest.mark.parametrize("inp", ["a\\a/..", "x/y\\z/../.."])
def test_backslash_opted_out_rejected_even_when_popped(inp: str) -> None:
    """Spike finding 1: the `\\` rule is on the raw input, not the end position."""
    assert nu(inp, Config(backslash_separator=False)) == Reject("input")


@pytest.mark.parametrize("cfg", [Config(), Config(backslash_separator=False)])
def test_nul_rejected_anywhere(cfg: Config) -> None:
    """Spike finding 2: NUL is rejected in the raw input, even in a popped name."""
    assert nu("x\0/..", cfg) == Reject("input")


def test_join_examples() -> None:
    c = Config()
    assert join("a", "..", c) == ""
    assert join("a/b", "../c", c) == "a/c"
    assert join("", "..", c) == Reject("escape")


# --- § 3.5 properties -------------------------------------------------------


@given(raw, configs)
def test_output_is_navigation_free_key_string(p: str, cfg: Config) -> None:
    """§ 3.5 'from here on' + TREE-011 shape."""
    k = nu(p, cfg)
    assume(ok(k))
    assert in_l_core(k)
    assert all(s not in ("", ".", "..") and "\\" not in s and "\0" not in s for s in segments(k))


@given(raw, configs)
def test_canonical_fixed_point(p: str, cfg: Config) -> None:
    """§ 3.5: ν(k) = k for every k ∈ L_api (round trip)."""
    k = nu(p, cfg)
    assume(ok(k))
    assert nu(k, cfg) == k


@given(raw, raw, configs)
def test_nu_decides_equivalence(p: str, q: str, cfg: Config) -> None:
    """§ 3.5: on accepted values, p ≈ q iff ν(p) = ν(q)."""
    kp, kq = nu(p, cfg), nu(q, cfg)
    assume(ok(kp) and ok(kq))
    assert (walk(p, cfg) == walk(q, cfg)) == (kp == kq)


@given(raw, raw, raw, configs)
def test_join_is_walk_continuation(k0: str, p: str, q: str, cfg: Config) -> None:
    """§ 3.5: (k ⊕ p) ⊕ q = k ⊕ (p/q) whenever k ⊕ p is accepted."""
    k = nu(k0, cfg)
    assume(ok(k))
    m = join(k, p, cfg)
    assume(ok(m))
    assert join(m, q, cfg) == join(k, p + "/" + q, cfg)


@given(raw)
def test_opt_out_only_rejects_more(p: str) -> None:
    """§ 3.3: opting out of `\\` never changes an accepted value's key string."""
    k_out = nu(p, Config(backslash_separator=False))
    assume(ok(k_out))
    assert nu(p, Config()) == k_out


# --- § 3.6 child stores -----------------------------------------------------


@given(child_roots, raw, configs)
def test_child_key_composes_with_parent(c: str, p: str, cfg: Config) -> None:
    """§ 3.6: an accepted child key k is the parent's c ⊕ k = ν_S(c/p)."""
    k = nu(p, cfg, root=c)
    assume(ok(k))
    full = "/".join(segments(c) + segments(k))
    assert nu(c + "/" + p, cfg) == full


@given(child_roots, raw, configs)
def test_child_chaining(c: str, d: str, cfg: Config) -> None:
    """CHILD-005 via § 3.6: child(c).child(d) has root c ⊕ ν_c(d) = ν_S(c/d), d → ε included."""
    assume(c != "")
    k = nu(d, cfg, root=c)
    assume(ok(k))
    assert "/".join(segments(c) + segments(k)) == nu(c + "/" + d, cfg)


def test_composed_length_can_reject() -> None:
    """§ 3.6: acceptance runs on c ⊕ k, not k."""
    cfg = Config(max_bytes=5)
    assert nu("abc", cfg) == "abc"
    assert nu("abc", cfg, root="xyz") == Reject("tier")


# --- spec 051 stores ---------------------------------------------------------

NAMES = ["a", "b", "A", ".", "..", "x\\y", NFC_E, NFD_E]


@st.composite
def stores(draw) -> Store:
    folders, items, contains, name = {0}, set(), set(), {0: ""}
    for x in range(1, draw(st.integers(0, 9)) + 1):
        p = draw(st.sampled_from(sorted(folders)))
        n = draw(st.sampled_from(NAMES))
        if any(name[y] == n for (q, y) in contains if q == p):
            continue
        (folders if draw(st.booleans()) else items).add(x)
        contains.add((p, x))
        name[x] = n
    return Store(folders=folders, items=items, root=0, contains=contains, name=name)


key_strings = st.lists(st.sampled_from(NAMES), max_size=4).map("/".join)


@given(stores())
def test_generator_yields_models(s: Store) -> None:
    assert axiom_violations(s) == []


@given(st.lists(st.text(min_size=1).filter(lambda t: "/" not in t), max_size=5), st.booleans())
def test_lemma_c(names: list[str], last_is_item: bool) -> None:
    """§ 4: every L_core string is a Key in the one-chain store."""
    k = "/".join(names)
    n = len(names)
    s = Store(
        folders=set(range(n)) | (set() if last_is_item and n else {n}),
        items={n} if last_is_item and n else set(),
        root=0,
        contains={(i, i + 1) for i in range(n)},
        name={0: "", **{i + 1: names[i] for i in range(n)}},
    )
    assert axiom_violations(s) == []
    assert k in s.keys()  # noqa: SIM118 -- Store.keys() is a method, not a dict view


@given(stores())
def test_operations_agree_with_spec_051(s: Store) -> None:
    """§ 4: last(Key(x)) = name(x); parent(Key(x)) = Key(container(x))."""
    for x in s.universe:
        k = s.key_of(x)
        assert last(k) == s.name[x]
        if x != s.root:
            assert parent(k) == s.key_of(s.container(x))


@given(stores(), key_strings)
def test_resolution(s: Store, k: str) -> None:
    """§ 3.7: prefixes up to j are Keys; each outcome means what the table says."""
    assume(k == "" or "" not in k.split("/"))
    keys = s.keys()
    r = resolve(k, s)
    n = len(segments(k))
    j = n if r[0] == "found" else len(segments(r[1])) if len(r) > 1 else n - 1
    assert all(prefix(k, i) in keys for i in range(j + 1))
    if r[0] == "found":
        assert s.key_of(r[1]) == k
    else:
        assert k not in keys
    if r[0] == "blocked":
        assert keys[r[1]] in s.items
    if r[0] == "absent":
        assert keys[parent(k)] in s.folders


@given(stores())
def test_root_is_found_folder(s: Store) -> None:
    assert resolve("", s) == ("found", s.root, "folder")


@given(stores(), key_strings)
def test_child_view_is_a_store(s: Store, c: str) -> None:
    assume(c != "")
    v = child_view(s, c)
    if v is not None:
        assert axiom_violations(v) == []


@given(stores(), st.data(), key_strings)
def test_child_resolution_commutes(s: Store, data: st.DataObject, k: str) -> None:
    """§ 3.6: on a found folder c, resolving k in the child = resolving c ⊕ k in S."""
    folder_keys = sorted(key for key, x in s.keys().items() if x in s.folders and key)
    assume(folder_keys)
    c = data.draw(st.sampled_from(folder_keys))
    v = child_view(s, c)
    assert v is not None
    full = "/".join(segments(c) + segments(k))
    rc, rs = resolve(k, v), resolve(full, s)
    assert rc[0] == rs[0]
    if rc[0] == "found":
        assert rc[1] == rs[1]


@given(stores(), key_strings)
def test_child_at_root_is_the_store(s: Store, k: str) -> None:
    """§ 3.6: a child at ε is S itself."""
    v = child_view(s, "")
    assert v is not None
    assert set(v.keys()) == set(s.keys())
    assert child_resolve(s, "", k) == resolve(k, s)


@given(stores(), key_strings, key_strings)
def test_child_composition_table(s: Store, c: str, k: str) -> None:
    """§ 3.6's table: below an absent c every key is AbsentAncestor; below an item, BlockedByItem."""
    assume(c != "" and k != "")
    at_c = resolve(c, s)
    below = child_resolve(s, c, k)
    if at_c[0] in ("absent", "absent_ancestor"):
        assert child_view(s, c) is None
        assert below[0] == "absent_ancestor"
    elif at_c[0] == "blocked" or (at_c[0] == "found" and at_c[2] == "item"):
        assert child_view(s, c) is None
        assert below[0] == "blocked"


# --- § 3.2 round trip on a rewriting backend ---------------------------------


@given(raw)
def test_nfd_backend_round_trip(p: str) -> None:
    def nfd(t: str) -> str:
        return unicodedata.normalize("NFD", t)

    cfg = Config(norm=nfd)
    k = nu(p, cfg)
    assume(ok(k))
    stored = "/".join(nfd(seg) for seg in segments(k))
    assert stored == k


def test_nfc_rejected_on_nfd_backend() -> None:
    cfg = Config(norm=lambda t: unicodedata.normalize("NFD", t))
    assert nu(NFC_E, cfg) == Reject("tier")
    assert nu(NFD_E, cfg) == NFD_E
