"""Run stream_rules.toml as an oracle against implementations (spike, step 4).

Usage (repo root): hatch run python sdd/research/bk-485-op01-stream-spike/slice/conform.py

1. Static: every call in a finite domain matches exactly one rule.
2. Conformance: a Hypothesis state machine drives an implementation (SUT)
   through random calls; the rules judge each observation. Only observables are
   compared: return value, raised category, warnings. A divergence is recorded
   with its trace and ends that example, so one run reports every diverging rule.
3. Report per SUT: rules hit, rules diverged (shortest trace), rules not
   exercised because the SUT offers no such event or fault injection.
"""

from __future__ import annotations

import contextlib
import errno
import gc
import io
import shutil
import sys
import tempfile
import warnings
from collections import defaultdict
from pathlib import Path

import stream_model as m
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule
from rules_engine import Obs, Oracle, check_rules

import remote_store.backends._local as local_mod
from remote_store import Store
from remote_store._errors import BackendUnavailable
from remote_store.backends import LocalBackend

WORK = Path(__file__).resolve().parents[4] / "tmp" / "op01-stream-spike"  # repo tmp/, gitignored


class SUT:
    """Adapter: perform one event on a stream, return the observation."""

    events: list[str]
    injects: list[str | None] = [None]
    n_min = -2  # smallest n drawn for read/chunk
    note = ""
    stream: object
    # exception class -> category name; first isinstance match wins
    categories: dict = {ValueError: "ValueError", m.Unavailable: "Unavailable", m.Cancelled: "Cancelled"}

    def category(self, exc: BaseException) -> str:
        for cls, name in self.categories.items():
            if isinstance(exc, cls):
                return name
        return f"other:{type(exc).__name__}"

    def perform(self, event: str, n: int, inject: str | None) -> tuple[Obs, str | None]:
        """Return the observation and the fault that actually reached the backend."""
        self.inject(inject)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                got = self.call(event, n)
                raised = None
            except (Exception, m.Cancelled, KeyboardInterrupt) as exc:  # noqa: BLE001 - categories are data
                got, raised = None, self.category(exc)
            if event == "collect":
                gc.collect()
        fired = self.fired(inject)
        self.inject(None)
        warns = frozenset(w.category.__name__ for w in caught if w.category is ResourceWarning)
        return Obs(got, raised, warns), fired

    def fired(self, inject: str | None) -> str | None:
        return inject

    def call(self, event: str, n: int) -> object:
        s = self.stream
        match event:
            case "read":
                return s.read(n)
            case "readinto":
                buf = bytearray(max(n, 0))
                return bytes(buf[: s.readinto(buf)])
            case "readline":
                return s.readline()
            case "chunk":
                return next(iter(s.chunks(n)), b"")
            case "close":
                return s.close()
            case "seekable":
                return s.seekable()
            case "collect":
                self.stream = None  # drop the last reference; gc runs in perform()
                return None
        raise AssertionError(event)

    def inject(self, name: str | None) -> None:
        pass

    def teardown(self) -> None:
        pass


class ModelSUT(SUT):
    name = "reference model (stream_model.py)"
    events = ["read", "readinto", "readline", "chunk", "close", "collect", "seekable"]
    injects = [None, "fail", "cancel", "release_fail"]

    def __init__(self, content: bytes) -> None:
        self.env = m.Env()
        self.stream = m.Stream(content, self.env)

    def inject(self, name: str | None) -> None:
        self.env.fail = self.env.cancel = self.env.release_fail = False
        if name:
            setattr(self.env, name, True)

    def fired(self, inject: str | None) -> str | None:
        return inject if inject and not getattr(self.env, inject) else None  # consumed = fired

    def call(self, event: str, n: int) -> object:
        if event == "collect":
            s, self.stream = self.stream, None
            s.collect()  # the model's stand-in for finalisation
            return None
        return super().call(event, n)


