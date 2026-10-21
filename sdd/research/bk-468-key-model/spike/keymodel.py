"""Executable model of research-key-model.md, for a spike. Not library code.

Section references (§) are to ../research-key-model.md; TREE-nnn to spec 051.
A key string is a str; ε is "".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Reject:
    reason: str  # "input" | "escape" | "floor" | "tier"


def _always(_: str) -> bool:
    return True


def _identity(s: str) -> str:
    return s


@dataclass(frozen=True)
class Config:
    """A store's configuration: Sep_S (§ 3.3) and its acceptance language (§ 3.2)."""

    native_backslash: bool = False
    backslash_separator: bool = True
    segment_ok: Callable[[str], bool] = _always  # tier predicate per segment
    max_bytes: int | None = None  # whole-string tier limit, UTF-8 bytes
    norm: Callable[[str], str] = _identity  # norm_b (§ 3.2)

    def __post_init__(self) -> None:
        if self.native_backslash and not self.backslash_separator:
            raise ValueError("a backend with native \\ cannot opt out (§ 3.3)")


# --- § 4 operations on key strings -------------------------------------


def segments(k: str) -> tuple[str, ...]:
    return tuple(k.split("/")) if k else ()


def prefix(k: str, i: int) -> str:
    return "/".join(segments(k)[:i])


def last(k: str) -> str:
    s = segments(k)
    return s[-1] if s else ""


def parent(k: str) -> str:
    s = segments(k)
    if not s:
        raise ValueError("parent(ε) is undefined")
    return "/".join(s[:-1])


def in_l_core(k: str) -> bool:
    """TREE-011 shape."""
    return k == "" or all(s != "" for s in k.split("/"))


# --- § 3.2 floor and tiers ------------------------------------------------


def floor_ok(s: str) -> bool:
    return "\0" not in s and "\\" not in s and s not in (".", "..")


# --- § 3.3 walk, § 3.5 reduction ------------------------------------------


def split_raw(raw: str, cfg: Config) -> list[str]:
    return re.split(r"[/\\]", raw) if cfg.backslash_separator else raw.split("/")


def walk(raw: str, cfg: Config) -> tuple[str, ...] | Reject:
    """§ 3.3: end position from the (child's) root, or an escape."""
    if "\0" in raw or (not cfg.backslash_separator and "\\" in raw):
        return Reject("input")  # § 3.5 step 0: rules on the whole raw input
    stack: list[str] = []
    for s in split_raw(raw, cfg):
        if s in ("", "."):
            continue
        if s == "..":
            if not stack:
                return Reject("escape")
            stack.pop()
            continue
        stack.append(s)
    return tuple(stack)


def accept(pos: tuple[str, ...], cfg: Config, root: str = "") -> str | Reject:
    """§ 3.5 step 2, on the composed string root ⊕ pos (§ 3.6)."""
    full = segments(root) + pos
    for s in full:
        if not floor_ok(s):
            return Reject("floor")
        if not cfg.segment_ok(s) or cfg.norm(s) != s:
            return Reject("tier")
    if cfg.max_bytes is not None and len("/".join(full).encode()) > cfg.max_bytes:
        return Reject("tier")
    return "/".join(pos)


def nu(raw: str, cfg: Config, root: str = "") -> str | Reject:
    pos = walk(raw, cfg)
    if isinstance(pos, Reject):
        return pos
    return accept(pos, cfg, root)


def join(k: str, p: str, cfg: Config, root: str = "") -> str | Reject:
    """§ 3.5: k ⊕ p = ν(k/p)."""
    return nu(k + "/" + p, cfg, root)


# --- spec 051 stores ------------------------------------------------------


@dataclass
class Store:
    folders: set[int]
    items: set[int]
    root: int
    contains: set[tuple[int, int]]
    name: dict[int, str]
    _keys: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def universe(self) -> set[int]:
        return self.folders | self.items

    def container(self, x: int) -> int:
        (p,) = [p for (p, y) in self.contains if y == x]
        return p

    def key_of(self, x: int) -> str:
        names: list[str] = []
        while x != self.root:
            names.append(self.name[x])
            x = self.container(x)
        return "/".join(reversed(names))

    def keys(self) -> dict[str, int]:
        if not self._keys:
            self._keys = {self.key_of(x): x for x in self.universe}
        return self._keys

    def kind(self, x: int) -> str:
        return "folder" if x in self.folders else "item"


def axiom_violations(s: Store) -> list[str]:
    """TREE-001 to TREE-008 on a finite store."""
    out = []
    u = s.universe
    if s.folders & s.items:
        out.append("TREE-001")
    if s.root not in s.folders:
        out.append("TREE-002")
    if any(p not in s.folders for (p, _) in s.contains):
        out.append("TREE-003")
    for x in u:
        cs = [p for (p, y) in s.contains if y == x]
        if len(cs) > 1:
            out.append("TREE-004")
        if x == s.root and cs:
            out.append("TREE-005")
    for x in u:  # TREE-006: walk up must reach root without a cycle
        seen, y = set(), x
        while y != s.root:
            cs = [p for (p, z) in s.contains if z == y]
            if len(cs) != 1 or y in seen:
                out.append("TREE-006")
                break
            seen.add(y)
            y = cs[0]
    if s.name[s.root] != "":
        out.append("TREE-007")
    for x in u - {s.root}:
        if s.name[x] == "" or "/" in s.name[x]:
            out.append("TREE-007")
    for p in s.folders:
        kids = [y for (q, y) in s.contains if q == p]
        if len({s.name[y] for y in kids}) != len(kids):
            out.append("TREE-008")
    return out


# --- § 3.7 resolution -------------------------------------------------------


def resolve(k: str, s: Store) -> tuple:
    keys = s.keys()
    segs = segments(k)
    n = len(segs)
    j = max(i for i in range(n + 1) if prefix(k, i) in keys)
    e = keys[prefix(k, j)]
    if j == n:
        return ("found", e, s.kind(e))
    if e in s.items:
        return ("blocked", prefix(k, j))
    if j == n - 1:
        return ("absent",)
    return ("absent_ancestor", prefix(k, j))


# --- § 3.6 child stores ---------------------------------------------------


def child_resolve(s: Store, c: str, k: str) -> tuple:
    """§ 3.6: a child at c resolves k as S resolves c ⊕ k, in every state."""
    return resolve("/".join(segments(c) + segments(k)), s)


def child_view(s: Store, c: str) -> Store | None:
    """The child's own store, which exists only at a folder c (K12)."""
    r = resolve(c, s)
    if r[0] == "found" and r[2] == "folder":
        e = r[1]
        below = c + "/" if c else ""  # at ε every key is below the root
        sub = {x for x in s.universe if x == e or (s.key_of(x) + "/").startswith(below)}
        return Store(
            folders=s.folders & sub,
            items=s.items & sub,
            root=e,
            contains={(p, y) for (p, y) in s.contains if p in sub and y in sub},
            name={x: ("" if x == e else s.name[x]) for x in sub},
        )
    return None  # absent or item c: no store of its own; see child_resolve
