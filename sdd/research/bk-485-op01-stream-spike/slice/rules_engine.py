"""Interpret stream_rules.toml as an oracle (spike, step 2b).

The oracle tracks state/content/pos, picks the one rule whose guard matches a
call, judges an observation against it, then applies its effect. Guards and
effects are trusted Python expressions from the rules file (spike only).
"""

from __future__ import annotations

import itertools
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RULES_FILE = Path(__file__).with_name("stream_rules.toml")
SAFE = {"__builtins__": {}, "len": len, "min": min}


@dataclass(frozen=True)
class Obs:
    """What a caller can see from one call."""

    got: object = None  # returned value, if no raise
    raised: str | None = None  # category name
    warns: frozenset[str] = frozenset()


@dataclass
class Oracle:
    content: bytes
    state: str = "New"
    pos: int = 0
    spec: dict = field(default_factory=lambda: tomllib.loads(RULES_FILE.read_text(encoding="utf-8")))

    def _scope(self, event: str, n: int, inject: str | None, got: object = None) -> dict:
        env = {
            "state": self.state,
            "content": self.content,
            "pos": self.pos,
            "event": event,
            "n": n,
            "inject": inject,
            "got": got,
        }
        for name, expr in self.spec["derive"].items():
            if name == "to_after" and not isinstance(got, bytes):
                continue  # needs a returned byte string
            env[name] = eval(expr, SAFE, env)  # noqa: S307 - trusted spike rules
        return env

    def matches(self, event: str, n: int, inject: str | None) -> list[dict]:
        env = self._scope(event, n, inject)
        return [r for r in self.spec["rule"] if event in r["on"] and "open" not in r and eval(r["when"], SAFE, env)]  # noqa: S307

    def step(self, event: str, n: int, inject: str | None, obs: Obs) -> tuple[str, str | None]:
        """Judge obs; on success apply the effect. Returns (rule id, error or None)."""
        (rule,) = self.matches(event, n, inject)  # completeness/disjointness: see check_rules
        env = self._scope(event, n, inject, obs.got)
        want_warn = frozenset([rule["warns"]]) if "warns" in rule else frozenset()
        if obs.warns != want_warn:
            return rule["id"], f"warnings {set(obs.warns) or '{}'}, expected {set(want_warn) or '{}'}"
        if "raises" in rule:
            if obs.raised != rule["raises"]:
                return rule["id"], f"{_show(obs)}, expected raise {rule['raises']}"
        elif obs.raised is not None:
            return rule["id"], f"raised {obs.raised}, expected success"
        elif "accept" in rule and not eval(rule["accept"], SAFE, env):  # noqa: S307
            return rule["id"], f"{_show(obs)}, rejected by: {rule['accept']}"
        if "advance" in rule:
            self.pos += eval(rule["advance"], SAFE, env)  # noqa: S307
        if "to" in rule:
            self.state = eval(rule["to"], SAFE, env)  # noqa: S307
        return rule["id"], None


def _show(obs: Obs) -> str:
    return f"raised {obs.raised}" if obs.raised else f"returned {obs.got!r}"


# -- static check: every call in a finite domain matches exactly one rule --------

EVENTS = ["read", "readinto", "readline", "chunk", "close", "collect", "seekable"]
INJECTS = [None, "fail", "cancel", "release_fail"]


def check_rules() -> list[str]:
    problems = []
    for content in (b"", b"a", b"ab\nc"):
        # Open before the end, Exhausted at it; Failed and Closed are reachable at any position
        every = range(len(content) + 1)
        for state, pos in (
            [("Open", p) for p in range(len(content))]
            + [("Exhausted", len(content))]
            + [(s, p) for s in ("Failed", "Closed") for p in every]
        ):
            o = Oracle(content, state, pos)
            for event, inject in itertools.product(EVENTS, INJECTS):
                for n in (-2, -1, 0, 1, 2, 5):
                    hit = [r["id"] for r in o.matches(event, n, inject)]
                    if len(hit) != 1:
                        problems.append(
                            f"{state} pos={pos} {content!r} {event}(n={n}) inject={inject}: {hit or 'no rule'}"
                        )
    o = Oracle(b"x")
    if [r["id"] for r in o.matches("open", 0, None)] != ["N1"]:
        problems.append("open from New: not exactly N1")
    return problems