class Faults:
    """One armed fault; the faulty raw file consumes it when it reaches the OS layer."""

    def __init__(self) -> None:
        self.armed: str | None = None
        self.fired: str | None = None

    def take(self, *names: str) -> str | None:
        if self.armed in names:
            self.fired, self.armed = self.armed, None
            return self.fired
        return None


class FaultyRaw(io.RawIOBase):
    """Raw file below BufferedReader: the OS layer Local's stream reads through.

    fail         readinto raises OSError(EIO)      (E8/E13 analogue)
    cancel       readinto, or close after the release, raises KeyboardInterrupt (E14, sync form)
    release_fail close releases the file, then raises OSError (D36 scenario)

    A cancel on close fires after the release: CPython delivers KeyboardInterrupt
    when control returns to the eval loop, after the C FileIO's close(2) has run.
    """

    def __init__(self, path: str, faults: Faults) -> None:
        self._f = io.FileIO(path, "rb")
        self._faults = faults

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return self._f.seekable()

    def seek(self, pos: int, whence: int = 0) -> int:
        return self._f.seek(pos, whence)

    def tell(self) -> int:
        return self._f.tell()

    def fileno(self) -> int:
        return self._f.fileno()

    def _dealloc_warn(self, source) -> None:
        self._f._dealloc_warn(source)  # BufferedReader asks its raw for the ResourceWarning

    def readinto(self, b) -> int:
        match self._faults.take("fail", "cancel"):
            case "fail":
                raise OSError(errno.EIO, "injected I/O error")
            case "cancel":
                raise KeyboardInterrupt
        return self._f.readinto(b)

    def close(self) -> None:
        if self.closed:
            return
        fault = self._faults.take("release_fail", "cancel")
        self._f.close()
        super().close()
        if fault == "release_fail":
            raise OSError(errno.EIO, "injected release failure")
        if fault == "cancel":
            raise KeyboardInterrupt  # delivered after the release, as for a C FileIO


class LocalSUT(SUT):
    name = "Local backend (Store(LocalBackend).read)"

    def __init__(self, content: bytes) -> None:
        WORK.mkdir(parents=True, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=WORK)
        Path(self.dir, "item.bin").write_bytes(content)
        self.stream = Store(LocalBackend(self.dir)).read("item.bin")
        offered = ["read", "readinto", "readline", "chunk", "close", "seekable"]
        self.events = [e for e in offered if e != "chunk" or hasattr(self.stream, "chunks")] + ["collect"]

    def teardown(self) -> None:
        if self.stream is not None:
            with contextlib.suppress(Exception, KeyboardInterrupt):  # a faulty close in cleanup
                self.stream.close()
        shutil.rmtree(self.dir, ignore_errors=True)


LOCAL_CATEGORIES = {
    BackendUnavailable: "Unavailable",  # the library's own category
    ValueError: "ValueError",
    KeyboardInterrupt: "Cancelled",
}


class FaultyLocalSUT(LocalSUT):
    """Local with faults injected below the library, judged strictly (D27 typing)."""

    name = "Local + faults, strict typing (library categories only)"
    injects = [None, "fail", "cancel", "release_fail"]
    n_min = -1  # F9 (n < -1) already recorded; parked so examples reach the faults
    note = "parked: F9 (read(n < -1)) and Z1 (seekable); see the plain Local run"
    categories = LOCAL_CATEGORIES

    def __init__(self, content: bytes) -> None:
        self.faults = Faults()

        def faulty_open(path, mode="r", *args, **kwargs):
            assert mode == "rb", mode
            return io.BufferedReader(FaultyRaw(path, self.faults))

        local_mod.open = faulty_open  # shadows builtins.open for LocalBackend.read only
        try:
            super().__init__(content)
        finally:
            del local_mod.open
        assert isinstance(self.stream.raw, FaultyRaw), "patch did not reach LocalBackend.read"
        self.events = [e for e in self.events if e != "seekable"]

    def inject(self, name: str | None) -> None:
        self.faults.armed, self.faults.fired = name, None

    def fired(self, inject: str | None) -> str | None:
        return self.faults.fired

    def teardown(self) -> None:
        self.faults.armed = None
        super().teardown()


