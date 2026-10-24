"""Spec 054's store key (KEY-001 to KEY-013), checked against a reference model.

The model is ν, Ω and the acceptance languages written from the spec's
sections, with spec 051 stores as finite tuples. Evidence of three kinds:

- **Rows from the spec and the research.** KEY-005's table and the
  counterexamples of ``research-key-model.md`` § 5, each a hand-written case
  a wrong ν fails.
- **Properties over drawn inputs.** Small token pools (navigation, `\\`,
  U+0000, a surrogate, NFC and NFD spellings, a reserved name) make
  collisions and navigation frequent; each derived section (KEY-010 to
  KEY-013) is checked against a computation that does not call the clause it
  tests where one exists, such as the walk's end position for KEY-011.
- **The profile table.** KEY-007 draws L_shared keys and runs them through a
  configuration per column of ``sdd/specs/profiles/054-store-key.md``, so a
  regex or a table cell that disagree fail here.

Bounds: the model is finite and its backends are stand-ins for the table's
cells, not the backends; the unbounded proofs are
``sdd/formal/lean/KeyModel.lean``. No backend is involved.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

if TYPE_CHECKING:
    from collections.abc import Callable

# --- Reference model (spec 054) ---


@dataclass(frozen=True)
class Refused:
    reason: str  # "input" | "escape" | "accept"


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _any(_: str) -> bool:
    return True


def _same(s: str) -> str:
    return s


@dataclass(frozen=True)
class Config:
    """Sep (KEY-009), L_api's choice (KEY-008) and one backend's L_b (KEY-006)."""

    native_backslash: bool = False
    backslash_separator: bool = True
    portable: bool = False
    name_ok: Callable[[str], bool] = _any
    stored_as_last: Callable[[str], str] = _same  # the name's spelling once stored as a last segment
    name_max: tuple[Callable[[str], int], int] | None = None
    key_max: tuple[Callable[[str], int], int] | None = None

    def __post_init__(self) -> None:
        if self.native_backslash and not self.backslash_separator:
            raise ValueError("KEY-009: a backend reading `\\` natively cannot opt out")


PORTABLE_NAME = r"(?!(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:[./]|$))[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?"
PORTABLE_KEY = rf"(?=[ -~]{{1,255}}\Z){PORTABLE_NAME}(?:/{PORTABLE_NAME})*"


def segments(k: str) -> tuple[str, ...]:
    return tuple(k.split("/")) if k else ()


def prefix(k: str, i: int) -> str:
    return "/".join(segments(k)[:i])


def in_l_core(k: str) -> bool:
    return k == "" or "" not in k.split("/")


def in_l_floor(k: str) -> bool:
    return in_l_core(k) and all("\0" not in s and "\\" not in s and s not in (".", "..") for s in segments(k))


def in_l_shared(k: str) -> bool:
    return k == "" or re.fullmatch(PORTABLE_KEY, k) is not None


def in_l_b(k: str, cfg: Config) -> bool:
    for s in segments(k):
        if not cfg.name_ok(s) or cfg.stored_as_last(s) != s:
            return False
        if cfg.name_max is not None and cfg.name_max[0](s) > cfg.name_max[1]:
            return False
    return cfg.key_max is None or cfg.key_max[0](k) <= cfg.key_max[1]


def in_l_api(k: str, cfg: Config) -> bool:
    return in_l_shared(k) if cfg.portable else in_l_floor(k) and in_l_b(k, cfg)


def _has_surrogate(p: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in p)


def walk(p: str, cfg: Config) -> tuple[str, ...] | Refused:
    """KEY-002, then KEY-003 and KEY-004: the end position, or a refusal."""
    if "\0" in p or _has_surrogate(p) or (not cfg.backslash_separator and "\\" in p):
        return Refused("input")
    pos: list[str] = []
    for s in re.split(r"[/\\]" if cfg.backslash_separator else "/", p):
        if s in ("", "."):
            continue
        if s == "..":
            if not pos:
                return Refused("escape")
            pos.pop()
            continue
        pos.append(s)
    return tuple(pos)


def nu(p: str, cfg: Config, base: str = "") -> str | Refused:
    """ν_c(p): KEY-005 judges c · (end position) and returns the end position."""
    pos = walk(p, cfg)
    if isinstance(pos, Refused):
        return pos
    k = "/".join(pos)
    return k if in_l_api("/".join(segments(base) + pos), cfg) else Refused("accept")


def ok(v: object) -> bool:
    return not isinstance(v, Refused)


@dataclass
class Store:
    """A spec 051 store tuple; entities are ints, the root 0."""

    folders: set[int]
    items: set[int]
    contains: set[tuple[int, int]]
    name: dict[int, str]
    root: int = 0
    _keys: dict[str, int] = field(default_factory=dict, repr=False)

    def key_of(self, x: int) -> str:
        names: list[str] = []
        while x != self.root:
            names.append(self.name[x])
            (x,) = [p for (p, y) in self.contains if y == x]
        return "/".join(reversed(names))

    def keys(self) -> dict[str, int]:
        if not self._keys:
            self._keys = {self.key_of(x): x for x in self.folders | self.items}
        return self._keys


def resolve(k: str, s: Store) -> tuple:
    """Ω_S(k), KEY-013."""
    keys = s.keys()
    n = len(segments(k))
    j = max(i for i in range(n + 1) if prefix(k, i) in keys)
    e = keys[prefix(k, j)]
    if j == n:
        return ("found", e, "folder" if e in s.folders else "item")
    if e in s.items:
        return ("blocked", prefix(k, j))
    return ("absent",) if j == n - 1 else ("absent_ancestor", prefix(k, j))


# --- Stand-ins for the profile table's columns (sdd/specs/profiles/054-store-key.md) ---

_WINDOWS_FORBIDDEN = set('<>:"|?*') | {chr(c) for c in range(1, 32)}
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {f"{d}{n}" for d in ("COM", "LPT") for n in "123456789¹²³"}


def _windows_name_ok(s: str) -> bool:
    return not (_WINDOWS_FORBIDDEN & set(s)) and s.split(".")[0].upper() not in _WINDOWS_DEVICES


def _windows_stored_as_last(s: str) -> str:
    return s.rstrip(". ")


def _s3_directory_name_ok(s: str) -> bool:
    return not any(ord(c) < 32 and c not in "\n\t\r" for c in s)


PROFILES = {
    "memory": Config(),
    "local-linux": Config(name_max=(_bytes, 255), key_max=(_bytes, 4095)),
    "local-apfs": Config(name_max=(_bytes, 255), key_max=(_bytes, 1023)),
    "local-windows": Config(
        native_backslash=True,
        name_ok=_windows_name_ok,
        stored_as_last=_windows_stored_as_last,
        name_max=(_utf16, 255),
        key_max=(_utf16, 259),
    ),
    "s3": Config(key_max=(_bytes, 1024)),
    "s3-directory": Config(name_ok=_s3_directory_name_ok, key_max=(_bytes, 1024)),
    "sftp-openssh-linux": Config(name_max=(_bytes, 255), key_max=(_bytes, 4095)),
}

WINDOWSISH = Config(native_backslash=True, name_ok=lambda s: s.upper() != "CON")
NFD_BACKEND = Config(stored_as_last=lambda s: unicodedata.normalize("NFD", s))
NFC_E, NFD_E = "é", "é"

CONFIGS = [Config(), Config(backslash_separator=False), WINDOWSISH, Config(key_max=(_bytes, 12)), NFD_BACKEND]
configs = st.sampled_from(CONFIGS)

TOKENS = ["a", "b", "A", "c", ".", "..", "", "CON", "a..b", ".hidden", NFC_E, NFD_E, "x\\y", "\\", "n\0", "\ud800"]
token = st.one_of(st.sampled_from(TOKENS), st.text(min_size=1, max_size=3))
raw = st.lists(token, max_size=7).flatmap(
    lambda ts: st.lists(st.sampled_from(["/", "\\"]), min_size=len(ts), max_size=len(ts)).map(
        lambda seps: "".join(t + s for t, s in zip(ts, seps, strict=True))
    )
)
bases = st.sampled_from(["", "a", "a/b", "A/c"])

NAMES = ["a", "b", "A", ".", "..", "x\\y", NFC_E, NFD_E]


@st.composite
def stores(draw: st.DrawFn) -> Store:
    folders, items, contains, name = {0}, set(), set(), {0: ""}
    for x in range(1, draw(st.integers(0, 9)) + 1):
        p = draw(st.sampled_from(sorted(folders)))
        n = draw(st.sampled_from(NAMES))
        if any(name[y] == n for (q, y) in contains if q == p):
            continue
        (folders if draw(st.booleans()) else items).add(x)
        contains.add((p, x))
        name[x] = n
    return Store(folders=folders, items=items, contains=contains, name=name)


key_strings = st.lists(st.sampled_from(NAMES), max_size=4).map("/".join)


# --- Reduction ---


@pytest.mark.spec("KEY-001")
@given(st.text(), configs, bases)
def test_nu_is_total_and_stateless(p: str, cfg: Config, c: str) -> None:
    assume(ok(nu(c, cfg)))
    k = nu(p, cfg, c)
    assert isinstance(k, (str, Refused))
    assert nu(p, cfg, c) == k
    if ok(k):
        assert in_l_core(k)


@pytest.mark.spec("KEY-002")
@pytest.mark.parametrize("p", ["x\0/..", "\0", "a/b\0c", "\ud800/..", "a/\udc00"])
@pytest.mark.parametrize("cfg", [Config(), Config(backslash_separator=False)], ids=["sep", "opt-out"])
def test_nul_and_surrogates_refused_anywhere(p: str, cfg: Config) -> None:
    assert nu(p, cfg) == Refused("input")


@pytest.mark.spec("KEY-002")
@pytest.mark.parametrize("p", ["a\\b", "a\\a/..", "x/y\\z/../.."])
def test_backslash_refused_anywhere_after_opt_out(p: str) -> None:
    assert nu(p, Config(backslash_separator=False)) == Refused("input")


@pytest.mark.spec("KEY-002")
@given(raw, st.integers(0, 20), st.sampled_from(["\0", "\ud800"]), configs)
def test_input_refusal_wherever_inserted(p: str, at: int, bad: str, cfg: Config) -> None:
    at = min(at, len(p))
    assert nu(p[:at] + bad + p[at:], cfg) == Refused("input")


@pytest.mark.spec("KEY-003")
@pytest.mark.parametrize(
    ("p", "want"),
    [("a/b", ("a", "b")), ("a//b/", ("a", "b")), ("a/./b", ("a", "b")), ("a/c/../b", ("a", "b")), ("a\\b", ("a", "b"))],
)
def test_walk_steps(p: str, want: tuple[str, ...]) -> None:
    assert walk(p, Config()) == want


@pytest.mark.spec("KEY-003")
@given(raw, st.sampled_from(["a", "CON", "..x", NFC_E]), configs)
def test_down_then_up_is_no_move(p: str, n: str, cfg: Config) -> None:
    """A name appended then dropped leaves the position, and the key, as they were."""
    assert nu(p + "/" + n + "/..", cfg) == nu(p, cfg)


@pytest.mark.spec("KEY-004")
@pytest.mark.parametrize("p", ["..", "/..", "a/../..", "./..", "\\.."])
def test_escape_refused(p: str) -> None:
    assert nu(p, Config()) == Refused("escape")


@pytest.mark.spec("KEY-004")
@given(raw, bases)
def test_escape_from_any_base(p: str, c: str) -> None:
    """The walk starts at the base's own root, so a leading `..` escapes whatever c is."""
    assume(ok(walk(p, Config())))
    assert nu("../" + p, Config(), c) == Refused("escape")
    assert nu("a/../b", Config()) == "b"


