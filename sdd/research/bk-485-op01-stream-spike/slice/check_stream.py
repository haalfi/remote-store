"""Check stream_model against stream_rows.toml and slice invariants (spike).

Usage (repo root): hatch run python sdd/research/bk-485-op01-stream-spike/slice/check_stream.py

1. Rows: every non-open row is replayed against the model.
2. Invariants: a Hypothesis state machine drives random call sequences with
   injected faults; an oracle written from the decisions, not from the model,
   checks every step.
3. Traceability: each slice decision must be hit by >= 1 row and >= 1 invariant.
"""

from __future__ import annotations

import contextlib
import sys
import tomllib
import unittest
import warnings
from pathlib import Path

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from stream_model import CLOSED, EXHAUSTED, OPEN, Cancelled, Env, Stream, Unavailable

HERE = Path(__file__).parent
ROWS = tomllib.loads((HERE / "stream_rows.toml").read_text(encoding="utf-8"))["row"]
SLICE = ["D6", "D7", "D15", "D16", "D17", "D18", "D20", "D36"]

# Invariants checked by the state machine, with the decisions they come from.
INVARIANTS = {
    "P03 delivered bytes are a prefix of the content": ["D6"],
    "P03b position equals bytes delivered": ["D6", "D2"],
    "P05 Failed is sticky: same category until close": ["D16", "D18"],
    "P06 Closed is absorbing: reads ValueError, close no-op": ["D15", "D18"],
    "P07 a cancelled read closes the stream": ["D20"],
    "P08 close() raises no storage failure": ["D36"],
    "P09 chunks are non-empty and at most size": ["D7"],
    "P10 a failed transfer delivers no bytes": ["D6", "D16"],
    "P11 collect warns iff not closed, then releases": ["D17"],
}


# -- 1. rows -----------------------------------------------------------------


def setup(row: dict) -> tuple[Stream | None, Env]:
    env = Env()
    if row["state"] == "New":
        return None, env
    s = Stream(row["content"].encode(), env)
    match row["state"]:
        case "Open":
            if row.get("pos"):
                s.read(row["pos"])
        case "Exhausted":
            s.read()
        case "Failed":
            env.fail = True
            with contextlib.suppress(Unavailable):
                s.read(1)
        case "Closed":
            s.close()
    assert s.state == row["state"], f"setup reached {s.state}"
    return s, env


def apply(s: Stream | None, env: Env, row: dict) -> tuple[Stream, object]:
    if row.get("inject"):
        setattr(env, row["inject"], True)
    args = row.get("args", {})
    match row["event"]:
        case "open":
            s = Stream(row["content"].encode(), env)
            return s, None
        case "read":
            return s, s.read(args["n"])
        case "readinto":
            buf = bytearray(args["n"])
            return s, bytes(buf[: s.readinto(buf)])
        case "readline":
            return s, s.readline()
        case "chunks":
            return s, list(s.chunks(args["size"]))
        case "close":
            return s, s.close()
        case "collect":
            return s, s.collect()
    raise AssertionError(f"unknown event {row['event']}")


def check_row(row: dict) -> str | None:
    """Return None on pass, else a failure message."""
    s, env = setup(row)
    expect = row.get("expect", {})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            s, got = apply(s, env, row)
        except (Exception, Cancelled) as exc:  # noqa: BLE001 - categories are data here
            if expect.get("raises") != type(exc).__name__:
                return f"raised {type(exc).__name__}, expected {expect or 'no raise'}"
            if row["state"] != "New" and s.state != row["next"]:
                return f"state {s.state}, expected {row['next']}"
            return None
    if "raises" in expect:
        return f"returned, expected {expect['raises']}"
    if "returns" in expect:
        want = None if expect["returns"] == "None" else expect["returns"].encode()
        if got != want:
            return f"returned {got!r}, expected {want!r}"
    if "concat" in expect:
        if b"".join(got) != expect["concat"].encode():
            return f"chunks {got!r} do not concatenate to {expect['concat']!r}"
        if any(not 0 < len(c) <= expect["max"] for c in got):
            return f"chunk size outside (0, {expect['max']}]: {got!r}"
    warned = {w.category.__name__ for w in caught}
    if expect.get("warns") and expect["warns"] not in warned:
        return f"no {expect['warns']}"
    if not expect.get("warns") and "ResourceWarning" in warned:
        return "unexpected ResourceWarning"
    if s.state != row["next"]:
        return f"state {s.state}, expected {row['next']}"
    return None


# -- 2. invariants -------------------------------------------------------------

faults = st.sampled_from([None, "fail", "cancel"])