class FaultyLocalLenientSUT(FaultyLocalSUT):
    """Same, but any OSError counts as Unavailable: checks the state machine alone."""

    name = "Local + faults, protocol only (OSError counted as Unavailable)"
    categories = {**LOCAL_CATEGORIES, OSError: "Unavailable"}


def make_machine(sut_cls: type[SUT], log: dict) -> type[RuleBasedStateMachine]:
    class Conformance(RuleBasedStateMachine):
        @initialize(content=st.binary(max_size=10).map(lambda b: b.replace(b"\x00", b"\n")))
        def open(self, content: bytes) -> None:
            self.sut = sut_cls(content)
            self.oracle = Oracle(content)
            self.trace = [f"open({content!r})"]
            self.done = False
            rid, err = self.oracle.step("open", 0, None, Obs())
            log["hit"][rid] += 1
            log["events"] = self.sut.events
            log["injects"] = self.sut.injects

        @rule(data=st.data())
        def call(self, data) -> None:
            if self.done:
                return  # example finished: divergence or collected stream
            event = data.draw(st.sampled_from(self.sut.events))
            lo = 0 if event == "readinto" else self.sut.n_min  # readinto's n is a buffer length
            n = -1 if event == "readline" else data.draw(st.integers(lo, 6))
            # the rules give collection no fault behaviour, so none is injected there
            inject = None if event == "collect" else data.draw(st.sampled_from(self.sut.injects))
            obs, fired = self.sut.perform(event, n, inject)
            tag = f" !{inject}" + ("" if fired else " (not reached)") if inject else ""
            self.trace.append(f"{event}({n}){tag}")
            rid, err = self.oracle.step(event, n, fired, obs)  # judge the fault that reached the backend
            log["hit"][rid] += 1
            if err:
                prev = log["diverged"].get(rid)
                if prev is None or len(self.trace) < len(prev[1]):
                    log["diverged"][rid] = (err, list(self.trace))
                self.done = True  # oracle and SUT may disagree on state from here
            if event == "collect":
                self.done = True  # no stream left to call

        def teardown(self) -> None:
            self.sut.teardown()

    Conformance.TestCase.settings = settings(
        max_examples=400, stateful_step_count=25, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    return Conformance


def run(sut_cls: type[SUT], rules: list[dict]) -> int:
    log = {"hit": defaultdict(int), "diverged": {}, "events": [], "injects": []}
    make_machine(sut_cls, log).TestCase("runTest").runTest()
    print(f"\n== {sut_cls.name}")
    print(f"   events offered: {', '.join(log['events'])}; injects: {', '.join(map(str, log['injects']))}")
    if sut_cls.note:
        print(f"   {sut_cls.note}")
    for r in rules:
        if "open" in r:
            print(f"   {r['id']:<4} OPEN      {r['open']}")
            continue
        hits = log["hit"].get(r["id"], 0)
        if r["id"] in log["diverged"]:
            err, trace = log["diverged"][r["id"]]
            tag = "DIVERGED"
        elif hits:
            tag = "PASS*" if "assumed" in r else "PASS"
        else:
            tag = "unexercised"
        line = f"   {r['id']:<4} {tag:<11} {'/'.join(r['src']):<9} hits={hits}"
        if tag == "DIVERGED":
            line += f"\n        {err}\n        trace: {' -> '.join(trace)}"
        print(line)
    return len(log["diverged"])


def main() -> int:
    problems = check_rules()
    print("Static check (each call matches exactly one rule):", "OK" if not problems else "FAIL")
    for p in problems[:15]:
        print("   ", p)
    rules = Oracle(b"").spec["rule"]
    suts = (ModelSUT, LocalSUT, FaultyLocalSUT, FaultyLocalLenientSUT)
    diverged = {sut.name: run(sut, rules) for sut in suts}
    print("\nSummary:", "; ".join(f"{k}: {v} rule(s) diverged" for k, v in diverged.items()))
    return 1 if problems else 0  # divergence on a real backend is a finding, not a script failure


if __name__ == "__main__":
    sys.exit(main())