@pytest.mark.spec("KEY-005")
@pytest.mark.parametrize(
    ("p", "want"),
    [
        *[(p, "a/b") for p in ["a/b", "a//b", "/a/b/", "a/./b", "a/c/../b", "a\\b", "a\\.\\b"]],
        *[(p, "") for p in ["", "/", ".", "a/..", "\\"]],
        ("a..b", "a..b"),
        (".hidden", ".hidden"),
        ("CON/../a", "a"),
        ("CON", Refused("accept")),
        ("a/CON", Refused("accept")),
        ("A/b", "A/b"),
    ],
)
def test_spec_table(p: str, want: object) -> None:
    assert nu(p, WINDOWSISH) == want


@pytest.mark.spec("KEY-005")
def test_acceptance_on_the_composed_key() -> None:
    cfg = Config(key_max=(_bytes, 5))
    assert nu("abc", cfg) == "abc"
    assert nu("abc", cfg, "xyz") == Refused("accept")


@pytest.mark.spec("KEY-005")
@given(raw, configs, bases)
def test_accepted_key_is_in_l_api(p: str, cfg: Config, c: str) -> None:
    k = nu(p, cfg, c)
    assume(ok(k))
    assert in_l_api("/".join(segments(c) + segments(k)), cfg)


# --- Acceptance ---