class StreamMachine(RuleBasedStateMachine):
    """Oracle state: delivered bytes and status live | failed | closed."""

    @initialize(content=st.binary(max_size=12))
    def open(self, content: bytes) -> None:
        self.content, self.env = content, Env()
        self.s = Stream(content, self.env)
        self.delivered = b""
        self.status = "live"

    def _reset_env(self) -> None:
        self.env.fail = self.env.cancel = self.env.release_fail = False

    def _expect_read(self, n: int, fault: str | None, call, *, chunk: bool = False) -> None:
        """chunk=True: D7 allows any non-empty prefix of at most n bytes (RF8), not exactly n."""
        remaining = self.content[len(self.delivered) :]
        want = remaining if n < 0 else remaining[:n]
        if fault:
            setattr(self.env, fault, True)
        try:
            got = call()
        except ValueError:
            assert self.status == "closed", "P06: ValueError only when closed"
            return
        except Unavailable:
            # sticky (D16), or a fail that reached the backend; at the end too (F10, RF6)
            assert self.status == "failed" or (self.status == "live" and fault == "fail"), "P05/P10"
            self.status = "failed"  # P10: delivered unchanged
            return
        except Cancelled:
            # D20 in every state but Closed (O45, RF5), whether or not bytes remain
            assert self.status != "closed", "P07: cancelled while closed"
            assert fault == "cancel", "P07: Cancelled without a cancel fault"
            self.status = "closed"
            return
        finally:
            self._reset_env()
        assert self.status == "live", f"P05/P06: read succeeded while {self.status}"
        if chunk:
            assert remaining.startswith(got), f"P03: chunk {got!r} is not the next bytes"
            assert bool(got) == bool(want), f"P09: chunk {got!r} with {len(want)} bytes remaining"
        else:
            assert got == want, f"P03: got {got!r}, expected {want!r}"
        assert not (fault and want), "a fault on a needed transfer must surface"
        self.delivered += got

    @rule(n=st.integers(-1, 8), fault=faults)
    def read(self, n: int, fault: str | None) -> None:
        self._expect_read(n, fault, lambda: self.s.read(n))

    @rule(size=st.integers(1, 5), take=st.integers(1, 4), fault=faults)
    def chunks(self, size: int, take: int, fault: str | None) -> None:
        for _ in range(take):
            before = len(self.delivered)

            def one() -> bytes:
                chunk = next(iter(self.s.chunks(size)), b"")
                assert chunk == b"" or 0 < len(chunk) <= size, "P09"
                return chunk

            self._expect_read(size, fault, one, chunk=True)
            fault = None  # fault applies to the first chunk only
            if self.status != "live" or len(self.delivered) == before:
                return

    @rule(fault=st.sampled_from([None, "release_fail", "cancel"]))
    def close(self, fault: str | None) -> None:
        if fault:
            setattr(self.env, fault, True)
        try:
            self.s.close()
        except Cancelled:
            assert fault == "cancel", "P08: Cancelled without a cancel fault"
            assert self.status != "closed", "P08: close() of a closed stream raised"
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"P08: close raised {exc!r}") from exc
        finally:
            self._reset_env()
        self.status = "closed"

    @rule()
    def collect(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.s.collect()
        warned = any(w.category is ResourceWarning for w in caught)
        assert warned == (self.status != "closed"), "P11"
        self.status = "closed"

    @invariant()
    def state_matches_oracle(self) -> None:
        assert self.content.startswith(self.delivered), "P03"
        assert self.s.pos == len(self.delivered), "P03b"
        if self.status == "closed":
            assert self.s.state == CLOSED
        elif self.status == "failed":
            assert self.s.state == "Failed"
        else:
            done = len(self.delivered) == len(self.content)
            assert self.s.state == (EXHAUSTED if done else OPEN)


# -- 3. report -----------------------------------------------------------------


def main() -> int:
    failures = 0
    print("Rows")
    for row in ROWS:
        if row.get("open"):
            print(f"  {row['id']} OPEN    {row['open']} ({row['event']} in {row['state']})")
            continue
        err = check_row(row)
        failures += err is not None
        tag = "FAIL" if err else ("PASS*" if row.get("assumed") else "PASS")
        print(f"  {row['id']} {tag:<7} {'/'.join(row['src'])}" + (f": {err}" if err else ""))

    print("\nInvariants (Hypothesis, 300 examples)")
    case = StreamMachine.TestCase
    case.settings = settings(max_examples=300, stateful_step_count=30, deadline=None)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(case)
    )
    failures += len(result.failures) + len(result.errors)

    print("\nTraceability")
    for d in SLICE:
        rows = [r["id"] for r in ROWS if d in r["src"]]
        invs = [k.split()[0] for k, v in INVARIANTS.items() if d in v]
        gap = "" if rows and invs else "  <-- GAP"
        print(f"  {d:<4} rows {','.join(rows) or '-'}  invariants {','.join(invs) or '-'}{gap}")
        failures += bool(gap)
    assumed = [r["id"] for r in ROWS if r.get("assumed")]
    print(f"\nAssumed cells (PASS*): {len(assumed)} {', '.join(assumed)}")
    print(f"Result: {'FAIL' if failures else 'OK'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