@pytest.mark.spec("KEY-006")
@pytest.mark.parametrize("p", ["a.", "a./b", "a /b", "d/x. "])
def test_rewritten_name_refused_at_every_segment(p: str) -> None:
    """A name a backend would store under another spelling is outside L_b at any depth."""
    assert nu(p, PROFILES["local-windows"]) == Refused("accept")
    assert nu(p, PROFILES["local-linux"]) == p.replace("\\", "/")


@pytest.mark.spec("KEY-006")
def test_normal_form_backend() -> None:
    assert nu(NFC_E, NFD_BACKEND) == Refused("accept")
    assert nu(NFD_E, NFD_BACKEND) == NFD_E


@pytest.mark.spec("KEY-006")
@given(raw)
def test_l_b_is_prefix_closed(p: str) -> None:
    k = nu(p, PROFILES["local-windows"])
    assume(ok(k))
    assert all(in_l_b(prefix(k, i), PROFILES["local-windows"]) for i in range(len(segments(k)) + 1))


portable_names = st.from_regex(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,14}[A-Za-z0-9_-])?", fullmatch=True)
portable_keys = st.lists(portable_names, min_size=1, max_size=20).map("/".join).filter(in_l_shared)


@pytest.mark.spec("KEY-007", "KEY-A-01")
@pytest.mark.parametrize("profile", sorted(PROFILES))
@given(k=portable_keys)
def test_portable_keys_held_by_every_profile(profile: str, k: str) -> None:
    """Within KEY-A-01's 255 bytes, each table column holds every L_shared key."""
    cfg = PROFILES[profile]
    room = Config(
        native_backslash=cfg.native_backslash,
        name_ok=cfg.name_ok,
        stored_as_last=cfg.stored_as_last,
        name_max=cfg.name_max,
        key_max=(cfg.key_max[0], min(cfg.key_max[1], 255)) if cfg.key_max else None,
    )
    assert in_l_floor(k)
    assert nu(k, room) == k


@pytest.mark.spec("KEY-007")
@pytest.mark.parametrize("name", ["CON", "con.txt", "LPT1", "COM0", "a.", "a ", ".a", "a b", "é"])
def test_portable_name_excludes(name: str) -> None:
    assert not in_l_shared(name)


@pytest.mark.spec("KEY-008")
@given(key_strings | portable_keys)
def test_portable_opt_in_accepts_exactly_l_shared(k: str) -> None:
    assume(in_l_floor(k))
    cfg = Config(portable=True)
    assert ok(nu(k, cfg)) == in_l_shared(k)
    assert nu(".", cfg) == ""


@pytest.mark.spec("KEY-008")
def test_default_acceptance_is_floor_and_backend() -> None:
    assert nu("a b/x.y", Config()) == "a b/x.y"
    assert nu("a b/x.y", Config(portable=True)) == Refused("accept")


@pytest.mark.spec("KEY-009")
def test_separator_set() -> None:
    assert nu("a\\b", Config()) == "a/b"
    assert nu("a\\b", Config(backslash_separator=False)) == Refused("input")
    with pytest.raises(ValueError, match="KEY-009"):
        Config(native_backslash=True, backslash_separator=False)


# --- Derived ---


@pytest.mark.spec("KEY-010")
@given(raw, configs, bases)
def test_canonical_fixed_point(p: str, cfg: Config, c: str) -> None:
    k = nu(p, cfg, c)
    assume(ok(k))
    assert nu(k, cfg, c) == k


@pytest.mark.spec("KEY-011")
@given(raw, raw, configs)
def test_nu_decides_equivalence(p: str, q: str, cfg: Config) -> None:
    kp, kq = nu(p, cfg), nu(q, cfg)
    assume(ok(kp) and ok(kq))
    assert (walk(p, cfg) == walk(q, cfg)) == (kp == kq)


@pytest.mark.spec("KEY-012")
@given(bases, raw, configs)
def test_composition(c: str, p: str, cfg: Config) -> None:
    k = nu(p, cfg, c)
    assume(ok(k))
    assert nu(c + "/" + p, cfg) == "/".join(segments(c) + segments(k))


# --- Resolution ---


@pytest.mark.spec("KEY-013")
@given(stores(), key_strings)
def test_resolution_outcomes(s: Store, k: str) -> None:
    assume(in_l_core(k))
    keys = s.keys()
    occupied = [i for i in range(len(segments(k)) + 1) if prefix(k, i) in keys]
    j, n = max(occupied), len(segments(k))
    assert occupied == list(range(j + 1))  # TREE-012: occupied prefixes close downward
    r = resolve(k, s)
    if j == n:
        assert r[0] == "found"
        assert s.key_of(r[1]) == k
    elif keys[prefix(k, j)] in s.items:
        assert r == ("blocked", prefix(k, j))
    elif j == n - 1:
        assert r == ("absent",)
    else:
        assert r == ("absent_ancestor", prefix(k, j))


@pytest.mark.spec("KEY-013")
@given(stores())
def test_root_is_found_folder(s: Store) -> None:
    assert resolve("", s) == ("found", 0, "folder")


@pytest.mark.spec("KEY-013")
def test_blocked_by_item() -> None:
    s = Store(folders={0}, items={1}, contains={(0, 1)}, name={0: "", 1: "f"})
    assert resolve("f/x/y", s) == ("blocked", "f")
    assert resolve("g", s) == ("absent",)
    assert resolve("g/h", s) == ("absent_ancestor", "")
